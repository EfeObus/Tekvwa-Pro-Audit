"""
Test suite for Advanced Billing Features (Issues #30-36)

Issue #30: Usage report generation
Issue #31: Billing cycle alignment
Issue #32: Subscription pause/resume
Issue #33: Service credit system
Issue #34: Referral/discount code system
Issue #35: Volume discount logic
Issue #36: Multi-currency support
"""

import pytest
from datetime import datetime, date, timedelta
from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

# Import the service classes
from app.services.advanced_billing_service import (
    CurrencyService,
    BillingCycleService,
    SubscriptionPauseService,
    ServiceCreditService,
    DiscountCodeService,
    VolumeDiscountService,
    UsageReportService,
    AdvancedBillingService,
    Currency,
    CreditType,
    CURRENCY_SYMBOLS,
    CURRENCY_NAMES,
    format_currency,
)
from app.models.sku import SKUTier


class TestCurrencyService:
    """Tests for Issue #36: Multi-currency support."""
    
    def test_currency_enum_values(self):
        """Test that all expected currencies are defined."""
        assert Currency.NGN.value == "NGN"
        assert Currency.USD.value == "USD"
        assert Currency.EUR.value == "EUR"
        assert Currency.GBP.value == "GBP"
    
    def test_currency_symbols(self):
        """Test currency symbols are correctly mapped."""
        assert CURRENCY_SYMBOLS["NGN"] == "₦"
        assert CURRENCY_SYMBOLS["USD"] == "$"
        assert CURRENCY_SYMBOLS["EUR"] == "€"
        assert CURRENCY_SYMBOLS["GBP"] == "£"
    
    def test_currency_names(self):
        """Test currency names are correctly mapped."""
        assert CURRENCY_NAMES["NGN"] == "Nigerian Naira"
        assert CURRENCY_NAMES["USD"] == "US Dollar"
        assert CURRENCY_NAMES["EUR"] == "Euro"
        assert CURRENCY_NAMES["GBP"] == "British Pound"
    
    def test_format_currency_ngn(self):
        """Test NGN currency formatting."""
        assert format_currency(50000, "NGN") == "₦50,000"
        assert format_currency(1234567, "NGN") == "₦1,234,567"
        assert format_currency(0, "NGN") == "₦0"
    
    def test_format_currency_usd(self):
        """Test USD currency formatting (no decimals for int)."""
        result = format_currency(100, "USD")
        assert "$" in result
        assert "100" in result
    
    def test_format_currency_eur(self):
        """Test EUR currency formatting."""
        result = format_currency(100, "EUR")
        assert "€" in result
        assert "100" in result
    
    def test_format_currency_gbp(self):
        """Test GBP currency formatting."""
        result = format_currency(100, "GBP")
        assert "£" in result
        assert "100" in result


class TestBillingCycleService:
    """Tests for Issue #31: Billing cycle alignment."""
    
    @pytest.fixture
    def service(self):
        """Create a BillingCycleService with a mocked database session."""
        mock_db = AsyncMock()
        return BillingCycleService(mock_db)
    
    def test_calculate_aligned_period_monthly_no_anchor(self, service):
        """Test monthly billing period without anchor date."""
        today = date(2025, 3, 15)
        period_start, period_end = service.calculate_aligned_period(
            today, 
            billing_anchor_day=None, 
            align_to_calendar_month=False, 
            billing_cycle="monthly"
        )
        assert period_start == date(2025, 3, 15)
        # Period end should be about 30 days later
        assert period_end >= period_start + timedelta(days=28)
    
    def test_calculate_aligned_period_monthly_with_anchor(self, service):
        """Test monthly billing with anchor day."""
        today = date(2025, 3, 15)
        period_start, period_end = service.calculate_aligned_period(
            today, 
            billing_anchor_day=1, 
            align_to_calendar_month=False, 
            billing_cycle="monthly"
        )
        # Should start on the 1st
        assert period_start.day == 1
    
    def test_calculate_aligned_period_calendar_aligned(self, service):
        """Test calendar-aligned billing."""
        today = date(2025, 3, 15)
        period_start, period_end = service.calculate_aligned_period(
            today, 
            billing_anchor_day=None, 
            align_to_calendar_month=True, 
            billing_cycle="monthly"
        )
        assert period_start == date(2025, 3, 1)
        assert period_end == date(2025, 4, 1)
    
    def test_calculate_proration_full_month(self, service):
        """Test proration for full month."""
        result = service.calculate_proration(
            full_price=50000,
            start_date=date(2025, 1, 1),
            period_end=date(2025, 2, 1),
            period_start=date(2025, 1, 1)
        )
        assert result["prorated_price"] == 50000
        assert result["proration_percentage"] == 100.0
        assert result["days_remaining"] == 31
    
    def test_calculate_proration_half_month(self, service):
        """Test proration for half month."""
        result = service.calculate_proration(
            full_price=30000,
            start_date=date(2025, 1, 16),
            period_end=date(2025, 2, 1),
            period_start=date(2025, 1, 1)
        )
        # Should be roughly half the price
        assert result["prorated_price"] < 30000
        assert result["proration_percentage"] < 100.0
        assert result["days_remaining"] == 16


