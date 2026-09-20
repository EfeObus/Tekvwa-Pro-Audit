"""
Regression coverage for Finding 50's fixed_assets/depreciation_entries column drift
(docs/FINDING_50_SCOPE.md, docs/REMEDIATION_LOG.md).

Before this fix, both FixedAssetService.create_asset() and .run_depreciation() always failed
with an UndefinedColumnError -- the models already declared the right Python attribute names,
but several of those columns (vendor_invoice_number/vat_recovered/disposal_amount/insured_value/
insurance_expiry on FixedAsset; period_year/period_month/depreciation_method/depreciation_rate/
posted_by_id on DepreciationEntry) never existed on the live tables at all.
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import BusinessEntity
from app.models.fixed_asset import AssetCategory, DepreciationMethod
from app.models.user import User
from app.services.fixed_asset_service import FixedAssetService


class TestFixedAssetPersistence:
    async def test_create_asset_with_full_fields(
        self, db_session: AsyncSession, test_entity: BusinessEntity, test_user: User,
    ):
        service = FixedAssetService(db_session)
        asset = await service.create_asset(
            entity_id=test_entity.id,
            name="Toyota Hilux",
            category=AssetCategory.MOTOR_VEHICLES,
            acquisition_date=date(2026, 1, 15),
            acquisition_cost=Decimal("25000000.00"),
            vendor_name="Toyota Nigeria Ltd",
            vendor_invoice_number="INV-2026-001",
            depreciation_method=DepreciationMethod.STRAIGHT_LINE,
            depreciation_rate=Decimal("20.00"),
            useful_life_years=5,
            condition="new",
            is_insured=True,
            insured_value=Decimal("25000000.00"),
            created_by_id=test_user.id,
        )

        assert asset.id is not None
        assert asset.entity_id == test_entity.id
        assert asset.vendor_invoice_number == "INV-2026-001"
        assert asset.condition == "new"
        assert asset.is_insured is True
        assert asset.insured_value == Decimal("25000000.00")
        assert asset.created_by_id == test_user.id
        assert asset.vat_recovered is False

    async def test_run_depreciation_creates_entries(
        self, db_session: AsyncSession, test_entity: BusinessEntity, test_user: User,
    ):
        service = FixedAssetService(db_session)
        asset = await service.create_asset(
            entity_id=test_entity.id,
            name="Office Generator",
            category=AssetCategory.OFFICE_EQUIPMENT,
            acquisition_date=date(2025, 1, 1),
            acquisition_cost=Decimal("1000000.00"),
            depreciation_method=DepreciationMethod.STRAIGHT_LINE,
            depreciation_rate=Decimal("20.00"),
            useful_life_years=5,
        )

        result = await service.run_depreciation(
            entity_id=test_entity.id,
            period_year=2026,
            period_month=None,
            posted_by_id=test_user.id,
            post_to_gl=False,
        )

        assert result["entries_created"] == 1

        await db_session.refresh(asset, attribute_names=["depreciation_entries"])
        assert len(asset.depreciation_entries) == 1
        entry = asset.depreciation_entries[0]
        assert entry.entity_id == test_entity.id
        assert entry.period_year == 2026
        assert entry.period_month is None
        assert entry.depreciation_method == DepreciationMethod.STRAIGHT_LINE
        assert entry.posted_by_id == test_user.id
        assert entry.depreciation_amount == Decimal("200000.00")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
