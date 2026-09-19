"""
Tekvwa Pro Audit - Admin SKU Management Router

Platform staff endpoints for managing tenant SKUs.
Only accessible to SUPER_ADMIN and ADMIN platform roles.

Nigerian Naira (₦) Pricing:
- Core: ₦25,000 - ₦75,000/month
- Professional: ₦150,000 - ₦400,000/month
- Enterprise: ₦1,000,000 - ₦5,000,000+/month
- Intelligence Add-on: ₦250,000 - ₦1,000,000/month
"""

import uuid
from datetime import date, datetime, timedelta
from typing import Optional, List
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, HTTPException, status, Body, Path
from sqlalchemy import select, and_, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, Field

from app.database import get_db
from app.dependencies import get_current_user, get_current_platform_admin
from app.models.user import User
from app.models.organization import Organization
from app.models.sku import (
    SKUTier,
    IntelligenceAddon,
    Feature,
    TenantSKU,
    UsageRecord,
    UsageEvent,
    FeatureAccessLog,
    TIER_LIMITS,
    INTELLIGENCE_LIMITS,
)
from app.services.feature_flags import FeatureFlagService
from app.services.metering_service import MeteringService, UsageMetricType
from app.services.usage_alert_service import UsageAlertService, AlertChannel
from app.config.sku_config import (
    TIER_PRICING,
    INTELLIGENCE_PRICING,
    get_tier_display_name,
    get_tier_description,
    TIER_LIMITS_CONFIG,
)


router = APIRouter(prefix="/admin/sku", tags=["Admin - SKU Management"])


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class TenantSKUCreate(BaseModel):
    """Create a new SKU assignment for an organization."""
    organization_id: uuid.UUID = Field(..., description="Organization to assign SKU to")
    tier: SKUTier = Field(SKUTier.CORE, description="SKU tier level")
    intelligence_addon: Optional[IntelligenceAddon] = Field(None, description="Intelligence add-on level")
    billing_cycle: str = Field("monthly", description="monthly or annual")
    custom_price_naira: Optional[int] = Field(None, ge=0, description="Custom price in Naira (for enterprise deals)")
    notes: Optional[str] = Field(None, max_length=500, description="Admin notes")


class TenantSKUUpdate(BaseModel):
    """Update an existing SKU assignment."""
    tier: Optional[SKUTier] = Field(None, description="New tier level")
    intelligence_addon: Optional[IntelligenceAddon] = Field(None, description="New intelligence add-on")
    is_active: Optional[bool] = Field(None, description="Active status")
    billing_cycle: Optional[str] = Field(None, description="Billing cycle")
    custom_price_naira: Optional[int] = Field(None, ge=0, description="Custom price override")
    notes: Optional[str] = Field(None, max_length=500, description="Admin notes")
    # Custom limits override
    custom_user_limit: Optional[int] = Field(None, ge=1)
    custom_entity_limit: Optional[int] = Field(None, ge=1)
    custom_transaction_limit: Optional[int] = Field(None, ge=-1, description="-1 for unlimited")


class UsageLimitOverride(BaseModel):
    """Override default tier limits for a specific tenant."""
    metric: UsageMetricType = Field(..., description="Metric to override")
    new_limit: int = Field(..., ge=-1, description="New limit (-1 for unlimited)")
    reason: str = Field(..., min_length=10, max_length=500, description="Reason for override")


class TenantSKUResponse(BaseModel):
    """Response model for tenant SKU details."""
    id: uuid.UUID
    organization_id: uuid.UUID
    organization_name: str
    tier: SKUTier
    tier_display_name: str
    intelligence_addon: Optional[IntelligenceAddon]
    is_active: bool
    billing_cycle: str
    base_price_naira: int
    custom_price_naira: Optional[int]
    effective_price_naira: int
    trial_ends_at: Optional[datetime]
    is_trial: bool
    current_period_start: date
    current_period_end: date
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class UsageSummaryResponse(BaseModel):
    """Response model for usage summary."""
    organization_id: uuid.UUID
    organization_name: str
    tier: SKUTier
    period_start: date
    period_end: date
    metrics: dict


