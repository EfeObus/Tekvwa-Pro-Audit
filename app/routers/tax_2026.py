"""
Tekvwa Pro Audit - 2026 Tax Reform Router

API endpoints for the 2026 Nigerian Tax Administration Act compliance:
- 72-Hour Buyer Review Module
- Advanced Input VAT Recovery
- Development Levy (4%)
- PIT Relief Documents
- Business Type Toggle (PIT vs CIT)
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Path, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.database import get_async_session
from app.dependencies import get_current_active_user, require_feature
from app.models.user import User
from app.models.entity import BusinessType
from app.models.invoice import BuyerStatus
from app.models.tax_2026 import VATRecoveryType, ReliefType, ReliefStatus, CreditNoteStatus
from app.models.sku import Feature
from app.services.buyer_review_service import BuyerReviewService
from app.services.vat_recovery_service import VATRecoveryService
from app.services.development_levy_service import DevelopmentLevyService
from app.services.pit_relief_service import PITReliefService
from app.services.entity_service import EntityService
from app.services.audit_service import AuditService
from app.models.audit_consolidated import AuditAction
from app.services.tin_validation_service import (
    TINValidationService,
    TINEntityType,
    TINValidationStatus,
    TINValidationResult,
)
from app.services.b2c_reporting_service import B2CReportingService
from app.services.compliance_penalty_service import (
    CompliancePenaltyService,
    PenaltyType,
    PenaltyStatus,
    PENALTY_SCHEDULE,
)
from app.services.peppol_export_service import (
    PeppolExportService,
    PeppolInvoice,
    PeppolParty,
    PeppolLineItem,
    InvoiceTypeCode,
    TaxCategoryCode,
)
from app.schemas.auth import MessageResponse

# Feature gate for 2026 tax reform features (PROFESSIONAL tier - NRS compliance)
tax_2026_feature_gate = require_feature([Feature.NRS_COMPLIANCE])

router = APIRouter(
    prefix="/api/v1/tax-2026",
    tags=["2026 Tax Reform"],
    dependencies=[Depends(tax_2026_feature_gate)],
)


# ===========================================
# SCHEMAS
# ===========================================

# Buyer Review Schemas
class BuyerResponseRequest(BaseModel):
    """Request to process buyer response."""
    accepted: bool
    rejection_reason: Optional[str] = None


class InvoiceBuyerStatusResponse(BaseModel):
    """Invoice buyer status response."""
    invoice_id: UUID
    invoice_number: str
    buyer_status: str
    dispute_deadline: Optional[str] = None
    buyer_response_at: Optional[str] = None
    credit_note_id: Optional[UUID] = None


class CreditNoteResponse(BaseModel):
    """Credit note response."""
    id: UUID
    credit_note_number: str
    original_invoice_id: Optional[UUID]
    issue_date: date
    reason: str
    subtotal: float
    vat_amount: float
    total_amount: float
    status: str
    nrs_irn: Optional[str] = None


# VAT Recovery Schemas
class VATRecoveryRequest(BaseModel):
    """Request to record VAT recovery."""
    transaction_id: Optional[UUID] = None
    vat_amount: Decimal = Field(..., gt=0)
    recovery_type: VATRecoveryType
    vendor_irn: Optional[str] = None
    transaction_date: date
    description: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_tin: Optional[str] = None


class VATRecoveryResponse(BaseModel):
    """VAT recovery record response."""
    id: UUID
    vat_amount: float
    recovery_type: str
    is_recoverable: bool
    non_recovery_reason: Optional[str]
    vendor_irn: Optional[str]
    has_valid_irn: bool
    transaction_date: date


class VATRecoverySummaryResponse(BaseModel):
    """VAT recovery summary response."""
    year: int
    month: int
    total_recoverable: float
    total_non_recoverable: float
    total_input_vat: float
    by_type: dict


# Development Levy Schemas
class DevelopmentLevyRequest(BaseModel):
    """Request to calculate Development Levy."""
    fiscal_year: int
    assessable_profit: Decimal = Field(..., ge=0)
    turnover: Optional[Decimal] = None
    fixed_assets: Optional[Decimal] = None


class DevelopmentLevyResponse(BaseModel):
    """Development Levy calculation response."""
    fiscal_year: int
    assessable_profit: float
    levy_rate_percentage: str
    levy_amount: float
    is_exempt: bool
    exemption_reason: Optional[str]


# PIT Relief Schemas
class PITReliefRequest(BaseModel):
    """Request to create PIT relief document."""
    relief_type: ReliefType
    fiscal_year: int
    claimed_amount: Decimal = Field(..., ge=0)
    annual_rent: Optional[Decimal] = None  # Required for RENT type


class PITReliefResponse(BaseModel):
    """PIT relief document response."""
    id: UUID
    relief_type: str
    fiscal_year: int
    claimed_amount: float
    allowed_amount: Optional[float]
    status: str
    document_url: Optional[str]
    is_verified: bool


class PITReliefVerifyRequest(BaseModel):
    """Request to verify a relief document."""
    approved: bool
    notes: Optional[str] = None


# Business Type Schemas
class BusinessTypeUpdateRequest(BaseModel):
    """Request to update business type."""
    business_type: BusinessType
    annual_turnover: Optional[Decimal] = None
    fixed_assets_value: Optional[Decimal] = None


class BusinessTypeResponse(BaseModel):
    """Business type response with tax implications."""
    entity_id: UUID
    entity_name: str
    business_type: str
    tax_regime: str  # "PIT" or "CIT"
    annual_turnover: Optional[float]
    fixed_assets_value: Optional[float]
    is_development_levy_exempt: bool
    tax_implications: dict


# B2C Reporting Schemas
class B2CSettingsRequest(BaseModel):
    """Request to update B2C reporting settings."""
    enabled: bool
    threshold: Optional[Decimal] = Field(None, ge=0)


class B2CSettingsResponse(BaseModel):
    """B2C reporting settings response."""
    entity_id: str
    b2c_realtime_reporting_enabled: bool
    b2c_reporting_threshold: float
    entity_name: str
    tin: Optional[str]


class B2CTransactionResponse(BaseModel):
    """B2C transaction response."""
    invoice_id: str
    invoice_number: str
    customer_name: Optional[str]
    total_amount: float
    vat_amount: float
    created_at: str
    report_deadline: Optional[str]
    reported_at: Optional[str]
    report_reference: Optional[str]
    is_overdue: bool


class B2CSummaryResponse(BaseModel):
    """B2C reporting summary response."""
    period: dict
    total_reportable: int
    reported_on_time: int
    pending: int
    overdue: int
    total_amount_reported: float
    total_amount_pending: float
    total_amount_overdue: float
    potential_penalty: float
    penalty_per_transaction: float
    max_daily_penalty: float


# Compliance Penalty Schemas
class PenaltyCalculationRequest(BaseModel):
    """Request for penalty calculation."""
    penalty_type: str = Field(..., description="Type of penalty")
    # For late filing
    original_due_date: Optional[date] = Field(None, description="Original due date")
    filing_date: Optional[date] = Field(None, description="Actual filing date")
    # For unregistered vendor
    contract_amount: Optional[Decimal] = Field(None, ge=0, description="Contract amount")
    # For tax remittance
    tax_amount: Optional[Decimal] = Field(None, ge=0, description="Tax amount due")
    due_date: Optional[date] = Field(None, description="Due date for remittance")
    payment_date: Optional[date] = Field(None, description="Actual payment date")


class PenaltyCalculationResponse(BaseModel):
    """Penalty calculation result."""
    penalty_type: str
    base_amount: float
    additional_amount: float
    total_amount: float
    months_late: int
    description: str
    breakdown: List[dict]


class PenaltyRecordResponse(BaseModel):
    """Penalty record response."""
    id: str
    penalty_type: str
    status: str
    base_amount: float
    additional_amount: float
    total_amount: float
    incurred_date: str
    due_date: str
    paid_date: Optional[str]
    description: str
    related_filing_type: Optional[str]
    related_filing_period: Optional[str]


class PenaltySummaryResponse(BaseModel):
    """Penalty summary response."""
    total_penalties: int
    total_incurred: float
    total_paid: float
    total_outstanding: float
    by_type: dict
    penalties: List[dict]


class CreatePenaltyRequest(BaseModel):
    """Request to create a penalty record."""
    penalty_type: str
    base_amount: Decimal = Field(..., ge=0)
    additional_amount: Decimal = Field(default=Decimal("0"), ge=0)
    description: str
    related_filing_type: Optional[str] = None
    related_filing_period: Optional[str] = None
    notes: Optional[str] = None


class UpdatePenaltyStatusRequest(BaseModel):
    """Request to update penalty status."""
    status: str = Field(..., description="New status: paid, waived, disputed")
    payment_reference: Optional[str] = None
    notes: Optional[str] = None


# Peppol BIS 3.0 Export Schemas
class PeppolPartyRequest(BaseModel):
    """Party information for Peppol invoice."""
    name: str
    tin: Optional[str] = None
    registration_name: Optional[str] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country_code: str = "NG"
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None


class PeppolLineItemRequest(BaseModel):
    """Line item for Peppol invoice."""
    item_id: str
    description: str
    quantity: Decimal = Field(..., ge=0)
    unit_code: str = "EA"  # Each
    unit_price: Decimal = Field(..., ge=0)
    vat_rate: Decimal = Field(default=Decimal("7.5"))
    tax_category: str = "S"  # Standard rate
    item_classification_code: Optional[str] = None


class PeppolExportRequest(BaseModel):
    """Request to export invoice in Peppol format."""
    invoice_number: str
    invoice_date: date
    due_date: date
    invoice_type: str = "380"  # Commercial invoice
    seller: PeppolPartyRequest
    buyer: PeppolPartyRequest
    line_items: List[PeppolLineItemRequest]
    currency_code: str = "NGN"
    payment_terms: Optional[str] = None
    nrs_irn: Optional[str] = None
    notes: Optional[str] = None


class PeppolExportResponse(BaseModel):
    """Peppol export response."""
    invoice_number: str
    format: str
    content: str
    csid: str
    qr_code_data: str
    is_compliant: bool


# ===========================================
# HELPER FUNCTIONS
# ===========================================

async def verify_entity_access(
    entity_id: UUID,
    current_user: User,
    db: AsyncSession,
):
    """Verify user has access to entity."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id)
    
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found",
        )
    
    # Check user has access
    has_access = any(
        access.entity_id == entity_id
        for access in current_user.entity_access
    )
    
    if not has_access and current_user.organization_id != entity.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this entity",
        )
    
    return entity


# ===========================================
# BUYER REVIEW ENDPOINTS (72-Hour Window)
# ===========================================

