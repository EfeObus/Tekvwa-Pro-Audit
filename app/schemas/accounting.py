"""
Tekvwa Pro Audit - Accounting Schemas

Pydantic schemas for Chart of Accounts and General Ledger.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, validator, ConfigDict


# =============================================================================
# ENUMS
# =============================================================================

class AccountType(str, Enum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    INCOME = "income"
    EXPENSE = "expense"


class AccountSubType(str, Enum):
    # Asset sub-types
    CASH = "cash"
    BANK = "bank"
    ACCOUNTS_RECEIVABLE = "accounts_receivable"
    INVENTORY = "inventory"
    PREPAID_EXPENSE = "prepaid_expense"
    FIXED_ASSET = "fixed_asset"
    ACCUMULATED_DEPRECIATION = "accumulated_depreciation"
    OTHER_CURRENT_ASSET = "other_current_asset"
    OTHER_NON_CURRENT_ASSET = "other_non_current_asset"
    
    # Liability sub-types
    ACCOUNTS_PAYABLE = "accounts_payable"
    ACCRUED_EXPENSE = "accrued_expense"
    VAT_PAYABLE = "vat_payable"
    WHT_PAYABLE = "wht_payable"
    PAYE_PAYABLE = "paye_payable"
    PENSION_PAYABLE = "pension_payable"
    LOAN = "loan"
    OTHER_CURRENT_LIABILITY = "other_current_liability"
    OTHER_NON_CURRENT_LIABILITY = "other_non_current_liability"
    
    # Equity sub-types
    SHARE_CAPITAL = "share_capital"
    RETAINED_EARNINGS = "retained_earnings"
    DRAWINGS = "drawings"
    OTHER_EQUITY = "other_equity"
    
    # Revenue sub-types
    SALES_REVENUE = "sales_revenue"
    SERVICE_REVENUE = "service_revenue"
    INTEREST_INCOME = "interest_income"
    OTHER_INCOME = "other_income"
    
    # Expense sub-types
    COST_OF_GOODS_SOLD = "cost_of_goods_sold"
    SALARY_EXPENSE = "salary_expense"
    RENT_EXPENSE = "rent_expense"
    UTILITIES_EXPENSE = "utilities_expense"
    DEPRECIATION_EXPENSE = "depreciation_expense"
    BANK_CHARGES = "bank_charges"
    TAX_EXPENSE = "tax_expense"
    OTHER_EXPENSE = "other_expense"


class NormalBalance(str, Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class JournalEntryStatus(str, Enum):
    DRAFT = "draft"
    PENDING = "pending"
    POSTED = "posted"
    REVERSED = "reversed"
    VOIDED = "voided"


class JournalEntryType(str, Enum):
    MANUAL = "manual"
    SALES = "sales"
    PURCHASE = "purchase"
    RECEIPT = "receipt"
    PAYMENT = "payment"
    PAYROLL = "payroll"
    DEPRECIATION = "depreciation"
    TAX_ADJUSTMENT = "tax_adjustment"
    BANK_RECONCILIATION = "bank_reconciliation"
    INVENTORY_ADJUSTMENT = "inventory_adjustment"
    OPENING_BALANCE = "opening_balance"
    CLOSING_ENTRY = "closing_entry"
    REVERSAL = "reversal"
    ACCRUAL = "accrual"
    PREPAYMENT = "prepayment"
    TRANSFER = "transfer"
    SYSTEM = "system"


class FiscalPeriodStatus(str, Enum):
    OPEN = "open"
    PENDING_CLOSE = "pending_close"
    CLOSED = "closed"
    LOCKED = "locked"
    REOPENED = "reopened"


# =============================================================================
# CHART OF ACCOUNTS SCHEMAS
# =============================================================================

class ChartOfAccountsBase(BaseModel):
    """Base schema for Chart of Accounts."""
    account_code: str = Field(..., min_length=1, max_length=20)
    account_name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    account_type: AccountType
    account_sub_type: Optional[AccountSubType] = None
    normal_balance: NormalBalance
    parent_id: Optional[UUID] = None
    is_header: bool = False
    opening_balance: Decimal = Decimal("0.00")
    opening_balance_date: Optional[date] = None
    bank_account_id: Optional[UUID] = None
    is_tax_account: bool = False
    tax_type: Optional[str] = None
    tax_rate: Optional[Decimal] = None
    is_reconcilable: bool = False
    cash_flow_category: Optional[str] = None
    sort_order: int = 0


class ChartOfAccountsCreate(ChartOfAccountsBase):
    """Schema for creating a new account."""
    pass


class ChartOfAccountsUpdate(BaseModel):
    """Schema for updating an account."""
    account_name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    account_sub_type: Optional[AccountSubType] = None
    parent_id: Optional[UUID] = None
    is_header: Optional[bool] = None
    bank_account_id: Optional[UUID] = None
    is_tax_account: Optional[bool] = None
    tax_type: Optional[str] = None
    tax_rate: Optional[Decimal] = None
    is_reconcilable: Optional[bool] = None
    is_active: Optional[bool] = None
    cash_flow_category: Optional[str] = None
    sort_order: Optional[int] = None


class ChartOfAccountsResponse(ChartOfAccountsBase):
    """Schema for account response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    entity_id: UUID
    level: int
    current_balance: Decimal
    ytd_debit: Decimal
    ytd_credit: Decimal
    is_system_account: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ChartOfAccountsTree(ChartOfAccountsResponse):
    """Schema for hierarchical account tree."""
    children: List["ChartOfAccountsTree"] = []