class SKUPricingResponse(BaseModel):
    """Response model for SKU pricing information."""
    tier: SKUTier
    display_name: str
    description: str
    base_price_monthly_naira: int
    base_price_annual_naira: int
    min_users: int
    max_users: int
    limits: dict


# =============================================================================
# PRICING INFO ENDPOINTS
# =============================================================================

@router.get("/pricing", response_model=List[SKUPricingResponse])
async def get_sku_pricing(
    current_user: User = Depends(get_current_platform_admin),
):
    """
    Get all SKU pricing tiers with limits.
    
    Platform admin only. Returns Naira pricing.
    """
    pricing_list = []
    
    for tier in [SKUTier.CORE, SKUTier.PROFESSIONAL, SKUTier.ENTERPRISE]:
        pricing = TIER_PRICING.get(tier)
        limits = TIER_LIMITS_CONFIG.get(tier, {})
        
        pricing_list.append(SKUPricingResponse(
            tier=tier,
            display_name=get_tier_display_name(tier),
            description=get_tier_description(tier),
            base_price_monthly_naira=int(pricing.monthly_min) if pricing else 0,
            base_price_annual_naira=int(pricing.annual_min) if pricing else 0,
            min_users=pricing.base_users_included if pricing else 1,
            max_users=pricing.base_users_included * 2 if pricing else 3,  # Estimate max
            limits=limits,
        ))
    
    return pricing_list


@router.get("/pricing/intelligence")
async def get_intelligence_addon_pricing(
    current_user: User = Depends(get_current_platform_admin),
):
    """
    Get Intelligence add-on pricing tiers.
    
    Platform admin only. Returns Naira pricing.
    """
    return {
        "addons": [
            {
                "level": addon.value,
                "display_name": addon.name.replace("_", " ").title(),
                "price_monthly_min_naira": int(INTELLIGENCE_PRICING.get(addon).monthly_min) 
                    if INTELLIGENCE_PRICING.get(addon) else 0,
                "price_monthly_max_naira": int(INTELLIGENCE_PRICING.get(addon).monthly_max) 
                    if INTELLIGENCE_PRICING.get(addon) else 0,
                "limits": INTELLIGENCE_LIMITS.get(addon, {}),
            }
            for addon in IntelligenceAddon
        ],
        "note": "Intelligence add-on requires minimum Professional tier",
    }


# =============================================================================
# TENANT SKU MANAGEMENT
# =============================================================================

@router.get("/tenants")
async def list_tenant_skus(
    tier: Optional[SKUTier] = Query(None, description="Filter by tier"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    has_addon: Optional[bool] = Query(None, description="Filter by intelligence add-on"),
    search: Optional[str] = Query(None, max_length=100, description="Search by org name"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_platform_admin),
):
    """
    List all tenant SKU assignments with filtering.
    
    Platform admin only.
    """
    query = (
        select(TenantSKU)
        .options(selectinload(TenantSKU.organization))
        .order_by(TenantSKU.created_at.desc())
    )
    
    if tier:
        query = query.where(TenantSKU.tier == tier)
    if is_active is not None:
        query = query.where(TenantSKU.is_active == is_active)
    if has_addon is not None:
        if has_addon:
            query = query.where(TenantSKU.intelligence_addon != None)
        else:
            query = query.where(TenantSKU.intelligence_addon == None)
    
    if search:
        query = query.join(Organization).where(
            Organization.name.ilike(f"%{search}%")
        )
    
    # Get total count
    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar() or 0
    
    # Get paginated results
    result = await db.execute(query.offset(skip).limit(limit))
    tenant_skus = result.scalars().all()
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [
            {
                "id": str(sku.id),
                "organization_id": str(sku.organization_id),
                "organization_name": sku.organization.name if sku.organization else "Unknown",
                "tier": sku.tier.value,
                "tier_display": get_tier_display_name(sku.tier),
                "intelligence_addon": sku.intelligence_addon.value if sku.intelligence_addon else None,
                "is_active": sku.is_active,
                "billing_cycle": sku.billing_cycle,
                "is_trial": sku.trial_ends_at and sku.trial_ends_at > datetime.utcnow() if sku.trial_ends_at else False,
                "trial_ends_at": sku.trial_ends_at.isoformat() if sku.trial_ends_at else None,
                "created_at": sku.created_at.isoformat() if sku.created_at else None,
            }
            for sku in tenant_skus
        ],
    }


