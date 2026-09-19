"""
Tekvwa Pro Audit - Self-Assessment & TaxPro Max Export Service

Generates pre-filled tax return data for NRS TaxPro Max portal upload.

Under the 2026 Nigeria Tax Administration Act:
- All companies must file annual self-assessment returns
- TaxPro Max is the official NRS portal for tax filing
- Returns include VAT, CIT, PAYE, WHT, Development Levy
- Data must be exported in specific CSV/Excel formats

Author: Tekvwa Pro Audit
"""

import csv
import io
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, func, and_, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import BusinessEntity, BusinessType
from app.models.transaction import Transaction, TransactionType
from app.models.invoice import Invoice, InvoiceStatus
from app.models.fixed_asset import FixedAsset, AssetStatus
from enum import Enum


class InvoiceType(str, Enum):
    """Invoice type for filtering."""
    INVOICE = "invoice"
    CREDIT_NOTE = "credit_note"
    DEBIT_NOTE = "debit_note"


# ===========================================
# ENUMS AND CONSTANTS
# ===========================================

class TaxReturnType(str, Enum):
    """Types of tax returns for TaxPro Max."""
    CIT = "cit"              # Company Income Tax
    VAT = "vat"              # Value Added Tax
    PAYE = "paye"            # Pay As You Earn
    WHT = "wht"              # Withholding Tax
    DEV_LEVY = "dev_levy"    # Development Levy
    CAPITAL_GAINS = "cgt"    # Capital Gains (taxed at CIT rate under 2026)


class TaxProMaxFormCode(str, Enum):
    """TaxPro Max form codes."""
    CIT_ANNUAL = "CIT-01"           # Annual CIT Return
    CIT_QUARTERLY = "CIT-02"        # Quarterly CIT Instalment
    VAT_MONTHLY = "VAT-01"          # Monthly VAT Return
    PAYE_MONTHLY = "PAYE-01"        # Monthly PAYE Return
    WHT_MONTHLY = "WHT-01"          # Monthly WHT Return
    DEV_LEVY_ANNUAL = "DL-01"       # Annual Development Levy
    ANNUAL_RETURNS = "AR-01"        # Annual Returns Package


# TaxPro Max CSV column headers
TAXPRO_CIT_COLUMNS = [
    "TIN", "RC_Number", "Company_Name", "Fiscal_Year_End",
    "Gross_Turnover", "Cost_of_Sales", "Gross_Profit",
    "Operating_Expenses", "Depreciation", "Net_Profit_Before_Tax",
    "Add_Backs", "Less_Allowable_Deductions", "Assessable_Profit",
    "Tax_Rate_Percent", "CIT_Liability", "Capital_Gains",
    "CGT_Liability", "Total_Tax_Payable", "WHT_Credits",
    "Net_Tax_Payable", "Development_Levy",
]

TAXPRO_VAT_COLUMNS = [
    "TIN", "Period_Year", "Period_Month", "Standard_Rated_Sales",
    "Zero_Rated_Sales", "Exempt_Sales", "Total_Sales",
    "Output_VAT", "Standard_Rated_Purchases", "Zero_Rated_Purchases",
    "Exempt_Purchases", "Total_Purchases", "Input_VAT",
    "Input_VAT_Fixed_Assets", "Total_Input_VAT",
    "Net_VAT_Payable", "Refund_Claimed",
]

TAXPRO_PAYE_COLUMNS = [
    "TIN", "Period_Year", "Period_Month", "Employee_Count",
    "Gross_Emoluments", "Pension_Contributions", "NHF_Contributions",
    "NHIS_Contributions", "Life_Insurance", "Taxable_Income",
    "PAYE_Withheld", "Employer_Name", "Employer_Address",
]

TAXPRO_WHT_COLUMNS = [
    "TIN", "Period_Year", "Period_Month", "Payee_TIN",
    "Payee_Name", "Service_Type", "Contract_Value",
    "WHT_Rate_Percent", "WHT_Amount", "Payment_Date",
    "Invoice_Reference",
]