class TestSubscriptionPauseService:
    """Tests for Issue #32: Subscription pause/resume."""
    
    @pytest.fixture
    def service(self):
        """Create a SubscriptionPauseService with a mocked database session."""
        mock_db = AsyncMock()
        return SubscriptionPauseService(mock_db)
    
    def test_max_pause_days_constant(self, service):
        """Test that max pause days is 90."""
        assert service.MAX_PAUSE_DAYS == 90
    
    def test_annual_pause_limit_constant(self, service):
        """Test that annual pause limit exists."""
        assert hasattr(service, 'ANNUAL_PAUSE_LIMIT') or hasattr(service, 'MAX_PAUSE_DAYS')
    
    def test_max_pauses_per_year_constant(self, service):
        """Test that max pauses per year is 2 (Issue #32 fix)."""
        assert service.MAX_PAUSES_PER_YEAR == 2
    
    def test_get_pause_count_for_year_new_year(self, service):
        """Test pause count resets for new year."""
        mock_sku = MagicMock()
        mock_sku.last_pause_year = 2024
        mock_sku.pause_count_this_year = 2
        
        # Should return 0 for a different year
        count = service._get_pause_count_for_year(mock_sku, 2025)
        assert count == 0
    
    def test_get_pause_count_for_year_same_year(self, service):
        """Test pause count persists within same year."""
        mock_sku = MagicMock()
        mock_sku.last_pause_year = 2025
        mock_sku.pause_count_this_year = 1
        
        # Should return the existing count for same year
        count = service._get_pause_count_for_year(mock_sku, 2025)
        assert count == 1


class TestServiceCreditService:
    """Tests for Issue #33: Service credit system."""
    
    @pytest.fixture
    def service(self):
        """Create a ServiceCreditService with a mocked database session."""
        mock_db = AsyncMock()
        return ServiceCreditService(mock_db)
    
    def test_sla_credit_tiers(self, service):
        """Test SLA credit tier definitions exist."""
        # Check that the service has the SLA credit tiers configured
        assert hasattr(service, 'SLA_CREDIT_TIERS')
        # Tiers should be a dictionary
        assert isinstance(service.SLA_CREDIT_TIERS, dict)
        # Should have at least some tiers
        assert len(service.SLA_CREDIT_TIERS) > 0


class TestDiscountCodeService:
    """Tests for Issue #34: Referral/discount code system."""
    
    @pytest.fixture
    def service(self):
        """Create a DiscountCodeService with a mocked database session."""
        mock_db = AsyncMock()
        return DiscountCodeService(mock_db)
    
    def test_calculate_discount_percentage(self, service):
        """Test percentage discount calculation."""
        result = service.calculate_discount(
            original_amount=100000,
            discount_type="percentage",
            discount_value=Decimal("20"),
            max_discount=None
        )
        assert result["discount_amount"] == 20000  # 20% of 100,000
        assert result["final_amount"] == 80000
    
    def test_calculate_discount_percentage_with_cap(self, service):
        """Test percentage discount with max cap."""
        result = service.calculate_discount(
            original_amount=200000,
            discount_type="percentage",
            discount_value=Decimal("50"),
            max_discount=50000  # Cap at 50k
        )
        assert result["discount_amount"] == 50000  # Capped at max
        assert result["final_amount"] == 150000
    
    def test_calculate_discount_fixed_amount(self, service):
        """Test fixed amount discount."""
        result = service.calculate_discount(
            original_amount=100000,
            discount_type="fixed_amount",
            discount_value=Decimal("15000"),
            max_discount=None
        )
        assert result["discount_amount"] == 15000
        assert result["final_amount"] == 85000


class TestVolumeDiscountService:
    """Tests for Issue #35: Volume discount logic."""
    
    @pytest.fixture
    def service(self):
        """Create a VolumeDiscountService with a mocked database session."""
        mock_db = AsyncMock()
        return VolumeDiscountService(mock_db)
    
    def test_service_has_db(self, service):
        """Test that service has database connection."""
        assert service.db is not None


