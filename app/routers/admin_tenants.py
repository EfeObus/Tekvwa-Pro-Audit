"""
Tekvwa Pro Audit - Admin Tenants Router

Platform staff endpoints for managing tenants (organizations).
Accessible by SUPER_ADMIN and ADMIN platform roles.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_async_session
from app.dependencies import get_current_platform_admin, require_super_admin
from app.models.user import User, PlatformRole, UserRole
from app.models.organization import Organization
from app.models.sku import TenantSKU, SKUTier
from app.models.entity import BusinessEntity


router = APIRouter(prefix="/admin/tenants", tags=["Admin - Tenant Management"])


# ========= SCHEMAS =========

class TenantCreate(BaseModel):
    """Create a new tenant (organization)."""
    name: str = Field(..., min_length=2, max_length=200, description="Organization name")
    slug: Optional[str] = Field(None, min_length=2, max_length=50, description="URL-friendly slug")
    contact_email: EmailStr = Field(..., description="Primary contact email")
    contact_name: Optional[str] = Field(None, max_length=100, description="Primary contact name")
    phone: Optional[str] = Field(None, max_length=20, description="Phone number")
    address: Optional[str] = Field(None, max_length=500, description="Business address")
    industry: Optional[str] = Field(None, max_length=100, description="Industry category")
    tier: SKUTier = Field(default=SKUTier.CORE, description="Initial SKU tier")


class TenantUpdate(BaseModel):
    """Update tenant details."""
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    slug: Optional[str] = Field(None, min_length=2, max_length=50)
    contact_email: Optional[EmailStr] = None
    contact_name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    address: Optional[str] = Field(None, max_length=500)
    industry: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None


class TenantSuspend(BaseModel):
    """Suspend a tenant with reason."""
    reason: str = Field(..., min_length=10, max_length=500, description="Reason for suspension")
    notify_users: bool = Field(default=True, description="Send email notification to users")


class TenantResponse(BaseModel):
    """Tenant response with full details."""
    id: UUID
    name: str
    slug: Optional[str] = None
    contact_email: Optional[str] = None
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    industry: Optional[str] = None
    is_active: bool
    is_suspended: bool = False
    suspended_reason: Optional[str] = None
    suspended_at: Optional[datetime] = None
    tier: Optional[str] = None
    user_count: int = 0
    entity_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class TenantListResponse(BaseModel):
    """Paginated tenant list."""
    tenants: List[TenantResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class TenantStats(BaseModel):
    """Tenant statistics."""
    total: int
    active: int
    trial: int
    suspended: int
    by_tier: dict


# ========= ENDPOINTS =========

@router.get("", response_model=TenantListResponse)
async def list_tenants(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_platform_admin),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search by name or email"),
    status_filter: Optional[str] = Query(None, description="Filter by status: active, suspended, trial"),
    tier: Optional[str] = Query(None, description="Filter by SKU tier"),
):
    """
    List all tenants with filtering and pagination.
    Platform admin only.
    """
    query = select(Organization).order_by(Organization.created_at.desc())
    
    # Apply search filter
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                Organization.name.ilike(search_term),
                Organization.contact_email.ilike(search_term),
                Organization.slug.ilike(search_term),
            )
        )
    
    # Apply status filter
    # Note: Organization model uses is_emergency_suspended instead of is_active
    if status_filter == "active":
        query = query.where(Organization.is_emergency_suspended == False)
    elif status_filter == "suspended":
        query = query.where(Organization.is_emergency_suspended == True)
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    
    result = await db.execute(query)
    organizations = result.scalars().all()
    
    # Build response with additional data
    tenants = []
    for org in organizations:
        # Get user count
        user_count_result = await db.execute(
            select(func.count()).where(User.organization_id == org.id)
        )
        user_count = user_count_result.scalar() or 0
        
        # Get entity count
        entity_count_result = await db.execute(
            select(func.count()).where(BusinessEntity.organization_id == org.id)
        )
        entity_count = entity_count_result.scalar() or 0
        
        # Get tier from TenantSKU
        sku_result = await db.execute(
            select(TenantSKU).where(TenantSKU.organization_id == org.id)
        )
        sku = sku_result.scalar_one_or_none()
        
        tenants.append(TenantResponse(
            id=org.id,
            name=org.name,
            slug=getattr(org, 'slug', None),
            contact_email=getattr(org, 'email', None),  # Use 'email' field from Organization
            contact_name=getattr(org, 'contact_name', None),
            phone=getattr(org, 'phone', None),
            address=getattr(org, 'address', None),
            industry=getattr(org, 'industry', None),
            is_active=not getattr(org, 'is_emergency_suspended', False),  # Derived from is_emergency_suspended
            is_suspended=getattr(org, 'is_emergency_suspended', False),
            suspended_reason=getattr(org, 'emergency_suspension_reason', None),
            suspended_at=getattr(org, 'emergency_suspended_at', None),
            tier=sku.tier.value if sku else None,
            user_count=user_count,
            entity_count=entity_count,
            created_at=org.created_at,
            updated_at=org.updated_at,
        ))
    
    total_pages = (total + page_size - 1) // page_size
    
    return TenantListResponse(
        tenants=tenants,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/stats", response_model=TenantStats)
async def get_tenant_stats(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_platform_admin),
):
    """
    Get tenant statistics.
    Platform admin only.
    """
    # Total
    total_result = await db.execute(select(func.count(Organization.id)))
    total = total_result.scalar() or 0
    
    # Active (not emergency suspended)
    active_result = await db.execute(
        select(func.count(Organization.id)).where(Organization.is_emergency_suspended == False)
    )
    active = active_result.scalar() or 0
    
    # Trial - this field doesn't exist, set to 0
    trial = 0
    
    # Suspended (emergency suspended)
    suspended_result = await db.execute(
        select(func.count(Organization.id)).where(Organization.is_emergency_suspended == True)
    )
    suspended = suspended_result.scalar() or 0
    
    # By tier - simplified without iteration
    by_tier = {}
    try:
        tier_result = await db.execute(
            select(TenantSKU.tier, func.count(TenantSKU.id))
            .group_by(TenantSKU.tier)
        )
        for row in tier_result:
            tier_val = row[0].value if row[0] else "unknown"
            by_tier[tier_val] = row[1]
    except Exception as e:
        # If SKU table query fails, return empty dict
        by_tier = {"core": 0, "professional": 0, "enterprise": 0}
    
    return TenantStats(
        total=total,
        active=active,
        trial=trial,
        suspended=suspended,
        by_tier=by_tier,
    )


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_platform_admin),
):
    """
    Get a specific tenant by ID.
    Platform admin only.
    """
    result = await db.execute(
        select(Organization).where(Organization.id == tenant_id)
    )
    org = result.scalar_one_or_none()
    
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    
    # Get counts
    user_count_result = await db.execute(
        select(func.count()).where(User.organization_id == org.id)
    )
    user_count = user_count_result.scalar() or 0
    
    entity_count_result = await db.execute(
        select(func.count()).where(BusinessEntity.organization_id == org.id)
    )
    entity_count = entity_count_result.scalar() or 0
    
    # Get tier
    sku_result = await db.execute(
        select(TenantSKU).where(TenantSKU.organization_id == org.id)
    )
    sku = sku_result.scalar_one_or_none()
    
    return TenantResponse(
        id=org.id,
        name=org.name,
        slug=getattr(org, 'slug', None),
        contact_email=getattr(org, 'email', None),  # Use 'email' field from Organization
        contact_name=getattr(org, 'contact_name', None),
        phone=getattr(org, 'phone', None),
        address=getattr(org, 'address', None),
        industry=getattr(org, 'industry', None),
        is_active=not getattr(org, 'is_emergency_suspended', False),  # Derived from is_emergency_suspended
        is_suspended=getattr(org, 'is_emergency_suspended', False),
        suspended_reason=getattr(org, 'emergency_suspension_reason', None),
        suspended_at=getattr(org, 'emergency_suspended_at', None),
        tier=sku.tier.value if sku else None,
        user_count=user_count,
        entity_count=entity_count,
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


@router.put("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: UUID,
    update_data: TenantUpdate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_platform_admin),
):
    """
    Update tenant details.
    Platform admin only.
    """
    result = await db.execute(
        select(Organization).where(Organization.id == tenant_id)
    )
    org = result.scalar_one_or_none()
    
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    
    # Update fields
    update_dict = update_data.dict(exclude_unset=True)
    for key, value in update_dict.items():
        if hasattr(org, key):
            setattr(org, key, value)
    
    org.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(org)
    
    # Return updated tenant
    return await get_tenant(tenant_id, db, current_user)


@router.post("/{tenant_id}/suspend")
async def suspend_tenant(
    tenant_id: UUID,
    suspend_data: TenantSuspend,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Suspend a tenant.
    Super Admin only.
    """
    result = await db.execute(
        select(Organization).where(Organization.id == tenant_id)
    )
    org = result.scalar_one_or_none()
    
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    
    # Set emergency suspension
    org.is_emergency_suspended = True
    org.emergency_suspension_reason = suspend_data.reason
    org.emergency_suspended_at = datetime.utcnow()
    org.emergency_suspended_by_id = str(current_user.id)
    
    org.updated_at = datetime.utcnow()
    
    await db.commit()
    
    # TODO: Send notification emails if suspend_data.notify_users
    
    return {
        "message": f"Tenant '{org.name}' has been suspended",
        "tenant_id": str(tenant_id),
        "reason": suspend_data.reason,
    }


