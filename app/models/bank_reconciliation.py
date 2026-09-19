"""
Tekvwa Pro Audit - Bank Reconciliation Model

Comprehensive bank reconciliation models for Nigerian businesses.
Supports:
- Multi-channel bank statement import (API: Mono/Okra/Stitch, CSV, Excel, MT940, PDF OCR)
- Advanced transaction matching (exact, fuzzy, one-to-many, many-to-one, rule-based)
- Nigerian-specific charge detection (EMTL, Stamp Duty, VAT, WHT)
- Full reconciliation workflow with audit trail
- Outstanding items tracking and carry-forward

Nigerian Banking Context:
- NIP transfers, USSD, POS settlements
- Delayed postings (weekends, holidays)
- Frequent reversals
- Electronic Money Transfer Levy (N50 on inflows > N10,000)
- Stamp Duty (N50 where applicable)
- VAT on bank charges (7.5%)
- WHT deducted at source
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
    Enum as SQLEnum, JSON, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, AuditMixin

if TYPE_CHECKING:
    from app.models.entity import BusinessEntity
    from app.models.transaction import Transaction
    from app.models.user import User


# =============================================================================
# ENUMS
# =============================================================================

class BankAccountType(str, Enum):
    """Bank account type."""
    CURRENT = "current"
    SAVINGS = "savings"
    DOMICILIARY = "domiciliary"
    FIXED_DEPOSIT = "fixed_deposit"
    ESCROW = "escrow"


class BankAccountCurrency(str, Enum):
    """Supported currencies."""
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


class MatchStatus(str, Enum):
    """Transaction matching status."""
    UNMATCHED = "unmatched"
    SUGGESTED = "suggested"
    AUTO_MATCHED = "auto_matched"
    MANUAL_MATCHED = "manual_matched"
    PARTIALLY_MATCHED = "partially_matched"
    RECONCILED = "reconciled"
    EXCLUDED = "excluded"
    DISPUTED = "disputed"


class MatchType(str, Enum):
    """Type of transaction match."""
    EXACT = "exact"
    FUZZY = "fuzzy"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    RULE_BASED = "rule_based"
    MANUAL = "manual"


class MatchConfidenceLevel(str, Enum):
    """Confidence level for automatic matches."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReconciliationStatus(str, Enum):
    """Bank reconciliation status."""
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    PENDING_REVIEW = "pending_review"
    COMPLETED = "completed"
    APPROVED = "approved"
    LOCKED = "locked"


class AdjustmentType(str, Enum):
    """Type of reconciliation adjustment - Nigerian specific."""
    BANK_CHARGE = "bank_charge"
    EMTL = "emtl"  # Electronic Money Transfer Levy
    STAMP_DUTY = "stamp_duty"
    SMS_FEE = "sms_fee"
    MAINTENANCE_FEE = "maintenance_fee"
    VAT_ON_CHARGES = "vat_on_charges"
    WHT_DEDUCTION = "wht_deduction"
    INTEREST_INCOME = "interest_income"
    INTEREST_EXPENSE = "interest_expense"
    REVERSAL = "reversal"
    POS_SETTLEMENT = "pos_settlement"
    NIP_CHARGE = "nip_charge"
    USSD_CHARGE = "ussd_charge"
    OTHER = "other"


class UnmatchedItemType(str, Enum):
    """Type of unmatched item."""
    OUTSTANDING_CHEQUE = "outstanding_cheque"
    DEPOSIT_IN_TRANSIT = "deposit_in_transit"
    BANK_CHARGE = "bank_charge"
    UNEXPECTED_DEPOSIT = "unexpected_deposit"
    UNEXPECTED_WITHDRAWAL = "unexpected_withdrawal"
    REVERSAL = "reversal"