@router.get("/tenants/{organization_id}")
async def get_tenant_sku(
    organization_id: uuid.UUID = Path(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_platform_admin),
):
    """
    Get detailed SKU information for a specific tenant.
    
    Platform admin only.
    """
    result = await db.execute(
        select(TenantSKU)
        .options(selectinload(TenantSKU.organization))
        .where(TenantSKU.organization_id == organization_id)
    )
    tenant_sku = result.scalar_one_or_none()
    
    if not tenant_sku:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No SKU assignment found for this organization",
        )
    
    # Get pricing info
    tier_pricing = TIER_PRICING.get(tenant_sku.tier)
    tier_limits = TIER_LIMITS.get(tenant_sku.tier, {})
    
    # Get usage data
    metering_service = MeteringService(db)
    usage_summary = await metering_service.get_usage_summary(organization_id)
    
    # Calculate effective price
    if tenant_sku.custom_price_naira:
        effective_price = tenant_sku.custom_price_naira
    elif tenant_sku.billing_cycle == "annual" and tier_pricing:
        effective_price = int(tier_pricing.annual_min) // 12  # Monthly equivalent
    elif tier_pricing:
        effective_price = int(tier_pricing.monthly_min)
    else:
        effective_price = 0
    
    # Add intelligence addon price
    if tenant_sku.intelligence_addon:
        addon_pricing = INTELLIGENCE_PRICING.get(tenant_sku.intelligence_addon)
        if addon_pricing:
            effective_price += int(addon_pricing.monthly_min)
    
    return {
        "id": str(tenant_sku.id),
        "organization_id": str(tenant_sku.organization_id),
        "organization_name": tenant_sku.organization.name if tenant_sku.organization else "Unknown",
        "tier": tenant_sku.tier.value,
        "tier_display": get_tier_display_name(tenant_sku.tier),
        "tier_description": get_tier_description(tenant_sku.tier),
        "intelligence_addon": tenant_sku.intelligence_addon.value if tenant_sku.intelligence_addon else None,
        "is_active": tenant_sku.is_active,
        "billing_cycle": tenant_sku.billing_cycle,
        "pricing": {
            "base_price_naira": int(tier_pricing.monthly_min) if tier_pricing else 0,
            "custom_price_naira": tenant_sku.custom_price_naira,
            "effective_price_naira": effective_price,
            "currency": "NGN",
        },
        "limits": tier_limits,
        "custom_limits": {
            "users": tenant_sku.custom_user_limit,
            "entities": tenant_sku.custom_entity_limit,
            "transactions": tenant_sku.custom_transaction_limit,
        },
        "trial": {
            "is_trial": tenant_sku.trial_ends_at and tenant_sku.trial_ends_at > datetime.utcnow() if tenant_sku.trial_ends_at else False,
            "trial_ends_at": tenant_sku.trial_ends_at.isoformat() if tenant_sku.trial_ends_at else None,
            "days_remaining": (tenant_sku.trial_ends_at - datetime.utcnow()).days 
                if tenant_sku.trial_ends_at and tenant_sku.trial_ends_at > datetime.utcnow() else 0,
        },
        "billing_period": {
            "start": tenant_sku.current_period_start.isoformat() if tenant_sku.current_period_start else None,
            "end": tenant_sku.current_period_end.isoformat() if tenant_sku.current_period_end else None,
        },
        "usage": usage_summary,
        "features_enabled": [f.value for f in Feature if True],  # Would need feature service call
        "created_at": tenant_sku.created_at.isoformat() if tenant_sku.created_at else None,
        "updated_at": tenant_sku.updated_at.isoformat() if tenant_sku.updated_at else None,
        "notes": tenant_sku.notes,
    }


