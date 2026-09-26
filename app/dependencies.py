"""
Tekvwa Pro Audit - FastAPI Dependencies

Shared dependencies for authentication, database sessions, and RBAC.

This module provides dependency injection for:
1. Database sessions
2. Current user authentication
3. Role-based access control for platform staff
4. Permission-based access control for organization users
5. Feature gating based on SKU tier
"""

import logging
import uuid
from uuid import UUID
from typing import List, Optional, Union, Dict, Any

from fastapi import Depends, HTTPException, status, Request

logger = logging.getLogger(__name__)
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_async_session
from app.models.user import User, UserRole, UserEntityAccess, PlatformRole
from app.models.organization import Organization
from app.models.sku import Feature, SKUTier, UsageMetricType
from app.utils.security import verify_access_token
from app.utils.permissions import (
    PlatformPermission,
    OrganizationPermission,
    has_platform_permission,
    has_organization_permission,
)


# HTTP Bearer token security
security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_async_session),
) -> User:
    """
    Get the current authenticated user from JWT token.
    
    Token can be provided via:
    1. Authorization: Bearer <token> header
    2. access_token cookie
    
    Raises:
        HTTPException: If token is invalid or user not found
    """
    token = None
    
    # Try Bearer header first
    if credentials:
        token = credentials.credentials
    else:
        # Fallback to cookie
        token = request.cookies.get("access_token")
        if token and token.startswith("Bearer "):
            token = token[7:]
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = verify_access_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user from database
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID in token",
        )
    
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.organization),
            selectinload(User.entity_access).selectinload(UserEntityAccess.entity)
        )
        .where(User.id == user_uuid)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current user and verify they are active."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )
    return current_user


