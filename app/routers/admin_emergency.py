"""
Tekvwa Pro Audit - Admin Emergency Controls Router

Platform emergency control endpoints for Super Admins only.
These are CRITICAL security features that should be used with extreme caution.

Features:
- Platform-wide read-only mode
- Feature kill switches
- Emergency tenant suspension
- Maintenance mode
- Login lockdown

All actions require mandatory reasons and are fully audited.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import require_super_admin
from app.models.user import User
from app.models.emergency_control import EmergencyActionType, FeatureKey
from app.services.emergency_control_service import EmergencyControlService


router = APIRouter(
    prefix="/admin/emergency",
    tags=["Admin - Emergency Controls"],
)


# ========= SCHEMAS =========

class EnableReadOnlyModeRequest(BaseModel):
    """Request to enable platform read-only mode."""
    reason: str = Field(
        ..., 
        min_length=10, 
        max_length=1000,
        description="Mandatory reason for enabling read-only mode"
    )
    message: Optional[str] = Field(
        None,
        max_length=500,
        description="Optional message to display to users"
    )


class DisableReadOnlyModeRequest(BaseModel):
    """Request to disable platform read-only mode."""
    reason: str = Field(
        ...,
        min_length=10,
        max_length=1000,
        description="Reason for disabling read-only mode"
    )


class FeatureKillSwitchRequest(BaseModel):
    """Request to toggle a feature kill switch."""
    reason: str = Field(
        ...,
        min_length=10,
        max_length=1000,
        description="Mandatory reason for the action"
    )


class EmergencyTenantSuspendRequest(BaseModel):
    """Request to emergency suspend a tenant."""
    reason: str = Field(
        ...,
        min_length=10,
        max_length=1000,
        description="Mandatory reason for emergency suspension"
    )
    notify_users: bool = Field(
        default=True,
        description="Whether to notify tenant users"
    )


class LiftEmergencySuspensionRequest(BaseModel):
    """Request to lift emergency suspension."""
    reason: str = Field(
        ...,
        min_length=10,
        max_length=1000,
        description="Reason for lifting suspension"
    )


class EnableMaintenanceModeRequest(BaseModel):
    """Request to enable maintenance mode."""
    reason: str = Field(
        ...,
        min_length=10,
        max_length=1000,
        description="Reason for maintenance"
    )
    message: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="Message to display to users"
    )
    expected_end: Optional[datetime] = Field(
        None,
        description="Expected end time of maintenance"
    )


class DisableMaintenanceModeRequest(BaseModel):
    """Request to disable maintenance mode."""
    reason: str = Field(
        ...,
        min_length=10,
        max_length=1000,
        description="Reason for ending maintenance"
    )


class EnableLoginLockdownRequest(BaseModel):
    """Request to enable login lockdown."""
    reason: str = Field(
        ...,
        min_length=10,
        max_length=1000,
        description="Mandatory reason for enabling login lockdown"
    )
    allow_admin_login: bool = Field(
        default=True,
        description="Whether to allow admin logins during lockdown"
    )


class DisableLoginLockdownRequest(BaseModel):
    """Request to disable login lockdown."""
    reason: str = Field(
        ...,
        min_length=10,
        max_length=1000,
        description="Reason for disabling login lockdown"
    )


class PlatformStatusResponse(BaseModel):
    """Current platform status response."""
    is_read_only: bool
    is_maintenance_mode: bool
    is_login_locked: bool
    disabled_features: List[str]
    maintenance_message: Optional[str] = None
    maintenance_expected_end: Optional[datetime] = None
    last_changed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class EmergencyControlResponse(BaseModel):
    """Emergency control action response."""
    id: UUID
    action_type: str
    target_type: str
    target_id: Optional[str] = None
    reason: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    is_active: bool
    affected_count: Optional[int] = None
    initiated_by_id: UUID
    ended_by_id: Optional[UUID] = None
    end_reason: Optional[str] = None
    
    class Config:
        from_attributes = True


class EmergencyStatsResponse(BaseModel):
    """Emergency control statistics."""
    platform_status: PlatformStatusResponse
    active_controls_count: int
    controls_by_type: dict
    suspended_tenants_count: int


class AvailableFeaturesResponse(BaseModel):
    """List of available feature keys for kill switches."""
    features: List[dict]


# ========= ENDPOINTS =========

@router.get("/status", response_model=PlatformStatusResponse)
async def get_platform_status(
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get current platform status.
    
    Returns the current state of all emergency controls including:
    - Read-only mode status
    - Maintenance mode status
    - Login lockdown status
    - Disabled features list
    """
    service = EmergencyControlService(db)
    status = await service.get_platform_status()
    
    return PlatformStatusResponse(
        is_read_only=status.is_read_only,
        is_maintenance_mode=status.is_maintenance_mode,
        is_login_locked=status.is_login_locked,
        disabled_features=status.disabled_features or [],
        maintenance_message=status.maintenance_message,
        maintenance_expected_end=status.maintenance_expected_end,
        last_changed_at=status.last_changed_at,
    )


