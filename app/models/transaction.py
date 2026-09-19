"""
Tekvwa Pro Audit - Transaction Model

Transaction model for recording income and expenses.

NTAA 2025 Compliance Features:
- Maker-Checker (SoD) for WREN expense verification
- Prevents Accountant from verifying expenses they created
- Audit trail for "before/after" category changes
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, AuditMixin

if TYPE_CHECKING:
    from app.models.entity import BusinessEntity
    from app.models.category import Category
    from app.models.vendor import Vendor


class TransactionType(str, Enum):
    """Type of transaction."""
    INCOME = "income"
    EXPENSE = "expense"


class WRENStatus(str, Enum):
    """WREN compliance status for expenses."""
    COMPLIANT = "compliant"              # Fully tax deductible
    NON_COMPLIANT = "non_compliant"      # Not tax deductible
    REVIEW_REQUIRED = "review_required"  # Needs manual review


class Transaction(BaseModel, AuditMixin):
    """
    Transaction model for recording income and expenses.
    
    Includes WREN compliance tracking for tax deductibility
    and VAT tracking for Input VAT recovery.
    """
    
    __tablename__ = "transactions"
    
    # Entity
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Type
    transaction_type: Mapped[TransactionType] = mapped_column(
        SQLEnum(TransactionType),
        nullable=False,
        index=True,
    )
    
    # Date
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    
    # ===========================================
    # MULTI-CURRENCY SUPPORT (IAS 21 COMPLIANT)
    # ===========================================
    
    # Original transaction currency
    currency: Mapped[str] = mapped_column(
        String(3),
        default="NGN",
        nullable=False,
        comment="Transaction currency code (e.g., USD, EUR, GBP, NGN)",
    )
    
    # Exchange rate at transaction date
    exchange_rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=6),
        default=Decimal("1.000000"),
        nullable=False,
        comment="Exchange rate at transaction date: 1 FC = X NGN",
    )
    
    # Exchange rate source
    exchange_rate_source: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Rate source: CBN, manual, spot, contract",
    )
    
    # Amount in original currency (may be foreign currency)
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
        comment="Transaction amount in original currency",
    )
    vat_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
        comment="VAT amount in original currency",
    )
    wht_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
        comment="Withholding Tax amount in original currency",
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
        comment="Total amount in original currency",
    )
    
    # Functional currency amounts (NGN - for financial reporting)
    functional_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
        comment="Base amount converted to NGN at booking rate",
    )
    functional_vat_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
        comment="VAT converted to NGN at booking rate",
    )
    functional_total_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
        comment="Total converted to NGN at booking rate",
    )
    
    # FX gain/loss tracking (for payment settlements)
    realized_fx_gain_loss: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
        comment="Realized FX gain/loss on settlement",
    )
    settlement_exchange_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=12, scale=6),
        nullable=True,
        comment="Exchange rate at payment/settlement",
    )
    settlement_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
        comment="Date of payment/settlement",
    )
    
    # Description
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    reference: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="External reference number",
    )
    
    # Category
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Vendor (for expenses)
    vendor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vendors.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # ===========================================
    # WREN COMPLIANCE - MAKER-CHECKER (NTAA 2025)
    # ===========================================
    
    # WREN Status (for expenses)
    wren_status: Mapped[WRENStatus] = mapped_column(
        SQLEnum(WRENStatus),
        default=WRENStatus.REVIEW_REQUIRED,
        nullable=False,
    )
    wren_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Maker-Checker Segregation of Duties
    # Maker: Person who created/uploaded the expense
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Maker: User who created this transaction",
    )
    
    # Checker: Person who verified WREN status (cannot be same as Maker)
    wren_verified_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Checker: User who verified WREN status (cannot be Maker)",
    )
    wren_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When WREN verification was performed",
    )
    
    # Original category before any changes (for audit trail)
    original_category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Original category for audit trail (if changed)",
    )
    category_change_history: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="History of category changes with before/after snapshots",
    )
    
    # VAT
    vat_recoverable: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="True if Input VAT can be recovered",
    )
    
    # WHT fields for tracking
    wht_service_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Service type for WHT calculation (e.g., professional_services, consultancy)",
    )
    wht_payee_type: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Payee type: individual or company",
    )
    
    # Attachments
    receipt_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Recurring
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recurring_frequency: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="monthly, quarterly, annually",
    )
    
    # Relationships
    entity: Mapped["BusinessEntity"] = relationship(
        "BusinessEntity",
        back_populates="transactions",
    )
    category: Mapped[Optional["Category"]] = relationship(
        "Category",
        back_populates="transactions",
    )
    vendor: Mapped[Optional["Vendor"]] = relationship(
        "Vendor",
        back_populates="transactions",
    )
    
    @property
    def is_expense(self) -> bool:
        return self.transaction_type == TransactionType.EXPENSE
    
    @property
    def is_income(self) -> bool:
        return self.transaction_type == TransactionType.INCOME
    
    @property
    def is_foreign_currency(self) -> bool:
        """Check if transaction is in foreign currency."""
        return self.currency != "NGN"
    
    @property
    def is_tax_deductible(self) -> bool:
        """Check if expense is tax deductible (WREN compliant)."""
        return self.wren_status == WRENStatus.COMPLIANT
    
    @property
    def is_settled(self) -> bool:
        """Check if transaction has been settled/paid."""
        return self.settlement_date is not None
    
    def __repr__(self) -> str:
        return f"<Transaction(id={self.id}, type={self.transaction_type}, amount={self.amount})>"