# ===========================================
# DATA CLASSES
# ===========================================

@dataclass
class CITSelfAssessment:
    """Company Income Tax self-assessment data."""
    entity_id: uuid.UUID
    fiscal_year_end: date
    tin: str
    rc_number: Optional[str]
    company_name: str
    
    # Income Statement
    gross_turnover: Decimal = Decimal("0")
    cost_of_sales: Decimal = Decimal("0")
    gross_profit: Decimal = Decimal("0")
    operating_expenses: Decimal = Decimal("0")
    depreciation: Decimal = Decimal("0")
    net_profit_before_tax: Decimal = Decimal("0")
    
    # Tax Adjustments
    add_backs: Decimal = Decimal("0")  # Non-deductible expenses
    allowable_deductions: Decimal = Decimal("0")
    assessable_profit: Decimal = Decimal("0")
    
    # Tax Calculation
    company_classification: str = "medium"  # small, medium, large
    tax_rate: Decimal = Decimal("30")
    cit_liability: Decimal = Decimal("0")
    
    # Capital Gains (taxed at CIT rate under 2026)
    capital_gains: Decimal = Decimal("0")
    cgt_liability: Decimal = Decimal("0")
    
    # Credits
    wht_credits: Decimal = Decimal("0")
    
    # Final
    total_tax_payable: Decimal = Decimal("0")
    net_tax_payable: Decimal = Decimal("0")
    development_levy: Decimal = Decimal("0")
    
    # Metadata
    generated_at: datetime = field(default_factory=datetime.utcnow)
    form_code: str = TaxProMaxFormCode.CIT_ANNUAL.value


@dataclass
class VATSelfAssessment:
    """VAT return self-assessment data."""
    entity_id: uuid.UUID
    period_year: int
    period_month: int
    tin: str
    
    # Sales
    standard_rated_sales: Decimal = Decimal("0")
    zero_rated_sales: Decimal = Decimal("0")
    exempt_sales: Decimal = Decimal("0")
    total_sales: Decimal = Decimal("0")
    output_vat: Decimal = Decimal("0")
    
    # Purchases
    standard_rated_purchases: Decimal = Decimal("0")
    zero_rated_purchases: Decimal = Decimal("0")
    exempt_purchases: Decimal = Decimal("0")
    total_purchases: Decimal = Decimal("0")
    input_vat: Decimal = Decimal("0")
    input_vat_fixed_assets: Decimal = Decimal("0")
    total_input_vat: Decimal = Decimal("0")
    
    # Net Position
    net_vat_payable: Decimal = Decimal("0")
    refund_claimed: Decimal = Decimal("0")
    
    # Metadata
    generated_at: datetime = field(default_factory=datetime.utcnow)
    form_code: str = TaxProMaxFormCode.VAT_MONTHLY.value


@dataclass
class PAYESelfAssessment:
    """PAYE return self-assessment data."""
    entity_id: uuid.UUID
    period_year: int
    period_month: int
    tin: str
    employer_name: str
    employer_address: str
    
    employee_count: int = 0
    gross_emoluments: Decimal = Decimal("0")
    pension_contributions: Decimal = Decimal("0")
    nhf_contributions: Decimal = Decimal("0")
    nhis_contributions: Decimal = Decimal("0")
    life_insurance: Decimal = Decimal("0")
    taxable_income: Decimal = Decimal("0")
    paye_withheld: Decimal = Decimal("0")
    
    # Metadata
    generated_at: datetime = field(default_factory=datetime.utcnow)
    form_code: str = TaxProMaxFormCode.PAYE_MONTHLY.value


@dataclass
class WHTEntry:
    """Single WHT deduction entry."""
    payee_tin: str
    payee_name: str
    service_type: str
    contract_value: Decimal
    wht_rate: Decimal
    wht_amount: Decimal
    payment_date: date
    invoice_reference: Optional[str] = None


