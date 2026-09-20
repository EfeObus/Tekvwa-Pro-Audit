"""
Advanced Accounting Models for Tekvwa Pro Audit
Implements: Dimensional Accounting, 3-Way Matching, WHT Vault, Budget Management

Nigerian Tax Reform 2026 Compliant
"""

from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from typing import Optional, List
import uuid

from sqlalchemy import (
    Column, String, Text, Boolean, Integer, BigInteger, Float, Date, DateTime,
    ForeignKey, Numeric, JSON, Enum as SQLEnum, Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


# =============================================================================
# ENUMS
# =============================================================================

class DimensionType(str, Enum):
    """Types of accounting dimensions for multi-dimensional reporting"""
    DEPARTMENT = "department"
    PROJECT = "project"
    LOCATION = "location"
    LGA = "lga"
    STATE = "state"
    SALES_CHANNEL = "sales_channel"
    COST_CENTER = "cost_center"
    PRODUCT_LINE = "product_line"
    CUSTOM = "custom"


class MatchingStatus(str, Enum):
    """
    Status for 3-way matching (PO, GRN, Invoice)

    Finding 50 (docs/FINDING_50_SCOPE.md): this enum's member set previously didn't match either
    the live Postgres enum type OR what ThreeWayMatchingService/forensic_audit.py actually
    reference (MATCHED/DISCREPANCY/PENDING_REVIEW/REJECTED) - PARTIAL_MATCH/FULL_MATCH/MISMATCH/
    AUTO_APPROVED/MANUAL_OVERRIDE had zero references anywhere in the codebase, and every real
    usage referenced a member that raised AttributeError. Not a casing issue (Finding 1's
    territory) - the member set itself was wrong.
    """
    PENDING = "pending"
    MATCHED = "matched"
    DISCREPANCY = "discrepancy"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"


class WHTCreditStatus(str, Enum):
    """Status for WHT Credit Notes"""
    PENDING = "pending"
    RECEIVED = "received"
    MATCHED = "matched"
    DISPUTED = "disputed"
    EXPIRED = "expired"
    APPLIED = "applied"


class ApprovalStatus(str, Enum):
    """
    Status for M-of-N approval workflows

    Finding 50 (docs/FINDING_50_SCOPE.md): PARTIALLY_APPROVED had zero references anywhere in the
    codebase and isn't a value the live Postgres enum has - removed. CANCELLED is a real live enum
    value with no current Python-side usage; added anyway to keep this enum a complete match for
    what the database actually accepts.
    """
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class BudgetPeriodType(str, Enum):
    """Budget period types"""
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"


# =============================================================================
# DIMENSIONAL ACCOUNTING MODELS
# =============================================================================

class AccountingDimension(BaseModel):
    """
    Accounting Dimensions for multi-dimensional reporting
    Allows tagging transactions with Department, Project, LGA, etc.
    """
    __tablename__ = "accounting_dimensions"
    
    entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id"), nullable=False, index=True)
    
    dimension_type = Column(SQLEnum(DimensionType), nullable=False)
    code = Column(String(50), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("accounting_dimensions.id"), nullable=True)
    
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    extra_data = Column(JSON, nullable=True)  # Additional dimension-specific data
    
    # Relationships
    entity = relationship("BusinessEntity", back_populates="dimensions")
    parent = relationship("AccountingDimension", remote_side="AccountingDimension.id")
    
    __table_args__ = (
        UniqueConstraint('entity_id', 'dimension_type', 'code', name='uq_dimension_entity_type_code'),
        Index('ix_dimension_entity_type', 'entity_id', 'dimension_type'),
    )


class TransactionDimension(BaseModel):
    """
    Links transactions to accounting dimensions for multi-dimensional analysis
    """
    __tablename__ = "transaction_dimensions"
    
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False)
    dimension_id = Column(UUID(as_uuid=True), ForeignKey("accounting_dimensions.id"), nullable=False)
    
    allocation_percentage = Column(Numeric(5, 2), default=100.00)  # For split allocations
    allocated_amount = Column(Numeric(18, 2), nullable=True)
    
    __table_args__ = (
        UniqueConstraint('transaction_id', 'dimension_id', name='uq_transaction_dimension'),
        Index('ix_txn_dim_transaction', 'transaction_id'),
        Index('ix_txn_dim_dimension', 'dimension_id'),
    )


# =============================================================================
# 3-WAY MATCHING MODELS
# =============================================================================

