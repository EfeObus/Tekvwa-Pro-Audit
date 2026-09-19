"""
Tekvwa Pro Audit - PAYE Calculator Service

PAYE (Pay As You Earn) calculation service for Nigerian 2026 tax reform.

Nigeria 2026 PAYE Tax Bands:
- ₦0 - ₦800,000: 0%
- ₦800,001 - ₦2,400,000: 15%
- ₦2,400,001 - ₦4,800,000: 20%
- ₦4,800,001 - ₦7,200,000: 25%
- Above ₦7,200,000: 30%

Relief:
- Consolidated Relief Allowance (CRA): ₦200,000 + 20% of gross income
- Pension contribution: Up to 8% of gross (exempt)
- NHF contribution: 2.5% of basic salary (exempt)
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from sqlalchemy import select, func, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tax import PAYERecord


@dataclass
class PAYETaxBand:
    """Tax band definition."""
    lower: Decimal
    upper: Optional[Decimal]
    rate: Decimal
    
    def calculate_tax(self, taxable_income: Decimal) -> Decimal:
        """Calculate tax for this band."""
        if taxable_income <= self.lower:
            return Decimal("0")
        
        if self.upper is None:
            # Top band (no upper limit)
            taxable_in_band = taxable_income - self.lower
        else:
            taxable_in_band = min(taxable_income, self.upper) - self.lower
        
        if taxable_in_band <= 0:
            return Decimal("0")
        
        return taxable_in_band * (self.rate / 100)


# Nigeria 2026 PAYE Tax Bands
NIGERIA_2026_PAYE_BANDS = [
    PAYETaxBand(Decimal("0"), Decimal("800000"), Decimal("0")),
    PAYETaxBand(Decimal("800000"), Decimal("2400000"), Decimal("15")),
    PAYETaxBand(Decimal("2400000"), Decimal("4800000"), Decimal("20")),
    PAYETaxBand(Decimal("4800000"), Decimal("7200000"), Decimal("25")),
    PAYETaxBand(Decimal("7200000"), None, Decimal("30")),
]

# Consolidated Relief Allowance (CRA)
CRA_FIXED_AMOUNT = Decimal("200000")
CRA_PERCENTAGE = Decimal("20")

# Maximum pension contribution percentage
MAX_PENSION_PERCENTAGE = Decimal("8")

# NHF percentage of basic salary
NHF_PERCENTAGE = Decimal("2.5")


class PAYECalculator:
    """
    PAYE (Pay As You Earn) calculator for Nigerian tax system.
    
    Implements the 2026 tax reform rates.
    """
    
    def __init__(self, tax_bands: List[PAYETaxBand] = None):
        self.tax_bands = tax_bands or NIGERIA_2026_PAYE_BANDS
    
    def calculate_cra(self, gross_annual_income: Decimal) -> Decimal:
        """
        Calculate Consolidated Relief Allowance (CRA).
        
        CRA = ₦200,000 OR 1% of gross income (whichever is higher) + 20% of gross income
        Simplified: ₦200,000 + 20% of gross income
        """
        fixed_relief = max(CRA_FIXED_AMOUNT, gross_annual_income * Decimal("0.01"))
        percentage_relief = gross_annual_income * (CRA_PERCENTAGE / 100)
        return fixed_relief + percentage_relief
    
    def calculate_pension_relief(
        self,
        gross_annual_income: Decimal,
        pension_percentage: Decimal = Decimal("8"),
    ) -> Decimal:
        """
        Calculate pension contribution relief.
        
        Employee pension contribution (up to 8% of gross) is tax-exempt.
        """
        rate = min(pension_percentage, MAX_PENSION_PERCENTAGE)
        return gross_annual_income * (rate / 100)
    
    def calculate_nhf_relief(
        self,
        basic_annual_salary: Decimal,
    ) -> Decimal:
        """
        Calculate NHF (National Housing Fund) contribution relief.
        
        NHF = 2.5% of basic salary.
        """
        return basic_annual_salary * (NHF_PERCENTAGE / 100)
    
    def calculate_taxable_income(
        self,
        gross_annual_income: Decimal,
        pension_contribution: Decimal = Decimal("0"),
        nhf_contribution: Decimal = Decimal("0"),
        other_reliefs: Decimal = Decimal("0"),
    ) -> Tuple[Decimal, Dict[str, Decimal]]:
        """
        Calculate taxable income after all reliefs.
        
        Returns:
            Tuple of (taxable_income, relief_breakdown)
        """
        cra = self.calculate_cra(gross_annual_income)
        
        total_reliefs = cra + pension_contribution + nhf_contribution + other_reliefs
        taxable_income = max(Decimal("0"), gross_annual_income - total_reliefs)
        
        relief_breakdown = {
            "consolidated_relief": cra,
            "pension_contribution": pension_contribution,
            "nhf_contribution": nhf_contribution,
            "other_reliefs": other_reliefs,
            "total_reliefs": total_reliefs,
        }
        
        return taxable_income, relief_breakdown
    
    def calculate_tax(self, taxable_income: Decimal) -> Tuple[Decimal, List[Dict[str, Any]]]:
        """
        Calculate PAYE tax using progressive tax bands.
        
        Returns:
            Tuple of (total_tax, band_breakdown)
        """
        total_tax = Decimal("0")
        band_breakdown = []
        
        for band in self.tax_bands:
            tax_in_band = band.calculate_tax(taxable_income)
            
            if tax_in_band > 0 or taxable_income > band.lower:
                band_breakdown.append({
                    "range": f"₦{band.lower:,.0f} - {'∞' if band.upper is None else f'₦{band.upper:,.0f}'}",
                    "rate": f"{band.rate}%",
                    "tax_amount": float(tax_in_band),
                })
            
            total_tax += tax_in_band
        
        return total_tax, band_breakdown
    
    def calculate_paye(
        self,
        gross_annual_income: float,
        basic_salary: Optional[float] = None,
        pension_percentage: float = 8.0,
        other_reliefs: float = 0,
    ) -> Dict[str, Any]:
        """
        Complete PAYE calculation with all reliefs.
        
        Args:
            gross_annual_income: Total annual income
            basic_salary: Basic salary for NHF calculation (defaults to 60% of gross)
            pension_percentage: Employee pension contribution percentage (max 8%)
            other_reliefs: Additional tax-exempt allowances
            
        Returns:
            Complete PAYE calculation breakdown
        """
        gross = Decimal(str(gross_annual_income))
        basic = Decimal(str(basic_salary)) if basic_salary else gross * Decimal("0.6")
        
        # Calculate reliefs
        pension_relief = self.calculate_pension_relief(gross, Decimal(str(pension_percentage)))
        nhf_relief = self.calculate_nhf_relief(basic)
        other = Decimal(str(other_reliefs))
        
        # Calculate taxable income
        taxable_income, relief_breakdown = self.calculate_taxable_income(
            gross, pension_relief, nhf_relief, other
        )
        
        # Calculate tax
        annual_tax, band_breakdown = self.calculate_tax(taxable_income)
        monthly_tax = annual_tax / 12
        
        # Effective tax rate
        effective_rate = (annual_tax / gross * 100) if gross > 0 else Decimal("0")
        
        return {
            "gross_annual_income": float(gross),
            "basic_salary": float(basic),
            "reliefs": {k: float(v) for k, v in relief_breakdown.items()},
            "taxable_income": float(taxable_income),
            "annual_tax": float(annual_tax),
            "monthly_tax": float(monthly_tax),
            "effective_rate": float(effective_rate),
            "tax_bands": band_breakdown,
            "net_annual_income": float(gross - annual_tax),
            "net_monthly_income": float((gross - annual_tax) / 12),
        }
    
    def calculate_monthly_paye(
        self,
        monthly_gross_income: float,
        year_to_date_gross: float = 0,
        year_to_date_tax: float = 0,
        pension_percentage: float = 8.0,
    ) -> Dict[str, Any]:
        """
        Calculate monthly PAYE with year-to-date adjustments.
        
        Uses annualized method for accurate monthly deduction.
        """
        # Annualize current month income
        # Estimate annual income based on current month
        months_elapsed = max(1, 12 - (12 * (year_to_date_gross / (monthly_gross_income * 12 + 0.01))))
        
        # Project annual income
        projected_annual = monthly_gross_income * 12
        
        # Calculate full year tax
        full_year_calc = self.calculate_paye(
            gross_annual_income=projected_annual,
            pension_percentage=pension_percentage,
        )
        
        # Calculate this month's tax
        annual_tax = Decimal(str(full_year_calc["annual_tax"]))
        ytd_tax_decimal = Decimal(str(year_to_date_tax))
        
        # Monthly tax = (Annual tax / 12) adjusted for YTD
        monthly_tax = annual_tax / 12
        
        return {
            "monthly_gross": float(monthly_gross_income),
            "monthly_tax": float(monthly_tax),
            "monthly_net": float(monthly_gross_income - float(monthly_tax)),
            "projected_annual_tax": float(annual_tax),
            "year_to_date_tax": float(ytd_tax_decimal),
            "effective_rate": full_year_calc["effective_rate"],
        }


class PAYEService:
    """Service for PAYE record management."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.calculator = PAYECalculator()
    
    async def get_paye_records_for_entity(
        self,
        entity_id: uuid.UUID,
        year: Optional[int] = None,
        month: Optional[int] = None,
        employee_tin: Optional[str] = None,
    ) -> List[PAYERecord]:
        """Get PAYE records for an entity."""
        query = select(PAYERecord).where(PAYERecord.entity_id == entity_id)
        
        if year:
            query = query.where(PAYERecord.period_year == year)
        
        if month:
            query = query.where(PAYERecord.period_month == month)
        
        if employee_tin:
            query = query.where(PAYERecord.employee_tin == employee_tin)
        
        query = query.order_by(
            PAYERecord.period_year.desc(),
            PAYERecord.period_month.desc(),
            PAYERecord.employee_name,
        )
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def create_paye_record(
        self,
        entity_id: uuid.UUID,
        employee_name: str,
        period_year: int,
        period_month: int,
        gross_salary: float,
        employee_tin: Optional[str] = None,
        pension_contribution: float = 0,
        nhf_contribution: float = 0,
        other_reliefs: float = 0,
    ) -> PAYERecord:
        """Create a PAYE record for an employee."""
        # Calculate PAYE
        gross = Decimal(str(gross_salary)) * 12  # Annualize
        pension = Decimal(str(pension_contribution)) * 12
        nhf = Decimal(str(nhf_contribution)) * 12
        other = Decimal(str(other_reliefs)) * 12
        
        cra = self.calculator.calculate_cra(gross)
        taxable_income, _ = self.calculator.calculate_taxable_income(
            gross, pension, nhf, other
        )
        annual_tax, _ = self.calculator.calculate_tax(taxable_income)
        monthly_tax = annual_tax / 12
        
        paye_record = PAYERecord(
            entity_id=entity_id,
            employee_name=employee_name,
            employee_tin=employee_tin,
            period_month=period_month,
            period_year=period_year,
            gross_salary=Decimal(str(gross_salary)),
            consolidated_relief=cra / 12,
            pension_contribution=Decimal(str(pension_contribution)),
            nhf_contribution=Decimal(str(nhf_contribution)),
            other_reliefs=Decimal(str(other_reliefs)) if other_reliefs else Decimal("0"),
            taxable_income=taxable_income / 12,
            tax_amount=monthly_tax,
        )
        
        self.db.add(paye_record)
        await self.db.commit()
        await self.db.refresh(paye_record)
        
        return paye_record
    
    async def get_paye_summary_for_period(
        self,
        entity_id: uuid.UUID,
        year: int,
        month: int,
    ) -> Dict[str, Any]:
        """Get PAYE summary for a period."""
        result = await self.db.execute(
            select(
                func.count(PAYERecord.id).label("employee_count"),
                func.coalesce(func.sum(PAYERecord.gross_salary), 0).label("total_gross"),
                func.coalesce(func.sum(PAYERecord.tax_amount), 0).label("total_tax"),
            )
            .where(PAYERecord.entity_id == entity_id)
            .where(PAYERecord.period_year == year)
            .where(PAYERecord.period_month == month)
        )
        row = result.one()
        
        return {
            "period": {"year": year, "month": month},
            "employee_count": row.employee_count,
            "total_gross_salary": float(row.total_gross),
            "total_paye_tax": float(row.total_tax),
        }