@dataclass
class WHTSelfAssessment:
    """WHT return self-assessment data."""
    entity_id: uuid.UUID
    period_year: int
    period_month: int
    tin: str
    
    entries: List[WHTEntry] = field(default_factory=list)
    total_wht: Decimal = Decimal("0")
    
    # Metadata
    generated_at: datetime = field(default_factory=datetime.utcnow)
    form_code: str = TaxProMaxFormCode.WHT_MONTHLY.value


@dataclass
class AnnualReturnsSummary:
    """Complete annual returns package summary."""
    entity_id: uuid.UUID
    fiscal_year: int
    tin: str
    company_name: str
    
    # Tax Components
    cit_assessment: Optional[CITSelfAssessment] = None
    vat_assessments: List[VATSelfAssessment] = field(default_factory=list)
    paye_assessments: List[PAYESelfAssessment] = field(default_factory=list)
    wht_assessments: List[WHTSelfAssessment] = field(default_factory=list)
    
    # Totals
    total_cit: Decimal = Decimal("0")
    total_vat: Decimal = Decimal("0")
    total_paye: Decimal = Decimal("0")
    total_wht: Decimal = Decimal("0")
    development_levy: Decimal = Decimal("0")
    grand_total: Decimal = Decimal("0")
    
    # Metadata
    generated_at: datetime = field(default_factory=datetime.utcnow)
    form_code: str = TaxProMaxFormCode.ANNUAL_RETURNS.value


# ===========================================
# SERVICE CLASS
# ===========================================

