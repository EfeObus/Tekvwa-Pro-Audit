"""
Tekvwa Pro Audit - NRS (Nigeria Revenue Service) Router

API endpoints for NRS Invoice Reporting System integration.
Provides:
- Invoice submission for IRN (Invoice Reference Number) generation
- TIN (Tax Identification Number) validation
- Buyer dispute handling
- B2C transaction reporting (2026 compliance)

Nigerian Compliance:
- All invoices above ₦50,000 must be submitted to NRS
- B2B invoices require buyer TIN
- Buyers have 72 hours to dispute submitted invoices
- B2C transactions > ₦50,000 require 24-hour reporting

SKU Tier: PROFESSIONAL (₦150,000+/mo)
Feature Flag: NRS_COMPLIANCE
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, get_current_entity_id, require_feature
from app.models.entity import BusinessEntity
from app.models.user import User
from app.models.sku import Feature
from app.services.nrs_service import (
    NRSApiClient,
    NRSInvoiceResponse,
    NRSTINValidationResponse,
    NRSDisputeResponse,
    get_nrs_client,
)
from app.services.audit_service import AuditService
from app.models.audit_consolidated import AuditAction

router = APIRouter(
    prefix="/nrs", 
    tags=["NRS Integration"],
    dependencies=[Depends(require_feature([Feature.NRS_COMPLIANCE]))]
)

# Note: All endpoints in this router require Professional tier (NRS_COMPLIANCE feature)


# ===========================================
# REQUEST/RESPONSE SCHEMAS
# ===========================================

class NRSInvoiceLineItem(BaseModel):
    """Line item for NRS invoice submission."""
    description: str = Field(..., min_length=1, max_length=500)
    quantity: float = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)
    vat_amount: float = Field(default=0, ge=0)
    total: float = Field(..., ge=0)
    hsn_code: Optional[str] = Field(None, max_length=20)


class NRSInvoiceSubmitRequest(BaseModel):
    """Request schema for NRS invoice submission."""
    buyer_name: str = Field(..., min_length=1, max_length=255)
    buyer_tin: Optional[str] = Field(None, max_length=20, description="Required for B2B invoices")
    buyer_address: Optional[str] = Field(None, max_length=500)
    invoice_number: str = Field(..., min_length=1, max_length=100)
    invoice_date: str = Field(..., description="Invoice date in YYYY-MM-DD format")
    subtotal: float = Field(..., ge=0)
    vat_amount: float = Field(default=0, ge=0)
    total_amount: float = Field(..., gt=0)
    vat_rate: float = Field(default=7.5, ge=0, le=100)
    line_items: List[NRSInvoiceLineItem] = Field(..., min_length=1)
    
    class Config:
        json_schema_extra = {
            "example": {
                "buyer_name": "ABC Ltd",
                "buyer_tin": "1234567890",
                "buyer_address": "123 Main Street, Lagos",
                "invoice_number": "INV-2026-001",
                "invoice_date": "2026-01-15",
                "subtotal": 100000.00,
                "vat_amount": 7500.00,
                "total_amount": 107500.00,
                "vat_rate": 7.5,
                "line_items": [
                    {
                        "description": "Professional Services",
                        "quantity": 1,
                        "unit_price": 100000.00,
                        "vat_amount": 7500.00,
                        "total": 107500.00
                    }
                ]
            }
        }


class NRSInvoiceSubmitResponse(BaseModel):
    """Response schema for NRS invoice submission."""
    success: bool
    message: str
    irn: Optional[str] = None
    qr_code_data: Optional[str] = None
    submission_timestamp: Optional[datetime] = None
    dispute_deadline: Optional[datetime] = None
    invoice_type: str = "B2B"  # B2B or B2C


class NRSTINValidateRequest(BaseModel):
    """Request schema for TIN validation."""
    tin: str = Field(..., min_length=10, max_length=20)
    name: Optional[str] = Field(None, max_length=255, description="Business name for cross-verification")
    
    class Config:
        json_schema_extra = {
            "example": {
                "tin": "1234567890",
                "name": "ABC Limited"
            }
        }


class NRSTINValidateResponse(BaseModel):
    """Response schema for TIN validation."""
    is_valid: bool
    tin: str
    registered_name: Optional[str] = None
    business_type: Optional[str] = None
    registration_date: Optional[str] = None
    status: Optional[str] = None
    message: str


class NRSDisputeSubmitRequest(BaseModel):
    """Request schema for buyer dispute submission."""
    irn: str = Field(..., min_length=10, max_length=50, description="Invoice Reference Number")
    dispute_reason: str = Field(..., min_length=10, max_length=1000)
    supporting_documents: Optional[List[str]] = Field(None, description="Document URLs or references")
    
    class Config:
        json_schema_extra = {
            "example": {
                "irn": "NGN20260115123456ABCD1234",
                "dispute_reason": "Invoice amount is incorrect. Agreed price was ₦95,000 not ₦100,000.",
                "supporting_documents": ["doc_ref_1", "doc_ref_2"]
            }
        }


class NRSDisputeSubmitResponse(BaseModel):
    """Response schema for dispute submission."""
    success: bool
    message: str
    dispute_reference: Optional[str] = None


class NRSB2CReportRequest(BaseModel):
    """Request schema for B2C transaction reporting (2026 compliance)."""
    transaction_date: str = Field(..., description="Transaction date in YYYY-MM-DD format")
    transaction_reference: str = Field(..., min_length=1, max_length=100)
    customer_name: str = Field(default="Walk-in Customer", max_length=255)
    customer_phone: Optional[str] = Field(None, max_length=20)
    customer_email: Optional[str] = Field(None, max_length=255)
    transaction_amount: float = Field(..., gt=0)
    vat_amount: float = Field(default=0, ge=0)
    payment_method: str = Field(default="cash", description="cash, card, or transfer")
    
    class Config:
        json_schema_extra = {
            "example": {
                "transaction_date": "2026-01-15",
                "transaction_reference": "TXN-2026-001",
                "customer_name": "Walk-in Customer",
                "transaction_amount": 75000.00,
                "vat_amount": 5625.00,
                "payment_method": "card"
            }
        }


class NRSB2CReportResponse(BaseModel):
    """Response schema for B2C transaction reporting."""
    success: bool
    message: str
    report_reference: Optional[str] = None
    reporting_deadline: Optional[str] = None
    amount_reported: float


class NRSBulkTINValidateRequest(BaseModel):
    """Request schema for bulk TIN validation."""
    tins: List[str] = Field(..., min_length=1, max_length=100, description="List of TINs to validate")


# ===========================================
# ENDPOINTS
# ===========================================

@router.post(
    "/invoices/submit",
    response_model=NRSInvoiceSubmitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit invoice to NRS for IRN",
    description="""
    Submit an invoice to the Nigeria Revenue Service (NRS) for IRN generation.
    
    **B2B Invoices:** Require buyer TIN. Both buyer and seller TINs are validated.
    
    **B2C Invoices:** No buyer TIN required. Suitable for retail transactions.
    
    **Returns:** Invoice Reference Number (IRN) and QR code data for the fiscal stamp.
    
    **Dispute Window:** Buyers have 72 hours after submission to dispute the invoice.
    """,
)
async def submit_invoice(
    request: NRSInvoiceSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Submit invoice to NRS for IRN generation."""
    # Fetch the entity
    result = await db.execute(select(BusinessEntity).where(BusinessEntity.id == entity_id))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    
    # Validate seller has TIN
    if not entity.tin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Entity TIN is required for NRS submission. Please update your business entity settings.",
        )
    
    # Initialize NRS client
    nrs_client = get_nrs_client()
    
    # Convert line items to dict format
    line_items = [item.model_dump() for item in request.line_items]
    
    # Submit to NRS
    result: NRSInvoiceResponse = await nrs_client.submit_invoice(
        seller_tin=entity.tin,
        seller_name=entity.legal_name or entity.name,
        seller_address=entity.full_address,
        buyer_name=request.buyer_name,
        buyer_tin=request.buyer_tin,
        buyer_address=request.buyer_address,
        invoice_number=request.invoice_number,
        invoice_date=request.invoice_date,
        subtotal=request.subtotal,
        vat_amount=request.vat_amount,
        total_amount=request.total_amount,
        vat_rate=request.vat_rate,
        line_items=line_items,
    )
    
    invoice_type = "B2B" if request.buyer_tin else "B2C"
    
    # Audit logging for NRS submission
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="invoice",
        entity_id=request.invoice_number,
        action=AuditAction.NRS_SUBMIT,
        user_id=current_user.id,
        new_values={
            "irn": result.irn,
            "invoice_number": request.invoice_number,
            "invoice_type": invoice_type,
            "total_amount": request.total_amount,
            "vat_amount": request.vat_amount,
            "buyer_name": request.buyer_name,
            "success": result.success,
        }
    )
    
    return NRSInvoiceSubmitResponse(
        success=result.success,
        message=result.message,
        irn=result.irn,
        qr_code_data=result.qr_code_data,
        submission_timestamp=result.submission_timestamp,
        dispute_deadline=result.dispute_deadline,
        invoice_type=invoice_type,
    )


