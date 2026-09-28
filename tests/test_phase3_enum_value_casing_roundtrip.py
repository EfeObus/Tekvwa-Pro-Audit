"""
Round-trip regression coverage for Phase 3 Finding 1 (docs/IMPLEMENTATION_ROADMAP.md §3.1,
docs/PRODUCTION_AUDIT_2026.md §1.2): before the `values_callable=lambda e: [m.value for m in e]`
fix, writing any non-default member of these enum columns raised
`invalid input value for enum <type>` at the database, since SQLAlchemy defaulted to sending the
Python member's uppercase `.name` against a live Postgres enum type that only has lowercase
labels. This must hit the real database (not a mock) to prove anything, since the bug is
Postgres's enum-label validation rejecting the value, not anything the ORM layer can catch itself.

Covers all 18 columns fixed under §3.1/§3.4 in this phase. The other 6 native-enum columns with a
genuine value-set divergence (not just casing) are intentionally excluded here -- see
docs/REMEDIATION_LOG.md's Phase 3 entry; they're blocked on a product decision, not fixed yet.

Important caveat (the same lesson already learned earlier in this phase): this suite runs against
`tests/conftest.py`'s `db_session` fixture, which is `Base.metadata.create_all()` against an
ephemeral test database, not a real Alembic-migrated one. `create_all()` always creates each native
enum type using the model's OWN current `column.type.enums` -- so it can never, by itself, catch
the casing-drift bug these fixes address (the type it creates and the values it writes always agree
with each other, tautologically). This suite's real value is proving the ORM mapping/row
construction is otherwise coherent for these columns; the actual regression protection against
casing drift specifically is `scripts/check_enum_value_casing.py`, which reads the real, migrated
database's live `pg_enum` labels.
"""
from datetime import date, timezone, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import BusinessEntity
from app.models.organization import Organization
from app.models.user import User
from app.models.sku import UsageEvent, UsageMetricType
from app.models.tax_2026 import (
    VATRecoveryRecord, VATRecoveryType, PITReliefDocument, ReliefType,
)
from app.models.fixed_asset import (
    FixedAsset, AssetCategory, AssetStatus, DepreciationMethod, DisposalType,
    DepreciationEntry,
)
from app.models.platform_api_key import PlatformApiKey, ApiKeyType, ApiKeyEnvironment
from app.models.emergency_control import EmergencyControl, EmergencyActionType
from app.models.accounting import FXRevaluation, FXRevaluationType, FXAccountType
from app.models.advanced_accounting import (
    AccountingDimension, DimensionType,
    Budget, BudgetPeriodType,
    ApprovalRequest, ApprovalStatus, ApprovalWorkflow,
    ThreeWayMatch, MatchingStatus, PurchaseOrder,
)
from app.models.vendor import Vendor
from app.models.invoice import Invoice, InvoiceStatus, VATTreatment


async def _round_trip(db_session: AsyncSession, row) -> None:
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)


class TestUsageEventsMetricType:
    async def test_every_member_round_trips(
        self, db_session: AsyncSession, test_organization: Organization,
    ):
        for member in UsageMetricType:
            event = UsageEvent(organization_id=test_organization.id, metric_type=member)
            await _round_trip(db_session, event)
            assert event.metric_type == member


class TestBusinessEntitiesBusinessType:
    async def test_every_member_round_trips(
        self, db_session: AsyncSession, test_organization: Organization,
    ):
        from app.models.entity import BusinessType
        for member in BusinessType:
            entity = BusinessEntity(
                name=f"Entity {member.value}",
                organization_id=test_organization.id,
                business_type=member,
                country="NG",
                currency="NGN",
                is_vat_registered=False,
            )
            await _round_trip(db_session, entity)
            assert entity.business_type == member


class TestVatRecoveryRecordsRecoveryType:
    async def test_every_member_round_trips(
        self, db_session: AsyncSession, test_entity: BusinessEntity,
    ):
        for member in VATRecoveryType:
            record = VATRecoveryRecord(
                entity_id=test_entity.id,
                vat_amount=Decimal("100.00"),
                recovery_type=member,
                is_recoverable=True,
                has_valid_irn=True,
                transaction_date=date(2026, 1, 1),
                recovery_period_year=2026,
                recovery_period_month=1,
            )
            await _round_trip(db_session, record)
            assert record.recovery_type == member


class TestPitReliefDocumentsReliefType:
    async def test_every_member_round_trips(
        self, db_session: AsyncSession, test_entity: BusinessEntity, test_user: User,
    ):
        for member in ReliefType:
            doc = PITReliefDocument(
                entity_id=test_entity.id,
                user_id=test_user.id,
                relief_type=member,
                fiscal_year=2026,
                claimed_amount=Decimal("50000.00"),
                is_verified=False,
            )
            await _round_trip(db_session, doc)
            assert doc.relief_type == member


