"""
Tekvwa Pro Audit - Vendors Router

API endpoints for vendor management with TIN verification.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import get_current_active_user, record_usage_event, require_within_usage_limit
from app.models.user import User
from app.models.audit_consolidated import AuditAction
from app.models.sku import UsageMetricType
from app.schemas.auth import MessageResponse
from app.schemas.vendor import (
    VendorCreateRequest,
    VendorUpdateRequest,
    VendorResponse,
    VendorListResponse,
    TINVerificationResponse,
)
from app.services.vendor_service import VendorService
from app.services.entity_service import EntityService
from app.services.audit_service import AuditService


router = APIRouter()


@router.get(
    "/{entity_id}/vendors",
    response_model=VendorListResponse,
    summary="List vendors",
    description="Get all vendors for a business entity.",
)
async def list_vendors(
    entity_id: UUID,
    search: Optional[str] = Query(None, description="Search by name, TIN, or email"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """List all vendors for an entity."""
    # Verify entity access
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    vendor_service = VendorService(db)
    vendors = await vendor_service.get_vendors_for_entity(
        entity_id,
        search=search,
    )
    
    vendor_responses = []
    for vendor in vendors:
        stats = await vendor_service.get_vendor_stats(vendor)
        vendor_responses.append(
            VendorResponse(
                id=vendor.id,
                entity_id=vendor.entity_id,
                name=vendor.name,
                tin=vendor.tin,
                contact_person=vendor.contact_person,
                email=vendor.email,
                phone=vendor.phone,
                address=vendor.address,
                city=vendor.city,
                state=vendor.state,
                country=vendor.country,
                bank_name=vendor.bank_name,
                bank_account_number=vendor.bank_account_number,
                bank_account_name=vendor.bank_account_name,
                is_vat_registered=vendor.is_vat_registered,
                default_wht_rate=vendor.default_wht_rate,
                tin_verified=vendor.tin_verified,
                tin_verified_at=vendor.tin_verified_at,
                total_paid=stats["total_paid"],
                transaction_count=stats["transaction_count"],
                notes=vendor.notes,
                is_active=vendor.is_active,
                created_at=vendor.created_at,
                updated_at=vendor.updated_at,
            )
        )
    
    return VendorListResponse(
        vendors=vendor_responses,
        total=len(vendor_responses),
    )


@router.post(
    "/{entity_id}/vendors",
    response_model=VendorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create vendor",
    description="Create a new vendor for a business entity.",
)
async def create_vendor(
    entity_id: UUID,
    request: VendorCreateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
    _limit_check: User = Depends(require_within_usage_limit(UsageMetricType.TRANSACTIONS)),
):
    """Create a new vendor."""
    # Verify entity access and write permission
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    can_write = await entity_service.check_user_can_write(current_user, entity_id)
    if not can_write:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access denied for this entity",
        )
    
    vendor_service = VendorService(db)
    
    try:
        vendor = await vendor_service.create_vendor(
            entity_id=entity_id,
            name=request.name,
            tin=request.tin,
            contact_person=request.contact_person,
            email=request.email,
            phone=request.phone,
            address=request.address,
            city=request.city,
            state=request.state,
            bank_name=request.bank_name,
            bank_account_number=request.bank_account_number,
            bank_account_name=request.bank_account_name,
            is_vat_registered=request.is_vat_registered,
            default_wht_rate=request.default_wht_rate,
            notes=request.notes,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    # Audit log for vendor creation
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="vendor",
        entity_id=str(vendor.id),
        action=AuditAction.CREATE,
        user_id=current_user.id,
        new_values={
            "name": request.name,
            "tin": request.tin,
            "email": request.email,
            "phone": request.phone,
            "is_vat_registered": request.is_vat_registered,
        },
    )
    
    # Record usage metering for SKU tier limits
    if current_user.organization_id:
        await record_usage_event(
            db=db,
            organization_id=current_user.organization_id,
            metric_type=UsageMetricType.TRANSACTIONS,
            entity_id=entity_id,
            user_id=current_user.id,
            resource_type="vendor",
            resource_id=str(vendor.id),
        )
    
    return VendorResponse(
        id=vendor.id,
        entity_id=vendor.entity_id,
        name=vendor.name,
        tin=vendor.tin,
        contact_person=vendor.contact_person,
        email=vendor.email,
        phone=vendor.phone,
        address=vendor.address,
        city=vendor.city,
        state=vendor.state,
        country=vendor.country,
        bank_name=vendor.bank_name,
        bank_account_number=vendor.bank_account_number,
        bank_account_name=vendor.bank_account_name,
        is_vat_registered=vendor.is_vat_registered,
        default_wht_rate=vendor.default_wht_rate,
        tin_verified=vendor.tin_verified,
        tin_verified_at=vendor.tin_verified_at,
        total_paid=0.0,
        transaction_count=0,
        notes=vendor.notes,
        is_active=vendor.is_active,
        created_at=vendor.created_at,
        updated_at=vendor.updated_at,
    )


@router.get(
    "/{entity_id}/vendors/{vendor_id}",
    response_model=VendorResponse,
    summary="Get vendor",
    description="Get a specific vendor by ID.",
)
async def get_vendor(
    entity_id: UUID,
    vendor_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get a specific vendor."""
    # Verify entity access
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    vendor_service = VendorService(db)
    vendor = await vendor_service.get_vendor_by_id(vendor_id, entity_id)
    
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found",
        )
    
    stats = await vendor_service.get_vendor_stats(vendor)
    
    return VendorResponse(
        id=vendor.id,
        entity_id=vendor.entity_id,
        name=vendor.name,
        tin=vendor.tin,
        contact_person=vendor.contact_person,
        email=vendor.email,
        phone=vendor.phone,
        address=vendor.address,
        city=vendor.city,
        state=vendor.state,
        country=vendor.country,
        bank_name=vendor.bank_name,
        bank_account_number=vendor.bank_account_number,
        bank_account_name=vendor.bank_account_name,
        is_vat_registered=vendor.is_vat_registered,
        default_wht_rate=vendor.default_wht_rate,
        tin_verified=vendor.tin_verified,
        tin_verified_at=vendor.tin_verified_at,
        total_paid=stats["total_paid"],
        transaction_count=stats["transaction_count"],
        notes=vendor.notes,
        is_active=vendor.is_active,
        created_at=vendor.created_at,
        updated_at=vendor.updated_at,
    )


