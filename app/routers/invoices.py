"""
Tekvwa Pro Audit - Invoices Router

API endpoints for invoice management with NRS e-invoicing support.

NTAA 2025 Compliance:
- 72-Hour Legal Lock: Submitted invoices are locked
- Only Owner can cancel NRS submissions during the 72-hour window

SKU Usage Metering:
- Invoice creation is metered for SKU tier limits
"""

from datetime import date, datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.database import get_async_session
from app.dependencies import get_current_active_user, require_within_usage_limit
from app.models.user import User, UserRole
from app.models.invoice import InvoiceStatus, VATTreatment
from app.models.sku import UsageMetricType
from app.services.invoice_service import InvoiceService
from app.services.entity_service import EntityService
from app.services.metering_service import MeteringService
from app.schemas.auth import MessageResponse
from app.utils.permissions import OrganizationPermission, has_organization_permission


router = APIRouter()


# ===========================================
# REQUEST/RESPONSE SCHEMAS
# ===========================================

class InvoiceLineItemRequest(BaseModel):
    """Schema for invoice line item in request."""
    description: str = Field(..., min_length=1, max_length=500)
    quantity: float = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)
    vat_rate: float = Field(7.5, ge=0, le=100)


class InvoiceCreateRequest(BaseModel):
    """Schema for creating an invoice."""
    customer_id: Optional[UUID] = None
    invoice_date: date
    due_date: date
    vat_treatment: str = "standard"
    vat_rate: float = Field(7.5, ge=0, le=100)
    line_items: List[InvoiceLineItemRequest] = Field(..., min_length=1)
    discount_amount: float = Field(0, ge=0)
    notes: Optional[str] = None
    terms: Optional[str] = None


class InvoiceUpdateRequest(BaseModel):
    """Schema for updating an invoice."""
    customer_id: Optional[UUID] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    vat_treatment: Optional[str] = None
    vat_rate: Optional[float] = Field(None, ge=0, le=100)
    discount_amount: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = None
    terms: Optional[str] = None


class PaymentRecordRequest(BaseModel):
    """Schema for recording a payment."""
    amount: float = Field(..., gt=0)
    payment_date: date
    payment_method: str = "bank_transfer"
    reference: Optional[str] = None
    notes: Optional[str] = None


class AddLineItemRequest(BaseModel):
    """Schema for adding a line item."""
    description: str = Field(..., min_length=1, max_length=500)
    quantity: float = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)
    vat_rate: float = Field(7.5, ge=0, le=100)


class LineItemResponse(BaseModel):
    """Schema for line item response."""
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


class InvoiceResponse(BaseModel):
    """Schema for invoice response."""
    id: UUID
    entity_id: UUID
    invoice_number: str
    customer_id: Optional[UUID] = None
    customer_name: Optional[str] = None
    invoice_date: date
    due_date: date
    subtotal: float
    vat_amount: float
    discount_amount: float
    total_amount: float
    amount_paid: float
    balance_due: float
    vat_treatment: str
    vat_rate: float
    status: str
    is_overdue: bool
    nrs_irn: Optional[str] = None
    nrs_qr_code_data: Optional[str] = None
    nrs_submitted_at: Optional[datetime] = None
    dispute_deadline: Optional[datetime] = None
    is_disputed: bool
    notes: Optional[str] = None
    terms: Optional[str] = None
    pdf_url: Optional[str] = None
    line_items: List[LineItemResponse] = []
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class InvoiceListResponse(BaseModel):
    """Schema for invoice list response."""
    invoices: List[InvoiceResponse]
    total: int
    page: int
    page_size: int


class InvoiceSummaryResponse(BaseModel):
    """Schema for invoice summary response."""
    total_invoices: int
    total_draft: int
    total_pending: int
    total_submitted: int
    total_accepted: int
    total_paid: int
    total_overdue: int
    total_invoiced: float
    total_collected: float
    total_outstanding: float
    total_vat_collected: float
    period_start: Optional[date] = None
    period_end: Optional[date] = None


class NRSSubmissionResponse(BaseModel):
    """Schema for NRS submission response."""
    success: bool
    invoice_id: str
    nrs_irn: Optional[str] = None
    qr_code_data: Optional[str] = None
    message: str
    submitted_at: Optional[datetime] = None
    dispute_deadline: Optional[datetime] = None


# ===========================================
# HELPER FUNCTIONS
# ===========================================