class TestFixedAssetsEnumColumns:
    async def _make_asset(self, test_entity: BusinessEntity, **overrides) -> FixedAsset:
        defaults = dict(
            entity_id=test_entity.id,
            name="Test Asset",
            asset_code=f"FA-{uuid4().hex[:8]}",
            category=AssetCategory.OTHER,
            acquisition_date=date(2026, 1, 1),
            acquisition_cost=Decimal("100000.00"),
            depreciation_rate=Decimal("10.00"),
        )
        defaults.update(overrides)
        return FixedAsset(**defaults)

    async def test_every_category_round_trips(
        self, db_session: AsyncSession, test_entity: BusinessEntity,
    ):
        for member in AssetCategory:
            asset = await self._make_asset(test_entity, category=member)
            await _round_trip(db_session, asset)
            assert asset.category == member

    async def test_every_status_round_trips(
        self, db_session: AsyncSession, test_entity: BusinessEntity,
    ):
        for member in AssetStatus:
            asset = await self._make_asset(test_entity, status=member)
            await _round_trip(db_session, asset)
            assert asset.status == member

    async def test_every_depreciation_method_round_trips(
        self, db_session: AsyncSession, test_entity: BusinessEntity,
    ):
        for member in DepreciationMethod:
            asset = await self._make_asset(test_entity, depreciation_method=member)
            await _round_trip(db_session, asset)
            assert asset.depreciation_method == member

    async def test_every_disposal_type_round_trips(
        self, db_session: AsyncSession, test_entity: BusinessEntity,
    ):
        for member in DisposalType:
            asset = await self._make_asset(test_entity, disposal_type=member)
            await _round_trip(db_session, asset)
            assert asset.disposal_type == member


class TestDepreciationEntriesDepreciationMethod:
    async def test_every_member_round_trips(
        self, db_session: AsyncSession, test_entity: BusinessEntity,
    ):
        asset = FixedAsset(
            entity_id=test_entity.id,
            name="Depreciable Asset",
            asset_code=f"FA-{uuid4().hex[:8]}",
            category=AssetCategory.OFFICE_EQUIPMENT,
            acquisition_date=date(2026, 1, 1),
            acquisition_cost=Decimal("100000.00"),
            depreciation_rate=Decimal("20.00"),
        )
        await _round_trip(db_session, asset)

        for member in DepreciationMethod:
            entry = DepreciationEntry(
                asset_id=asset.id,
                entity_id=test_entity.id,
                opening_book_value=Decimal("100000.00"),
                depreciation_amount=Decimal("20000.00"),
                closing_book_value=Decimal("80000.00"),
                period_year=2026,
                depreciation_method=member,
                depreciation_rate=Decimal("20.00"),
            )
            await _round_trip(db_session, entry)
            assert entry.depreciation_method == member


class TestPlatformApiKeysEnumColumns:
    async def _make_key(self, **overrides) -> PlatformApiKey:
        defaults = dict(
            name="Test Key",
            api_key=f"key_{uuid4().hex}",
            masked_key="key_****",
            key_hash=uuid4().hex,
        )
        defaults.update(overrides)
        return PlatformApiKey(**defaults)

    async def test_every_key_type_round_trips(self, db_session: AsyncSession):
        for member in ApiKeyType:
            key = await self._make_key(key_type=member)
            await _round_trip(db_session, key)
            assert key.key_type == member

    async def test_every_environment_round_trips(self, db_session: AsyncSession):
        for member in ApiKeyEnvironment:
            key = await self._make_key(environment=member)
            await _round_trip(db_session, key)
            assert key.environment == member


class TestEmergencyControlsActionType:
    async def test_every_member_round_trips(
        self, db_session: AsyncSession, test_user: User,
    ):
        for member in EmergencyActionType:
            control = EmergencyControl(
                action_type=member,
                target_type="platform",
                initiated_by_id=test_user.id,
                reason="Round-trip regression test",
                started_at=datetime.now(timezone.utc),
            )
            await _round_trip(db_session, control)
            assert control.action_type == member


