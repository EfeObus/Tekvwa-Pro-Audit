"""
Tekvwa Pro Audit - Dashboard Schemas

Pydantic schemas for world-class organizational dashboards.

NTAA 2025 Compliance Features:
- Tax Health Score (Red/Amber/Green indicator)
- NRS Connection Status (heartbeat monitor)
- Compliance Calendar (VAT 21st, PAYE 10th deadlines)
- Liquidity Ratio widget
- Organization-Type-Specific Dashboard Data

Permission Matrix (Maker-Checker View):
- Owner: Full access to all widgets
- Accountant: Financial statements (Full), WREN (Maker)
- External Accountant: View + File, WREN (Checker - Final)
- Sales Staff: Draft invoices only, No financial access
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field


# ===========================================
# ENUMS
# ===========================================

class TaxHealthStatus(str, Enum):
    """Tax Health Score status - Red/Amber/Green indicator."""
    RED = "red"           # Critical issues - missing TIN, unfiled VAT
    AMBER = "amber"       # Warnings - approaching deadlines
    GREEN = "green"       # All compliant


class NRSConnectionStatus(str, Enum):
    """NRS (Nigeria Revenue Service) connection status."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class WRENStatus(str, Enum):
    """WREN expense verification status."""
    PENDING = "pending"       # Not yet categorized
    MAKER_DONE = "maker_done" # Categorized by Maker, awaiting Checker
    VERIFIED = "verified"     # Checker has verified
    REJECTED = "rejected"     # Checker rejected categorization


class DashboardViewLevel(str, Enum):
    """Permission-based view levels for dashboard widgets."""
    FULL = "full"           # Complete access
    VIEW_FILE = "view_file" # View + file tax returns
    VIEW_ONLY = "view_only" # Read-only access
    DRAFT_ONLY = "draft_only" # Draft operations only
    NO_ACCESS = "no_access" # Widget hidden


# ===========================================
# TAX HEALTH SCORE
# ===========================================

class TaxHealthCheck(BaseModel):
    """Individual tax health check item."""
    name: str = Field(..., description="Check name (e.g., 'TIN Registration')")
    status: str = Field(..., description="pass, warning, fail, info")
    message: str = Field(..., description="Status message")
    icon: str = Field("check-circle", description="Icon name")
    is_critical: bool = Field(False, description="Is this a blocking issue?")


class TaxHealthScore(BaseModel):
    """
    Tax Health Score - Real-time Red/Amber/Green indicator.
    
    Based on:
    - Missing TINs
    - Unfiled VAT
    - Unverified WREN expenses
    - Approaching deadlines
    """
    status: TaxHealthStatus = Field(..., description="Overall status")
    score: int = Field(..., ge=0, le=100, description="Numeric score 0-100")
    checks: List[TaxHealthCheck] = Field(default_factory=list)
    issues_count: int = Field(0, description="Number of critical issues")
    warnings_count: int = Field(0, description="Number of warnings")
    summary: str = Field("", description="Human-readable summary")
    
    # Specific issues
    missing_tin: bool = Field(False)
    unfiled_vat: bool = Field(False)
    pending_wren_expenses: int = Field(0)
    overdue_filings: int = Field(0)


# ===========================================
# NRS CONNECTION STATUS
# ===========================================

class NRSStatus(BaseModel):
    """
    NRS Connection Status - Heartbeat monitor.
    
    Shows if the app is currently synced with Nigeria Revenue Service.
    """
    status: NRSConnectionStatus = Field(NRSConnectionStatus.UNKNOWN)
    endpoint: str = Field("", description="NRS API endpoint")
    last_sync: Optional[datetime] = Field(None, description="Last successful sync")
    latency_ms: Optional[int] = Field(None, description="API latency in ms")
    uptime_percentage: Optional[float] = Field(None, description="24h uptime %")
    pending_submissions: int = Field(0, description="Invoices pending NRS submission")
    failed_submissions: int = Field(0, description="Failed submissions to retry")
    message: str = Field("", description="Status message")


# ===========================================
# COMPLIANCE CALENDAR
# ===========================================

class DeadlineItem(BaseModel):
    """Single compliance deadline."""
    name: str = Field(..., description="Deadline name (e.g., 'VAT Filing')")
    due_date: date = Field(..., description="Due date")
    days_remaining: int = Field(..., description="Days until deadline")
    urgency: str = Field("low", description="high, medium, low")
    tax_type: str = Field("", description="VAT, PAYE, CIT, WHT, etc.")
    amount_due: Optional[Decimal] = Field(None, description="Estimated amount due")
    is_overdue: bool = Field(False)
    
    # Filing status
    is_filed: bool = Field(False)
    completed_date: Optional[date] = Field(None)
    filing_reference: Optional[str] = Field(None)