@router.post("/tenants")
async def create_tenant_sku(
    data: TenantSKUCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_platform_admin),
):
    """
    Create a new SKU assignment for an organization.
    
    Platform admin only.
    """
    # Check organization exists
    org_result = await db.execute(
        select(Organization).where(Organization.id == data.organization_id)
    )
    organization = org_result.scalar_one_or_none()
    
    if not organization:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    
    # Check if SKU already exists
    existing = await db.execute(
        select(TenantSKU).where(TenantSKU.organization_id == data.organization_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SKU assignment already exists for this organization. Use PUT to update.",
        )
    
    # Validate intelligence addon requirements
    if data.intelligence_addon and data.tier == SKUTier.CORE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Intelligence add-on requires minimum Professional tier",
        )
    
    # Set billing period
    today = date.today()
    if data.billing_cycle == "annual":
        period_end = date(today.year + 1, today.month, today.day)
    else:
        next_month = today.month + 1 if today.month < 12 else 1
        next_year = today.year if today.month < 12 else today.year + 1
        period_end = date(next_year, next_month, today.day)
    
    tenant_sku = TenantSKU(
        organization_id=data.organization_id,
        tier=data.tier,
        intelligence_addon=data.intelligence_addon,
        is_active=True,
        billing_cycle=data.billing_cycle,
        custom_price_naira=data.custom_price_naira,
        current_period_start=today,
        current_period_end=period_end,
        notes=data.notes,
    )
    
    db.add(tenant_sku)
    await db.commit()
    await db.refresh(tenant_sku)
    
    return {
        "message": "SKU assignment created successfully",
        "id": str(tenant_sku.id),
        "organization_id": str(data.organization_id),
        "organization_name": organization.name,
        "tier": data.tier.value,
        "billing_cycle": data.billing_cycle,
        "period_start": today.isoformat(),
        "period_end": period_end.isoformat(),
    }


@router.put("/tenants/{organization_id}")
async def update_tenant_sku(
    organization_id: uuid.UUID = Path(..., description="Organization ID"),
    data: TenantSKUUpdate = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_platform_admin),
):
    """
    Update an existing SKU assignment.
    
    Platform admin only. Supports tier upgrade/downgrade, add-on changes, and custom limits.
    """
    result = await db.execute(
        select(TenantSKU)
        .options(selectinload(TenantSKU.organization))
        .where(TenantSKU.organization_id == organization_id)
    )
    tenant_sku = result.scalar_one_or_none()
    
    if not tenant_sku:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No SKU assignment found for this organization",
        )
    
    changes = []
    
    # Track tier change for logging
    old_tier = tenant_sku.tier
    
    if data.tier is not None and data.tier != tenant_sku.tier:
        # Validate intelligence addon compatibility on downgrade
        if data.tier == SKUTier.CORE and tenant_sku.intelligence_addon:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot downgrade to Core tier with Intelligence add-on. Remove add-on first.",
            )
        tenant_sku.tier = data.tier
        changes.append(f"tier: {old_tier.value} → {data.tier.value}")
    
    if data.intelligence_addon is not None:
        # Validate tier requirements
        effective_tier = data.tier if data.tier else tenant_sku.tier
        if effective_tier == SKUTier.CORE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Intelligence add-on requires minimum Professional tier",
            )
        old_addon = tenant_sku.intelligence_addon
        tenant_sku.intelligence_addon = data.intelligence_addon
        changes.append(f"intelligence_addon: {old_addon.value if old_addon else 'none'} → {data.intelligence_addon.value}")
    
    if data.is_active is not None:
        tenant_sku.is_active = data.is_active
        changes.append(f"is_active: {data.is_active}")
    
    if data.billing_cycle is not None:
        tenant_sku.billing_cycle = data.billing_cycle
        changes.append(f"billing_cycle: {data.billing_cycle}")
    
    if data.custom_price_naira is not None:
        tenant_sku.custom_price_naira = data.custom_price_naira
        changes.append(f"custom_price_naira: ₦{data.custom_price_naira:,}")
    
    if data.notes is not None:
        tenant_sku.notes = data.notes
    
    # Custom limit overrides
    if data.custom_user_limit is not None:
        tenant_sku.custom_user_limit = data.custom_user_limit
        changes.append(f"custom_user_limit: {data.custom_user_limit}")
    
    if data.custom_entity_limit is not None:
        tenant_sku.custom_entity_limit = data.custom_entity_limit
        changes.append(f"custom_entity_limit: {data.custom_entity_limit}")
    
    if data.custom_transaction_limit is not None:
        tenant_sku.custom_transaction_limit = data.custom_transaction_limit
        changes.append(f"custom_transaction_limit: {data.custom_transaction_limit}")
    
    tenant_sku.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(tenant_sku)
    
    return {
        "message": "SKU assignment updated successfully",
        "organization_id": str(organization_id),
        "organization_name": tenant_sku.organization.name if tenant_sku.organization else "Unknown",
        "changes": changes,
        "current_tier": tenant_sku.tier.value,
        "current_addon": tenant_sku.intelligence_addon.value if tenant_sku.intelligence_addon else None,
    }