@router.get("/stats", response_model=EmergencyStatsResponse)
async def get_emergency_stats(
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_async_session),
):
    """Get emergency control statistics."""
    service = EmergencyControlService(db)
    stats = await service.get_emergency_stats()
    
    return EmergencyStatsResponse(
        platform_status=PlatformStatusResponse(**stats["platform_status"]),
        active_controls_count=stats["active_controls_count"],
        controls_by_type=stats["controls_by_type"],
        suspended_tenants_count=stats["suspended_tenants_count"],
    )


@router.get("/features", response_model=AvailableFeaturesResponse)
async def get_available_features(
    current_user: User = Depends(require_super_admin),
):
    """
    Get list of available features for kill switches.
    
    Returns all platform features that can be disabled via kill switch.
    """
    features = [
        {
            "key": f.value,
            "name": f.value.replace("_", " ").title(),
            "description": _get_feature_description(f.value),
        }
        for f in FeatureKey
    ]
    
    return AvailableFeaturesResponse(features=features)


def _get_feature_description(feature_key: str) -> str:
    """Get description for a feature key."""
    descriptions = {
        "payments": "Payment processing and transactions",
        "invoicing": "Invoice creation and management",
        "payroll": "Payroll processing and salary payments",
        "bank_reconciliation": "Bank statement reconciliation",
        "expense_claims": "Expense claim submissions and approvals",
        "tax_filing": "Tax calculation and filing",
        "audit_reports": "Audit report generation",
        "user_registration": "New user registration",
        "api_access": "External API access",
        "exports": "Data export functionality",
        "file_uploads": "File upload capability",
        "integrations": "Third-party integrations",
        "ml_inference": "Machine learning predictions",
        "notifications": "Email and push notifications",
    }
    return descriptions.get(feature_key, "Platform feature")


# ========= READ-ONLY MODE =========

