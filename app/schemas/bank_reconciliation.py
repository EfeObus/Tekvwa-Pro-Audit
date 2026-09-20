"""
Tekvwa Pro Audit - Bank Reconciliation Schemas

Pydantic schemas for bank reconciliation API requests and responses.
Includes Nigerian-specific features for EMTL, Stamp Duty, and bank charge detection.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


# ===========================================
# ENUMS
# ===========================================

class BankAccountCurrency(str, Enum):
    """Supported currencies for Nigerian bank accounts."""
    NGN = "NGN"
    USD = "USD"
    GBP = "GBP"
    EUR = "EUR"


class BankStatementSource(str, Enum):
    """Source of bank statement data."""
    MONO_API = "mono_api"
    OKRA_API = "okra_api"
    STITCH_API = "stitch_api"
    CSV_UPLOAD = "csv_upload"
    EXCEL_UPLOAD = "excel_upload"
    MT940_UPLOAD = "mt940_upload"
    PDF_OCR = "pdf_ocr"
    EMAIL_PARSE = "email_parse"
    MANUAL_ENTRY = "manual_entry"


class ReconciliationStatus(str, Enum):
    """Status of a bank reconciliation."""
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"


class MatchType(str, Enum):
    """Type of transaction match."""
    EXACT = "exact"
    FUZZY_AMOUNT = "fuzzy_amount"
    FUZZY_DATE = "fuzzy_date"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    RULE_BASED = "rule_based"
    MANUAL = "manual"


class MatchConfidenceLevel(str, Enum):
    """Confidence level of a match."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MANUAL = "manual"


class AdjustmentType(str, Enum):
    """Type of reconciliation adjustment."""
    BANK_CHARGE = "bank_charge"
    EMTL = "emtl"
    STAMP_DUTY = "stamp_duty"
    SMS_FEE = "sms_fee"
    MAINTENANCE_FEE = "maintenance_fee"
    VAT_ON_CHARGES = "vat_on_charges"
    WHT_DEDUCTION = "wht_deduction"
    POS_SETTLEMENT = "pos_settlement"
    NIP_CHARGE = "nip_charge"
    USSD_CHARGE = "ussd_charge"
    INTEREST_EARNED = "interest_earned"
    INTEREST_PAID = "interest_paid"
    FOREIGN_EXCHANGE = "foreign_exchange"
    REVERSAL = "reversal"
    TIMING_DIFFERENCE = "timing_difference"
    ERROR_CORRECTION = "error_correction"
    OTHER = "other"


class UnmatchedItemType(str, Enum):
    """Type of unmatched item."""
    OUTSTANDING_CHEQUE = "outstanding_cheque"
    DEPOSIT_IN_TRANSIT = "deposit_in_transit"
    BANK_ERROR = "bank_error"
    BOOK_ERROR = "book_error"
    TIMING_DIFFERENCE = "timing_difference"
    UNIDENTIFIED_DEPOSIT = "unidentified_deposit"
    UNIDENTIFIED_WITHDRAWAL = "unidentified_withdrawal"
    REVERSAL_PENDING = "reversal_pending"
    OTHER = "other"


class ChargeDetectionMethod(str, Enum):
    """Method used to detect bank charges."""
    NARRATION_PATTERN = "narration_pattern"
    EXACT_AMOUNT = "exact_amount"
    AMOUNT_RANGE = "amount_range"
    KEYWORD_MATCH = "keyword_match"
    COMBINED = "combined"


# ===========================================
# BASE SCHEMAS
# ===========================================

class BankAccountBase(BaseModel):
    """Base schema for bank account data."""
    bank_name: str = Field(..., min_length=2, max_length=100)
    account_number: str = Field(..., min_length=10, max_length=20)
    account_name: str = Field(..., min_length=2, max_length=200)
    account_type: str = Field(default="current", max_length=50)
    currency: BankAccountCurrency = Field(default=BankAccountCurrency.NGN)
    bank_code: Optional[str] = Field(None, max_length=10)
    sort_code: Optional[str] = Field(None, max_length=20)
    swift_code: Optional[str] = Field(None, max_length=11)
    iban: Optional[str] = Field(None, max_length=34)
    branch_name: Optional[str] = Field(None, max_length=200)
    branch_address: Optional[str] = None
    gl_account_code: Optional[str] = Field(None, max_length=20)
    gl_account_name: Optional[str] = Field(None, max_length=100)
    is_primary: bool = Field(default=False)
    opening_balance: Decimal = Field(default=Decimal("0.00"))


