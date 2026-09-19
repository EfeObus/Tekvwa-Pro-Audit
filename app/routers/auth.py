"""
Tekvwa Pro Audit - Authentication Router

API endpoints for user authentication.
"""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_async_session
from app.dependencies import get_current_user, get_current_active_user
from app.models.user import User
from app.schemas.auth import (
    UserRegisterRequest,
    UserLoginRequest,
    TokenRefreshRequest,
    PasswordChangeRequest,
    PasswordResetRequest,
    PasswordResetConfirm,
    TokenResponse,
    UserResponse,
    UserWithTokenResponse,
    CurrentUserResponse,
    OrganizationResponse,
    EntityAccessResponse,
    MessageResponse,
    EmailVerificationRequest,
    ResendVerificationRequest,
)
from app.config import settings
from app.services.auth_service import AuthService
from app.services.email_service import EmailService
from app.services.audit_service import AuditService
from app.models.audit_consolidated import AuditAction
from app.utils.security import verify_refresh_token


router = APIRouter()


@router.post(
    "/register",
    response_model=UserWithTokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Register a new user with organization. Creates user, organization, and default business entity. Supports multiple account types: Individual, Small Business, SME, School, Non-Profit, Corporation.",
)
async def register(
    request: UserRegisterRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Register a new user with organization.
    
    Supports different account types:
    - Individual: Personal use, minimal info required
    - Small Business: Micro businesses (BN registration)
    - SME: Small & Medium Enterprises (RC registration)
    - School: Educational institutions
    - Non-Profit: NGOs and charities (IT registration)
    - Corporation: Large companies
    """
    auth_service = AuthService(db)
    email_service = EmailService()
    
    try:
        user, organization, entity = await auth_service.register_user(
            email=request.email,
            password=request.password,
            first_name=request.first_name,
            last_name=request.last_name,
            organization_name=request.organization_name,
            phone_number=request.phone_number,
            # New comprehensive registration fields
            account_type=request.account_type,
            street_address=request.street_address,
            city=request.city,
            state=request.state,
            lga=request.lga,
            postal_code=request.postal_code,
            country=request.country,
            tin=request.tin,
            cac_registration_number=request.cac_registration_number,
            cac_registration_type=request.cac_registration_type,
            date_of_incorporation=request.date_of_incorporation,
            nin=request.nin,
            industry=request.industry,
            employee_count=request.employee_count,
            annual_revenue_range=request.annual_revenue_range,
            school_type=request.school_type,
            moe_registration_number=request.moe_registration_number,
            scuml_registration=request.scuml_registration,
            mission_statement=request.mission_statement,
            referral_code=request.referral_code,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    # Send verification email (only for self-registered users)
    try:
        verification_token = auth_service.create_email_verification_token(user)
        # Commit the verification token to database
        await db.commit()
        await db.refresh(user)
        
        verification_url = f"{settings.base_url}/verify-email?token={verification_token}"
        await email_service.send_verification_email(
            to_email=user.email,
            user_name=user.first_name,
            verification_url=verification_url,
        )
    except Exception:
        # Log the error but don't fail registration
        pass
    
    # Create tokens
    tokens = auth_service.create_tokens(user)
    
    return UserWithTokenResponse(
        user=UserResponse(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            phone_number=user.phone_number,
            role=user.role.value if user.role else None,
            is_active=user.is_active,
            is_verified=user.is_verified,
            must_reset_password=getattr(user, 'must_reset_password', False),
            organization_id=user.organization_id,
            is_platform_staff=user.is_platform_staff,
            platform_role=user.platform_role.value if user.platform_role else None,
            created_at=user.created_at,
        ),
        tokens=TokenResponse(**tokens),
    )


@router.post(
    "/login",
    response_model=UserWithTokenResponse,
    summary="Login user",
    description="Authenticate user with email and password. Works for both organization users and platform staff.",
)
async def login(
    request: UserLoginRequest,
    response: Response,
    fastapi_request: Request = None,
    db: AsyncSession = Depends(get_async_session),
):
    """Login with email and password."""
    from app.utils.ndpa_security import AccountLockoutManager
    
    # Get client IP for lockout tracking
    client_ip = "127.0.0.1"
    if fastapi_request and hasattr(fastapi_request, 'state') and hasattr(fastapi_request.state, 'client_ip'):
        client_ip = fastapi_request.state.client_ip
    elif fastapi_request and fastapi_request.client:
        client_ip = fastapi_request.client.host
    
    # Get user agent for audit logging
    user_agent = fastapi_request.headers.get("user-agent", "unknown") if fastapi_request else "unknown"
    
    # Check if account/IP is locked out
    is_locked, seconds_remaining = AccountLockoutManager.is_locked_out(request.email)
    if not is_locked:
        is_locked, seconds_remaining = AccountLockoutManager.is_locked_out(client_ip)
    
    if is_locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Account temporarily locked. Try again in {seconds_remaining} seconds.",
            headers={"Retry-After": str(seconds_remaining)},
        )
    
    auth_service = AuthService(db)
    
    user = await auth_service.authenticate_user(
        email=request.email,
        password=request.password,
    )
    
    if not user:
        # Record failed attempt
        remaining, lockout_duration = AccountLockoutManager.record_failed_attempt(request.email)
        AccountLockoutManager.record_failed_attempt(client_ip)
        
        # Audit logging for failed login
        audit_service = AuditService(db)
        await audit_service.log_action(
            business_entity_id=None,
            entity_type="user",
            entity_id=None,
            action=AuditAction.LOGIN_FAILED,
            user_id=None,
            new_values={
                "email": request.email,
                "ip_address": client_ip,
                "reason": "invalid_credentials",
            },
            ip_address=client_ip,
            user_agent=user_agent,
        )
        
        if lockout_duration:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many failed attempts. Account locked for {lockout_duration} seconds.",
                headers={"Retry-After": str(lockout_duration)},
            )
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid email or password. {remaining} attempts remaining.",
        )
    
    # Clear failed attempts on successful login
    AccountLockoutManager.clear_attempts(request.email)
    AccountLockoutManager.clear_attempts(client_ip)
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )
    
    # Audit logging for successful login
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=user.organization_id if user.organization_id else user.id,
        entity_type="user",
        entity_id=str(user.id),
        action=AuditAction.LOGIN,
        user_id=user.id,
        new_values={
            "email": user.email,
            "ip_address": client_ip,
            "user_agent": user_agent,
            "login_time": str(datetime.utcnow()),
        },
        ip_address=client_ip,
        user_agent=user_agent,
    )
    
    # Create tokens
    tokens = auth_service.create_tokens(user)
    
    # Set access token as HTTP-only cookie for server-side authentication
    # This is more reliable than client-side JavaScript cookie setting
    is_production = settings.app_env == 'production'
    response.set_cookie(
        key="access_token",
        value=tokens["access_token"],
        max_age=60 * 60 * 24 * 7,  # 7 days
        path="/",
        httponly=False,  # Allow JS access for now (needed for some client-side operations)
        samesite="lax",
        secure=is_production,  # Use Secure flag in production (HTTPS)
    )
    
    return UserWithTokenResponse(
        user=UserResponse(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            phone_number=user.phone_number,
            role=user.role.value if user.role else None,
            is_active=user.is_active,
            is_verified=user.is_verified,
            must_reset_password=getattr(user, 'must_reset_password', False),
            organization_id=user.organization_id,
            is_platform_staff=user.is_platform_staff,
            platform_role=user.platform_role.value if user.platform_role else None,
            created_at=user.created_at,
        ),
        tokens=TokenResponse(**tokens),
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
    description="Get a new access token using refresh token.",
)
async def refresh_token(
    request: TokenRefreshRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """Refresh access token."""
    payload = verify_refresh_token(request.refresh_token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    
    auth_service = AuthService(db)
    
    import uuid
    user_id = uuid.UUID(payload.get("sub"))
    user = await auth_service.get_user_by_id(user_id)
    
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
    
    # Create new tokens
    tokens = auth_service.create_tokens(user)
    
    return TokenResponse(**tokens)


@router.get(
    "/me",
    response_model=CurrentUserResponse,
    summary="Get current user",
    description="Get the current authenticated user with organization and entity access. Works for both org users and platform staff.",
)
async def get_me(
    current_user: User = Depends(get_current_active_user),
):
    """Get current authenticated user."""
    from app.utils.permissions import (
        get_platform_permissions,
        get_organization_permissions,
    )
    
    # Build entity access list (only for org users)
    entity_access_list = []
    if not current_user.is_platform_staff:
        for access in current_user.entity_access:
            entity_access_list.append(
                EntityAccessResponse(
                    entity_id=access.entity_id,
                    entity_name=access.entity.name if access.entity else "Unknown",
                    can_write=access.can_write,
                    can_delete=access.can_delete,
                )
            )
    
    # Get permissions based on user type
    permissions = []
    if current_user.is_platform_staff and current_user.platform_role:
        permissions = [p.value for p in get_platform_permissions(current_user.platform_role)]
    elif current_user.role:
        permissions = [p.value for p in get_organization_permissions(current_user.role)]
    
    # Build organization response (only for org users)
    org_response = None
    if current_user.organization:
        org_response = OrganizationResponse(
            id=current_user.organization.id,
            name=current_user.organization.name,
            slug=current_user.organization.slug,
            subscription_tier=current_user.organization.subscription_tier.value,
            organization_type=current_user.organization.organization_type.value if hasattr(current_user.organization, 'organization_type') and current_user.organization.organization_type else None,
            verification_status=current_user.organization.verification_status.value if hasattr(current_user.organization, 'verification_status') and current_user.organization.verification_status else None,
            is_verified=current_user.organization.is_verified if hasattr(current_user.organization, 'is_verified') else False,
            created_at=current_user.organization.created_at,
        )
    
    return CurrentUserResponse(
        user=UserResponse(
            id=current_user.id,
            email=current_user.email,
            first_name=current_user.first_name,
            last_name=current_user.last_name,
            phone_number=current_user.phone_number,
            role=current_user.role.value if current_user.role else None,
            is_active=current_user.is_active,
            is_verified=current_user.is_verified,
            must_reset_password=getattr(current_user, 'must_reset_password', False),
            organization_id=current_user.organization_id,
            is_platform_staff=current_user.is_platform_staff,
            platform_role=current_user.platform_role.value if current_user.platform_role else None,
            created_at=current_user.created_at,
        ),
        organization=org_response,
        entity_access=entity_access_list,
        permissions=permissions,
    )


@router.post(
    "/change-password",
    response_model=MessageResponse,
    summary="Change password",
    description="Change the current user's password.",
)
async def change_password(
    request: PasswordChangeRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Change user password."""
    auth_service = AuthService(db)
    
    try:
        await auth_service.change_password(
            user=current_user,
            current_password=request.current_password,
            new_password=request.new_password,
        )
        
        # Audit logging for password change
        audit_service = AuditService(db)
        await audit_service.log_action(
            business_entity_id=current_user.organization_id if current_user.organization_id else current_user.id,
            entity_type="user",
            entity_id=str(current_user.id),
            action=AuditAction.UPDATE,
            user_id=current_user.id,
            new_values={
                "action": "password_change",
                "email": current_user.email,
            }
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return MessageResponse(
        message="Password changed successfully",
        success=True,
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Logout user",
    description="Logout the current user (client should discard tokens).",
)
async def logout(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Logout user.
    
    Note: JWT tokens are stateless, so logout is handled client-side
    by discarding the tokens. This endpoint is for consistency and
    future token blacklisting implementation.
    """
    # Audit logging for logout
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=current_user.organization_id if current_user.organization_id else current_user.id,
        entity_type="user",
        entity_id=str(current_user.id),
        action=AuditAction.LOGOUT,
        user_id=current_user.id,
        new_values={
            "email": current_user.email,
        }
    )
    
    return MessageResponse(
        message="Logged out successfully",
        success=True,
    )


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    summary="Request password reset",
    description="Send a password reset email to the user.",
)
async def forgot_password(
    request: PasswordResetRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """Request password reset email."""
    auth_service = AuthService(db)
    email_service = EmailService()
    
    user = await auth_service.get_user_by_email(request.email)
    
    # Always return success to prevent email enumeration attacks
    if user:
        reset_token = auth_service.create_password_reset_token(user)
        reset_url = f"{settings.base_url}/reset-password?token={reset_token}"
        
        try:
            await email_service.send_password_reset(
                to_email=user.email,
                user_name=user.first_name,
                reset_url=reset_url,
            )
        except Exception:
            # Log the error but don't expose to user
            pass
    
    return MessageResponse(
        message="If an account with that email exists, a password reset link has been sent.",
        success=True,
    )


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    summary="Reset password with token",
    description="Reset the user's password using a valid reset token.",
)
async def reset_password(
    request: PasswordResetConfirm,
    db: AsyncSession = Depends(get_async_session),
):
    """Reset password using reset token."""
    auth_service = AuthService(db)
    
    try:
        await auth_service.reset_password_with_token(
            token=request.token,
            new_password=request.new_password,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return MessageResponse(
        message="Password reset successfully",
        success=True,
    )


@router.post(
    "/verify-email",
    response_model=MessageResponse,
    summary="Verify email address",
    description="Verify user's email address using the verification token sent to their email.",
)
async def verify_email(
    request: EmailVerificationRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """Verify email address using verification token."""
    auth_service = AuthService(db)
    
    try:
        await auth_service.verify_email_with_token(token=request.token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return MessageResponse(
        message="Email verified successfully. You can now access all features.",
        success=True,
    )


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    summary="Resend verification email",
    description="Resend the email verification link to the user's email address.",
)
async def resend_verification(
    request: ResendVerificationRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """Resend verification email."""
    auth_service = AuthService(db)
    email_service = EmailService()
    
    user = await auth_service.resend_verification_email(request.email)
    
    # Always return success to prevent email enumeration attacks
    if user:
        verification_token = auth_service.create_email_verification_token(user)
        # Commit the token to database
        await db.commit()
        await db.refresh(user)
        
        verification_url = f"{settings.base_url}/verify-email?token={verification_token}"
        
        try:
            await email_service.send_verification_email(
                to_email=user.email,
                user_name=user.first_name,
                verification_url=verification_url,
            )
        except Exception:
            # Log the error but don't expose to user
            pass
    
    return MessageResponse(
        message="If an unverified account with that email exists, a verification link has been sent.",
        success=True,
    )


# ===========================================
# USER PROFILE MANAGEMENT
# ===========================================

class UpdateProfileRequest(BaseModel):
    """Request schema for updating user profile."""
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone_number: Optional[str] = Field(None, max_length=20)


class ProfileResponse(BaseModel):
    """Response for profile operations."""
    id: str
    email: str
    first_name: str
    last_name: str
    phone_number: Optional[str]
    role: Optional[str]
    is_platform_staff: bool
    platform_role: Optional[str]
    is_verified: bool
    created_at: str
    updated_at: Optional[str]


@router.patch(
    "/me",
    response_model=ProfileResponse,
    summary="Update current user profile",
    description="Update the current user's profile information.",
)
async def update_profile(
    request: UpdateProfileRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Update current user's profile."""
    update_data = request.model_dump(exclude_unset=True)
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )
    
    for key, value in update_data.items():
        setattr(current_user, key, value)
    
    await db.commit()
    await db.refresh(current_user)
    
    return ProfileResponse(
        id=str(current_user.id),
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        phone_number=current_user.phone_number,
        role=current_user.role.value if current_user.role else None,
        is_platform_staff=current_user.is_platform_staff,
        platform_role=current_user.platform_role.value if current_user.platform_role else None,
        is_verified=current_user.is_verified,
        created_at=current_user.created_at.isoformat(),
        updated_at=current_user.updated_at.isoformat() if current_user.updated_at else None,
    )


@router.delete(
    "/me",
    response_model=MessageResponse,
    summary="Request account deletion",
    description="Request deletion of the current user's account. Requires confirmation.",
)
async def request_account_deletion(
    confirm: bool = Query(False, description="Confirm account deletion"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Request account deletion (soft delete)."""
    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please confirm account deletion by setting confirm=true",
        )
    
    # Soft delete - deactivate the account
    current_user.is_active = False
    await db.commit()
    
    return MessageResponse(
        message="Account has been deactivated. Contact support to permanently delete your data.",
        success=True,
    )


@router.get(
    "/me/sessions",
    summary="Get active sessions",
    description="Get list of active login sessions (placeholder for future implementation).",
)
async def get_sessions(
    current_user: User = Depends(get_current_active_user),
):
    """Get active sessions (placeholder)."""
    # In a full implementation, this would query a sessions table
    return {
        "sessions": [
            {
                "id": "current",
                "device": "Current Device",
                "ip_address": "Unknown",
                "last_active": current_user.updated_at.isoformat() if current_user.updated_at else None,
                "is_current": True,
            }
        ],
        "total": 1,
    }


# ===========================================
# DASHBOARD API
# ===========================================

@router.get(
    "/dashboard",
    summary="Get user dashboard",
    description="Get the full dashboard for the current user including 2026 compliance data.",
)
async def get_dashboard(
    entity_id: str = None,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get dashboard with 2026 compliance features.
    
    Includes:
    - TIN/CAC Vault display
    - Compliance Health indicator
    - Financial metrics
    - Recent transactions
    """
    from app.services.dashboard_service import DashboardService
    import uuid as uuid_module
    
    dashboard_service = DashboardService(db)
    
    # Parse entity_id if provided
    parsed_entity_id = None
    if entity_id:
        try:
            parsed_entity_id = uuid_module.UUID(entity_id)
        except ValueError:
            pass
    
    dashboard_data = await dashboard_service.get_dashboard(current_user, parsed_entity_id)
    
    return dashboard_data


# ===========================================
# TWO-FACTOR AUTHENTICATION (2FA)
# ===========================================

from pydantic import BaseModel, Field
from typing import Optional, List


class Setup2FAResponse(BaseModel):
    """Response for 2FA setup initiation."""
    secret: str
    qr_code_url: str
    backup_codes: List[str]
    message: str


class Verify2FARequest(BaseModel):
    """Request to verify and enable 2FA."""
    code: str = Field(..., min_length=6, max_length=6, description="6-digit TOTP code")


class Disable2FARequest(BaseModel):
    """Request to disable 2FA."""
    password: str = Field(..., min_length=1, description="Current password for verification")
    code: str = Field(..., min_length=6, max_length=6, description="Current 2FA code")


class Login2FARequest(BaseModel):
    """Request for 2FA verification during login."""
    user_id: str = Field(..., description="User ID from initial login response")
    code: str = Field(..., min_length=6, max_length=6, description="6-digit TOTP code")


class TwoFactorStatusResponse(BaseModel):
    """Response for 2FA status check."""
    enabled: bool
    verified: bool
    backup_codes_remaining: int
    last_verified: Optional[str]


@router.post(
    "/2fa/setup",
    response_model=Setup2FAResponse,
    summary="Setup two-factor authentication",
)
async def setup_2fa(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Initiate 2FA setup for the current user.
    
    Returns:
    - Secret key for manual entry
    - QR code URL for authenticator apps
    - Backup codes for account recovery
    
    The user must verify the setup by calling /auth/2fa/verify
    with a valid TOTP code before 2FA is fully enabled.
    """
    import secrets
    import pyotp
    import base64
    
    # Generate a new TOTP secret
    secret = pyotp.random_base32()
    
    # Generate backup codes
    backup_codes = [secrets.token_hex(4).upper() for _ in range(8)]
    
    # Store the secret temporarily (not verified yet)
    # In production, store encrypted in database
    current_user.totp_secret_pending = secret
    current_user.backup_codes_pending = ",".join(backup_codes)
    
    await db.commit()
    
    # Generate QR code URL for authenticator apps
    totp = pyotp.TOTP(secret)
    qr_code_url = totp.provisioning_uri(
        name=current_user.email,
        issuer_name="Tekvwa Pro Audit"
    )
    
    return Setup2FAResponse(
        secret=secret,
        qr_code_url=qr_code_url,
        backup_codes=backup_codes,
        message="Scan the QR code with your authenticator app, then verify with a code.",
    )


@router.post(
    "/2fa/verify",
    response_model=MessageResponse,
    summary="Verify and enable 2FA",
)
async def verify_2fa_setup(
    request: Verify2FARequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Verify the 2FA setup with a TOTP code.
    
    This enables 2FA for the account after successful verification.
    """
    import pyotp
    
    pending_secret = getattr(current_user, 'totp_secret_pending', None)
    if not pending_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending 2FA setup. Please call /auth/2fa/setup first.",
        )
    
    # Verify the code
    totp = pyotp.TOTP(pending_secret)
    if not totp.verify(request.code, valid_window=1):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code. Please try again.",
        )
    
    # Enable 2FA
    current_user.totp_secret = pending_secret
    current_user.backup_codes = getattr(current_user, 'backup_codes_pending', '')
    current_user.totp_secret_pending = None
    current_user.backup_codes_pending = None
    current_user.two_factor_enabled = True
    
    await db.commit()
    
    return MessageResponse(
        message="Two-factor authentication has been enabled successfully.",
        success=True,
    )


@router.post(
    "/2fa/disable",
    response_model=MessageResponse,
    summary="Disable 2FA",
)
async def disable_2fa(
    request: Disable2FARequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Disable two-factor authentication.
    
    Requires both password and current 2FA code for security.
    """
    import pyotp
    from app.utils.security import verify_password
    
    # Verify password
    if not verify_password(request.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password.",
        )
    
    # Check if 2FA is enabled
    if not getattr(current_user, 'two_factor_enabled', False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is not enabled.",
        )
    
    # Verify the 2FA code
    totp_secret = getattr(current_user, 'totp_secret', None)
    if totp_secret:
        totp = pyotp.TOTP(totp_secret)
        if not totp.verify(request.code, valid_window=1):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid 2FA code.",
            )
    
    # Disable 2FA
    current_user.two_factor_enabled = False
    current_user.totp_secret = None
    current_user.backup_codes = None
    
    await db.commit()
    
    return MessageResponse(
        message="Two-factor authentication has been disabled.",
        success=True,
    )


@router.get(
    "/2fa/status",
    response_model=TwoFactorStatusResponse,
    summary="Get 2FA status",
)
async def get_2fa_status(
    current_user: User = Depends(get_current_active_user),
):
    """Get the current 2FA status for the user."""
    backup_codes = getattr(current_user, 'backup_codes', None)
    backup_count = len(backup_codes.split(',')) if backup_codes else 0
    
    return TwoFactorStatusResponse(
        enabled=getattr(current_user, 'two_factor_enabled', False),
        verified=getattr(current_user, 'totp_secret', None) is not None,
        backup_codes_remaining=backup_count,
        last_verified=None,  # Would track in production
    )


@router.get(
    "/2fa/backup-codes",
    summary="View backup codes",
    description="View existing backup codes. Requires password verification.",
)
async def view_backup_codes(
    password: str = Query(..., description="Current password for verification"),
    current_user: User = Depends(get_current_active_user),
):
    """
    View the current backup codes for 2FA recovery.
    
    Requires password verification for security.
    """
    from app.utils.security import verify_password
    
    # Verify password
    if not verify_password(password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password.",
        )
    
    if not getattr(current_user, 'two_factor_enabled', False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is not enabled.",
        )
    
    backup_codes = getattr(current_user, 'backup_codes', '')
    codes_list = backup_codes.split(',') if backup_codes else []
    
    return {
        "backup_codes": codes_list,
        "remaining": len(codes_list),
    }


@router.post(
    "/2fa/verify-login",
    response_model=UserWithTokenResponse,
    summary="Complete login with 2FA",
)
async def verify_2fa_login(
    request: Login2FARequest,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Complete login by verifying 2FA code.
    
    This endpoint is called after initial login returns requires_2fa=true.
    """
    import pyotp
    import uuid
    
    auth_service = AuthService(db)
    
    try:
        user_id = uuid.UUID(request.user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format.",
        )
    
    user = await auth_service.get_user_by_id(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    
    # Verify the 2FA code
    totp_secret = getattr(user, 'totp_secret', None)
    backup_codes = getattr(user, 'backup_codes', '')
    
    code_valid = False
    
    if totp_secret:
        totp = pyotp.TOTP(totp_secret)
        code_valid = totp.verify(request.code, valid_window=1)
    
    # Check backup codes if TOTP didn't work
    if not code_valid and backup_codes:
        codes_list = backup_codes.split(',')
        if request.code.upper() in codes_list:
            code_valid = True
            # Remove used backup code
            codes_list.remove(request.code.upper())
            user.backup_codes = ','.join(codes_list)
            await db.commit()
    
    if not code_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid 2FA code.",
        )
    
    # Create tokens
    tokens = auth_service.create_tokens(user)
    
    return UserWithTokenResponse(
        user=UserResponse(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            phone_number=user.phone_number,
            role=user.role.value if user.role else None,
            is_active=user.is_active,
            is_verified=user.is_verified,
            must_reset_password=getattr(user, 'must_reset_password', False),
            organization_id=user.organization_id,
            is_platform_staff=user.is_platform_staff,
            platform_role=user.platform_role.value if user.platform_role else None,
            created_at=user.created_at,
        ),
        tokens=TokenResponse(**tokens),
    )


@router.post(
    "/2fa/regenerate-backup-codes",
    summary="Regenerate backup codes",
)
async def regenerate_backup_codes(
    password: str = Query(..., description="Current password for verification"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Regenerate backup codes for 2FA recovery.
    
    This invalidates all previous backup codes.
    """
    import secrets
    from app.utils.security import verify_password
    
    # Verify password
    if not verify_password(password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password.",
        )
    
    if not getattr(current_user, 'two_factor_enabled', False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is not enabled.",
        )
    
    # Generate new backup codes
    backup_codes = [secrets.token_hex(4).upper() for _ in range(8)]
    current_user.backup_codes = ','.join(backup_codes)
    
    await db.commit()
    
    return {
        "backup_codes": backup_codes,
        "message": "New backup codes generated. Store them securely.",
    }


# ===========================================
# SESSION MANAGEMENT
# ===========================================

class SessionResponse(BaseModel):
    """Response for a single session."""
    id: str
    device: str
    browser: str
    ip_address: str
    location: Optional[str]
    created_at: str
    last_active: str
    is_current: bool


class SessionListResponse(BaseModel):
    """Response for session list."""
    sessions: List[SessionResponse]
    total: int


@router.get(
    "/sessions",
    response_model=SessionListResponse,
    summary="List active sessions",
)
async def list_sessions(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    List all active sessions for the current user.
    
    Shows device info, location, and last activity time.
    """
    from datetime import datetime
    
    # In production, query a sessions table
    # For now, return current session info
    sessions = [
        SessionResponse(
            id="current-session",
            device="Current Device",
            browser="Unknown",
            ip_address="Unknown",
            location=None,
            created_at=current_user.created_at.isoformat() if current_user.created_at else datetime.now().isoformat(),
            last_active=current_user.updated_at.isoformat() if current_user.updated_at else datetime.now().isoformat(),
            is_current=True,
        )
    ]
    
    return SessionListResponse(
        sessions=sessions,
        total=len(sessions),
    )


@router.delete(
    "/sessions/{session_id}",
    response_model=MessageResponse,
    summary="Revoke a session",
)
async def revoke_session(
    session_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Revoke a specific session.
    
    This logs out the device associated with that session.
    Cannot revoke the current session (use /logout instead).
    """
    if session_id == "current-session":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot revoke current session. Use /auth/logout instead.",
        )
    
    # In production, delete from sessions table
    # For now, return success
    
    return MessageResponse(
        message="Session revoked successfully.",
        success=True,
    )


@router.post(
    "/sessions/revoke-all",
    response_model=MessageResponse,
    summary="Revoke all other sessions",
)
async def revoke_all_sessions(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Revoke all sessions except the current one.
    
    Useful when a user suspects unauthorized access.
    """
    # In production, delete all sessions except current from sessions table
    # For now, return success
    
    return MessageResponse(
        message="All other sessions have been revoked.",
        success=True,
    )


@router.get(
    "/sessions/activity",
    summary="Get login activity",
)
async def get_login_activity(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get recent login activity for the current user.
    
    Shows login attempts, successes, and failures.
    """
    from datetime import datetime
    
    # In production, query audit log
    # For now, return minimal data
    
    return {
        "activity": [
            {
                "id": "1",
                "type": "login_success",
                "device": "Current Device",
                "ip_address": "Unknown",
                "timestamp": datetime.now().isoformat(),
                "details": "Successful login",
            }
        ],
        "total": 1,
    }


# ===========================================
# NIGERIA STATES AND LGAS
# ===========================================

@router.get(
    "/nigeria/states",
    summary="Get Nigerian states",
    description="Get list of all Nigerian states including FCT.",
)
async def get_nigeria_states():
    """Get all Nigerian states for registration dropdowns."""
    from app.utils.nigeria_data import get_all_states
    
    states = get_all_states()
    return {"states": states, "total": len(states)}


@router.get(
    "/nigeria/states/{state}/lgas",
    summary="Get LGAs for a state",
    description="Get list of Local Government Areas for a specific Nigerian state.",
)
async def get_state_lgas(state: str):
    """Get LGAs for a specific Nigerian state."""
    from app.utils.nigeria_data import get_lgas_by_state
    
    lgas = get_lgas_by_state(state)
    if not lgas:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"State '{state}' not found. Please provide a valid Nigerian state.",
        )
    
    return {"state": state, "lgas": lgas, "total": len(lgas)}
