"""
Tekvwa Pro Audit - Organization Users Router

API endpoints for managing users within an organization.

Endpoints:
- GET /organizations/{org_id}/users - List organization users
- POST /organizations/{org_id}/users/invite - Invite new user
- PUT /organizations/{org_id}/users/{user_id}/role - Update user role
- POST /organizations/{org_id}/users/{user_id}/deactivate - Deactivate user
- POST /organizations/{org_id}/users/{user_id}/reactivate - Reactivate user
- PUT /organizations/{org_id}/users/{user_id}/entity-access - Update entity access
- POST /me/impersonation - Toggle impersonation permission
"""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import (
    get_current_active_user,
    require_organization_permission,
    require_within_usage_limit,
    record_usage_event,
)
from app.models.user import User, UserRole
from app.services.organization_user_service import OrganizationUserService
from app.services.audit_service import AuditService
from app.services.metering_service import UsageMetricType
from app.models.audit_consolidated import AuditAction
from app.utils.permissions import OrganizationPermission


router = APIRouter(prefix="/organizations", tags=["Organization Users"])


# ===========================================
# REQUEST/RESPONSE SCHEMAS
# ===========================================

class InviteUserRequest(BaseModel):
    """Request schema for inviting a new user."""
    email: EmailStr
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    phone_number: Optional[str] = Field(None, max_length=20)
    role: str = Field(..., description="User role: owner, admin, accountant, external_accountant, auditor, payroll_manager, inventory_manager, viewer")
    entity_ids: Optional[List[uuid.UUID]] = Field(None, description="Optional list of entity IDs to grant access to")


class OrgUserResponse(BaseModel):
    """Response schema for organization user."""
    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    phone_number: Optional[str]
    role: str
    is_active: bool
    is_verified: bool
    can_be_impersonated: bool
    created_at: str
    
    class Config:
        from_attributes = True


class InviteUserResponse(BaseModel):
    """Response for user invitation."""
    user: OrgUserResponse
    temporary_password: str
    message: str


class OrgUserListResponse(BaseModel):
    """Response for user list."""
    users: List[OrgUserResponse]
    total: int


class UpdateRoleRequest(BaseModel):
    """Request for updating user role."""
    role: str = Field(..., description="New role")


class UpdateEntityAccessRequest(BaseModel):
    """Request for updating entity access."""
    entity_id: uuid.UUID
    can_write: bool
    can_delete: bool


class EntityAccessResponse(BaseModel):
    """Response for entity access update."""
    entity_id: uuid.UUID
    can_write: bool
    can_delete: bool


class ImpersonationToggleRequest(BaseModel):
    """Request for toggling impersonation permission."""
    allow: bool


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    success: bool = True


# ===========================================
# HELPER FUNCTIONS
# ===========================================

def parse_user_role(role_str: str) -> UserRole:
    """Parse string to UserRole enum."""
    role_map = {
        "owner": UserRole.OWNER,
        "admin": UserRole.ADMIN,
        "accountant": UserRole.ACCOUNTANT,
        "external_accountant": UserRole.EXTERNAL_ACCOUNTANT,  # NTAA 2025: For outsourced accounting firms
        "auditor": UserRole.AUDITOR,
        "payroll_manager": UserRole.PAYROLL_MANAGER,
        "inventory_manager": UserRole.INVENTORY_MANAGER,
        "viewer": UserRole.VIEWER,
    }
    role = role_map.get(role_str.lower())
    if not role:
        raise ValueError(f"Invalid role: {role_str}. Valid roles: {list(role_map.keys())}")
    return role


def user_to_response(user: User) -> OrgUserResponse:
    """Convert User model to OrgUserResponse."""
    return OrgUserResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        phone_number=user.phone_number,
        role=user.role.value if user.role else "unknown",
        is_active=user.is_active,
        is_verified=user.is_verified,
        can_be_impersonated=user.can_be_impersonated,
        created_at=user.created_at.isoformat() if user.created_at else "",
    )


# ===========================================
# ENDPOINTS
# ===========================================