class PurchaseOrder(BaseModel):
    """
    Purchase Order for 3-way matching
    Links: PO -> GRN -> Invoice

    Finding 50 (docs/FINDING_50_SCOPE.md): this model previously declared wht_amount/currency/
    terms_and_conditions/matching_status, none of which existed on the live table
    (alembic/versions/20260106_1600_advanced_accounting.py:102-121) and none of which had any real
    reference anywhere in the codebase. Conversely, delivery_address/payment_terms existed on the
    live table but not the model, despite app/services/three_way_matching.py's only real
    construction site (create_purchase_order) already passing both -- confirmed crashing with
    TypeError on every call before this fix.
    """
    __tablename__ = "purchase_orders"

    entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id"), nullable=False, index=True)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False)

    po_number = Column(String(50), nullable=False)
    po_date = Column(Date, nullable=False, default=date.today)
    expected_delivery_date = Column(Date, nullable=True)
    delivery_address = Column(Text, nullable=True)
    payment_terms = Column(String(200), nullable=True)

    subtotal = Column(Numeric(20, 2), nullable=False, default=0)
    vat_amount = Column(Numeric(20, 2), nullable=False, default=0)
    total_amount = Column(Numeric(20, 2), nullable=False, default=0)

    notes = Column(Text, nullable=True)

    status = Column(String(50), default="draft")  # draft, sent, acknowledged, fulfilled, cancelled

    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    approved_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    
    # Relationships
    entity = relationship("BusinessEntity")
    vendor = relationship("Vendor")
    items = relationship("PurchaseOrderItem", back_populates="purchase_order", cascade="all, delete-orphan")
    grns = relationship("GoodsReceivedNote", back_populates="purchase_order")
    
    __table_args__ = (
        UniqueConstraint('entity_id', 'po_number', name='uq_po_entity_number'),
        Index('ix_po_vendor', 'vendor_id'),
        Index('ix_po_status', 'status'),
    )


class PurchaseOrderItem(BaseModel):
    """
    Individual line items in a Purchase Order

    Finding 50 (docs/FINDING_50_SCOPE.md): this model previously declared item_code/description/
    subtotal/vat_rate/total/received_quantity/invoiced_quantity, none of which existed on the live
    table (alembic/versions/20260106_1600_advanced_accounting.py:128-139) and none of which had any
    real reference anywhere in the codebase. app/services/three_way_matching.py's only real
    construction site already used the live table's actual column names
    (item_description/line_total/gl_account_code) directly, meaning every call crashed with
    TypeError before this fix. Model migrated to match the DB (option (B)).
    """
    __tablename__ = "purchase_order_items"

    purchase_order_id = Column(UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False)
    inventory_item_id = Column(UUID(as_uuid=True), ForeignKey("inventory_items.id"), nullable=True)

    item_description = Column(String(500), nullable=False)
    quantity = Column(Numeric(15, 4), nullable=False)
    unit_price = Column(Numeric(20, 4), nullable=False)
    unit_of_measure = Column(String(50), nullable=True)

    vat_amount = Column(Numeric(20, 2), default=0, nullable=False)
    line_total = Column(Numeric(20, 2), nullable=False)
    gl_account_code = Column(String(20), nullable=True)

    purchase_order = relationship("PurchaseOrder", back_populates="items")


class GoodsReceivedNote(BaseModel):
    """
    Goods Received Note (GRN) for 3-way matching
    """
    __tablename__ = "goods_received_notes"
    
    entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id"), nullable=False, index=True)
    purchase_order_id = Column(UUID(as_uuid=True), ForeignKey("purchase_orders.id"), nullable=False)
    
    grn_number = Column(String(50), nullable=False)
    received_date = Column(Date, nullable=False, default=date.today)
    
    delivery_note_number = Column(String(100), nullable=True)
    received_by = Column(String(255), nullable=True)
    warehouse_location = Column(String(255), nullable=True)
    
    notes = Column(Text, nullable=True)
    status = Column(String(20), default="draft")  # draft, confirmed, partial, complete
    
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Relationships
    purchase_order = relationship("PurchaseOrder", back_populates="grns")
    items = relationship("GoodsReceivedNoteItem", back_populates="grn", cascade="all, delete-orphan")
    
    __table_args__ = (
        UniqueConstraint('entity_id', 'grn_number', name='uq_grn_entity_number'),
    )


class GoodsReceivedNoteItem(BaseModel):
    """Individual line items in a GRN"""
    __tablename__ = "goods_received_note_items"
    
    grn_id = Column(UUID(as_uuid=True), ForeignKey("goods_received_notes.id", ondelete="CASCADE"), nullable=False)
    po_item_id = Column(UUID(as_uuid=True), ForeignKey("purchase_order_items.id"), nullable=False)
    
    quantity_received = Column(Numeric(18, 4), nullable=False)
    quantity_rejected = Column(Numeric(18, 4), default=0)
    rejection_reason = Column(Text, nullable=True)
    
    batch_number = Column(String(100), nullable=True)
    serial_numbers = Column(ARRAY(String), nullable=True)
    expiry_date = Column(Date, nullable=True)
    
    inspection_notes = Column(Text, nullable=True)
    
    grn = relationship("GoodsReceivedNote", back_populates="items")