class ComplianceCalendar(BaseModel):
    """
    Compliance Calendar - Automatic countdowns.
    
    - VAT: 21st of every month
    - PAYE: 10th of every month
    - CIT: 6 months after fiscal year end
    - WHT: 21st of every month
    """
    next_vat_deadline: Optional[DeadlineItem] = None
    next_paye_deadline: Optional[DeadlineItem] = None
    next_cit_deadline: Optional[DeadlineItem] = None
    next_wht_deadline: Optional[DeadlineItem] = None
    
    upcoming_deadlines: List[DeadlineItem] = Field(default_factory=list)
    overdue_items: List[DeadlineItem] = Field(default_factory=list)
    
    current_month: str = Field("", description="Current month name")
    current_year: int = Field(2026)


# ===========================================
# LIQUIDITY RATIO
# ===========================================

class LiquidityRatio(BaseModel):
    """
    Liquidity Ratio widget - Cash Runway tracking.
    
    Formula: Cash / Average Monthly Expenses
    2026 "Cash Runway" requirement.
    """
    cash_balance: Decimal = Field(Decimal("0"), description="Current cash balance")
    avg_monthly_expenses: Decimal = Field(Decimal("0"), description="Average monthly expenses")
    ratio: float = Field(0.0, description="Cash / Avg Monthly Expenses")
    runway_months: float = Field(0.0, description="Months of runway remaining")
    
    # Status
    status: str = Field("unknown", description="healthy, warning, critical")
    message: str = Field("")
    
    # Trend
    trend_direction: str = Field("stable", description="up, down, stable")
    previous_ratio: Optional[float] = Field(None)


# ===========================================
# SME & SMALL BUSINESS DASHBOARD
# ===========================================

class ThresholdMonitor(BaseModel):
    """
    Threshold Monitor - Progress towards tax thresholds.
    
    Vital for knowing when SME moves from 0% to 30% tax.
    """
    current_turnover: Decimal = Field(Decimal("0"))
    threshold_50m: Decimal = Field(Decimal("50000000"))  # ₦50M
    threshold_100m: Decimal = Field(Decimal("100000000"))  # ₦100M
    
    # Progress towards 50M
    progress_50m_percentage: float = Field(0.0)
    remaining_to_50m: Decimal = Field(Decimal("50000000"))
    
    # Progress towards 100M
    progress_100m_percentage: float = Field(0.0)
    remaining_to_100m: Decimal = Field(Decimal("100000000"))
    
    # Current status
    current_tier: str = Field("small", description="small (0% CIT), medium (20% CIT), large (30% CIT)")
    estimated_cit_rate: int = Field(0, description="Current CIT rate %")
    
    # Alert if approaching threshold
    approaching_threshold: bool = Field(False)
    threshold_alert: Optional[str] = Field(None)


class VATRecoveryTracker(BaseModel):
    """
    VAT Recovery Tracker - Input VAT Credits.
    
    Shows VAT Paid to Vendors vs VAT Collected from Customers.
    """
    vat_collected: Decimal = Field(Decimal("0"), description="VAT collected from sales")
    vat_paid: Decimal = Field(Decimal("0"), description="VAT paid on purchases")
    net_vat: Decimal = Field(Decimal("0"), description="Net VAT payable/recoverable")
    
    # Recovery status
    is_recoverable: bool = Field(False, description="Is there VAT to recover?")
    recoverable_amount: Decimal = Field(Decimal("0"))
    
    # Period
    period_start: date = Field(default_factory=date.today)
    period_end: date = Field(default_factory=date.today)
    
    # Filing status
    last_vat_filing: Optional[date] = Field(None)
    next_filing_due: Optional[date] = Field(None)


class WRENValidatorItem(BaseModel):
    """Single expense requiring WREN categorization."""
    id: UUID
    description: str
    amount: Decimal
    date: date
    vendor_name: Optional[str] = None
    current_category: Optional[str] = None
    suggested_category: Optional[str] = None
    status: WRENStatus = WRENStatus.PENDING
    created_by_id: Optional[UUID] = None
    created_by_name: Optional[str] = None