@router.post("/read-only-mode/enable", response_model=EmergencyControlResponse)
async def enable_read_only_mode(
    request: EnableReadOnlyModeRequest,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Enable platform-wide read-only mode.
    
    CRITICAL: This will block ALL write operations platform-wide.
    
    Use cases:
    - Emergency security incidents
    - Critical data migration
    - System maintenance requiring data freeze
    """
    service = EmergencyControlService(db)
    
    try:
        control, status = await service.enable_read_only_mode(
            admin_id=current_user.id,
            reason=request.reason,
            message=request.message,
        )
        
        return EmergencyControlResponse(
            id=control.id,
            action_type=control.action_type.value,
            target_type=control.target_type,
            target_id=control.target_id,
            reason=control.reason,
            started_at=control.started_at,
            is_active=control.is_active,
            initiated_by_id=control.initiated_by_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/read-only-mode/disable", response_model=EmergencyControlResponse)
async def disable_read_only_mode(
    request: DisableReadOnlyModeRequest,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Disable platform-wide read-only mode.
    
    This restores normal write operations.
    """
    service = EmergencyControlService(db)
    
    try:
        control, status = await service.disable_read_only_mode(
            admin_id=current_user.id,
            reason=request.reason,
        )
        
        if control:
            return EmergencyControlResponse(
                id=control.id,
                action_type=control.action_type.value,
                target_type=control.target_type,
                target_id=control.target_id,
                reason=control.reason,
                started_at=control.started_at,
                ended_at=control.ended_at,
                is_active=control.is_active,
                initiated_by_id=control.initiated_by_id,
                ended_by_id=control.ended_by_id,
                end_reason=control.end_reason,
            )
        
        raise HTTPException(status_code=404, detail="No active read-only control found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ========= FEATURE KILL SWITCHES =========

@router.post("/kill-switch/{feature_key}/disable", response_model=EmergencyControlResponse)
async def disable_feature(
    feature_key: str,
    request: FeatureKillSwitchRequest,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Disable a specific platform feature.
    
    CRITICAL: This will immediately disable the specified feature
    for ALL users across ALL tenants.
    
    Valid feature keys:
    - payments, invoicing, payroll, bank_reconciliation
    - expense_claims, tax_filing, audit_reports
    - user_registration, api_access, exports
    - file_uploads, integrations, ml_inference, notifications
    """
    service = EmergencyControlService(db)
    
    try:
        control, status = await service.disable_feature(
            admin_id=current_user.id,
            feature_key=feature_key,
            reason=request.reason,
        )
        
        return EmergencyControlResponse(
            id=control.id,
            action_type=control.action_type.value,
            target_type=control.target_type,
            target_id=control.target_id,
            reason=control.reason,
            started_at=control.started_at,
            is_active=control.is_active,
            initiated_by_id=control.initiated_by_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/kill-switch/{feature_key}/enable", response_model=EmergencyControlResponse)
async def enable_feature(
    feature_key: str,
    request: FeatureKillSwitchRequest,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Re-enable a disabled platform feature.
    
    This restores the feature for all users.
    """
    service = EmergencyControlService(db)
    
    try:
        control, status = await service.enable_feature(
            admin_id=current_user.id,
            feature_key=feature_key,
            reason=request.reason,
        )
        
        if control:
            return EmergencyControlResponse(
                id=control.id,
                action_type=control.action_type.value,
                target_type=control.target_type,
                target_id=control.target_id,
                reason=control.reason,
                started_at=control.started_at,
                ended_at=control.ended_at,
                is_active=control.is_active,
                initiated_by_id=control.initiated_by_id,
                ended_by_id=control.ended_by_id,
                end_reason=control.end_reason,
            )
        
        raise HTTPException(status_code=404, detail="No active kill switch found for this feature")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ========= EMERGENCY TENANT SUSPENSION =========

@router.post("/tenant/{tenant_id}/emergency-suspend", response_model=EmergencyControlResponse)
async def emergency_suspend_tenant(
    tenant_id: UUID,
    request: EmergencyTenantSuspendRequest,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Emergency suspend a tenant (organization).
    
    CRITICAL: This immediately blocks ALL access for the tenant's users.
    
    Use cases:
    - Suspected fraud or security breach
    - Severe compliance violations
    - Legal requirements (court orders, etc.)
    """
    service = EmergencyControlService(db)
    
    try:
        control, tenant = await service.emergency_suspend_tenant(
            admin_id=current_user.id,
            tenant_id=tenant_id,
            reason=request.reason,
            notify_users=request.notify_users,
        )
        
        return EmergencyControlResponse(
            id=control.id,
            action_type=control.action_type.value,
            target_type=control.target_type,
            target_id=control.target_id,
            reason=control.reason,
            started_at=control.started_at,
            is_active=control.is_active,
            affected_count=control.affected_count,
            initiated_by_id=control.initiated_by_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tenant/{tenant_id}/lift-suspension", response_model=EmergencyControlResponse)
async def lift_emergency_suspension(
    tenant_id: UUID,
    request: LiftEmergencySuspensionRequest,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Lift emergency suspension from a tenant.
    
    This restores access for all tenant users.
    """
    service = EmergencyControlService(db)
    
    try:
        control, tenant = await service.lift_emergency_suspension(
            admin_id=current_user.id,
            tenant_id=tenant_id,
            reason=request.reason,
        )
        
        if control:
            return EmergencyControlResponse(
                id=control.id,
                action_type=control.action_type.value,
                target_type=control.target_type,
                target_id=control.target_id,
                reason=control.reason,
                started_at=control.started_at,
                ended_at=control.ended_at,
                is_active=control.is_active,
                affected_count=control.affected_count,
                initiated_by_id=control.initiated_by_id,
                ended_by_id=control.ended_by_id,
                end_reason=control.end_reason,
            )
        
        raise HTTPException(status_code=404, detail="No active suspension found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tenant/suspended", response_model=List[dict])
async def get_suspended_tenants(
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_async_session),
):
    """Get all emergency suspended tenants."""
    service = EmergencyControlService(db)
    tenants = await service.get_emergency_suspended_tenants()
    
    return [
        {
            "id": str(tenant.id),
            "name": tenant.name,
            "suspended_at": tenant.emergency_suspended_at,
            "suspended_by_id": str(tenant.emergency_suspended_by_id) if tenant.emergency_suspended_by_id else None,
            "reason": tenant.emergency_suspension_reason,
        }
        for tenant in tenants
    ]


# ========= MAINTENANCE MODE =========

@router.post("/maintenance-mode/enable", response_model=EmergencyControlResponse)
async def enable_maintenance_mode(
    request: EnableMaintenanceModeRequest,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Enable platform maintenance mode.
    
    CRITICAL: This will block ALL non-admin users from accessing the platform.
    
    Only platform staff will be able to access the system.
    """
    service = EmergencyControlService(db)
    
    try:
        control, status = await service.enable_maintenance_mode(
            admin_id=current_user.id,
            reason=request.reason,
            message=request.message,
            expected_end=request.expected_end,
        )
        
        return EmergencyControlResponse(
            id=control.id,
            action_type=control.action_type.value,
            target_type=control.target_type,
            target_id=control.target_id,
            reason=control.reason,
            started_at=control.started_at,
            is_active=control.is_active,
            initiated_by_id=control.initiated_by_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/maintenance-mode/disable", response_model=EmergencyControlResponse)
async def disable_maintenance_mode(
    request: DisableMaintenanceModeRequest,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Disable platform maintenance mode.
    
    This restores access for all users.
    """
    service = EmergencyControlService(db)
    
    try:
        control, status = await service.disable_maintenance_mode(
            admin_id=current_user.id,
            reason=request.reason,
        )
        
        if control:
            return EmergencyControlResponse(
                id=control.id,
                action_type=control.action_type.value,
                target_type=control.target_type,
                target_id=control.target_id,
                reason=control.reason,
                started_at=control.started_at,
                ended_at=control.ended_at,
                is_active=control.is_active,
                initiated_by_id=control.initiated_by_id,
                ended_by_id=control.ended_by_id,
                end_reason=control.end_reason,
            )
        
        raise HTTPException(status_code=404, detail="No active maintenance mode found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ========= LOGIN LOCKDOWN =========

@router.post("/login-lockdown/enable", response_model=EmergencyControlResponse)
async def enable_login_lockdown(
    request: EnableLoginLockdownRequest,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Enable platform-wide login lockdown.
    
    CRITICAL: This will prevent ALL non-admin users from logging in.
    
    Use cases:
    - Active security breach
    - Suspected credential compromise
    - Emergency system maintenance
    """
    service = EmergencyControlService(db)
    
    try:
        control, status = await service.enable_login_lockdown(
            admin_id=current_user.id,
            reason=request.reason,
            allow_admin_login=request.allow_admin_login,
        )
        
        return EmergencyControlResponse(
            id=control.id,
            action_type=control.action_type.value,
            target_type=control.target_type,
            target_id=control.target_id,
            reason=control.reason,
            started_at=control.started_at,
            is_active=control.is_active,
            initiated_by_id=control.initiated_by_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login-lockdown/disable", response_model=EmergencyControlResponse)
async def disable_login_lockdown(
    request: DisableLoginLockdownRequest,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Disable platform-wide login lockdown.
    
    This restores normal login capability for all users.
    """
    service = EmergencyControlService(db)
    
    try:
        control, status = await service.disable_login_lockdown(
            admin_id=current_user.id,
            reason=request.reason,
        )
        
        if control:
            return EmergencyControlResponse(
                id=control.id,
                action_type=control.action_type.value,
                target_type=control.target_type,
                target_id=control.target_id,
                reason=control.reason,
                started_at=control.started_at,
                ended_at=control.ended_at,
                is_active=control.is_active,
                initiated_by_id=control.initiated_by_id,
                ended_by_id=control.ended_by_id,
                end_reason=control.end_reason,
            )
        
        raise HTTPException(status_code=404, detail="No active login lockdown found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ========= HISTORY =========

@router.get("/history", response_model=List[EmergencyControlResponse])
async def get_emergency_control_history(
    action_type: Optional[str] = Query(None, description="Filter by action type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get emergency control action history.
    
    Returns all emergency control actions with optional filtering.
    """
    service = EmergencyControlService(db)
    
    # Parse action type if provided
    parsed_action_type = None
    if action_type:
        try:
            parsed_action_type = EmergencyActionType(action_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid action type. Valid types: {[t.value for t in EmergencyActionType]}"
            )
    
    controls = await service.get_emergency_control_history(
        action_type=parsed_action_type,
        limit=limit,
        offset=offset,
    )
    
    return [
        EmergencyControlResponse(
            id=c.id,
            action_type=c.action_type.value,
            target_type=c.target_type,
            target_id=c.target_id,
            reason=c.reason,
            started_at=c.started_at,
            ended_at=c.ended_at,
            is_active=c.is_active,
            affected_count=c.affected_count,
            initiated_by_id=c.initiated_by_id,
            ended_by_id=c.ended_by_id,
            end_reason=c.end_reason,
        )
        for c in controls
    ]


@router.get("/active", response_model=List[EmergencyControlResponse])
async def get_active_emergency_controls(
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_async_session),
):
    """Get all currently active emergency controls."""
    service = EmergencyControlService(db)
    controls = await service.get_active_emergency_controls()
    
    return [
        EmergencyControlResponse(
            id=c.id,
            action_type=c.action_type.value,
            target_type=c.target_type,
            target_id=c.target_id,
            reason=c.reason,
            started_at=c.started_at,
            is_active=c.is_active,
            affected_count=c.affected_count,
            initiated_by_id=c.initiated_by_id,
        )
        for c in controls
    ]