class ChargeDetectionMethod(str, Enum):
    """Method for detecting bank charges."""
    NARRATION_REGEX = "narration_regex"
    AMOUNT_EXACT = "amount_exact"
    AMOUNT_RANGE = "amount_range"
    COMBINED = "combined"
    UNMATCHED = "unmatched"
    AUTO_MATCHED = "auto_matched"
    MANUAL_MATCHED = "manual_matched"
    RECONCILED = "reconciled"
    DISPUTED = "disputed"


class ReconciliationStatus(str, Enum):
    """Bank reconciliation status."""
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    APPROVED = "approved"


# ===========================================
# BANK ACCOUNT (FOR RECONCILIATION)
# ===========================================

class BankAccount(BaseModel, AuditMixin):
    """
    Bank account for reconciliation purposes.
    
    Links to the Chart of Accounts (GL) for proper accounting integration.
    Supports Nigerian banking APIs: Mono, Okra, Stitch.
    """
    
    __tablename__ = "bank_accounts"
    
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Bank Details
    bank_name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_name: Mapped[str] = mapped_column(String(200), nullable=False)
    account_number: Mapped[str] = mapped_column(String(20), nullable=False)
    account_type: Mapped[BankAccountType] = mapped_column(
        SQLEnum(BankAccountType),
        default=BankAccountType.CURRENT,
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(String(3), default="NGN", nullable=False)
    bank_code: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True,
        comment="CBN bank code for electronic transfers",
    )
    
    # GL Integration
    gl_account_code: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
        comment="General Ledger account code for this bank account",
    )
    gl_account_name: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
    )
    
    # Opening Balance
    opening_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    opening_balance_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    
    # Current Balance (updated from reconciliations)
    current_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    last_reconciled_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    last_reconciled_balance: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=18, scale=2), nullable=True,
    )
    
    # Nigerian Banking API Integration
    # Mono API (https://mono.co)
    mono_account_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    mono_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    mono_last_sync: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Okra API (https://okra.ng)
    okra_account_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    okra_record_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    okra_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    okra_last_sync: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Stitch API (https://stitch.money)
    stitch_account_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    stitch_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    stitch_last_sync: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Sync Settings
    auto_sync_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sync_frequency_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    last_sync_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Legacy API field (for backward compatibility)
    api_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    api_credentials: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True,
        comment="Encrypted API credentials for bank integration",
    )
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    entity: Mapped["BusinessEntity"] = relationship("BusinessEntity", back_populates="bank_accounts")
    statements: Mapped[List["BankStatement"]] = relationship(
        "BankStatement",
        back_populates="bank_account",
        cascade="all, delete-orphan",
    )
    reconciliations: Mapped[List["BankReconciliation"]] = relationship(
        "BankReconciliation",
        back_populates="bank_account",
        cascade="all, delete-orphan",
    )
    charge_rules: Mapped[List["BankChargeRule"]] = relationship(
        "BankChargeRule",
        back_populates="bank_account",
        cascade="all, delete-orphan",
    )
    matching_rules: Mapped[List["MatchingRule"]] = relationship(
        "MatchingRule",
        back_populates="bank_account",
        cascade="all, delete-orphan",
    )
    
    __table_args__ = (
        UniqueConstraint('entity_id', 'account_number', 'bank_name', name='uq_bank_account'),
    )
    
    def __repr__(self) -> str:
        return f"<BankAccount(id={self.id}, bank={self.bank_name}, account={self.account_number})>"


# ===========================================
# BANK STATEMENT
# ===========================================

class BankStatement(BaseModel):
    """
    Imported bank statement containing transactions from the bank.
    """
    
    __tablename__ = "bank_statements"
    
    bank_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bank_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Statement Period
    statement_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Balances from Statement
    opening_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
    )
    closing_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
    )
    
    # Import Details
    source: Mapped[BankStatementSource] = mapped_column(
        SQLEnum(BankStatementSource),
        default=BankStatementSource.MANUAL_ENTRY,
        nullable=False,
    )
    file_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )
    imported_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Transaction Count
    total_transactions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matched_transactions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unmatched_transactions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Relationships
    bank_account: Mapped["BankAccount"] = relationship(
        "BankAccount", back_populates="statements",
    )
    transactions: Mapped[List["BankStatementTransaction"]] = relationship(
        "BankStatementTransaction",
        back_populates="statement",
        cascade="all, delete-orphan",
    )
    
    def __repr__(self) -> str:
        return f"<BankStatement(id={self.id}, date={self.statement_date})>"