class WRENValidator(BaseModel):
    """
    WREN Validator - Queue of uncategorized expenses.
    
    Wholly, Exclusively, and Necessarily for business.
    Maker-Checker Segregation of Duties (SoD).
    """
    pending_count: int = Field(0, description="Expenses needing categorization")
    pending_expenses: List[WRENValidatorItem] = Field(default_factory=list)
    
    # Stats
    total_pending_amount: Decimal = Field(Decimal("0"))
    oldest_pending_date: Optional[date] = Field(None)
    
    # User's role in WREN process
    can_categorize: bool = Field(False, description="Is Maker")
    can_verify: bool = Field(False, description="Is Checker")


class SMEDashboard(BaseModel):
    """SME & Small Business specialized dashboard."""
    threshold_monitor: ThresholdMonitor
    vat_recovery: VATRecoveryTracker
    wren_validator: WRENValidator


# ===========================================
# SCHOOL DASHBOARD
# ===========================================

class TeacherPAYESummary(BaseModel):
    """
    Teacher PAYE Summary - 2026 progressive bands.
    
    0% for the first ₦800,000.
    """
    total_staff: int = Field(0)
    total_teachers: int = Field(0)
    total_monthly_payroll: Decimal = Field(Decimal("0"))
    total_paye_liability: Decimal = Field(Decimal("0"))
    
    # Breakdown by band
    staff_in_tax_free_band: int = Field(0, description="Earning <= ₦800K/year")
    staff_in_7_percent_band: int = Field(0, description="₦800K - ₦1.6M")
    staff_in_higher_bands: int = Field(0)
    
    next_paye_filing: Optional[date] = Field(None)
    last_paye_filing: Optional[date] = Field(None)


class FeeCollectionVAT(BaseModel):
    """
    Fee Collection vs VAT Exemption.
    
    Separates tuition (VAT Exempt) from uniforms/books (Taxable).
    """
    tuition_fees_collected: Decimal = Field(Decimal("0"), description="VAT Exempt")
    taxable_sales: Decimal = Field(Decimal("0"), description="Uniforms, books, etc.")
    vat_on_taxable_sales: Decimal = Field(Decimal("0"))
    
    # Breakdown
    uniform_sales: Decimal = Field(Decimal("0"))
    book_sales: Decimal = Field(Decimal("0"))
    other_taxable: Decimal = Field(Decimal("0"))


class VendorWHTVault(BaseModel):
    """
    Vendor WHT Vault - Withholding Tax tracking.
    
    5-10% WHT deducted from school contractors/suppliers.
    """
    total_wht_deducted: Decimal = Field(Decimal("0"))
    pending_remittance: Decimal = Field(Decimal("0"))
    last_remittance_date: Optional[date] = Field(None)
    next_remittance_due: Optional[date] = Field(None)
    
    # Breakdown
    contractors_wht: Decimal = Field(Decimal("0"), description="10% WHT")
    suppliers_wht: Decimal = Field(Decimal("0"), description="5% WHT")
    
    vendors_with_pending_wht: int = Field(0)


class SchoolDashboard(BaseModel):
    """School Management specialized dashboard."""
    teacher_paye: TeacherPAYESummary
    fee_collection: FeeCollectionVAT
    wht_vault: VendorWHTVault


# ===========================================
# NON-PROFIT DASHBOARD
# ===========================================

class ReturnOnMission(BaseModel):
    """
    Return on Mission (ROM) Widget.
    
    Tracks % of every Naira spent on Program vs Admin/Fundraising.
    """
    total_expenses: Decimal = Field(Decimal("0"))
    program_expenses: Decimal = Field(Decimal("0"))
    admin_expenses: Decimal = Field(Decimal("0"))
    fundraising_expenses: Decimal = Field(Decimal("0"))
    
    # Percentages
    program_percentage: float = Field(0.0, description="% spent on mission")
    admin_percentage: float = Field(0.0)
    fundraising_percentage: float = Field(0.0)
    
    # Industry benchmark
    benchmark_program_min: float = Field(75.0, description="Minimum recommended for programs")
    meets_benchmark: bool = Field(False)
    
    # ROM Score
    rom_score: str = Field("N/A", description="A, B, C, D, F rating")


