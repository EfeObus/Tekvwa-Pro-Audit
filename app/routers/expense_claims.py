"""
Tekvwa Pro Audit - Expense Claims Router

API endpoints for expense claims and reimbursements.

SKU Tier: PROFESSIONAL (₦150,000+/mo)
Feature Flag: EXPENSE_CLAIMS
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import (
    get_current_user, 
    get_current_entity_id, 
    record_usage_event, 
    require_within_usage_limit,
    require_feature,
)
from app.models.user import User
from app.models.expense_claims import ExpenseCategory, ClaimStatus, PaymentMethod
from app.models.sku import Feature, UsageMetricType
from app.services.expense_claims_service import (
    ExpenseClaimsService, get_expense_claims_service
)
from app.services.audit_service import AuditService
from app.models.audit_consolidated import AuditAction

router = APIRouter(
    prefix="/expense-claims", 
    tags=["Expense Claims"],
    dependencies=[Depends(require_feature([Feature.EXPENSE_CLAIMS]))]
)

# Note: All endpoints in this router require Professional tier (EXPENSE_CLAIMS feature)


# ===========================================
# REQUEST/RESPONSE SCHEMAS
# ===========================================

class ExpenseClaimCreate(BaseModel):
    """Schema for creating an expense claim."""
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    expense_date_from: date
    expense_date_to: date
    project_code: Optional[str] = None
    cost_center: Optional[str] = None
    department: Optional[str] = None


class ExpenseItemCreate(BaseModel):
    """Schema for adding an expense item."""
    expense_date: date
    category: ExpenseCategory
    description: str
    amount: float = Field(..., gt=0)
    vat_amount: float = Field(default=0, ge=0)
    vendor_name: Optional[str] = None
    receipt_number: Optional[str] = None
    receipt_file_url: Optional[str] = None
    is_tax_deductible: bool = True
    gl_account_code: Optional[str] = None
    notes: Optional[str] = None


class ExpenseItemResponse(BaseModel):
    """Response schema for expense item."""
    id: str
    expense_date: date
    category: str
    description: str
    amount: float
    vat_amount: float
    approved_amount: float
    vendor_name: Optional[str]
    receipt_number: Optional[str]
    has_receipt: bool
    is_tax_deductible: bool


class ExpenseClaimResponse(BaseModel):
    """Response schema for expense claim."""
    id: str
    claim_number: str
    title: str
    description: Optional[str]
    expense_date_from: date
    expense_date_to: date
    currency: str
    total_amount: float
    approved_amount: float
    status: str
    submitted_at: Optional[datetime]
    approved_at: Optional[datetime]
    paid_at: Optional[datetime]
    line_items: List[ExpenseItemResponse]


class ClaimApprovalRequest(BaseModel):
    """Request for approving a claim."""
    approval_notes: Optional[str] = None
    item_adjustments: Optional[dict] = None


class ClaimRejectionRequest(BaseModel):
    """Request for rejecting a claim."""
    rejection_reason: str = Field(..., min_length=10)


class ClaimPaymentRequest(BaseModel):
    """Request for marking a claim as paid."""
    payment_method: PaymentMethod
    payment_reference: Optional[str] = None


# ===========================================
# ENDPOINTS
# ===========================================

@router.post(
    "",
    response_model=ExpenseClaimResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create expense claim",
)
async def create_expense_claim(
    request: ExpenseClaimCreate,
    employee_id: uuid.UUID = Query(..., description="Employee ID for the claim"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    _limit_check: User = Depends(require_within_usage_limit(UsageMetricType.TRANSACTIONS)),
):
    """Create a new expense claim."""
    service = get_expense_claims_service(db)
    
    claim = await service.create_claim(
        entity_id=entity_id,
        employee_id=employee_id,
        title=request.title,
        description=request.description,
        expense_date_from=request.expense_date_from,
        expense_date_to=request.expense_date_to,
        project_code=request.project_code,
        cost_center=request.cost_center,
        department=request.department,
        created_by_id=current_user.id,
    )
    
    # Audit logging
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="expense_claim",
        entity_id=str(claim.id),
        action=AuditAction.CREATE,
        user_id=current_user.id,
        new_values={
            "claim_number": claim.claim_number,
            "title": claim.title,
            "employee_id": str(employee_id),
        }
    )
    
    # Record usage metering for transaction tracking
    if current_user.organization_id:
        await record_usage_event(
            db=db,
            organization_id=current_user.organization_id,
            metric_type=UsageMetricType.TRANSACTIONS,
            entity_id=entity_id,
            user_id=current_user.id,
            resource_type="expense_claim",
            resource_id=str(claim.id),
        )
    
    return _claim_to_response(claim)


@router.get(
    "",
    response_model=List[ExpenseClaimResponse],
    summary="List expense claims",
)
async def list_expense_claims(
    employee_id: Optional[uuid.UUID] = None,
    status_filter: Optional[ClaimStatus] = Query(None, alias="status"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """List expense claims with optional filters."""
    service = get_expense_claims_service(db)
    
    claims = await service.get_claims(
        entity_id=entity_id,
        employee_id=employee_id,
        status=status_filter,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    
    return [_claim_to_response(c) for c in claims]


@router.get(
    "/{claim_id}",
    response_model=ExpenseClaimResponse,
    summary="Get expense claim details",
)
async def get_expense_claim(
    claim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get a specific expense claim."""
    service = get_expense_claims_service(db)
    claim = await service.get_claim(claim_id, entity_id)
    
    if not claim:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expense claim not found",
        )
    
    return _claim_to_response(claim)