# ===========================================
# BANK STATEMENT TRANSACTION
# ===========================================

class BankStatementTransaction(BaseModel):
    """
    Individual transaction from a bank statement.
    
    Enhanced with Nigerian-specific features:
    - EMTL (Electronic Money Transfer Levy) detection
    - Stamp Duty detection
    - Bank charge categorization
    - Reversal tracking
    - Clean narration (post-regex processing)
    """
    
    __tablename__ = "bank_statement_transactions"
    
    statement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bank_statements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Transaction Details
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    value_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    
    # Narration
    raw_narration: Mapped[str] = mapped_column(Text, nullable=False)
    clean_narration: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Cleaned narration after regex processing",
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)  # Alias for compatibility
    reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    bank_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Amounts
    debit_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    credit_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
    )
    
    # Nigerian-Specific Flags
    is_reversal: Mapped[bool] = mapped_column(Boolean, default=False)
    reversed_transaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
        comment="ID of the transaction this reverses",
    )
    is_emtl: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="Electronic Money Transfer Levy (N50 on inflows > N10,000)",
    )
    is_stamp_duty: Mapped[bool] = mapped_column(Boolean, default=False)
    is_bank_charge: Mapped[bool] = mapped_column(Boolean, default=False)
    is_vat_charge: Mapped[bool] = mapped_column(Boolean, default=False)
    is_wht_deduction: Mapped[bool] = mapped_column(Boolean, default=False)
    is_pos_settlement: Mapped[bool] = mapped_column(Boolean, default=False)
    is_nip_transfer: Mapped[bool] = mapped_column(Boolean, default=False)
    is_ussd_transaction: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Detected Charge Type
    detected_charge_type: Mapped[Optional[str]] = mapped_column(
        SQLEnum(AdjustmentType), nullable=True,
    )
    
    # Matching
    match_status: Mapped[MatchStatus] = mapped_column(
        SQLEnum(MatchStatus),
        default=MatchStatus.UNMATCHED,
        nullable=False,
        index=True,
    )
    match_type: Mapped[Optional[str]] = mapped_column(
        SQLEnum(MatchType), nullable=True,
    )
    matched_transaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    match_group_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True,
        comment="Groups related transactions in one-to-many/many-to-one matches",
    )
    match_confidence: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=5, scale=2), nullable=True,
        comment="Auto-match confidence score (0-100)",
    )
    match_confidence_level: Mapped[Optional[str]] = mapped_column(
        SQLEnum(MatchConfidenceLevel), nullable=True,
    )
    matched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    matched_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    matching_rule_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
        comment="ID of the matching rule used for auto-match",
    )
    
    # Duplicate Detection
    duplicate_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True,
        comment="SHA256 hash for duplicate detection",
    )
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Categorization
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    subcategory: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Raw Data
    raw_data: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True,
        comment="Original import data for audit purposes",
    )
    
    # Relationships
    statement: Mapped["BankStatement"] = relationship(
        "BankStatement", back_populates="transactions",
    )
    matched_transaction: Mapped[Optional["Transaction"]] = relationship(
        "Transaction", foreign_keys=[matched_transaction_id],
    )
    
    __table_args__ = (
        Index("ix_bank_stmt_txn_account_date", "statement_id", "transaction_date"),
        Index("ix_bank_stmt_txn_amount", "statement_id", "debit_amount", "credit_amount"),
    )
    matched_transaction: Mapped[Optional["Transaction"]] = relationship(
        "Transaction", foreign_keys=[matched_transaction_id],
    )
    
    @property
    def amount(self) -> Decimal:
        """Get net amount (positive for credits, negative for debits)."""
        return self.credit_amount - self.debit_amount
    
    def __repr__(self) -> str:
        return f"<BankStatementTransaction(id={self.id}, date={self.transaction_date}, amount={self.amount})>"