def invoice_to_response(invoice) -> InvoiceResponse:
    """Convert Invoice model to response schema."""
    today = date.today()
    is_overdue = (
        invoice.due_date < today and 
        invoice.status.value not in ["paid", "cancelled"]
    )
    
    line_items = [
        LineItemResponse(
            id=li.id,
            description=li.description,
            quantity=float(li.quantity),
            unit_price=float(li.unit_price),
            subtotal=float(li.subtotal),
            vat_amount=float(li.vat_amount),
            total=float(li.total),
            sort_order=li.sort_order,
        )
        for li in sorted(invoice.line_items, key=lambda x: x.sort_order)
    ]
    
    return InvoiceResponse(
        id=invoice.id,
        entity_id=invoice.entity_id,
        invoice_number=invoice.invoice_number,
        customer_id=invoice.customer_id,
        customer_name=invoice.customer.name if invoice.customer else None,
        invoice_date=invoice.invoice_date,
        due_date=invoice.due_date,
        subtotal=float(invoice.subtotal),
        vat_amount=float(invoice.vat_amount),
        discount_amount=float(invoice.discount_amount),
        total_amount=float(invoice.total_amount),
        amount_paid=float(invoice.amount_paid),
        balance_due=float(invoice.balance_due),
        vat_treatment=invoice.vat_treatment.value,
        vat_rate=float(invoice.vat_rate),
        status=invoice.status.value,
        is_overdue=is_overdue,
        nrs_irn=invoice.nrs_irn,
        nrs_qr_code_data=invoice.nrs_qr_code_data,
        nrs_submitted_at=invoice.nrs_submitted_at,
        dispute_deadline=invoice.dispute_deadline,
        is_disputed=invoice.is_disputed,
        notes=invoice.notes,
        terms=invoice.terms,
        pdf_url=invoice.pdf_url,
        line_items=line_items,
        created_at=invoice.created_at,
        updated_at=invoice.updated_at,
    )


async def verify_entity_access(
    entity_id: UUID,
    user: User,
    db: AsyncSession,
) -> None:
    """Verify user has access to the entity."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, user)
    
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business entity not found or access denied",
        )


# ===========================================
# ENDPOINTS
# ===========================================

@router.get(
    "/{entity_id}/invoices",
    response_model=InvoiceListResponse,
    summary="List invoices",
)
async def list_invoices(
    entity_id: UUID,
    status: Optional[str] = Query(None, description="Filter by status"),
    customer_id: Optional[UUID] = Query(None, description="Filter by customer"),
    start_date: Optional[date] = Query(None, description="Filter from date"),
    end_date: Optional[date] = Query(None, description="Filter to date"),
    is_overdue: Optional[bool] = Query(None, description="Filter overdue invoices"),
    search: Optional[str] = Query(None, description="Search invoice number"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    List all invoices for a business entity.
    
    Supports filtering by status, customer, date range, and search.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    invoice_service = InvoiceService(db)
    
    # Convert status string to enum
    status_enum = None
    if status:
        try:
            status_enum = InvoiceStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status}",
            )
    
    invoices, total = await invoice_service.get_invoices_for_entity(
        entity_id=entity_id,
        status=status_enum,
        customer_id=customer_id,
        start_date=start_date,
        end_date=end_date,
        is_overdue=is_overdue,
        search=search,
        page=page,
        page_size=page_size,
    )
    
    return InvoiceListResponse(
        invoices=[invoice_to_response(inv) for inv in invoices],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/{entity_id}/invoices",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create invoice",
)
async def create_invoice(
    entity_id: UUID,
    request: InvoiceCreateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
    _limit_check: User = Depends(require_within_usage_limit(UsageMetricType.INVOICES)),
):
    """
    Create a new invoice with multi-currency support.
    
    Invoice is created in DRAFT status and can be edited until finalized.
    
    Multi-Currency Features (IAS 21 Compliant):
    - currency: Invoice currency (defaults to NGN)
    - exchange_rate: Exchange rate to functional currency (NGN)
    - Functional currency amounts auto-calculated
    """
    await verify_entity_access(entity_id, current_user, db)
    
    invoice_service = InvoiceService(db)
    
    # Get FX service for rate lookups if needed
    fx_service = None
    if request.currency and request.currency != "NGN":
        from app.services.fx_service import FXService
        fx_service = FXService(db)
    
    # Convert vat_treatment string to enum
    try:
        vat_treatment = VATTreatment(request.vat_treatment)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid VAT treatment: {request.vat_treatment}",
        )
    
    # Convert line items to dicts
    line_items_data = [
        {
            "description": li.description,
            "quantity": li.quantity,
            "unit_price": li.unit_price,
            "vat_rate": li.vat_rate,
        }
        for li in request.line_items
    ]
    
    invoice = await invoice_service.create_invoice(
        entity_id=entity_id,
        user_id=current_user.id,
        invoice_date=request.invoice_date,
        due_date=request.due_date,
        line_items_data=line_items_data,
        customer_id=request.customer_id,
        vat_treatment=vat_treatment,
        vat_rate=request.vat_rate,
        discount_amount=request.discount_amount,
        notes=request.notes,
        terms=request.terms,
        # Multi-currency support
        currency=request.currency,
        exchange_rate=request.exchange_rate,
        exchange_rate_source=request.exchange_rate_source,
        fx_service=fx_service,
    )
    
    # Record usage metering for SKU tier limits
    if current_user.organization_id:
        metering_service = MeteringService(db)
        await metering_service.record_invoice(
            organization_id=current_user.organization_id,
            entity_id=entity_id,
            user_id=current_user.id,
            invoice_id=str(invoice.id),
        )
    
    return invoice_to_response(invoice)


@router.get(
    "/{entity_id}/invoices/summary",
    response_model=InvoiceSummaryResponse,
    summary="Get invoice summary",
)
async def get_invoice_summary(
    entity_id: UUID,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get invoice summary statistics for a business entity.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    invoice_service = InvoiceService(db)
    summary = await invoice_service.get_invoice_summary(
        entity_id=entity_id,
        start_date=start_date,
        end_date=end_date,
    )
    
    return InvoiceSummaryResponse(**summary)


@router.get(
    "/{entity_id}/invoices/{invoice_id}",
    response_model=InvoiceResponse,
    summary="Get invoice",
)
async def get_invoice(
    entity_id: UUID,
    invoice_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get a specific invoice by ID.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    invoice_service = InvoiceService(db)
    invoice = await invoice_service.get_invoice_by_id(invoice_id, entity_id)
    
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )
    
    return invoice_to_response(invoice)


@router.patch(
    "/{entity_id}/invoices/{invoice_id}",
    response_model=InvoiceResponse,
    summary="Update invoice",
)
async def update_invoice(
    entity_id: UUID,
    invoice_id: UUID,
    request: InvoiceUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Update an invoice (only DRAFT invoices can be updated).
    """
    await verify_entity_access(entity_id, current_user, db)
    
    invoice_service = InvoiceService(db)
    
    update_data = request.model_dump(exclude_unset=True)
    
    # Convert vat_treatment string to enum if present
    if "vat_treatment" in update_data and update_data["vat_treatment"]:
        try:
            update_data["vat_treatment"] = VATTreatment(update_data["vat_treatment"])
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid VAT treatment: {update_data['vat_treatment']}",
            )
    
    try:
        invoice = await invoice_service.update_invoice(
            invoice_id=invoice_id,
            entity_id=entity_id,
            user_id=current_user.id,
            **update_data,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )
    
    return invoice_to_response(invoice)


