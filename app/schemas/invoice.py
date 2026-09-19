"""
Tekvwa Pro Audit - Invoice Schemas

Pydantic schemas for invoice management with NRS e-invoicing support.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, Field, field_validator, computed_field


class InvoiceStatus(str, Enum):
    """Invoice status workflow."""
    DRAFT = "draft"
    PENDING = "pending"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DISPUTED = "disputed"
    CANCELLED = "cancelled"
    PAID = "paid"
    PARTIALLY_PAID = "partially_paid"


class VATTreatment(str, Enum):
    """VAT treatment for invoice."""
    STANDARD = "standard"      # 7.5% VAT
    ZERO_RATED = "zero_rated"  # 0% VAT
    EXEMPT = "exempt"          # VAT exempt


# ===========================================
# LINE ITEM SCHEMAS
# ===========================================

class InvoiceLineItemCreate(BaseModel):
    """Schema for creating an invoice line item."""
    description: str = Field(..., min_length=1, max_length=500)
    quantity: float = Field(..., gt=0, description="Quantity of items")
    unit_price: float = Field(..., ge=0, description="Price per unit")
    vat_rate: float = Field(7.5, ge=0, le=100, description="VAT rate percentage")
    
    @computed_field
    @property
    def subtotal(self) -> float:
        """Calculate line subtotal before VAT."""
        return round(self.quantity * self.unit_price, 2)
    
    @computed_field
    @property
    def vat_amount(self) -> float:
        """Calculate VAT amount for line."""
        return round(self.subtotal * (self.vat_rate / 100), 2)
    
    @computed_field
    @property
    def total(self) -> float:
        """Calculate line total with VAT."""
        return round(self.subtotal + self.vat_amount, 2)


class InvoiceLineItemUpdate(BaseModel):
    """Schema for updating an invoice line item."""
    description: Optional[str] = Field(None, min_length=1, max_length=500)
    quantity: Optional[float] = Field(None, gt=0)
    unit_price: Optional[float] = Field(None, ge=0)
    vat_rate: Optional[float] = Field(None, ge=0, le=100)


class InvoiceLineItemResponse(BaseModel):
    """Schema for invoice line item response."""
    id: UUID
    description: str
    quantity: float
    unit_price: float
    subtotal: float
    vat_amount: float
    total: float
    sort_order: int
    
    class Config:
        from_attributes = True


# ===========================================
# INVOICE REQUEST SCHEMAS
# ===========================================

class InvoiceCreateRequest(BaseModel):
    """Schema for creating an invoice."""
    customer_id: Optional[UUID] = Field(None, description="Customer to invoice")
    invoice_date: date = Field(..., description="Date of invoice")
    due_date: date = Field(..., description="Payment due date")
    
    # Multi-Currency Support (IAS 21)
    currency: str = Field("NGN", min_length=3, max_length=3, description="Invoice currency code (USD, EUR, GBP, NGN)")
    exchange_rate: Optional[float] = Field(None, gt=0, description="Exchange rate at invoice date (1 FC = X NGN). Auto-fetched if not provided.")
    exchange_rate_source: Optional[str] = Field(None, description="Rate source: CBN, manual, spot, contract")
    
    # VAT Treatment
    vat_treatment: VATTreatment = VATTreatment.STANDARD
    vat_rate: float = Field(7.5, ge=0, le=100, description="VAT rate for standard treatment")
    
    # Line items
    line_items: List[InvoiceLineItemCreate] = Field(..., min_length=1)
    
    # Optional discount
    discount_amount: float = Field(0, ge=0, description="Discount amount in invoice currency")
    
    # Notes
    notes: Optional[str] = Field(None, max_length=1000)
    terms: Optional[str] = Field(None, max_length=1000)
    
    @field_validator('due_date')
    @classmethod
    def due_date_must_be_after_invoice_date(cls, v, info):
        if 'invoice_date' in info.data and v < info.data['invoice_date']:
            raise ValueError('Due date must be on or after invoice date')
        return v


class InvoiceUpdateRequest(BaseModel):
    """Schema for updating an invoice."""
    customer_id: Optional[UUID] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    
    # VAT Treatment
    vat_treatment: Optional[VATTreatment] = None
    vat_rate: Optional[float] = Field(None, ge=0, le=100)
    
    # Optional discount
    discount_amount: Optional[float] = Field(None, ge=0)
    
    # Notes
    notes: Optional[str] = Field(None, max_length=1000)
    terms: Optional[str] = Field(None, max_length=1000)


class PaymentRecordRequest(BaseModel):
    """Schema for recording a payment against an invoice."""
    amount: float = Field(..., gt=0, description="Payment amount in payment currency")
    payment_date: date = Field(..., description="Date of payment")
    payment_method: str = Field("bank_transfer", description="Payment method used")
    reference: Optional[str] = Field(None, max_length=100, description="Payment reference")
    notes: Optional[str] = Field(None, max_length=500)
    
    # Multi-Currency Payment Support
    payment_currency: Optional[str] = Field(None, min_length=3, max_length=3, description="Currency of payment (defaults to invoice currency)")
    payment_exchange_rate: Optional[float] = Field(None, gt=0, description="Exchange rate at payment date (for calculating FX gain/loss)")


class InvoiceSendRequest(BaseModel):
    """Schema for sending an invoice via email."""
    recipient_email: str = Field(..., description="Email address to send to")
    cc_emails: Optional[List[str]] = Field(None, description="CC email addresses")
    subject: Optional[str] = Field(None, description="Custom email subject")
    message: Optional[str] = Field(None, description="Custom email message")


# ===========================================
# INVOICE RESPONSE SCHEMAS
# ===========================================

class InvoiceResponse(BaseModel):
    """Schema for invoice response."""
    id: UUID
    entity_id: UUID
    invoice_number: str
    
    # Customer
    customer_id: Optional[UUID] = None
    customer_name: Optional[str] = None
    customer_tin: Optional[str] = None
    is_b2b: bool = False
    
    # Dates
    invoice_date: date
    due_date: date
    
    # Multi-Currency (IAS 21)
    currency: str = "NGN"
    exchange_rate: float = 1.0
    exchange_rate_source: Optional[str] = None
    is_foreign_currency: bool = False
    
    # Amounts in original currency
    subtotal: float
    vat_amount: float
    discount_amount: float
    total_amount: float
    amount_paid: float
    balance_due: float
    
    # Functional currency amounts (NGN)
    functional_subtotal: float = 0.0
    functional_vat_amount: float = 0.0
    functional_total_amount: float = 0.0
    functional_amount_paid: float = 0.0
    functional_balance_due: float = 0.0
    
    # FX Gain/Loss
    realized_fx_gain_loss: float = 0.0
    unrealized_fx_gain_loss: float = 0.0
    last_revaluation_date: Optional[date] = None
    last_revaluation_rate: Optional[float] = None
    needs_fx_revaluation: bool = False
    
    # VAT
    vat_treatment: str
    vat_rate: float
    
    # Status
    status: str
    is_overdue: bool = False
    
    # NRS E-Invoicing
    nrs_irn: Optional[str] = None
    nrs_qr_code_data: Optional[str] = None
    nrs_submitted_at: Optional[datetime] = None
    
    # Dispute
    dispute_deadline: Optional[datetime] = None
    is_disputed: bool = False
    dispute_reason: Optional[str] = None
    
    # Notes
    notes: Optional[str] = None
    terms: Optional[str] = None
    
    # PDF
    pdf_url: Optional[str] = None
    
    # Line items
    line_items: List[InvoiceLineItemResponse] = []
    
    # Metadata
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class InvoiceListResponse(BaseModel):
    """Schema for list of invoices response."""
    invoices: List[InvoiceResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class InvoiceSummaryResponse(BaseModel):
    """Schema for invoice summary/statistics."""
    total_invoices: int
    total_draft: int
    total_pending: int
    total_submitted: int
    total_accepted: int
    total_paid: int
    total_overdue: int
    
    # Financial summary
    total_invoiced: float
    total_collected: float
    total_outstanding: float
    total_vat_collected: float
    
    # Period
    period_start: Optional[date] = None
    period_end: Optional[date] = None


class NRSSubmissionResponse(BaseModel):
    """Schema for NRS submission result."""
    success: bool
    invoice_id: UUID
    nrs_irn: Optional[str] = None
    qr_code_data: Optional[str] = None
    message: str
    submitted_at: Optional[datetime] = None
    dispute_deadline: Optional[datetime] = None
    raw_response: Optional[dict] = None


class InvoicePDFResponse(BaseModel):
    """Schema for generated invoice PDF."""
    invoice_id: UUID
    invoice_number: str
    pdf_url: str
    generated_at: datetime
