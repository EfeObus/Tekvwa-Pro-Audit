"""
Tekvwa Pro Audit - Transaction Schemas

Pydantic schemas for transaction (expense/income) recording.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class TransactionType(str, Enum):
    """Transaction types."""
    INCOME = "income"
    EXPENSE = "expense"


class WRENStatus(str, Enum):
    """WREN classification status."""
    PENDING = "pending"
    CLASSIFIED = "classified"
    REVIEWED = "reviewed"


class PaymentMethod(str, Enum):
    """Payment methods."""
    CASH = "cash"
    BANK_TRANSFER = "bank_transfer"
    CHEQUE = "cheque"
    CARD = "card"
    MOBILE_MONEY = "mobile_money"
    OTHER = "other"


# ===========================================
# REQUEST SCHEMAS
# ===========================================

class TransactionCreateRequest(BaseModel):
    """Schema for creating a transaction."""
    transaction_type: TransactionType = Field(..., description="'income' or 'expense'")
    date: date = Field(..., description="Transaction date")
    
    # Multi-Currency Support (IAS 21)
    currency: str = Field("NGN", min_length=3, max_length=3, description="Transaction currency code (USD, EUR, GBP, NGN)")
    exchange_rate: Optional[float] = Field(None, gt=0, description="Exchange rate at transaction date (1 FC = X NGN). Auto-fetched if not provided.")
    exchange_rate_source: Optional[str] = Field(None, description="Rate source: CBN, manual, spot, contract")
    
    # Amounts (in transaction currency)
    amount: float = Field(..., gt=0, description="Net amount before VAT/taxes in transaction currency")
    vat_amount: float = Field(0, ge=0, description="VAT amount in transaction currency")
    wht_amount: float = Field(0, ge=0, description="Withholding Tax amount in transaction currency")
    
    # Description
    description: str = Field(..., min_length=1, max_length=500)
    reference: Optional[str] = Field(None, max_length=100, description="Receipt/reference number")
    
    # Classification
    category_id: UUID = Field(..., description="Category for WREN classification")
    
    # Related entities (optional)
    vendor_id: Optional[UUID] = Field(None, description="For expenses")
    customer_id: Optional[UUID] = Field(None, description="For income")
    invoice_id: Optional[UUID] = Field(None, description="If linked to invoice")
    
    # Payment details
    payment_method: PaymentMethod = PaymentMethod.BANK_TRANSFER
    payment_date: Optional[date] = Field(None, description="If different from transaction date")
    
    # Attachments
    attachment_urls: Optional[List[str]] = Field(None, description="URLs of uploaded receipts/documents")
    
    notes: Optional[str] = None


class TransactionUpdateRequest(BaseModel):
    """Schema for updating a transaction."""
    date: Optional[date] = None
    
    # Amounts
    amount: Optional[float] = Field(None, gt=0)
    vat_amount: Optional[float] = Field(None, ge=0)
    wht_amount: Optional[float] = Field(None, ge=0)
    
    # Description
    description: Optional[str] = Field(None, min_length=1, max_length=500)
    reference: Optional[str] = Field(None, max_length=100)
    
    # Classification
    category_id: Optional[UUID] = None
    
    # Related entities
    vendor_id: Optional[UUID] = None
    customer_id: Optional[UUID] = None
    
    # Payment details
    payment_method: Optional[PaymentMethod] = None
    payment_date: Optional[date] = None
    
    # Attachments
    attachment_urls: Optional[List[str]] = None
    
    notes: Optional[str] = None


class TransactionBulkCreateRequest(BaseModel):
    """Schema for bulk creating transactions."""
    transactions: List[TransactionCreateRequest]


# ===========================================
# RESPONSE SCHEMAS
# ===========================================

class TransactionResponse(BaseModel):
    """Schema for transaction response."""
    id: UUID
    entity_id: UUID
    transaction_type: str
    date: date
    
    # Multi-Currency (IAS 21)
    currency: str = "NGN"
    exchange_rate: float = 1.0
    exchange_rate_source: Optional[str] = None
    is_foreign_currency: bool = False
    
    # Amounts in original currency
    amount: float
    vat_amount: float
    wht_amount: float
    total_amount: float
    
    # Functional currency amounts (NGN)
    functional_amount: float = 0.0
    functional_vat_amount: float = 0.0
    functional_total_amount: float = 0.0
    
    # FX Gain/Loss
    realized_fx_gain_loss: float = 0.0
    settlement_exchange_rate: Optional[float] = None
    settlement_date: Optional[date] = None
    is_settled: bool = False
    
    # Description
    description: str
    reference: Optional[str] = None
    
    # Classification
    category_id: UUID
    category_name: Optional[str] = None
    wren_type: Optional[str] = None
    wren_status: str
    
    # Related entities
    vendor_id: Optional[UUID] = None
    vendor_name: Optional[str] = None
    customer_id: Optional[UUID] = None
    customer_name: Optional[str] = None
    invoice_id: Optional[UUID] = None
    invoice_number: Optional[str] = None
    
    # Payment details
    payment_method: str
    payment_date: Optional[date] = None
    is_paid: bool
    
    # Attachments
    attachment_urls: List[str] = []
    
    notes: Optional[str] = None
    
    # Audit
    created_by_id: UUID
    created_by_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class TransactionListResponse(BaseModel):
    """List of transactions response."""
    transactions: List[TransactionResponse]
    total: int
    total_amount: float
    total_vat: float
    total_wht: float


class TransactionSummaryResponse(BaseModel):
    """Transaction summary for a period."""
    period_start: date
    period_end: date
    
    # Income summary
    total_income: float
    income_count: int
    income_vat_collected: float
    
    # Expense summary
    total_expenses: float
    expense_count: int
    expense_vat_paid: float
    
    # Net
    net_amount: float
    vat_position: float  # VAT collected - VAT paid
    
    # By WREN category
    wren_breakdown: dict


class TransactionFilterParams(BaseModel):
    """Filter parameters for transactions."""
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    transaction_type: Optional[TransactionType] = None
    category_id: Optional[UUID] = None
    vendor_id: Optional[UUID] = None
    customer_id: Optional[UUID] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    is_paid: Optional[bool] = None
    wren_status: Optional[WRENStatus] = None
