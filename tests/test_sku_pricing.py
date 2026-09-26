"""
Regression coverage for Finding 50's sku_pricing column drift
(docs/FINDING_50_SCOPE.md, docs/REMEDIATION_LOG.md).

app/services/advanced_billing_service.py's CurrencyService.get_pricing_for_currency() reads
foreign-currency prices via getattr(pricing, f"base_price_monthly_{currency}", None) -- a pattern
that only works if the model actually declares those columns. It didn't: SKUPricing had zero USD/
EUR/GBP fields even though the live table has all 6 (base_price_monthly_usd/base_price_annual_usd/
base_price_monthly_eur/base_price_annual_eur/base_price_monthly_gbp/base_price_annual_gbp). The
getattr default silently swallowed the mismatch -- every currency lookup fell back to live FX
conversion from NGN, ignoring any fixed foreign-currency price an admin had actually configured,
with no error to signal why.
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sku import SKUPricing, SKUTier
from app.services.advanced_billing_service import CurrencyService


class TestSKUPricingPersistence:
    async def test_fixed_usd_price_is_read_directly_not_via_fx_fallback(
        self, db_session: AsyncSession,
    ):
        pricing = SKUPricing(
            sku_tier=SKUTier.PROFESSIONAL,
            base_price_monthly=Decimal("75000.00"),
            base_price_annual=Decimal("765000.00"),
            base_price_monthly_usd=Decimal("49.00"),
            base_price_annual_usd=Decimal("499.00"),
            effective_from=date(2026, 1, 1),
            is_active=True,
        )
        db_session.add(pricing)
        await db_session.commit()
        await db_session.refresh(pricing)

        assert pricing.base_price_monthly_usd == Decimal("49.00")

        service = CurrencyService(db_session)
        monthly_usd = await service.get_pricing_for_currency(
            SKUTier.PROFESSIONAL, currency="USD", billing_cycle="monthly",
        )
        annual_usd = await service.get_pricing_for_currency(
            SKUTier.PROFESSIONAL, currency="USD", billing_cycle="annual",
        )

        assert monthly_usd == 49
        assert annual_usd == 499


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
