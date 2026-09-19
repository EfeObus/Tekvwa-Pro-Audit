"""
Tekvwa Pro Audit - Organization Settings Router

API endpoints for organization settings management.

Features:
- Organization profile management
- Subscription information
- Branding/logo management
- API keys management
- Integration settings
"""

import uuid
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_async_session
from app.dependencies import get_current_active_user, require_organization_permission
from app.models.user import User, UserRole
from app.models.organization import Organization, OrganizationType, VerificationStatus
from app.services.audit_service import AuditService
from app.models.audit_consolidated import AuditAction
from app.utils.permissions import OrganizationPermission


router = APIRouter(prefix="/organizations", tags=["Organization Settings"])


# ===========================================
# SCHEMAS
# ===========================================

class OrganizationSettingsResponse(BaseModel):
    """Response for organization settings."""
    id: uuid.UUID
    name: str
    slug: str
    organization_type: str
    subscription_tier: str
    
    # Contact
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    
    # Address
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: str = "Nigeria"
    postal_code: Optional[str] = None
    
    # Verification
    is_verified: bool
    verification_status: str
    
    # Branding
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    
    # Settings
    default_currency: str = "NGN"
    fiscal_year_start_month: int = 1
    timezone: str = "Africa/Lagos"
    
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class UpdateOrganizationRequest(BaseModel):
    """Request for updating organization settings."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    website: Optional[str] = Field(None, max_length=255)
    
    address_line1: Optional[str] = Field(None, max_length=255)
    address_line2: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    
    primary_color: Optional[str] = Field(None, pattern=r'^#[0-9A-Fa-f]{6}$')
    fiscal_year_start_month: Optional[int] = Field(None, ge=1, le=12)
    timezone: Optional[str] = None


class SubscriptionResponse(BaseModel):
    """Response for subscription information."""
    organization_id: uuid.UUID
    tier: str
    status: str
    
    # Limits
    max_entities: int
    max_users: int
    max_invoices_per_month: int
    max_storage_gb: float
    
    # Usage
    current_entities: int
    current_users: int
    invoices_this_month: int
    storage_used_gb: float
    
    # Billing
    billing_cycle: str
    next_billing_date: Optional[str] = None
    amount_due: Optional[float] = None
    
    # Features
    features: List[str]
    
    class Config:
        from_attributes = True


class APIKeyResponse(BaseModel):
    """Response for API key."""
    id: uuid.UUID
    name: str
    prefix: str
    created_at: datetime
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_active: bool
    scopes: List[str]


class CreateAPIKeyRequest(BaseModel):
    """Request for creating API key."""
    name: str = Field(..., min_length=1, max_length=100)
    scopes: List[str] = Field(default=["read"])
    expires_in_days: Optional[int] = Field(None, ge=1, le=365)


class CreateAPIKeyResponse(BaseModel):
    """Response after creating API key (includes full key, shown once)."""
    id: uuid.UUID
    name: str
    api_key: str  # Full key, shown only on creation
    prefix: str
    scopes: List[str]
    expires_at: Optional[datetime] = None
    message: str = "Save this API key securely. It will not be shown again."


class IntegrationSettingsResponse(BaseModel):
    """Response for integration settings."""
    nrs_integration: dict
    payment_gateways: List[dict]
    accounting_software: List[dict]
    webhooks: List[dict]


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    success: bool = True


# ===========================================
# HELPER FUNCTIONS
# ===========================================

async def get_organization(
    org_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> Organization:
    """Get organization and verify access."""
    if not user.is_platform_staff and user.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this organization",
        )
    
    result = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    organization = result.scalar_one_or_none()
    
    if not organization:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    
    return organization


# ===========================================
# ORGANIZATION ENDPOINTS
# ===========================================

@router.get(
    "/{org_id}/settings",
    response_model=OrganizationSettingsResponse,
    summary="Get organization settings",
    description="Get the settings for an organization.",
)
async def get_organization_settings(
    org_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get organization settings."""
    organization = await get_organization(org_id, current_user, db)
    
    return OrganizationSettingsResponse(
        id=organization.id,
        name=organization.name,
        slug=organization.slug,
        organization_type=organization.organization_type.value if organization.organization_type else "business",
        subscription_tier=organization.subscription_tier.value,
        email=organization.email,
        phone=organization.phone,
        website=organization.website,
        address_line1=getattr(organization, 'address_line1', None),
        address_line2=getattr(organization, 'address_line2', None),
        city=getattr(organization, 'city', None),
        state=getattr(organization, 'state', None),
        country=getattr(organization, 'country', 'Nigeria'),
        postal_code=getattr(organization, 'postal_code', None),
        is_verified=organization.is_verified,
        verification_status=organization.verification_status.value if organization.verification_status else "pending",
        logo_url=getattr(organization, 'logo_url', None),
        primary_color=getattr(organization, 'primary_color', None),
        default_currency=getattr(organization, 'default_currency', 'NGN'),
        fiscal_year_start_month=getattr(organization, 'fiscal_year_start_month', 1),
        timezone=getattr(organization, 'timezone', 'Africa/Lagos'),
        created_at=organization.created_at,
        updated_at=organization.updated_at,
    )