@router.get(
    "/invoices/{irn}/status",
    summary="Get invoice status by IRN",
    description="Retrieve the current status of a submitted invoice using its IRN.",
)
async def get_invoice_status(
    irn: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get status of a submitted invoice."""
    nrs_client = get_nrs_client()
    result = await nrs_client.get_invoice_status(irn)
    return result


@router.post(
    "/tin/validate",
    response_model=NRSTINValidateResponse,
    summary="Validate a Tax Identification Number",
    description="""
    Validate a Nigerian Tax Identification Number (TIN).
    
    **Nigerian TIN Format:**
    - Personal TIN: 10 digits
    - Corporate TIN: 10-14 digits
    
    **Optional:** Provide business name for cross-verification.
    """,
)
async def validate_tin(
    request: NRSTINValidateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Validate a TIN with the NRS."""
    nrs_client = get_nrs_client()
    
    result: NRSTINValidationResponse = await nrs_client.validate_tin(
        tin=request.tin,
        name=request.name,
    )
    
    return NRSTINValidateResponse(
        is_valid=result.is_valid,
        tin=result.tin,
        registered_name=result.registered_name,
        business_type=result.business_type,
        registration_date=result.registration_date,
        status=result.status,
        message=result.message,
    )


@router.post(
    "/tin/validate/bulk",
    response_model=List[NRSTINValidateResponse],
    summary="Validate multiple TINs",
    description="Validate multiple Tax Identification Numbers in a single request. Max 100 TINs per request.",
)
async def validate_tins_bulk(
    request: NRSBulkTINValidateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Validate multiple TINs in bulk."""
    if len(request.tins) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 100 TINs per bulk validation request.",
        )
    
    nrs_client = get_nrs_client()
    results = await nrs_client.bulk_validate_tins(request.tins)
    
    return [
        NRSTINValidateResponse(
            is_valid=r.is_valid,
            tin=r.tin,
            registered_name=r.registered_name,
            business_type=r.business_type,
            registration_date=r.registration_date,
            status=r.status,
            message=r.message,
        )
        for r in results
    ]


@router.post(
    "/disputes/submit",
    response_model=NRSDisputeSubmitResponse,
    summary="Submit a buyer dispute",
    description="""
    Submit a buyer dispute for a received invoice.
    
    **Dispute Window:** Must be submitted within 72 hours of invoice acceptance.
    
    **Supporting Documents:** Optional - attach document references if available.
    
    **Resolution:** FIRS will review and mediate disputes.
    """,
)
async def submit_dispute(
    request: NRSDisputeSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a buyer dispute for an invoice."""
    nrs_client = get_nrs_client()
    
    result: NRSDisputeResponse = await nrs_client.submit_dispute(
        irn=request.irn,
        dispute_reason=request.dispute_reason,
        supporting_documents=request.supporting_documents,
    )
    
    return NRSDisputeSubmitResponse(
        success=result.success,
        message=result.message,
        dispute_reference=result.dispute_reference,
    )


@router.post(
    "/b2c/report",
    response_model=NRSB2CReportResponse,
    summary="Report B2C transaction (2026 compliance)",
    description="""
    Report a B2C (Business-to-Consumer) transaction for 2026 compliance.
    
    **2026 Requirement:** B2C transactions > ₦50,000 must be reported within 24 hours.
    
    **Applies to:** Retail, hospitality, and consumer-facing businesses.
    
    **Purpose:** Enables FIRS real-time monitoring of high-value consumer transactions.
    """,
)
async def report_b2c_transaction(
    request: NRSB2CReportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Report a B2C transaction for 2026 compliance."""
    # Fetch the entity
    result = await db.execute(select(BusinessEntity).where(BusinessEntity.id == entity_id))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    
    # Validate seller has TIN
    if not entity.tin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Entity TIN is required for B2C reporting.",
        )
    
    # Check if B2C reporting is enabled for entity
    if not entity.b2c_realtime_reporting_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="B2C real-time reporting is not enabled for this entity. Enable in settings.",
        )
    
    # Check if transaction meets threshold
    if request.transaction_amount < float(entity.b2c_reporting_threshold):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Transaction amount ₦{request.transaction_amount:,.2f} is below the reporting threshold of ₦{entity.b2c_reporting_threshold:,.2f}.",
        )
    
    nrs_client = get_nrs_client()
    
    result = await nrs_client.submit_b2c_transaction_report(
        seller_tin=entity.tin,
        seller_name=entity.legal_name or entity.name,
        transaction_date=request.transaction_date,
        transaction_reference=request.transaction_reference,
        customer_name=request.customer_name,
        customer_phone=request.customer_phone,
        customer_email=request.customer_email,
        transaction_amount=request.transaction_amount,
        vat_amount=request.vat_amount,
        payment_method=request.payment_method,
    )
    
    return NRSB2CReportResponse(
        success=result.get("success", False),
        message=result.get("message", ""),
        report_reference=result.get("report_reference"),
        reporting_deadline=result.get("reporting_deadline"),
        amount_reported=request.transaction_amount,
    )


@router.get(
    "/b2c/status",
    summary="Get B2C reporting status",
    description="Get B2C reporting status for a date range. Shows total, pending, and overdue transactions.",
)
async def get_b2c_reporting_status(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get B2C reporting status for a period."""
    # Fetch the entity
    result = await db.execute(select(BusinessEntity).where(BusinessEntity.id == entity_id))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    
    if not entity.tin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Entity TIN is required.",
        )
    
    nrs_client = get_nrs_client()
    result = await nrs_client.get_b2c_reporting_status(
        seller_tin=entity.tin,
        start_date=start_date,
        end_date=end_date,
    )
    return result


@router.get(
    "/health",
    summary="Check NRS API connectivity",
    description="Check if the NRS API is reachable and responding.",
)
async def check_nrs_health():
    """Check NRS API health status."""
    nrs_client = get_nrs_client()
    
    return {
        "status": "healthy",
        "environment": nrs_client.environment.value,
        "sandbox_mode": nrs_client.sandbox_mode,
        "base_url": nrs_client.base_url,
        "timestamp": datetime.utcnow().isoformat(),
    }