@router.patch(
    "/{entity_id}/vendors/{vendor_id}",
    response_model=VendorResponse,
    summary="Update vendor",
    description="Update a vendor. Changing TIN will reset verification status.",
)
async def update_vendor(
    entity_id: UUID,
    vendor_id: UUID,
    request: VendorUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Update a vendor."""
    # Verify entity access and write permission
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    can_write = await entity_service.check_user_can_write(current_user, entity_id)
    if not can_write:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access denied for this entity",
        )
    
    vendor_service = VendorService(db)
    vendor = await vendor_service.get_vendor_by_id(vendor_id, entity_id)
    
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found",
        )
    
    # Store old values for audit
    old_values = {
        "name": vendor.name,
        "tin": vendor.tin,
        "email": vendor.email,
        "phone": vendor.phone,
    }
    
    update_data = request.model_dump(exclude_unset=True)
    vendor = await vendor_service.update_vendor(vendor, **update_data)
    
    # Audit log for vendor update
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="vendor",
        entity_id=str(vendor.id),
        action=AuditAction.UPDATE,
        user_id=current_user.id,
        old_values=old_values,
        new_values=update_data,
    )
    
    stats = await vendor_service.get_vendor_stats(vendor)
    
    return VendorResponse(
        id=vendor.id,
        entity_id=vendor.entity_id,
        name=vendor.name,
        tin=vendor.tin,
        contact_person=vendor.contact_person,
        email=vendor.email,
        phone=vendor.phone,
        address=vendor.address,
        city=vendor.city,
        state=vendor.state,
        country=vendor.country,
        bank_name=vendor.bank_name,
        bank_account_number=vendor.bank_account_number,
        bank_account_name=vendor.bank_account_name,
        is_vat_registered=vendor.is_vat_registered,
        default_wht_rate=vendor.default_wht_rate,
        tin_verified=vendor.tin_verified,
        tin_verified_at=vendor.tin_verified_at,
        total_paid=stats["total_paid"],
        transaction_count=stats["transaction_count"],
        notes=vendor.notes,
        is_active=vendor.is_active,
        created_at=vendor.created_at,
        updated_at=vendor.updated_at,
    )


@router.delete(
    "/{entity_id}/vendors/{vendor_id}",
    response_model=MessageResponse,
    summary="Delete vendor",
    description="Soft delete a vendor.",
)
async def delete_vendor(
    entity_id: UUID,
    vendor_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Delete a vendor."""
    # Verify entity access and write permission
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    can_write = await entity_service.check_user_can_write(current_user, entity_id)
    if not can_write:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access denied for this entity",
        )
    
    vendor_service = VendorService(db)
    vendor = await vendor_service.get_vendor_by_id(vendor_id, entity_id)
    
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found",
        )
    
    # Store vendor data for audit before deletion
    deleted_values = {
        "name": vendor.name,
        "tin": vendor.tin,
        "email": vendor.email,
    }
    deleted_id = str(vendor.id)
    
    await vendor_service.delete_vendor(vendor)
    
    # Audit log for vendor deletion
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="vendor",
        entity_id=deleted_id,
        action=AuditAction.DELETE,
        user_id=current_user.id,
        old_values=deleted_values,
    )
    
    return MessageResponse(
        message="Vendor deleted successfully",
        success=True,
    )