@router.delete("/tenants/{organization_id}")
async def delete_tenant_sku(
    organization_id: uuid.UUID = Path(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_platform_admin),
):
    """
    Delete/deactivate a SKU assignment.
    
    Platform admin only. Soft-deletes by setting is_active=False.
    """
    result = await db.execute(
        select(TenantSKU).where(TenantSKU.organization_id == organization_id)
    )
    tenant_sku = result.scalar_one_or_none()
    
    if not tenant_sku:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No SKU assignment found for this organization",
        )
    
    tenant_sku.is_active = False
    tenant_sku.updated_at = datetime.utcnow()
    tenant_sku.notes = (tenant_sku.notes or "") + f"\nDeactivated by {current_user.email} on {datetime.utcnow().isoformat()}"
    
    await db.commit()
    
    return {
        "message": "SKU assignment deactivated",
        "organization_id": str(organization_id),
        "note": "Organization will be downgraded to free tier limits",
    }


# =============================================================================
# TRIAL MANAGEMENT
# =============================================================================

@router.post("/tenants/{organization_id}/trial")
async def start_trial(
    organization_id: uuid.UUID = Path(..., description="Organization ID"),
    tier: SKUTier = Query(SKUTier.PROFESSIONAL, description="Trial tier level"),
    days: int = Query(14, ge=7, le=30, description="Trial duration in days"),
    include_intelligence: bool = Query(False, description="Include Intelligence add-on in trial"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_platform_admin),
):
    """
    Start a trial for an organization.
    
    Platform admin only.
    """
    result = await db.execute(
        select(TenantSKU)
        .options(selectinload(TenantSKU.organization))
        .where(TenantSKU.organization_id == organization_id)
    )
    tenant_sku = result.scalar_one_or_none()
    
    if tenant_sku and tenant_sku.trial_ends_at and tenant_sku.trial_ends_at > datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Organization already has an active trial ending {tenant_sku.trial_ends_at.isoformat()}",
        )
    
    trial_end = datetime.utcnow() + timedelta(days=days)
    
    if tenant_sku:
        # Update existing
        tenant_sku.tier = tier
        tenant_sku.trial_ends_at = trial_end
        if include_intelligence and tier != SKUTier.CORE:
            tenant_sku.intelligence_addon = IntelligenceAddon.STANDARD
        tenant_sku.updated_at = datetime.utcnow()
    else:
        # Create new
        org_result = await db.execute(
            select(Organization).where(Organization.id == organization_id)
        )
        organization = org_result.scalar_one_or_none()
        
        if not organization:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )
        
        today = date.today()
        tenant_sku = TenantSKU(
            organization_id=organization_id,
            tier=tier,
            intelligence_addon=IntelligenceAddon.STANDARD if include_intelligence and tier != SKUTier.CORE else None,
            is_active=True,
            billing_cycle="monthly",
            trial_ends_at=trial_end,
            current_period_start=today,
            current_period_end=today + timedelta(days=days),
        )
        db.add(tenant_sku)
    
    await db.commit()
    
    return {
        "message": "Trial started successfully",
        "organization_id": str(organization_id),
        "trial_tier": tier.value,
        "includes_intelligence": include_intelligence and tier != SKUTier.CORE,
        "trial_ends_at": trial_end.isoformat(),
        "days_remaining": days,
    }


