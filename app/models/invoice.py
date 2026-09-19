"""
Tekvwa Pro Audit - Invoice Model

Invoice model for sales invoices with NRS e-invoicing support.

NTAA 2025 Compliance Features:
- 72-Hour Legal Lock: Once submitted to NRS, invoices cannot be edited
- Only Owner can cancel NRS submissions during the 72-hour window
- Credit Notes required for any post-submission modifications
- NRS cryptographic stamp and IRN storage for audit compliance
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, AuditMixin

if TYPE_CHECKING:
    from app.models.entity import BusinessEntity
    from app.models.customer import Customer


class InvoiceStatus(str, Enum):
    """Invoice status workflow."""
    DRAFT = "draft"           # Not yet finalized
    PENDING = "pending"       # Awaiting NRS submission
    SUBMITTED = "submitted"   # Submitted to NRS
    ACCEPTED = "accepted"     # Accepted by NRS
    REJECTED = "rejected"     # Rejected by NRS or buyer
    DISPUTED = "disputed"     # Under dispute (72-hour window)
    CANCELLED = "cancelled"   # Cancelled
    PAID = "paid"             # Payment received
    PARTIALLY_PAID = "partially_paid"

class BuyerStatus(str, Enum):
    """Buyer confirmation status (72-hour window)."""
    PENDING = "pending"              # Awaiting buyer response
    ACCEPTED = "accepted"            # Buyer accepted the invoice
    AUTO_ACCEPTED = "auto_accepted"  # Auto-accepted (72-hour window expired)
    REJECTED = "rejected"            # Buyer rejected the invoice

class VATTreatment(str, Enum):
    """VAT treatment for invoice."""
    STANDARD = "standard"      # 7.5% VAT
    ZERO_RATED = "zero_rated"  # 0% VAT
    EXEMPT = "exempt"          # VAT exempt


class Invoice(BaseModel, AuditMixin):
    """
    Invoice model for sales invoices.
    
    Supports NRS e-invoicing with IRN generation and QR codes.
    """
    
    __tablename__ = "invoices"
    
    # Entity
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Invoice Number
    invoice_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    
    # Customer
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Dates
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    # ===========================================
    # MULTI-CURRENCY SUPPORT (IAS 21 COMPLIANT)
    # ===========================================
    
    # Currency of the invoice (original transaction currency)
    currency: Mapped[str] = mapped_column(
        String(3),
        default="NGN",
        nullable=False,
        comment="Invoice currency code (e.g., USD, EUR, GBP, NGN)",
    )
    
    # Exchange rate at invoice date (foreign currency to NGN)
    exchange_rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=6),
        default=Decimal("1.000000"),
        nullable=False,
        comment="Exchange rate at invoice date: 1 FC = X NGN",
    )
    
    # Exchange rate source
    exchange_rate_source: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Rate source: CBN, manual, spot, contract",
    )
    
    # Amounts in original currency (FC = Foreign Currency)
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        comment="Subtotal in invoice currency",
    )
    vat_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        comment="VAT in invoice currency",
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        comment="Discount in invoice currency",
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        comment="Total in invoice currency",
    )
    amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        comment="Amount paid in invoice currency",
    )
    
    # Functional currency amounts (NGN - for financial reporting)
    functional_subtotal: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
        comment="Subtotal converted to NGN at booking rate",
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
    functional_amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
        comment="Amount paid converted to NGN (may differ due to FX gain/loss)",
    )
    
    # FX gain/loss tracking
    realized_fx_gain_loss: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
        comment="Realized FX gain/loss on payments received",
    )
    unrealized_fx_gain_loss: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
        comment="Unrealized FX gain/loss at reporting date",
    )
    last_revaluation_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
        comment="Last FX revaluation date for this invoice",
    )
    last_revaluation_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=12, scale=6),
        nullable=True,
        comment="Exchange rate used in last revaluation",
    )
    
    # VAT
    vat_treatment: Mapped[VATTreatment] = mapped_column(
        SQLEnum(VATTreatment),
        default=VATTreatment.STANDARD,
        nullable=False,
    )
    vat_rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2),
        default=Decimal("7.50"),
        nullable=False,
    )
    
    # Status
    status: Mapped[InvoiceStatus] = mapped_column(
        SQLEnum(InvoiceStatus),
        default=InvoiceStatus.DRAFT,
        nullable=False,
        index=True,
    )
    
    # ===========================================
    # NRS E-INVOICING (NTAA 2025 COMPLIANT)
    # ===========================================
    
    nrs_irn: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        unique=True,
        comment="NRS Invoice Reference Number",
    )
    nrs_qr_code_data: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="QR code data from NRS",
    )
    nrs_submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    nrs_response: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Full NRS API response including cryptographic stamp",
    )
    nrs_cryptographic_stamp: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="NRS cryptographic signature for audit verification",
    )
    
    # 72-Hour Legal Lock (NTAA 2025)
    # Once submitted to NRS, invoice is locked. Only Owner can cancel.
    is_nrs_locked: Mapped[bool] = mapped_column(
        Boolean, 
        default=False, 
        nullable=False,
        comment="True when submitted to NRS - prevents editing",
    )
    nrs_lock_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="72-hour window end for buyer review",
    )
    nrs_cancelled_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_invoices_nrs_cancelled_by"),
        nullable=True,
        comment="Owner who cancelled NRS submission (if any)",
    )
    nrs_cancellation_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Reason for NRS cancellation",
    )
    
    # Dispute Tracking (72-hour window)
    dispute_deadline: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Deadline for buyer dispute",
    )
    is_disputed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dispute_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Buyer Review (72-hour NRS mandate)
    buyer_status: Mapped[Optional[BuyerStatus]] = mapped_column(
        SQLEnum(BuyerStatus),
        default=BuyerStatus.PENDING,
        nullable=True,
        comment="Buyer confirmation status (72-hour window)",
    )
    buyer_response_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When buyer responded",
    )
    
    # Credit Note Tracking
    credit_note_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("credit_notes.id", ondelete="SET NULL", name="fk_invoice_credit_note"),
        nullable=True,
        comment="Reference to credit note if rejected",
    )
    is_credit_note: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    original_invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="SET NULL", name="fk_invoice_original", use_alter=True),
        nullable=True,
        comment="Reference to original invoice if this is a credit note",
    )
    
    # B2C Real-time Reporting (24-hour NRS mandate for transactions > ₦50,000)
    is_b2c_reportable: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="True if B2C transaction > ₦50,000 threshold",
    )
    b2c_reported_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When transaction was reported to NRS",
    )
    b2c_report_reference: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="NRS B2C report reference number",
    )
    b2c_report_deadline: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="24-hour deadline for B2C reporting",
    )
    
    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    terms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # PDF
    pdf_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Relationships
    entity: Mapped["BusinessEntity"] = relationship(
        "BusinessEntity",
        back_populates="invoices",
    )
    customer: Mapped[Optional["Customer"]] = relationship(
        "Customer",
        back_populates="invoices",
    )
    line_items: Mapped[List["InvoiceLineItem"]] = relationship(
        "InvoiceLineItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
    )
    
    @property
    def balance_due(self) -> Decimal:
        """Calculate remaining balance in original currency."""
        return self.total_amount - self.amount_paid
    
    @property
    def functional_balance_due(self) -> Decimal:
        """Calculate remaining balance in functional currency (NGN)."""
        return self.functional_total_amount - self.functional_amount_paid
    
    @property
    def is_fully_paid(self) -> bool:
        """Check if invoice is fully paid."""
        return self.balance_due <= Decimal("0")
    
    @property
    def is_foreign_currency(self) -> bool:
        """Check if invoice is in foreign currency."""
        return self.currency != "NGN"
    
    @property
    def is_b2b(self) -> bool:
        """Check if this is a B2B invoice (requires NRS e-invoicing)."""
        return self.customer is not None and self.customer.is_business
    
    @property
    def needs_fx_revaluation(self) -> bool:
        """Check if invoice needs FX revaluation (foreign currency with open balance)."""
        return self.is_foreign_currency and not self.is_fully_paid
    
    def __repr__(self) -> str:
        return f"<Invoice(id={self.id}, number={self.invoice_number}, status={self.status})>"


class InvoiceLineItem(BaseModel):
    """
    Invoice line item model.
    """
    
    __tablename__ = "invoice_line_items"
    
    # Invoice
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    # Item Details
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=False,
        default=Decimal("1.00"),
    )
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    
    # Amounts
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    vat_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal("0.00"),
    )
    total: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    
    # Ordering
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Relationships
    invoice: Mapped["Invoice"] = relationship(
        "Invoice",
        back_populates="line_items",
    )
    
    def __repr__(self) -> str:
        return f"<InvoiceLineItem(id={self.id}, description={self.description[:30]}...)>"