class FundSeparation(BaseModel):
    """
    Restricted vs Unrestricted Funds.
    
    Grant money (Exempt) vs Commercial Trading (Taxable).
    """
    total_funds: Decimal = Field(Decimal("0"))
    
    # Restricted funds (grants, donations with conditions)
    restricted_funds: Decimal = Field(Decimal("0"))
    restricted_percentage: float = Field(0.0)
    
    # Unrestricted funds (general donations, trading income)
    unrestricted_funds: Decimal = Field(Decimal("0"))
    unrestricted_percentage: float = Field(0.0)
    
    # Taxable income from trading
    trading_income: Decimal = Field(Decimal("0"), description="Taxable")
    grant_income: Decimal = Field(Decimal("0"), description="Tax Exempt")


class DonorTransparencyReport(BaseModel):
    """
    Donor Transparency Portal.
    
    One-click Audit-Ready Report for donors.
    """
    can_generate_report: bool = Field(False)
    last_report_date: Optional[date] = Field(None)
    
    # Summary stats for donors
    total_donations_ytd: Decimal = Field(Decimal("0"))
    total_program_spending_ytd: Decimal = Field(Decimal("0"))
    beneficiaries_served: int = Field(0)
    
    # Compliance
    charity_registration_valid: bool = Field(False)
    tax_exemption_certificate: bool = Field(False)


class NonProfitDashboard(BaseModel):
    """Non-Profit (NGO) specialized dashboard."""
    return_on_mission: ReturnOnMission
    fund_separation: FundSeparation
    donor_transparency: DonorTransparencyReport


# ===========================================
# INDIVIDUAL/FREELANCER DASHBOARD
# ===========================================

class TaxFreeBandTracker(BaseModel):
    """
    Tax-Free Band Tracker.
    
    Shows how much of ₦800,000 tax-free allowance is used.
    """
    tax_free_limit: Decimal = Field(Decimal("800000"))
    income_ytd: Decimal = Field(Decimal("0"))
    
    # Remaining allowance
    remaining_tax_free: Decimal = Field(Decimal("800000"))
    tax_free_used_percentage: float = Field(0.0)
    
    # Is income still in tax-free band?
    is_in_tax_free_band: bool = Field(True)
    
    # Next band info
    next_band_starts_at: Decimal = Field(Decimal("800000"))
    next_band_rate: int = Field(7, description="7% rate after ₦800K")
    
    # Estimated tax
    estimated_annual_tax: Decimal = Field(Decimal("0"))


class ReliefDocumentVault(BaseModel):
    """
    Relief Document Vault.
    
    Store Rent Receipts (20% relief), NHIA, Pension contributions.
    """
    # Rent relief (20% of rental income or rent paid)
    rent_receipts_count: int = Field(0)
    total_rent_paid: Decimal = Field(Decimal("0"))
    rent_relief_amount: Decimal = Field(Decimal("0"))
    
    # NHIA contributions
    nhia_contributions: Decimal = Field(Decimal("0"))
    
    # Pension contributions
    pension_contributions: Decimal = Field(Decimal("0"))
    
    # Life insurance premiums
    life_insurance_premiums: Decimal = Field(Decimal("0"))
    
    # Total reliefs
    total_reliefs: Decimal = Field(Decimal("0"))
    
    # Document upload status
    documents_uploaded: int = Field(0)
    documents_verified: int = Field(0)


class HustlePersonalToggle(BaseModel):
    """
    Hustle vs Personal Toggle.
    
    Separates business expenses from personal groceries.
    """
    # Summary
    total_transactions: int = Field(0)
    business_transactions: int = Field(0)
    personal_transactions: int = Field(0)
    untagged_transactions: int = Field(0)
    
    # Amounts
    business_expenses: Decimal = Field(Decimal("0"))
    personal_expenses: Decimal = Field(Decimal("0"))
    untagged_amount: Decimal = Field(Decimal("0"))
    
    # Tax implication
    deductible_expenses: Decimal = Field(Decimal("0"))
    non_deductible_expenses: Decimal = Field(Decimal("0"))


class IndividualDashboard(BaseModel):
    """Individual/Freelancer specialized dashboard."""
    tax_free_tracker: TaxFreeBandTracker
    relief_vault: ReliefDocumentVault
    hustle_toggle: HustlePersonalToggle


# ===========================================
# MISSING WORLD-CLASS MODULES
# ===========================================

class EFSStatus(BaseModel):
    """
    Electronic Fiscal System (EFS) Status.
    
    NTAA 2025 Section 42 - Mandatory digital record keeping.
    """
    is_compliant: bool = Field(False)
    efs_registration_id: Optional[str] = Field(None)
    last_audit_date: Optional[date] = Field(None)
    records_digital_percentage: float = Field(0.0)
    pending_digitization: int = Field(0)
    message: str = Field("")