# Self-reference for nested tree
ChartOfAccountsTree.model_rebuild()


class AccountBalanceSummary(BaseModel):
    """Summary of account balance."""
    account_id: UUID
    account_code: str
    account_name: str
    account_type: AccountType
    current_balance: Decimal
    ytd_debit: Decimal
    ytd_credit: Decimal


# =============================================================================
# FISCAL PERIOD SCHEMAS
# =============================================================================

class FiscalYearBase(BaseModel):
    """Base schema for Fiscal Year."""
    year_name: str = Field(..., min_length=1, max_length=50)
    start_date: date
    end_date: date


class FiscalYearCreate(FiscalYearBase):
    """Schema for creating fiscal year."""
    auto_create_periods: bool = True


class FiscalYearResponse(FiscalYearBase):
    """Schema for fiscal year response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    entity_id: UUID
    is_current: bool
    is_closed: bool
    closed_at: Optional[datetime] = None
    closed_by_id: Optional[UUID] = None


class FiscalPeriodBase(BaseModel):
    """Base schema for Fiscal Period."""
    period_name: str = Field(..., min_length=1, max_length=50)
    period_number: int = Field(..., ge=1, le=13)
    start_date: date
    end_date: date


class FiscalPeriodCreate(FiscalPeriodBase):
    """Schema for creating fiscal period."""
    fiscal_year_id: UUID


class FiscalPeriodUpdate(BaseModel):
    """Schema for updating fiscal period."""
    status: Optional[FiscalPeriodStatus] = None
    closing_notes: Optional[str] = None


class FiscalPeriodResponse(FiscalPeriodBase):
    """Schema for fiscal period response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    entity_id: UUID
    fiscal_year_id: UUID
    status: FiscalPeriodStatus
    bank_reconciled: bool
    closed_at: Optional[datetime] = None
    closed_by_id: Optional[UUID] = None


# =============================================================================
# JOURNAL ENTRY SCHEMAS
# =============================================================================