class BankAccountCreate(BankAccountBase):
    """Schema for creating a bank account."""
    pass


class BankAccountUpdate(BaseModel):
    """Schema for updating a bank account."""
    bank_name: Optional[str] = Field(None, min_length=2, max_length=100)
    account_name: Optional[str] = Field(None, min_length=2, max_length=200)
    account_type: Optional[str] = Field(None, max_length=50)
    bank_code: Optional[str] = Field(None, max_length=10)
    sort_code: Optional[str] = Field(None, max_length=20)
    swift_code: Optional[str] = Field(None, max_length=11)
    branch_name: Optional[str] = Field(None, max_length=200)
    branch_address: Optional[str] = None
    gl_account_code: Optional[str] = Field(None, max_length=20)
    gl_account_name: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None
    is_primary: Optional[bool] = None
    auto_sync_enabled: Optional[bool] = None
    sync_frequency_hours: Optional[int] = None


class BankAccountResponse(BankAccountBase):
    """Schema for bank account response."""
    id: UUID
    entity_id: UUID
    is_active: bool
    current_balance: Decimal
    last_reconciled_date: Optional[date] = None
    last_reconciled_balance: Optional[Decimal] = None
    
    # API Connection Status
    mono_connected: bool = False
    mono_last_sync: Optional[datetime] = None
    okra_connected: bool = False
    okra_last_sync: Optional[datetime] = None
    stitch_connected: bool = False
    stitch_last_sync: Optional[datetime] = None
    
    # Sync Settings
    auto_sync_enabled: bool = False
    sync_frequency_hours: int = 24
    last_sync_status: Optional[str] = None
    last_sync_error: Optional[str] = None
    
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ===========================================
# BANK STATEMENT TRANSACTION SCHEMAS
# ===========================================

class BankStatementTransactionBase(BaseModel):
    """Base schema for bank statement transaction."""
    transaction_date: date
    value_date: Optional[date] = None
    narration: str = Field(..., max_length=500)
    reference: Optional[str] = Field(None, max_length=100)
    debit_amount: Optional[Decimal] = None
    credit_amount: Optional[Decimal] = None
    balance: Optional[Decimal] = None
    transaction_type: Optional[str] = Field(None, max_length=50)
    channel: Optional[str] = Field(None, max_length=50)
    category: Optional[str] = Field(None, max_length=100)


class BankStatementTransactionCreate(BankStatementTransactionBase):
    """Schema for creating a bank statement transaction."""
    bank_account_id: UUID
    statement_id: Optional[UUID] = None


class BankStatementTransactionResponse(BankStatementTransactionBase):
    """Schema for bank statement transaction response."""
    id: UUID
    bank_account_id: UUID
    statement_id: Optional[UUID] = None
    
    # Clean narration
    raw_narration: Optional[str] = None
    clean_narration: Optional[str] = None
    bank_reference: Optional[str] = None
    
    # Reversal tracking
    is_reversal: bool = False
    reversed_transaction_id: Optional[UUID] = None
    
    # Nigerian charge detection
    is_emtl: bool = False
    is_stamp_duty: bool = False
    is_bank_charge: bool = False
    is_vat_charge: bool = False
    is_wht_deduction: bool = False
    is_pos_settlement: bool = False
    is_nip_transfer: bool = False
    is_ussd_transaction: bool = False
    detected_charge_type: Optional[str] = None
    
    # Matching
    is_matched: bool = False
    matched_transaction_id: Optional[UUID] = None
    match_type: Optional[MatchType] = None
    match_group_id: Optional[UUID] = None
    match_confidence: Optional[Decimal] = None
    match_confidence_level: Optional[MatchConfidenceLevel] = None
    matched_at: Optional[datetime] = None
    
    # Metadata
    source: Optional[BankStatementSource] = None
    external_id: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ===========================================
# BANK STATEMENT IMPORT SCHEMAS
# ===========================================

class BankStatementImportCreate(BaseModel):
    """Schema for initiating bank statement import."""
    bank_account_id: UUID
    source: BankStatementSource
    statement_start_date: Optional[date] = None
    statement_end_date: Optional[date] = None


class CSVImportConfig(BaseModel):
    """Configuration for CSV import column mapping."""
    date_column: str
    narration_column: str
    debit_column: Optional[str] = None
    credit_column: Optional[str] = None
    amount_column: Optional[str] = None
    balance_column: Optional[str] = None
    reference_column: Optional[str] = None
    date_format: str = Field(default="%d/%m/%Y")
    skip_rows: int = Field(default=0)
    has_header: bool = Field(default=True)