@router.delete(
    "/{entity_id}/invoices/{invoice_id}",
    response_model=MessageResponse,
    summary="Delete invoice",
)
async def delete_invoice(
    entity_id: UUID,
    invoice_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Delete an invoice (only DRAFT invoices can be deleted).
    """
    await verify_entity_access(entity_id, current_user, db)
    
    invoice_service = InvoiceService(db)
    
    try:
        deleted = await invoice_service.delete_invoice(invoice_id, entity_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )
    
    return MessageResponse(message="Invoice deleted successfully")


# ===========================================
# LINE ITEM ENDPOINTS
# ===========================================

@router.post(
    "/{entity_id}/invoices/{invoice_id}/line-items",
    response_model=InvoiceResponse,
    summary="Add line item",
)
async def add_line_item(
    entity_id: UUID,
    invoice_id: UUID,
    request: AddLineItemRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Add a line item to an invoice (only DRAFT invoices).
    """
    await verify_entity_access(entity_id, current_user, db)
    
    invoice_service = InvoiceService(db)
    
    try:
        invoice = await invoice_service.add_line_item(
            invoice_id=invoice_id,
            entity_id=entity_id,
            user_id=current_user.id,
            description=request.description,
            quantity=request.quantity,
            unit_price=request.unit_price,
            vat_rate=request.vat_rate,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return invoice_to_response(invoice)


@router.delete(
    "/{entity_id}/invoices/{invoice_id}/line-items/{line_item_id}",
    response_model=InvoiceResponse,
    summary="Remove line item",
)
async def remove_line_item(
    entity_id: UUID,
    invoice_id: UUID,
    line_item_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Remove a line item from an invoice (only DRAFT invoices, must have at least one item).
    """
    await verify_entity_access(entity_id, current_user, db)
    
    invoice_service = InvoiceService(db)
    
    try:
        invoice = await invoice_service.remove_line_item(
            invoice_id=invoice_id,
            line_item_id=line_item_id,
            entity_id=entity_id,
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return invoice_to_response(invoice)


# ===========================================
# STATUS MANAGEMENT ENDPOINTS
# ===========================================

@router.post(
    "/{entity_id}/invoices/{invoice_id}/finalize",
    response_model=InvoiceResponse,
    summary="Finalize invoice",
)
async def finalize_invoice(
    entity_id: UUID,
    invoice_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Finalize a DRAFT invoice (moves to PENDING status).
    
    Once finalized, the invoice cannot be edited, only cancelled.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    invoice_service = InvoiceService(db)
    
    try:
        invoice = await invoice_service.finalize_invoice(
            invoice_id=invoice_id,
            entity_id=entity_id,
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return invoice_to_response(invoice)


@router.post(
    "/{entity_id}/invoices/{invoice_id}/cancel",
    response_model=InvoiceResponse,
    summary="Cancel invoice",
)
async def cancel_invoice(
    entity_id: UUID,
    invoice_id: UUID,
    reason: Optional[str] = Query(None, description="Cancellation reason"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Cancel an invoice.
    
    Cannot cancel PAID or already CANCELLED invoices.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    invoice_service = InvoiceService(db)
    
    try:
        invoice = await invoice_service.cancel_invoice(
            invoice_id=invoice_id,
            entity_id=entity_id,
            user_id=current_user.id,
            reason=reason,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return invoice_to_response(invoice)


# ===========================================
# PAYMENT ENDPOINTS
# ===========================================

@router.post(
    "/{entity_id}/invoices/{invoice_id}/payments",
    response_model=InvoiceResponse,
    summary="Record payment",
)
async def record_payment(
    entity_id: UUID,
    invoice_id: UUID,
    request: PaymentRecordRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Record a payment against an invoice with multi-currency support.
    
    Automatically updates invoice status to PAID or PARTIALLY_PAID.
    
    Multi-Currency Features (IAS 21 Compliant):
    - payment_currency: Currency of the payment (defaults to invoice currency)
    - payment_exchange_rate: Exchange rate to functional currency (NGN)
    - Automatic FX gain/loss calculation when rates differ
    """
    await verify_entity_access(entity_id, current_user, db)
    
    invoice_service = InvoiceService(db)
    
    # Get FX service for rate lookups if needed
    fx_service = None
    if request.payment_currency or request.payment_exchange_rate:
        from app.services.fx_service import FXService
        fx_service = FXService(db)
    
    try:
        invoice = await invoice_service.record_payment(
            invoice_id=invoice_id,
            entity_id=entity_id,
            user_id=current_user.id,
            amount=request.amount,
            payment_date=request.payment_date,
            payment_method=request.payment_method,
            reference=request.reference,
            notes=request.notes,
            # Multi-currency support
            payment_currency=request.payment_currency,
            payment_exchange_rate=request.payment_exchange_rate,
            fx_service=fx_service,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return invoice_to_response(invoice)


# ===========================================
# NRS E-INVOICING ENDPOINTS
# ===========================================

@router.post(
    "/{entity_id}/invoices/{invoice_id}/submit-nrs",
    response_model=NRSSubmissionResponse,
    summary="Submit to NRS",
)
async def submit_to_nrs(
    entity_id: UUID,
    invoice_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Submit invoice to NRS (FIRS) for IRN generation.
    
    This is a placeholder endpoint. Full NRS integration will be implemented in Segment 14.
    
    Requirements for NRS submission:
    - Invoice must be in PENDING or REJECTED status
    - B2B invoices require customer TIN
    """
    await verify_entity_access(entity_id, current_user, db)
    
    invoice_service = InvoiceService(db)
    
    try:
        result = await invoice_service.submit_to_nrs(
            invoice_id=invoice_id,
            entity_id=entity_id,
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return NRSSubmissionResponse(
        success=result["success"],
        invoice_id=result["invoice_id"],
        nrs_irn=result.get("nrs_irn"),
        qr_code_data=result.get("qr_code_data"),
        message=result["message"],
        submitted_at=result.get("submitted_at"),
        dispute_deadline=result.get("dispute_deadline"),
    )


# ===========================================
# NRS CANCELLATION (NTAA 2025 - 72-Hour Lock)
# ===========================================

class NRSCancellationRequest(BaseModel):
    """Request schema for NRS cancellation."""
    reason: str = Field(..., min_length=10, max_length=1000, description="Reason for cancellation (required)")


class NRSCancellationResponse(BaseModel):
    """Response schema for NRS cancellation."""
    success: bool
    invoice_id: str
    cancelled_by: str
    message: str


@router.post(
    "/{entity_id}/invoices/{invoice_id}/cancel-nrs",
    response_model=NRSCancellationResponse,
    summary="Cancel NRS Submission (Owner Only)",
    description="""
    Cancel an NRS submission during the 72-hour buyer review window.
    
    NTAA 2025 Compliance - 72-Hour Legal Lock:
    - Only the Owner can cancel an NRS submission
    - Cancellation is only allowed during the 72-hour buyer review window
    - After the window expires, a Credit Note is required
    
    Required permission: CANCEL_NRS_SUBMISSION (Owner only)
    
    Legal Warning: Modifying a "Submitted" invoice without proper NRS-tracked 
    Credit Note is a criminal offense under the NTAA 2025.
    """,
)
async def cancel_nrs_submission(
    entity_id: UUID,
    invoice_id: UUID,
    request: NRSCancellationRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Cancel an NRS submission during the 72-hour window.
    
    Owner only - requires CANCEL_NRS_SUBMISSION permission.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    # NTAA 2025: Only Owner can cancel NRS submission
    if not current_user.is_platform_staff:
        if not has_organization_permission(current_user.role, OrganizationPermission.CANCEL_NRS_SUBMISSION):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CANCEL_NRS_SUBMISSION permission required. Only the organization Owner can cancel NRS submissions.",
            )
    
    invoice_service = InvoiceService(db)
    
    # Get the invoice
    invoice = await invoice_service.get_invoice_by_id(invoice_id, entity_id)
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )
    
    # Check if invoice is NRS locked
    if not invoice.is_nrs_locked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice has not been submitted to NRS",
        )
    
    # Check if within 72-hour window
    if invoice.nrs_lock_expires_at:
        from datetime import timezone
        now = datetime.now(timezone.utc)
        if now > invoice.nrs_lock_expires_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="72-hour window has expired. A Credit Note is required to modify this invoice.",
            )
    
    try:
        result = await invoice_service.cancel_nrs_submission(
            invoice_id=invoice_id,
            entity_id=entity_id,
            user_id=current_user.id,
            reason=request.reason,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return NRSCancellationResponse(
        success=True,
        invoice_id=str(invoice_id),
        cancelled_by=current_user.email,
        message=f"NRS submission cancelled successfully. Reason: {request.reason}",
    )


# ===========================================
# ADDITIONAL INVOICE ACTIONS
# ===========================================

class SendInvoiceRequest(BaseModel):
    """Request schema for sending invoice via email."""
    recipient_email: Optional[str] = None
    cc_emails: Optional[List[str]] = None
    message: Optional[str] = None
    attach_pdf: bool = True


class DuplicateInvoiceRequest(BaseModel):
    """Request schema for duplicating invoice."""
    new_invoice_date: Optional[date] = None
    new_due_date: Optional[date] = None
    copy_line_items: bool = True


class PaymentHistoryResponse(BaseModel):
    """Response for payment history."""
    payments: List[dict]
    total_paid: float
    balance_due: float


@router.post(
    "/{entity_id}/invoices/{invoice_id}/send",
    response_model=MessageResponse,
    summary="Send invoice via email",
    description="Send the invoice to the customer via email with optional PDF attachment.",
)
async def send_invoice(
    entity_id: UUID,
    invoice_id: UUID,
    request: SendInvoiceRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Send invoice to customer via email."""
    await verify_entity_access(entity_id, current_user, db)
    
    invoice_service = InvoiceService(db)
    invoice = await invoice_service.get_invoice_by_id(invoice_id, entity_id)
    
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )
    
    # Determine recipient
    recipient = request.recipient_email
    if not recipient and invoice.customer:
        recipient = invoice.customer.email
    
    if not recipient:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No recipient email provided and customer has no email on file",
        )
    
    # Send email
    from app.services.email_service import EmailService
    email_service = EmailService()
    
    try:
        await email_service.send_invoice_email(
            to_email=recipient,
            customer_name=invoice.customer.name if invoice.customer else "Customer",
            invoice_number=invoice.invoice_number,
            amount=float(invoice.total_amount),
            due_date=invoice.due_date.isoformat(),
            invoice_url=f"/invoices/{invoice_id}",
            custom_message=request.message,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send email: {str(e)}",
        )
    
    return MessageResponse(message=f"Invoice sent to {recipient}")


@router.post(
    "/{entity_id}/invoices/{invoice_id}/remind",
    response_model=MessageResponse,
    summary="Send payment reminder",
    description="Send a payment reminder for an outstanding invoice.",
)
async def send_reminder(
    entity_id: UUID,
    invoice_id: UUID,
    custom_message: Optional[str] = Query(None, description="Custom reminder message"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Send payment reminder."""
    await verify_entity_access(entity_id, current_user, db)
    
    invoice_service = InvoiceService(db)
    invoice = await invoice_service.get_invoice_by_id(invoice_id, entity_id)
    
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )
    
    if invoice.status.value == "paid":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice is already paid",
        )
    
    if not invoice.customer or not invoice.customer.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Customer has no email on file",
        )
    
    # Calculate days overdue
    today = date.today()
    days_overdue = (today - invoice.due_date).days if today > invoice.due_date else 0
    
    from app.services.email_service import EmailService
    email_service = EmailService()
    
    try:
        await email_service.send_overdue_reminder(
            to_email=invoice.customer.email,
            customer_name=invoice.customer.name,
            invoice_number=invoice.invoice_number,
            amount=float(invoice.balance_due),
            due_date=invoice.due_date.isoformat(),
            days_overdue=days_overdue,
            custom_message=custom_message,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send reminder: {str(e)}",
        )
    
    return MessageResponse(message=f"Reminder sent to {invoice.customer.email}")


@router.get(
    "/{entity_id}/invoices/{invoice_id}/pdf",
    summary="Download invoice PDF",
    description="Download the invoice as a PDF document.",
)
async def download_invoice_pdf(
    entity_id: UUID,
    invoice_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Download invoice as PDF."""
    from fastapi.responses import Response
    
    await verify_entity_access(entity_id, current_user, db)
    
    invoice_service = InvoiceService(db)
    invoice = await invoice_service.get_invoice_by_id(invoice_id, entity_id)
    
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )
    
    # In a full implementation, generate PDF here
    # For now, return placeholder
    pdf_content = f"Invoice {invoice.invoice_number} - Total: {invoice.total_amount}".encode()
    
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=invoice_{invoice.invoice_number}.pdf"
        }
    )


@router.post(
    "/{entity_id}/invoices/{invoice_id}/duplicate",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Duplicate invoice",
    description="Create a copy of an existing invoice with new dates.",
)
async def duplicate_invoice(
    entity_id: UUID,
    invoice_id: UUID,
    request: DuplicateInvoiceRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Duplicate an invoice."""
    await verify_entity_access(entity_id, current_user, db)
    
    invoice_service = InvoiceService(db)
    original = await invoice_service.get_invoice_by_id(invoice_id, entity_id)
    
    if not original:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )
    
    # Set dates
    new_invoice_date = request.new_invoice_date or date.today()
    new_due_date = request.new_due_date
    if not new_due_date:
        # Calculate due date based on original payment terms
        days_until_due = (original.due_date - original.invoice_date).days
        new_due_date = new_invoice_date + timedelta(days=days_until_due)
    
    # Create line items data
    line_items_data = []
    if request.copy_line_items:
        for li in original.line_items:
            line_items_data.append({
                "description": li.description,
                "quantity": float(li.quantity),
                "unit_price": float(li.unit_price),
                "vat_rate": float(getattr(li, 'vat_rate', 7.5)),
            })
    
    # Create new invoice
    new_invoice = await invoice_service.create_invoice(
        entity_id=entity_id,
        user_id=current_user.id,
        invoice_date=new_invoice_date,
        due_date=new_due_date,
        line_items_data=line_items_data or [{"description": "Item", "quantity": 1, "unit_price": 0, "vat_rate": 7.5}],
        customer_id=original.customer_id,
        vat_treatment=original.vat_treatment,
        vat_rate=float(original.vat_rate),
        discount_amount=float(original.discount_amount),
        notes=f"Copied from {original.invoice_number}",
        terms=original.terms,
    )
    
    return invoice_to_response(new_invoice)


@router.get(
    "/{entity_id}/invoices/{invoice_id}/payments",
    response_model=PaymentHistoryResponse,
    summary="Get payment history",
    description="Get the payment history for an invoice.",
)
async def get_payment_history(
    entity_id: UUID,
    invoice_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get payment history for an invoice."""
    await verify_entity_access(entity_id, current_user, db)
    
    invoice_service = InvoiceService(db)
    invoice = await invoice_service.get_invoice_by_id(invoice_id, entity_id)
    
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )
    
    # In a full implementation, query payments table
    # For now, return placeholder based on invoice data
    payments = []
    if invoice.amount_paid > 0:
        payments.append({
            "id": str(uuid.uuid4()),
            "amount": float(invoice.amount_paid),
            "payment_date": invoice.updated_at.date().isoformat() if invoice.updated_at else None,
            "payment_method": "recorded",
            "reference": None,
        })
    
    return PaymentHistoryResponse(
        payments=payments,
        total_paid=float(invoice.amount_paid),
        balance_due=float(invoice.balance_due),
    )


# Need to import timedelta and uuid for duplicate function
from datetime import timedelta
import uuid


# ===========================================
# INVOICE AGING & VOID ENDPOINTS
# ===========================================

class InvoiceAgingBucket(BaseModel):
    """Aging bucket for invoices."""
    bucket: str
    count: int
    total_amount: float
    invoices: List[dict]


class InvoiceAgingResponse(BaseModel):
    """Invoice aging report."""
    as_of_date: date
    total_outstanding: float
    total_overdue: float
    buckets: List[InvoiceAgingBucket]


class VoidInvoiceRequest(BaseModel):
    """Request to void an invoice."""
    reason: str = Field(..., min_length=10, max_length=500, description="Reason for voiding")


class UpdateLineItemRequest(BaseModel):
    """Request to update a line item."""
    description: Optional[str] = None
    quantity: Optional[float] = Field(None, gt=0)
    unit_price: Optional[float] = Field(None, ge=0)
    vat_rate: Optional[float] = Field(None, ge=0, le=100)


class InvoiceTemplateResponse(BaseModel):
    """Invoice template."""
    id: UUID
    name: str
    description: Optional[str]
    line_items: List[dict]
    default_terms: Optional[str]
    is_default: bool


@router.get(
    "/{entity_id}/invoices/aging",
    response_model=InvoiceAgingResponse,
    summary="Get invoice aging report",
    description="Get aging analysis of outstanding invoices.",
)
async def get_invoice_aging(
    entity_id: UUID,
    as_of_date: Optional[date] = Query(None, description="Date for aging calculation"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get invoice aging report."""
    await verify_entity_access(entity_id, current_user, db)
    
    report_date = as_of_date or date.today()
    
    from sqlalchemy import select
    from app.models.invoice import Invoice
    
    query = select(Invoice).where(
        Invoice.entity_id == entity_id,
        Invoice.balance_due > 0,
        Invoice.is_deleted == False,
    )
    
    result = await db.execute(query)
    invoices = result.scalars().all()
    
    # Define aging buckets
    buckets = {
        "current": {"label": "Current (0-30 days)", "min": 0, "max": 30, "invoices": []},
        "30_60": {"label": "31-60 days", "min": 31, "max": 60, "invoices": []},
        "60_90": {"label": "61-90 days", "min": 61, "max": 90, "invoices": []},
        "90_plus": {"label": "Over 90 days", "min": 91, "max": 9999, "invoices": []},
    }
    
    total_outstanding = 0
    total_overdue = 0
    
    for inv in invoices:
        days_outstanding = (report_date - inv.due_date).days
        balance = float(inv.balance_due)
        total_outstanding += balance
        
        if days_outstanding > 0:
            total_overdue += balance
        
        inv_data = {
            "id": str(inv.id),
            "invoice_number": inv.invoice_number,
            "customer_name": inv.customer.name if inv.customer else "Unknown",
            "due_date": inv.due_date.isoformat(),
            "balance_due": balance,
            "days_outstanding": days_outstanding,
        }
        
        if days_outstanding <= 30:
            buckets["current"]["invoices"].append(inv_data)
        elif days_outstanding <= 60:
            buckets["30_60"]["invoices"].append(inv_data)
        elif days_outstanding <= 90:
            buckets["60_90"]["invoices"].append(inv_data)
        else:
            buckets["90_plus"]["invoices"].append(inv_data)
    
    bucket_responses = []
    for key, bucket in buckets.items():
        bucket_responses.append(InvoiceAgingBucket(
            bucket=bucket["label"],
            count=len(bucket["invoices"]),
            total_amount=sum(i["balance_due"] for i in bucket["invoices"]),
            invoices=bucket["invoices"],
        ))
    
    return InvoiceAgingResponse(
        as_of_date=report_date,
        total_outstanding=total_outstanding,
        total_overdue=total_overdue,
        buckets=bucket_responses,
    )


@router.post(
    "/{entity_id}/invoices/{invoice_id}/void",
    response_model=MessageResponse,
    summary="Void an invoice",
    description="Void an invoice with proper audit trail. Cannot void NRS-submitted invoices.",
)
async def void_invoice(
    entity_id: UUID,
    invoice_id: UUID,
    request: VoidInvoiceRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Void an invoice."""
    await verify_entity_access(entity_id, current_user, db)
    
    invoice_service = InvoiceService(db)
    invoice = await invoice_service.get_invoice_by_id(invoice_id, entity_id)
    
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )
    
    # Check if already voided
    if invoice.status == InvoiceStatus.VOIDED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice is already voided",
        )
    
    # Cannot void NRS-submitted invoices
    if invoice.nrs_submitted and not invoice.nrs_cancelled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot void NRS-submitted invoice. Cancel NRS submission first.",
        )
    
    # Cannot void paid invoices
    if invoice.amount_paid > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot void invoice with payments. Refund payments first.",
        )
    
    # Void the invoice
    invoice.status = InvoiceStatus.VOIDED
    invoice.voided_at = datetime.utcnow()
    invoice.voided_by_id = current_user.id
    invoice.void_reason = request.reason
    
    # Log audit trail
    from app.services.audit_service import AuditService
    audit_service = AuditService(db)
    await audit_service.log_action(
        user_id=current_user.id,
        entity_id=entity_id,
        action="invoice_voided",
        resource_type="invoice",
        resource_id=str(invoice.id),
        details={
            "invoice_number": invoice.invoice_number,
            "reason": request.reason,
        },
    )
    
    await db.commit()
    
    return MessageResponse(message=f"Invoice {invoice.invoice_number} voided successfully")