@router.get(
    "/{org_id}/users",
    response_model=OrgUserListResponse,
    summary="List organization users",
    description="Get all users in an organization. Requires MANAGE_USERS permission.",
)
async def list_organization_users(
    org_id: uuid.UUID,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_organization_permission([OrganizationPermission.MANAGE_USERS])),
):
    """List all users in an organization."""
    service = OrganizationUserService(db)
    
    try:
        users = await service.get_organization_users(
            requesting_user=current_user,
            organization_id=org_id,
            include_inactive=include_inactive,
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    
    return OrgUserListResponse(
        users=[user_to_response(u) for u in users],
        total=len(users),
    )


@router.post(
    "/{org_id}/users/invite",
    response_model=InviteUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invite new user",
    description="Invite a new user to the organization. Returns a temporary password.",
)
async def invite_user(
    org_id: uuid.UUID,
    request: InviteUserRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_organization_permission([OrganizationPermission.MANAGE_USERS])),
    _limit_check: User = Depends(require_within_usage_limit(UsageMetricType.USERS)),
):
    """Invite a new user to the organization."""
    # Verify org_id matches current user's org
    if not current_user.is_platform_staff and current_user.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot invite users to another organization",
        )
    
    try:
        role = parse_user_role(request.role)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    service = OrganizationUserService(db)
    
    try:
        new_user, temp_password = await service.invite_user(
            requesting_user=current_user,
            email=request.email,
            first_name=request.first_name,
            last_name=request.last_name,
            role=role,
            phone_number=request.phone_number,
            entity_ids=request.entity_ids,
        )
        
        # Record usage metric for new user
        if current_user.organization_id:
            await record_usage_event(
                db=db,
                organization_id=current_user.organization_id,
                metric_type=UsageMetricType.USERS,
                user_id=current_user.id,
                resource_type="user",
                resource_id=str(new_user.id),
            )
        
        # Audit logging for user invitation
        audit_service = AuditService(db)
        await audit_service.log_action(
            business_entity_id=org_id,
            entity_type="user",
            entity_id=str(new_user.id),
            action=AuditAction.CREATE,
            user_id=current_user.id,
            new_values={
                "email": new_user.email,
                "first_name": new_user.first_name,
                "last_name": new_user.last_name,
                "role": role.value,
                "invited_by": current_user.email,
            }
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return InviteUserResponse(
        user=user_to_response(new_user),
        temporary_password=temp_password,
        message="User invited successfully. Please share the temporary password securely.",
    )


@router.put(
    "/{org_id}/users/{user_id}/role",
    response_model=OrgUserResponse,
    summary="Update user role",
    description="Update a user's role within the organization.",
)
async def update_user_role(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    request: UpdateRoleRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_organization_permission([OrganizationPermission.MANAGE_USERS])),
):
    """Update a user's role."""
    if not current_user.is_platform_staff and current_user.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify users in another organization",
        )
    
    try:
        new_role = parse_user_role(request.role)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    service = OrganizationUserService(db)
    
    try:
        updated_user = await service.update_user_role(
            requesting_user=current_user,
            target_user_id=user_id,
            new_role=new_role,
        )
        
        # Audit logging for role change
        audit_service = AuditService(db)
        await audit_service.log_action(
            business_entity_id=org_id,
            entity_type="user",
            entity_id=str(user_id),
            action=AuditAction.UPDATE,
            user_id=current_user.id,
            old_values={"role": "previous_role"},
            new_values={
                "role": new_role.value,
                "changed_by": current_user.email,
            }
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return user_to_response(updated_user)


@router.post(
    "/{org_id}/users/{user_id}/deactivate",
    response_model=MessageResponse,
    summary="Deactivate user",
    description="Deactivate a user's account in the organization.",
)
async def deactivate_user(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_organization_permission([OrganizationPermission.MANAGE_USERS])),
):
    """Deactivate a user."""
    if not current_user.is_platform_staff and current_user.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify users in another organization",
        )
    
    service = OrganizationUserService(db)
    
    try:
        await service.deactivate_user(
            requesting_user=current_user,
            target_user_id=user_id,
        )
        
        # Audit logging for user deactivation
        audit_service = AuditService(db)
        await audit_service.log_action(
            business_entity_id=org_id,
            entity_type="user",
            entity_id=str(user_id),
            action=AuditAction.UPDATE,
            user_id=current_user.id,
            old_values={"is_active": True},
            new_values={
                "is_active": False,
                "deactivated_by": current_user.email,
            }
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return MessageResponse(message="User deactivated successfully")


@router.post(
    "/{org_id}/users/{user_id}/reactivate",
    response_model=MessageResponse,
    summary="Reactivate user",
    description="Reactivate a deactivated user's account.",
)
async def reactivate_user(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_organization_permission([OrganizationPermission.MANAGE_USERS])),
):
    """Reactivate a deactivated user."""
    if not current_user.is_platform_staff and current_user.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify users in another organization",
        )
    
    service = OrganizationUserService(db)
    
    try:
        await service.reactivate_user(
            requesting_user=current_user,
            target_user_id=user_id,
        )
        
        # Audit logging for user reactivation
        audit_service = AuditService(db)
        await audit_service.log_action(
            business_entity_id=org_id,
            entity_type="user",
            entity_id=str(user_id),
            action=AuditAction.UPDATE,
            user_id=current_user.id,
            old_values={"is_active": False},
            new_values={
                "is_active": True,
                "reactivated_by": current_user.email,
            }
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return MessageResponse(message="User reactivated successfully")


@router.put(
    "/{org_id}/users/{user_id}/entity-access",
    response_model=EntityAccessResponse,
    summary="Update entity access",
    description="Update a user's access level for a specific entity.",
)
async def update_entity_access(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    request: UpdateEntityAccessRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_organization_permission([OrganizationPermission.MANAGE_USERS])),
):
    """Update entity access for a user."""
    if not current_user.is_platform_staff and current_user.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify users in another organization",
        )
    
    service = OrganizationUserService(db)
    
    try:
        access = await service.update_entity_access(
            requesting_user=current_user,
            target_user_id=user_id,
            entity_id=request.entity_id,
            can_write=request.can_write,
            can_delete=request.can_delete,
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return EntityAccessResponse(
        entity_id=access.entity_id,
        can_write=access.can_write,
        can_delete=access.can_delete,
    )


# ===========================================
# USER SELF-SERVICE ENDPOINTS
# ===========================================

@router.post(
    "/me/impersonation",
    response_model=MessageResponse,
    summary="Toggle impersonation permission",
    description="Allow or disallow customer service to impersonate your account for troubleshooting.",
)
async def toggle_impersonation(
    request: ImpersonationToggleRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """Toggle whether CSR can impersonate this user."""
    if current_user.is_platform_staff:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Platform staff accounts cannot be impersonated",
        )
    
    service = OrganizationUserService(db)
    await service.toggle_impersonation_permission(current_user, request.allow)
    
    if request.allow:
        return MessageResponse(message="Customer service can now access your account for troubleshooting")
    else:
        return MessageResponse(message="Customer service impersonation disabled")


# ===========================================
# ADDITIONAL USER MANAGEMENT ENDPOINTS
# ===========================================

@router.delete(
    "/{org_id}/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user",
    description="Permanently delete a user from the organization. Requires MANAGE_USERS permission.",
)
async def delete_user(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    permanent: bool = False,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_organization_permission([OrganizationPermission.MANAGE_USERS])),
):
    """
    Delete a user from the organization.
    
    By default, this is a soft delete (deactivation).
    Set permanent=true to permanently remove the user record.
    
    Note: Only org owners and admins can perform permanent deletions.
    User's historical data (transactions, audit trail) is preserved.
    """
    if not current_user.is_platform_staff and current_user.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete users in another organization",
        )
    
    # Cannot delete yourself
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )
    
    service = OrganizationUserService(db)
    
    try:
        if permanent:
            # Only owners can permanently delete
            if current_user.role not in [UserRole.OWNER]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only organization owners can permanently delete users",
                )
            await service.permanently_delete_user(
                requesting_user=current_user,
                target_user_id=user_id,
            )
        else:
            await service.deactivate_user(
                requesting_user=current_user,
                target_user_id=user_id,
            )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return None