class BankStatementImportResponse(BaseModel):
    """Schema for bank statement import response."""
    id: UUID
    entity_id: UUID
    bank_account_id: UUID
    source: BankStatementSource
    filename: Optional[str] = None
    
    # Period
    statement_start_date: Optional[date] = None
    statement_end_date: Optional[date] = None
    
    # Statistics
    total_rows: int = 0
    imported_count: int = 0
    duplicate_count: int = 0
    error_count: int = 0
    
    # Auto-detected charges
    emtl_count: int = 0
    stamp_duty_count: int = 0
    bank_charge_count: int = 0
    reversal_count: int = 0
    
    # Status
    status: str
    error_message: Optional[str] = None
    processing_time_ms: Optional[int] = None
    
    imported_at: datetime
    
    class Config:
        from_attributes = True


# ===========================================
# BANK RECONCILIATION SCHEMAS
# ===========================================

class BankReconciliationCreate(BaseModel):
    """Schema for creating a bank reconciliation."""
    bank_account_id: UUID
    reconciliation_date: date
    period_start: date
    period_end: date
    statement_ending_balance: Decimal
    ledger_ending_balance: Decimal
    reference: Optional[str] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def validate_dates(self) -> "BankReconciliationCreate":
        if self.period_start > self.period_end:
            raise ValueError("Period start date must be before or equal to period end date")
        if self.reconciliation_date < self.period_end:
            raise ValueError("Reconciliation date must be on or after period end date")
        return self


class BankReconciliationUpdate(BaseModel):
    """Schema for updating a bank reconciliation."""
    statement_ending_balance: Optional[Decimal] = None
    ledger_ending_balance: Optional[Decimal] = None
    deposits_in_transit: Optional[Decimal] = None
    outstanding_checks: Optional[Decimal] = None
    bank_charges: Optional[Decimal] = None
    interest_earned: Optional[Decimal] = None
    other_adjustments: Optional[Decimal] = None
    notes: Optional[str] = None


class BankReconciliationResponse(BaseModel):
    """Schema for bank reconciliation response."""
    id: UUID
    entity_id: UUID
    bank_account_id: UUID
    
    # Period
    reconciliation_date: date
    period_start: date
    period_end: date
    
    # Balances
    statement_ending_balance: Decimal
    ledger_ending_balance: Decimal
    adjusted_bank_balance: Optional[Decimal] = None
    adjusted_book_balance: Optional[Decimal] = None
    
    # Reconciling Items
    deposits_in_transit: Decimal = Decimal("0.00")
    outstanding_checks: Decimal = Decimal("0.00")
    bank_charges: Decimal = Decimal("0.00")
    interest_earned: Decimal = Decimal("0.00")
    other_adjustments: Decimal = Decimal("0.00")
    difference: Decimal = Decimal("0.00")
    
    # Nigerian-specific totals
    total_emtl: Decimal = Decimal("0.00")
    total_stamp_duty: Decimal = Decimal("0.00")
    total_vat_on_charges: Decimal = Decimal("0.00")
    total_wht_deducted: Decimal = Decimal("0.00")
    
    # Statistics
    total_transactions: int = 0
    matched_transactions: int = 0
    unmatched_bank_transactions: int = 0
    unmatched_book_transactions: int = 0
    auto_matched_count: int = 0
    manual_matched_count: int = 0
    
    # Status
    status: ReconciliationStatus
    is_balanced: bool = False
    
    # Workflow
    prepared_by_id: Optional[UUID] = None
    prepared_at: Optional[datetime] = None
    reviewed_by_id: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    approved_by_id: Optional[UUID] = None
    approved_at: Optional[datetime] = None
    
    reference: Optional[str] = None
    notes: Optional[str] = None
    rejection_reason: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BankReconciliationDetailResponse(BankReconciliationResponse):
    """Detailed response including related items."""
    adjustments: List["ReconciliationAdjustmentResponse"] = []
    unmatched_items: List["UnmatchedItemResponse"] = []
    matched_transactions: List["MatchedTransactionResponse"] = []


# ===========================================
# RECONCILIATION ADJUSTMENT SCHEMAS
# ===========================================