class TestFxRevaluationsEnumColumns:
    async def _make_account(self, test_entity: BusinessEntity):
        from app.models.accounting import ChartOfAccounts, AccountType, NormalBalance
        account = ChartOfAccounts(
            entity_id=test_entity.id,
            account_code=f"ACC-{uuid4().hex[:8]}",
            account_name="FX Test Account",
            account_type=AccountType.ASSET,
            normal_balance=NormalBalance.DEBIT,
            level=1,
            is_header=False,
        )
        return account

    async def test_every_revaluation_type_round_trips(
        self, db_session: AsyncSession, test_entity: BusinessEntity,
    ):
        account = await self._make_account(test_entity)
        await _round_trip(db_session, account)

        for member in FXRevaluationType:
            reval = FXRevaluation(
                entity_id=test_entity.id,
                revaluation_date=date(2026, 1, 1),
                revaluation_type=member,
                account_id=account.id,
                fx_account_type=FXAccountType.BANK,
                foreign_currency="USD",
                original_fc_amount=Decimal("1000.00"),
                original_exchange_rate=Decimal("1500.00"),
                original_ngn_amount=Decimal("1500000.00"),
                revaluation_rate=Decimal("1550.00"),
                revalued_ngn_amount=Decimal("1550000.00"),
                fx_gain_loss=Decimal("50000.00"),
                is_gain=True,
            )
            await _round_trip(db_session, reval)
            assert reval.revaluation_type == member

    async def test_every_fx_account_type_round_trips(
        self, db_session: AsyncSession, test_entity: BusinessEntity,
    ):
        account = await self._make_account(test_entity)
        await _round_trip(db_session, account)

        for member in FXAccountType:
            reval = FXRevaluation(
                entity_id=test_entity.id,
                revaluation_date=date(2026, 1, 1),
                revaluation_type=FXRevaluationType.UNREALIZED,
                account_id=account.id,
                fx_account_type=member,
                foreign_currency="USD",
                original_fc_amount=Decimal("1000.00"),
                original_exchange_rate=Decimal("1500.00"),
                original_ngn_amount=Decimal("1500000.00"),
                revaluation_rate=Decimal("1550.00"),
                revalued_ngn_amount=Decimal("1550000.00"),
                fx_gain_loss=Decimal("50000.00"),
                is_gain=True,
            )
            await _round_trip(db_session, reval)
            assert reval.fx_account_type == member


class TestAccountingDimensionsDimensionType:
    async def test_every_member_round_trips(
        self, db_session: AsyncSession, test_entity: BusinessEntity,
    ):
        for member in DimensionType:
            dimension = AccountingDimension(
                entity_id=test_entity.id,
                dimension_type=member,
                code=f"DIM-{uuid4().hex[:8]}",
                name=f"Dimension {member.value}",
                is_active=True,
            )
            await _round_trip(db_session, dimension)
            assert dimension.dimension_type == member


class TestBudgetsPeriodType:
    async def test_every_member_round_trips(
        self, db_session: AsyncSession, test_entity: BusinessEntity, test_user: User,
    ):
        for member in BudgetPeriodType:
            budget = Budget(
                entity_id=test_entity.id,
                name=f"Budget {member.value}",
                fiscal_year=2026,
                period_type=member,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
                created_by_id=test_user.id,
            )
            await _round_trip(db_session, budget)
            assert budget.period_type == member


class TestApprovalRequestsStatus:
    async def test_every_member_round_trips(
        self, db_session: AsyncSession, test_entity: BusinessEntity,
    ):
        workflow = ApprovalWorkflow(
            entity_id=test_entity.id,
            workflow_type="payment",
            name="Test Workflow",
            required_approvers=1,
            is_active=True,
        )
        await _round_trip(db_session, workflow)

        for member in ApprovalStatus:
            request = ApprovalRequest(
                entity_id=test_entity.id,
                workflow_id=workflow.id,
                resource_type="payment",
                resource_id=uuid4(),
                status=member,
            )
            await _round_trip(db_session, request)
            assert request.status == member


class TestThreeWayMatchesStatus:
    async def test_every_member_round_trips(
        self, db_session: AsyncSession, test_entity: BusinessEntity, test_user: User,
    ):
        vendor = Vendor(
            entity_id=test_entity.id,
            name="Test Vendor",
            tin_verified=False,
            is_vat_registered=False,
            is_active=True,
        )
        await _round_trip(db_session, vendor)

        po = PurchaseOrder(
            entity_id=test_entity.id,
            vendor_id=vendor.id,
            po_number=f"PO-{uuid4().hex[:8]}",
            po_date=date(2026, 1, 1),
            subtotal=Decimal("1000.00"),
            vat_amount=Decimal("75.00"),
            total_amount=Decimal("1075.00"),
            status="open",
            created_by_id=test_user.id,
        )
        await _round_trip(db_session, po)

        invoice = Invoice(
            entity_id=test_entity.id,
            invoice_number=f"INV-{uuid4().hex[:8]}",
            invoice_date=date(2026, 1, 1),
            due_date=date(2026, 1, 31),
            subtotal=Decimal("1000.00"),
            vat_amount=Decimal("75.00"),
            discount_amount=Decimal("0.00"),
            total_amount=Decimal("1075.00"),
            amount_paid=Decimal("0.00"),
            vat_treatment=VATTreatment.STANDARD,
            vat_rate=Decimal("7.5"),
            status=InvoiceStatus.DRAFT,
            is_disputed=False,
        )
        await _round_trip(db_session, invoice)

        for member in MatchingStatus:
            match = ThreeWayMatch(
                entity_id=test_entity.id,
                purchase_order_id=po.id,
                invoice_id=invoice.id,
                status=member,
                po_amount=Decimal("1075.00"),
                invoice_amount=Decimal("1075.00"),
            )
            await _round_trip(db_session, match)
            assert match.status == member