class ForceResetPasswordRequest(BaseModel):
    """Request for forcing password reset."""
    send_email: bool = Field(True, description="Send password reset email to user")
    generate_temp_password: bool = Field(False, description="Generate and return temporary password")


class ForceResetPasswordResponse(BaseModel):
    """Response for force password reset."""
    message: str
    temporary_password: Optional[str] = None
    email_sent: bool


@router.post(
    "/{org_id}/users/{user_id}/force-reset-password",
    response_model=ForceResetPasswordResponse,
    summary="Force password reset",
    description="Force a user to reset their password on next login.",
)
async def force_reset_password(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    request: ForceResetPasswordRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_organization_permission([OrganizationPermission.MANAGE_USERS])),
):
    """
    Force a user to reset their password.
    
    Options:
    - Send password reset email
    - Generate temporary password (for secure sharing)
    - Mark account for password reset on next login
    """
    import secrets
    
    if not current_user.is_platform_staff and current_user.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot manage users in another organization",
        )
    
    service = OrganizationUserService(db)
    
    try:
        target_user = await service.get_user_by_id(user_id)
        
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        
        if target_user.organization_id != org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not belong to this organization",
            )
        
        temp_password = None
        email_sent = False
        
        # Mark user for forced password reset
        target_user.must_reset_password = True
        
        if request.generate_temp_password:
            # Generate temporary password
            temp_password = secrets.token_urlsafe(12)
            from app.utils.security import hash_password
            target_user.hashed_password = hash_password(temp_password)
        
        if request.send_email:
            from app.services.email_service import EmailService
            from app.services.auth_service import AuthService
            from app.config import settings
            
            auth_service = AuthService(db)
            email_service = EmailService()
            
            reset_token = auth_service.create_password_reset_token(target_user)
            reset_url = f"{settings.base_url}/reset-password?token={reset_token}"
            
            try:
                await email_service.send_password_reset(
                    to_email=target_user.email,
                    user_name=target_user.first_name,
                    reset_url=reset_url,
                )
                email_sent = True
            except Exception:
                pass
        
        await db.commit()
        
        return ForceResetPasswordResponse(
            message="Password reset initiated. User will be prompted to change password on next login.",
            temporary_password=temp_password,
            email_sent=email_sent,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to initiate password reset: {str(e)}",
        )