# ===========================================
# BANK RECONCILIATION
# ===========================================

class BankReconciliation(BaseModel, AuditMixin):
    """
    Bank reconciliation record for a specific period.
    
    Tracks the reconciliation process and results.
    """
    
    __tablename__ = "bank_reconciliations"
    
    bank_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bank_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Reconciliation Period
    reconciliation_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Bank Statement Balances
    statement_opening_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
    )
    statement_closing_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
    )
    
    # Book Balances (from GL)
    book_opening_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
    )
    book_closing_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
    )
    
    # Reconciliation Adjustments
    deposits_in_transit: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
        comment="Deposits recorded in books but not yet in bank",
    )
    outstanding_checks: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
        comment="Checks issued but not yet cleared",
    )
    bank_charges: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
        comment="Bank charges not yet recorded in books",
    )
    interest_earned: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
        comment="Interest not yet recorded in books",
    )
    other_adjustments: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Reconciled Balance
    adjusted_bank_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
    )
    adjusted_book_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
    )
    difference: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
        comment="Difference after adjustments (should be 0 when reconciled)",
    )
    
    # Status
    status: Mapped[ReconciliationStatus] = mapped_column(
        SQLEnum(ReconciliationStatus),
        default=ReconciliationStatus.DRAFT,
        nullable=False,
    )
    
    # Approval
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    completed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    approved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Outstanding Items (JSON for flexibility)
    outstanding_items: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True,
        comment="List of outstanding/unreconciled items",
    )
    
    # Relationships
    bank_account: Mapped["BankAccount"] = relationship(
        "BankAccount", back_populates="reconciliations",
    )
    adjustments: Mapped[List["ReconciliationAdjustment"]] = relationship(
        "ReconciliationAdjustment",
        back_populates="reconciliation",
        cascade="all, delete-orphan",
    )
    unmatched_items: Mapped[List["UnmatchedItem"]] = relationship(
        "UnmatchedItem",
        back_populates="reconciliation",
        cascade="all, delete-orphan",
    )
    
    @property
    def is_balanced(self) -> bool:
        """Check if reconciliation is balanced (difference is zero)."""
        return self.difference == Decimal("0.00")
    
    def __repr__(self) -> str:
        return f"<BankReconciliation(id={self.id}, date={self.reconciliation_date}, status={self.status})>"


# ===========================================
# RECONCILIATION ADJUSTMENT
# ===========================================

class ReconciliationAdjustment(BaseModel):
    """
    Adjusting journal entries created during reconciliation.
    
    Automatically handles Nigerian-specific charges:
    - EMTL (Electronic Money Transfer Levy) - N50 on inflows > N10,000
    - Stamp Duty - N50 where applicable
    - Bank Charges
    - SMS Alert Fees
    - Maintenance Fees
    - VAT on Charges (7.5%)
    - WHT Deductions
    """
    
    __tablename__ = "reconciliation_adjustments"
    
    reconciliation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bank_reconciliations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    bank_transaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bank_statement_transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Adjustment Type
    adjustment_type: Mapped[AdjustmentType] = mapped_column(
        SQLEnum(AdjustmentType),
        nullable=False,
    )
    
    # Journal Entry Details
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    debit_account_code: Mapped[str] = mapped_column(String(20), nullable=False)
    debit_account_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    credit_account_code: Mapped[str] = mapped_column(String(20), nullable=False)
    credit_account_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
    )
    
    # Nigerian Tax Details
    vat_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=18, scale=2), nullable=True,
        comment="VAT component if applicable (7.5%)",
    )
    wht_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=18, scale=2), nullable=True,
        comment="WHT component if applicable",
    )
    
    # Journal Reference
    journal_entry_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    journal_posted: Mapped[bool] = mapped_column(Boolean, default=False)
    journal_posted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    
    # Auto-detection
    auto_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    detection_rule_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    
    # Approval
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    
    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    reconciliation: Mapped["BankReconciliation"] = relationship(
        "BankReconciliation", back_populates="adjustments",
    )
    bank_transaction: Mapped[Optional["BankStatementTransaction"]] = relationship(
        "BankStatementTransaction",
    )
    journal_entry: Mapped[Optional["Transaction"]] = relationship(
        "Transaction", foreign_keys=[journal_entry_id],
    )
    
    def __repr__(self) -> str:
        return f"<ReconciliationAdjustment({self.adjustment_type.value}, {self.amount})>"