@router.get(
    "/{entity_id}/buyer-review/pending",
    response_model=List[InvoiceBuyerStatusResponse],
    summary="Get invoices pending buyer review",
    tags=["2026 Reform - Buyer Review"],
)
async def get_pending_reviews(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get all invoices awaiting buyer confirmation within 72-hour window."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = BuyerReviewService(db)
    invoices = await service.get_invoices_pending_review(entity_id)
    
    return [
        InvoiceBuyerStatusResponse(
            invoice_id=inv.id,
            invoice_number=inv.invoice_number,
            buyer_status=inv.buyer_status.value if inv.buyer_status else "unknown",
            dispute_deadline=inv.dispute_deadline.isoformat() if inv.dispute_deadline else None,
            buyer_response_at=inv.buyer_response_at.isoformat() if inv.buyer_response_at else None,
            credit_note_id=inv.credit_note_id,
        )
        for inv in invoices
    ]


@router.get(
    "/{entity_id}/buyer-review/overdue",
    response_model=List[InvoiceBuyerStatusResponse],
    summary="Get overdue buyer reviews",
    tags=["2026 Reform - Buyer Review"],
)
async def get_overdue_reviews(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get invoices where 72-hour review window has expired."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = BuyerReviewService(db)
    invoices = await service.get_overdue_reviews(entity_id)
    
    return [
        InvoiceBuyerStatusResponse(
            invoice_id=inv.id,
            invoice_number=inv.invoice_number,
            buyer_status=inv.buyer_status.value if inv.buyer_status else "unknown",
            dispute_deadline=inv.dispute_deadline.isoformat() if inv.dispute_deadline else None,
        )
        for inv in invoices
    ]


@router.get(
    "/{entity_id}/buyer-review/auto-accepted",
    response_model=List[InvoiceBuyerStatusResponse],
    summary="Get auto-accepted invoices",
    tags=["2026 Reform - Buyer Review"],
)
async def get_auto_accepted_invoices(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get invoices auto-accepted after 72-hour window expired without buyer response."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = BuyerReviewService(db)
    invoices = await service.get_auto_accepted_invoices(entity_id)
    
    return [
        InvoiceBuyerStatusResponse(
            invoice_id=inv.id,
            invoice_number=inv.invoice_number,
            buyer_status=inv.buyer_status.value if inv.buyer_status else "unknown",
            dispute_deadline=inv.dispute_deadline.isoformat() if inv.dispute_deadline else None,
            buyer_response_at=inv.buyer_response_at.isoformat() if inv.buyer_response_at else None,
        )
        for inv in invoices
    ]


@router.post(
    "/{entity_id}/buyer-review/{invoice_id}/respond",
    summary="Process buyer response",
    tags=["2026 Reform - Buyer Review"],
)
async def process_buyer_response(
    entity_id: UUID,
    invoice_id: UUID,
    request: BuyerResponseRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Process buyer's acceptance or rejection of invoice.
    
    If rejected, automatically creates a Credit Note.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    service = BuyerReviewService(db)
    
    try:
        result = await service.process_buyer_response(
            invoice_id=invoice_id,
            accepted=request.accepted,
            rejection_reason=request.rejection_reason,
        )
        
        # Audit logging for buyer response
        audit_service = AuditService(db)
        await audit_service.log_action(
            business_entity_id=entity_id,
            entity_type="buyer_review",
            entity_id=str(invoice_id),
            action=AuditAction.UPDATE,
            user_id=current_user.id,
            new_values={
                "accepted": request.accepted,
                "rejection_reason": request.rejection_reason,
            }
        )
        
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{entity_id}/buyer-review/poll-nrs",
    summary="Poll NRS for buyer responses",
    tags=["2026 Reform - Buyer Review"],
)
async def poll_nrs_responses(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Poll NRS API for buyer responses on pending invoices."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = BuyerReviewService(db)
    results = await service.poll_nrs_for_responses(entity_id)
    
    return {
        "processed": len(results),
        "results": results,
    }


@router.get(
    "/{entity_id}/credit-notes",
    response_model=List[CreditNoteResponse],
    summary="Get credit notes",
    tags=["2026 Reform - Buyer Review"],
)
async def get_credit_notes(
    entity_id: UUID,
    status: Optional[CreditNoteStatus] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get all credit notes for an entity."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = BuyerReviewService(db)
    notes = await service.get_credit_notes(entity_id, status)
    
    return [
        CreditNoteResponse(
            id=note.id,
            credit_note_number=note.credit_note_number,
            original_invoice_id=note.original_invoice_id,
            issue_date=note.issue_date,
            reason=note.reason,
            subtotal=float(note.subtotal),
            vat_amount=float(note.vat_amount),
            total_amount=float(note.total_amount),
            status=note.status.value,
            nrs_irn=note.nrs_irn,
        )
        for note in notes
    ]


@router.post(
    "/{entity_id}/credit-notes/{credit_note_id}/submit-nrs",
    summary="Submit credit note to NRS",
    tags=["2026 Reform - Buyer Review"],
)
async def submit_credit_note_to_nrs(
    entity_id: UUID,
    credit_note_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Submit a credit note to NRS for processing."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = BuyerReviewService(db)
    
    try:
        result = await service.submit_credit_note_to_nrs(credit_note_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ===========================================
# VAT RECOVERY ENDPOINTS (Advanced 2026)
# ===========================================

@router.post(
    "/{entity_id}/vat-recovery",
    response_model=VATRecoveryResponse,
    summary="Record VAT recovery",
    tags=["2026 Reform - VAT Recovery"],
)
async def record_vat_recovery(
    entity_id: UUID,
    request: VATRecoveryRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Record an input VAT recovery entry.
    
    Under 2026 Act:
    - Services VAT is now recoverable
    - Capital assets VAT is now recoverable
    - MUST have valid vendor IRN for recovery
    """
    await verify_entity_access(entity_id, current_user, db)
    
    service = VATRecoveryService(db)
    record = await service.record_vat_recovery(
        entity_id=entity_id,
        transaction_id=request.transaction_id,
        vat_amount=request.vat_amount,
        recovery_type=request.recovery_type,
        vendor_irn=request.vendor_irn,
        transaction_date=request.transaction_date,
        description=request.description,
        vendor_name=request.vendor_name,
        vendor_tin=request.vendor_tin,
    )
    
    # Audit logging for VAT recovery
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="vat_recovery",
        entity_id=str(record.id),
        action=AuditAction.CREATE,
        user_id=current_user.id,
        new_values={
            "vat_amount": float(record.vat_amount),
            "recovery_type": record.recovery_type.value,
            "is_recoverable": record.is_recoverable,
            "vendor_irn": record.vendor_irn,
        }
    )
    
    return VATRecoveryResponse(
        id=record.id,
        vat_amount=float(record.vat_amount),
        recovery_type=record.recovery_type.value,
        is_recoverable=record.is_recoverable,
        non_recovery_reason=record.non_recovery_reason,
        vendor_irn=record.vendor_irn,
        has_valid_irn=record.has_valid_irn,
        transaction_date=record.transaction_date,
    )


@router.get(
    "/{entity_id}/vat-recovery/summary/{year}/{month}",
    response_model=VATRecoverySummaryResponse,
    summary="Get VAT recovery summary",
    tags=["2026 Reform - VAT Recovery"],
)
async def get_vat_recovery_summary(
    entity_id: UUID,
    year: int = Path(..., ge=2020, le=2100),
    month: int = Path(..., ge=1, le=12),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get VAT recovery summary for a period.
    
    Shows breakdown by type (stock, services, capital) and
    recoverable vs non-recoverable amounts.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    service = VATRecoveryService(db)
    summary = await service.get_recovery_summary(entity_id, year, month)
    
    return VATRecoverySummaryResponse(**summary)


@router.get(
    "/{entity_id}/vat-recovery/non-recoverable",
    summary="Get non-recoverable VAT records",
    tags=["2026 Reform - VAT Recovery"],
)
async def get_non_recoverable_vat(
    entity_id: UUID,
    year: Optional[int] = None,
    month: Optional[int] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get all VAT flagged as non-recoverable (missing vendor IRN)."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = VATRecoveryService(db)
    records = await service.get_non_recoverable_records(entity_id, year, month)
    
    return [
        VATRecoveryResponse(
            id=r.id,
            vat_amount=float(r.vat_amount),
            recovery_type=r.recovery_type.value,
            is_recoverable=r.is_recoverable,
            non_recovery_reason=r.non_recovery_reason,
            vendor_irn=r.vendor_irn,
            has_valid_irn=r.has_valid_irn,
            transaction_date=r.transaction_date,
        )
        for r in records
    ]


@router.get(
    "/{entity_id}/vat-recovery/vendors-without-irn/{year}",
    summary="Get vendors without NRS e-invoices",
    tags=["2026 Reform - VAT Recovery"],
)
async def get_vendors_without_irn(
    entity_id: UUID,
    year: int = Path(..., ge=2020, le=2100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get list of vendors who didn't provide NRS e-invoices.
    
    Helps identify non-compliant vendors causing lost VAT recovery.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    service = VATRecoveryService(db)
    vendors = await service.get_vendors_without_irn(entity_id, year)
    
    return {
        "year": year,
        "vendors": vendors,
        "recommendation": "Request NRS-compliant e-invoices from these vendors to recover input VAT",
    }


# ===========================================
# ZERO-RATED VAT ENDPOINTS (2026 Reform)
# ===========================================

class ZeroRatedVATSaleRequest(BaseModel):
    """Request to record zero-rated sale."""
    sale_amount: float = Field(..., gt=0, description="Sale amount")
    category: str = Field(..., description="Zero-rated category")
    transaction_date: date
    description: Optional[str] = None


class ZeroRatedVATInputRequest(BaseModel):
    """Request to record input VAT for refund."""
    purchase_amount: float = Field(..., gt=0)
    vat_amount: float = Field(..., gt=0)
    transaction_date: date
    vendor_tin: str
    vendor_irn: Optional[str] = None
    description: Optional[str] = None


@router.get(
    "/zero-rated/categories",
    summary="Get zero-rated VAT categories",
    tags=["2026 Reform - Zero-Rated VAT"],
)
async def get_zero_rated_categories(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get list of zero-rated VAT categories.
    
    Zero-rated supplies have 0% VAT but allow input VAT refund claims.
    """
    from app.services.tax_calculators.minimum_etr_cgt_service import ZeroRatedVATTracker
    
    return {
        "categories": ZeroRatedVATTracker.ZERO_RATED_CATEGORIES,
        "note": "Zero-rated supplies allow sellers to claim input VAT refunds",
    }


@router.post(
    "/{entity_id}/zero-rated/record-sale",
    summary="Record zero-rated sale",
    tags=["2026 Reform - Zero-Rated VAT"],
)
async def record_zero_rated_sale(
    entity_id: UUID,
    request: ZeroRatedVATSaleRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Record a zero-rated sale for VAT refund tracking.
    
    Zero-rated supplies (basic food, education, healthcare, exports)
    have 0% VAT but allow input VAT refund claims.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    from app.services.tax_calculators.minimum_etr_cgt_service import ZeroRatedVATTracker
    
    tracker = ZeroRatedVATTracker()
    
    record = tracker.record_zero_rated_sale(
        sale_amount=Decimal(str(request.sale_amount)),
        category=request.category,
        date=request.transaction_date,
        description=request.description or "",
    )
    
    return {
        "entity_id": str(entity_id),
        **{k: float(v) if isinstance(v, Decimal) else v for k, v in record.items()},
    }


@router.post(
    "/{entity_id}/zero-rated/record-input",
    summary="Record input VAT for refund",
    tags=["2026 Reform - Zero-Rated VAT"],
)
async def record_zero_rated_input(
    entity_id: UUID,
    request: ZeroRatedVATInputRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Record input VAT paid for potential refund.
    
    Only purchases with valid vendor IRN qualify for refund.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    from app.services.tax_calculators.minimum_etr_cgt_service import ZeroRatedVATTracker
    
    tracker = ZeroRatedVATTracker()
    
    record = tracker.record_input_vat(
        purchase_amount=Decimal(str(request.purchase_amount)),
        vat_amount=Decimal(str(request.vat_amount)),
        date=request.transaction_date,
        vendor_tin=request.vendor_tin,
        vendor_irn=request.vendor_irn,
        description=request.description or "",
    )
    
    return {
        "entity_id": str(entity_id),
        **{k: float(v) if isinstance(v, Decimal) else v for k, v in record.items()},
    }


@router.get(
    "/{entity_id}/zero-rated/refund-claim",
    summary="Calculate VAT refund claim",
    tags=["2026 Reform - Zero-Rated VAT"],
)
async def calculate_refund_claim(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Calculate VAT refund claim for zero-rated supplier.
    
    Zero-rated suppliers can claim back input VAT paid on purchases.
    Only purchases with valid NRS IRN are eligible for refund.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    from app.services.tax_calculators.minimum_etr_cgt_service import ZeroRatedVATTracker
    
    tracker = ZeroRatedVATTracker()
    claim = tracker.calculate_refund_claim()
    
    return {
        "entity_id": str(entity_id),
        **claim,
    }


# ===========================================
# MINIMUM ETR ENDPOINTS (15% Large Companies)
# ===========================================

class MinimumETRRequest(BaseModel):
    """Request for Minimum ETR calculation."""
    annual_turnover: float = Field(..., gt=0, description="Annual turnover in NGN")
    assessable_profit: float = Field(..., ge=0, description="Assessable profit in NGN")
    regular_tax_paid: float = Field(..., ge=0, description="Regular CIT/taxes already calculated")
    is_mne_constituent: bool = Field(default=False, description="Part of MNE group with €750M+ revenue")
    mne_group_revenue_eur: Optional[float] = Field(None, description="MNE group revenue in EUR (if applicable)")


@router.get(
    "/minimum-etr/thresholds",
    summary="Get Minimum ETR thresholds",
    tags=["2026 Reform - Minimum ETR"],
)
async def get_minimum_etr_thresholds(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get Minimum ETR thresholds and applicability criteria.
    
    Under Section 57 of the 2026 NTAA:
    - Companies with turnover >= ₦50 billion are subject to 15% minimum ETR
    - MNE constituents with group revenue >= €750 million are also subject
    """
    from app.services.tax_calculators.minimum_etr_cgt_service import (
        MINIMUM_ETR_RATE, TURNOVER_THRESHOLD_NGN, MNE_REVENUE_THRESHOLD_EUR
    )
    
    return {
        "minimum_etr_rate": "15%",
        "turnover_threshold_ngn": float(TURNOVER_THRESHOLD_NGN),
        "turnover_threshold_formatted": "₦50,000,000,000 (₦50 billion)",
        "mne_revenue_threshold_eur": float(MNE_REVENUE_THRESHOLD_EUR),
        "mne_revenue_threshold_formatted": "€750,000,000 (€750 million)",
        "applicability": [
            "Companies with annual turnover >= ₦50 billion",
            "Constituents of MNE groups with aggregate revenue >= €750 million",
        ],
        "compliance_note": "If a company's effective tax rate is below 15%, a top-up tax is required to reach 15%",
        "legislation": "Section 57, Nigeria Tax Administration Act 2026",
    }


@router.post(
    "/minimum-etr/check-applicability",
    summary="Check if subject to Minimum ETR",
    tags=["2026 Reform - Minimum ETR"],
)
async def check_minimum_etr_applicability(
    annual_turnover: float = Query(..., gt=0, description="Annual turnover in NGN"),
    is_mne_constituent: bool = Query(default=False, description="Part of MNE group"),
    mne_group_revenue_eur: Optional[float] = Query(None, description="MNE group revenue in EUR"),
    current_user: User = Depends(get_current_active_user),
):
    """
    Check if a company is subject to Minimum ETR without full calculation.
    
    Quick check based on turnover and MNE status.
    """
    from app.services.tax_calculators.minimum_etr_cgt_service import MinimumETRCalculator
    
    calculator = MinimumETRCalculator()
    is_subject, reason = calculator.check_minimum_etr_applicability(
        annual_turnover=Decimal(str(annual_turnover)),
        is_mne_constituent=is_mne_constituent,
        mne_group_revenue_eur=Decimal(str(mne_group_revenue_eur)) if mne_group_revenue_eur else None,
    )
    
    return {
        "is_subject_to_minimum_etr": is_subject,
        "reason": reason,
        "annual_turnover": annual_turnover,
        "threshold": 50_000_000_000,
    }


@router.post(
    "/{entity_id}/minimum-etr/calculate",
    summary="Calculate Minimum ETR and top-up tax",
    tags=["2026 Reform - Minimum ETR"],
)
async def calculate_minimum_etr(
    entity_id: UUID,
    request: MinimumETRRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Calculate Minimum ETR and any required top-up tax.
    
    For companies subject to the 15% Minimum ETR rule, this calculates:
    - Current effective tax rate
    - ETR shortfall (if below 15%)
    - Top-up tax required to reach 15%
    
    Top-up tax = (15% × Assessable Profit) - Regular Tax Paid
    """
    await verify_entity_access(entity_id, current_user, db)
    
    from app.services.tax_calculators.minimum_etr_cgt_service import MinimumETRCalculator
    
    calculator = MinimumETRCalculator()
    result = calculator.calculate_minimum_etr(
        annual_turnover=Decimal(str(request.annual_turnover)),
        assessable_profit=Decimal(str(request.assessable_profit)),
        regular_tax_paid=Decimal(str(request.regular_tax_paid)),
        is_mne_constituent=request.is_mne_constituent,
        mne_group_revenue_eur=Decimal(str(request.mne_group_revenue_eur)) if request.mne_group_revenue_eur else None,
    )
    
    formatted = calculator.format_result(result)
    
    return {
        "entity_id": str(entity_id),
        **formatted,
    }


# ===========================================
# CAPITAL GAINS TAX (CGT) ENDPOINTS (30%)
# ===========================================

class CGTCalculationRequest(BaseModel):
    """Request for CGT calculation."""
    asset_cost: float = Field(..., gt=0, description="Original cost of asset")
    sale_proceeds: float = Field(..., gt=0, description="Sale proceeds")
    annual_turnover: float = Field(..., gt=0, description="Company's annual turnover")
    fixed_assets_value: float = Field(..., ge=0, description="Company's total fixed assets value")
    acquisition_date: Optional[date] = Field(None, description="Date asset was acquired")
    disposal_date: Optional[date] = Field(None, description="Date asset was disposed")
    apply_indexation: bool = Field(default=True, description="Apply inflation indexation allowance")


@router.get(
    "/cgt/thresholds",
    summary="Get CGT thresholds and rates",
    tags=["2026 Reform - Capital Gains Tax"],
)
async def get_cgt_thresholds(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get CGT rates and small company exemption thresholds.
    
    Under the 2026 reform:
    - CGT rate for large companies: 30%
    - Small company exemption: Turnover ≤ ₦100M AND Fixed Assets ≤ ₦250M
    """
    from app.services.tax_calculators.minimum_etr_cgt_service import (
        CGT_RATE_LARGE, SMALL_COMPANY_TURNOVER, SMALL_COMPANY_ASSETS
    )
    
    return {
        "cgt_rate_large_companies": "30%",
        "cgt_rate_numeric": float(CGT_RATE_LARGE),
        "small_company_exemption": {
            "turnover_threshold": float(SMALL_COMPANY_TURNOVER),
            "turnover_formatted": "₦100,000,000 (₦100 million)",
            "assets_threshold": float(SMALL_COMPANY_ASSETS),
            "assets_formatted": "₦250,000,000 (₦250 million)",
            "note": "Both conditions must be met for exemption (turnover ≤ ₦100M AND assets ≤ ₦250M)",
        },
        "indexation_allowance": "Available for assets held > 1 year",
        "legislation": "Capital Gains Tax (Amendment) Act 2026",
    }


@router.post(
    "/cgt/check-exemption",
    summary="Check small company CGT exemption",
    tags=["2026 Reform - Capital Gains Tax"],
)
async def check_cgt_exemption(
    annual_turnover: float = Query(..., gt=0, description="Annual turnover in NGN"),
    fixed_assets_value: float = Query(..., ge=0, description="Fixed assets value in NGN"),
    current_user: User = Depends(get_current_active_user),
):
    """
    Check if company qualifies for small company CGT exemption.
    
    Small companies (turnover ≤ ₦100M AND fixed assets ≤ ₦250M) are exempt.
    """
    from app.services.tax_calculators.minimum_etr_cgt_service import (
        CGTCalculator, CompanyClassification
    )
    
    calculator = CGTCalculator()
    classification = calculator.classify_company(
        annual_turnover=Decimal(str(annual_turnover)),
        fixed_assets_value=Decimal(str(fixed_assets_value)),
    )
    
    is_exempt = classification == CompanyClassification.SMALL
    
    return {
        "is_exempt": is_exempt,
        "company_classification": classification.value,
        "annual_turnover": annual_turnover,
        "fixed_assets_value": fixed_assets_value,
        "exemption_reason": (
            "Small company exemption: Turnover ≤ ₦100M and Fixed Assets ≤ ₦250M"
            if is_exempt
            else "Company exceeds small company thresholds - subject to 30% CGT"
        ),
    }


@router.post(
    "/{entity_id}/cgt/calculate",
    summary="Calculate Capital Gains Tax on asset disposal",
    tags=["2026 Reform - Capital Gains Tax"],
)
async def calculate_cgt(
    entity_id: UUID,
    request: CGTCalculationRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Calculate Capital Gains Tax on asset disposal.
    
    For large companies (turnover > ₦100M OR assets > ₦250M):
    - CGT rate is 30% on capital gains
    - Indexation allowance available for inflation adjustment
    
    For small companies:
    - CGT exemption applies (0% rate)
    """
    await verify_entity_access(entity_id, current_user, db)
    
    from app.services.tax_calculators.minimum_etr_cgt_service import CGTCalculator
    
    calculator = CGTCalculator()
    result = calculator.calculate_cgt(
        asset_cost=Decimal(str(request.asset_cost)),
        sale_proceeds=Decimal(str(request.sale_proceeds)),
        annual_turnover=Decimal(str(request.annual_turnover)),
        fixed_assets_value=Decimal(str(request.fixed_assets_value)),
        acquisition_date=request.acquisition_date,
        disposal_date=request.disposal_date,
        apply_indexation=request.apply_indexation,
    )
    
    formatted = calculator.format_result(result)
    
    return {
        "entity_id": str(entity_id),
        **formatted,
    }


# ===========================================
# PROGRESSIVE PAYE ENDPOINTS (2026 Tax Bands)
# ===========================================

class PAYEQuickCalculateRequest(BaseModel):
    """Request for quick PAYE calculation."""
    gross_annual_income: float = Field(..., gt=0, description="Gross annual income in NGN")
    basic_salary: Optional[float] = Field(None, description="Basic salary for NHF calculation")
    pension_percentage: float = Field(default=8.0, ge=0, le=20, description="Pension contribution %")
    other_reliefs: float = Field(default=0, ge=0, description="Other tax reliefs")


@router.get(
    "/paye/bands",
    summary="Get 2026 PAYE tax bands",
    tags=["2026 Reform - Progressive PAYE"],
)
async def get_paye_bands(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get the 2026 Nigeria PAYE tax bands.
    
    2026 Tax Reform introduced progressive rates with ₦800,000 tax-free threshold:
    - ₦0 - ₦800,000: 0%
    - ₦800,001 - ₦2,400,000: 15%
    - ₦2,400,001 - ₦4,800,000: 20%
    - ₦4,800,001 - ₦7,200,000: 25%
    - Above ₦7,200,000: 30%
    """
    return {
        "bands": [
            {"lower": 0, "upper": 800_000, "rate": "0%", "description": "Tax-free threshold"},
            {"lower": 800_001, "upper": 2_400_000, "rate": "15%", "description": "First taxable band"},
            {"lower": 2_400_001, "upper": 4_800_000, "rate": "20%", "description": "Second band"},
            {"lower": 4_800_001, "upper": 7_200_000, "rate": "25%", "description": "Third band"},
            {"lower": 7_200_001, "upper": None, "rate": "30%", "description": "Top band (no limit)"},
        ],
        "reliefs": {
            "cra": "₦200,000 + 20% of gross income",
            "pension": "Up to 8% of gross income (employee contribution)",
            "nhf": "2.5% of basic salary",
        },
        "tax_free_threshold": 800_000,
        "tax_free_threshold_formatted": "₦800,000",
        "legislation": "Personal Income Tax (Amendment) Act 2026",
        "effective_date": "January 1, 2026",
    }


@router.post(
    "/paye/quick-calculate",
    summary="Quick PAYE calculation",
    tags=["2026 Reform - Progressive PAYE"],
)
async def quick_calculate_paye(
    request: PAYEQuickCalculateRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    Quick PAYE calculation with automatic reliefs.
    
    Automatically applies:
    - Consolidated Relief Allowance (CRA): ₦200,000 + 20% of gross
    - Pension contribution relief (default 8%)
    - NHF relief (2.5% of basic salary if provided)
    """
    from app.services.tax_calculators.paye_service import PAYECalculator
    
    calculator = PAYECalculator()
    result = calculator.calculate_paye(
        gross_annual_income=Decimal(str(request.gross_annual_income)),
        basic_salary=Decimal(str(request.basic_salary)) if request.basic_salary else None,
        pension_percentage=Decimal(str(request.pension_percentage)),
        other_reliefs=Decimal(str(request.other_reliefs)),
    )
    
    return result


@router.get(
    "/paye/threshold-check",
    summary="Check if income is below tax-free threshold",
    tags=["2026 Reform - Progressive PAYE"],
)
async def check_paye_threshold(
    gross_annual_income: float = Query(..., gt=0, description="Gross annual income in NGN"),
    current_user: User = Depends(get_current_active_user),
):
    """
    Check if income falls below the ₦800,000 tax-free threshold.
    
    After applying CRA (₦200,000 + 20% of gross), if taxable income
    is below ₦800,000, no PAYE tax is due.
    """
    from app.services.tax_calculators.paye_service import PAYECalculator
    
    calculator = PAYECalculator()
    cra = calculator.calculate_cra(Decimal(str(gross_annual_income)))
    taxable_income = max(Decimal("0"), Decimal(str(gross_annual_income)) - cra)
    
    is_exempt = taxable_income <= Decimal("800000")
    
    return {
        "gross_annual_income": gross_annual_income,
        "consolidated_relief": float(cra),
        "taxable_income": float(taxable_income),
        "tax_free_threshold": 800_000,
        "is_tax_exempt": is_exempt,
        "message": (
            "Income is below ₦800,000 tax-free threshold - no PAYE due"
            if is_exempt
            else f"Taxable income (₦{float(taxable_income):,.2f}) exceeds ₦800,000 threshold"
        ),
        "monthly_gross": gross_annual_income / 12,
    }


@router.get(
    "/paye/monthly-breakdown",
    summary="Get monthly PAYE breakdown",
    tags=["2026 Reform - Progressive PAYE"],
)
async def get_monthly_paye_breakdown(
    gross_annual_income: float = Query(..., gt=0, description="Gross annual income"),
    pension_percentage: float = Query(default=8.0, ge=0, le=20),
    current_user: User = Depends(get_current_active_user),
):
    """
    Calculate PAYE with monthly breakdown for payroll.
    
    Useful for employers to understand monthly deductions.
    """
    from app.services.tax_calculators.paye_service import PAYECalculator
    
    calculator = PAYECalculator()
    result = calculator.calculate_paye(
        gross_annual_income=Decimal(str(gross_annual_income)),
        pension_percentage=Decimal(str(pension_percentage)),
    )
    
    annual_tax = result.get("annual_paye_tax", 0)
    monthly_tax = annual_tax / 12
    monthly_gross = gross_annual_income / 12
    monthly_net = monthly_gross - monthly_tax - (gross_annual_income * pension_percentage / 100 / 12)
    
    return {
        **result,
        "monthly_breakdown": {
            "gross_monthly_salary": round(monthly_gross, 2),
            "monthly_paye_deduction": round(monthly_tax, 2),
            "monthly_pension_deduction": round(gross_annual_income * pension_percentage / 100 / 12, 2),
            "estimated_net_monthly": round(monthly_net, 2),
        },
    }


# ===========================================
# DEVELOPMENT LEVY ENDPOINTS (4% Consolidated)
# ===========================================

@router.post(
    "/{entity_id}/development-levy/calculate",
    response_model=DevelopmentLevyResponse,
    summary="Calculate Development Levy",
    tags=["2026 Reform - Development Levy"],
)
async def calculate_development_levy(
    entity_id: UUID,
    request: DevelopmentLevyRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Calculate 4% Development Levy for a fiscal year.
    
    Consolidates TET, Police Fund, and other levies.
    Exempt if: turnover <= ₦100M AND fixed assets <= ₦250M
    """
    await verify_entity_access(entity_id, current_user, db)
    
    service = DevelopmentLevyService(db)
    result = await service.calculate_development_levy(
        entity_id=entity_id,
        fiscal_year=request.fiscal_year,
        assessable_profit=request.assessable_profit,
        turnover=request.turnover,
        fixed_assets=request.fixed_assets,
    )
    
    return DevelopmentLevyResponse(
        fiscal_year=result["fiscal_year"],
        assessable_profit=result["assessable_profit"],
        levy_rate_percentage=result["levy_rate_percentage"],
        levy_amount=result["levy_amount"],
        is_exempt=result["is_exempt"],
        exemption_reason=result["exemption_reason"],
    )


@router.post(
    "/{entity_id}/development-levy/save",
    summary="Save Development Levy record",
    tags=["2026 Reform - Development Levy"],
)
async def save_development_levy(
    entity_id: UUID,
    request: DevelopmentLevyRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Save a Development Levy calculation for filing."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = DevelopmentLevyService(db)
    record = await service.save_development_levy_record(
        entity_id=entity_id,
        fiscal_year=request.fiscal_year,
        assessable_profit=request.assessable_profit,
        turnover=request.turnover,
        fixed_assets=request.fixed_assets,
    )
    
    # Audit logging for development levy creation
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="development_levy",
        entity_id=str(record.id),
        action=AuditAction.CREATE,
        user_id=current_user.id,
        new_values={
            "fiscal_year": record.fiscal_year,
            "levy_amount": float(record.levy_amount),
            "is_exempt": record.is_exempt,
            "assessable_profit": float(request.assessable_profit),
        }
    )
    
    return {
        "id": str(record.id),
        "fiscal_year": record.fiscal_year,
        "levy_amount": float(record.levy_amount),
        "is_exempt": record.is_exempt,
        "is_filed": record.is_filed,
    }


@router.get(
    "/{entity_id}/development-levy/{fiscal_year}",
    summary="Get Development Levy record",
    tags=["2026 Reform - Development Levy"],
)
async def get_development_levy(
    entity_id: UUID,
    fiscal_year: int = Path(..., ge=2020, le=2100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get Development Levy record for a fiscal year."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = DevelopmentLevyService(db)
    record = await service.get_development_levy_record(entity_id, fiscal_year)
    
    if not record:
        raise HTTPException(status_code=404, detail="Development Levy record not found")
    
    return {
        "id": str(record.id),
        "fiscal_year": record.fiscal_year,
        "assessable_profit": float(record.assessable_profit),
        "levy_rate": f"{float(record.levy_rate) * 100}%",
        "levy_amount": float(record.levy_amount),
        "is_exempt": record.is_exempt,
        "exemption_reason": record.exemption_reason,
        "is_filed": record.is_filed,
        "filed_at": record.filed_at.isoformat() if record.filed_at else None,
    }


@router.get(
    "/{entity_id}/development-levy/compare-old-regime",
    summary="Compare to old tax regime",
    tags=["2026 Reform - Development Levy"],
)
async def compare_development_levy_regimes(
    entity_id: UUID,
    assessable_profit: Decimal = Query(..., ge=0),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Compare Development Levy to old separate TET and Police Fund."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = DevelopmentLevyService(db)
    comparison = service.compare_to_old_regime(assessable_profit)
    
    return comparison


# ===========================================
# PIT RELIEF ENDPOINTS (CRA Abolished)
# ===========================================

@router.post(
    "/{entity_id}/pit-reliefs",
    response_model=PITReliefResponse,
    summary="Create PIT relief document",
    tags=["2026 Reform - PIT Reliefs"],
)
async def create_pit_relief(
    entity_id: UUID,
    request: PITReliefRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Create a PIT relief document.
    
    Under 2026 reforms, CRA is abolished. All reliefs require documentary proof.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    # Validate rent relief requires annual_rent
    if request.relief_type == ReliefType.RENT and not request.annual_rent:
        raise HTTPException(
            status_code=400,
            detail="annual_rent is required for Rent Relief type",
        )
    
    service = PITReliefService(db)
    document = await service.create_relief_document(
        entity_id=entity_id,
        user_id=current_user.id,
        relief_type=request.relief_type,
        fiscal_year=request.fiscal_year,
        claimed_amount=request.claimed_amount,
        annual_rent=request.annual_rent,
    )
    
    # Audit logging for PIT relief creation
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="pit_relief",
        entity_id=str(document.id),
        action=AuditAction.CREATE,
        user_id=current_user.id,
        new_values={
            "relief_type": document.relief_type.value,
            "fiscal_year": document.fiscal_year,
            "claimed_amount": float(document.claimed_amount),
            "status": document.status.value,
        }
    )
    
    return PITReliefResponse(
        id=document.id,
        relief_type=document.relief_type.value,
        fiscal_year=document.fiscal_year,
        claimed_amount=float(document.claimed_amount),
        allowed_amount=float(document.allowed_amount) if document.allowed_amount else None,
        status=document.status.value,
        document_url=document.document_url,
        is_verified=document.is_verified,
    )


@router.post(
    "/{entity_id}/pit-reliefs/{relief_id}/upload",
    summary="Upload relief supporting document",
    tags=["2026 Reform - PIT Reliefs"],
)
async def upload_relief_document(
    entity_id: UUID,
    relief_id: UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Upload supporting document for a PIT relief claim."""
    await verify_entity_access(entity_id, current_user, db)
    
    # Validate file type
    allowed_types = ["application/pdf", "image/jpeg", "image/png"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed: PDF, JPEG, PNG",
        )
    
    content = await file.read()
    
    service = PITReliefService(db)
    document = await service.upload_document(
        relief_id=relief_id,
        file_content=content,
        filename=file.filename,
        content_type=file.content_type,
    )
    
    return {
        "success": True,
        "document_url": document.document_url,
        "document_name": document.document_name,
    }


@router.post(
    "/{entity_id}/pit-reliefs/{relief_id}/verify",
    summary="Verify relief document",
    tags=["2026 Reform - PIT Reliefs"],
)
async def verify_pit_relief(
    entity_id: UUID,
    relief_id: UUID,
    request: PITReliefVerifyRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Verify/approve a PIT relief document."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = PITReliefService(db)
    
    try:
        document = await service.verify_relief(
            relief_id=relief_id,
            verified_by=current_user.id,
            approved=request.approved,
            notes=request.notes,
        )
        
        # Audit logging for PIT relief verification
        audit_service = AuditService(db)
        await audit_service.log_action(
            business_entity_id=entity_id,
            entity_type="pit_relief",
            entity_id=str(relief_id),
            action=AuditAction.APPROVE if request.approved else AuditAction.REJECT,
            user_id=current_user.id,
            new_values={
                "approved": request.approved,
                "notes": request.notes,
                "status": document.status.value,
                "verified_at": document.verified_at.isoformat() if document.verified_at else None,
            }
        )
        
        return {
            "success": True,
            "status": document.status.value,
            "verified_at": document.verified_at.isoformat() if document.verified_at else None,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/{entity_id}/pit-reliefs/my-reliefs",
    response_model=List[PITReliefResponse],
    summary="Get my relief documents",
    tags=["2026 Reform - PIT Reliefs"],
)
async def get_my_pit_reliefs(
    entity_id: UUID,
    fiscal_year: Optional[int] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get current user's PIT relief documents."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = PITReliefService(db)
    documents = await service.get_user_reliefs(entity_id, current_user.id, fiscal_year)
    
    return [
        PITReliefResponse(
            id=doc.id,
            relief_type=doc.relief_type.value,
            fiscal_year=doc.fiscal_year,
            claimed_amount=float(doc.claimed_amount),
            allowed_amount=float(doc.allowed_amount) if doc.allowed_amount else None,
            status=doc.status.value,
            document_url=doc.document_url,
            is_verified=doc.is_verified,
        )
        for doc in documents
    ]


@router.get(
    "/{entity_id}/pit-reliefs/summary/{fiscal_year}",
    summary="Get relief summary",
    tags=["2026 Reform - PIT Reliefs"],
)
async def get_pit_relief_summary(
    entity_id: UUID,
    fiscal_year: int = Path(..., ge=2020, le=2100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get PIT relief summary for a fiscal year."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = PITReliefService(db)
    summary = await service.get_relief_summary(entity_id, current_user.id, fiscal_year)
    
    return summary


@router.get(
    "/{entity_id}/pit-reliefs/pending-verification",
    response_model=List[PITReliefResponse],
    summary="Get pending verifications",
    tags=["2026 Reform - PIT Reliefs"],
)
async def get_pending_verifications(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get all relief documents pending verification (for admins)."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = PITReliefService(db)
    documents = await service.get_pending_verifications(entity_id)
    
    return [
        PITReliefResponse(
            id=doc.id,
            relief_type=doc.relief_type.value,
            fiscal_year=doc.fiscal_year,
            claimed_amount=float(doc.claimed_amount),
            allowed_amount=float(doc.allowed_amount) if doc.allowed_amount else None,
            status=doc.status.value,
            document_url=doc.document_url,
            is_verified=doc.is_verified,
        )
        for doc in documents
    ]


@router.get(
    "/pit-reliefs/types",
    summary="Get relief types info",
    tags=["2026 Reform - PIT Reliefs"],
)
async def get_relief_types():
    """Get information about available PIT relief types."""
    service = PITReliefService(None)
    return service.get_relief_types_info()


# ===========================================
# BUSINESS TYPE ENDPOINTS (PIT vs CIT Toggle)
# ===========================================

@router.get(
    "/{entity_id}/business-type",
    response_model=BusinessTypeResponse,
    summary="Get business type and tax implications",
    tags=["2026 Reform - Business Type"],
)
async def get_business_type(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get entity's business type and its tax regime implications.
    
    Business Name = Personal Income Tax (PIT)
    Limited Company = Company Income Tax (CIT)
    """
    entity = await verify_entity_access(entity_id, current_user, db)
    
    is_pit = entity.business_type == BusinessType.BUSINESS_NAME
    
    tax_implications = {
        "tax_type": "PIT (Personal Income Tax)" if is_pit else "CIT (Company Income Tax)",
        "rates": (
            "0%/15%/20%/25%/30% progressive bands" if is_pit
            else "0%/20%/30% based on company size"
        ),
        "development_levy": "Not applicable" if is_pit else (
            "Exempt" if entity.is_development_levy_exempt else "4% of assessable profit"
        ),
        "reliefs": (
            "Document-backed reliefs (Rent, Insurance, NHF, Pension, etc.)" if is_pit
            else "Capital allowances, business expenses"
        ),
        "filing_deadline": (
            "31st March (individuals)" if is_pit
            else "Within 6 months of accounting year end"
        ),
    }
    
    return BusinessTypeResponse(
        entity_id=entity.id,
        entity_name=entity.name,
        business_type=entity.business_type.value,
        tax_regime="PIT" if is_pit else "CIT",
        annual_turnover=float(entity.annual_turnover) if entity.annual_turnover else None,
        fixed_assets_value=float(entity.fixed_assets_value) if entity.fixed_assets_value else None,
        is_development_levy_exempt=entity.is_development_levy_exempt,
        tax_implications=tax_implications,
    )


@router.patch(
    "/{entity_id}/business-type",
    response_model=BusinessTypeResponse,
    summary="Update business type",
    tags=["2026 Reform - Business Type"],
)
async def update_business_type(
    entity_id: UUID,
    request: BusinessTypeUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Update entity's business type.
    
    This affects whether PIT or CIT rules apply.
    """
    entity = await verify_entity_access(entity_id, current_user, db)
    
    # Update business type
    entity.business_type = request.business_type
    
    if request.annual_turnover is not None:
        entity.annual_turnover = request.annual_turnover
    if request.fixed_assets_value is not None:
        entity.fixed_assets_value = request.fixed_assets_value
    
    # Recalculate Development Levy exemption
    dev_service = DevelopmentLevyService(db)
    await dev_service.update_entity_thresholds(
        entity_id=entity_id,
        annual_turnover=entity.annual_turnover,
        fixed_assets_value=entity.fixed_assets_value,
    )
    
    await db.refresh(entity)
    
    is_pit = entity.business_type == BusinessType.BUSINESS_NAME
    
    tax_implications = {
        "tax_type": "PIT (Personal Income Tax)" if is_pit else "CIT (Company Income Tax)",
        "rates": (
            "0%/15%/20%/25%/30% progressive bands" if is_pit
            else "0%/20%/30% based on company size"
        ),
        "development_levy": "Not applicable" if is_pit else (
            "Exempt" if entity.is_development_levy_exempt else "4% of assessable profit"
        ),
    }
    
    return BusinessTypeResponse(
        entity_id=entity.id,
        entity_name=entity.name,
        business_type=entity.business_type.value,
        tax_regime="PIT" if is_pit else "CIT",
        annual_turnover=float(entity.annual_turnover) if entity.annual_turnover else None,
        fixed_assets_value=float(entity.fixed_assets_value) if entity.fixed_assets_value else None,
        is_development_levy_exempt=entity.is_development_levy_exempt,
        tax_implications=tax_implications,
    )


@router.get(
    "/business-types/comparison",
    summary="Compare Business Name vs Limited Company",
    tags=["2026 Reform - Business Type"],
)
async def compare_business_types():
    """
    Get comparison between Business Name and Limited Company tax treatment.
    
    Helps users decide which structure suits their business.
    """
    return {
        "business_name": {
            "registration": "CAC Business Name registration",
            "tax_type": "Personal Income Tax (PIT)",
            "rates": {
                "first_₦800,000": "0%",
                "next_₦2,400,000": "15%",
                "next_₦4,000,000": "20%",
                "next_₦7,000,000": "25%",
                "above_₦14,200,000": "30%",
            },
            "development_levy": "Not applicable",
            "liability": "Unlimited personal liability",
            "suitable_for": "Freelancers, small traders, sole proprietors",
        },
        "limited_company": {
            "registration": "CAC Company registration",
            "tax_type": "Company Income Tax (CIT)",
            "rates": {
                "turnover_≤₦25M": "0% (Small company)",
                "turnover_₦25M-₦100M": "20% (Medium company)",
                "turnover_>₦100M": "30% (Large company)",
            },
            "development_levy": "4% of assessable profit (exempt if turnover ≤ ₦100M AND assets ≤ ₦250M)",
            "liability": "Limited to share capital",
            "suitable_for": "Growing businesses, those seeking investment, contractors",
        },
        "2026_reform_note": "The 2026 reforms introduced clearer distinctions and simplified compliance for both structures.",
    }


# ===========================================
# TIN VALIDATION ENDPOINTS (NRS TaxID Portal)
# ===========================================

class TINValidationRequest(BaseModel):
    """Request to validate a TIN."""
    tin: str = Field(..., min_length=10, max_length=18, description="Tax Identification Number to validate")
    entity_type: Optional[str] = Field(
        None, 
        description="Type of entity: individual, business_name, company, incorporated_trustee, limited_partnership, llp"
    )
    search_term: Optional[str] = Field(
        None,
        description="NIN for individuals, or business name for corporate entities"
    )


class TINValidationResponse(BaseModel):
    """Response from TIN validation."""
    is_valid: bool
    tin: str
    status: str
    entity_type: Optional[str] = None
    registered_name: Optional[str] = None
    rc_number: Optional[str] = None
    registration_date: Optional[str] = None
    address: Optional[str] = None
    tax_office: Optional[str] = None
    vat_registered: Optional[bool] = None
    message: str
    validated_at: Optional[str] = None


class BulkTINValidationRequest(BaseModel):
    """Request to validate multiple TINs."""
    tins: List[str] = Field(..., min_length=1, max_length=50, description="List of TINs to validate")


class BulkTINValidationResponse(BaseModel):
    """Response from bulk TIN validation."""
    total: int
    valid_count: int
    invalid_count: int
    results: List[TINValidationResponse]


@router.post(
    "/tin/validate",
    response_model=TINValidationResponse,
    summary="Validate a TIN",
    tags=["2026 Reform - TIN Validation"],
)
async def validate_tin(
    request: TINValidationRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Validate a Tax Identification Number (TIN) via NRS TaxID Portal.
    
    2026 Compliance Requirement:
    - Mandatory TIN validation for all individuals and businesses
    - All vendors/suppliers must have valid TINs before contracts
    - Failure to validate can result in ₦5,000,000 penalty
    
    Portal: https://taxid.nrs.gov.ng/
    """
    service = TINValidationService(db)
    
    # Convert entity_type string to enum if provided
    entity_type = None
    if request.entity_type:
        try:
            entity_type = TINEntityType(request.entity_type)
        except ValueError:
            pass  # Invalid entity type, proceed without it
    
    result = await service.validate_tin(
        tin=request.tin,
        entity_type=entity_type,
        search_term=request.search_term,
    )
    
    return TINValidationResponse(
        is_valid=result.is_valid,
        tin=result.tin,
        status=result.status.value,
        entity_type=result.entity_type.value if result.entity_type else None,
        registered_name=result.registered_name,
        rc_number=result.rc_number,
        registration_date=result.registration_date,
        address=result.address,
        tax_office=result.tax_office,
        vat_registered=result.vat_registered,
        message=result.message,
        validated_at=result.validated_at.isoformat() if result.validated_at else None,
    )


@router.post(
    "/tin/validate-bulk",
    response_model=BulkTINValidationResponse,
    summary="Bulk validate TINs",
    tags=["2026 Reform - TIN Validation"],
)
async def validate_tins_bulk(
    request: BulkTINValidationRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Validate multiple TINs in a single request.
    
    Useful for bulk vendor/customer onboarding.
    Maximum 50 TINs per request.
    """
    service = TINValidationService(db)
    
    results = []
    valid_count = 0
    invalid_count = 0
    
    for tin in request.tins:
        result = await service.validate_tin(tin=tin)
        
        if result.is_valid:
            valid_count += 1
        else:
            invalid_count += 1
        
        results.append(TINValidationResponse(
            is_valid=result.is_valid,
            tin=result.tin,
            status=result.status.value,
            entity_type=result.entity_type.value if result.entity_type else None,
            registered_name=result.registered_name,
            rc_number=result.rc_number,
            registration_date=result.registration_date,
            address=result.address,
            tax_office=result.tax_office,
            vat_registered=result.vat_registered,
            message=result.message,
            validated_at=result.validated_at.isoformat() if result.validated_at else None,
        ))
    
    return BulkTINValidationResponse(
        total=len(request.tins),
        valid_count=valid_count,
        invalid_count=invalid_count,
        results=results,
    )


@router.get(
    "/tin/entity-types",
    summary="Get TIN entity types",
    tags=["2026 Reform - TIN Validation"],
)
async def get_tin_entity_types():
    """
    Get list of entity types supported for TIN validation.
    
    Each entity type has different validation requirements:
    - Individual: Requires NIN (National Identification Number)
    - Corporate: Requires CAC registration details
    """
    return {
        "entity_types": [
            {
                "value": "individual",
                "label": "Individual",
                "description": "Individual taxpayer with NIN",
                "requires": "NIN (National Identification Number)",
            },
            {
                "value": "business_name",
                "label": "Business Name",
                "description": "Sole Proprietorship registered with CAC",
                "requires": "Business Name registration number",
            },
            {
                "value": "company",
                "label": "Limited Liability Company",
                "description": "Company registered with CAC",
                "requires": "RC Number",
            },
            {
                "value": "incorporated_trustee",
                "label": "Incorporated Trustee",
                "description": "NGOs, Churches, Associations",
                "requires": "IT Number",
            },
            {
                "value": "limited_partnership",
                "label": "Limited Partnership",
                "description": "Partnership with limited liability partners",
                "requires": "LP Number",
            },
            {
                "value": "llp",
                "label": "Limited Liability Partnership",
                "description": "Professional partnership with LLP registration",
                "requires": "LLP Number",
            },
        ],
        "portal_url": "https://taxid.nrs.gov.ng/",
        "compliance_note": "2026 NTAA requires TIN validation for all business transactions above ₦100,000",
    }


# ===========================================
# B2C REAL-TIME REPORTING ENDPOINTS
# ===========================================

@router.get(
    "/b2c/thresholds",
    summary="Get B2C reporting thresholds",
    tags=["2026 Reform - B2C Reporting"],
)
async def get_b2c_thresholds():
    """
    Get B2C reporting compliance thresholds.
    
    2026 Compliance:
    - B2C transactions > ₦50,000 must be reported within 24 hours
    - Penalty: ₦10,000 per late transaction (max ₦500,000/day)
    """
    return {
        "default_threshold": 50000.00,
        "reporting_window_hours": 24,
        "late_penalty_per_transaction": 10000.00,
        "max_daily_penalty": 500000.00,
        "description": "B2C transactions over ₦50,000 must be reported to NRS within 24 hours",
        "compliance_reference": "Nigeria Tax Administration Act 2025, Section 42",
    }


@router.get(
    "/{entity_id}/b2c/settings",
    response_model=B2CSettingsResponse,
    summary="Get B2C reporting settings",
    tags=["2026 Reform - B2C Reporting"],
)
async def get_b2c_settings(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get B2C real-time reporting settings for an entity."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = B2CReportingService(db)
    settings = await service.get_entity_settings(entity_id)
    
    return B2CSettingsResponse(**settings)


@router.put(
    "/{entity_id}/b2c/settings",
    response_model=B2CSettingsResponse,
    summary="Update B2C reporting settings",
    tags=["2026 Reform - B2C Reporting"],
)
async def update_b2c_settings(
    entity_id: UUID,
    request: B2CSettingsRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Update B2C real-time reporting settings for an entity."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = B2CReportingService(db)
    settings = await service.update_entity_settings(
        entity_id=entity_id,
        enabled=request.enabled,
        threshold=request.threshold,
    )
    
    return B2CSettingsResponse(**settings)


@router.get(
    "/{entity_id}/b2c/pending",
    response_model=List[B2CTransactionResponse],
    summary="Get pending B2C reports",
    tags=["2026 Reform - B2C Reporting"],
)
async def get_pending_b2c_reports(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get B2C transactions pending reporting to NRS."""
    await verify_entity_access(entity_id, current_user, db)
    
    from datetime import datetime
    
    service = B2CReportingService(db)
    invoices = await service.get_pending_b2c_reports(entity_id)
    now = datetime.utcnow()
    
    return [
        B2CTransactionResponse(
            invoice_id=str(inv.id),
            invoice_number=inv.invoice_number,
            customer_name=inv.customer.name if inv.customer else "Walk-in Customer",
            total_amount=float(inv.total_amount),
            vat_amount=float(inv.vat_amount),
            created_at=inv.created_at.isoformat(),
            report_deadline=inv.b2c_report_deadline.isoformat() if inv.b2c_report_deadline else None,
            reported_at=None,
            report_reference=None,
            is_overdue=inv.b2c_report_deadline < now if inv.b2c_report_deadline else False,
        )
        for inv in invoices
    ]


@router.get(
    "/{entity_id}/b2c/overdue",
    response_model=List[B2CTransactionResponse],
    summary="Get overdue B2C reports",
    tags=["2026 Reform - B2C Reporting"],
)
async def get_overdue_b2c_reports(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get B2C transactions past 24-hour reporting deadline."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = B2CReportingService(db)
    invoices = await service.get_overdue_b2c_reports(entity_id)
    
    return [
        B2CTransactionResponse(
            invoice_id=str(inv.id),
            invoice_number=inv.invoice_number,
            customer_name=inv.customer.name if inv.customer else "Walk-in Customer",
            total_amount=float(inv.total_amount),
            vat_amount=float(inv.vat_amount),
            created_at=inv.created_at.isoformat(),
            report_deadline=inv.b2c_report_deadline.isoformat() if inv.b2c_report_deadline else None,
            reported_at=None,
            report_reference=None,
            is_overdue=True,
        )
        for inv in invoices
    ]


@router.get(
    "/{entity_id}/b2c/reported",
    response_model=List[B2CTransactionResponse],
    summary="Get reported B2C transactions",
    tags=["2026 Reform - B2C Reporting"],
)
async def get_reported_b2c_transactions(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get successfully reported B2C transactions."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = B2CReportingService(db)
    invoices = await service.get_reported_b2c_transactions(entity_id)
    
    return [
        B2CTransactionResponse(
            invoice_id=str(inv.id),
            invoice_number=inv.invoice_number,
            customer_name=inv.customer.name if inv.customer else "Walk-in Customer",
            total_amount=float(inv.total_amount),
            vat_amount=float(inv.vat_amount),
            created_at=inv.created_at.isoformat(),
            report_deadline=inv.b2c_report_deadline.isoformat() if inv.b2c_report_deadline else None,
            reported_at=inv.b2c_reported_at.isoformat() if inv.b2c_reported_at else None,
            report_reference=inv.b2c_report_reference,
            is_overdue=False,
        )
        for inv in invoices
    ]


@router.post(
    "/{entity_id}/b2c/{invoice_id}/report",
    summary="Submit B2C transaction to NRS",
    tags=["2026 Reform - B2C Reporting"],
)
async def submit_b2c_report(
    entity_id: UUID,
    invoice_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Submit a single B2C transaction to NRS for real-time reporting."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = B2CReportingService(db)
    
    try:
        result = await service.submit_b2c_report(invoice_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{entity_id}/b2c/submit-all",
    summary="Submit all pending B2C reports",
    tags=["2026 Reform - B2C Reporting"],
)
async def submit_all_b2c_reports(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Submit all pending B2C transactions to NRS."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = B2CReportingService(db)
    result = await service.submit_all_pending_reports(entity_id)
    
    return result


@router.get(
    "/{entity_id}/b2c/summary/{year}/{month}",
    response_model=B2CSummaryResponse,
    summary="Get B2C reporting summary",
    tags=["2026 Reform - B2C Reporting"],
)
async def get_b2c_summary(
    entity_id: UUID,
    year: int = Path(..., ge=2020, le=2100),
    month: int = Path(..., ge=1, le=12),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get B2C reporting summary for a month."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = B2CReportingService(db)
    summary = await service.get_b2c_summary(entity_id, year, month)
    
    return B2CSummaryResponse(**summary)


# ===========================================
# COMPLIANCE PENALTIES ENDPOINTS
# ===========================================

@router.get(
    "/penalties/rates",
    summary="Get penalty rates",
    tags=["2026 Reform - Compliance Penalties"],
)
async def get_penalty_rates():
    """
    Get current compliance penalty rates per 2026 Tax Reform.
    
    Penalty Schedule:
    - Late Filing: ₦100,000 (first month) + ₦50,000 (each subsequent month)
    - Unregistered Vendor Contract: ₦5,000,000
    - B2C Late Reporting: ₦10,000 per transaction (max ₦500,000/day)
    - E-Invoice Non-Compliance: ₦50,000 per invoice
    - Invalid TIN: ₦25,000 per occurrence
    - Missing Records: ₦100,000 per year
    - NRS Access Denial: ₦1,000,000
    - Tax Remittance (VAT/PAYE/WHT): 10% + 2% monthly interest
    """
    return {
        "penalty_types": [pt.value for pt in PenaltyType],
        "rates": {
            penalty_type.value: {
                k: float(v) if isinstance(v, Decimal) else v
                for k, v in rates.items()
            }
            for penalty_type, rates in PENALTY_SCHEDULE.items()
        },
        "compliance_reference": "Nigeria Tax Administration Act 2026",
    }


@router.post(
    "/penalties/calculate",
    response_model=PenaltyCalculationResponse,
    summary="Calculate compliance penalty",
    tags=["2026 Reform - Compliance Penalties"],
)
async def calculate_penalty(
    request: PenaltyCalculationRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Calculate penalty for a specific compliance violation.
    
    Supports:
    - late_filing: Requires original_due_date, filing_date
    - unregistered_vendor: Requires contract_amount
    - vat_non_remittance, paye_non_remittance, wht_non_remittance: 
      Requires tax_amount, due_date, payment_date
    """
    service = CompliancePenaltyService(db)
    
    try:
        penalty_type = PenaltyType(request.penalty_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid penalty type. Valid types: {[pt.value for pt in PenaltyType]}",
        )
    
    if penalty_type == PenaltyType.LATE_FILING:
        if not request.original_due_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="original_due_date is required for late filing calculation",
            )
        result = service.calculate_late_filing_penalty(
            original_due_date=request.original_due_date,
            filing_date=request.filing_date,
        )
    
    elif penalty_type == PenaltyType.UNREGISTERED_VENDOR:
        if not request.contract_amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="contract_amount is required for unregistered vendor calculation",
            )
        result = service.calculate_unregistered_vendor_penalty(
            contract_amount=request.contract_amount,
        )
    
    elif penalty_type in [
        PenaltyType.VAT_NON_REMITTANCE,
        PenaltyType.PAYE_NON_REMITTANCE,
        PenaltyType.WHT_NON_REMITTANCE,
    ]:
        if not request.tax_amount or not request.due_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="tax_amount and due_date are required for tax remittance calculation",
            )
        result = service.calculate_tax_remittance_penalty(
            penalty_type=penalty_type,
            tax_amount=request.tax_amount,
            due_date=request.due_date,
            payment_date=request.payment_date,
        )
    
    else:
        # For other penalty types, return their fixed rates
        rates = PENALTY_SCHEDULE.get(penalty_type, {})
        amount = rates.get("fixed_amount") or rates.get("per_occurrence") or rates.get("per_invoice") or rates.get("per_year") or Decimal("0")
        result = PenaltyCalculation(
            penalty_type=penalty_type,
            base_amount=amount,
            additional_amount=Decimal("0"),
            total_amount=amount,
            months_late=0,
            description=rates.get("description", f"Penalty for {penalty_type.value}"),
            breakdown=[{"type": "fixed", "amount": float(amount)}],
        )
    
    return PenaltyCalculationResponse(
        penalty_type=result.penalty_type.value,
        base_amount=float(result.base_amount),
        additional_amount=float(result.additional_amount),
        total_amount=float(result.total_amount),
        months_late=result.months_late,
        description=result.description,
        breakdown=result.breakdown,
    )


# Import PenaltyCalculation for the calculate endpoint
from app.services.compliance_penalty_service import PenaltyCalculation


@router.get(
    "/{entity_id}/penalties",
    response_model=List[PenaltyRecordResponse],
    summary="Get entity penalties",
    tags=["2026 Reform - Compliance Penalties"],
)
async def get_entity_penalties(
    entity_id: UUID,
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    start_date: Optional[date] = Query(None, description="Start date filter"),
    end_date: Optional[date] = Query(None, description="End date filter"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get all penalty records for an entity."""
    await verify_entity_access(entity_id, current_user, db)
    
    status_enum = None
    if status_filter:
        try:
            status_enum = PenaltyStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status. Valid values: {[s.value for s in PenaltyStatus]}",
            )
    
    service = CompliancePenaltyService(db)
    penalties = await service.get_entity_penalties(
        entity_id=entity_id,
        status=status_enum,
        start_date=start_date,
        end_date=end_date,
    )
    
    return [
        PenaltyRecordResponse(
            id=str(p.id),
            penalty_type=p.penalty_type.value,
            status=p.status.value,
            base_amount=float(p.base_amount),
            additional_amount=float(p.additional_amount),
            total_amount=float(p.total_amount),
            incurred_date=p.incurred_date.isoformat(),
            due_date=p.due_date.isoformat(),
            paid_date=p.paid_date.isoformat() if p.paid_date else None,
            description=p.description,
            related_filing_type=p.related_filing_type,
            related_filing_period=p.related_filing_period,
        )
        for p in penalties
    ]


@router.get(
    "/{entity_id}/penalties/summary",
    response_model=PenaltySummaryResponse,
    summary="Get penalty summary",
    tags=["2026 Reform - Compliance Penalties"],
)
async def get_penalty_summary(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get penalty summary for an entity."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = CompliancePenaltyService(db)
    summary = await service.get_penalty_summary(entity_id)
    
    return PenaltySummaryResponse(**summary)


@router.post(
    "/{entity_id}/penalties",
    response_model=PenaltyRecordResponse,
    summary="Create penalty record",
    tags=["2026 Reform - Compliance Penalties"],
)
async def create_penalty_record(
    entity_id: UUID,
    request: CreatePenaltyRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Create a new penalty record for an entity."""
    await verify_entity_access(entity_id, current_user, db)
    
    try:
        penalty_type = PenaltyType(request.penalty_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid penalty type. Valid types: {[pt.value for pt in PenaltyType]}",
        )
    
    service = CompliancePenaltyService(db)
    
    # Create a calculation object for the record
    calculation = PenaltyCalculation(
        penalty_type=penalty_type,
        base_amount=request.base_amount,
        additional_amount=request.additional_amount,
        total_amount=request.base_amount + request.additional_amount,
        months_late=0,
        description=request.description,
        breakdown=[],
    )
    
    record = await service.create_penalty_record(
        entity_id=entity_id,
        calculation=calculation,
        related_filing_type=request.related_filing_type,
        related_filing_period=request.related_filing_period,
        notes=request.notes,
    )
    
    return PenaltyRecordResponse(
        id=str(record.id),
        penalty_type=record.penalty_type.value,
        status=record.status.value,
        base_amount=float(record.base_amount),
        additional_amount=float(record.additional_amount),
        total_amount=float(record.total_amount),
        incurred_date=record.incurred_date.isoformat(),
        due_date=record.due_date.isoformat(),
        paid_date=record.paid_date.isoformat() if record.paid_date else None,
        description=record.description,
        related_filing_type=record.related_filing_type,
        related_filing_period=record.related_filing_period,
    )


@router.put(
    "/{entity_id}/penalties/{penalty_id}/status",
    response_model=MessageResponse,
    summary="Update penalty status",
    tags=["2026 Reform - Compliance Penalties"],
)
async def update_penalty_status(
    entity_id: UUID,
    penalty_id: UUID,
    request: UpdatePenaltyStatusRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Update penalty status (mark as paid, waived, disputed)."""
    await verify_entity_access(entity_id, current_user, db)
    
    try:
        new_status = PenaltyStatus(request.status)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Valid values: {[s.value for s in PenaltyStatus]}",
        )
    
    # Get the penalty record
    from app.services.compliance_penalty_service import PenaltyRecord
    from sqlalchemy import select
    
    query = select(PenaltyRecord).where(
        PenaltyRecord.id == penalty_id,
        PenaltyRecord.entity_id == entity_id,
    )
    result = await db.execute(query)
    record = result.scalar_one_or_none()
    
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Penalty record not found",
        )
    
    # Update status
    record.status = new_status
    if request.payment_reference:
        record.payment_reference = request.payment_reference
    if request.notes:
        record.notes = request.notes
    if new_status == PenaltyStatus.PAID:
        record.paid_date = date.today()
    
    await db.commit()
    
    return MessageResponse(message=f"Penalty status updated to {new_status.value}")


# ===========================================
# PEPPOL BIS 3.0 EXPORT ENDPOINTS
# ===========================================

@router.get(
    "/peppol/info",
    summary="Get Peppol BIS 3.0 information",
    tags=["2026 Reform - Peppol Export"],
)
async def get_peppol_info():
    """
    Get information about Peppol BIS Billing 3.0 export capabilities.
    
    Peppol BIS Billing 3.0 is the mandated standard for:
    - Structured digital invoices
    - Cross-border e-invoicing
    - NRS compliance
    """
    return {
        "standard": "Peppol BIS Billing 3.0",
        "formats": ["xml", "json"],
        "ubl_version": "2.1",
        "profile_id": "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0",
        "customization_id": "urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0",
        "invoice_types": {
            "380": "Commercial Invoice",
            "381": "Credit Note",
            "383": "Debit Note",
            "384": "Corrected Invoice",
            "386": "Prepayment Invoice",
        },
        "tax_categories": {
            "S": "Standard Rate (7.5%)",
            "Z": "Zero Rated",
            "E": "Exempt",
            "O": "Not Subject to Tax",
        },
        "features": [
            "UBL 2.1 XML export",
            "JSON representation",
            "CSID (Cryptographic Stamp ID) generation",
            "QR code data embedding",
            "NRS compliance metadata",
        ],
        "compliance_reference": "Nigeria Tax Administration Act 2026",
    }


@router.post(
    "/peppol/export/xml",
    response_model=PeppolExportResponse,
    summary="Export invoice as Peppol XML",
    tags=["2026 Reform - Peppol Export"],
)
async def export_peppol_xml(
    request: PeppolExportRequest,
):
    """
    Export an invoice in Peppol BIS Billing 3.0 XML format (UBL 2.1).
    
    The export includes:
    - Complete UBL 2.1 structured XML
    - NRS CSID (Cryptographic Stamp ID)
    - QR code data for verification
    - All required Peppol metadata
    """
    service = PeppolExportService()
    
    # Convert request to PeppolInvoice
    seller = PeppolParty(
        name=request.seller.name,
        tin=request.seller.tin,
        registration_name=request.seller.registration_name,
        street_address=request.seller.street_address,
        city=request.seller.city,
        state=request.seller.state,
        postal_code=request.seller.postal_code,
        country_code=request.seller.country_code,
        contact_name=request.seller.contact_name,
        contact_email=request.seller.contact_email,
        contact_phone=request.seller.contact_phone,
    )
    
    buyer = PeppolParty(
        name=request.buyer.name,
        tin=request.buyer.tin,
        registration_name=request.buyer.registration_name,
        street_address=request.buyer.street_address,
        city=request.buyer.city,
        state=request.buyer.state,
        postal_code=request.buyer.postal_code,
        country_code=request.buyer.country_code,
        contact_name=request.buyer.contact_name,
        contact_email=request.buyer.contact_email,
        contact_phone=request.buyer.contact_phone,
    )
    
    line_items = []
    subtotal = Decimal("0")
    total_vat = Decimal("0")
    
    for item in request.line_items:
        line_total = item.quantity * item.unit_price
        vat_amount = line_total * (item.vat_rate / 100)
        subtotal += line_total
        total_vat += vat_amount
        
        line_items.append(PeppolLineItem(
            item_id=item.item_id,
            description=item.description,
            quantity=item.quantity,
            unit_code=item.unit_code,
            unit_price=item.unit_price,
            line_total=line_total,
            vat_rate=item.vat_rate,
            vat_amount=vat_amount,
            tax_category=TaxCategoryCode(item.tax_category),
            item_classification_code=item.item_classification_code,
        ))
    
    invoice = PeppolInvoice(
        invoice_number=request.invoice_number,
        invoice_date=request.invoice_date,
        due_date=request.due_date,
        invoice_type=InvoiceTypeCode(request.invoice_type),
        seller=seller,
        buyer=buyer,
        line_items=line_items,
        currency_code=request.currency_code,
        subtotal=subtotal,
        total_vat=total_vat,
        total_amount=subtotal + total_vat,
        payment_terms=request.payment_terms,
        nrs_irn=request.nrs_irn,
        notes=request.notes,
    )
    
    # Generate CSID and QR data
    csid = service.generate_csid(invoice)
    qr_data = service.generate_qr_code_data(invoice)
    
    # Update invoice with generated data
    invoice.nrs_csid = csid
    invoice.nrs_qr_code_data = qr_data
    
    # Generate XML
    xml_content = service.to_ubl_xml(invoice)
    
    return PeppolExportResponse(
        invoice_number=invoice.invoice_number,
        format="xml",
        content=xml_content,
        csid=csid,
        qr_code_data=qr_data,
        is_compliant=True,
    )


@router.post(
    "/peppol/export/json",
    response_model=PeppolExportResponse,
    summary="Export invoice as Peppol JSON",
    tags=["2026 Reform - Peppol Export"],
)
async def export_peppol_json(
    request: PeppolExportRequest,
):
    """
    Export an invoice in Peppol BIS Billing 3.0 JSON format.
    
    The export includes:
    - Structured JSON representation
    - NRS compliance metadata
    - CSID and QR code data
    """
    service = PeppolExportService()
    
    # Convert request to PeppolInvoice (same as XML)
    seller = PeppolParty(
        name=request.seller.name,
        tin=request.seller.tin,
        registration_name=request.seller.registration_name,
        street_address=request.seller.street_address,
        city=request.seller.city,
        state=request.seller.state,
        postal_code=request.seller.postal_code,
        country_code=request.seller.country_code,
        contact_name=request.seller.contact_name,
        contact_email=request.seller.contact_email,
        contact_phone=request.seller.contact_phone,
    )
    
    buyer = PeppolParty(
        name=request.buyer.name,
        tin=request.buyer.tin,
        registration_name=request.buyer.registration_name,
        street_address=request.buyer.street_address,
        city=request.buyer.city,
        state=request.buyer.state,
        postal_code=request.buyer.postal_code,
        country_code=request.buyer.country_code,
        contact_name=request.buyer.contact_name,
        contact_email=request.buyer.contact_email,
        contact_phone=request.buyer.contact_phone,
    )
    
    line_items = []
    subtotal = Decimal("0")
    total_vat = Decimal("0")
    
    for item in request.line_items:
        line_total = item.quantity * item.unit_price
        vat_amount = line_total * (item.vat_rate / 100)
        subtotal += line_total
        total_vat += vat_amount
        
        line_items.append(PeppolLineItem(
            item_id=item.item_id,
            description=item.description,
            quantity=item.quantity,
            unit_code=item.unit_code,
            unit_price=item.unit_price,
            line_total=line_total,
            vat_rate=item.vat_rate,
            vat_amount=vat_amount,
            tax_category=TaxCategoryCode(item.tax_category),
            item_classification_code=item.item_classification_code,
        ))
    
    invoice = PeppolInvoice(
        invoice_number=request.invoice_number,
        invoice_date=request.invoice_date,
        due_date=request.due_date,
        invoice_type=InvoiceTypeCode(request.invoice_type),
        seller=seller,
        buyer=buyer,
        line_items=line_items,
        currency_code=request.currency_code,
        subtotal=subtotal,
        total_vat=total_vat,
        total_amount=subtotal + total_vat,
        payment_terms=request.payment_terms,
        nrs_irn=request.nrs_irn,
        notes=request.notes,
    )
    
    # Generate CSID and QR data
    csid = service.generate_csid(invoice)
    qr_data = service.generate_qr_code_data(invoice)
    
    # Update invoice with generated data
    invoice.nrs_csid = csid
    invoice.nrs_qr_code_data = qr_data
    
    # Generate JSON
    json_content = service.to_json(invoice)
    
    return PeppolExportResponse(
        invoice_number=invoice.invoice_number,
        format="json",
        content=json_content,
        csid=csid,
        qr_code_data=qr_data,
        is_compliant=True,
    )


@router.get(
    "/{entity_id}/peppol/export/{invoice_id}/xml",
    response_model=PeppolExportResponse,
    summary="Export existing invoice as Peppol XML",
    tags=["2026 Reform - Peppol Export"],
)
async def export_existing_invoice_xml(
    entity_id: UUID,
    invoice_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Export an existing invoice as Peppol BIS 3.0 XML."""
    await verify_entity_access(entity_id, current_user, db)
    
    # Get invoice from database
    from app.models.invoice import Invoice
    from app.models.customer import Customer
    from app.models.entity import BusinessEntity
    from sqlalchemy import select
    
    query = select(Invoice).where(
        Invoice.id == invoice_id,
        Invoice.entity_id == entity_id,
    )
    result = await db.execute(query)
    invoice = result.scalar_one_or_none()
    
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )
    
    # Get entity (seller)
    entity_query = select(BusinessEntity).where(BusinessEntity.id == entity_id)
    entity_result = await db.execute(entity_query)
    entity = entity_result.scalar_one_or_none()
    
    # Get customer (buyer) if exists
    customer = None
    if invoice.customer_id:
        customer_query = select(Customer).where(Customer.id == invoice.customer_id)
        customer_result = await db.execute(customer_query)
        customer = customer_result.scalar_one_or_none()
    
    service = PeppolExportService()
    
    # Build seller party from entity
    seller = PeppolParty(
        name=entity.name,
        tin=entity.tin,
        registration_name=entity.name,
        street_address=entity.address,
        city=entity.city,
        state=entity.state,
        country_code="NG",
        contact_email=entity.email,
        contact_phone=entity.phone,
    )
    
    # Build buyer party
    buyer = PeppolParty(
        name=customer.name if customer else "Walk-in Customer",
        tin=customer.tin if customer else None,
        street_address=customer.address if customer else None,
        city=customer.city if customer else None,
        state=customer.state if customer else None,
        country_code="NG",
        contact_email=customer.email if customer else None,
        contact_phone=customer.phone if customer else None,
    )
    
    # Build line items from invoice items
    line_items = []
    for item in invoice.items:
        line_items.append(PeppolLineItem(
            item_id=str(item.id),
            description=item.description,
            quantity=Decimal(str(item.quantity)),
            unit_code="EA",
            unit_price=Decimal(str(item.unit_price)),
            line_total=Decimal(str(item.line_total)),
            vat_rate=Decimal("7.5"),
            vat_amount=Decimal(str(item.vat_amount)) if hasattr(item, 'vat_amount') else Decimal("0"),
            tax_category=TaxCategoryCode.STANDARD_RATE,
        ))
    
    peppol_invoice = PeppolInvoice(
        invoice_number=invoice.invoice_number,
        invoice_date=invoice.invoice_date,
        due_date=invoice.due_date or invoice.invoice_date,
        invoice_type=InvoiceTypeCode.COMMERCIAL_INVOICE,
        seller=seller,
        buyer=buyer,
        line_items=line_items,
        currency_code="NGN",
        subtotal=Decimal(str(invoice.subtotal)),
        total_vat=Decimal(str(invoice.vat_amount)),
        total_amount=Decimal(str(invoice.total_amount)),
        nrs_irn=invoice.irn,
        notes=invoice.notes,
    )
    
    # Generate CSID and QR data
    csid = service.generate_csid(peppol_invoice)
    qr_data = service.generate_qr_code_data(peppol_invoice)
    
    peppol_invoice.nrs_csid = csid
    peppol_invoice.nrs_qr_code_data = qr_data
    
    # Generate XML
    xml_content = service.to_ubl_xml(peppol_invoice)
    
    return PeppolExportResponse(
        invoice_number=peppol_invoice.invoice_number,
        format="xml",
        content=xml_content,
        csid=csid,
        qr_code_data=qr_data,
        is_compliant=True,
    )


@router.get(
    "/{entity_id}/peppol/export/{invoice_id}/json",
    response_model=PeppolExportResponse,
    summary="Export existing invoice as Peppol JSON",
    tags=["2026 Reform - Peppol Export"],
)
async def export_existing_invoice_json(
    entity_id: UUID,
    invoice_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Export an existing invoice as Peppol BIS 3.0 JSON."""
    await verify_entity_access(entity_id, current_user, db)
    
    # Get invoice from database
    from app.models.invoice import Invoice
    from app.models.customer import Customer
    from app.models.entity import BusinessEntity
    from sqlalchemy import select
    
    query = select(Invoice).where(
        Invoice.id == invoice_id,
        Invoice.entity_id == entity_id,
    )
    result = await db.execute(query)
    invoice = result.scalar_one_or_none()
    
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )
    
    # Get entity (seller)
    entity_query = select(BusinessEntity).where(BusinessEntity.id == entity_id)
    entity_result = await db.execute(entity_query)
    entity = entity_result.scalar_one_or_none()
    
    # Get customer (buyer) if exists
    customer = None
    if invoice.customer_id:
        customer_query = select(Customer).where(Customer.id == invoice.customer_id)
        customer_result = await db.execute(customer_query)
        customer = customer_result.scalar_one_or_none()
    
    service = PeppolExportService()
    
    # Build seller party from entity
    seller = PeppolParty(
        name=entity.name,
        tin=entity.tin,
        registration_name=entity.name,
        street_address=entity.address,
        city=entity.city,
        state=entity.state,
        country_code="NG",
        contact_email=entity.email,
        contact_phone=entity.phone,
    )
    
    # Build buyer party
    buyer = PeppolParty(
        name=customer.name if customer else "Walk-in Customer",
        tin=customer.tin if customer else None,
        street_address=customer.address if customer else None,
        city=customer.city if customer else None,
        state=customer.state if customer else None,
        country_code="NG",
        contact_email=customer.email if customer else None,
        contact_phone=customer.phone if customer else None,
    )
    
    # Build line items from invoice items
    line_items = []
    for item in invoice.items:
        line_items.append(PeppolLineItem(
            item_id=str(item.id),
            description=item.description,
            quantity=Decimal(str(item.quantity)),
            unit_code="EA",
            unit_price=Decimal(str(item.unit_price)),
            line_total=Decimal(str(item.line_total)),
            vat_rate=Decimal("7.5"),
            vat_amount=Decimal(str(item.vat_amount)) if hasattr(item, 'vat_amount') else Decimal("0"),
            tax_category=TaxCategoryCode.STANDARD_RATE,
        ))
    
    peppol_invoice = PeppolInvoice(
        invoice_number=invoice.invoice_number,
        invoice_date=invoice.invoice_date,
        due_date=invoice.due_date or invoice.invoice_date,
        invoice_type=InvoiceTypeCode.COMMERCIAL_INVOICE,
        seller=seller,
        buyer=buyer,
        line_items=line_items,
        currency_code="NGN",
        subtotal=Decimal(str(invoice.subtotal)),
        total_vat=Decimal(str(invoice.vat_amount)),
        total_amount=Decimal(str(invoice.total_amount)),
        nrs_irn=invoice.irn,
        notes=invoice.notes,
    )
    
    # Generate CSID and QR data
    csid = service.generate_csid(peppol_invoice)
    qr_data = service.generate_qr_code_data(peppol_invoice)
    
    peppol_invoice.nrs_csid = csid
    peppol_invoice.nrs_qr_code_data = qr_data
    
    # Generate JSON
    json_content = service.to_json(peppol_invoice)
    
    return PeppolExportResponse(
        invoice_number=peppol_invoice.invoice_number,
        format="json",
        content=json_content,
        csid=csid,
        qr_code_data=qr_data,
        is_compliant=True,
    )


# ===========================================
# SELF-ASSESSMENT & TAXPRO MAX EXPORT ENDPOINTS
# ===========================================

from app.services.self_assessment_service import (
    SelfAssessmentService,
    TaxReturnType,
    TaxProMaxFormCode,
    CITSelfAssessment,
    VATSelfAssessment,
    AnnualReturnsSummary,
)


# Schemas for Self-Assessment
class SelfAssessmentInfoResponse(BaseModel):
    """Self-assessment service information."""
    service_name: str
    description: str
    supported_forms: List[dict]
    taxpro_max_portal: str
    export_formats: List[str]
    fiscal_year_support: str


class CITAssessmentResponse(BaseModel):
    """CIT self-assessment response."""
    entity_id: str
    fiscal_year_end: str
    tin: str
    company_name: str
    company_classification: str
    income_statement: dict
    tax_computation: dict
    capital_gains: dict
    final_computation: dict
    form_code: str
    generated_at: str


class VATAssessmentResponse(BaseModel):
    """VAT self-assessment response."""
    entity_id: str
    period: str
    tin: str
    sales: dict
    purchases: dict
    net_position: dict
    form_code: str
    generated_at: str


class AnnualReturnsResponse(BaseModel):
    """Annual returns package response."""
    entity_id: str
    fiscal_year: int
    tin: str
    company_name: str
    summary: dict
    cit_assessment: Optional[dict]
    vat_monthly_breakdown: List[dict]
    taxpro_max: dict
    generated_at: str


class TaxProExportRequest(BaseModel):
    """Request for TaxPro Max export."""
    fiscal_year: int = Field(..., ge=2020, le=2100)
    return_type: TaxReturnType = TaxReturnType.CIT
    format: str = Field(default="csv", pattern="^(csv|xlsx|json)$")


class TaxProExportResponse(BaseModel):
    """TaxPro Max export response."""
    form_code: str
    format: str
    filename: str
    content: str
    record_count: int
    generated_at: str
    upload_instructions: str


@router.get(
    "/self-assessment/info",
    tags=["2026 Reform - Self-Assessment"],
    summary="Get self-assessment service information",
)
async def get_self_assessment_info() -> SelfAssessmentInfoResponse:
    """
    Get information about the Self-Assessment and TaxPro Max Export service.
    
    Provides details on:
    - Supported NRS form types
    - Export formats for TaxPro Max upload
    - Fiscal year support
    """
    return SelfAssessmentInfoResponse(
        service_name="Tekvwa Pro Audit Self-Assessment",
        description="Pre-fills NRS tax forms based on yearly financial data for TaxPro Max upload",
        supported_forms=[
            {"code": TaxProMaxFormCode.CIT_ANNUAL.value, "name": "Annual CIT Return", "description": "Company Income Tax annual return"},
            {"code": TaxProMaxFormCode.VAT_MONTHLY.value, "name": "Monthly VAT Return", "description": "Value Added Tax monthly return"},
            {"code": TaxProMaxFormCode.PAYE_MONTHLY.value, "name": "Monthly PAYE Return", "description": "Pay As You Earn monthly return"},
            {"code": TaxProMaxFormCode.WHT_MONTHLY.value, "name": "Monthly WHT Return", "description": "Withholding Tax monthly return"},
            {"code": TaxProMaxFormCode.DEV_LEVY_ANNUAL.value, "name": "Annual Development Levy", "description": "Development Levy annual return"},
            {"code": TaxProMaxFormCode.ANNUAL_RETURNS.value, "name": "Annual Returns Package", "description": "Complete annual returns bundle"},
        ],
        taxpro_max_portal="https://taxpromax.nrs.gov.ng/",
        export_formats=["csv", "xlsx", "json"],
        fiscal_year_support="2024 onwards (2026 Tax Reform compliant)",
    )


@router.get(
    "/self-assessment/{entity_id}/cit/{fiscal_year}",
    tags=["2026 Reform - Self-Assessment"],
    summary="Generate CIT self-assessment",
)
async def generate_cit_self_assessment(
    entity_id: UUID,
    fiscal_year: int = Path(..., ge=2020, le=2100),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
) -> CITAssessmentResponse:
    """
    Generate Company Income Tax (CIT) self-assessment for a fiscal year.
    
    Pre-fills the CIT-01 form with:
    - Income statement figures (turnover, expenses, profit)
    - Tax computation (assessable profit, tax rate, liability)
    - Capital gains (taxed at CIT rate under 2026 law)
    - Development Levy calculation
    - WHT credits deduction
    """
    service = SelfAssessmentService(db)
    
    try:
        assessment = await service.generate_cit_assessment(entity_id, fiscal_year)
        
        return CITAssessmentResponse(
            entity_id=str(assessment.entity_id),
            fiscal_year_end=assessment.fiscal_year_end.isoformat(),
            tin=assessment.tin,
            company_name=assessment.company_name,
            company_classification=assessment.company_classification,
            income_statement={
                "gross_turnover": float(assessment.gross_turnover),
                "cost_of_sales": float(assessment.cost_of_sales),
                "gross_profit": float(assessment.gross_profit),
                "operating_expenses": float(assessment.operating_expenses),
                "depreciation": float(assessment.depreciation),
                "net_profit_before_tax": float(assessment.net_profit_before_tax),
            },
            tax_computation={
                "add_backs": float(assessment.add_backs),
                "allowable_deductions": float(assessment.allowable_deductions),
                "assessable_profit": float(assessment.assessable_profit),
                "tax_rate_percent": float(assessment.tax_rate),
                "cit_liability": float(assessment.cit_liability),
            },
            capital_gains={
                "total_gains": float(assessment.capital_gains),
                "cgt_liability": float(assessment.cgt_liability),
                "note": "Under 2026 law, capital gains are taxed at the flat CIT rate",
            },
            final_computation={
                "total_tax_payable": float(assessment.total_tax_payable),
                "wht_credits": float(assessment.wht_credits),
                "net_tax_payable": float(assessment.net_tax_payable),
                "development_levy": float(assessment.development_levy),
            },
            form_code=assessment.form_code,
            generated_at=assessment.generated_at.isoformat(),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/self-assessment/{entity_id}/vat/{year}/{month}",
    tags=["2026 Reform - Self-Assessment"],
    summary="Generate VAT self-assessment",
)
async def generate_vat_self_assessment(
    entity_id: UUID,
    year: int = Path(..., ge=2020, le=2100),
    month: int = Path(..., ge=1, le=12),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
) -> VATAssessmentResponse:
    """
    Generate monthly VAT return self-assessment.
    
    Pre-fills the VAT-01 form with:
    - Output VAT from sales
    - Input VAT from purchases
    - Input VAT on fixed assets (2026: now recoverable with IRN)
    - Net VAT payable or refund
    """
    service = SelfAssessmentService(db)
    
    try:
        assessment = await service.generate_vat_assessment(entity_id, year, month)
        
        return VATAssessmentResponse(
            entity_id=str(assessment.entity_id),
            period=f"{year}-{month:02d}",
            tin=assessment.tin,
            sales={
                "standard_rated": float(assessment.standard_rated_sales),
                "zero_rated": float(assessment.zero_rated_sales),
                "exempt": float(assessment.exempt_sales),
                "total": float(assessment.total_sales),
                "output_vat": float(assessment.output_vat),
            },
            purchases={
                "standard_rated": float(assessment.standard_rated_purchases),
                "zero_rated": float(assessment.zero_rated_purchases),
                "exempt": float(assessment.exempt_purchases),
                "total": float(assessment.total_purchases),
                "input_vat": float(assessment.input_vat),
                "input_vat_fixed_assets": float(assessment.input_vat_fixed_assets),
                "total_input_vat": float(assessment.total_input_vat),
            },
            net_position={
                "net_vat_payable": float(assessment.net_vat_payable),
                "refund_claimed": float(assessment.refund_claimed),
            },
            form_code=assessment.form_code,
            generated_at=assessment.generated_at.isoformat(),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/self-assessment/{entity_id}/annual/{fiscal_year}",
    tags=["2026 Reform - Self-Assessment"],
    summary="Generate annual returns package",
)
async def generate_annual_returns(
    entity_id: UUID,
    fiscal_year: int = Path(..., ge=2020, le=2100),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
) -> AnnualReturnsResponse:
    """
    Generate complete annual returns package for TaxPro Max upload.
    
    Includes:
    - CIT annual return (CIT-01)
    - 12 monthly VAT returns (VAT-01)
    - Development Levy calculation
    - Summary totals
    - Export format options
    """
    service = SelfAssessmentService(db)
    
    try:
        summary = await service.generate_annual_returns(entity_id, fiscal_year)
        json_data = service.export_annual_summary_json(summary)
        
        return AnnualReturnsResponse(
            entity_id=str(summary.entity_id),
            fiscal_year=summary.fiscal_year,
            tin=summary.tin,
            company_name=summary.company_name,
            summary=json_data["summary"],
            cit_assessment=json_data["cit_assessment"],
            vat_monthly_breakdown=json_data["vat_monthly_breakdown"],
            taxpro_max=json_data["taxpro_max"],
            generated_at=summary.generated_at.isoformat(),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/taxpro-export/{entity_id}",
    tags=["2026 Reform - TaxPro Max Export"],
    summary="Export tax data for TaxPro Max upload",
)
async def export_for_taxpro_max(
    entity_id: UUID,
    request: TaxProExportRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
) -> TaxProExportResponse:
    """
    Export tax data in TaxPro Max compatible format.
    
    Generates ready-to-upload CSV/Excel files for:
    - CIT annual returns
    - VAT monthly returns
    - PAYE returns
    - WHT returns
    
    Export format matches NRS TaxPro Max upload requirements.
    """
    service = SelfAssessmentService(db)
    
    try:
        if request.return_type == TaxReturnType.CIT:
            assessment = await service.generate_cit_assessment(entity_id, request.fiscal_year)
            content = service.export_cit_to_csv(assessment)
            form_code = TaxProMaxFormCode.CIT_ANNUAL.value
            filename = f"CIT_{assessment.tin}_{request.fiscal_year}.csv"
            record_count = 1
            
        elif request.return_type == TaxReturnType.VAT:
            # Generate all 12 months
            assessments = []
            for month in range(1, 13):
                try:
                    vat = await service.generate_vat_assessment(entity_id, request.fiscal_year, month)
                    assessments.append(vat)
                except Exception:
                    pass
            
            if not assessments:
                raise ValueError("No VAT data found for the fiscal year")
            
            content = service.export_vat_to_csv(assessments)
            form_code = TaxProMaxFormCode.VAT_MONTHLY.value
            filename = f"VAT_{assessments[0].tin}_{request.fiscal_year}.csv"
            record_count = len(assessments)
            
        else:
            raise ValueError(f"Export for {request.return_type.value} not yet implemented")
        
        return TaxProExportResponse(
            form_code=form_code,
            format=request.format,
            filename=filename,
            content=content,
            record_count=record_count,
            generated_at=datetime.utcnow().isoformat(),
            upload_instructions=(
                "1. Log in to TaxPro Max at https://taxpromax.nrs.gov.ng/\n"
                "2. Navigate to Self-Assessment > Upload Returns\n"
                "3. Select the appropriate form type\n"
                "4. Upload this CSV file\n"
                "5. Review and submit the return"
            ),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/taxpro-export/formats",
    tags=["2026 Reform - TaxPro Max Export"],
    summary="Get supported export formats",
)
async def get_taxpro_export_formats() -> dict:
    """
    Get information about TaxPro Max export formats.
    
    Returns supported file formats and their specifications.
    """
    return {
        "formats": [
            {
                "format": "csv",
                "description": "Comma-Separated Values",
                "mime_type": "text/csv",
                "recommended": True,
                "notes": "Standard TaxPro Max upload format",
            },
            {
                "format": "xlsx",
                "description": "Microsoft Excel Spreadsheet",
                "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "recommended": False,
                "notes": "Convert to CSV before upload if required",
            },
            {
                "format": "json",
                "description": "JavaScript Object Notation",
                "mime_type": "application/json",
                "recommended": False,
                "notes": "For API integrations and data review",
            },
        ],
        "return_types": [
            {"type": TaxReturnType.CIT.value, "form_code": TaxProMaxFormCode.CIT_ANNUAL.value, "name": "Company Income Tax"},
            {"type": TaxReturnType.VAT.value, "form_code": TaxProMaxFormCode.VAT_MONTHLY.value, "name": "Value Added Tax"},
            {"type": TaxReturnType.PAYE.value, "form_code": TaxProMaxFormCode.PAYE_MONTHLY.value, "name": "Pay As You Earn"},
            {"type": TaxReturnType.WHT.value, "form_code": TaxProMaxFormCode.WHT_MONTHLY.value, "name": "Withholding Tax"},
            {"type": TaxReturnType.DEV_LEVY.value, "form_code": TaxProMaxFormCode.DEV_LEVY_ANNUAL.value, "name": "Development Levy"},
        ],
        "portal": {
            "name": "NRS TaxPro Max",
            "url": "https://taxpromax.nrs.gov.ng/",
            "filing_deadlines": {
                "CIT": "Within 6 months of fiscal year end",
                "VAT": "21st of the following month",
                "PAYE": "10th of the following month",
                "WHT": "21st of the following month",
            },
        },
    }