class EntityAccessListItem(BaseModel):
    """Entity access item for list response."""
    entity_id: uuid.UUID
    entity_name: str
    can_read: bool
    can_write: bool
    can_delete: bool
    granted_at: str
    granted_by: Optional[str]


class UserEntityAccessResponse(BaseModel):
    """Response for user's entity access list."""
    user_id: uuid.UUID
    user_name: str
    entities: List[EntityAccessListItem]
    total: int


@router.get(
    "/{org_id}/users/{user_id}/entity-access",
    response_model=UserEntityAccessResponse,
    summary="Get user entity access",
    description="Get all entity access permissions for a user.",
)
async def get_user_entity_access(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_organization_permission([OrganizationPermission.MANAGE_USERS])),
):
    """Get all entities a user has access to."""
    if not current_user.is_platform_staff and current_user.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot view users in another organization",
        )
    
    service = OrganizationUserService(db)
    
    try:
        target_user = await service.get_user_by_id(user_id)
        
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        
        if target_user.organization_id != org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not belong to this organization",
            )
        
        # Get entity access list
        entities = []
        for access in target_user.entity_access:
            entities.append(EntityAccessListItem(
                entity_id=access.entity_id,
                entity_name=access.entity.name if access.entity else "Unknown",
                can_read=True,  # Read access is implicit if record exists
                can_write=access.can_write,
                can_delete=access.can_delete,
                granted_at=access.created_at.isoformat() if hasattr(access, 'created_at') and access.created_at else "",
                granted_by=None,  # Would need to track this
            ))
        
        return UserEntityAccessResponse(
            user_id=target_user.id,
            user_name=f"{target_user.first_name} {target_user.last_name}",
            entities=entities,
            total=len(entities),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to get entity access: {str(e)}",
        )


class GrantEntityAccessRequest(BaseModel):
    """Request for granting entity access."""
    entity_ids: List[uuid.UUID] = Field(..., min_length=1)
    can_write: bool = True
    can_delete: bool = False


@router.post(
    "/{org_id}/users/{user_id}/entity-access/grant",
    response_model=MessageResponse,
    summary="Grant entity access",
    description="Grant access to multiple entities for a user.",
)
async def grant_entity_access(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    request: GrantEntityAccessRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_organization_permission([OrganizationPermission.MANAGE_USERS])),
):
    """Grant access to multiple entities for a user."""
    if not current_user.is_platform_staff and current_user.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot manage users in another organization",
        )
    
    service = OrganizationUserService(db)
    
    try:
        granted_count = await service.grant_entity_access_bulk(
            requesting_user=current_user,
            target_user_id=user_id,
            entity_ids=request.entity_ids,
            can_write=request.can_write,
            can_delete=request.can_delete,
        )
        
        return MessageResponse(
            message=f"Access granted to {granted_count} entities",
        )
        
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


class RevokeEntityAccessRequest(BaseModel):
    """Request for revoking entity access."""
    entity_ids: List[uuid.UUID] = Field(..., min_length=1)


@router.post(
    "/{org_id}/users/{user_id}/entity-access/revoke",
    response_model=MessageResponse,
    summary="Revoke entity access",
    description="Revoke access to entities for a user.",
)
async def revoke_entity_access(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    request: RevokeEntityAccessRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_organization_permission([OrganizationPermission.MANAGE_USERS])),
):
    """Revoke access to entities for a user."""
    if not current_user.is_platform_staff and current_user.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot manage users in another organization",
        )
    
    service = OrganizationUserService(db)
    
    try:
        revoked_count = await service.revoke_entity_access_bulk(
            requesting_user=current_user,
            target_user_id=user_id,
            entity_ids=request.entity_ids,
        )
        
        return MessageResponse(
            message=f"Access revoked from {revoked_count} entities",
        )
        
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/{org_id}/users/{user_id}",
    response_model=OrgUserResponse,
    summary="Get user details",
    description="Get detailed information about a specific user.",
)
async def get_user_details(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_organization_permission([OrganizationPermission.MANAGE_USERS])),
):
    """Get details for a specific user."""
    if not current_user.is_platform_staff and current_user.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot view users in another organization",
        )
    
    service = OrganizationUserService(db)
    
    user = await service.get_user_by_id(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    if user.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not belong to this organization",
        )
    
    return user_to_response(user)