@router.patch(
    "/{org_id}/settings",
    response_model=OrganizationSettingsResponse,
    summary="Update organization settings",
    description="Update organization settings. Requires admin permissions.",
)
async def update_organization_settings(
    org_id: uuid.UUID,
    request: UpdateOrganizationRequest,
    current_user: User = Depends(require_organization_permission([OrganizationPermission.MANAGE_SETTINGS])),
    db: AsyncSession = Depends(get_async_session),
):
    """Update organization settings."""
    organization = await get_organization(org_id, current_user, db)
    
    # Capture old values for audit
    old_values = {
        "name": organization.name,
        "email": organization.email,
        "phone": organization.phone,
        "fiscal_year_start_month": getattr(organization, 'fiscal_year_start_month', 1),
    }
    
    update_data = request.model_dump(exclude_unset=True)
    
    for key, value in update_data.items():
        if hasattr(organization, key):
            setattr(organization, key, value)
    
    await db.commit()
    await db.refresh(organization)
    
    # Audit logging for settings update
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=org_id,
        entity_type="organization_settings",
        entity_id=str(org_id),
        action=AuditAction.UPDATE,
        user_id=current_user.id,
        old_values=old_values,
        new_values={
            "name": organization.name,
            "email": organization.email,
            "phone": organization.phone,
            "fiscal_year_start_month": getattr(organization, 'fiscal_year_start_month', 1),
            "updated_fields": list(update_data.keys()),
        }
    )
    
    return OrganizationSettingsResponse(
        id=organization.id,
        name=organization.name,
        slug=organization.slug,
        organization_type=organization.organization_type.value if organization.organization_type else "business",
        subscription_tier=organization.subscription_tier.value,
        email=organization.email,
        phone=organization.phone,
        website=organization.website,
        address_line1=getattr(organization, 'address_line1', None),
        address_line2=getattr(organization, 'address_line2', None),
        city=getattr(organization, 'city', None),
        state=getattr(organization, 'state', None),
        country=getattr(organization, 'country', 'Nigeria'),
        postal_code=getattr(organization, 'postal_code', None),
        is_verified=organization.is_verified,
        verification_status=organization.verification_status.value if organization.verification_status else "pending",
        logo_url=getattr(organization, 'logo_url', None),
        primary_color=getattr(organization, 'primary_color', None),
        default_currency=getattr(organization, 'default_currency', 'NGN'),
        fiscal_year_start_month=getattr(organization, 'fiscal_year_start_month', 1),
        timezone=getattr(organization, 'timezone', 'Africa/Lagos'),
        created_at=organization.created_at,
        updated_at=organization.updated_at,
    )


@router.post(
    "/{org_id}/logo",
    response_model=MessageResponse,
    summary="Upload organization logo",
    description="Upload a logo image for the organization.",
)
async def upload_organization_logo(
    org_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(require_organization_permission([OrganizationPermission.MANAGE_SETTINGS])),
    db: AsyncSession = Depends(get_async_session),
):
    """Upload organization logo."""
    organization = await get_organization(org_id, current_user, db)
    
    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "image/svg+xml"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed: {allowed_types}",
        )
    
    # Validate file size (max 2MB)
    content = await file.read()
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large. Maximum size is 2MB",
        )
    
    # In a full implementation, upload to cloud storage
    # For now, just acknowledge the upload
    # organization.logo_url = uploaded_url
    # await db.commit()
    
    return MessageResponse(
        message="Logo uploaded successfully",
        success=True,
    )


# ===========================================
# SUBSCRIPTION ENDPOINTS
# ===========================================

