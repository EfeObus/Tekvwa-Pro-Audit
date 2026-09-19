"""
Tekvwa Pro Audit - Advanced Payroll Models

World-class payroll features for Nigerian enterprises:
- Compliance Status Engine with penalty estimation
- Payroll Change Impact Preview
- Exception Flags with acknowledgement
- Decision Logs (immutable)
- YTD Ledger (stored snapshots)
- Opening Balance Import
- Smart Validation (Ghost detection, variance flags)
- Cost-to-Company Analytics
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Optional, List, Dict, Any

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
    Enum as SQLEnum, JSON, UniqueConstraint, Index, func
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, AuditMixin

if TYPE_CHECKING:
    from app.models.payroll import PayrollRun, Payslip, Employee


# ===========================================
# COMPLIANCE STATUS ENUMS
# ===========================================

class ComplianceStatus(str, Enum):
    """Statutory remittance compliance status."""
    ON_TIME = "on_time"
    OVERDUE = "overdue"
    PARTIALLY_PAID = "partially_paid"
    PENALTY_RISK = "penalty_risk"
    NOT_DUE = "not_due"
    EXEMPT = "exempt"


class RemittanceType(str, Enum):
    """Types of statutory remittances."""
    PAYE = "paye"
    PENSION = "pension"
    NHF = "nhf"
    NSITF = "nsitf"
    ITF = "itf"


class ExceptionSeverity(str, Enum):
    """Exception severity levels."""
    CRITICAL = "critical"  # Blocks payroll
    WARNING = "warning"    # Requires acknowledgement
    INFO = "info"          # Informational only


class ExceptionCode(str, Enum):
    """Standardized exception codes for payroll validation."""
    # Critical
    NEGATIVE_NET_PAY = "NEGATIVE_NET_PAY"
    DUPLICATE_BVN = "DUPLICATE_BVN"
    DUPLICATE_ACCOUNT = "DUPLICATE_ACCOUNT"
    BELOW_MINIMUM_WAGE = "BELOW_MINIMUM_WAGE"
    
    # Warning
    MISSING_TIN = "MISSING_TIN"
    MISSING_PENSION_PIN = "MISSING_PENSION_PIN"
    MISSING_NHF_NUMBER = "MISSING_NHF_NUMBER"
    MISSING_BANK_ACCOUNT = "MISSING_BANK_ACCOUNT"
    ZERO_PAYE_HIGH_INCOME = "ZERO_PAYE_HIGH_INCOME"
    PENSION_BELOW_MINIMUM = "PENSION_BELOW_MINIMUM"
    LARGE_VARIANCE = "LARGE_VARIANCE"
    BANK_ACCOUNT_MISMATCH = "BANK_ACCOUNT_MISMATCH"
    
    # Info
    NEW_HIRE_PRORATION = "NEW_HIRE_PRORATION"
    EXIT_PRORATION = "EXIT_PRORATION"
    SALARY_CHANGE = "SALARY_CHANGE"
    TAX_BAND_MOVEMENT = "TAX_BAND_MOVEMENT"


class VarianceReason(str, Enum):
    """Standard variance reason codes."""
    NEW_HIRE = "new_hire"
    TERMINATION = "termination"
    SALARY_INCREASE = "salary_increase"
    SALARY_DECREASE = "salary_decrease"
    PROMOTION = "promotion"
    ALLOWANCE_CHANGE = "allowance_change"
    LOAN_REPAYMENT = "loan_repayment"
    LOAN_COMPLETED = "loan_completed"
    LEAVE_DEDUCTION = "leave_deduction"
    TAX_BAND_CHANGE = "tax_band_change"
    ARREARS_PAID = "arrears_paid"
    BONUS_PAYMENT = "bonus_payment"
    OTHER = "other"


class ProrationMode(str, Enum):
    """Proration calculation modes."""
    CALENDAR_DAYS = "calendar_days"
    WORKING_DAYS = "working_days"
    FIXED_30_DAYS = "fixed_30_days"


# ===========================================
# COMPLIANCE STATUS SNAPSHOT
# ===========================================

class ComplianceSnapshot(BaseModel):
    """
    Compliance status snapshot for statutory remittances.
    Tracks PAYE, Pension, NHF, NSITF, ITF status per period.
    """
    
    __tablename__ = "compliance_snapshots"
    
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Period
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # PAYE Status
    paye_status: Mapped[ComplianceStatus] = mapped_column(
        SQLEnum(ComplianceStatus),
        default=ComplianceStatus.NOT_DUE,
        nullable=False,
    )
    paye_amount_due: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    paye_amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    paye_due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    paye_days_overdue: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    paye_penalty_estimate: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
        comment="Estimated penalty based on FIRS guidelines",
    )
    paye_tax_state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Pension Status
    pension_status: Mapped[ComplianceStatus] = mapped_column(
        SQLEnum(ComplianceStatus),
        default=ComplianceStatus.NOT_DUE,
        nullable=False,
    )
    pension_amount_due: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    pension_amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    pension_due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    pension_days_overdue: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pension_penalty_estimate: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # NHF Status
    nhf_status: Mapped[ComplianceStatus] = mapped_column(
        SQLEnum(ComplianceStatus),
        default=ComplianceStatus.NOT_DUE,
        nullable=False,
    )
    nhf_amount_due: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    nhf_amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    nhf_due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    nhf_days_overdue: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # NSITF Status
    nsitf_status: Mapped[ComplianceStatus] = mapped_column(
        SQLEnum(ComplianceStatus),
        default=ComplianceStatus.NOT_DUE,
        nullable=False,
    )
    nsitf_amount_due: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    nsitf_amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # ITF Status
    itf_status: Mapped[ComplianceStatus] = mapped_column(
        SQLEnum(ComplianceStatus),
        default=ComplianceStatus.NOT_DUE,
        nullable=False,
    )
    itf_amount_due: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    itf_amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Total Penalty Exposure
    total_penalty_exposure: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Snapshot metadata
    snapshot_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    
    __table_args__ = (
        UniqueConstraint('entity_id', 'period_month', 'period_year', name='uq_compliance_period'),
        Index('ix_compliance_entity_period', 'entity_id', 'period_year', 'period_month'),
    )
    
    def __repr__(self) -> str:
        return f"<ComplianceSnapshot(entity={self.entity_id}, period={self.period_month}/{self.period_year})>"


# ===========================================
# PAYROLL IMPACT PREVIEW
# ===========================================

class PayrollImpactPreview(BaseModel):
    """
    Pre-approval impact summary comparing current vs previous payroll.
    Shows variance drivers before approval.
    """
    
    __tablename__ = "payroll_impact_previews"
    
    payroll_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payroll_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    
    # Previous Period Reference
    previous_payroll_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payroll_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Current Period Totals
    current_gross: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    current_net: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    current_paye: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    current_employer_cost: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    current_employee_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Previous Period Totals
    previous_gross: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    previous_net: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    previous_paye: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    previous_employer_cost: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    previous_employee_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Variance Calculations
    gross_variance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    gross_variance_percent: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    net_variance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    paye_variance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    employer_cost_variance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Variance Drivers (Top 5)
    variance_drivers: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="Top variance drivers with amounts",
    )
    
    # New Hires / Terminations
    new_hires_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_hires_cost: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    terminations_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    terminations_savings: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Human-Readable Summary
    impact_summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        comment="Human-readable impact summary",
    )
    
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    
    def __repr__(self) -> str:
        return f"<PayrollImpactPreview(payroll={self.payroll_run_id}, variance={self.gross_variance_percent}%)>"


# ===========================================
# PAYROLL EXCEPTION
# ===========================================

class PayrollException(BaseModel):
    """
    Structured exception flags for payroll validation.
    Requires acknowledgement before approval.
    """
    
    __tablename__ = "payroll_exceptions"
    
    payroll_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payroll_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    payslip_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payslips.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    
    employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Exception Details
    exception_code: Mapped[ExceptionCode] = mapped_column(
        SQLEnum(ExceptionCode),
        nullable=False,
    )
    severity: Mapped[ExceptionSeverity] = mapped_column(
        SQLEnum(ExceptionSeverity),
        nullable=False,
    )
    
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Related data
    related_field: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    current_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    expected_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Acknowledgement
    requires_acknowledgement: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )
    is_acknowledged: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    acknowledged_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    acknowledgement_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Resolution
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    
    __table_args__ = (
        Index('ix_exception_payroll_severity', 'payroll_run_id', 'severity'),
    )
    
    def __repr__(self) -> str:
        return f"<PayrollException(code={self.exception_code}, severity={self.severity})>"


# ===========================================
# PAYROLL DECISION LOG (IMMUTABLE)
# ===========================================

class PayrollDecisionLog(BaseModel):
    """
    Immutable log of payroll decisions and notes.
    Cannot be modified after payroll completion.
    """
    
    __tablename__ = "payroll_decision_logs"
    
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    payroll_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payroll_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    
    payslip_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payslips.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Log Details
    decision_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="approval, adjustment, exception_override, note",
    )
    category: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="payroll, salary, deduction, exception, approval",
    )
    
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Context
    context_data: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Relevant context for the decision",
    )
    
    # Author
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
    )
    created_by_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by_role: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    
    # Immutability flag
    is_locked: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="Locked after payroll completion",
    )
    
    # Hash for integrity
    content_hash: Mapped[str] = mapped_column(
        String(64), nullable=False,
        comment="SHA-256 hash of log content",
    )
    
    __table_args__ = (
        Index('ix_decision_log_payroll', 'payroll_run_id', 'created_at'),
    )
    
    def __repr__(self) -> str:
        return f"<PayrollDecisionLog(type={self.decision_type}, title={self.title})>"


# ===========================================
# YTD PAYROLL LEDGER
# ===========================================

class YTDPayrollLedger(BaseModel):
    """
    Year-to-date payroll ledger per employee.
    Stored snapshots for fast reporting and mid-year migrations.
    """
    
    __tablename__ = "ytd_payroll_ledgers"
    
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Tax Year
    tax_year: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # YTD Earnings
    ytd_gross: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    ytd_basic: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    ytd_housing: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    ytd_transport: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    ytd_other_earnings: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # YTD Deductions
    ytd_paye: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    ytd_pension_employee: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    ytd_nhf: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    ytd_other_deductions: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    ytd_total_deductions: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # YTD Net
    ytd_net: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # YTD Employer Contributions
    ytd_pension_employer: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    ytd_nsitf: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    ytd_itf: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Total Cost to Company
    ytd_total_employer_cost: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
        comment="Gross + all employer contributions",
    )
    
    # Months Processed
    months_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Last Updated
    last_payroll_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payroll_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    
    # Opening Balances (for migration)
    has_opening_balance: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    opening_balance_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    
    __table_args__ = (
        UniqueConstraint('entity_id', 'employee_id', 'tax_year', name='uq_ytd_employee_year'),
        Index('ix_ytd_entity_year', 'entity_id', 'tax_year'),
    )
    
    def __repr__(self) -> str:
        return f"<YTDPayrollLedger(employee={self.employee_id}, year={self.tax_year}, ytd_gross={self.ytd_gross})>"


# ===========================================
# OPENING BALANCE IMPORT
# ===========================================

class OpeningBalanceImport(BaseModel, AuditMixin):
    """
    Opening balance import for mid-year migrations from Excel/Sage.
    """
    
    __tablename__ = "opening_balance_imports"
    
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    # Import Reference
    import_batch_id: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="Batch ID for this import",
    )
    
    # Tax Year
    tax_year: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    months_covered: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Prior YTD Values
    prior_ytd_gross: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    prior_ytd_paye: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    prior_ytd_pension_employee: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    prior_ytd_pension_employer: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    prior_ytd_nhf: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    prior_ytd_net: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Source Information
    source_system: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        comment="Excel, Sage, QuickBooks, etc.",
    )
    source_file: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Verification
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    
    # Applied
    is_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    applied_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    __table_args__ = (
        UniqueConstraint('entity_id', 'employee_id', 'tax_year', name='uq_opening_balance_employee_year'),
    )
    
    def __repr__(self) -> str:
        return f"<OpeningBalanceImport(employee={self.employee_id}, year={self.tax_year})>"


# ===========================================
# PAYSLIP EXPLANATION
# ===========================================

class PayslipExplanation(BaseModel):
    """
    Human-readable payslip explanations.
    Generated from rules, not AI.
    """
    
    __tablename__ = "payslip_explanations"
    
    payslip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payslips.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    
    # Key Changes This Period
    has_changes: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Explanation Sections
    gross_explanation: Mapped[str] = mapped_column(
        Text, nullable=False, default="",
    )
    deduction_explanation: Mapped[str] = mapped_column(
        Text, nullable=False, default="",
    )
    tax_explanation: Mapped[str] = mapped_column(
        Text, nullable=False, default="",
    )
    net_explanation: Mapped[str] = mapped_column(
        Text, nullable=False, default="",
    )
    
    # Full Explanation
    full_explanation: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="Complete human-readable explanation",
    )
    
    # Variance Notes
    variance_notes: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Explanation of changes vs previous period",
    )
    
    # Generated
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    
    def __repr__(self) -> str:
        return f"<PayslipExplanation(payslip={self.payslip_id})>"


# ===========================================
# EMPLOYEE VARIANCE LOG
# ===========================================

class EmployeeVarianceLog(BaseModel):
    """
    Log of significant payroll variances requiring reason codes.
    """
    
    __tablename__ = "employee_variance_logs"
    
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    payslip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payslips.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    previous_payslip_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payslips.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Variance Details
    variance_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="gross, net, paye, pension",
    )
    previous_value: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
    )
    current_value: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
    )
    variance_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
    )
    variance_percent: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2),
        nullable=False,
    )
    
    # Reason Code (Required for >5% variance)
    reason_code: Mapped[Optional[VarianceReason]] = mapped_column(
        SQLEnum(VarianceReason),
        nullable=True,
    )
    reason_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Auto-flagged
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    flag_threshold_percent: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2),
        default=Decimal("5.00"),
        nullable=False,
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    
    def __repr__(self) -> str:
        return f"<EmployeeVarianceLog(employee={self.employee_id}, variance={self.variance_percent}%)>"


# ===========================================
# COST TO COMPANY ANALYTICS
# ===========================================

class CostToCompanySnapshot(BaseModel):
    """
    Cost-to-Company (CTC) analytics snapshot.
    True cost including all employer contributions.
    """
    
    __tablename__ = "ctc_snapshots"
    
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Period
    snapshot_month: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_year: Mapped[int] = mapped_column(Integer, nullable=False)
    
    payroll_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payroll_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Company-Wide Totals
    total_employees: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Cost Components
    total_gross_salary: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    total_pension_employer: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    total_nsitf: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    total_itf: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    total_hmo: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
        comment="Health insurance (if any)",
    )
    total_group_life: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
        comment="Group life insurance",
    )
    total_other_benefits: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Total CTC
    total_ctc: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
        comment="Total Cost to Company",
    )
    
    # Per Employee Average
    average_ctc_per_employee: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Department Breakdown
    department_breakdown: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    
    # Budget Tracking
    monthly_budget: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=True,
    )
    budget_variance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    budget_variance_percent: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    snapshot_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    
    __table_args__ = (
        UniqueConstraint('entity_id', 'snapshot_month', 'snapshot_year', name='uq_ctc_entity_period'),
    )
    
    def __repr__(self) -> str:
        return f"<CostToCompanySnapshot(entity={self.entity_id}, ctc={self.total_ctc})>"


# ===========================================
# WHAT-IF SIMULATION
# ===========================================

class WhatIfSimulation(BaseModel):
    """
    What-If simulation for payroll impact analysis.
    Helps executives see impact of changes.
    """
    
    __tablename__ = "what_if_simulations"
    
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Simulation Details
    simulation_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Scenario Type
    scenario_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="salary_increase, new_hires, terminations, tax_reform, custom",
    )
    
    # Input Parameters
    parameters: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Simulation input parameters",
    )
    
    # Current State (Baseline)
    baseline_gross: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    baseline_paye: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    baseline_employer_cost: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    baseline_ctc: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Projected State
    projected_gross: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    projected_paye: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    projected_employer_cost: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    projected_ctc: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Impact
    gross_impact: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    paye_impact: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    employer_cost_impact: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    ctc_impact: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Impact Percentages
    gross_impact_percent: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    ctc_impact_percent: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Summary
    impact_summary: Mapped[str] = mapped_column(
        Text, nullable=False, default="",
    )
    
    # Metadata
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    
    is_saved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    def __repr__(self) -> str:
        return f"<WhatIfSimulation(name={self.simulation_name}, impact={self.ctc_impact})>"


# ===========================================
# GHOST WORKER DETECTION LOG
# ===========================================

class GhostWorkerDetection(BaseModel):
    """
    Ghost worker detection log.
    Flags duplicate BVNs, account numbers, etc.
    """
    
    __tablename__ = "ghost_worker_detections"
    
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Detection Type
    detection_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="duplicate_bvn, duplicate_account, duplicate_nin, etc.",
    )
    
    # Affected Employees
    employee_1_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    employee_2_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    # Duplicate Value
    duplicate_field: Mapped[str] = mapped_column(String(50), nullable=False)
    duplicate_value: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Severity
    severity: Mapped[ExceptionSeverity] = mapped_column(
        SQLEnum(ExceptionSeverity),
        default=ExceptionSeverity.CRITICAL,
        nullable=False,
    )
    
    # Resolution
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    
    def __repr__(self) -> str:
        return f"<GhostWorkerDetection(type={self.detection_type}, field={self.duplicate_field})>"
