"""
Tekvwa Pro Audit - CIT Calculator Service

Company Income Tax (CIT) calculation service for Nigerian tax compliance.

CIT Rates (2026 Nigeria Tax Reform):
- Turnover ≤ ₦25,000,000: 0% (Small companies exempt)
- Turnover ₦25,000,001 - ₦100,000,000: 20% (Medium companies)
- Turnover > ₦100,000,000: 30% (Large companies)

Minimum Tax:
- 0.5% of gross turnover for companies with no taxable profit or tax liability < minimum tax
- Exempted for small companies and for the first 4 years of new companies

Tertiary Education Tax (TET): 3% of assessable profit (additional to CIT)
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession


class CompanySize(str, Enum):
    """Company size classification for CIT purposes."""
    SMALL = "small"  # ≤ ₦25M turnover
    MEDIUM = "medium"  # ₦25M - ₦100M turnover
    LARGE = "large"  # > ₦100M turnover


@dataclass
class CITRate:
    """CIT rate structure."""
    size: CompanySize
    turnover_min: Decimal
    turnover_max: Optional[Decimal]
    rate: Decimal


# CIT rates based on turnover thresholds (2026 Nigeria Tax Reform)
CIT_RATES = [
    CITRate(
        size=CompanySize.SMALL,
        turnover_min=Decimal("0"),
        turnover_max=Decimal("25000000"),
        rate=Decimal("0"),
    ),
    CITRate(
        size=CompanySize.MEDIUM,
        turnover_min=Decimal("25000000.01"),
        turnover_max=Decimal("100000000"),
        rate=Decimal("20"),
    ),
    CITRate(
        size=CompanySize.LARGE,
        turnover_min=Decimal("100000000.01"),
        turnover_max=None,
        rate=Decimal("30"),
    ),
]

# Tertiary Education Tax rate
TET_RATE = Decimal("3")  # 3% of assessable profit

# Minimum tax rate
MINIMUM_TAX_RATE = Decimal("0.5")  # 0.5% of gross turnover


class CITCalculator:
    """
    Company Income Tax (CIT) calculator.
    
    Implements Nigeria 2026 Tax Reform CIT rules.
    """
    
    @staticmethod
    def get_company_size(turnover: float) -> CompanySize:
        """
        Determine company size based on turnover.
        
        Args:
            turnover: Annual gross turnover
            
        Returns:
            CompanySize enum value
        """
        t = Decimal(str(turnover))
        
        if t <= Decimal("25000000"):
            return CompanySize.SMALL
        elif t <= Decimal("100000000"):
            return CompanySize.MEDIUM
        else:
            return CompanySize.LARGE
    
    @staticmethod
    def get_cit_rate(turnover: float) -> Decimal:
        """
        Get CIT rate based on turnover.
        
        Args:
            turnover: Annual gross turnover
            
        Returns:
            CIT rate as percentage
        """
        t = Decimal(str(turnover))
        
        for rate_info in CIT_RATES:
            if rate_info.turnover_max is None:
                if t >= rate_info.turnover_min:
                    return rate_info.rate
            elif rate_info.turnover_min <= t <= rate_info.turnover_max:
                return rate_info.rate
        
        return Decimal("30")  # Default to large company rate
    
    @staticmethod
    def calculate_cit(
        gross_turnover: float,
        assessable_profit: float,
        is_new_company: bool = False,
        company_age_years: int = 0,
        claim_minimum_tax_exemption: bool = False,
    ) -> Dict[str, Any]:
        """
        Calculate Company Income Tax.
        
        Args:
            gross_turnover: Annual gross revenue/turnover
            assessable_profit: Taxable profit after allowable deductions
            is_new_company: Whether company is in first 4 years of operation
            company_age_years: Number of years since incorporation
            claim_minimum_tax_exemption: Claim exemption from minimum tax
            
        Returns:
            Dict with CIT calculation details
        """
        turnover = Decimal(str(gross_turnover))
        profit = Decimal(str(assessable_profit))
        
        company_size = CITCalculator.get_company_size(gross_turnover)
        cit_rate = CITCalculator.get_cit_rate(gross_turnover)
        
        # Calculate CIT on profit
        cit_on_profit = max(Decimal("0"), profit * (cit_rate / 100))
        
        # Calculate minimum tax (0.5% of turnover)
        minimum_tax = turnover * (MINIMUM_TAX_RATE / 100)
        
        # Determine if minimum tax applies
        is_minimum_tax_exempt = (
            company_size == CompanySize.SMALL or
            (is_new_company and company_age_years < 4) or
            claim_minimum_tax_exemption
        )
        
        # Final CIT is higher of CIT on profit or minimum tax (if not exempt)
        if is_minimum_tax_exempt:
            final_cit = cit_on_profit
            minimum_tax_applied = False
        else:
            if cit_on_profit < minimum_tax and profit <= 0:
                final_cit = minimum_tax
                minimum_tax_applied = True
            else:
                final_cit = cit_on_profit
                minimum_tax_applied = False
        
        # Calculate Tertiary Education Tax (3% of assessable profit)
        tet = max(Decimal("0"), profit * (TET_RATE / 100))
        
        # Total tax liability
        total_tax = final_cit + tet
        
        # Effective rate
        effective_rate = (total_tax / turnover * 100) if turnover > 0 else Decimal("0")
        
        return {
            "gross_turnover": float(turnover),
            "assessable_profit": float(profit),
            "company_size": company_size.value,
            "cit_rate": float(cit_rate),
            "cit_on_profit": float(round(cit_on_profit, 2)),
            "minimum_tax": float(round(minimum_tax, 2)),
            "is_minimum_tax_exempt": is_minimum_tax_exempt,
            "minimum_tax_applied": minimum_tax_applied,
            "final_cit": float(round(final_cit, 2)),
            "tertiary_education_tax": float(round(tet, 2)),
            "total_tax_liability": float(round(total_tax, 2)),
            "effective_rate": float(round(effective_rate, 2)),
        }
    
    @staticmethod
    def calculate_provisional_tax(
        estimated_turnover: float,
        estimated_profit: float,
    ) -> Dict[str, Any]:
        """
        Calculate provisional tax (for advance tax payments).
        
        Provisional tax is paid in advance during the year.
        Usually 2 installments based on estimated figures.
        """
        result = CITCalculator.calculate_cit(
            gross_turnover=estimated_turnover,
            assessable_profit=estimated_profit,
        )
        
        # Provisional tax is divided into 2 installments
        first_installment = Decimal(str(result["total_tax_liability"])) / 2
        second_installment = Decimal(str(result["total_tax_liability"])) / 2
        
        return {
            **result,
            "first_installment": float(round(first_installment, 2)),
            "second_installment": float(round(second_installment, 2)),
            "first_installment_due": "Within 3 months of year start",
            "second_installment_due": "Within 6 months of year start",
        }
    
    @staticmethod
    def get_cit_thresholds() -> List[Dict[str, Any]]:
        """Get all CIT thresholds for reference."""
        thresholds = []
        for rate_info in CIT_RATES:
            thresholds.append({
                "company_size": rate_info.size.value,
                "turnover_min": float(rate_info.turnover_min),
                "turnover_max": float(rate_info.turnover_max) if rate_info.turnover_max else None,
                "cit_rate": float(rate_info.rate),
            })
        return thresholds


class CITService:
    """Service for CIT tracking and management."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.calculator = CITCalculator()
    
    async def get_annual_turnover(
        self,
        entity_id: uuid.UUID,
        fiscal_year_start: date,
        fiscal_year_end: date,
    ) -> Decimal:
        """
        Calculate annual turnover from invoices.
        """
        from app.models.invoice import Invoice, InvoiceStatus
        
        result = await self.db.execute(
            select(func.coalesce(func.sum(Invoice.total_amount), 0))
            .where(Invoice.entity_id == entity_id)
            .where(Invoice.invoice_date >= fiscal_year_start)
            .where(Invoice.invoice_date <= fiscal_year_end)
            .where(Invoice.status.in_([InvoiceStatus.FINALIZED, InvoiceStatus.PAID]))
        )
        
        return result.scalar() or Decimal("0")
    
    async def get_annual_expenses(
        self,
        entity_id: uuid.UUID,
        fiscal_year_start: date,
        fiscal_year_end: date,
    ) -> Decimal:
        """
        Calculate annual expenses from transactions.
        """
        from app.models.transaction import Transaction, TransactionType
        
        result = await self.db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_date >= fiscal_year_start)
            .where(Transaction.transaction_date <= fiscal_year_end)
            .where(Transaction.transaction_type == TransactionType.EXPENSE)
        )
        
        return result.scalar() or Decimal("0")
    
    async def calculate_cit_for_entity(
        self,
        entity_id: uuid.UUID,
        fiscal_year: int,
        fiscal_year_start: Optional[date] = None,
        fiscal_year_end: Optional[date] = None,
        adjustments: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """
        Calculate CIT for an entity for a fiscal year.
        
        Args:
            entity_id: Business entity ID
            fiscal_year: Fiscal year (e.g., 2026)
            fiscal_year_start: Start of fiscal year (defaults to Jan 1)
            fiscal_year_end: End of fiscal year (defaults to Dec 31)
            adjustments: Tax adjustments (add_backs, allowable_deductions, etc.)
        """
        if fiscal_year_start is None:
            fiscal_year_start = date(fiscal_year, 1, 1)
        if fiscal_year_end is None:
            fiscal_year_end = date(fiscal_year, 12, 31)
        if adjustments is None:
            adjustments = {}
        
        # Get financial data
        gross_turnover = await self.get_annual_turnover(
            entity_id, fiscal_year_start, fiscal_year_end
        )
        total_expenses = await self.get_annual_expenses(
            entity_id, fiscal_year_start, fiscal_year_end
        )
        
        # Calculate accounting profit
        accounting_profit = gross_turnover - total_expenses
        
        # Apply tax adjustments
        add_backs = Decimal(str(adjustments.get("add_backs", 0)))
        further_deductions = Decimal(str(adjustments.get("further_deductions", 0)))
        capital_allowances = Decimal(str(adjustments.get("capital_allowances", 0)))
        
        # Assessable profit = Accounting profit + Add-backs - Further deductions - Capital allowances
        assessable_profit = accounting_profit + add_backs - further_deductions - capital_allowances
        
        # Calculate CIT
        cit_result = CITCalculator.calculate_cit(
            gross_turnover=float(gross_turnover),
            assessable_profit=float(assessable_profit),
            is_new_company=adjustments.get("is_new_company", False),
            company_age_years=adjustments.get("company_age_years", 5),
        )
        
        return {
            "entity_id": str(entity_id),
            "fiscal_year": fiscal_year,
            "period_start": fiscal_year_start.isoformat(),
            "period_end": fiscal_year_end.isoformat(),
            "financial_data": {
                "gross_turnover": float(gross_turnover),
                "total_expenses": float(total_expenses),
                "accounting_profit": float(accounting_profit),
                "add_backs": float(add_backs),
                "further_deductions": float(further_deductions),
                "capital_allowances": float(capital_allowances),
                "assessable_profit": float(assessable_profit),
            },
            "cit_calculation": cit_result,
        }