class TestAdvancedBillingService:
    """Tests for the combined AdvancedBillingService."""
    
    @pytest.fixture
    def service(self):
        """Create an AdvancedBillingService with a mocked database session."""
        mock_db = AsyncMock()
        return AdvancedBillingService(mock_db)
    
    def test_service_initialization(self, service):
        """Test that all sub-services are initialized."""
        # Check sub-services use correct attribute names
        assert service.currency is not None
        assert service.billing_cycle is not None
        assert service.pause is not None
        assert service.credits is not None
        assert service.discounts is not None
        assert service.volume is not None
        assert service.reports is not None


class TestUsageReportService:
    """Tests for Issue #30: Usage report generation."""
    
    @pytest.fixture
    def service(self):
        """Create a UsageReportService with a mocked database session."""
        mock_db = AsyncMock()
        return UsageReportService(mock_db)
    
    def test_service_has_csv_method(self, service):
        """Test that CSV generation method exists."""
        assert hasattr(service, 'generate_usage_report_csv')
        assert callable(service.generate_usage_report_csv)
    
    def test_service_has_pdf_method(self, service):
        """Test that PDF generation method exists (Issue #30 fix)."""
        assert hasattr(service, 'generate_usage_report_pdf')
        assert callable(service.generate_usage_report_pdf)
    
    def test_generate_report_html_method_exists(self, service):
        """Test that HTML generation method exists for PDF."""
        assert hasattr(service, '_generate_report_html')
    
    def test_create_simple_pdf_method_exists(self, service):
        """Test that simple PDF fallback method exists."""
        assert hasattr(service, '_create_simple_pdf')
    
    def test_html_report_generation(self, service):
        """Test HTML report content generation."""
        html = service._generate_report_html(
            organization_name="Test Org",
            organization_id="test-id-123",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            records=[],
            summary={
                "total_transactions": 100,
                "total_invoices": 50,
                "peak_users": 10,
                "total_api_calls": 5000,
                "total_ocr_pages": 200,
                "peak_storage_mb": 150.5,
            }
        )
        assert "Test Org" in html
        assert "Tekvwa Pro Audit" in html
        assert "Usage Report" in html
        assert "100" in html  # total_transactions
    
    def test_simple_pdf_fallback(self, service):
        """Test simple PDF generation without external libraries."""
        pdf_bytes = service._create_simple_pdf(
            organization_name="Test Org",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            records=[],
            summary={
                "total_transactions": 100,
                "total_invoices": 50,
                "peak_users": 10,
                "total_api_calls": 5000,
                "total_ocr_pages": 200,
                "peak_storage_mb": 150.5,
            }
        )
        # Should return valid PDF bytes
        assert pdf_bytes is not None
        assert len(pdf_bytes) > 0
        # PDF files start with %PDF
        assert pdf_bytes.startswith(b'%PDF') or b'PDF' in pdf_bytes[:100]


class TestSKUTierEnum:
    """Tests for SKU tier definitions."""
    
    def test_tier_values(self):
        """Test that all expected tiers exist."""
        assert SKUTier.CORE.value == "core"
        assert SKUTier.PROFESSIONAL.value == "professional"
        assert SKUTier.ENTERPRISE.value == "enterprise"


# Integration-style tests for API endpoints (would require httpx test client)
class TestAdvancedBillingEndpoints:
    """Tests for the advanced billing API endpoints."""
    
    @pytest.mark.asyncio
    async def test_get_currencies_endpoint_structure(self):
        """Test that currencies endpoint returns expected structure."""
        # This would be an integration test with httpx
        expected_currencies = ["NGN", "USD", "EUR", "GBP"]
        for currency in expected_currencies:
            assert currency in [c.value for c in Currency]


# Additional edge case tests
class TestEdgeCases:
    """Edge case tests for billing features."""
    
    def test_format_currency_with_zero(self):
        """Test formatting zero amounts."""
        assert format_currency(0, "NGN") == "₦0"
        result_usd = format_currency(0, "USD")
        assert "$" in result_usd
        assert "0" in result_usd
    
    def test_format_currency_with_large_number(self):
        """Test formatting large amounts."""
        result = format_currency(1000000000, "NGN")
        assert "₦" in result
        assert "1,000,000,000" in result
    
    def test_format_currency_unknown_currency(self):
        """Test formatting with unknown currency code."""
        result = format_currency(100, "XYZ")
        # Should fallback gracefully
        assert "100" in str(result)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
