"""
Regression coverage for Finding 50's accounting_dimensions/transaction_dimensions/
entity_group_members column drift (docs/FINDING_50_SCOPE.md, docs/REMEDIATION_LOG.md).

`AccountingDimension` and `TransactionDimension` are both confirmed dead code (zero real
construction sites anywhere in the codebase), but were still tracked as Finding 50 tables:
- `AccountingDimension.sort_order`/`extra_data` had no matching live column (the live column is
  `metadata`); its `SQLEnum(DimensionType)` had no explicit `name=`, so SQLAlchemy would have bound
  against an auto-derived `dimensiontype` type that doesn't exist (the real type is
  `dimension_type`, with an underscore). The live enum type was also missing 3 of 9 Python members
  (location/sales_channel/product_line).
- `TransactionDimension` inherits `BaseModel`, which always adds a NOT NULL `updated_at` -- the
  live table only had `created_at`.

`EntityGroupMember` had a real, unmapped `joined_at` column (server-defaulted, so not a crash, but
a dead attribute) and a `consolidation_method` narrower than the live column.
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import BusinessEntity
from app.models.organization import Organization
from app.models.transaction import Transaction, TransactionType
from app.models.advanced_accounting import (
    AccountingDimension,
    DimensionType,
    TransactionDimension,
)
from app.services.consolidation_service import ConsolidationService


class TestAccountingDimensionPersistence:
    async def test_all_dimension_types_are_valid(
        self, db_session: AsyncSession, test_entity: BusinessEntity,
    ):
        """Confirms the enum-type-name fix and the 3 backfilled enum values all work."""
        for i, dtype in enumerate(DimensionType):
            dimension = AccountingDimension(
                entity_id=test_entity.id,
                dimension_type=dtype,
                code=f"DIM-{i}",
                name=f"{dtype.value} dimension",
                dimension_metadata={"source": "test"},
            )
            db_session.add(dimension)
        await db_session.commit()


class TestTransactionDimensionPersistence:
    async def test_create_has_updated_at(
        self, db_session: AsyncSession, test_entity: BusinessEntity,
    ):
        transaction = Transaction(
            entity_id=test_entity.id,
            transaction_type=TransactionType.EXPENSE,
            transaction_date=date(2026, 9, 1),
            amount=Decimal("10000.00"),
            total_amount=Decimal("10000.00"),
            description="Office supplies",
        )
        db_session.add(transaction)
        await db_session.commit()
        await db_session.refresh(transaction)

        dimension = AccountingDimension(
            entity_id=test_entity.id,
            dimension_type=DimensionType.DEPARTMENT,
            code="DEPT-OPS",
            name="Operations",
        )
        db_session.add(dimension)
        await db_session.commit()
        await db_session.refresh(dimension)

        txn_dimension = TransactionDimension(
            transaction_id=transaction.id,
            dimension_id=dimension.id,
            allocation_percentage=Decimal("100.00"),
            allocated_amount=Decimal("10000.00"),
        )
        db_session.add(txn_dimension)
        await db_session.commit()
        await db_session.refresh(txn_dimension)

        assert txn_dimension.id is not None
        assert txn_dimension.updated_at is not None


class TestEntityGroupMemberPersistence:
    async def test_add_group_member_has_joined_at(
        self, db_session: AsyncSession, test_organization: Organization, test_entity: BusinessEntity,
    ):
        other_entity = BusinessEntity(
            name="Subsidiary Ltd",
            organization_id=test_organization.id,
            business_type=test_entity.business_type,
            tin="98765432-0001",
            rc_number="RC987654",
            address_line1="456 Subsidiary Road",
            city="Abuja",
            state="FCT",
            email="subsidiary@example.com",
            phone="+234 802 000 0000",
            is_vat_registered=True,
        )
        db_session.add(other_entity)
        await db_session.commit()
        await db_session.refresh(other_entity)

        service = ConsolidationService(db_session)
        group = await service.create_entity_group(
            organization_id=test_organization.id,
            name="Test Group",
            parent_entity_id=test_entity.id,
        )
        member = await service.add_group_member(
            group_id=group.id,
            entity_id=other_entity.id,
            ownership_percentage=Decimal("75.00"),
        )

        assert member.id is not None
        assert member.joined_at is not None
        assert member.consolidation_method == "full"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