class ThreeWayMatch(BaseModel):
    """
    3-Way Matching Record linking PO, GRN, and Invoice

    Finding 50 (docs/FINDING_50_SCOPE.md): grn_amount/quantity_variance/price_variance/
    variance_percentage/price_tolerance/quantity_tolerance/auto_approved/auto_approved_at/
    manual_override/override_reason/override_by_id/override_at/payment_authorized/
    payment_authorized_at/payment_due_date below were removed - none exist on the live table and
    none had any other reference anywhere in the codebase (ThreeWayMatchingService, the only real
    caller, has never used them). grn_quantity/discrepancies/resolution_notes added - all three
    already existed on the live table and are exactly what the service actually writes/reads, but
    were never declared here.
    """
    __tablename__ = "three_way_matches"

    entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id"), nullable=False, index=True)

    purchase_order_id = Column(UUID(as_uuid=True), ForeignKey("purchase_orders.id"), nullable=False)
    grn_id = Column(UUID(as_uuid=True), ForeignKey("goods_received_notes.id"), nullable=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False)

    status = Column(SQLEnum(MatchingStatus), default=MatchingStatus.PENDING, nullable=False)

    # Matching details
    po_amount = Column(Numeric(20, 2), nullable=False)
    grn_quantity = Column(Numeric(15, 4), nullable=True)
    invoice_amount = Column(Numeric(20, 2), nullable=False)
    discrepancies = Column(JSON, nullable=True)

    matched_at = Column(DateTime, nullable=True)

    # Resolution
    resolved_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    resolution_notes = Column(Text, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index('ix_3way_entity_status', 'entity_id', 'status'),
    )


# =============================================================================
# WHT CREDIT NOTE VAULT
# =============================================================================

class WHTCreditNote(BaseModel):
    """
    WHT Credit Note Vault
    Tracks Withholding Tax credit notes and matches against receivables

    Finding 50 (docs/FINDING_50_SCOPE.md): expiry_date/matched_transaction_id/matched_by_id/
    applied_amount/applied_to_period/document_url/document_verified/notes below were removed -
    confirmed zero references anywhere in the codebase, and none exist on the live table.
    expires_at/applied_tax_reference/received_at/created_by_id added - all four already existed on
    the live table and are exactly what WHTCreditVaultService actually writes/reads (using those
    real names, not the removed ones), but were never declared here. Needed zero migration - the
    database was already correct.
    """
    __tablename__ = "wht_credit_notes"

    entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id"), nullable=False, index=True)

    # Credit note details
    credit_note_number = Column(String(100), nullable=False)
    issue_date = Column(Date, nullable=False)
    expires_at = Column(DateTime, nullable=True)  # WHT credits expire after 6 years

    # Issuer (client who withheld tax)
    issuer_name = Column(String(300), nullable=False)
    issuer_tin = Column(String(20), nullable=False)
    issuer_address = Column(Text, nullable=True)

    # Amounts
    gross_amount = Column(Numeric(20, 2), nullable=False)  # Original invoice amount
    wht_rate = Column(Numeric(5, 2), nullable=False)  # WHT rate applied
    wht_amount = Column(Numeric(20, 2), nullable=False)  # WHT deducted

    # Classification
    wht_type = Column(String(50), nullable=False)  # professional, contract, rent, dividend, etc.
    tax_year = Column(Integer, nullable=False)

    # Status tracking
    status = Column(SQLEnum(WHTCreditStatus), default=WHTCreditStatus.PENDING, nullable=False)

    # Matching
    matched_invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True)
    matched_at = Column(DateTime, nullable=True)

    # Application to tax liability
    applied_tax_reference = Column(String(100), nullable=True)
    applied_at = Column(DateTime, nullable=True)
    applied_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    received_at = Column(DateTime, nullable=True)
    description = Column(Text, nullable=True)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    
    __table_args__ = (
        UniqueConstraint('entity_id', 'credit_note_number', 'issuer_tin', name='uq_wht_credit_note'),
        Index('ix_wht_entity_status', 'entity_id', 'status'),
        Index('ix_wht_issuer_tin', 'issuer_tin'),
    )


# =============================================================================
# BUDGET MANAGEMENT
# =============================================================================