@router.post(
    "/{entity_id}/vendors/{vendor_id}/verify-tin",
    response_model=TINVerificationResponse,
    summary="Verify vendor TIN",
    description="Verify vendor TIN with FIRS/NRS.",
)
async def verify_vendor_tin(
    entity_id: UUID,
    vendor_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Verify vendor TIN."""
    # Verify entity access
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    vendor_service = VendorService(db)
    vendor = await vendor_service.get_vendor_by_id(vendor_id, entity_id)
    
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found",
        )
    
    if not vendor.tin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vendor has no TIN to verify",
        )
    
    verified, message = await vendor_service.verify_tin(vendor)
    
    return TINVerificationResponse(
        vendor_id=vendor.id,
        tin=vendor.tin,
        verified=verified,
        verified_at=vendor.tin_verified_at if verified else None,
        verification_message=message,
    )


# ===========================================
# ADDITIONAL VENDOR ENDPOINTS
# ===========================================

from typing import List
from pydantic import BaseModel
from datetime import date, datetime


class VendorTransactionResponse(BaseModel):
    """Transaction with this vendor."""
    id: UUID
    transaction_date: date
    description: str
    amount: float
    vat_amount: float
    wht_amount: float
    net_amount: float
    reference: Optional[str]
    category_name: Optional[str]


class VendorTransactionsListResponse(BaseModel):
    """List of vendor transactions."""
    transactions: List[VendorTransactionResponse]
    total: int
    total_amount: float
    total_wht: float


class WHTSummaryResponse(BaseModel):
    """WHT summary for a vendor."""
    vendor_id: UUID
    vendor_name: str
    vendor_tin: Optional[str]
    period_start: date
    period_end: date
    total_payments: float
    total_wht_deducted: float
    transaction_count: int
    transactions: List[dict]


class WHTCertificateResponse(BaseModel):
    """WHT Certificate response."""
    certificate_number: str
    vendor_name: str
    vendor_tin: Optional[str]
    period: str
    total_payments: float
    total_wht: float
    generated_at: datetime
    pdf_url: Optional[str]


class VendorStatsResponse(BaseModel):
    """Vendor statistics."""
    total_vendors: int
    active_vendors: int
    tin_verified_count: int
    total_paid_all_time: float
    avg_payment_amount: float
    top_vendors: List[dict]


@router.get(
    "/{entity_id}/vendors/{vendor_id}/transactions",
    response_model=VendorTransactionsListResponse,
    summary="Get vendor transactions",
    description="Get all transactions with a specific vendor.",
)
async def get_vendor_transactions(
    entity_id: UUID,
    vendor_id: UUID,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get all transactions with a vendor."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    vendor_service = VendorService(db)
    vendor = await vendor_service.get_vendor_by_id(vendor_id, entity_id)
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found",
        )
    
    from sqlalchemy import select
    from app.models.transaction import Transaction
    
    query = select(Transaction).where(
        Transaction.entity_id == entity_id,
        Transaction.vendor_id == vendor_id,
        Transaction.is_deleted == False,
    )
    
    if start_date:
        query = query.where(Transaction.transaction_date >= start_date)
    if end_date:
        query = query.where(Transaction.transaction_date <= end_date)
    
    query = query.order_by(Transaction.transaction_date.desc()).offset(skip).limit(limit)
    
    result = await db.execute(query)
    transactions = result.scalars().all()
    
    txn_responses = []
    for t in transactions:
        wht_amount = float(t.amount) * float(vendor.default_wht_rate or 0) / 100
        txn_responses.append(VendorTransactionResponse(
            id=t.id,
            transaction_date=t.transaction_date,
            description=t.description,
            amount=float(t.amount),
            vat_amount=float(t.vat_amount),
            wht_amount=wht_amount,
            net_amount=float(t.amount) - wht_amount,
            reference=t.reference,
            category_name=t.category.name if t.category else None,
        ))
    
    return VendorTransactionsListResponse(
        transactions=txn_responses,
        total=len(txn_responses),
        total_amount=sum(t.amount for t in txn_responses),
        total_wht=sum(t.wht_amount for t in txn_responses),
    )


@router.get(
    "/{entity_id}/vendors/{vendor_id}/wht-summary",
    response_model=WHTSummaryResponse,
    summary="Get WHT summary for vendor",
    description="Get withholding tax summary for a vendor over a period.",
)
async def get_vendor_wht_summary(
    entity_id: UUID,
    vendor_id: UUID,
    start_date: date = Query(..., description="Period start date"),
    end_date: date = Query(..., description="Period end date"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get WHT summary for a vendor."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    vendor_service = VendorService(db)
    vendor = await vendor_service.get_vendor_by_id(vendor_id, entity_id)
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found",
        )
    
    from sqlalchemy import select, func
    from app.models.transaction import Transaction, TransactionType
    
    query = select(Transaction).where(
        Transaction.entity_id == entity_id,
        Transaction.vendor_id == vendor_id,
        Transaction.transaction_type == TransactionType.EXPENSE,
        Transaction.transaction_date >= start_date,
        Transaction.transaction_date <= end_date,
        Transaction.is_deleted == False,
    )
    
    result = await db.execute(query)
    transactions = result.scalars().all()
    
    wht_rate = float(vendor.default_wht_rate or 0) / 100
    total_payments = sum(float(t.amount) for t in transactions)
    total_wht = total_payments * wht_rate
    
    txn_details = [
        {
            "id": str(t.id),
            "date": t.transaction_date.isoformat(),
            "amount": float(t.amount),
            "wht": float(t.amount) * wht_rate,
            "reference": t.reference,
        }
        for t in transactions
    ]
    
    return WHTSummaryResponse(
        vendor_id=vendor.id,
        vendor_name=vendor.name,
        vendor_tin=vendor.tin,
        period_start=start_date,
        period_end=end_date,
        total_payments=total_payments,
        total_wht_deducted=total_wht,
        transaction_count=len(transactions),
        transactions=txn_details,
    )


@router.post(
    "/{entity_id}/vendors/{vendor_id}/wht-certificate",
    response_model=WHTCertificateResponse,
    summary="Generate WHT certificate",
    description="Generate a WHT certificate PDF for a vendor.",
)
async def generate_wht_certificate(
    entity_id: UUID,
    vendor_id: UUID,
    start_date: date = Query(..., description="Period start date"),
    end_date: date = Query(..., description="Period end date"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Generate WHT certificate for a vendor."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    vendor_service = VendorService(db)
    vendor = await vendor_service.get_vendor_by_id(vendor_id, entity_id)
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found",
        )
    
    from sqlalchemy import select
    from app.models.transaction import Transaction, TransactionType
    import uuid as uuid_lib
    
    query = select(Transaction).where(
        Transaction.entity_id == entity_id,
        Transaction.vendor_id == vendor_id,
        Transaction.transaction_type == TransactionType.EXPENSE,
        Transaction.transaction_date >= start_date,
        Transaction.transaction_date <= end_date,
        Transaction.is_deleted == False,
    )
    
    result = await db.execute(query)
    transactions = result.scalars().all()
    
    wht_rate = float(vendor.default_wht_rate or 0) / 100
    total_payments = sum(float(t.amount) for t in transactions)
    total_wht = total_payments * wht_rate
    
    # Generate certificate number
    cert_number = f"WHT-{entity_id.hex[:8].upper()}-{vendor_id.hex[:4].upper()}-{start_date.strftime('%Y%m')}"
    
    # In production, generate actual PDF here
    return WHTCertificateResponse(
        certificate_number=cert_number,
        vendor_name=vendor.name,
        vendor_tin=vendor.tin,
        period=f"{start_date.isoformat()} to {end_date.isoformat()}",
        total_payments=total_payments,
        total_wht=total_wht,
        generated_at=datetime.utcnow(),
        pdf_url=f"/api/v1/entities/{entity_id}/vendors/{vendor_id}/wht-certificate/download?start_date={start_date}&end_date={end_date}",
    )


@router.get(
    "/{entity_id}/vendors/statistics",
    response_model=VendorStatsResponse,
    summary="Get vendor statistics",
    description="Get overall vendor statistics for the entity.",
)
async def get_vendor_statistics(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get vendor statistics."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    vendor_service = VendorService(db)
    vendors = await vendor_service.get_vendors_for_entity(entity_id)
    
    active_vendors = [v for v in vendors if v.is_active]
    verified_vendors = [v for v in vendors if v.tin_verified]
    
    # Get top vendors by payment
    vendor_stats = []
    for vendor in vendors:
        stats = await vendor_service.get_vendor_stats(vendor)
        vendor_stats.append({
            "id": str(vendor.id),
            "name": vendor.name,
            "total_paid": stats["total_paid"],
        })
    
    vendor_stats.sort(key=lambda x: x["total_paid"], reverse=True)
    top_vendors = vendor_stats[:10]
    
    total_paid = sum(v["total_paid"] for v in vendor_stats)
    avg_payment = total_paid / len(vendor_stats) if vendor_stats else 0
    
    return VendorStatsResponse(
        total_vendors=len(vendors),
        active_vendors=len(active_vendors),
        tin_verified_count=len(verified_vendors),
        total_paid_all_time=total_paid,
        avg_payment_amount=avg_payment,
        top_vendors=top_vendors,
    )


@router.post(
    "/{entity_id}/vendors/{vendor_id}/restore",
    response_model=MessageResponse,
    summary="Restore deleted vendor",
    description="Restore a soft-deleted vendor.",
)
async def restore_vendor(
    entity_id: UUID,
    vendor_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Restore a deleted vendor."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    from sqlalchemy import select, update
    from app.models.vendor import Vendor
    
    # Find the deleted vendor
    result = await db.execute(
        select(Vendor).where(
            Vendor.id == vendor_id,
            Vendor.entity_id == entity_id,
        )
    )
    vendor = result.scalar_one_or_none()
    
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found",
        )
    
    if vendor.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vendor is not deleted",
        )
    
    vendor.is_active = True
    await db.commit()
    
    return MessageResponse(message="Vendor restored successfully")