@router.post("/{tenant_id}/activate")
async def activate_tenant(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Reactivate a suspended tenant.
    Super Admin only.
    """
    result = await db.execute(
        select(Organization).where(Organization.id == tenant_id)
    )
    org = result.scalar_one_or_none()
    
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    
    # Clear emergency suspension
    org.is_emergency_suspended = False
    org.emergency_suspension_reason = None
    org.emergency_suspended_at = None
    org.emergency_suspended_by_id = None
    
    org.updated_at = datetime.utcnow()
    
    await db.commit()
    
    return {
        "message": f"Tenant '{org.name}' has been reactivated",
        "tenant_id": str(tenant_id),
    }


@router.delete("/{tenant_id}")
async def delete_tenant(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Delete a tenant (soft delete).
    Super Admin only. Use with extreme caution.
    """
    result = await db.execute(
        select(Organization).where(Organization.id == tenant_id)
    )
    org = result.scalar_one_or_none()
    
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    
    # Soft delete - use emergency suspension mechanism
    org.is_emergency_suspended = True
    org.emergency_suspension_reason = "Deleted by Super Admin"
    org.emergency_suspended_at = datetime.utcnow()
    org.emergency_suspended_by_id = str(current_user.id)
    
    await db.commit()
    
    return {
        "message": f"Tenant '{org.name}' has been deleted",
        "tenant_id": str(tenant_id),
    }
