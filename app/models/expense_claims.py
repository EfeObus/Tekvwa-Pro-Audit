"""
Tekvwa Pro Audit - Expense Claims Model

Expense claims and reimbursement models for Nigerian businesses.
Supports:
- Employee expense claims
- Approval workflow
- Receipt attachments
- Reimbursement tracking
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
    Enum as SQLEnum, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, AuditMixin

if TYPE_CHECKING:
    from app.models.entity import BusinessEntity
    from app.models.user import User
    from app.models.payroll import Employee


class ExpenseCategory(str, Enum):
    """Expense claim categories."""
    TRAVEL = "travel"
    ACCOMMODATION = "accommodation"
    MEALS = "meals"
    TRANSPORT = "transport"
    FUEL = "fuel"
    OFFICE_SUPPLIES = "office_supplies"
    COMMUNICATION = "communication"
    TRAINING = "training"
    ENTERTAINMENT = "entertainment"
    MEDICAL = "medical"
    PROFESSIONAL_SERVICES = "professional_services"
    UTILITIES = "utilities"
    OTHER = "other"


class ClaimStatus(str, Enum):
    """Expense claim status."""
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAID = "paid"
    CANCELLED = "cancelled"


class PaymentMethod(str, Enum):
    """Reimbursement payment method."""
    BANK_TRANSFER = "bank_transfer"
    CASH = "cash"
    PAYROLL = "payroll"
    CHEQUE = "cheque"


# ===========================================
# EXPENSE CLAIM
# ===========================================

class ExpenseClaim(BaseModel, AuditMixin):
    """
    Expense claim submitted by an employee for reimbursement.
    """
    
    __tablename__ = "expense_claims"
    
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Claimant
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Claim Details
    claim_number: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True,
        comment="Unique claim reference number",
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Period
    expense_date_from: Mapped[date] = mapped_column(Date, nullable=False)
    expense_date_to: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Amounts
    currency: Mapped[str] = mapped_column(String(3), default="NGN", nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    approved_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Status
    status: Mapped[ClaimStatus] = mapped_column(
        SQLEnum(ClaimStatus),
        default=ClaimStatus.DRAFT,
        nullable=False,
        index=True,
    )
    
    # Submission
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    
    # Approval
    approved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    approval_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Rejection
    rejected_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    rejected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Payment
    payment_method: Mapped[Optional[PaymentMethod]] = mapped_column(
        SQLEnum(PaymentMethod), nullable=True,
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    payment_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Project/Cost Center
    project_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    cost_center: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Relationships
    entity: Mapped["BusinessEntity"] = relationship("BusinessEntity")
    employee: Mapped["Employee"] = relationship("Employee")
    line_items: Mapped[List["ExpenseClaimItem"]] = relationship(
        "ExpenseClaimItem",
        back_populates="claim",
        cascade="all, delete-orphan",
    )
    
    def __repr__(self) -> str:
        return f"<ExpenseClaim(id={self.id}, number={self.claim_number}, status={self.status})>"


# ===========================================
# EXPENSE CLAIM ITEM
# ===========================================

class ExpenseClaimItem(BaseModel):
    """
    Individual expense item within a claim.
    """
    
    __tablename__ = "expense_claim_items"
    
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("expense_claims.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Item Details
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    category: Mapped[ExpenseCategory] = mapped_column(
        SQLEnum(ExpenseCategory),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    vendor_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Amounts
    currency: Mapped[str] = mapped_column(String(3), default="NGN", nullable=False)
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    vat_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    approved_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Receipt
    receipt_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    receipt_file_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    has_receipt: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Tax Deductibility (for Nigerian compliance)
    is_tax_deductible: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
        comment="Whether expense is tax deductible per FIRS rules",
    )
    gl_account_code: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
        comment="GL account for expense posting",
    )
    
    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    claim: Mapped["ExpenseClaim"] = relationship(
        "ExpenseClaim", back_populates="line_items",
    )
    
    def __repr__(self) -> str:
        return f"<ExpenseClaimItem(id={self.id}, date={self.expense_date}, amount={self.amount})>"