class SelfAssessmentService:
    """
    Service for generating self-assessment tax returns.
    
    Pre-fills NRS TaxPro Max forms based on yearly financial data.
    Supports export to CSV/Excel formats compatible with TaxPro Max upload.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # ===========================================
    # CIT SELF-ASSESSMENT
    # ===========================================
    
    async def generate_cit_assessment(
        self,
        entity_id: uuid.UUID,
        fiscal_year: int,
    ) -> CITSelfAssessment:
        """
        Generate CIT self-assessment for a fiscal year.
        
        Calculates:
        - Assessable profit from transactions
        - Tax rate based on company classification
        - CIT liability
        - Capital gains (taxed at CIT rate under 2026)
        - Development Levy if applicable
        """
        # Get entity
        entity = await self._get_entity(entity_id)
        if not entity:
            raise ValueError(f"Entity {entity_id} not found")
        
        # Calculate fiscal year dates
        fiscal_start = date(fiscal_year, entity.fiscal_year_start_month, 1)
        if entity.fiscal_year_start_month == 1:
            fiscal_end = date(fiscal_year, 12, 31)
        else:
            fiscal_end = date(fiscal_year + 1, entity.fiscal_year_start_month - 1, 28)
        
        # Get income (revenue)
        income_result = await self.db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_type == TransactionType.INCOME)
            .where(Transaction.date >= fiscal_start)
            .where(Transaction.date <= fiscal_end)
        )
        gross_turnover = Decimal(str(income_result.scalar() or 0))
        
        # Get cost of sales
        cost_result = await self.db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_type == TransactionType.EXPENSE)
            .where(Transaction.category_id.isnot(None))  # Direct costs
            .where(Transaction.date >= fiscal_start)
            .where(Transaction.date <= fiscal_end)
        )
        cost_of_sales = Decimal(str(cost_result.scalar() or 0)) * Decimal("0.4")  # Estimate 40% as COGS
        
        # Get operating expenses
        expense_result = await self.db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_type == TransactionType.EXPENSE)
            .where(Transaction.date >= fiscal_start)
            .where(Transaction.date <= fiscal_end)
        )
        total_expenses = Decimal(str(expense_result.scalar() or 0))
        operating_expenses = total_expenses - cost_of_sales
        
        # Get depreciation from fixed assets
        depreciation = await self._calculate_depreciation(entity_id, fiscal_year)
        
        # Get capital gains from disposed assets
        capital_gains = await self._calculate_capital_gains(entity_id, fiscal_year)
        
        # Calculate profits
        gross_profit = gross_turnover - cost_of_sales
        net_profit_before_tax = gross_profit - operating_expenses - depreciation
        
        # Tax adjustments (simplified)
        add_backs = operating_expenses * Decimal("0.05")  # 5% non-deductible estimate
        assessable_profit = net_profit_before_tax + add_backs
        
        # Determine company classification and tax rate
        company_class, tax_rate = self._determine_tax_rate(
            gross_turnover,
            entity.fixed_assets_value or Decimal("0"),
        )
        
        # Calculate CIT
        if assessable_profit > 0:
            cit_liability = assessable_profit * (tax_rate / 100)
        else:
            cit_liability = Decimal("0")
        
        # Capital gains taxed at CIT rate under 2026
        if capital_gains > 0:
            cgt_liability = capital_gains * (tax_rate / 100)
        else:
            cgt_liability = Decimal("0")
        
        # Total tax
        total_tax_payable = cit_liability + cgt_liability
        
        # WHT credits (from transactions marked as having WHT)
        wht_credits = await self._get_wht_credits(entity_id, fiscal_year)
        
        # Net tax payable
        net_tax_payable = max(total_tax_payable - wht_credits, Decimal("0"))
        
        # Development Levy (4% for large companies)
        development_levy = Decimal("0")
        if company_class == "large":
            development_levy = assessable_profit * Decimal("0.04")
        
        return CITSelfAssessment(
            entity_id=entity_id,
            fiscal_year_end=fiscal_end,
            tin=entity.tin or "",
            rc_number=entity.rc_number,
            company_name=entity.name,
            gross_turnover=gross_turnover,
            cost_of_sales=cost_of_sales,
            gross_profit=gross_profit,
            operating_expenses=operating_expenses,
            depreciation=depreciation,
            net_profit_before_tax=net_profit_before_tax,
            add_backs=add_backs,
            allowable_deductions=Decimal("0"),
            assessable_profit=assessable_profit,
            company_classification=company_class,
            tax_rate=tax_rate,
            cit_liability=cit_liability,
            capital_gains=capital_gains,
            cgt_liability=cgt_liability,
            wht_credits=wht_credits,
            total_tax_payable=total_tax_payable,
            net_tax_payable=net_tax_payable,
            development_levy=development_levy,
        )
    
    # ===========================================
    # VAT SELF-ASSESSMENT
    # ===========================================
    
    async def generate_vat_assessment(
        self,
        entity_id: uuid.UUID,
        year: int,
        month: int,
    ) -> VATSelfAssessment:
        """Generate monthly VAT return assessment."""
        entity = await self._get_entity(entity_id)
        if not entity:
            raise ValueError(f"Entity {entity_id} not found")
        
        # Get sales invoices for the period
        sales_result = await self.db.execute(
            select(
                func.coalesce(func.sum(Invoice.subtotal), 0).label("subtotal"),
                func.coalesce(func.sum(Invoice.vat_amount), 0).label("vat"),
            )
            .where(Invoice.entity_id == entity_id)
            .where(Invoice.invoice_type == InvoiceType.INVOICE)
            .where(extract('year', Invoice.issue_date) == year)
            .where(extract('month', Invoice.issue_date) == month)
        )
        sales_row = sales_result.one()
        standard_rated_sales = Decimal(str(sales_row.subtotal or 0))
        output_vat = Decimal(str(sales_row.vat or 0))
        
        # Get purchases (expenses with VAT)
        purchase_result = await self.db.execute(
            select(
                func.coalesce(func.sum(Transaction.amount), 0).label("amount"),
                func.coalesce(func.sum(Transaction.vat_amount), 0).label("vat"),
            )
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_type == TransactionType.EXPENSE)
            .where(extract('year', Transaction.date) == year)
            .where(extract('month', Transaction.date) == month)
        )
        purchase_row = purchase_result.one()
        standard_rated_purchases = Decimal(str(purchase_row.amount or 0))
        input_vat = Decimal(str(purchase_row.vat or 0))
        
        # Input VAT on fixed assets (2026 now allows recovery)
        input_vat_fixed_assets = await self._get_fixed_asset_vat(entity_id, year, month)
        
        total_input_vat = input_vat + input_vat_fixed_assets
        total_sales = standard_rated_sales
        total_purchases = standard_rated_purchases
        
        # Net VAT position
        net_vat_payable = output_vat - total_input_vat
        refund_claimed = Decimal("0") if net_vat_payable >= 0 else abs(net_vat_payable)
        
        return VATSelfAssessment(
            entity_id=entity_id,
            period_year=year,
            period_month=month,
            tin=entity.tin or "",
            standard_rated_sales=standard_rated_sales,
            zero_rated_sales=Decimal("0"),
            exempt_sales=Decimal("0"),
            total_sales=total_sales,
            output_vat=output_vat,
            standard_rated_purchases=standard_rated_purchases,
            zero_rated_purchases=Decimal("0"),
            exempt_purchases=Decimal("0"),
            total_purchases=total_purchases,
            input_vat=input_vat,
            input_vat_fixed_assets=input_vat_fixed_assets,
            total_input_vat=total_input_vat,
            net_vat_payable=max(net_vat_payable, Decimal("0")),
            refund_claimed=refund_claimed,
        )
    
    # ===========================================
    # ANNUAL RETURNS PACKAGE
    # ===========================================
    
    async def generate_annual_returns(
        self,
        entity_id: uuid.UUID,
        fiscal_year: int,
    ) -> AnnualReturnsSummary:
        """
        Generate complete annual returns package for TaxPro Max.
        
        Includes:
        - CIT assessment
        - 12 monthly VAT returns
        - 12 monthly PAYE returns
        - WHT summary
        - Development Levy calculation
        """
        entity = await self._get_entity(entity_id)
        if not entity:
            raise ValueError(f"Entity {entity_id} not found")
        
        # Generate CIT assessment
        cit_assessment = await self.generate_cit_assessment(entity_id, fiscal_year)
        
        # Generate 12 monthly VAT returns
        vat_assessments = []
        for month in range(1, 13):
            try:
                vat = await self.generate_vat_assessment(entity_id, fiscal_year, month)
                vat_assessments.append(vat)
            except Exception:
                pass  # Skip months with no data
        
        # Calculate totals
        total_vat = sum(v.net_vat_payable for v in vat_assessments)
        
        return AnnualReturnsSummary(
            entity_id=entity_id,
            fiscal_year=fiscal_year,
            tin=entity.tin or "",
            company_name=entity.name,
            cit_assessment=cit_assessment,
            vat_assessments=vat_assessments,
            paye_assessments=[],  # Placeholder for PAYE
            wht_assessments=[],   # Placeholder for WHT
            total_cit=cit_assessment.net_tax_payable,
            total_vat=total_vat,
            total_paye=Decimal("0"),
            total_wht=cit_assessment.wht_credits,
            development_levy=cit_assessment.development_levy,
            grand_total=(
                cit_assessment.net_tax_payable +
                total_vat +
                cit_assessment.development_levy
            ),
        )
    
    # ===========================================
    # TAXPRO MAX EXPORT
    # ===========================================
    
    def export_cit_to_csv(self, assessment: CITSelfAssessment) -> str:
        """Export CIT assessment to TaxPro Max CSV format."""
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(TAXPRO_CIT_COLUMNS)
        
        # Write data row
        writer.writerow([
            assessment.tin,
            assessment.rc_number or "",
            assessment.company_name,
            assessment.fiscal_year_end.isoformat(),
            str(assessment.gross_turnover),
            str(assessment.cost_of_sales),
            str(assessment.gross_profit),
            str(assessment.operating_expenses),
            str(assessment.depreciation),
            str(assessment.net_profit_before_tax),
            str(assessment.add_backs),
            str(assessment.allowable_deductions),
            str(assessment.assessable_profit),
            str(assessment.tax_rate),
            str(assessment.cit_liability),
            str(assessment.capital_gains),
            str(assessment.cgt_liability),
            str(assessment.total_tax_payable),
            str(assessment.wht_credits),
            str(assessment.net_tax_payable),
            str(assessment.development_levy),
        ])
        
        return output.getvalue()
    
    def export_vat_to_csv(self, assessments: List[VATSelfAssessment]) -> str:
        """Export VAT assessments to TaxPro Max CSV format."""
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(TAXPRO_VAT_COLUMNS)
        
        # Write data rows
        for vat in assessments:
            writer.writerow([
                vat.tin,
                vat.period_year,
                vat.period_month,
                str(vat.standard_rated_sales),
                str(vat.zero_rated_sales),
                str(vat.exempt_sales),
                str(vat.total_sales),
                str(vat.output_vat),
                str(vat.standard_rated_purchases),
                str(vat.zero_rated_purchases),
                str(vat.exempt_purchases),
                str(vat.total_purchases),
                str(vat.input_vat),
                str(vat.input_vat_fixed_assets),
                str(vat.total_input_vat),
                str(vat.net_vat_payable),
                str(vat.refund_claimed),
            ])
        
        return output.getvalue()
    
    def export_annual_summary_json(
        self,
        summary: AnnualReturnsSummary,
    ) -> Dict[str, Any]:
        """Export annual returns summary as JSON for API response."""
        return {
            "entity_id": str(summary.entity_id),
            "fiscal_year": summary.fiscal_year,
            "tin": summary.tin,
            "company_name": summary.company_name,
            "generated_at": summary.generated_at.isoformat(),
            "form_code": summary.form_code,
            "summary": {
                "total_cit": float(summary.total_cit),
                "total_vat": float(summary.total_vat),
                "total_paye": float(summary.total_paye),
                "total_wht": float(summary.total_wht),
                "development_levy": float(summary.development_levy),
                "grand_total": float(summary.grand_total),
            },
            "cit_assessment": self._cit_to_dict(summary.cit_assessment) if summary.cit_assessment else None,
            "vat_monthly_breakdown": [
                {
                    "month": v.period_month,
                    "output_vat": float(v.output_vat),
                    "input_vat": float(v.total_input_vat),
                    "net_vat": float(v.net_vat_payable),
                }
                for v in summary.vat_assessments
            ],
            "taxpro_max": {
                "form_codes": [
                    TaxProMaxFormCode.CIT_ANNUAL.value,
                    TaxProMaxFormCode.VAT_MONTHLY.value,
                    TaxProMaxFormCode.DEV_LEVY_ANNUAL.value,
                ],
                "export_formats": ["csv", "xlsx", "json"],
                "upload_portal": "https://taxpromax.nrs.gov.ng/",
            },
        }
    
    # ===========================================
    # HELPER METHODS
    # ===========================================
    
    async def _get_entity(self, entity_id: uuid.UUID) -> Optional[BusinessEntity]:
        """Get entity by ID."""
        result = await self.db.execute(
            select(BusinessEntity).where(BusinessEntity.id == entity_id)
        )
        return result.scalar_one_or_none()
    
    async def _calculate_depreciation(
        self,
        entity_id: uuid.UUID,
        fiscal_year: int,
    ) -> Decimal:
        """Calculate total depreciation for the fiscal year."""
        result = await self.db.execute(
            select(FixedAsset)
            .where(FixedAsset.entity_id == entity_id)
            .where(FixedAsset.status == AssetStatus.ACTIVE)
        )
        assets = list(result.scalars().all())
        
        total_depreciation = Decimal("0")
        for asset in assets:
            annual_dep = asset.calculate_annual_depreciation()
            total_depreciation += annual_dep
        
        return total_depreciation
    
    async def _calculate_capital_gains(
        self,
        entity_id: uuid.UUID,
        fiscal_year: int,
    ) -> Decimal:
        """Calculate total capital gains from disposed assets."""
        result = await self.db.execute(
            select(FixedAsset)
            .where(FixedAsset.entity_id == entity_id)
            .where(FixedAsset.status == AssetStatus.DISPOSED)
            .where(extract('year', FixedAsset.disposal_date) == fiscal_year)
        )
        assets = list(result.scalars().all())
        
        total_gains = Decimal("0")
        for asset in assets:
            gain = asset.capital_gain_on_disposal
            if gain and gain > 0:
                total_gains += gain
        
        return total_gains
    
    async def _get_wht_credits(
        self,
        entity_id: uuid.UUID,
        fiscal_year: int,
    ) -> Decimal:
        """Get WHT credits from transactions."""
        result = await self.db.execute(
            select(func.coalesce(func.sum(Transaction.wht_amount), 0))
            .where(Transaction.entity_id == entity_id)
            .where(extract('year', Transaction.date) == fiscal_year)
        )
        return Decimal(str(result.scalar() or 0))
    
    async def _get_fixed_asset_vat(
        self,
        entity_id: uuid.UUID,
        year: int,
        month: int,
    ) -> Decimal:
        """Get input VAT on fixed assets acquired in the period."""
        result = await self.db.execute(
            select(func.coalesce(func.sum(FixedAsset.vat_amount), 0))
            .where(FixedAsset.entity_id == entity_id)
            .where(FixedAsset.vendor_irn.isnot(None))  # Valid IRN for recovery
            .where(extract('year', FixedAsset.acquisition_date) == year)
            .where(extract('month', FixedAsset.acquisition_date) == month)
        )
        return Decimal(str(result.scalar() or 0))
    
    def _determine_tax_rate(
        self,
        turnover: Decimal,
        fixed_assets: Decimal,
    ) -> Tuple[str, Decimal]:
        """
        Determine company classification and CIT rate under 2026 law.
        
        Returns: (classification, rate)
        """
        # Small company: Turnover <= ₦50M = 0%
        if turnover <= Decimal("50000000"):
            return ("small", Decimal("0"))
        
        # Medium company: Turnover > ₦50M and <= ₦200M = 20%
        if turnover <= Decimal("200000000"):
            return ("medium", Decimal("20"))
        
        # Large company: Turnover > ₦200M = 30%
        return ("large", Decimal("30"))
    
    def _cit_to_dict(self, cit: CITSelfAssessment) -> Dict[str, Any]:
        """Convert CIT assessment to dictionary."""
        return {
            "fiscal_year_end": cit.fiscal_year_end.isoformat(),
            "company_classification": cit.company_classification,
            "income_statement": {
                "gross_turnover": float(cit.gross_turnover),
                "cost_of_sales": float(cit.cost_of_sales),
                "gross_profit": float(cit.gross_profit),
                "operating_expenses": float(cit.operating_expenses),
                "depreciation": float(cit.depreciation),
                "net_profit_before_tax": float(cit.net_profit_before_tax),
            },
            "tax_computation": {
                "add_backs": float(cit.add_backs),
                "allowable_deductions": float(cit.allowable_deductions),
                "assessable_profit": float(cit.assessable_profit),
                "tax_rate_percent": float(cit.tax_rate),
                "cit_liability": float(cit.cit_liability),
            },
            "capital_gains": {
                "total_gains": float(cit.capital_gains),
                "cgt_liability": float(cit.cgt_liability),
                "note": "Under 2026 law, capital gains are taxed at the flat CIT rate",
            },
            "final_computation": {
                "total_tax_payable": float(cit.total_tax_payable),
                "wht_credits": float(cit.wht_credits),
                "net_tax_payable": float(cit.net_tax_payable),
                "development_levy": float(cit.development_levy),
            },
        }