class ReconciliationAdjustmentCreate(BaseModel):
    """Schema for creating a reconciliation adjustment."""
    bank_transaction_id: Optional[UUID] = None
    adjustment_type: AdjustmentType
    description: str = Field(..., max_length=500)
    debit_account_code: str = Field(..., max_length=20)
    debit_account_name: Optional[str] = Field(None, max_length=100)
    credit_account_code: str = Field(..., max_length=20)
    credit_account_name: Optional[str] = Field(None, max_length=100)
    amount: Decimal = Field(..., gt=0)
    vat_amount: Optional[Decimal] = None
    wht_amount: Optional[Decimal] = None
    notes: Optional[str] = None


class ReconciliationAdjustmentResponse(BaseModel):
    """Schema for reconciliation adjustment response."""
    id: UUID
    reconciliation_id: UUID
    bank_transaction_id: Optional[UUID] = None
    
    adjustment_type: AdjustmentType
    description: str
    debit_account_code: str
    debit_account_name: Optional[str] = None
    credit_account_code: str
    credit_account_name: Optional[str] = None
    amount: Decimal
    
    # Nigerian Tax
    vat_amount: Optional[Decimal] = None
    wht_amount: Optional[Decimal] = None
    
    # Journal Reference
    journal_entry_id: Optional[UUID] = None
    journal_posted: bool = False
    journal_posted_at: Optional[datetime] = None
    
    # Auto-detection
    auto_detected: bool = False
    detection_rule_id: Optional[UUID] = None
    
    # Approval
    approved: bool = False
    approved_by_id: Optional[UUID] = None
    approved_at: Optional[datetime] = None
    
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ===========================================
# UNMATCHED ITEM SCHEMAS
# ===========================================

class UnmatchedItemCreate(BaseModel):
    """Schema for creating an unmatched item."""
    item_type: UnmatchedItemType
    source: str = Field(..., pattern="^(bank|ledger)$")
    bank_transaction_id: Optional[UUID] = None
    ledger_transaction_id: Optional[UUID] = None
    transaction_date: date
    amount: Decimal
    description: Optional[str] = None
    reference: Optional[str] = Field(None, max_length=100)


class UnmatchedItemUpdate(BaseModel):
    """Schema for updating an unmatched item."""
    resolution: Optional[str] = Field(None, pattern="^(carry_forward|journal_created|matched|cancelled|excluded)$")
    resolution_notes: Optional[str] = None


class UnmatchedItemResponse(BaseModel):
    """Schema for unmatched item response."""
    id: UUID
    reconciliation_id: UUID
    
    item_type: UnmatchedItemType
    source: str
    
    bank_transaction_id: Optional[UUID] = None
    ledger_transaction_id: Optional[UUID] = None
    
    transaction_date: date
    amount: Decimal
    description: Optional[str] = None
    reference: Optional[str] = None
    
    resolution: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by_id: Optional[UUID] = None
    resolution_notes: Optional[str] = None
    
    carried_to_reconciliation_id: Optional[UUID] = None
    carried_from_reconciliation_id: Optional[UUID] = None
    journal_entry_id: Optional[UUID] = None
    
    created_at: datetime

    class Config:
        from_attributes = True


# ===========================================
# MATCHING SCHEMAS
# ===========================================

class MatchedTransactionResponse(BaseModel):
    """Schema for a matched transaction pair."""
    bank_transaction_id: UUID
    ledger_transaction_id: UUID
    match_type: MatchType
    match_confidence: Decimal
    match_confidence_level: MatchConfidenceLevel
    matched_at: datetime
    matched_by_id: Optional[UUID] = None
    matching_rule_id: Optional[UUID] = None
    
    # Bank side details
    bank_date: date
    bank_amount: Decimal
    bank_narration: str
    
    # Ledger side details
    ledger_date: date
    ledger_amount: Decimal
    ledger_description: str


class ManualMatchRequest(BaseModel):
    """Schema for manually matching transactions."""
    bank_transaction_ids: List[UUID] = Field(..., min_length=1)
    ledger_transaction_ids: List[UUID] = Field(..., min_length=1)
    match_type: MatchType = Field(default=MatchType.MANUAL)
    notes: Optional[str] = None


class UnmatchRequest(BaseModel):
    """Schema for unmatching transactions."""
    bank_transaction_ids: List[UUID]
    reason: Optional[str] = None