@router.delete("/tenants/{organization_id}/trial")
async def end_trial(
    organization_id: uuid.UUID = Path(..., description="Organization ID"),
    convert_to_paid: bool = Query(False, description="Convert to paid subscription"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_platform_admin),
):
    """
    End a trial early.
    
    Platform admin only.
    """
    result = await db.execute(
        select(TenantSKU).where(TenantSKU.organization_id == organization_id)
    )
    tenant_sku = result.scalar_one_or_none()
    
    if not tenant_sku:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No SKU assignment found",
        )
    
    if not tenant_sku.trial_ends_at or tenant_sku.trial_ends_at <= datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization does not have an active trial",
        )
    
    if convert_to_paid:
        # Keep current tier, clear trial
        tenant_sku.trial_ends_at = None
        message = f"Trial converted to paid {tenant_sku.tier.value} subscription"
    else:
        # Downgrade to Core
        tenant_sku.tier = SKUTier.CORE
        tenant_sku.intelligence_addon = None
        tenant_sku.trial_ends_at = None
        message = "Trial ended, downgraded to Core tier"
    
    tenant_sku.updated_at = datetime.utcnow()
    await db.commit()
    
    return {
        "message": message,
        "organization_id": str(organization_id),
        "current_tier": tenant_sku.tier.value,
    }


# =============================================================================
# USAGE & ANALYTICS
# =============================================================================

@router.get("/tenants/{organization_id}/usage")
async def get_tenant_usage(
    organization_id: uuid.UUID = Path(..., description="Organization ID"),
    months: int = Query(3, ge=1, le=12, description="Number of months of history"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_platform_admin),
):
    """
    Get detailed usage data for a tenant.
    
    Platform admin only.
    """
    metering_service = MeteringService(db)
    
    # Get current usage
    current_usage = await metering_service.get_usage_summary(organization_id)
    
    # Get historical usage
    history = await metering_service.get_usage_history(organization_id, months=months)
    
    return {
        "organization_id": str(organization_id),
        "current": current_usage,
        "history": [
            {
                "period_start": record.period_start.isoformat(),
                "period_end": record.period_end.isoformat(),
                "transactions": record.transactions_count,
                "users": record.users_count,
                "entities": record.entities_count,
                "invoices": record.invoices_count,
                "api_calls": record.api_calls_count,
                "storage_mb": float(record.storage_used_mb),
                "ml_inferences": record.ml_inferences_count,
                "ocr_pages": record.ocr_pages_count,
                "employees": record.employees_count,
                "is_billed": record.is_billed,
            }
            for record in history
        ],
    }


@router.get("/analytics/tier-distribution")
async def get_tier_distribution(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_platform_admin),
):
    """
    Get distribution of tenants across tiers.
    
    Platform admin only.
    """
    result = await db.execute(
        select(TenantSKU.tier, func.count(TenantSKU.id))
        .where(TenantSKU.is_active == True)
        .group_by(TenantSKU.tier)
    )
    
    distribution = {tier.value: 0 for tier in SKUTier}
    for tier, count in result.all():
        distribution[tier.value] = count
    
    # Get addon counts
    addon_result = await db.execute(
        select(TenantSKU.intelligence_addon, func.count(TenantSKU.id))
        .where(TenantSKU.is_active == True)
        .where(TenantSKU.intelligence_addon != None)
        .group_by(TenantSKU.intelligence_addon)
    )
    
    addons = {}
    for addon, count in addon_result.all():
        if addon:
            addons[addon.value] = count
    
    # Get trial counts
    trial_result = await db.execute(
        select(func.count(TenantSKU.id))
        .where(TenantSKU.is_active == True)
        .where(TenantSKU.trial_ends_at > datetime.utcnow())
    )
    trials = trial_result.scalar() or 0
    
    return {
        "tier_distribution": distribution,
        "total_active": sum(distribution.values()),
        "intelligence_addons": addons,
        "total_addons": sum(addons.values()),
        "active_trials": trials,
    }