async def get_current_verified_user(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Get current user and verify email is verified."""
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified",
        )
    return current_user


async def get_current_entity_id(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
) -> uuid.UUID:
    """
    Get the current entity ID from cookie or user's first accessible entity.
    
    For API endpoints, retrieves entity_id from:
    1. Cookie (if set by UI entity selection)
    2. User's first accessible entity (fallback)
    
    Args:
        request: FastAPI request object (for cookie access)
        current_user: Authenticated user
        db: Database session
        
    Returns:
        uuid.UUID of the current entity
        
    Raises:
        HTTPException: 400 if no entity selected or accessible
    """
    from app.models.entity import BusinessEntity
    
    # Try to get from cookie first
    entity_id_str = request.cookies.get("entity_id")
    if entity_id_str:
        try:
            entity_id = uuid.UUID(entity_id_str)
            # Verify user has access to this entity
            has_access = any(
                access.entity_id == entity_id 
                for access in current_user.entity_access
            )
            if has_access:
                return entity_id
        except ValueError:
            pass
    
    # Fallback: Get user's first accessible entity
    if current_user.entity_access:
        return current_user.entity_access[0].entity_id
    
    # For platform staff, get first entity from their organization
    if current_user.is_platform_staff and current_user.organization_id:
        result = await db.execute(
            select(BusinessEntity)
            .where(BusinessEntity.organization_id == current_user.organization_id)
            .limit(1)
        )
        entity = result.scalar_one_or_none()
        if entity:
            return entity.id
    
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="No entity selected. Please select a business entity first.",
    )


async def verify_entity_access(
    entity_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> None:
    """
    Verify user has access to the specified business entity.
    
    Args:
        entity_id: UUID of the business entity
        user: Current authenticated user
        db: Database session
        
    Raises:
        HTTPException: 404 if entity not found, 403 if access denied
    """
    from app.models.entity import BusinessEntity
    
    result = await db.execute(
        select(BusinessEntity).where(BusinessEntity.id == entity_id)
    )
    entity = result.scalar_one_or_none()
    
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business entity not found",
        )
    
    has_access = any(
        access.entity_id == entity_id 
        for access in user.entity_access
    )
    
    if not has_access and entity.organization_id != user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this business entity",
        )


async def require_entity_access(
    entity_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
) -> "BusinessEntity":
    """
    Centralized entity-access-check dependency (Finding 18, docs/IMPLEMENTATION_ROADMAP.md Phase 2
    Section 2.1). Use `Depends(require_entity_access)` in place of a raw `entity_id: uuid.UUID` path
    parameter on any entity-scoped route -- this makes the access check mechanically checkable (a
    route with a raw `entity_id` param and no `require_entity_access` dependency is, by definition,
    unfixed) instead of relying on each call site hand-rolling its own check correctly.

    Delegates to `EntityService.get_entity_by_id`, the one pattern in this codebase the audit found
    already correct (`transactions.py::list_transactions`), rather than reimplementing the access
    logic here a third time -- `verify_entity_access` above is a second, looser variant (grants
    access on shared organization_id alone, without checking the user's own UserEntityAccess grants
    unless the FIRST check already failed) that predates this fix; do not use it for new routes.

    Returns the resolved BusinessEntity so route handlers that need it don't have to look it up
    again.
    """
    from app.services.entity_service import EntityService

    entity = await EntityService(db).get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    return entity


async def require_group_access(
    group_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
) -> "EntityGroup":
    """
    Centralized cross-tenant access check for consolidation entity groups, the group_id-keyed
    counterpart to `require_entity_access` above.

    Discovered while migrating `app/routers/consolidation.py` for Finding 18: `EntityGroup` lookups
    throughout that file (`ConsolidationService.get_entity_group`) filter by `group_id` alone, with no
    `organization_id` check at all -- unlike the `entity_id` pattern this same phase already covers,
    this gap was not counted in the original audit's per-file endpoint tally for this file, and is
    fixed here as a same-root-cause extension of Finding 18 rather than a separate finding. See
    docs/REMEDIATION_LOG.md's Phase 2 entry for `consolidation.py` for the full discovery writeup.

    Use `Depends(require_group_access)` in place of a raw `group_id: uuid.UUID` path parameter on any
    group-scoped consolidation route.
    """
    from app.models.advanced_accounting import EntityGroup

    result = await db.execute(
        select(EntityGroup).where(
            EntityGroup.id == group_id,
            EntityGroup.organization_id == current_user.organization_id,
        )
    )
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity group not found or access denied",
        )
    return group


def require_role(allowed_roles: list[UserRole]):
    """
    Dependency factory for organization role-based access control.
    
    Usage:
        @router.get("/admin-only")
        async def admin_endpoint(user: User = Depends(require_role([UserRole.OWNER, UserRole.ADMIN]))):
            ...
    """
    async def role_checker(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        # Platform staff bypass org role checks (they have their own permissions)
        if current_user.is_platform_staff:
            return current_user
            
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {[r.value for r in allowed_roles]}",
            )
        return current_user
    
    return role_checker


# ===========================================
# PLATFORM STAFF RBAC DEPENDENCIES
# ===========================================

def require_platform_staff():
    """
    Require the user to be a platform staff member.
    
    Usage:
        @router.get("/staff-only")
        async def staff_endpoint(user: User = Depends(require_platform_staff())):
            ...
    """
    async def staff_checker(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        if not current_user.is_platform_staff:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Platform staff only.",
            )
        return current_user
    
    return staff_checker


def require_platform_role(allowed_roles: List[PlatformRole]):
    """
    Require specific platform roles.
    
    Usage:
        @router.get("/super-admin-only")
        async def super_admin_endpoint(
            user: User = Depends(require_platform_role([PlatformRole.SUPER_ADMIN]))
        ):
            ...
    """
    async def role_checker(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        if not current_user.is_platform_staff:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Platform staff only.",
            )
        
        if current_user.platform_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required platform roles: {[r.value for r in allowed_roles]}",
            )
        return current_user
    
    return role_checker


def require_platform_permission(required_permissions: List[PlatformPermission]):
    """
    Require specific platform permissions.
    
    Usage:
        @router.get("/verify-orgs")
        async def verify_org_endpoint(
            user: User = Depends(require_platform_permission([PlatformPermission.VERIFY_ORGANIZATIONS]))
        ):
            ...
    """
    async def permission_checker(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        if not current_user.is_platform_staff or not current_user.platform_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Platform staff only.",
            )
        
        missing_permissions = []
        for perm in required_permissions:
            if not has_platform_permission(current_user.platform_role, perm):
                missing_permissions.append(perm.value)
        
        if missing_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Missing permissions: {missing_permissions}",
            )
        return current_user
    
    return permission_checker


def require_super_admin():
    """Shortcut for requiring Super Admin role."""
    return require_platform_role([PlatformRole.SUPER_ADMIN])


def require_admin_or_above():
    """Shortcut for requiring Admin or Super Admin role."""
    return require_platform_role([PlatformRole.SUPER_ADMIN, PlatformRole.ADMIN])


async def get_current_platform_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """
    Get current user and verify they are a platform admin (ADMIN or SUPER_ADMIN).
    
    This is a direct dependency (not a factory) for simpler usage in routers.
    
    Usage:
        @router.get("/admin/endpoint")
        async def admin_endpoint(user: User = Depends(get_current_platform_admin)):
            ...
    
    Raises:
        HTTPException: If user is not a platform admin
    """
    if not current_user.is_platform_staff:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin access required",
        )
    
    if current_user.platform_role not in [PlatformRole.SUPER_ADMIN, PlatformRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient platform permissions. Required: Admin or Super Admin",
        )
    
    return current_user


# ===========================================
# ORGANIZATION USER RBAC DEPENDENCIES
# ===========================================

def require_organization_permission(required_permissions: List[OrganizationPermission]):
    """
    Require specific organization permissions.
    
    Usage:
        @router.get("/transactions")
        async def get_transactions(
            user: User = Depends(require_organization_permission([OrganizationPermission.VIEW_ALL_TRANSACTIONS]))
        ):
            ...
    """
    async def permission_checker(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        # Platform staff have elevated access - check their platform permissions instead
        if current_user.is_platform_staff:
            # Platform staff can view user data
            if current_user.platform_role and has_platform_permission(
                current_user.platform_role, 
                PlatformPermission.VIEW_USER_DATA
            ):
                return current_user
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Platform staff: insufficient permissions for organization data",
            )
        
        if not current_user.role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No organization role assigned",
            )
        
        missing_permissions = []
        for perm in required_permissions:
            if not has_organization_permission(current_user.role, perm):
                missing_permissions.append(perm.value)
        
        if missing_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Missing permissions: {missing_permissions}",
            )
        return current_user
    
    return permission_checker


def require_organization_owner():
    """Require the user to be an organization owner."""
    return require_role([UserRole.OWNER])


def require_organization_admin():
    """Require the user to be an organization admin or owner."""
    return require_role([UserRole.OWNER, UserRole.ADMIN])


def require_financial_access():
    """Require access to financial data (accountant level or above)."""
    return require_role([UserRole.OWNER, UserRole.ADMIN, UserRole.ACCOUNTANT, UserRole.AUDITOR])


# ===========================================
# COMBINED ACCESS DEPENDENCIES
# ===========================================

def require_any_admin():
    """
    Require either platform admin or organization admin.
    Useful for endpoints that both platform staff and org admins can access.
    """
    async def admin_checker(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        # Check platform admin
        if current_user.is_platform_staff:
            if current_user.platform_role in [PlatformRole.SUPER_ADMIN, PlatformRole.ADMIN]:
                return current_user
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Admin access required.",
            )
        
        # Check organization admin
        if current_user.role in [UserRole.OWNER, UserRole.ADMIN]:
            return current_user
        
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin access required.",
        )
    
    return admin_checker


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_async_session),
) -> Optional[User]:
    """
    Get current user if authenticated, otherwise return None.
    Useful for endpoints that work differently for authenticated vs anonymous users.
    """
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None


# ===========================================
# SKU FEATURE GATING DEPENDENCIES
# ===========================================

def require_feature(required_features: List[Feature]):
    """
    Dependency factory for SKU feature-based access control.
    
    Checks if the user's organization has access to the required features
    based on their SKU tier and any custom overrides.
    
    Usage:
        @router.get("/payroll")
        async def payroll_endpoint(
            user: User = Depends(require_feature([Feature.PAYROLL]))
        ):
            ...
    
    Args:
        required_features: List of features that must be available
    
    Returns:
        Dependency that validates feature access and returns the user
    """
    async def feature_checker(
        request: Request,
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_async_session),
    ) -> User:
        from app.services.feature_flags import FeatureFlagService, FeatureAccessDenied
        
        # Platform staff bypass feature checks
        if current_user.is_platform_staff:
            return current_user
        
        if not current_user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is not associated with an organization",
            )
        
        feature_service = FeatureFlagService(db)
        
        # Build request context for logging
        request_context: Dict[str, Any] = {
            "endpoint": str(request.url.path),
            "ip_address": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
        }
        
        # Check each required feature
        for feature in required_features:
            try:
                await feature_service.require_feature(
                    organization_id=current_user.organization_id,
                    feature=feature,
                    user_id=current_user.id,
                    request_context=request_context,
                )
            except FeatureAccessDenied as e:
                # Get upgrade recommendation
                recommendation = await feature_service.get_upgrade_recommendation(
                    organization_id=current_user.organization_id,
                    denied_feature=feature,
                )
                
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": "feature_not_available",
                        "message": str(e),
                        "feature": feature.value,
                        "upgrade_recommendation": recommendation,
                    },
                )
        
        return current_user
    
    return feature_checker


def require_within_usage_limit(metric: UsageMetricType):
    """
    Dependency factory for checking usage limits before allowing an action.
    
    Usage:
        @router.post("/transactions")
        async def create_transaction(
            user: User = Depends(require_within_usage_limit(UsageMetricType.TRANSACTIONS))
        ):
            ...
    
    Args:
        metric: The usage metric to check limits for
    
    Returns:
        Dependency that validates usage is within limits
    """
    async def limit_checker(
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_async_session),
    ) -> User:
        from app.services.feature_flags import FeatureFlagService, UsageLimitExceeded
        from app.services.metering_service import MeteringService
        
        # Platform staff bypass limit checks
        if current_user.is_platform_staff:
            return current_user
        
        if not current_user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is not associated with an organization",
            )
        
        feature_service = FeatureFlagService(db)
        metering_service = MeteringService(db)
        
        # Get current usage for the metric
        current_usage = await metering_service.get_current_usage(
            organization_id=current_user.organization_id,
            metric=metric,
        )
        
        try:
            await feature_service.require_within_limit(
                organization_id=current_user.organization_id,
                metric=metric,
                current_usage=current_usage,
            )
        except UsageLimitExceeded as e:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "usage_limit_exceeded",
                    "message": str(e),
                    "metric": metric.value,
                    "current_usage": current_usage,
                    "limit": e.limit,
                    "upgrade_message": "Contact sales to increase your limits or upgrade your plan.",
                },
            )
        
        return current_user
    
    return limit_checker


async def get_tenant_sku_context(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
) -> Dict[str, Any]:
    """
    Get the SKU context for the current user's organization.
    
    Returns a dictionary with:
    - tier: Current SKU tier
    - intelligence_addon: Intelligence add-on level
    - enabled_features: Set of enabled feature names
    - limits: Dictionary of usage limits
    
    Useful for UI rendering to show/hide features.
    """
    from app.services.feature_flags import FeatureFlagService
    
    if current_user.is_platform_staff:
        # Platform staff see all features
        return {
            "tier": "platform_staff",
            "intelligence_addon": "full",
            "enabled_features": [f.value for f in Feature],
            "limits": {},
            "is_platform_staff": True,
        }
    
    if not current_user.organization_id:
        return {
            "tier": None,
            "intelligence_addon": None,
            "enabled_features": [],
            "limits": {},
            "error": "No organization associated",
        }
    
    feature_service = FeatureFlagService(db)
    
    tier = await feature_service.get_effective_tier(current_user.organization_id)
    intel_addon = await feature_service.get_intelligence_addon(current_user.organization_id)
    enabled_features = await feature_service.get_enabled_features(current_user.organization_id)
    
    # Get limits for key metrics
    limits = {}
    for metric in UsageMetricType:
        limit = await feature_service.get_limit(current_user.organization_id, metric)
        limits[metric.value] = limit
    
    return {
        "tier": tier.value,
        "intelligence_addon": intel_addon.value,
        "enabled_features": [f.value for f in enabled_features],
        "limits": limits,
        "is_platform_staff": False,
    }


# Shortcut dependencies for common feature requirements
def require_payroll():
    """Require payroll feature (Professional tier or above)."""
    return require_feature([Feature.PAYROLL])


def require_bank_reconciliation():
    """Require bank reconciliation feature (Professional tier or above)."""
    return require_feature([Feature.BANK_RECONCILIATION])


def require_advanced_reports():
    """Require advanced reports feature (Professional tier or above)."""
    return require_feature([Feature.ADVANCED_REPORTS])


def require_worm_vault():
    """Require WORM vault feature (Enterprise tier only)."""
    return require_feature([Feature.WORM_VAULT])


def require_multi_entity():
    """Require multi-entity feature (Enterprise tier only)."""
    return require_feature([Feature.MULTI_ENTITY])


def require_intercompany():
    """Require intercompany feature (Enterprise tier only)."""
    return require_feature([Feature.INTERCOMPANY])


def require_ml_features():
    """Require ML features (Intelligence add-on required)."""
    return require_feature([Feature.ML_ANOMALY_DETECTION])


def require_benfords_law():
    """Require Benford's Law analysis (Intelligence add-on required)."""
    return require_feature([Feature.BENFORDS_LAW])


def require_ocr():
    """Require OCR feature (Intelligence add-on required)."""
    return require_feature([Feature.OCR_EXTRACTION])


def require_api_access():
    """Require API access (Enterprise tier for full access)."""
    return require_feature([Feature.FULL_API_ACCESS])


# =============================================================================
# ADDITIONAL SHORTCUT DEPENDENCIES (SKU Tier Enforcement)
# =============================================================================

def require_fixed_assets():
    """Require Fixed Assets feature (Professional tier)."""
    return require_feature([Feature.FIXED_ASSETS])


def require_expense_claims():
    """Require Expense Claims feature (Professional tier)."""
    return require_feature([Feature.EXPENSE_CLAIMS])


def require_nrs_compliance():
    """Require NRS Compliance feature (Professional tier)."""
    return require_feature([Feature.NRS_COMPLIANCE])


def require_bank_reconciliation():
    """Require Bank Reconciliation feature (Professional tier)."""
    return require_feature([Feature.BANK_RECONCILIATION])


def require_advanced_reports():
    """Require Advanced Reports feature (Professional tier)."""
    return require_feature([Feature.ADVANCED_REPORTS])


def require_forensic_audit():
    """Require Forensic Audit features (Intelligence add-on required)."""
    return require_feature([Feature.BENFORDS_LAW, Feature.ZSCORE_ANALYSIS])


def require_advanced_audit():
    """Require Advanced Audit features (Enterprise tier)."""
    return require_feature([Feature.WORM_VAULT, Feature.ATTESTATION])


def require_segregation_of_duties():
    """Require Segregation of Duties feature (Enterprise tier)."""
    return require_feature([Feature.SEGREGATION_OF_DUTIES])


def require_predictive_forecasting():
    """Require Predictive Forecasting feature (Intelligence add-on)."""
    return require_feature([Feature.PREDICTIVE_FORECASTING])


def require_fraud_detection():
    """Require Fraud Detection feature (Intelligence add-on)."""
    return require_feature([Feature.FRAUD_DETECTION])


# =============================================================================
# METERING HELPER FUNCTIONS
# =============================================================================

async def record_usage_event(
    db: AsyncSession,
    organization_id: UUID,
    metric_type: "UsageMetricType",
    quantity: int = 1,
    entity_id: Optional[UUID] = None,
    user_id: Optional[UUID] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
) -> None:
    """
    Helper function to record a usage event.
    
    This is a convenience wrapper around MeteringService for use in routers.
    Silently handles errors to not disrupt the main request flow.
    
    Args:
        db: Database session
        organization_id: Organization UUID
        metric_type: Type of usage metric (TRANSACTIONS, INVOICES, etc.)
        quantity: Amount to record (default 1)
        entity_id: Optional business entity ID
        user_id: Optional user ID
        resource_type: Type of resource (e.g., "customer", "vendor")
        resource_id: ID of the specific resource
    """
    try:
        from app.services.metering_service import MeteringService
        
        metering_service = MeteringService(db)
        await metering_service.record_event(
            organization_id=organization_id,
            metric_type=metric_type,
            quantity=quantity,
            entity_id=entity_id,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
    except Exception as e:
        # Log but don't fail the request if metering fails
        logger.warning(f"Failed to record usage event: {e}")


async def record_entity_creation(
    db: AsyncSession,
    organization_id: UUID,
    entity_id: UUID,
    user_id: Optional[UUID] = None,
) -> None:
    """Record entity creation and update entity count."""
    try:
        from app.services.metering_service import MeteringService, UsageMetricType
        
        metering_service = MeteringService(db)
        await metering_service.record_event(
            organization_id=organization_id,
            metric_type=UsageMetricType.ENTITIES,
            quantity=1,
            entity_id=entity_id,
            user_id=user_id,
            resource_type="entity",
            resource_id=str(entity_id),
        )
    except Exception as e:
        logger.warning(f"Failed to record entity creation: {e}")