class Budget(BaseModel):
    """
    Budget definition for Budget vs Actual analysis

    Supports:
    - Multiple period types (monthly, quarterly, annual)
    - Version control with revision tracking
    - Approval workflow integration
    - Forecasting with actuals rollover

    Finding 50 (docs/FINDING_50_SCOPE.md): description/total_revenue_budget/total_expense_budget/
    total_capex_budget below were already correctly declared here, but didn't exist on the live
    table at all (which had notes/total_revenue/total_expense instead, no capex concept) until
    alembic/versions/20260920_0731_backfill_budgets_column_drift.py added and backfilled them - the
    database was migrated to match this model and budget_service.py, not the other way around,
    since both already consistently used these names. The old notes/total_revenue/total_expense
    columns still exist, unmapped, pending a later cleanup migration.
    """
    __tablename__ = "budgets"
    
    entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id"), nullable=False, index=True)
    
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    fiscal_year = Column(Integer, nullable=False)
    period_type = Column(SQLEnum(BudgetPeriodType), default=BudgetPeriodType.MONTHLY)
    
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    
    total_revenue_budget = Column(Numeric(18, 2), default=0)
    total_expense_budget = Column(Numeric(18, 2), default=0)
    total_capex_budget = Column(Numeric(18, 2), default=0)
    
    status = Column(String(50), default="draft")  # draft, pending_approval, approved, active, locked, closed
    approved_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # =========================================================================
    # REVISION TRACKING
    # =========================================================================
    version = Column(Integer, default=1, nullable=False, comment="Budget revision version")
    parent_budget_id = Column(UUID(as_uuid=True), ForeignKey("budgets.id"), nullable=True,
        comment="Previous version of this budget (for revision chain)")
    revision_reason = Column(Text, nullable=True, comment="Reason for revision")
    revision_date = Column(DateTime, nullable=True, comment="When revision was created")
    is_current_version = Column(Boolean, default=True, comment="Is this the active version")
    
    # =========================================================================
    # APPROVAL WORKFLOW INTEGRATION
    # =========================================================================
    approval_workflow_id = Column(UUID(as_uuid=True), ForeignKey("approval_workflows.id"), nullable=True,
        comment="Linked approval workflow for this budget")
    approval_request_id = Column(UUID(as_uuid=True), ForeignKey("approval_requests.id"), nullable=True,
        comment="Current approval request if pending")
    required_approvers = Column(Integer, default=1, comment="Number of approvals required")
    current_approvals = Column(Integer, default=0, comment="Current approval count")
    approval_notes = Column(JSON, nullable=True, comment="History of approval comments")
    
    # =========================================================================
    # FORECASTING SUPPORT
    # =========================================================================
    is_forecast = Column(Boolean, default=False, comment="Is this a forecast vs original budget")
    base_budget_id = Column(UUID(as_uuid=True), ForeignKey("budgets.id"), nullable=True,
        comment="Original budget this forecast is based on")
    forecast_method = Column(String(50), nullable=True,
        comment="Method: rolling, year-to-go, full-year. Determines how forecast is calculated")
    last_forecast_date = Column(Date, nullable=True, comment="Date of last forecast update")
    actuals_through_date = Column(Date, nullable=True, 
        comment="Date through which actuals are included in forecast")
    
    # =========================================================================
    # VARIANCE THRESHOLDS
    # =========================================================================
    variance_threshold_pct = Column(Numeric(5, 2), default=10.00,
        comment="Alert if variance exceeds this % of budget")
    variance_threshold_amt = Column(Numeric(18, 2), nullable=True,
        comment="Alert if variance exceeds this absolute amount")
    
    # =========================================================================
    # CURRENCY (FOR MULTI-CURRENCY BUDGETS)
    # =========================================================================
    currency = Column(String(3), default="NGN", comment="Budget currency")
    exchange_rate_date = Column(Date, nullable=True, comment="Rate date for multi-currency conversion")
    
    # Relationships
    line_items = relationship("BudgetLineItem", back_populates="budget", cascade="all, delete-orphan",
        foreign_keys="BudgetLineItem.budget_id")
    periods = relationship("BudgetPeriod", back_populates="budget", cascade="all, delete-orphan")
    
    __table_args__ = (
        UniqueConstraint('entity_id', 'fiscal_year', 'name', 'version', name='uq_budget_entity_year_name_ver'),
        Index('ix_budget_entity_year', 'entity_id', 'fiscal_year'),
        Index('ix_budget_status', 'status'),
        Index('ix_budget_current_version', 'entity_id', 'is_current_version'),
    )


class BudgetPeriod(BaseModel):
    """
    Individual budget periods for flexible period support.
    
    Allows:
    - Monthly, quarterly, or custom periods
    - Period-level forecasting
    - Period-level locking
    """
    __tablename__ = "budget_periods"

    # Present on the live table (alembic/versions/20260127_1100_add_budget_period_revision_fields.py)
    # but never declared on this model — Finding 49. Nullable, no ON DELETE action in the migration.
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    budget_id = Column(UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False)
    
    period_number = Column(Integer, nullable=False, comment="Period sequence (1-12 for monthly, 1-4 for quarterly)")
    period_name = Column(String(50), nullable=False, comment="E.g., 'January 2026', 'Q1 2026'")
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    
    # Period-level amounts (summary)
    budgeted_revenue = Column(Numeric(18, 2), default=0)
    budgeted_expense = Column(Numeric(18, 2), default=0)
    budgeted_capex = Column(Numeric(18, 2), default=0)
    budgeted_net_income = Column(Numeric(18, 2), default=0)
    
    # Actuals (updated as transactions post)
    actual_revenue = Column(Numeric(18, 2), default=0)
    actual_expense = Column(Numeric(18, 2), default=0)
    actual_capex = Column(Numeric(18, 2), default=0)
    actual_net_income = Column(Numeric(18, 2), default=0)
    
    # Forecast (may differ from original budget)
    forecast_revenue = Column(Numeric(18, 2), nullable=True)
    forecast_expense = Column(Numeric(18, 2), nullable=True)
    forecast_capex = Column(Numeric(18, 2), nullable=True)
    forecast_net_income = Column(Numeric(18, 2), nullable=True)
    
    # Variance
    revenue_variance = Column(Numeric(18, 2), default=0, comment="Actual - Budget")
    expense_variance = Column(Numeric(18, 2), default=0)
    revenue_variance_pct = Column(Numeric(8, 4), default=0, comment="Variance as % of budget")
    expense_variance_pct = Column(Numeric(8, 4), default=0)
    
    # Status
    is_locked = Column(Boolean, default=False, comment="Prevent further changes to this period")
    is_closed = Column(Boolean, default=False, comment="Period has been closed for reporting")
    last_actuals_sync = Column(DateTime, nullable=True, comment="When actuals were last synced")
    
    budget = relationship("Budget", back_populates="periods")
    
    __table_args__ = (
        UniqueConstraint('budget_id', 'period_number', name='uq_budget_period'),
        Index('ix_budget_period_dates', 'start_date', 'end_date'),
    )