# ===========================================
# UNMATCHED ITEM
# ===========================================

class UnmatchedItem(BaseModel):
    """
    Tracks unmatched items that need resolution or carry-forward.
    
    Examples:
    - Outstanding cheques
    - Deposits in transit
    - Bank charges not in books
    - Unexpected deposits/withdrawals
    """
    
    __tablename__ = "unmatched_items"
    
    reconciliation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bank_reconciliations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Source
    item_type: Mapped[UnmatchedItemType] = mapped_column(
        SQLEnum(UnmatchedItemType),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="'bank' or 'ledger'",
    )
    
    # Transaction Reference
    bank_transaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bank_statement_transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    ledger_transaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Details
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Resolution
    resolution: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        comment="carry_forward, journal_created, matched, cancelled, excluded",
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    resolved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Carry Forward
    carried_to_reconciliation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    carried_from_reconciliation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    
    # Journal Entry (if created)
    journal_entry_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Relationships
    reconciliation: Mapped["BankReconciliation"] = relationship(
        "BankReconciliation", back_populates="unmatched_items",
    )
    bank_transaction: Mapped[Optional["BankStatementTransaction"]] = relationship(
        "BankStatementTransaction",
    )
    ledger_transaction: Mapped[Optional["Transaction"]] = relationship(
        "Transaction", foreign_keys=[ledger_transaction_id],
    )
    journal_entry: Mapped[Optional["Transaction"]] = relationship(
        "Transaction", foreign_keys=[journal_entry_id],
    )
    
    def __repr__(self) -> str:
        return f"<UnmatchedItem({self.item_type.value}, {self.amount}, {self.source})>"


# ===========================================
# BANK CHARGE RULE
# ===========================================

class BankChargeRule(BaseModel):
    """
    Rules for automatically detecting and categorizing Nigerian bank charges.
    
    Nigerian-specific rules:
    - EMTL (Electronic Money Transfer Levy) - N50 on transfers > N10,000
    - Stamp Duty - N50 on qualifying transactions
    - SMS Alert Fees
    - Account Maintenance Fees
    - VAT on Bank Charges (7.5%)
    """
    
    __tablename__ = "bank_charge_rules"
    
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=True,  # Null for system-wide rules
        index=True,
    )
    bank_account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bank_accounts.id", ondelete="CASCADE"),
        nullable=True,  # Null for all accounts
    )
    
    # Rule Details
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    charge_type: Mapped[AdjustmentType] = mapped_column(
        SQLEnum(AdjustmentType),
        nullable=False,
    )
    
    # Detection Method
    detection_method: Mapped[ChargeDetectionMethod] = mapped_column(
        SQLEnum(ChargeDetectionMethod),
        nullable=False,
    )
    
    # Narration Pattern (regex)
    narration_pattern: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True,
        comment="Regex pattern to match narration",
    )
    narration_keywords: Mapped[Optional[List[str]]] = mapped_column(
        JSONB, nullable=True,
        comment="List of keywords to match in narration",
    )
    
    # Amount Criteria
    exact_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=18, scale=2), nullable=True,
    )
    min_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=18, scale=2), nullable=True,
    )
    max_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=18, scale=2), nullable=True,
    )
    
    # Account Mapping
    debit_account_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    credit_account_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # Nigerian Tax
    includes_vat: Mapped[bool] = mapped_column(Boolean, default=False)
    vat_rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2),
        default=Decimal("7.5"),
    )
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_system_rule: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="Built-in vs user-defined",
    )
    priority: Mapped[int] = mapped_column(
        Integer, default=100,
        comment="Lower = higher priority",
    )
    
    # Statistics
    times_applied: Mapped[int] = mapped_column(Integer, default=0)
    last_applied_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    
    # Relationships
    entity: Mapped[Optional["BusinessEntity"]] = relationship("BusinessEntity")
    bank_account: Mapped[Optional["BankAccount"]] = relationship(
        "BankAccount", back_populates="charge_rules",
    )
    
    def __repr__(self) -> str:
        return f"<BankChargeRule({self.name}, {self.charge_type.value})>"