class AutoMatchConfig(BaseModel):
    """Configuration for auto-matching."""
    date_tolerance_days: int = Field(default=3, ge=0, le=30)
    amount_tolerance_percent: Decimal = Field(default=Decimal("0.00"), ge=0, le=5)
    enable_fuzzy_matching: bool = Field(default=True)
    enable_one_to_many: bool = Field(default=True)
    enable_many_to_one: bool = Field(default=True)
    enable_rule_based: bool = Field(default=True)
    min_confidence_threshold: Decimal = Field(default=Decimal("70.00"))


class AutoMatchResult(BaseModel):
    """Result of auto-matching operation."""
    total_bank_transactions: int
    total_ledger_transactions: int
    exact_matches: int
    fuzzy_matches: int
    one_to_many_matches: int
    many_to_one_matches: int
    rule_based_matches: int
    unmatched_bank: int
    unmatched_ledger: int
    matches: List[MatchedTransactionResponse]


# ===========================================
# BANK CHARGE RULE SCHEMAS
# ===========================================

class BankChargeRuleCreate(BaseModel):
    """Schema for creating a bank charge rule."""
    bank_account_id: Optional[UUID] = None
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    charge_type: AdjustmentType
    detection_method: ChargeDetectionMethod
    narration_pattern: Optional[str] = Field(None, max_length=500)
    narration_keywords: Optional[List[str]] = None
    exact_amount: Optional[Decimal] = None
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None
    debit_account_code: Optional[str] = Field(None, max_length=20)
    credit_account_code: Optional[str] = Field(None, max_length=20)
    includes_vat: bool = False
    vat_rate: Decimal = Field(default=Decimal("7.5"))
    priority: int = Field(default=100)


class BankChargeRuleUpdate(BaseModel):
    """Schema for updating a bank charge rule."""
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    narration_pattern: Optional[str] = Field(None, max_length=500)
    narration_keywords: Optional[List[str]] = None
    exact_amount: Optional[Decimal] = None
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None
    debit_account_code: Optional[str] = Field(None, max_length=20)
    credit_account_code: Optional[str] = Field(None, max_length=20)
    includes_vat: Optional[bool] = None
    vat_rate: Optional[Decimal] = None
    is_active: Optional[bool] = None
    priority: Optional[int] = None


class BankChargeRuleResponse(BaseModel):
    """Schema for bank charge rule response."""
    id: UUID
    entity_id: Optional[UUID] = None
    bank_account_id: Optional[UUID] = None
    
    name: str
    description: Optional[str] = None
    charge_type: AdjustmentType
    detection_method: ChargeDetectionMethod
    
    narration_pattern: Optional[str] = None
    narration_keywords: Optional[List[str]] = None
    
    exact_amount: Optional[Decimal] = None
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None
    
    debit_account_code: Optional[str] = None
    credit_account_code: Optional[str] = None
    
    includes_vat: bool
    vat_rate: Decimal
    
    is_active: bool
    is_system_rule: bool
    priority: int
    
    times_applied: int
    last_applied_at: Optional[datetime] = None
    
    created_at: datetime

    class Config:
        from_attributes = True


# ===========================================
# MATCHING RULE SCHEMAS
# ===========================================

class MatchingRuleCreate(BaseModel):
    """Schema for creating a matching rule."""
    bank_account_id: Optional[UUID] = None
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    
    # Bank criteria
    bank_narration_pattern: Optional[str] = Field(None, max_length=500)
    bank_narration_keywords: Optional[List[str]] = None
    bank_reference_pattern: Optional[str] = Field(None, max_length=200)
    bank_amount_min: Optional[Decimal] = None
    bank_amount_max: Optional[Decimal] = None
    bank_is_debit: Optional[bool] = None
    
    # Ledger criteria
    ledger_description_pattern: Optional[str] = Field(None, max_length=500)
    ledger_account_code: Optional[str] = Field(None, max_length=20)
    ledger_vendor_id: Optional[UUID] = None
    ledger_customer_id: Optional[UUID] = None
    
    # Settings
    date_tolerance_days: int = Field(default=3)
    amount_tolerance_percent: Decimal = Field(default=Decimal("0.00"))
    auto_match: bool = Field(default=False)
    priority: int = Field(default=100)