class BudgetLineItem(BaseModel):
    """
    Individual budget line items by category/account
    
    Supports both fixed monthly columns and flexible period allocations
    """
    __tablename__ = "budget_line_items"
    
    budget_id = Column(UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True)
    dimension_id = Column(UUID(as_uuid=True), ForeignKey("accounting_dimensions.id"), nullable=True)
    
    account_code = Column(String(50), nullable=True)
    account_name = Column(String(255), nullable=False)
    line_type = Column(String(20), nullable=False)  # revenue, expense, capex
    
    # GL Account linkage for variance analysis
    gl_account_id = Column(UUID(as_uuid=True), ForeignKey("chart_of_accounts.id"), nullable=True,
        comment="Link to GL account for automatic variance calculation")
    
    # Monthly allocations (for monthly budgets)
    jan_amount = Column(Numeric(18, 2), default=0)
    feb_amount = Column(Numeric(18, 2), default=0)
    mar_amount = Column(Numeric(18, 2), default=0)
    apr_amount = Column(Numeric(18, 2), default=0)
    may_amount = Column(Numeric(18, 2), default=0)
    jun_amount = Column(Numeric(18, 2), default=0)
    jul_amount = Column(Numeric(18, 2), default=0)
    aug_amount = Column(Numeric(18, 2), default=0)
    sep_amount = Column(Numeric(18, 2), default=0)
    oct_amount = Column(Numeric(18, 2), default=0)
    nov_amount = Column(Numeric(18, 2), default=0)
    dec_amount = Column(Numeric(18, 2), default=0)
    
    total_budget = Column(Numeric(18, 2), default=0)
    
    # Flexible period allocations (JSON for quarterly/custom periods)
    period_allocations = Column(JSON, nullable=True,
        comment="Flexible allocations: {'Q1': 100000, 'Q2': 150000, ...} or {'P1': 50000, 'P2': 75000, ...}")
    
    # Actual amounts (updated as transactions post)
    jan_actual = Column(Numeric(18, 2), default=0)
    feb_actual = Column(Numeric(18, 2), default=0)
    mar_actual = Column(Numeric(18, 2), default=0)
    apr_actual = Column(Numeric(18, 2), default=0)
    may_actual = Column(Numeric(18, 2), default=0)
    jun_actual = Column(Numeric(18, 2), default=0)
    jul_actual = Column(Numeric(18, 2), default=0)
    aug_actual = Column(Numeric(18, 2), default=0)
    sep_actual = Column(Numeric(18, 2), default=0)
    oct_actual = Column(Numeric(18, 2), default=0)
    nov_actual = Column(Numeric(18, 2), default=0)
    dec_actual = Column(Numeric(18, 2), default=0)
    
    total_actual = Column(Numeric(18, 2), default=0)
    
    # Variance fields
    total_variance = Column(Numeric(18, 2), default=0, comment="Actual - Budget (negative = under budget)")
    variance_pct = Column(Numeric(8, 4), default=0, comment="Variance as % of budget")
    is_favorable = Column(Boolean, nullable=True, comment="True if variance is favorable")
    
    # Forecasting
    forecast_amount = Column(Numeric(18, 2), nullable=True, comment="Year-end forecast")
    forecast_variance = Column(Numeric(18, 2), nullable=True, comment="Forecast vs Budget variance")
    
    notes = Column(Text, nullable=True)
    
    budget = relationship("Budget", back_populates="line_items", foreign_keys=[budget_id])
    
    __table_args__ = (
        Index('ix_budget_item_budget', 'budget_id'),
        Index('ix_budget_item_account', 'account_code'),
        Index('ix_budget_item_gl', 'gl_account_id'),
    )


# =============================================================================
# M-OF-N APPROVAL WORKFLOWS
# =============================================================================