# ===========================================
# MATCHING RULE
# ===========================================

class MatchingRule(BaseModel):
    """
    User-defined rules for automatic transaction matching.
    
    Allows custom matching criteria based on:
    - Narration keywords
    - Amount ranges
    - Reference patterns
    - Date tolerance
    """
    
    __tablename__ = "matching_rules"
    
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    bank_account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bank_accounts.id", ondelete="CASCADE"),
        nullable=True,  # Null for all accounts
    )
    
    # Rule Details
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Bank Side Criteria
    bank_narration_pattern: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    bank_narration_keywords: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    bank_reference_pattern: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    bank_amount_min: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=18, scale=2), nullable=True,
    )
    bank_amount_max: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=18, scale=2), nullable=True,
    )
    bank_is_debit: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    
    # Ledger Side Criteria
    ledger_description_pattern: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ledger_account_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    ledger_vendor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    ledger_customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    
    # Match Settings
    date_tolerance_days: Mapped[int] = mapped_column(Integer, default=3)
    amount_tolerance_percent: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2),
        default=Decimal("0.00"),
    )
    auto_match: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="Auto-match without review",
    )
    
    # Statistics
    times_used: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    successful_matches: Mapped[int] = mapped_column(Integer, default=0)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    
    # Relationships
    entity: Mapped["BusinessEntity"] = relationship("BusinessEntity")
    bank_account: Mapped[Optional["BankAccount"]] = relationship(
        "BankAccount", back_populates="matching_rules",
    )
    
    def __repr__(self) -> str:
        return f"<MatchingRule({self.name})>"


# ===========================================
# BANK STATEMENT IMPORT LOG
# ===========================================

class BankStatementImport(BaseModel):
    """
    Tracks bank statement import history for audit trail.
    """
    
    __tablename__ = "bank_statement_imports"
    
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    bank_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bank_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    # Import Details
    source: Mapped[BankStatementSource] = mapped_column(
        SQLEnum(BankStatementSource),
        nullable=False,
    )
    filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
        comment="SHA256 hash for duplicate file detection",
    )
    
    # Period
    statement_start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    statement_end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    
    # Statistics
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Auto-detected charges
    emtl_count: Mapped[int] = mapped_column(Integer, default=0)
    stamp_duty_count: Mapped[int] = mapped_column(Integer, default=0)
    bank_charge_count: Mapped[int] = mapped_column(Integer, default=0)
    reversal_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Status
    status: Mapped[str] = mapped_column(
        String(20), default="pending",
        comment="pending, processing, completed, failed",
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Import User
    imported_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )
    processing_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Raw Data
    import_log: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True,
        comment="Detailed import log for debugging",
    )
    
    # Relationships
    entity: Mapped["BusinessEntity"] = relationship("BusinessEntity")
    bank_account: Mapped["BankAccount"] = relationship("BankAccount")
    imported_by: Mapped[Optional["User"]] = relationship("User")
    
    def __repr__(self) -> str:
        return f"<BankStatementImport({self.source.value}, {self.imported_at})>"