class JournalEntryLineBase(BaseModel):
    """Base schema for journal entry line."""
    account_id: UUID
    description: Optional[str] = None
    debit_amount: Decimal = Decimal("0.00")
    credit_amount: Decimal = Decimal("0.00")
    department_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    tax_code: Optional[str] = None
    tax_amount: Decimal = Decimal("0.00")
    customer_id: Optional[UUID] = None
    vendor_id: Optional[UUID] = None
    bank_transaction_id: Optional[UUID] = None
    
    @validator('debit_amount', 'credit_amount')
    def validate_amounts(cls, v):
        if v < 0:
            raise ValueError('Amount cannot be negative')
        return v


class JournalEntryLineCreate(JournalEntryLineBase):
    """Schema for creating journal entry line."""
    pass


class JournalEntryLineResponse(JournalEntryLineBase):
    """Schema for journal entry line response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    journal_entry_id: UUID
    line_number: int
    account_code: Optional[str] = None
    account_name: Optional[str] = None


class JournalEntryBase(BaseModel):
    """Base schema for journal entry."""
    entry_date: date
    description: str = Field(..., min_length=1, max_length=500)
    memo: Optional[str] = None
    entry_type: JournalEntryType = JournalEntryType.MANUAL
    source_module: Optional[str] = None
    source_document_type: Optional[str] = None
    source_document_id: Optional[UUID] = None
    source_reference: Optional[str] = None
    currency: str = "NGN"
    exchange_rate: Decimal = Decimal("1.000000")
    requires_approval: bool = False
    reconciliation_id: Optional[UUID] = None


class JournalEntryCreate(JournalEntryBase):
    """Schema for creating a journal entry."""
    lines: List[JournalEntryLineCreate] = Field(..., min_length=2)
    auto_post: bool = False
    
    @validator('lines')
    def validate_balanced(cls, v):
        total_debit = sum(line.debit_amount for line in v)
        total_credit = sum(line.credit_amount for line in v)
        if total_debit != total_credit:
            raise ValueError(f'Entry must be balanced. Debit: {total_debit}, Credit: {total_credit}')
        if total_debit == 0:
            raise ValueError('Entry must have a non-zero amount')
        return v


class JournalEntryUpdate(BaseModel):
    """Schema for updating a journal entry (draft only)."""
    entry_date: Optional[date] = None
    description: Optional[str] = Field(None, min_length=1, max_length=500)
    memo: Optional[str] = None
    lines: Optional[List[JournalEntryLineCreate]] = None
    
    @validator('lines')
    def validate_balanced(cls, v):
        if v is None:
            return v
        total_debit = sum(line.debit_amount for line in v)
        total_credit = sum(line.credit_amount for line in v)
        if total_debit != total_credit:
            raise ValueError(f'Entry must be balanced. Debit: {total_debit}, Credit: {total_credit}')
        return v


class JournalEntryResponse(JournalEntryBase):
    """Schema for journal entry response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    entity_id: UUID
    fiscal_period_id: Optional[UUID] = None
    entry_number: str
    total_debit: Decimal
    total_credit: Decimal
    status: JournalEntryStatus
    posted_at: Optional[datetime] = None
    posted_by_id: Optional[UUID] = None
    is_reversed: bool
    reversed_at: Optional[datetime] = None
    reversal_entry_id: Optional[UUID] = None
    original_entry_id: Optional[UUID] = None
    approved_at: Optional[datetime] = None
    approved_by_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    lines: List[JournalEntryLineResponse] = []