class ApprovalWorkflow(BaseModel):
    """
    Configurable M-of-N approval workflow definitions

    Finding 50 (docs/FINDING_50_SCOPE.md): this model previously declared trigger_type/
    trigger_condition/total_approvers/approval_timeout_hours/priority/required_approvals, none of
    which exist on the live table (confirmed via \\d approval_workflows) - the real columns are
    workflow_type/threshold_amount/escalation_hours/required_approvers, and
    ApprovalWorkflowService.create_workflow (app/services/approval_workflow.py) already
    constructs this model using exactly those real names, meaning workflow creation was
    completely broken (TypeError on every call) before this fix, not just missing FKs.
    trigger_condition/total_approvers/approval_timeout_hours/priority had zero other references
    anywhere in the codebase - removed rather than kept as unused phantom columns.
    """
    __tablename__ = "approval_workflows"

    entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id"), nullable=False, index=True)

    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # What triggers this workflow
    workflow_type = Column(String(50), nullable=False)  # budget, expense_claim, fx_exposure_hedge, etc.
    # (a real index, ix_approval_workflows_type, already exists on this column in the live DB -
    # not re-declared here via index=True to avoid a naming-convention mismatch; see Finding 50 notes)
    threshold_amount = Column(Numeric(20, 2), nullable=True)
    escalation_hours = Column(Integer, nullable=True)

    # M-of-N configuration
    required_approvers = Column(Integer, nullable=False, default=1)  # M

    is_active = Column(Boolean, default=True, nullable=False)

    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    
    # Relationships
    approvers = relationship("ApprovalWorkflowApprover", back_populates="workflow", cascade="all, delete-orphan")