@router.post(
    "/{claim_id}/items",
    response_model=ExpenseItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add expense item to claim",
)
async def add_expense_item(
    claim_id: uuid.UUID,
    request: ExpenseItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Add an expense item to a claim."""
    service = get_expense_claims_service(db)
    
    # Verify claim exists and belongs to entity
    claim = await service.get_claim(claim_id, entity_id)
    if not claim:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expense claim not found",
        )
    
    if claim.status != ClaimStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only add items to draft claims",
        )
    
    item = await service.add_expense_item(
        claim_id=claim_id,
        expense_date=request.expense_date,
        category=request.category,
        description=request.description,
        amount=Decimal(str(request.amount)),
        vat_amount=Decimal(str(request.vat_amount)),
        vendor_name=request.vendor_name,
        receipt_number=request.receipt_number,
        receipt_file_url=request.receipt_file_url,
        is_tax_deductible=request.is_tax_deductible,
        gl_account_code=request.gl_account_code,
        notes=request.notes,
    )
    
    return ExpenseItemResponse(
        id=str(item.id),
        expense_date=item.expense_date,
        category=item.category.value,
        description=item.description,
        amount=float(item.amount),
        vat_amount=float(item.vat_amount),
        approved_amount=float(item.approved_amount),
        vendor_name=item.vendor_name,
        receipt_number=item.receipt_number,
        has_receipt=item.has_receipt,
        is_tax_deductible=item.is_tax_deductible,
    )


@router.post(
    "/{claim_id}/submit",
    response_model=ExpenseClaimResponse,
    summary="Submit claim for approval",
)
async def submit_expense_claim(
    claim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Submit a draft claim for approval."""
    service = get_expense_claims_service(db)
    
    try:
        claim = await service.submit_claim(claim_id)
        
        # Audit logging
        audit_service = AuditService(db)
        await audit_service.log_action(
            business_entity_id=entity_id,
            entity_type="expense_claim",
            entity_id=str(claim_id),
            action=AuditAction.UPDATE,
            user_id=current_user.id,
            old_values={"status": "draft"},
            new_values={
                "status": "submitted",
                "claim_number": claim.claim_number,
                "total_amount": str(claim.total_amount),
            }
        )
        
        return _claim_to_response(claim)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/{claim_id}/approve",
    response_model=ExpenseClaimResponse,
    summary="Approve expense claim",
)
async def approve_expense_claim(
    claim_id: uuid.UUID,
    request: ClaimApprovalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve a submitted expense claim."""
    service = get_expense_claims_service(db)
    
    try:
        # Convert item adjustments to Decimal
        item_adjustments = None
        if request.item_adjustments:
            item_adjustments = {
                k: Decimal(str(v)) for k, v in request.item_adjustments.items()
            }
        
        claim = await service.approve_claim(
            claim_id=claim_id,
            approved_by_id=current_user.id,
            approval_notes=request.approval_notes,
            item_adjustments=item_adjustments,
        )
        
        # Audit logging
        audit_service = AuditService(db)
        await audit_service.log_action(
            business_entity_id=claim.entity_id,
            entity_type="expense_claim",
            entity_id=str(claim_id),
            action=AuditAction.UPDATE,
            user_id=current_user.id,
            old_values={"status": "submitted"},
            new_values={
                "status": "approved",
                "approved_amount": str(claim.approved_amount),
                "approval_notes": request.approval_notes,
            }
        )
        
        return _claim_to_response(claim)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/{claim_id}/reject",
    response_model=ExpenseClaimResponse,
    summary="Reject expense claim",
)
async def reject_expense_claim(
    claim_id: uuid.UUID,
    request: ClaimRejectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reject a submitted expense claim."""
    service = get_expense_claims_service(db)
    
    try:
        claim = await service.reject_claim(
            claim_id=claim_id,
            rejected_by_id=current_user.id,
            rejection_reason=request.rejection_reason,
        )
        
        # Audit logging
        audit_service = AuditService(db)
        await audit_service.log_action(
            business_entity_id=claim.entity_id,
            entity_type="expense_claim",
            entity_id=str(claim_id),
            action=AuditAction.UPDATE,
            user_id=current_user.id,
            old_values={"status": "submitted"},
            new_values={
                "status": "rejected",
                "rejection_reason": request.rejection_reason,
            }
        )
        
        return _claim_to_response(claim)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/{claim_id}/pay",
    response_model=ExpenseClaimResponse,
    summary="Mark claim as paid",
)
async def mark_claim_paid(
    claim_id: uuid.UUID,
    request: ClaimPaymentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark an approved claim as paid/reimbursed."""
    service = get_expense_claims_service(db)
    
    try:
        claim = await service.mark_as_paid(
            claim_id=claim_id,
            payment_method=request.payment_method,
            payment_reference=request.payment_reference,
        )
        return _claim_to_response(claim)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/summary",
    summary="Get expense claims summary",
)
async def get_claims_summary(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get summary statistics for expense claims."""
    service = get_expense_claims_service(db)
    summary = await service.get_claims_summary(entity_id, date_from, date_to)
    return summary


@router.get(
    "/by-category",
    summary="Get expenses by category",
)
async def get_expenses_by_category(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get expense breakdown by category."""
    service = get_expense_claims_service(db)
    breakdown = await service.get_expense_by_category(entity_id, date_from, date_to)
    return breakdown


def _claim_to_response(claim) -> ExpenseClaimResponse:
    """Convert claim model to response schema."""
    return ExpenseClaimResponse(
        id=str(claim.id),
        claim_number=claim.claim_number,
        title=claim.title,
        description=claim.description,
        expense_date_from=claim.expense_date_from,
        expense_date_to=claim.expense_date_to,
        currency=claim.currency,
        total_amount=float(claim.total_amount),
        approved_amount=float(claim.approved_amount),
        status=claim.status.value,
        submitted_at=claim.submitted_at,
        approved_at=claim.approved_at,
        paid_at=claim.paid_at,
        line_items=[
            ExpenseItemResponse(
                id=str(item.id),
                expense_date=item.expense_date,
                category=item.category.value,
                description=item.description,
                amount=float(item.amount),
                vat_amount=float(item.vat_amount),
                approved_amount=float(item.approved_amount),
                vendor_name=item.vendor_name,
                receipt_number=item.receipt_number,
                has_receipt=item.has_receipt,
                is_tax_deductible=item.is_tax_deductible,
            )
            for item in (claim.line_items or [])
        ],
    )
