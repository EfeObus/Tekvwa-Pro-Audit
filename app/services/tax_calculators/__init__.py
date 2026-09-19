"""
Tekvwa Pro Audit - Tax Calculators Package

Tax calculation services for Nigerian 2026 tax reform.

Modules:
- vat_service: VAT calculation and tracking (7.5% rate)
- paye_service: PAYE calculation with 2026 bands (0%/15%/20%/25%/30%)
- wht_service: WHT calculation by service type (5%-10% rates)
- cit_service: CIT calculation by company size (0%/20%/30%)
"""

from decimal import Decimal

from app.services.tax_calculators.vat_service import VATCalculator, VATService, NIGERIA_VAT_RATE
from app.services.tax_calculators.paye_service import PAYECalculator, PAYEService
from app.services.tax_calculators.wht_service import WHTCalculator, WHTService, WHTServiceType, PayeeType
from app.services.tax_calculators.cit_service import CITCalculator, CITService, CompanySize
from app.services.tax_calculators.minimum_etr_cgt_service import (
    MinimumETRCalculator,
    CGTCalculator,
    ZeroRatedVATTracker,
    CompanyClassification,
    MinimumETRResult,
    CGTResult,
    get_minimum_etr_calculator,
    get_cgt_calculator,
    get_zero_rated_vat_tracker,
)


# ===========================================
# CONVENIENCE FUNCTIONS
# ===========================================

def calculate_vat(amount: Decimal, is_exempt: bool = False) -> Decimal:
    """
    Calculate VAT on an amount.
    
    Args:
        amount: Base amount
        is_exempt: Whether item is VAT exempt
    
    Returns:
        VAT amount (7.5% or 0 if exempt)
    """
    if is_exempt:
        return Decimal("0.00")
    _, vat_amount, _ = VATCalculator.calculate_vat(amount)
    return vat_amount


def calculate_paye(annual_income: Decimal) -> Decimal:
    """
    Calculate PAYE tax on annual income.
    
    Uses Nigeria 2026 Tax Reform bands:
    - 0%: ≤₦800,000
    - 15%: ₦800,001 - ₦2,500,000
    - 20%: ₦2,500,001 - ₦5,000,000
    - 25%: ₦5,000,001 - ₦10,000,000
    - 30%: >₦10,000,000
    
    Args:
        annual_income: Annual taxable income
    
    Returns:
        Total PAYE tax amount
    """
    calculator = PAYECalculator()
    total_tax, _ = calculator.calculate_tax(annual_income)
    return total_tax


def calculate_wht(amount: Decimal, service_type: str) -> Decimal:
    """
    Calculate Withholding Tax on payment.
    
    Rates:
    - Professional/Consultancy: 10%
    - Construction/Contracts: 5%
    - Rent: 10%
    - Dividends/Royalties: 10%
    
    Args:
        amount: Payment amount
        service_type: Type of service
    
    Returns:
        WHT amount
    """
    wht_type = WHTServiceType(service_type)
    result = WHTCalculator.calculate_wht(float(amount), wht_type)
    return Decimal(str(result["wht_amount"]))


def calculate_cit(profit: Decimal, turnover: Decimal) -> Decimal:
    """
    Calculate Company Income Tax.
    
    Uses Nigeria 2026 Tax Reform rates:
    - 0%: Turnover <₦25M
    - 20%: Turnover ₦25M-₦100M
    - 30%: Turnover >₦100M
    
    Args:
        profit: Taxable profit
        turnover: Annual turnover
    
    Returns:
        CIT amount
    """
    if profit <= 0:
        return Decimal("0.00")
    result = CITCalculator.calculate_cit(float(turnover), float(profit))
    return Decimal(str(result.get("cit_on_profit", 0)))


def get_paye_band(annual_income: Decimal) -> str:
    """
    Get the PAYE tax band for an income level.
    
    Args:
        annual_income: Annual income
    
    Returns:
        Band description (Exempt, 15%, 20%, 25%, 30%)
    """
    if annual_income <= Decimal("800000"):
        return "Exempt"
    elif annual_income <= Decimal("2500000"):
        return "15%"
    elif annual_income <= Decimal("5000000"):
        return "20%"
    elif annual_income <= Decimal("10000000"):
        return "25%"
    else:
        return "30%"


__all__ = [
    # VAT
    "VATCalculator",
    "VATService",
    "NIGERIA_VAT_RATE",
    # PAYE
    "PAYECalculator",
    "PAYEService",
    # WHT
    "WHTCalculator",
    "WHTService",
    "WHTServiceType",
    "PayeeType",
    # CIT
    "CITCalculator",
    "CITService",
    "CompanySize",
    # Minimum ETR & CGT (2026)
    "MinimumETRCalculator",
    "CGTCalculator",
    "ZeroRatedVATTracker",
    "CompanyClassification",
    "MinimumETRResult",
    "CGTResult",
    "get_minimum_etr_calculator",
    "get_cgt_calculator",
    "get_zero_rated_vat_tracker",
    # Convenience functions
    "calculate_vat",
    "calculate_paye",
    "calculate_wht",
    "calculate_cit",
    "get_paye_band",
]