class ApprovalWorkflowApprover(BaseModel):
    """
    Approvers assigned to a workflow

    Finding 50 (docs/FINDING_50_SCOPE.md): this model previously declared `approver_level`, a
    column that never existed on the live table under any name (confirmed: not referenced
    anywhere else in the codebase, safe to rename rather than add as a redundant duplicate) - the
    real column is `approval_order`. `role`/`is_required`/`delegated_from_id`/`delegation_expires`
    all already existed on the live table (including a real FK constraint on
    delegated_from_id) but were never declared here at all.
    """
    __tablename__ = "approval_workflow_approvers"

    workflow_id = Column(UUID(as_uuid=True), ForeignKey("approval_workflows.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    role = Column(String(50), nullable=True)
    approval_order = Column(Integer, default=1, nullable=False)  # For sequential approvals
    can_delegate = Column(Boolean, default=False, nullable=False)
    is_required = Column(Boolean, default=False, nullable=False)
    delegated_from_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    delegation_expires = Column(DateTime, nullable=True)

    workflow = relationship("ApprovalWorkflow", back_populates="approvers")


class ApprovalRequest(BaseModel):
    """
    Individual approval requests created when workflow is triggered

    Finding 50 (docs/FINDING_50_SCOPE.md): resource_data/requested_by_id/requested_at/
    required_approvals/current_approvals/current_rejections/notes below were removed - confirmed
    zero references anywhere in the codebase, and none exist on the live table.
    amount/submitted_by_id/context added - all three already existed on the live table and are
    exactly what ApprovalWorkflowService.submit_for_approval actually writes, but were never
    declared here. Needed zero migration for these three - the database was already correct.
    """
    __tablename__ = "approval_requests"

    entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id"), nullable=False, index=True)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("approval_workflows.id"), nullable=False)

    # What needs approval
    resource_type = Column(String(100), nullable=False)  # payment, purchase_order, etc.
    resource_id = Column(UUID(as_uuid=True), nullable=False)
    amount = Column(Numeric(20, 2), nullable=True)

    status = Column(SQLEnum(ApprovalStatus), default=ApprovalStatus.PENDING, nullable=False)
    submitted_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    context = Column(JSON, nullable=True)  # Snapshot of resource at request time

    expires_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    # workflow: ApprovalWorkflowService.approve() eager-loads this (selectinload) and it never
    # existed on this model at all - AttributeError on every real call, unrelated to the Finding 50
    # column drift above, found while writing a regression test for it.
    workflow = relationship("ApprovalWorkflow")
    decisions = relationship("ApprovalDecision", back_populates="request", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('ix_approval_request_resource', 'resource_type', 'resource_id'),
        Index('ix_approval_request_status', 'status'),
    )


class ApprovalDecision(BaseModel):
    """
    Individual approval/rejection decisions

    Finding 50 (docs/FINDING_50_SCOPE.md): signature_hash/ip_address/user_agent below were
    removed - confirmed zero references anywhere in the codebase, and none exist on the live
    table. Separately, this table is missing both created_at and updated_at at the DB level (its
    original migration only declared decided_at) - see the accompanying migration.
    """
    __tablename__ = "approval_decisions"

    request_id = Column(UUID(as_uuid=True), ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False)
    approver_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    decision = Column(String(20), nullable=False)  # approved, rejected
    decided_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    comments = Column(Text, nullable=True)

    request = relationship("ApprovalRequest", back_populates="decisions")
    
    __table_args__ = (
        UniqueConstraint('request_id', 'approver_id', name='uq_approval_decision_request_approver'),
    )


# =============================================================================
# IMMUTABLE LEDGER (HASH CHAIN)
# =============================================================================

class LedgerEntry(BaseModel):
    """
    Immutable ledger entries with hash chain for audit integrity
    Every financial transaction creates an entry here that cannot be modified

    Finding 50 (docs/FINDING_50_SCOPE.md): every column below except entity_id/entry_type/
    entry_hash/previous_hash was missing from the live table until
    alembic/versions/20260920_0617_backfill_ledger_entries_column_drift.py added and backfilled
    them - the original migration built a completely different, generic audit-log shape
    (resource_type/resource_id/action/data_snapshot/user_id/ip_address, none of which this model or
    ImmutableLedgerService ever used) instead of the hash-chained ledger this model and its only
    real caller already agreed on. Those old columns still exist on the table (unused by this model
    going forward) pending a later cleanup migration. created_by_id is nullable, not the model's
    original NOT NULL, because it backfills from the old user_id column which was itself nullable.
    """
    __tablename__ = "ledger_entries"

    entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id"), nullable=False, index=True)

    # Sequence number for ordering
    sequence_number = Column(BigInteger, nullable=False)
    
    # Entry details
    entry_type = Column(String(50), nullable=False)  # transaction, adjustment, opening_balance, etc.
    source_type = Column(String(50), nullable=False)  # invoice, payment, journal, etc.
    source_id = Column(UUID(as_uuid=True), nullable=False)
    
    # Financial data
    account_code = Column(String(50), nullable=True)
    debit_amount = Column(Numeric(18, 2), default=0)
    credit_amount = Column(Numeric(18, 2), default=0)
    balance = Column(Numeric(18, 2), nullable=True)
    
    currency = Column(String(3), default="NGN")
    
    # Entry metadata
    entry_date = Column(Date, nullable=False)
    description = Column(Text, nullable=True)
    reference = Column(String(100), nullable=True)
    
    # User tracking
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Hash chain for immutability
    previous_hash = Column(String(64), nullable=True)  # Hash of previous entry
    entry_hash = Column(String(64), nullable=False)  # Hash of this entry
    
    # Verification
    is_verified = Column(Boolean, default=False)
    verified_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        UniqueConstraint('entity_id', 'sequence_number', name='uq_ledger_entity_sequence'),
        Index('ix_ledger_entry_date', 'entry_date'),
        Index('ix_ledger_source', 'source_type', 'source_id'),
    )


# =============================================================================
# CONSOLIDATION (MULTI-ENTITY)
# =============================================================================

class EntityGroup(BaseModel):
    """
    Parent-subsidiary relationships for consolidation
    """
    __tablename__ = "entity_groups"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)

    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # Finding 50 (docs/FINDING_50_SCOPE.md): this column and fiscal_year_end_month below did not
    # exist on the live table until alembic/versions/20260919_2124_add_missing_columns_to_entity_groups.py
    # added them. nullable=True here (not the originally-intended NOT NULL) because a data-driven
    # backfill can't invent a parent for a zero-member group, and this environment can't confirm no
    # such group exists in production - see that migration's docstring. Tighten to NOT NULL (both
    # here and at the DB level) once that's verified.
    parent_entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id"), nullable=True)
    consolidation_currency = Column(String(3), default="NGN")

    fiscal_year_end_month = Column(Integer, default=12)  # December
    
    is_active = Column(Boolean, default=True)
    
    # Relationships
    members = relationship("EntityGroupMember", back_populates="group", cascade="all, delete-orphan")


class EntityGroupMember(BaseModel):
    """
    Members of an entity group for consolidation
    
    IAS 21 Currency Translation Support:
    - functional_currency: The currency of the primary economic environment
    - cumulative_translation_adjustment: Running total of translation differences (OCI)
    - last_translation_date: Date of most recent currency translation
    - last_translation_rate: Exchange rate used in most recent translation
    """
    __tablename__ = "entity_group_members"
    
    group_id = Column(UUID(as_uuid=True), ForeignKey("entity_groups.id", ondelete="CASCADE"), nullable=False)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id"), nullable=False)
    
    ownership_percentage = Column(Numeric(5, 2), default=100.00)
    consolidation_method = Column(String(20), default="full")  # full, proportional, equity
    
    is_parent = Column(Boolean, default=False)
    
    # ===========================================
    # IAS 21 CURRENCY TRANSLATION FIELDS
    # ===========================================
    functional_currency = Column(String(3), default="NGN", nullable=True, comment="Entity's functional currency")
    cumulative_translation_adjustment = Column(Numeric(18, 2), default=0, nullable=True, 
        comment="CTA - goes to OCI (Other Comprehensive Income)")
    last_translation_date = Column(Date, nullable=True, comment="Date of most recent translation")
    last_translation_rate = Column(Numeric(18, 6), nullable=True, comment="Closing rate used in last translation")
    average_rate_period = Column(Numeric(18, 6), nullable=True, comment="Average rate for income statement translation")
    
    # Translation method: current_rate (standard) or temporal (for hyperinflationary economies)
    translation_method = Column(String(20), default="current_rate", nullable=True,
        comment="IAS 21 translation method: current_rate or temporal")
    
    # Historical rate tracking for equity items
    historical_equity_rate = Column(Numeric(18, 6), nullable=True, 
        comment="Historical rate for translating equity opening balances")
    
    group = relationship("EntityGroup", back_populates="members")
    
    __table_args__ = (
        UniqueConstraint('group_id', 'entity_id', name='uq_group_member'),
    )


