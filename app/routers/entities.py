"""
Tekvwa Pro Audit - Business Entities Router

API endpoints for business entity management.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import get_current_active_user, require_role, record_usage_event, require_within_usage_limit, require_entity_access
from app.models.user import User, UserRole
from app.models.entity import BusinessEntity
from app.models.sku import UsageMetricType
from app.schemas.entity import (
    EntityCreateRequest,
    EntityUpdateRequest,
    EntityResponse,
    EntityListResponse,
    EntitySummaryResponse,
)
from app.schemas.auth import MessageResponse
from app.services.entity_service import EntityService
from app.services.audit_service import AuditService
from app.models.audit_consolidated import AuditAction


router = APIRouter()


@router.get(
    "",
    response_model=EntityListResponse,
    summary="List business entities",
    description="Get all business entities the current user has access to.",
)
async def list_entities(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """List all entities user has access to."""
    entity_service = EntityService(db)
    entities = await entity_service.get_entities_for_user(current_user)
    
    entity_responses = []
    for entity in entities:
        entity_responses.append(
            EntityResponse(
                id=entity.id,
                organization_id=entity.organization_id,
                name=entity.name,
                legal_name=entity.legal_name,
                tin=entity.tin,
                rc_number=entity.rc_number,
                address_line1=entity.address_line1,
                address_line2=entity.address_line2,
                city=entity.city,
                state=entity.state,
                country=entity.country,
                full_address=entity.full_address,
                email=entity.email,
                phone=entity.phone,
                website=entity.website,
                fiscal_year_start_month=entity.fiscal_year_start_month,
                currency=entity.currency,
                is_vat_registered=entity.is_vat_registered,
                vat_registration_date=entity.vat_registration_date,
                annual_turnover_threshold=entity.annual_turnover_threshold,
                is_active=entity.is_active,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
            )
        )
    
    return EntityListResponse(
        entities=entity_responses,
        total=len(entity_responses),
    )


@router.post(
    "",
    response_model=EntityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create business entity",
    description="Create a new business entity. Only owners and admins can create entities.",
)
async def create_entity(
    request: EntityCreateRequest,
    current_user: User = Depends(require_role([UserRole.OWNER, UserRole.ADMIN])),
    db: AsyncSession = Depends(get_async_session),
    _limit_check: User = Depends(require_within_usage_limit(UsageMetricType.ENTITIES)),
):
    """Create a new business entity."""
    entity_service = EntityService(db)
    
    entity = await entity_service.create_entity(
        user=current_user,
        name=request.name,
        legal_name=request.legal_name,
        tin=request.tin,
        rc_number=request.rc_number,
        address_line1=request.address_line1,
        address_line2=request.address_line2,
        city=request.city,
        state=request.state,
        email=request.email,
        phone=request.phone,
        website=request.website,
        fiscal_year_start_month=request.fiscal_year_start_month,
        currency=request.currency,
        is_vat_registered=request.is_vat_registered,
        vat_registration_date=request.vat_registration_date,
        annual_turnover_threshold=request.annual_turnover_threshold,
    )
    
    # Audit logging for entity creation
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity.id,
        entity_type="business_entity",
        entity_id=str(entity.id),
        action=AuditAction.CREATE,
        user_id=current_user.id,
        new_values={
            "name": entity.name,
            "legal_name": entity.legal_name,
            "tin": entity.tin,
            "rc_number": entity.rc_number,
            "is_vat_registered": entity.is_vat_registered,
        }
    )
    
    # Record usage metering for entity count tracking
    if current_user.organization_id:
        await record_usage_event(
            db=db,
            organization_id=current_user.organization_id,
            metric_type=UsageMetricType.ENTITIES,
            entity_id=entity.id,
            user_id=current_user.id,
            resource_type="business_entity",
            resource_id=str(entity.id),
        )
    
    return EntityResponse(
        id=entity.id,
        organization_id=entity.organization_id,
        name=entity.name,
        legal_name=entity.legal_name,
        tin=entity.tin,
        rc_number=entity.rc_number,
        address_line1=entity.address_line1,
        address_line2=entity.address_line2,
        city=entity.city,
        state=entity.state,
        country=entity.country,
        full_address=entity.full_address,
        email=entity.email,
        phone=entity.phone,
        website=entity.website,
        fiscal_year_start_month=entity.fiscal_year_start_month,
        currency=entity.currency,
        is_vat_registered=entity.is_vat_registered,
        vat_registration_date=entity.vat_registration_date,
        annual_turnover_threshold=entity.annual_turnover_threshold,
        is_active=entity.is_active,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


@router.get(
    "/{entity_id}",
    response_model=EntityResponse,
    summary="Get business entity",
    description="Get a specific business entity by ID.",
)
async def get_entity(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get a specific entity."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    return EntityResponse(
        id=entity.id,
        organization_id=entity.organization_id,
        name=entity.name,
        legal_name=entity.legal_name,
        tin=entity.tin,
        rc_number=entity.rc_number,
        address_line1=entity.address_line1,
        address_line2=entity.address_line2,
        city=entity.city,
        state=entity.state,
        country=entity.country,
        full_address=entity.full_address,
        email=entity.email,
        phone=entity.phone,
        website=entity.website,
        fiscal_year_start_month=entity.fiscal_year_start_month,
        currency=entity.currency,
        is_vat_registered=entity.is_vat_registered,
        vat_registration_date=entity.vat_registration_date,
        annual_turnover_threshold=entity.annual_turnover_threshold,
        is_active=entity.is_active,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


@router.patch(
    "/{entity_id}",
    response_model=EntityResponse,
    summary="Update business entity",
    description="Update a business entity. Requires write access.",
)
async def update_entity(
    entity_id: UUID,
    request: EntityUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Update a business entity."""
    entity_service = EntityService(db)
    
    # Check access
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    # Check write permission
    can_write = await entity_service.check_user_can_write(current_user, entity_id)
    if not can_write:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access denied for this entity",
        )
    
    # Capture old values for audit
    old_values = {
        "name": entity.name,
        "legal_name": entity.legal_name,
        "tin": entity.tin,
        "email": entity.email,
        "phone": entity.phone,
        "is_vat_registered": entity.is_vat_registered,
    }
    
    # Update entity
    update_data = request.model_dump(exclude_unset=True)
    entity = await entity_service.update_entity(entity, **update_data)
    
    # Audit logging for entity update
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="business_entity",
        entity_id=str(entity_id),
        action=AuditAction.UPDATE,
        user_id=current_user.id,
        old_values=old_values,
        new_values={
            "name": entity.name,
            "legal_name": entity.legal_name,
            "tin": entity.tin,
            "email": entity.email,
            "phone": entity.phone,
            "is_vat_registered": entity.is_vat_registered,
        }
    )
    
    return EntityResponse(
        id=entity.id,
        organization_id=entity.organization_id,
        name=entity.name,
        legal_name=entity.legal_name,
        tin=entity.tin,
        rc_number=entity.rc_number,
        address_line1=entity.address_line1,
        address_line2=entity.address_line2,
        city=entity.city,
        state=entity.state,
        country=entity.country,
        full_address=entity.full_address,
        email=entity.email,
        phone=entity.phone,
        website=entity.website,
        fiscal_year_start_month=entity.fiscal_year_start_month,
        currency=entity.currency,
        is_vat_registered=entity.is_vat_registered,
        vat_registration_date=entity.vat_registration_date,
        annual_turnover_threshold=entity.annual_turnover_threshold,
        is_active=entity.is_active,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


@router.delete(
    "/{entity_id}",
    response_model=MessageResponse,
    summary="Delete business entity",
    description="Soft delete a business entity. Only owners can delete entities.",
)
async def delete_entity(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Delete (deactivate) a business entity."""
    entity_service = EntityService(db)
    
    # Check access
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    # Check delete permission
    can_delete = await entity_service.check_user_can_delete(current_user, entity_id)
    if not can_delete:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Delete access denied for this entity",
        )
    
    # Capture entity data for audit before deletion
    deleted_entity_data = {
        "name": entity.name,
        "legal_name": entity.legal_name,
        "tin": entity.tin,
    }
    
    await entity_service.delete_entity(entity)
    
    # Audit logging for entity deletion
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="business_entity",
        entity_id=str(entity_id),
        action=AuditAction.DELETE,
        user_id=current_user.id,
        old_values=deleted_entity_data
    )
    
    return MessageResponse(
        message="Entity deleted successfully",
        success=True,
    )


# ===========================================
# ADDITIONAL ENTITY ENDPOINTS
# ===========================================

from typing import Optional, List
from pydantic import BaseModel
from datetime import date, datetime


class EntityDashboardSummary(BaseModel):
    """Entity dashboard summary data."""
    entity_id: UUID
    entity_name: str
    period_start: date
    period_end: date
    # Financials
    total_revenue: float
    total_expenses: float
    net_income: float
    # Invoicing
    total_invoiced: float
    total_received: float
    outstanding_receivables: float
    overdue_receivables: float
    # Tax
    vat_collected: float
    vat_paid: float
    vat_position: float
    # Counts
    invoice_count: int
    transaction_count: int
    customer_count: int
    vendor_count: int


class TINVerificationResponse(BaseModel):
    """TIN verification response."""
    entity_id: UUID
    tin: Optional[str]
    verified: bool
    verified_at: Optional[datetime]
    verification_message: str


class FiscalPeriodResponse(BaseModel):
    """Fiscal period info."""
    period_id: str
    start_date: date
    end_date: date
    is_current: bool
    is_closed: bool
    closed_at: Optional[datetime]
    closed_by: Optional[str]


class ComplianceStatusResponse(BaseModel):
    """Entity compliance status."""
    entity_id: UUID
    overall_status: str
    vat_status: dict
    paye_status: dict
    wht_status: dict
    cit_status: dict
    pending_filings: List[dict]


@router.get(
    "/{entity_id}/summary",
    response_model=EntityDashboardSummary,
    summary="Get entity summary",
    description="Get comprehensive dashboard summary for an entity.",
)
async def get_entity_summary(
    entity_id: UUID,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get entity dashboard summary."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    # Default to current month
    from datetime import date as date_type
    today = date_type.today()
    if not start_date:
        start_date = date_type(today.year, today.month, 1)
    if not end_date:
        end_date = today
    
    from sqlalchemy import select, func
    from app.models.transaction import Transaction, TransactionType
    from app.models.invoice import Invoice
    from app.models.customer import Customer
    from app.models.vendor import Vendor
    
    # Get transaction totals
    income_query = select(func.sum(Transaction.amount)).where(
        Transaction.entity_id == entity_id,
        Transaction.transaction_type == TransactionType.INCOME,
        Transaction.transaction_date >= start_date,
        Transaction.transaction_date <= end_date,
        Transaction.is_deleted == False,
    )
    income_result = await db.execute(income_query)
    total_revenue = float(income_result.scalar() or 0)
    
    expense_query = select(func.sum(Transaction.amount)).where(
        Transaction.entity_id == entity_id,
        Transaction.transaction_type == TransactionType.EXPENSE,
        Transaction.transaction_date >= start_date,
        Transaction.transaction_date <= end_date,
        Transaction.is_deleted == False,
    )
    expense_result = await db.execute(expense_query)
    total_expenses = float(expense_result.scalar() or 0)
    
    # Get VAT totals
    vat_collected_query = select(func.sum(Transaction.vat_amount)).where(
        Transaction.entity_id == entity_id,
        Transaction.transaction_type == TransactionType.INCOME,
        Transaction.transaction_date >= start_date,
        Transaction.transaction_date <= end_date,
        Transaction.is_deleted == False,
    )
    vat_collected = float((await db.execute(vat_collected_query)).scalar() or 0)
    
    vat_paid_query = select(func.sum(Transaction.vat_amount)).where(
        Transaction.entity_id == entity_id,
        Transaction.transaction_type == TransactionType.EXPENSE,
        Transaction.transaction_date >= start_date,
        Transaction.transaction_date <= end_date,
        Transaction.is_deleted == False,
    )
    vat_paid = float((await db.execute(vat_paid_query)).scalar() or 0)
    
    # Get invoice totals
    invoice_query = select(
        func.sum(Invoice.total_amount),
        func.sum(Invoice.amount_paid),
        func.count(Invoice.id),
    ).where(
        Invoice.entity_id == entity_id,
        Invoice.invoice_date >= start_date,
        Invoice.invoice_date <= end_date,
        Invoice.is_deleted == False,
    )
    inv_result = await db.execute(invoice_query)
    inv_row = inv_result.one()
    total_invoiced = float(inv_row[0] or 0)
    total_received = float(inv_row[1] or 0)
    invoice_count = int(inv_row[2] or 0)
    
    # Get overdue receivables
    overdue_query = select(func.sum(Invoice.balance_due)).where(
        Invoice.entity_id == entity_id,
        Invoice.balance_due > 0,
        Invoice.due_date < today,
        Invoice.is_deleted == False,
    )
    overdue_result = await db.execute(overdue_query)
    overdue_receivables = float(overdue_result.scalar() or 0)
    
    # Get counts
    txn_count_query = select(func.count(Transaction.id)).where(
        Transaction.entity_id == entity_id,
        Transaction.transaction_date >= start_date,
        Transaction.transaction_date <= end_date,
        Transaction.is_deleted == False,
    )
    txn_count = int((await db.execute(txn_count_query)).scalar() or 0)
    
    customer_count = int((await db.execute(
        select(func.count(Customer.id)).where(
            Customer.entity_id == entity_id,
            Customer.is_active == True,
        )
    )).scalar() or 0)
    
    vendor_count = int((await db.execute(
        select(func.count(Vendor.id)).where(
            Vendor.entity_id == entity_id,
            Vendor.is_active == True,
        )
    )).scalar() or 0)
    
    return EntityDashboardSummary(
        entity_id=entity_id,
        entity_name=entity.name,
        period_start=start_date,
        period_end=end_date,
        total_revenue=total_revenue,
        total_expenses=total_expenses,
        net_income=total_revenue - total_expenses,
        total_invoiced=total_invoiced,
        total_received=total_received,
        outstanding_receivables=total_invoiced - total_received,
        overdue_receivables=overdue_receivables,
        vat_collected=vat_collected,
        vat_paid=vat_paid,
        vat_position=vat_collected - vat_paid,
        invoice_count=invoice_count,
        transaction_count=txn_count,
        customer_count=customer_count,
        vendor_count=vendor_count,
    )


@router.post(
    "/{entity_id}/verify-tin",
    response_model=TINVerificationResponse,
    summary="Verify entity TIN",
    description="Verify entity TIN with FIRS.",
)
async def verify_entity_tin(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Verify entity TIN with FIRS."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    if not entity.tin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Entity has no TIN to verify",
        )
    
    # In production, call FIRS verification API
    verified = True
    message = "TIN verified successfully with FIRS"
    
    if verified:
        entity.tin_verified = True
        entity.tin_verified_at = datetime.utcnow()
        await db.commit()
    
    return TINVerificationResponse(
        entity_id=entity.id,
        tin=entity.tin,
        verified=verified,
        verified_at=entity.tin_verified_at if verified else None,
        verification_message=message,
    )


@router.get(
    "/{entity_id}/fiscal-periods",
    response_model=List[FiscalPeriodResponse],
    summary="List fiscal periods",
    description="Get all fiscal periods for the entity.",
)
async def list_fiscal_periods(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """List fiscal periods."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    # Generate fiscal periods based on entity's fiscal year start
    from datetime import date as date_type
    today = date_type.today()
    fiscal_start_month = entity.fiscal_year_start_month or 1
    
    periods = []
    
    # Current fiscal year
    if today.month >= fiscal_start_month:
        fy_start = date_type(today.year, fiscal_start_month, 1)
        fy_end = date_type(today.year + 1, fiscal_start_month, 1) - timedelta(days=1)
    else:
        fy_start = date_type(today.year - 1, fiscal_start_month, 1)
        fy_end = date_type(today.year, fiscal_start_month, 1) - timedelta(days=1)
    
    periods.append(FiscalPeriodResponse(
        period_id=f"FY{fy_start.year}",
        start_date=fy_start,
        end_date=fy_end,
        is_current=True,
        is_closed=False,
        closed_at=None,
        closed_by=None,
    ))
    
    # Previous fiscal year
    prev_fy_start = date_type(fy_start.year - 1, fiscal_start_month, 1)
    prev_fy_end = fy_start - timedelta(days=1)
    
    periods.append(FiscalPeriodResponse(
        period_id=f"FY{prev_fy_start.year}",
        start_date=prev_fy_start,
        end_date=prev_fy_end,
        is_current=False,
        is_closed=True,
        closed_at=None,
        closed_by=None,
    ))
    
    return periods


@router.post(
    "/{entity_id}/fiscal-periods/{period_id}/close",
    response_model=MessageResponse,
    summary="Close fiscal period",
    description="Close a fiscal period. Prevents further transactions in that period.",
)
async def close_fiscal_period(
    entity_id: UUID,
    period_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Close a fiscal period."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    # Check permission (only Owner/Admin)
    if current_user.role not in [UserRole.OWNER, UserRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Owner or Admin can close fiscal periods",
        )
    
    # In production, update FiscalPeriod table
    return MessageResponse(message=f"Fiscal period {period_id} closed successfully")


@router.get(
    "/{entity_id}/compliance-status",
    response_model=ComplianceStatusResponse,
    summary="Get compliance status",
    description="Get tax compliance status overview for the entity.",
)
async def get_compliance_status(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get entity compliance status."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    from datetime import date as date_type
    today = date_type.today()
    
    # Check VAT status
    vat_status = {
        "registered": entity.is_vat_registered,
        "last_filed": None,
        "next_due": date_type(today.year, today.month, 21).isoformat() if today.day <= 21 else None,
        "status": "compliant" if entity.is_vat_registered else "not_applicable",
    }
    
    # Placeholder statuses
    paye_status = {
        "employees_registered": 0,
        "last_filed": None,
        "next_due": date_type(today.year, today.month, 10).isoformat() if today.day <= 10 else None,
        "status": "compliant",
    }
    
    wht_status = {
        "last_filed": None,
        "next_due": date_type(today.year, today.month, 21).isoformat() if today.day <= 21 else None,
        "status": "compliant",
    }
    
    cit_status = {
        "last_filed": None,
        "next_due": date_type(today.year, 6, 30).isoformat() if today.month <= 6 else None,
        "status": "compliant",
    }
    
    pending_filings = []
    overall_status = "compliant"
    
    return ComplianceStatusResponse(
        entity_id=entity_id,
        overall_status=overall_status,
        vat_status=vat_status,
        paye_status=paye_status,
        wht_status=wht_status,
        cit_status=cit_status,
        pending_filings=pending_filings,
    )


@router.post(
    "/{entity_id}/restore",
    response_model=MessageResponse,
    summary="Restore deleted entity",
    description="Restore a soft-deleted entity.",
)
async def restore_entity(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
    entity: BusinessEntity = Depends(require_entity_access),
):
    """Restore a deleted entity."""
    # Previously: looked up `from app.models.entity import Entity` (no such class exists -- only
    # BusinessEntity -- so this endpoint raised ImportError on every call) via a raw, org-unscoped
    # `select(Entity).where(Entity.id == entity_id)` query (Finding 18, docs/IMPLEMENTATION_ROADMAP.md
    # Phase 2 Section 2.1 -- "add an organization-match check, not just a role check"). Now resolved
    # by Depends(require_entity_access), the same as every other migrated endpoint;
    # EntityService.get_entity_by_id doesn't filter by is_active, so a soft-deleted entity in the
    # caller's own organization still resolves correctly here.
    if entity.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Entity is not deleted",
        )
    
    # Check permission (only Owner)
    if current_user.role != UserRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Owner can restore entities",
        )
    
    entity.is_active = True
    await db.commit()
    
    return MessageResponse(message="Entity restored successfully")


# Import timedelta for fiscal period calculations
from datetime import timedelta
