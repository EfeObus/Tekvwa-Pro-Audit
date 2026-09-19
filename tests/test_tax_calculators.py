"""
Tekvwa Pro Audit - Tax Calculator Tests

Unit tests for Nigeria 2026 Tax Reform calculations.
"""

import pytest
from decimal import Decimal

from app.services.tax_calculators import (
    calculate_vat,
    calculate_paye,
    calculate_wht,
    calculate_cit,
    get_paye_band,
)


class TestVATCalculation:
    """Test VAT calculations per Nigeria 2026 Tax Reform."""
    
    def test_vat_rate_is_7_5_percent(self):
        """VAT should be 7.5% effective Sept 2024."""
        amount = Decimal("100000.00")
        vat = calculate_vat(amount)
        
        assert vat == Decimal("7500.00")
    
    def test_vat_on_small_amount(self):
        """Test VAT on small amounts."""
        amount = Decimal("100.00")
        vat = calculate_vat(amount)
        
        assert vat == Decimal("7.50")
    
    def test_vat_on_large_amount(self):
        """Test VAT on large amounts."""
        amount = Decimal("10000000.00")  # 10 million
        vat = calculate_vat(amount)
        
        assert vat == Decimal("750000.00")
    
    def test_vat_exempt_items(self):
        """Test VAT exemption for exempt items."""
        # Medical supplies, educational materials, etc. are exempt
        amount = Decimal("50000.00")
        vat = calculate_vat(amount, is_exempt=True)
        
        assert vat == Decimal("0.00")


class TestPAYECalculation:
    """Test PAYE calculations per Nigeria 2026 Tax Reform."""
    
    def test_paye_exempt_under_800k(self):
        """Annual income under ₦800,000 is tax-free."""
        annual_income = Decimal("700000.00")
        paye = calculate_paye(annual_income)
        
        assert paye == Decimal("0.00")
    
    def test_paye_band_1_15_percent(self):
        """₦800,001 - ₦2,400,000 at 15%."""
        annual_income = Decimal("1500000.00")  # 1.5 million
        paye = calculate_paye(annual_income)
        
        # Tax on (1,500,000 - 800,000) = 700,000 at 15% = 105,000
        expected = Decimal("105000.00")
        assert paye == expected
    
    def test_paye_band_2_20_percent(self):
        """₦2,400,001 - ₦4,800,000 at 20%."""
        annual_income = Decimal("4000000.00")  # 4 million
        paye = calculate_paye(annual_income)
        
        # Band 1 (15%): (2,400,000 - 800,000) = 1,600,000 at 15% = 240,000
        # Band 2 (20%): (4,000,000 - 2,400,000) = 1,600,000 at 20% = 320,000
        # Total: 560,000
        expected = Decimal("560000.00")
        assert paye == expected
    
    def test_paye_band_3_25_percent(self):
        """₦4,800,001 - ₦7,200,000 at 25%."""
        annual_income = Decimal("6000000.00")  # 6 million
        paye = calculate_paye(annual_income)
        
        # Band 1 (15%): (2,400,000 - 800,000) = 1,600,000 at 15% = 240,000
        # Band 2 (20%): (4,800,000 - 2,400,000) = 2,400,000 at 20% = 480,000
        # Band 3 (25%): (6,000,000 - 4,800,000) = 1,200,000 at 25% = 300,000
        # Total: 1,020,000
        expected = Decimal("1020000.00")
        assert paye == expected
    
    def test_paye_band_4_30_percent(self):
        """Above ₦7,200,000 at 30%."""
        annual_income = Decimal("10000000.00")  # 10 million
        paye = calculate_paye(annual_income)
        
        # Band 1 (15%): (2,400,000 - 800,000) = 1,600,000 at 15% = 240,000
        # Band 2 (20%): (4,800,000 - 2,400,000) = 2,400,000 at 20% = 480,000
        # Band 3 (25%): (7,200,000 - 4,800,000) = 2,400,000 at 25% = 600,000
        # Band 4 (30%): (10,000,000 - 7,200,000) = 2,800,000 at 30% = 840,000
        # Total: 2,160,000
        expected = Decimal("2160000.00")
        assert paye == expected
    
    def test_paye_exact_threshold(self):
        """Test PAYE at exact ₦800,000 threshold."""
        annual_income = Decimal("800000.00")
        paye = calculate_paye(annual_income)
        
        assert paye == Decimal("0.00")