class MatchingRuleUpdate(BaseModel):
    """Schema for updating a matching rule."""
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    
    bank_narration_pattern: Optional[str] = Field(None, max_length=500)
    bank_narration_keywords: Optional[List[str]] = None
    bank_reference_pattern: Optional[str] = Field(None, max_length=200)
    bank_amount_min: Optional[Decimal] = None
    bank_amount_max: Optional[Decimal] = None
    bank_is_debit: Optional[bool] = None
    
    ledger_description_pattern: Optional[str] = Field(None, max_length=500)
    ledger_account_code: Optional[str] = Field(None, max_length=20)
    ledger_vendor_id: Optional[UUID] = None
    ledger_customer_id: Optional[UUID] = None
    
    date_tolerance_days: Optional[int] = None
    amount_tolerance_percent: Optional[Decimal] = None
    auto_match: Optional[bool] = None
    is_active: Optional[bool] = None
    priority: Optional[int] = None


class MatchingRuleResponse(BaseModel):
    """Schema for matching rule response."""
    id: UUID
    entity_id: UUID
    bank_account_id: Optional[UUID] = None
    
    name: str
    description: Optional[str] = None
    
    bank_narration_pattern: Optional[str] = None
    bank_narration_keywords: Optional[List[str]] = None
    bank_reference_pattern: Optional[str] = None
    bank_amount_min: Optional[Decimal] = None
    bank_amount_max: Optional[Decimal] = None
    bank_is_debit: Optional[bool] = None
    
    ledger_description_pattern: Optional[str] = None
    ledger_account_code: Optional[str] = None
    ledger_vendor_id: Optional[UUID] = None
    ledger_customer_id: Optional[UUID] = None
    
    date_tolerance_days: int
    amount_tolerance_percent: Decimal
    auto_match: bool
    
    times_used: int
    last_used_at: Optional[datetime] = None
    successful_matches: int
    
    is_active: bool
    priority: int
    
    created_at: datetime

    class Config:
        from_attributes = True


# ===========================================
# API CONNECTION SCHEMAS
# ===========================================

class MonoConnectRequest(BaseModel):
    """Schema for connecting Mono account."""
    auth_code: str = Field(..., description="Mono authorization code from Connect widget")


class OkraConnectRequest(BaseModel):
    """Schema for connecting Okra account."""
    record_id: str = Field(..., description="Okra record ID from widget")
    customer_id: Optional[str] = None


class StitchConnectRequest(BaseModel):
    """Schema for connecting Stitch account."""
    authorization_code: str = Field(..., description="OAuth authorization code")
    redirect_uri: str


class BankSyncRequest(BaseModel):
    """Schema for triggering bank sync."""
    bank_account_id: UUID
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class BankSyncResponse(BaseModel):
    """Schema for bank sync response."""
    bank_account_id: UUID
    source: BankStatementSource
    status: str
    transactions_fetched: int
    new_transactions: int
    duplicates_skipped: int
    sync_started_at: datetime
    sync_completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


# ===========================================
# REPORT SCHEMAS
# ===========================================

class ReconciliationSummaryReport(BaseModel):
    """Schema for reconciliation summary report."""
    reconciliation_id: UUID
    bank_account_name: str
    bank_name: str
    account_number: str
    reconciliation_date: date
    period_start: date
    period_end: date
    
    # Balance Summary
    statement_ending_balance: Decimal
    adjusted_bank_balance: Decimal
    ledger_ending_balance: Decimal
    adjusted_book_balance: Decimal
    difference: Decimal
    is_balanced: bool
    
    # Nigerian Charges Summary
    total_emtl: Decimal
    total_stamp_duty: Decimal
    total_bank_charges: Decimal
    total_vat_on_charges: Decimal
    total_wht_deducted: Decimal
    
    # Match Summary
    total_transactions: int
    matched_transactions: int
    match_percentage: Decimal
    
    # Outstanding Items
    deposits_in_transit_count: int
    deposits_in_transit_total: Decimal
    outstanding_checks_count: int
    outstanding_checks_total: Decimal
    
    # Workflow
    status: ReconciliationStatus
    prepared_by: Optional[str] = None
    prepared_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None


class ReconciliationHistoryItem(BaseModel):
    """Schema for reconciliation history list item."""
    id: UUID
    reconciliation_date: date
    period_start: date
    period_end: date
    statement_ending_balance: Decimal
    difference: Decimal
    is_balanced: bool
    status: ReconciliationStatus
    matched_transactions: int
    total_transactions: int
    created_at: datetime


# ===========================================
# PAGINATION
# ===========================================

class PaginatedResponse(BaseModel):
    """Generic paginated response."""
    items: List[Any]
    total: int
    page: int
    page_size: int
    pages: int


# Update forward references
BankReconciliationDetailResponse.model_rebuild()
