"""
Tekvwa Pro Audit - Chart of Accounts & General Ledger Models

Complete Double-Entry Accounting System with:
- Chart of Accounts (Assets, Liabilities, Equity, Revenue, Expenses)
- General Ledger with Journal Entries
- Period Management and Closing
- Bank Reconciliation Integration
- Nigerian Tax Integration (VAT, WHT, EMTL)

This is the accounting backbone that all modules post to.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
    Enum as SQLEnum, JSON, UniqueConstraint, Index, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, AuditMixin

if TYPE_CHECKING:
    from app.models.entity import BusinessEntity
    from app.models.user import User


# =============================================================================
# ENUMS
# =============================================================================

class AccountType(str, Enum):
    """Main account types (ALERIE)."""
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    INCOME = "income"  # Alias for revenue
    EXPENSE = "expense"


class AccountSubType(str, Enum):
    """Sub-types for detailed classification."""
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
    """Normal balance direction."""
    DEBIT = "debit"
    CREDIT = "credit"


class JournalEntryStatus(str, Enum):
    """Status of a journal entry."""
    DRAFT = "draft"
    PENDING = "pending"
    POSTED = "posted"
    REVERSED = "reversed"
    VOIDED = "voided"


class JournalEntryType(str, Enum):
    """Type/source of journal entry."""
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
    # FX Gain/Loss types
    FX_REVALUATION = "fx_revaluation"
    FX_REALIZED_GAIN_LOSS = "fx_realized_gain_loss"
    FX_UNREALIZED_GAIN_LOSS = "fx_unrealized_gain_loss"


class FiscalPeriodStatus(str, Enum):
    """Status of a fiscal period."""
    OPEN = "open"
    PENDING_CLOSE = "pending_close"
    CLOSED = "closed"
    LOCKED = "locked"
    REOPENED = "reopened"


# =============================================================================
# CHART OF ACCOUNTS
# =============================================================================

class ChartOfAccounts(BaseModel, AuditMixin):
    """
    Chart of Accounts - The foundation of the accounting system.
    
    Every account in the system is defined here. Follows Nigerian
    IFRS/GAAP standards with local tax integration.
    """
    
    __tablename__ = "chart_of_accounts"

    # Overrides AuditMixin's created_by_id/updated_by_id: this table's migration added a real
    # FK to users.id that the mixin doesn't declare (see docs/REMEDIATION_LOG.md, Finding 49).
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )
    updated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )

    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Account Identification
    account_code: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="Unique account code (e.g., 1000, 1100, 2000)",
    )
    account_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Classification
    account_type: Mapped[AccountType] = mapped_column(
        SQLEnum(AccountType), nullable=False,
    )
    account_sub_type: Mapped[Optional[AccountSubType]] = mapped_column(
        SQLEnum(AccountSubType), nullable=True,
    )
    normal_balance: Mapped[NormalBalance] = mapped_column(
        SQLEnum(NormalBalance), nullable=False,
    )
    
    # Hierarchy
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chart_of_accounts.id", ondelete="SET NULL"),
        nullable=True,
        comment="Parent account for hierarchical COA",
    )
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_header: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="True if this is a header/parent account, not for posting",
    )
    
    # Balance Tracking
    opening_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    opening_balance_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    current_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
        comment="Current balance (updated by journal entries)",
    )
    ytd_debit: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    ytd_credit: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Bank Account Link
    bank_account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bank_accounts.id", ondelete="SET NULL"),
        nullable=True,
        comment="Link to bank account for bank-type accounts",
    )
    
    # Tax Integration
    is_tax_account: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tax_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        comment="vat_output, vat_input, wht_payable, wht_receivable, paye, pension, emtl, stamp_duty",
    )
    tax_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=5, scale=2), nullable=True,
    )
    
    # System Flags
    is_system_account: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="System-generated accounts cannot be deleted",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_reconcilable: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="Can this account be reconciled?",
    )
    
    # Reporting Tags
    cash_flow_category: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        comment="operating, investing, financing",
    )
    
    # Multi-Currency Support (for FX/domiciliary accounts)
    currency: Mapped[str] = mapped_column(
        String(3), default="NGN", nullable=False,
        comment="Currency code (ISO 4217) - NGN, USD, EUR, GBP, etc.",
    )
    
    # Sorting
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Relationships
    entity: Mapped["BusinessEntity"] = relationship("BusinessEntity")
    parent: Mapped[Optional["ChartOfAccounts"]] = relationship(
        "ChartOfAccounts",
        remote_side="ChartOfAccounts.id",
        back_populates="children",
    )
    children: Mapped[List["ChartOfAccounts"]] = relationship(
        "ChartOfAccounts",
        back_populates="parent",
    )
    journal_lines: Mapped[List["JournalEntryLine"]] = relationship(
        "JournalEntryLine",
        back_populates="account",
    )
    
    __table_args__ = (
        UniqueConstraint('entity_id', 'account_code', name='uq_coa_entity_code'),
        Index('ix_coa_entity_type', 'entity_id', 'account_type'),
        Index('ix_coa_entity_parent', 'entity_id', 'parent_id'),
    )
    
    def __repr__(self) -> str:
        return f"<ChartOfAccounts({self.account_code}: {self.account_name})>"


# =============================================================================
# FISCAL PERIODS
# =============================================================================

class FiscalYear(BaseModel):
    """
    Fiscal year definition.
    """
    
    __tablename__ = "fiscal_years"
    
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    year_name: Mapped[str] = mapped_column(String(50), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Relationships
    periods: Mapped[List["FiscalPeriod"]] = relationship(
        "FiscalPeriod",
        back_populates="fiscal_year",
        cascade="all, delete-orphan",
    )
    
    __table_args__ = (
        UniqueConstraint('entity_id', 'year_name', name='uq_fiscal_year_entity_name'),
    )


class FiscalPeriod(BaseModel):
    """
    Fiscal period (month) within a fiscal year.
    Controls when journal entries can be posted.
    """
    
    __tablename__ = "fiscal_periods"
    
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fiscal_year_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fiscal_years.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    period_name: Mapped[str] = mapped_column(String(50), nullable=False)
    period_number: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    status: Mapped[FiscalPeriodStatus] = mapped_column(
        SQLEnum(FiscalPeriodStatus),
        default=FiscalPeriodStatus.OPEN,
        nullable=False,
    )
    
    # Bank reconciliation requirement
    bank_reconciled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="All bank accounts reconciled for this period?",
    )
    reconciliation_ids: Mapped[Optional[List]] = mapped_column(
        JSONB, nullable=True,
        comment="List of completed reconciliation IDs",
    )
    
    # Closing details
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    closing_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    fiscal_year: Mapped["FiscalYear"] = relationship("FiscalYear", back_populates="periods")
    journal_entries: Mapped[List["JournalEntry"]] = relationship(
        "JournalEntry",
        back_populates="fiscal_period",
    )
    
    __table_args__ = (
        UniqueConstraint('entity_id', 'fiscal_year_id', 'period_number', name='uq_fiscal_period'),
        CheckConstraint('period_number >= 1 AND period_number <= 13', name='ck_period_number'),
    )


# =============================================================================
# JOURNAL ENTRIES
# =============================================================================

class JournalEntry(BaseModel, AuditMixin):
    """
    Journal Entry - The core of double-entry accounting.
    
    Every financial transaction creates a journal entry with
    balanced debits and credits.
    """
    
    __tablename__ = "journal_entries"

    # Overrides AuditMixin's created_by_id/updated_by_id — see ChartOfAccounts above (Finding 49).
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )
    updated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )

    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fiscal_period_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fiscal_periods.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Entry Identification
    entry_number: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="Auto-generated journal entry number (e.g., JE-2026-00001)",
    )
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    
    # Entry Type & Source
    entry_type: Mapped[JournalEntryType] = mapped_column(
        SQLEnum(JournalEntryType),
        default=JournalEntryType.MANUAL,
        nullable=False,
    )
    source_module: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        comment="Module that created this entry (sales, payroll, etc.)",
    )
    source_document_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        comment="Type of source document (invoice, receipt, etc.)",
    )
    source_document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
        comment="ID of the source document",
    )
    source_reference: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        comment="Reference number from source document",
    )
    
    # Description
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    memo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Totals (for quick reference - must always balance)
    total_debit: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    total_credit: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Currency
    currency: Mapped[str] = mapped_column(String(3), default="NGN", nullable=False)
    exchange_rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=6),
        default=Decimal("1.000000"),
        nullable=False,
    )
    
    # Status
    status: Mapped[JournalEntryStatus] = mapped_column(
        SQLEnum(JournalEntryStatus),
        default=JournalEntryStatus.DRAFT,
        nullable=False,
    )
    
    # Posting details
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    posted_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Reversal tracking
    is_reversed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reversed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reversed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reversal_entry_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("journal_entries.id", ondelete="SET NULL"),
        nullable=True,
        comment="ID of the reversing entry",
    )
    original_entry_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("journal_entries.id", ondelete="SET NULL"),
        nullable=True,
        comment="ID of original entry (if this is a reversal)",
    )
    reversal_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Audit & Compliance
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Bank reconciliation link
    reconciliation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bank_reconciliations.id", ondelete="SET NULL"),
        nullable=True,
        comment="Created by bank reconciliation",
    )
    
    # Finding 50 (docs/FINDING_50_SCOPE.md): attachments (JSONB) was removed - it never existed on
    # the live table and had zero references anywhere in the codebase. is_recurring/
    # recurring_entry_id added below - both already existed on the live table but were never
    # declared here. Neither pair is currently used by any real call site; fixed to match the
    # live table exactly since it's the real, deployed state, not because either side has an
    # active bug today.
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # No ForeignKey() here - the live column has no FK constraint at all, unlike most id-shaped
    # columns in this codebase; declaring one would mean a new migration for a currently-unused
    # field.
    recurring_entry_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Relationships
    entity: Mapped["BusinessEntity"] = relationship("BusinessEntity")
    fiscal_period: Mapped[Optional["FiscalPeriod"]] = relationship(
        "FiscalPeriod", back_populates="journal_entries",
    )
    lines: Mapped[List["JournalEntryLine"]] = relationship(
        "JournalEntryLine",
        back_populates="journal_entry",
        cascade="all, delete-orphan",
        order_by="JournalEntryLine.line_number",
    )
    
    __table_args__ = (
        UniqueConstraint('entity_id', 'entry_number', name='uq_journal_entry_number'),
        Index('ix_je_entity_date', 'entity_id', 'entry_date'),
        Index('ix_je_entity_status', 'entity_id', 'status'),
        Index('ix_je_source', 'source_module', 'source_document_id'),
        CheckConstraint('total_debit = total_credit', name='ck_balanced_entry'),
    )
    
    def __repr__(self) -> str:
        return f"<JournalEntry({self.entry_number}: {self.description[:50]})>"


class JournalEntryLine(BaseModel):
    """
    Individual line item in a journal entry.
    Each line is either a debit or credit to a specific account.
    """
    
    __tablename__ = "journal_entry_lines"
    
    journal_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("journal_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chart_of_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Amount (one or the other, not both)
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
    
    # Dimensions (for multi-dimensional reporting)
    # Finding 50 (docs/FINDING_50_SCOPE.md): department_id/project_id/bank_transaction_id below
    # previously declared ForeignKey()s that were never actually created on the live table -
    # confirmed zero references anywhere in the codebase for all three, so removed the
    # ForeignKey() rather than write a migration to create real constraints for currently-unused
    # columns. cost_center_id added (already existed on the live table, also unused, also no FK).
    department_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    cost_center_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Tax details
    tax_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Customer/Vendor link
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
    )
    vendor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendors.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Bank transaction link
    bank_transaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    
    # Relationships
    journal_entry: Mapped["JournalEntry"] = relationship(
        "JournalEntry", back_populates="lines",
    )
    account: Mapped["ChartOfAccounts"] = relationship(
        "ChartOfAccounts", back_populates="journal_lines",
    )
    
    __table_args__ = (
        UniqueConstraint('journal_entry_id', 'line_number', name='uq_je_line_number'),
        Index('ix_jel_account', 'account_id'),
        CheckConstraint(
            '(debit_amount > 0 AND credit_amount = 0) OR (credit_amount > 0 AND debit_amount = 0) OR (debit_amount = 0 AND credit_amount = 0)',
            name='ck_debit_or_credit'
        ),
    )
    
    def __repr__(self) -> str:
        return f"<JournalEntryLine(DR: {self.debit_amount}, CR: {self.credit_amount})>"


# =============================================================================
# ACCOUNT BALANCES (DENORMALIZED FOR PERFORMANCE)
# =============================================================================

class AccountBalance(BaseModel):
    """
    Period-specific account balances for quick reporting.
    Denormalized from journal entries for performance.

    Finding 50 (docs/FINDING_50_SCOPE.md): entity_id/ytd_debit/ytd_credit/last_updated below were
    already correctly declared here, but didn't exist on the live table at all (which had no
    entity_id, no ytd_debit/ytd_credit, and last_calculated_at instead of last_updated) until
    alembic/versions/20260920_0742_backfill_account_balances_column_drift.py added and backfilled
    them - the database was migrated to match this model and its real callers
    (app/utils/query_optimization.py, accounting_service.py, year_end_closing_service.py), not the
    other way around. The old last_calculated_at column stays in place, unmapped.
    """

    __tablename__ = "account_balances"
    
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chart_of_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    fiscal_period_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fiscal_periods.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    # Balance components
    opening_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    period_debit: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    period_credit: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    closing_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Running balance for YTD
    ytd_debit: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    ytd_credit: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )
    
    __table_args__ = (
        UniqueConstraint('entity_id', 'account_id', 'fiscal_period_id', name='uq_account_balance'),
        Index('ix_ab_entity_period', 'entity_id', 'fiscal_period_id'),
        Index('ix_ab_account', 'account_id'),
    )


# =============================================================================
# RECURRING JOURNAL ENTRIES
# =============================================================================

class RecurringJournalEntry(BaseModel, AuditMixin):
    """
    Template for recurring journal entries (depreciation, accruals, etc.)

    Finding 50 (docs/FINDING_50_SCOPE.md): this model is imported by accounting_service.py but
    never actually constructed, queried, or read anywhere in the codebase - genuinely dead in
    current usage, unlike every other table fixed under this finding. With no real call site to
    determine intent from, and the database being the real, migrated, currently-deployed state,
    fixed this model to match the live table exactly (option (B)) rather than write a migration
    for speculative fields nothing depends on. entry_type/next_date/template_lines/total_amount/
    last_generated_date/times_generated below were removed (none exist on the live table);
    start_date/next_run_date/template_data/run_count/auto_post added (all already existed on the
    live table).
    """

    __tablename__ = "recurring_journal_entries"

    # Overrides AuditMixin's created_by_id only — this table's migration added a FK for
    # created_by_id but NOT updated_by_id (confirmed via live-DB constraint check, Finding 49).
    # updated_by_id intentionally keeps inheriting the mixin's plain (no-FK) column.
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )

    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Schedule
    frequency: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="daily, weekly, monthly, quarterly, annually",
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    next_run_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    last_run_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Template data
    template_data: Mapped[dict] = mapped_column(
        JSONB, nullable=False,
        comment="Template line items for the entry",
    )

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_post: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    run_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index('ix_rje_entity_active', 'entity_id', 'is_active'),
    )


# =============================================================================
# GL INTEGRATION TRACKING
# =============================================================================

class GLIntegrationLog(BaseModel):
    """
    Tracks what has been posted to the GL from each module.
    Ensures no double posting and enables reconciliation.

    Finding 50 (docs/FINDING_50_SCOPE.md): this table is missing both created_at and updated_at at
    the DB level entirely - see the accompanying migration. journal_entry_id's nullable/ondelete
    relaxed to match the live column exactly (SET NULL, not CASCADE) - purely a metadata
    correction, zero functional risk either way since gl_event_service.py/accounting_service.py
    always provide a value. The model's __table_args__ unique constraint additionally includes
    is_reversed, which the live constraint doesn't - left as-is since nothing in the codebase
    currently ever sets GLIntegrationLog.is_reversed to True, making the difference dormant rather
    than an active bug.
    """

    __tablename__ = "gl_integration_logs"
    
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Source document
    source_module: Mapped[str] = mapped_column(String(50), nullable=False)
    source_document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # GL Entry
    journal_entry_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("journal_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Tracking
    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )
    posted_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Reversal tracking
    is_reversed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reversal_log_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gl_integration_logs.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    __table_args__ = (
        UniqueConstraint(
            'entity_id', 'source_module', 'source_document_type', 
            'source_document_id', 'is_reversed',
            name='uq_gl_integration_source'
        ),
        Index('ix_gli_source', 'source_module', 'source_document_id'),
        Index('ix_gli_journal', 'journal_entry_id'),
    )


# =============================================================================
# MULTI-CURRENCY FX GAIN/LOSS
# =============================================================================

class FXRevaluationType(str, Enum):
    """Type of FX revaluation."""
    REALIZED = "realized"         # Actual conversion (payment/receipt)
    UNREALIZED = "unrealized"     # Period-end revaluation
    SETTLEMENT = "settlement"     # Final settlement of FC balance


class FXAccountType(str, Enum):
    """Types of accounts that can have FX exposure."""
    BANK = "bank"                 # Foreign currency bank accounts
    RECEIVABLE = "receivable"     # Foreign currency AR
    PAYABLE = "payable"           # Foreign currency AP
    LOAN = "loan"                 # Foreign currency loans
    INTERCOMPANY = "intercompany" # Intercompany balances


class FXRevaluation(BaseModel):
    """
    Foreign Exchange Revaluation Records.
    
    Tracks realized and unrealized FX gains/losses for:
    - Foreign currency bank accounts (domiciliary accounts)
    - Foreign currency AR/AP balances
    - Intercompany balances
    
    Nigerian IFRS compliance: IAS 21 - Effects of Changes in Foreign Exchange Rates
    """
    
    __tablename__ = "fx_revaluations"
    
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Revaluation identification
    revaluation_date: Mapped[date] = mapped_column(Date, nullable=False)
    revaluation_type: Mapped[FXRevaluationType] = mapped_column(
        SQLEnum(FXRevaluationType),
        nullable=False,
    )
    
    # Source account
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chart_of_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    fx_account_type: Mapped[FXAccountType] = mapped_column(
        SQLEnum(FXAccountType),
        nullable=False,
    )
    
    # Currency details
    foreign_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    functional_currency: Mapped[str] = mapped_column(String(3), default="NGN", nullable=False)
    
    # Original booking
    original_fc_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
        comment="Original amount in foreign currency",
    )
    original_exchange_rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=6),
        nullable=False,
        comment="Exchange rate at original booking",
    )
    original_ngn_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
        comment="Original NGN equivalent",
    )
    
    # Revaluation
    revaluation_rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=6),
        nullable=False,
        comment="Exchange rate at revaluation date",
    )
    revalued_ngn_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
        comment="NGN equivalent at revaluation rate",
    )
    
    # FX gain/loss
    fx_gain_loss: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
        comment="Positive = gain, Negative = loss",
    )
    is_gain: Mapped[bool] = mapped_column(Boolean, nullable=False)
    
    # Journal entry link
    journal_entry_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("journal_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Reference document (for realized gains/losses)
    source_document_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source_document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    
    # Fiscal period
    fiscal_period_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fiscal_periods.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Audit
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    entity: Mapped["BusinessEntity"] = relationship("BusinessEntity")
    account: Mapped["ChartOfAccounts"] = relationship("ChartOfAccounts")
    journal_entry: Mapped[Optional["JournalEntry"]] = relationship("JournalEntry")
    fiscal_period: Mapped[Optional["FiscalPeriod"]] = relationship("FiscalPeriod")
    
    __table_args__ = (
        Index('ix_fx_reval_entity_date', 'entity_id', 'revaluation_date'),
        Index('ix_fx_reval_account', 'account_id', 'revaluation_date'),
        Index('ix_fx_reval_type', 'revaluation_type', 'revaluation_date'),
    )


class FXExposureSummary(BaseModel):
    """
    Summarizes FX exposure by currency for reporting.
    Maintained through triggers or batch updates.
    """
    
    __tablename__ = "fx_exposure_summaries"
    
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # As of date
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Currency
    foreign_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    
    # Exposure by type
    bank_fc_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2), default=Decimal("0.00"), nullable=False
    )
    receivable_fc_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2), default=Decimal("0.00"), nullable=False
    )
    payable_fc_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2), default=Decimal("0.00"), nullable=False
    )
    loan_fc_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2), default=Decimal("0.00"), nullable=False
    )
    
    # Net exposure
    net_fc_exposure: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2), nullable=False,
        comment="Assets - Liabilities in FC",
    )
    
    # Current rate and NGN equivalent
    current_rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=6), nullable=False
    )
    net_ngn_exposure: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2), nullable=False
    )
    
    # YTD gain/loss
    ytd_realized_gain_loss: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2), default=Decimal("0.00"), nullable=False
    )
    ytd_unrealized_gain_loss: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2), default=Decimal("0.00"), nullable=False
    )
    
    __table_args__ = (
        UniqueConstraint('entity_id', 'as_of_date', 'foreign_currency', name='uq_fx_exposure_date_currency'),
        Index('ix_fx_exposure_entity', 'entity_id', 'as_of_date'),
    )