@router.put(
    "/{entity_id}/invoices/{invoice_id}/line-items/{line_item_id}",
    response_model=LineItemResponse,
    summary="Update line item",
    description="Update a specific line item on an invoice.",
)
async def update_line_item(
    entity_id: UUID,
    invoice_id: UUID,
    line_item_id: UUID,
    request: UpdateLineItemRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Update a line item."""
    await verify_entity_access(entity_id, current_user, db)
    
    invoice_service = InvoiceService(db)
    invoice = await invoice_service.get_invoice_by_id(invoice_id, entity_id)
    
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )
    
    # Check if invoice is editable
    if invoice.status not in [InvoiceStatus.DRAFT]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only edit line items on draft invoices",
        )
    
    # Find the line item
    line_item = None
    for li in invoice.line_items:
        if li.id == line_item_id:
            line_item = li
            break
    
    if not line_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Line item not found",
        )
    
    # Update fields
    if request.description is not None:
        line_item.description = request.description
    if request.quantity is not None:
        line_item.quantity = request.quantity
    if request.unit_price is not None:
        line_item.unit_price = request.unit_price
    if request.vat_rate is not None:
        line_item.vat_rate = request.vat_rate
    
    # Recalculate
    line_item.subtotal = line_item.quantity * line_item.unit_price
    line_item.vat_amount = line_item.subtotal * (line_item.vat_rate / 100)
    line_item.total = line_item.subtotal + line_item.vat_amount
    
    # Recalculate invoice totals
    await invoice_service.recalculate_invoice_totals(invoice)
    
    await db.commit()
    await db.refresh(line_item)
    
    return LineItemResponse(
        id=line_item.id,
        description=line_item.description,
        quantity=float(line_item.quantity),
        unit_price=float(line_item.unit_price),
        subtotal=float(line_item.subtotal),
        vat_amount=float(line_item.vat_amount),
        total=float(line_item.total),
        sort_order=line_item.sort_order,
    )


@router.post(
    "/{entity_id}/invoices/batch-finalize",
    response_model=MessageResponse,
    summary="Batch finalize invoices",
    description="Finalize multiple draft invoices at once.",
)
async def batch_finalize_invoices(
    entity_id: UUID,
    invoice_ids: List[UUID],
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Batch finalize draft invoices."""
    await verify_entity_access(entity_id, current_user, db)
    
    invoice_service = InvoiceService(db)
    
    finalized_count = 0
    errors = []
    
    for inv_id in invoice_ids:
        invoice = await invoice_service.get_invoice_by_id(inv_id, entity_id)
        if not invoice:
            errors.append(f"Invoice {inv_id} not found")
            continue
        
        if invoice.status != InvoiceStatus.DRAFT:
            errors.append(f"Invoice {invoice.invoice_number} is not a draft")
            continue
        
        try:
            await invoice_service.finalize_invoice(invoice, current_user.id)
            finalized_count += 1
        except Exception as e:
            errors.append(f"Failed to finalize {invoice.invoice_number}: {str(e)}")
    
    await db.commit()
    
    message = f"Finalized {finalized_count} invoices"
    if errors:
        message += f". Errors: {'; '.join(errors[:5])}"
    
    return MessageResponse(message=message)


@router.post(
    "/{entity_id}/invoices/batch-remind",
    response_model=MessageResponse,
    summary="Send batch payment reminders",
    description="Send payment reminders for multiple overdue invoices.",
)
async def batch_send_reminders(
    entity_id: UUID,
    invoice_ids: Optional[List[UUID]] = None,
    overdue_only: bool = Query(True, description="Only send to overdue invoices"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Send batch payment reminders."""
    await verify_entity_access(entity_id, current_user, db)
    
    from sqlalchemy import select
    from app.models.invoice import Invoice
    
    if invoice_ids:
        query = select(Invoice).where(
            Invoice.entity_id == entity_id,
            Invoice.id.in_(invoice_ids),
            Invoice.is_deleted == False,
        )
    else:
        query = select(Invoice).where(
            Invoice.entity_id == entity_id,
            Invoice.balance_due > 0,
            Invoice.is_deleted == False,
        )
        if overdue_only:
            query = query.where(Invoice.due_date < date.today())
    
    result = await db.execute(query)
    invoices = result.scalars().all()
    
    sent_count = 0
    errors = []
    
    from app.services.email_service import EmailService
    email_service = EmailService()
    
    for inv in invoices:
        if not inv.customer or not inv.customer.email:
            errors.append(f"{inv.invoice_number}: no customer email")
            continue
        
        try:
            days_overdue = (date.today() - inv.due_date).days
            await email_service.send_overdue_reminder(
                to_email=inv.customer.email,
                customer_name=inv.customer.name,
                invoice_number=inv.invoice_number,
                amount=float(inv.balance_due),
                due_date=inv.due_date.isoformat(),
                days_overdue=days_overdue if days_overdue > 0 else 0,
            )
            sent_count += 1
        except Exception as e:
            errors.append(f"{inv.invoice_number}: {str(e)}")
    
    message = f"Sent {sent_count} reminders"
    if errors:
        message += f". Errors: {len(errors)}"
    
    return MessageResponse(message=message)


@router.get(
    "/{entity_id}/invoices/nrs-status",
    summary="Get NRS submission status for all invoices",
    description="Get NRS e-invoicing status summary.",
)
async def get_nrs_status_summary(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get NRS submission status summary."""
    await verify_entity_access(entity_id, current_user, db)
    
    from sqlalchemy import select, func
    from app.models.invoice import Invoice
    
    # Count by NRS status
    total_query = select(func.count(Invoice.id)).where(
        Invoice.entity_id == entity_id,
        Invoice.is_deleted == False,
    )
    total_result = await db.execute(total_query)
    total = total_result.scalar() or 0
    
    submitted_query = select(func.count(Invoice.id)).where(
        Invoice.entity_id == entity_id,
        Invoice.nrs_submitted == True,
        Invoice.is_deleted == False,
    )
    submitted_result = await db.execute(submitted_query)
    submitted = submitted_result.scalar() or 0
    
    pending_query = select(func.count(Invoice.id)).where(
        Invoice.entity_id == entity_id,
        Invoice.nrs_submitted == True,
        Invoice.buyer_approved == None,
        Invoice.is_deleted == False,
    )
    pending_result = await db.execute(pending_query)
    pending = pending_result.scalar() or 0
    
    approved_query = select(func.count(Invoice.id)).where(
        Invoice.entity_id == entity_id,
        Invoice.buyer_approved == True,
        Invoice.is_deleted == False,
    )
    approved_result = await db.execute(approved_query)
    approved = approved_result.scalar() or 0
    
    return {
        "total_invoices": total,
        "nrs_submitted": submitted,
        "pending_buyer_approval": pending,
        "buyer_approved": approved,
        "not_submitted": total - submitted,
    }


@router.get(
    "/{entity_id}/invoices/templates",
    response_model=List[InvoiceTemplateResponse],
    summary="List invoice templates",
    description="Get all saved invoice templates.",
)
async def list_invoice_templates(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """List invoice templates."""
    await verify_entity_access(entity_id, current_user, db)
    
    # In production, query InvoiceTemplate table
    # For now, return empty list
    return []


@router.post(
    "/{entity_id}/invoices/templates",
    response_model=InvoiceTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create invoice template",
    description="Create a new invoice template from an existing invoice or from scratch.",
)
async def create_invoice_template(
    entity_id: UUID,
    name: str = Query(..., description="Template name"),
    from_invoice_id: Optional[UUID] = Query(None, description="Create from existing invoice"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Create an invoice template."""
    await verify_entity_access(entity_id, current_user, db)
    
    line_items = []
    default_terms = None
    
    if from_invoice_id:
        invoice_service = InvoiceService(db)
        invoice = await invoice_service.get_invoice_by_id(from_invoice_id, entity_id)
        if invoice:
            line_items = [
                {
                    "description": li.description,
                    "quantity": float(li.quantity),
                    "unit_price": float(li.unit_price),
                    "vat_rate": float(getattr(li, 'vat_rate', 7.5)),
                }
                for li in invoice.line_items
            ]
            default_terms = invoice.terms
    
    # In production, save to InvoiceTemplate table
    # For now, return placeholder
    return InvoiceTemplateResponse(
        id=uuid.uuid4(),
        name=name,
        description=None,
        line_items=line_items,
        default_terms=default_terms,
        is_default=False,
    )