@router.get("/analytics/revenue")
async def get_revenue_analytics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_platform_admin),
):
    """
    Get revenue analytics by tier.
    
    Platform admin only. All values in Nigerian Naira (₦).
    """
    result = await db.execute(
        select(TenantSKU)
        .where(TenantSKU.is_active == True)
        .where(TenantSKU.trial_ends_at == None)  # Exclude trials
    )
    tenant_skus = result.scalars().all()
    
    revenue_by_tier = {tier.value: 0 for tier in SKUTier}
    addon_revenue = 0
    
    for sku in tenant_skus:
        # Calculate base tier revenue
        pricing = TIER_PRICING.get(sku.tier)
        if sku.custom_price_naira:
            monthly_revenue = sku.custom_price_naira
        elif sku.billing_cycle == "annual" and pricing:
            monthly_revenue = int(pricing.annual_min) // 12
        elif pricing:
            monthly_revenue = int(pricing.monthly_min)
        else:
            monthly_revenue = 0
        
        revenue_by_tier[sku.tier.value] += monthly_revenue
        
        # Calculate addon revenue
        if sku.intelligence_addon:
            addon_pricing = INTELLIGENCE_PRICING.get(sku.intelligence_addon)
            if addon_pricing:
                addon_revenue += int(addon_pricing.monthly_min)
    
    total_mrr = sum(revenue_by_tier.values()) + addon_revenue
    
    return {
        "currency": "NGN",
        "monthly_recurring_revenue": {
            "total": total_mrr,
            "formatted": f"₦{total_mrr:,.0f}",
            "by_tier": {
                tier: {
                    "amount": amount,
                    "formatted": f"₦{amount:,.0f}",
                }
                for tier, amount in revenue_by_tier.items()
            },
            "intelligence_addons": {
                "amount": addon_revenue,
                "formatted": f"₦{addon_revenue:,.0f}",
            },
        },
        "annual_run_rate": {
            "amount": total_mrr * 12,
            "formatted": f"₦{total_mrr * 12:,.0f}",
        },
    }


# =============================================================================
# USAGE ALERTS ENDPOINTS
# =============================================================================

@router.get(
    "/organizations/{organization_id}/usage-alerts",
    summary="Get usage alerts for organization",
)
async def get_organization_usage_alerts(
    organization_id: uuid.UUID = Path(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_platform_admin),
):
    """
    Get all active usage alerts for an organization.
    
    Returns alerts for metrics that are approaching or exceeding limits.
    """
    service = UsageAlertService(db)
    alerts = await service.get_active_alerts(organization_id)
    
    return {
        "organization_id": str(organization_id),
        "alerts": [alert.to_dict() for alert in alerts],
        "count": len(alerts),
    }


@router.get(
    "/organizations/{organization_id}/usage-summary",
    summary="Get comprehensive usage summary",
)
async def get_organization_usage_summary(
    organization_id: uuid.UUID = Path(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_platform_admin),
):
    """
    Get comprehensive usage summary for an organization.
    
    Shows current usage vs limits for all metrics with status indicators.
    """
    service = UsageAlertService(db)
    return await service.get_usage_summary(organization_id)


@router.post(
    "/organizations/{organization_id}/usage-alerts/notify",
    summary="Send usage alert notifications",
)
async def send_usage_alert_notifications(
    organization_id: uuid.UUID = Path(..., description="Organization ID"),
    channels: List[str] = Query(["in_app"], description="Notification channels"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_platform_admin),
):
    """
    Manually trigger usage alert notifications for an organization.
    
    Channels: email, websocket, in_app, webhook
    """
    service = UsageAlertService(db)
    alerts = await service.get_active_alerts(organization_id)
    
    if not alerts:
        return {
            "message": "No active alerts to notify",
            "alerts_count": 0,
        }
    
    # Convert channel strings to enum
    channel_enums = []
    for ch in channels:
        try:
            channel_enums.append(AlertChannel(ch))
        except ValueError:
            pass
    
    if not channel_enums:
        channel_enums = [AlertChannel.IN_APP]
    
    results = await service.notify_alerts(alerts, channel_enums)
    
    return {
        "alerts_count": len(alerts),
        "notification_results": results,
    }


@router.post(
    "/organizations/{organization_id}/usage-alerts/{metric}/acknowledge",
    summary="Acknowledge a usage alert",
)
async def acknowledge_usage_alert(
    organization_id: uuid.UUID = Path(..., description="Organization ID"),
    metric: UsageMetricType = Path(..., description="Metric type"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_platform_admin),
):
    """
    Acknowledge a usage alert to stop repeated notifications.
    
    Alert will not re-trigger until usage drops below threshold
    and rises again.
    """
    service = UsageAlertService(db)
    await service.acknowledge_alert(organization_id, metric)
    
    return {
        "message": f"Alert for {metric.value} acknowledged",
        "organization_id": str(organization_id),
    }