class IntercompanyTransaction(BaseModel):
    """
    Tracks inter-company transactions for elimination during consolidation

    Finding 50 (docs/FINDING_50_SCOPE.md): from_entity_id/to_entity_id/transaction_date/currency/
    from_transaction_id/to_transaction_id/elimination_date/notes below did not exist on the live table
    until alembic/versions/20260919_2120_backfill_intercompany_transactions_.py added and backfilled
    them from the original migration's source_entity_id/target_entity_id/source_transaction_id/
    target_transaction_id/eliminated_at/description columns, which still exist on the table (unused by
    this model going forward) pending a later cleanup migration to drop them.
    """
    __tablename__ = "intercompany_transactions"

    group_id = Column(UUID(as_uuid=True), ForeignKey("entity_groups.id"), nullable=False)

    from_entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id"), nullable=False)
    to_entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id"), nullable=False)

    transaction_date = Column(Date, nullable=False)
    transaction_type = Column(String(50), nullable=False)  # sale, purchase, loan, dividend, etc.

    amount = Column(Numeric(20, 2), nullable=False)
    currency = Column(String(3), default="NGN")
    
    # Matching
    from_transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=True)
    to_transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=True)
    
    is_eliminated = Column(Boolean, default=False)
    elimination_date = Column(Date, nullable=True)
    
    notes = Column(Text, nullable=True)
    
    __table_args__ = (
        Index('ix_interco_group', 'group_id'),
        Index('ix_interco_entities', 'from_entity_id', 'to_entity_id'),
    )


class CurrencyTranslationHistory(BaseModel):
    """
    Historical record of currency translations for foreign subsidiaries.
    
    IAS 21 Compliance:
    - Records each translation event with rates used
    - Tracks translation adjustments that go to OCI
    - Supports both current rate and temporal methods
    """
    __tablename__ = "currency_translation_history"
    
    group_id = Column(UUID(as_uuid=True), ForeignKey("entity_groups.id"), nullable=False)
    member_id = Column(UUID(as_uuid=True), ForeignKey("entity_group_members.id"), nullable=False)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id"), nullable=False)
    
    # Period information
    translation_date = Column(Date, nullable=False)
    fiscal_period_id = Column(UUID(as_uuid=True), ForeignKey("fiscal_periods.id"), nullable=True)
    
    # Currency pair
    functional_currency = Column(String(3), nullable=False, comment="Subsidiary's functional currency")
    presentation_currency = Column(String(3), nullable=False, comment="Group's presentation currency")
    
    # Exchange rates used
    closing_rate = Column(Numeric(18, 6), nullable=False, comment="Rate at balance sheet date")
    average_rate = Column(Numeric(18, 6), nullable=False, comment="Average rate for income statement")
    historical_equity_rate = Column(Numeric(18, 6), nullable=True, comment="Historical rate for equity")
    
    # Pre-translation amounts (in functional currency)
    pre_translation_assets = Column(Numeric(18, 2), default=0)
    pre_translation_liabilities = Column(Numeric(18, 2), default=0)
    pre_translation_equity = Column(Numeric(18, 2), default=0)
    pre_translation_revenue = Column(Numeric(18, 2), default=0)
    pre_translation_expenses = Column(Numeric(18, 2), default=0)
    pre_translation_net_income = Column(Numeric(18, 2), default=0)
    
    # Post-translation amounts (in presentation currency)
    post_translation_assets = Column(Numeric(18, 2), default=0)
    post_translation_liabilities = Column(Numeric(18, 2), default=0)
    post_translation_equity = Column(Numeric(18, 2), default=0)
    post_translation_revenue = Column(Numeric(18, 2), default=0)
    post_translation_expenses = Column(Numeric(18, 2), default=0)
    post_translation_net_income = Column(Numeric(18, 2), default=0)
    
    # Translation adjustments (goes to OCI)
    translation_adjustment = Column(Numeric(18, 2), default=0,
        comment="Current period translation difference")
    cumulative_translation_adjustment = Column(Numeric(18, 2), default=0,
        comment="Running total CTA balance")
    
    # Metadata
    translation_method = Column(String(20), default="current_rate")  # current_rate or temporal
    notes = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    
    __table_args__ = (
        Index('ix_translation_group_period', 'group_id', 'translation_date'),
        Index('ix_translation_entity', 'entity_id', 'translation_date'),
    )