class AssetRegister(BaseModel):
    """
    Asset Register - Depreciation & Capital Gains tracking.
    
    Replaces old Capital Allowance proration.
    """
    total_assets: int = Field(0)
    total_asset_value: Decimal = Field(Decimal("0"))
    accumulated_depreciation: Decimal = Field(Decimal("0"))
    net_book_value: Decimal = Field(Decimal("0"))
    
    # Depreciation this year
    depreciation_ytd: Decimal = Field(Decimal("0"))
    
    # Assets approaching end of life
    assets_fully_depreciated: int = Field(0)
    assets_near_disposal: int = Field(0)


class NRSIRNGenerator(BaseModel):
    """
    NRS IRN Generator status.
    
    Embeds unique Invoice Reference Number on PDFs.
    Mandatory for invoice to be "Legal."
    """
    is_configured: bool = Field(False)
    total_irn_generated: int = Field(0)
    irn_generated_this_month: int = Field(0)
    pending_irn_generation: int = Field(0)
    last_irn_generated_at: Optional[datetime] = Field(None)


class DevelopmentLevyCalc(BaseModel):
    """
    Development Levy Calculator.
    
    Automatic 4% calculation on assessable profit.
    Replaces old Education/Police taxes.
    """
    assessable_profit: Decimal = Field(Decimal("0"))
    development_levy_rate: float = Field(4.0)
    estimated_levy: Decimal = Field(Decimal("0"))
    
    # Exemption check
    is_exempt: bool = Field(False, description="Turnover <= ₦100M exemption")
    exemption_reason: Optional[str] = Field(None)
    
    # Filing status
    last_filed: Optional[date] = Field(None)
    next_due: Optional[date] = Field(None)


class WorldClassModules(BaseModel):
    """World-class modules for NTAA 2025 compliance."""
    efs_status: EFSStatus
    asset_register: AssetRegister
    nrs_irn: NRSIRNGenerator
    development_levy: DevelopmentLevyCalc


# ===========================================
# VIEW PERMISSIONS
# ===========================================

class DashboardViewPermissions(BaseModel):
    """
    Permission Level Matrix for dashboard widgets.
    
    Maker-Checker view restrictions.
    """
    financial_statements: DashboardViewLevel = DashboardViewLevel.NO_ACCESS
    nrs_submission: DashboardViewLevel = DashboardViewLevel.NO_ACCESS
    bank_balance: DashboardViewLevel = DashboardViewLevel.NO_ACCESS
    wren_categorization: DashboardViewLevel = DashboardViewLevel.NO_ACCESS
    salary_details: DashboardViewLevel = DashboardViewLevel.NO_ACCESS
    tax_filings: DashboardViewLevel = DashboardViewLevel.NO_ACCESS
    inventory: DashboardViewLevel = DashboardViewLevel.NO_ACCESS
    payroll: DashboardViewLevel = DashboardViewLevel.NO_ACCESS


# ===========================================
# MAIN DASHBOARD RESPONSE
# ===========================================

class OrganizationDashboardResponse(BaseModel):
    """
    Complete organization dashboard response.
    
    World-class dashboard with NTAA 2025 compliance features.
    """
    # User & Organization Info
    user_id: UUID
    user_name: str
    user_role: str
    organization_id: UUID
    organization_name: str
    organization_type: str
    entity_id: Optional[UUID] = None
    entity_name: Optional[str] = None
    
    # Core Widgets (All organizations)
    tax_health_score: TaxHealthScore
    nrs_status: NRSStatus
    compliance_calendar: ComplianceCalendar
    liquidity_ratio: LiquidityRatio
    
    # Organization-Type-Specific Widgets
    sme_dashboard: Optional[SMEDashboard] = None
    school_dashboard: Optional[SchoolDashboard] = None
    nonprofit_dashboard: Optional[NonProfitDashboard] = None
    individual_dashboard: Optional[IndividualDashboard] = None
    
    # World-Class Modules
    world_class_modules: WorldClassModules
    
    # View Permissions
    permissions: DashboardViewPermissions
    
    # Quick Actions (role-based)
    quick_actions: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Metadata
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    cache_ttl_seconds: int = Field(300, description="Cache TTL")

    class Config:
        from_attributes = True