class JournalEntryListResponse(BaseModel):
    """Schema for paginated journal entries list."""
    items: List[JournalEntryResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class JournalEntryPost(BaseModel):
    """Schema for posting a journal entry."""
    post_date: Optional[date] = None


class JournalEntryReverse(BaseModel):
    """Schema for reversing a journal entry."""
    reversal_date: date
    reason: str = Field(..., min_length=1, max_length=500)


# =============================================================================
# REPORTING SCHEMAS
# =============================================================================

class TrialBalanceItem(BaseModel):
    """Item in trial balance report."""
    account_id: UUID
    account_code: str
    account_name: str
    account_type: AccountType
    debit_balance: Decimal
    credit_balance: Decimal


class TrialBalanceReport(BaseModel):
    """Trial balance report."""
    entity_id: UUID
    as_of_date: date
    total_debits: Decimal
    total_credits: Decimal
    is_balanced: bool
    items: List[TrialBalanceItem]


class IncomeStatementItem(BaseModel):
    """Item in income statement."""
    account_id: UUID
    account_code: str
    account_name: str
    account_sub_type: Optional[AccountSubType]
    amount: Decimal


class IncomeStatementReport(BaseModel):
    """Income statement (P&L) report."""
    entity_id: UUID
    start_date: date
    end_date: date
    revenue_items: List[IncomeStatementItem]
    expense_items: List[IncomeStatementItem]
    total_revenue: Decimal
    total_expenses: Decimal
    net_income: Decimal


class BalanceSheetItem(BaseModel):
    """Item in balance sheet."""
    account_id: UUID
    account_code: str
    account_name: str
    account_sub_type: Optional[AccountSubType]
    balance: Decimal


class BalanceSheetReport(BaseModel):
    """Balance sheet report."""
    entity_id: UUID
    as_of_date: date
    assets: List[BalanceSheetItem]
    liabilities: List[BalanceSheetItem]
    equity: List[BalanceSheetItem]
    total_assets: Decimal
    total_liabilities: Decimal
    total_equity: Decimal
    is_balanced: bool


# =============================================================================
# CASH FLOW STATEMENT SCHEMAS
# =============================================================================

class CashFlowCategory(str, Enum):
    """Cash flow statement categories."""
    OPERATING = "operating"
    INVESTING = "investing"
    FINANCING = "financing"


class CashFlowItem(BaseModel):
    """Single item in cash flow statement."""
    description: str
    amount: Decimal
    category: CashFlowCategory


class CashFlowSection(BaseModel):
    """Section of cash flow statement."""
    items: List[CashFlowItem]
    total: Decimal


class CashFlowStatementReport(BaseModel):
    """Cash flow statement report (indirect method)."""
    entity_id: UUID
    start_date: date
    end_date: date
    
    # Operating Activities
    net_income: Decimal
    depreciation: Decimal
    changes_in_working_capital: List[CashFlowItem]
    operating_activities_total: Decimal
    
    # Investing Activities
    investing_items: List[CashFlowItem]
    investing_activities_total: Decimal
    
    # Financing Activities  
    financing_items: List[CashFlowItem]
    financing_activities_total: Decimal
    
    # Summary
    net_change_in_cash: Decimal
    beginning_cash: Decimal
    ending_cash: Decimal


class AccountLedgerEntry(BaseModel):
    """Single entry in account ledger."""
    date: date
    entry_number: str
    description: str
    reference: Optional[str]
    debit: Decimal
    credit: Decimal
    balance: Decimal


class AccountLedgerReport(BaseModel):
    """Account ledger (T-account) report."""
    account_id: UUID
    account_code: str
    account_name: str
    account_type: AccountType
    start_date: date
    end_date: date
    opening_balance: Decimal
    entries: List[AccountLedgerEntry]
    total_debits: Decimal
    total_credits: Decimal
    closing_balance: Decimal


# =============================================================================
# GL INTEGRATION SCHEMAS
# =============================================================================

class GLPostingRequest(BaseModel):
    """Request to post a document to GL."""
    source_module: str
    source_document_type: str
    source_document_id: UUID
    source_reference: Optional[str] = None
    entry_date: date
    description: str
    lines: List[JournalEntryLineCreate]
    auto_post: bool = True


class GLPostingResponse(BaseModel):
    """Response from GL posting."""
    success: bool
    journal_entry_id: Optional[UUID] = None
    entry_number: Optional[str] = None
    message: str


# =============================================================================
# PERIOD CLOSE SCHEMAS
# =============================================================================

class PeriodCloseChecklist(BaseModel):
    """Checklist for closing a period."""
    period_id: UUID
    period_name: str
    
    # Checks
    all_entries_posted: bool
    bank_reconciliations_complete: bool
    outstanding_items_reviewed: bool
    adjusting_entries_made: bool
    trial_balance_balanced: bool
    
    # Details
    unposted_entries_count: int
    unreconciled_bank_accounts: List[str]
    outstanding_items_count: int
    
    can_close: bool
    blocking_issues: List[str]


class PeriodCloseRequest(BaseModel):
    """Request to close a fiscal period."""
    period_id: UUID
    closing_notes: Optional[str] = None
    force_close: bool = False


class PeriodCloseResponse(BaseModel):
    """Response from period close."""
    success: bool
    period_id: UUID
    status: FiscalPeriodStatus
    message: str
    closed_at: Optional[datetime] = None


# =============================================================================
# FIXED ASSET INTEGRATION SCHEMAS
# =============================================================================

class FixedAssetSummaryItem(BaseModel):
    """Summary of a fixed asset for financial reporting."""
    asset_id: UUID
    asset_code: str
    name: str
    category: str
    acquisition_date: date
    acquisition_cost: Decimal
    accumulated_depreciation: Decimal
    net_book_value: Decimal
    depreciation_method: str
    depreciation_rate: Decimal
    status: str


class FixedAssetCategorySummary(BaseModel):
    """Summary by category for Balance Sheet notes."""
    category: str
    asset_count: int
    total_cost: Decimal
    total_depreciation: Decimal
    total_nbv: Decimal


class FixedAssetRegisterSummary(BaseModel):
    """Complete fixed asset register summary for accounting integration."""
    entity_id: UUID
    as_of_date: date
    total_assets: int
    active_assets: int
    disposed_assets: int
    total_acquisition_cost: Decimal
    total_accumulated_depreciation: Decimal
    total_net_book_value: Decimal
    by_category: List[FixedAssetCategorySummary]
    assets: List[FixedAssetSummaryItem]


class GLFixedAssetValidation(BaseModel):
    """Validation result comparing GL balances to Fixed Asset Register."""
    entity_id: UUID
    validation_date: date
    is_valid: bool
    
    # GL Balances (from Chart of Accounts)
    gl_fixed_asset_cost: Decimal
    gl_accumulated_depreciation: Decimal
    gl_net_book_value: Decimal
    
    # Register Balances (from Fixed Asset tables)
    register_total_cost: Decimal
    register_accumulated_depreciation: Decimal
    register_net_book_value: Decimal
    
    # Variances
    cost_variance: Decimal
    depreciation_variance: Decimal
    nbv_variance: Decimal
    
    # Issues
    issues: List[str]
    recommendations: List[str]


class EnhancedBalanceSheetReport(BalanceSheetReport):
    """Enhanced balance sheet with fixed asset details and validation."""
    # Fixed Asset Details
    fixed_asset_summary: Optional[FixedAssetRegisterSummary] = None
    fixed_asset_validation: Optional[GLFixedAssetValidation] = None
    
    # Additional Notes
    fixed_asset_notes: Optional[str] = None
    depreciation_policy: Optional[str] = None


# =============================================================================
# SOURCE SYSTEM INTEGRATION SCHEMAS
# =============================================================================

class InventorySummaryForGL(BaseModel):
    """Inventory summary for GL reconciliation. Maps to GL 1140."""
    entity_id: UUID
    as_of_date: date
    total_items: int
    active_items: int
    total_inventory_value: Decimal  # Should match GL 1140
    total_quantity_on_hand: int
    low_stock_items: int
    categories: List[dict]  # Breakdown by category
    valuation_method: str = "weighted_average"


class ARAgingSummary(BaseModel):
    """Accounts Receivable aging for GL reconciliation. Maps to GL 1130."""
    entity_id: UUID
    as_of_date: date
    total_receivables: Decimal  # Should match GL 1130
    current: Decimal  # 0-30 days
    days_31_60: Decimal
    days_61_90: Decimal
    over_90_days: Decimal
    total_customers: int
    customers_with_balance: int
    top_receivables: List[dict]  # Top 10 customers by balance


class APAgingSummary(BaseModel):
    """Accounts Payable aging for GL reconciliation. Maps to GL 2110."""
    entity_id: UUID
    as_of_date: date
    total_payables: Decimal  # Should match GL 2110
    current: Decimal  # 0-30 days
    days_31_60: Decimal
    days_61_90: Decimal
    over_90_days: Decimal
    total_vendors: int
    vendors_with_balance: int
    top_payables: List[dict]  # Top 10 vendors by balance


class PayrollSummaryForGL(BaseModel):
    """Payroll summary for GL reconciliation. Maps to GL 2150-2190, 5200-5230."""
    entity_id: UUID
    period_start: date
    period_end: date
    
    # Expense accounts (5200-5230)
    total_gross_salary: Decimal  # GL 5200
    total_employer_pension: Decimal  # GL 5210
    total_employer_nsitf: Decimal  # GL 5220
    total_itf: Decimal  # GL 5230
    
    # Liability accounts (2150-2190)
    total_paye_payable: Decimal  # GL 2150
    total_pension_payable: Decimal  # GL 2160
    total_nhf_payable: Decimal  # GL 2170
    total_nsitf_payable: Decimal  # GL 2180
    total_salaries_payable: Decimal  # GL 2190
    
    # Stats
    total_employees: int
    payroll_runs: int


class BankAccountSummaryForGL(BaseModel):
    """Bank account summary for GL reconciliation. Maps to GL 1120."""
    entity_id: UUID
    as_of_date: date
    total_bank_balance: Decimal  # Should match GL 1120
    accounts: List[dict]  # Individual bank account balances
    last_reconciled_date: Optional[date]
    unreconciled_items_count: int
    outstanding_deposits: Decimal
    outstanding_checks: Decimal


class ExpenseClaimSummaryForGL(BaseModel):
    """Expense claims summary for GL reconciliation."""
    entity_id: UUID
    as_of_date: date
    total_pending_claims: Decimal
    total_approved_claims: Decimal
    total_paid_claims: Decimal
    claims_by_category: List[dict]
    claims_count: int


class GLSourceSystemSummary(BaseModel):
    """Comprehensive GL summary with all source system data."""
    entity_id: UUID
    as_of_date: date
    generated_at: datetime
    
    # Source system summaries
    inventory: Optional[InventorySummaryForGL] = None
    accounts_receivable: Optional[ARAgingSummary] = None
    accounts_payable: Optional[APAgingSummary] = None
    payroll: Optional[PayrollSummaryForGL] = None
    bank_accounts: Optional[BankAccountSummaryForGL] = None
    fixed_assets: Optional[FixedAssetRegisterSummary] = None
    expense_claims: Optional[ExpenseClaimSummaryForGL] = None
    
    # GL Validation
    validations: List[dict] = []  # List of validation results
    has_discrepancies: bool = False
    discrepancy_count: int = 0


class GLAccountReconciliation(BaseModel):
    """Reconciliation of a single GL account with source system."""
    account_code: str
    account_name: str
    gl_balance: Decimal
    source_system: str
    source_balance: Decimal
    variance: Decimal
    variance_percent: Optional[Decimal]
    is_reconciled: bool
    notes: Optional[str] = None
    last_reconciled: Optional[date] = None


# =============================================================================
# FX (FOREIGN EXCHANGE) SCHEMAS
# =============================================================================

class FXRevaluationType(str, Enum):
    """Type of FX revaluation."""
    REALIZED = "realized"
    UNREALIZED = "unrealized"
    SETTLEMENT = "settlement"


class FXAccountType(str, Enum):
    """Types of accounts with FX exposure."""
    BANK = "bank"
    RECEIVABLE = "receivable"
    PAYABLE = "payable"
    LOAN = "loan"
    INTERCOMPANY = "intercompany"


class ExchangeRateCreate(BaseModel):
    """Schema for creating exchange rate."""
    from_currency: str = Field(..., min_length=3, max_length=3)
    to_currency: str = Field(..., min_length=3, max_length=3)
    rate: Decimal = Field(..., gt=0)
    rate_date: date
    source: str = "manual"
    is_billing_rate: bool = False


class ExchangeRateResponse(BaseModel):
    """Schema for exchange rate response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    from_currency: str
    to_currency: str
    rate: Decimal
    rate_date: date
    source: Optional[str]
    is_billing_rate: bool
    created_at: datetime


class CurrencyConversionRequest(BaseModel):
    """Schema for currency conversion."""
    amount: Decimal
    from_currency: str = Field(..., min_length=3, max_length=3)
    to_currency: str = Field(..., min_length=3, max_length=3)
    rate_date: Optional[date] = None
    exchange_rate: Optional[Decimal] = None


class CurrencyConversionResponse(BaseModel):
    """Schema for currency conversion response."""
    original_amount: Decimal
    from_currency: str
    to_currency: str
    converted_amount: Decimal
    exchange_rate: Decimal
    rate_date: date


class FXExposureAccount(BaseModel):
    """Individual account FX exposure."""
    account_code: str
    account_name: str
    account_type: str
    balance: Decimal


class FXExposureByCurrency(BaseModel):
    """FX exposure for a single currency."""
    currency: str
    bank_balance: Decimal
    receivable_balance: Decimal
    payable_balance: Decimal
    loan_balance: Decimal
    net_fc_exposure: Decimal
    current_rate: Optional[Decimal]
    ngn_equivalent: Decimal
    accounts: List[FXExposureAccount]


class FXExposureReport(BaseModel):
    """Complete FX exposure report."""
    entity_id: UUID
    as_of_date: date
    functional_currency: str = "NGN"
    exposures: List[FXExposureByCurrency]
    total_net_exposure_ngn: Decimal


class RealizedFXGainLossRequest(BaseModel):
    """Request to calculate realized FX gain/loss."""
    account_id: UUID
    fc_amount: Decimal
    original_rate: Decimal
    settlement_rate: Decimal
    settlement_date: date
    source_document_type: Optional[str] = None
    source_document_id: Optional[UUID] = None
    auto_post: bool = True
    notes: Optional[str] = None


class PeriodEndRevaluationRequest(BaseModel):
    """Request for period-end FX revaluation."""
    period_id: UUID
    revaluation_date: date
    auto_post: bool = True


class FXRevaluationResponse(BaseModel):
    """Response for FX revaluation."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    revaluation_date: date
    revaluation_type: str
    foreign_currency: str
    original_fc_amount: Decimal
    original_exchange_rate: Decimal
    original_ngn_amount: Decimal
    revaluation_rate: Decimal
    revalued_ngn_amount: Decimal
    fx_gain_loss: Decimal
    is_gain: bool
    journal_entry_id: Optional[UUID]
    created_at: datetime


class FXRevaluationSummary(BaseModel):
    """Summary of period-end revaluation."""
    entity_id: UUID
    period_id: UUID
    revaluation_date: date
    accounts_revalued: int
    total_unrealized_gain: Decimal
    total_unrealized_loss: Decimal
    net_fx_impact: Decimal
    journal_entries_created: List[UUID]
    errors: List[str]


class FXGainLossByType(BaseModel):
    """FX gain/loss breakdown."""
    total_gain: Decimal
    total_loss: Decimal
    net: Decimal
    by_currency: dict


class FXGainLossReport(BaseModel):
    """FX gain/loss report for a period."""
    period_start: date
    period_end: date
    realized: FXGainLossByType
    unrealized: FXGainLossByType
    total_fx_impact: Decimal
    details: List[dict]