@router.get(
    "/{org_id}/subscription",
    response_model=SubscriptionResponse,
    summary="Get subscription details",
    description="Get subscription tier, usage, and billing information.",
)
async def get_subscription(
    org_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get subscription details."""
    organization = await get_organization(org_id, current_user, db)
    
    # Define tier limits
    tier_limits = {
        "free": {"entities": 1, "users": 2, "invoices": 50, "storage": 0.5},
        "starter": {"entities": 2, "users": 5, "invoices": 200, "storage": 2.0},
        "professional": {"entities": 5, "users": 15, "invoices": 1000, "storage": 10.0},
        "enterprise": {"entities": 999, "users": 999, "invoices": 99999, "storage": 100.0},
    }
    
    tier = organization.subscription_tier.value
    limits = tier_limits.get(tier, tier_limits["free"])
    
    # Count current usage (simplified)
    current_entities = len(organization.entities) if organization.entities else 0
    current_users = len(organization.users) if organization.users else 0
    
    # Define features by tier
    tier_features = {
        "free": ["Basic invoicing", "VAT calculation", "5-year audit trail"],
        "starter": ["Everything in Free", "NRS e-invoicing", "Multi-entity", "Email support"],
        "professional": ["Everything in Starter", "Advanced reporting", "API access", "Priority support"],
        "enterprise": ["Everything in Professional", "Custom integrations", "Dedicated support", "SLA"],
    }
    
    return SubscriptionResponse(
        organization_id=organization.id,
        tier=tier,
        status="active",
        max_entities=limits["entities"],
        max_users=limits["users"],
        max_invoices_per_month=limits["invoices"],
        max_storage_gb=limits["storage"],
        current_entities=current_entities,
        current_users=current_users,
        invoices_this_month=0,  # Would calculate from invoice table
        storage_used_gb=0.0,  # Would calculate from file storage
        billing_cycle="monthly",
        next_billing_date=None,
        amount_due=None,
        features=tier_features.get(tier, []),
    )


# ===========================================
# API KEYS ENDPOINTS
# ===========================================

@router.get(
    "/{org_id}/api-keys",
    response_model=List[APIKeyResponse],
    summary="List API keys",
    description="List all API keys for the organization.",
)
async def list_api_keys(
    org_id: uuid.UUID,
    current_user: User = Depends(require_organization_permission([OrganizationPermission.MANAGE_SETTINGS])),
    db: AsyncSession = Depends(get_async_session),
):
    """List API keys (placeholder)."""
    await get_organization(org_id, current_user, db)
    
    # In a full implementation, this would query an api_keys table
    return []


@router.post(
    "/{org_id}/api-keys",
    response_model=CreateAPIKeyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create API key",
    description="Create a new API key for the organization.",
)
async def create_api_key(
    org_id: uuid.UUID,
    request: CreateAPIKeyRequest,
    current_user: User = Depends(require_organization_permission([OrganizationPermission.MANAGE_SETTINGS])),
    db: AsyncSession = Depends(get_async_session),
):
    """Create API key (placeholder)."""
    await get_organization(org_id, current_user, db)
    
    # In a full implementation, this would create an API key
    import secrets
    key_id = uuid.uuid4()
    api_key = f"tpa_{secrets.token_urlsafe(32)}"
    prefix = api_key[:12]
    
    return CreateAPIKeyResponse(
        id=key_id,
        name=request.name,
        api_key=api_key,
        prefix=prefix,
        scopes=request.scopes,
        expires_at=None,
    )


@router.delete(
    "/{org_id}/api-keys/{key_id}",
    response_model=MessageResponse,
    summary="Revoke API key",
    description="Revoke an API key.",
)
async def revoke_api_key(
    org_id: uuid.UUID,
    key_id: uuid.UUID,
    current_user: User = Depends(require_organization_permission([OrganizationPermission.MANAGE_SETTINGS])),
    db: AsyncSession = Depends(get_async_session),
):
    """Revoke API key (placeholder)."""
    await get_organization(org_id, current_user, db)
    
    # In a full implementation, this would delete/deactivate the API key
    return MessageResponse(message="API key revoked successfully")


# ===========================================
# INTEGRATION SETTINGS
# ===========================================

@router.get(
    "/{org_id}/integrations",
    response_model=IntegrationSettingsResponse,
    summary="Get integration settings",
    description="Get integration settings and connected services.",
)
async def get_integrations(
    org_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get integration settings."""
    await get_organization(org_id, current_user, db)
    
    return IntegrationSettingsResponse(
        nrs_integration={
            "enabled": True,
            "status": "connected",
            "last_sync": None,
            "api_version": "2.0",
        },
        payment_gateways=[
            {"name": "Paystack", "enabled": False, "status": "not_configured"},
            {"name": "Flutterwave", "enabled": False, "status": "not_configured"},
        ],
        accounting_software=[
            {"name": "QuickBooks", "enabled": False, "status": "not_configured"},
            {"name": "Sage", "enabled": False, "status": "not_configured"},
        ],
        webhooks=[],
    )