class TestWHTCalculation:
    """Test Withholding Tax calculations."""
    
    def test_wht_professional_services(self):
        """Professional services WHT at 5% (company rate)."""
        amount = Decimal("500000.00")
        wht = calculate_wht(amount, service_type="professional_services")
        # Company rate for professional services is 5%
        assert wht == Decimal("25000.00")
    
    def test_wht_consultancy(self):
        """Consultancy WHT at 5%."""
        amount = Decimal("1000000.00")
        wht = calculate_wht(amount, service_type="consultancy")
        
        assert wht == Decimal("50000.00")
    
    def test_wht_construction(self):
        """Construction WHT at 5%."""
        amount = Decimal("5000000.00")
        wht = calculate_wht(amount, service_type="construction")
        
        assert wht == Decimal("250000.00")
    
    def test_wht_rent(self):
        """Rent WHT at 10%."""
        amount = Decimal("2400000.00")
        wht = calculate_wht(amount, service_type="rent")
        
        assert wht == Decimal("240000.00")
    
    def test_wht_dividends(self):
        """Dividends WHT at 10%."""
        amount = Decimal("1000000.00")
        wht = calculate_wht(amount, service_type="dividends")
        
        assert wht == Decimal("100000.00")
    
    def test_wht_royalties(self):
        """Royalties WHT at 10%."""
        amount = Decimal("500000.00")
        wht = calculate_wht(amount, service_type="royalties")
        
        assert wht == Decimal("50000.00")
    
    def test_wht_contract_supply(self):
        """Contract/supply WHT at 5%."""
        amount = Decimal("3000000.00")
        wht = calculate_wht(amount, service_type="contract_supply")
        
        assert wht == Decimal("150000.00")


class TestCITCalculation:
    """Test Company Income Tax calculations per 2026 Tax Reform."""
    
    def test_cit_small_business_exempt(self):
        """Turnover under ₦25 million is exempt."""
        turnover = Decimal("20000000.00")  # 20 million
        profit = Decimal("5000000.00")
        cit = calculate_cit(profit, turnover)
        
        assert cit == Decimal("0.00")
    
    def test_cit_medium_business_20_percent(self):
        """₦25M - ₦100M turnover at 20%."""
        turnover = Decimal("50000000.00")  # 50 million
        profit = Decimal("10000000.00")  # 10 million profit
        cit = calculate_cit(profit, turnover)
        
        # 20% of profit
        expected = Decimal("2000000.00")
        assert cit == expected
    
    def test_cit_large_business_30_percent(self):
        """Above ₦100M turnover at 30%."""
        turnover = Decimal("500000000.00")  # 500 million
        profit = Decimal("50000000.00")  # 50 million profit
        cit = calculate_cit(profit, turnover)
        
        # 30% of profit
        expected = Decimal("15000000.00")
        assert cit == expected
    
    def test_cit_exact_25m_threshold(self):
        """Test CIT at exact ₦25M threshold - still small (0%)."""
        turnover = Decimal("25000000.00")
        profit = Decimal("5000000.00")
        cit = calculate_cit(profit, turnover)
        
        # At exactly 25M, small business rate applies (exempt)
        expected = Decimal("0.00")
        assert cit == expected
    
    def test_cit_exact_100m_threshold(self):
        """Test CIT at exact ₦100M threshold - still medium (20%)."""
        turnover = Decimal("100000000.00")
        profit = Decimal("20000000.00")
        cit = calculate_cit(profit, turnover)
        
        # At exactly 100M, medium business rate applies (20%)
        expected = Decimal("4000000.00")  # 20%
        assert cit == expected
    
    def test_cit_loss_year(self):
        """Test CIT when business has a loss."""
        turnover = Decimal("50000000.00")
        profit = Decimal("-5000000.00")  # Loss
        cit = calculate_cit(profit, turnover)
        
        assert cit == Decimal("0.00")


class TestPAYEBands:
    """Test PAYE band identification."""
    
    def test_get_band_exempt(self):
        """Test band for exempt income."""
        band = get_paye_band(Decimal("500000.00"))
        assert band == "Exempt"
    
    def test_get_band_1(self):
        """Test band 1 identification."""
        band = get_paye_band(Decimal("1500000.00"))
        assert band == "15%"
    
    def test_get_band_2(self):
        """Test band 2 identification."""
        band = get_paye_band(Decimal("3000000.00"))
        assert band == "20%"
    
    def test_get_band_3(self):
        """Test band 3 identification."""
        band = get_paye_band(Decimal("7000000.00"))
        assert band == "25%"
    
    def test_get_band_4(self):
        """Test band 4 identification."""
        band = get_paye_band(Decimal("15000000.00"))
        assert band == "30%"
