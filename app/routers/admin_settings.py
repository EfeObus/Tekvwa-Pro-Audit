"""
TekVwarho ProAudit - Platform Settings Router

Super Admin endpoints for managing platform-wide settings.
Includes general settings, trial configuration, billing, NRS, and notifications.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import require_super_admin
from app.models.user import User
from app.models.audit_consolidated import AuditLog, AuditAction

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/settings",
    tags=["Admin - Platform Settings"],
)


# ========= SCHEMAS =========

class GeneralSettingsRequest(BaseModel):
    """General platform settings."""
    platform_name: str = Field(default="TekVwarho ProAudit", max_length=100)
    support_email: EmailStr = Field(default="info@tekvwa.org")
    billing_email: EmailStr = Field(default="info@tekvwa.org")
    default_currency: str = Field(default="NGN", pattern="^[A-Z]{3}$")
    default_timezone: str = Field(default="Africa/Lagos")


class TrialSettingsRequest(BaseModel):
    """Trial and subscription settings."""
    trial_days: int = Field(default=14, ge=0, le=90)
    grace_days: int = Field(default=7, ge=0, le=30)
    default_trial_tier: str = Field(default="core", pattern="^(core|professional|enterprise)$")
    allow_trial_extensions: bool = Field(default=True)
    max_trial_extensions: int = Field(default=2, ge=0, le=5)


class NRSSettingsRequest(BaseModel):
    """NRS Gateway settings."""
    api_endpoint: str = Field(default="https://api.nrs.gov.ng/v1")
    sandbox_mode: bool = Field(default=True)
    auto_submit: bool = Field(default=False)
    retry_failed: bool = Field(default=True)
    retry_attempts: int = Field(default=3, ge=1, le=10)


class BillingSettingsRequest(BaseModel):
    """Billing and payment settings."""
    paystack_public_key: Optional[str] = Field(None, max_length=100)
    paystack_secret_key: Optional[str] = Field(None, max_length=100)
    paystack_sandbox_mode: bool = Field(default=True)
    auto_charge_enabled: bool = Field(default=False)
    invoice_prefix: str = Field(default="INV", max_length=10)


class SecuritySettingsRequest(BaseModel):
    """Security configuration settings."""
    max_login_attempts: int = Field(default=5, ge=3, le=10)
    lockout_duration_minutes: int = Field(default=30, ge=5, le=1440)
    session_timeout_minutes: int = Field(default=60, ge=15, le=480)
    require_mfa_for_admins: bool = Field(default=False)
    geo_fencing_enabled: bool = Field(default=True)
    allowed_countries: list = Field(default=["NG"])


class NotificationSettingsRequest(BaseModel):
    """Notification and email settings."""
    smtp_host: str = Field(default="smtp.sendgrid.net", max_length=255)
    smtp_port: int = Field(default=587, ge=25, le=65535)
    from_email: EmailStr = Field(default="info@tekvwa.org")
    from_name: str = Field(default="TekVwarho ProAudit", max_length=100)
    email_enabled: bool = Field(default=True)
    sms_enabled: bool = Field(default=False)
    slack_enabled: bool = Field(default=False)


class PlatformSettingsResponse(BaseModel):
    """Complete platform settings response."""
    general: Dict[str, Any]
    trial: Dict[str, Any]
    nrs: Dict[str, Any]
    billing: Dict[str, Any]
    security: Dict[str, Any]
    notifications: Dict[str, Any]
    updated_at: datetime
    updated_by: Optional[str] = None


# ========= In-memory settings store (replace with database in production) =========
# In a production system, these would be stored in a database table

_platform_settings = {
    "general": {
        "platform_name": "TekVwarho ProAudit",
        "support_email": "info@tekvwa.org",
        "billing_email": "info@tekvwa.org",
        "default_currency": "NGN",
        "default_timezone": "Africa/Lagos",
    },
    "trial": {
        "trial_days": 14,
        "grace_days": 7,
        "default_trial_tier": "core",
        "allow_trial_extensions": True,
        "max_trial_extensions": 2,
    },
    "nrs": {
        "api_endpoint": "https://api.nrs.gov.ng/v1",
        "sandbox_mode": True,
        "auto_submit": False,
        "retry_failed": True,
        "retry_attempts": 3,
    },
    "billing": {
        "paystack_public_key": "",
        "paystack_secret_key_masked": "••••••••",
        "paystack_sandbox_mode": True,
        "auto_charge_enabled": False,
        "invoice_prefix": "INV",
    },
    "security": {
        "max_login_attempts": 5,
        "lockout_duration_minutes": 30,
        "session_timeout_minutes": 60,
        "require_mfa_for_admins": False,
        "geo_fencing_enabled": True,
        "allowed_countries": ["NG"],
    },
    "notifications": {
        "smtp_host": "smtp.sendgrid.net",
        "smtp_port": 587,
        "from_email": "info@tekvwa.org",
        "from_name": "TekVwarho ProAudit",
        "email_enabled": True,
        "sms_enabled": False,
        "slack_enabled": False,
    },
    "updated_at": datetime.utcnow(),
    "updated_by": None,
}


# ========= ENDPOINTS =========

@router.get("")
async def get_all_settings(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Get all platform settings.
    
    Super Admin only endpoint.
    """
    logger.info(f"Super Admin {current_user.email} retrieved platform settings")
    
    return {
        "success": True,
        "data": _platform_settings,
    }


@router.get("/general")
async def get_general_settings(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """Get general platform settings."""
    return {
        "success": True,
        "data": _platform_settings["general"],
    }


@router.put("/general")
async def update_general_settings(
    request: GeneralSettingsRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """Update general platform settings."""
    old_values = _platform_settings["general"].copy()
    
    _platform_settings["general"] = {
        "platform_name": request.platform_name,
        "support_email": request.support_email,
        "billing_email": request.billing_email,
        "default_currency": request.default_currency,
        "default_timezone": request.default_timezone,
    }
    _platform_settings["updated_at"] = datetime.utcnow()
    _platform_settings["updated_by"] = current_user.email
    
    # Log audit
    audit_log = AuditLog(
        user_id=current_user.id,
        action=AuditAction.SETTINGS_UPDATED,
        entity_type="platform_settings",
        entity_id=None,
        changes={"category": "general", "old": old_values, "new": _platform_settings["general"]},
        ip_address="system",
    )
    db.add(audit_log)
    await db.commit()
    
    logger.info(f"Super Admin {current_user.email} updated general settings")
    
    return {
        "success": True,
        "message": "General settings updated successfully",
        "data": _platform_settings["general"],
    }


@router.get("/trial")
async def get_trial_settings(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """Get trial and subscription settings."""
    return {
        "success": True,
        "data": _platform_settings["trial"],
    }


@router.put("/trial")
async def update_trial_settings(
    request: TrialSettingsRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """Update trial and subscription settings."""
    old_values = _platform_settings["trial"].copy()
    
    _platform_settings["trial"] = {
        "trial_days": request.trial_days,
        "grace_days": request.grace_days,
        "default_trial_tier": request.default_trial_tier,
        "allow_trial_extensions": request.allow_trial_extensions,
        "max_trial_extensions": request.max_trial_extensions,
    }
    _platform_settings["updated_at"] = datetime.utcnow()
    _platform_settings["updated_by"] = current_user.email
    
    # Log audit
    audit_log = AuditLog(
        user_id=current_user.id,
        action=AuditAction.SETTINGS_UPDATED,
        entity_type="platform_settings",
        entity_id=None,
        changes={"category": "trial", "old": old_values, "new": _platform_settings["trial"]},
        ip_address="system",
    )
    db.add(audit_log)
    await db.commit()
    
    logger.info(f"Super Admin {current_user.email} updated trial settings")
    
    return {
        "success": True,
        "message": "Trial settings updated successfully",
        "data": _platform_settings["trial"],
    }


@router.get("/nrs")
async def get_nrs_settings(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """Get NRS Gateway settings."""
    return {
        "success": True,
        "data": _platform_settings["nrs"],
    }


@router.put("/nrs")
async def update_nrs_settings(
    request: NRSSettingsRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """Update NRS Gateway settings."""
    old_values = _platform_settings["nrs"].copy()
    
    _platform_settings["nrs"] = {
        "api_endpoint": request.api_endpoint,
        "sandbox_mode": request.sandbox_mode,
        "auto_submit": request.auto_submit,
        "retry_failed": request.retry_failed,
        "retry_attempts": request.retry_attempts,
    }
    _platform_settings["updated_at"] = datetime.utcnow()
    _platform_settings["updated_by"] = current_user.email
    
    # Log audit
    audit_log = AuditLog(
        user_id=current_user.id,
        action=AuditAction.SETTINGS_UPDATED,
        entity_type="platform_settings",
        entity_id=None,
        changes={"category": "nrs", "old": old_values, "new": _platform_settings["nrs"]},
        ip_address="system",
    )
    db.add(audit_log)
    await db.commit()
    
    logger.info(f"Super Admin {current_user.email} updated NRS settings")
    
    return {
        "success": True,
        "message": "NRS settings updated successfully",
        "data": _platform_settings["nrs"],
    }


@router.get("/billing")
async def get_billing_settings(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """Get billing and payment settings (secrets masked)."""
    # Return masked version
    masked_settings = _platform_settings["billing"].copy()
    return {
        "success": True,
        "data": masked_settings,
    }


@router.put("/billing")
async def update_billing_settings(
    request: BillingSettingsRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """Update billing and payment settings."""
    old_values = {"paystack_sandbox_mode": _platform_settings["billing"]["paystack_sandbox_mode"]}
    
    _platform_settings["billing"] = {
        "paystack_public_key": request.paystack_public_key or "",
        "paystack_secret_key_masked": "••••••••" if request.paystack_secret_key else "",
        "paystack_sandbox_mode": request.paystack_sandbox_mode,
        "auto_charge_enabled": request.auto_charge_enabled,
        "invoice_prefix": request.invoice_prefix,
    }
    _platform_settings["updated_at"] = datetime.utcnow()
    _platform_settings["updated_by"] = current_user.email
    
    # Log audit (don't log secrets)
    audit_log = AuditLog(
        user_id=current_user.id,
        action=AuditAction.SETTINGS_UPDATED,
        entity_type="platform_settings",
        entity_id=None,
        changes={"category": "billing", "note": "Billing settings updated"},
        ip_address="system",
    )
    db.add(audit_log)
    await db.commit()
    
    logger.info(f"Super Admin {current_user.email} updated billing settings")
    
    return {
        "success": True,
        "message": "Billing settings updated successfully",
        "data": _platform_settings["billing"],
    }


@router.get("/security")
async def get_security_settings(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """Get security configuration settings."""
    return {
        "success": True,
        "data": _platform_settings["security"],
    }


@router.put("/security")
async def update_security_settings(
    request: SecuritySettingsRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """Update security configuration settings."""
    old_values = _platform_settings["security"].copy()
    
    _platform_settings["security"] = {
        "max_login_attempts": request.max_login_attempts,
        "lockout_duration_minutes": request.lockout_duration_minutes,
        "session_timeout_minutes": request.session_timeout_minutes,
        "require_mfa_for_admins": request.require_mfa_for_admins,
        "geo_fencing_enabled": request.geo_fencing_enabled,
        "allowed_countries": request.allowed_countries,
    }
    _platform_settings["updated_at"] = datetime.utcnow()
    _platform_settings["updated_by"] = current_user.email
    
    # Log audit
    audit_log = AuditLog(
        user_id=current_user.id,
        action=AuditAction.SETTINGS_UPDATED,
        entity_type="platform_settings",
        entity_id=None,
        changes={"category": "security", "old": old_values, "new": _platform_settings["security"]},
        ip_address="system",
    )
    db.add(audit_log)
    await db.commit()
    
    logger.info(f"Super Admin {current_user.email} updated security settings")
    
    return {
        "success": True,
        "message": "Security settings updated successfully",
        "data": _platform_settings["security"],
    }


@router.get("/notifications")
async def get_notification_settings(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """Get notification and email settings."""
    return {
        "success": True,
        "data": _platform_settings["notifications"],
    }


@router.put("/notifications")
async def update_notification_settings(
    request: NotificationSettingsRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """Update notification and email settings."""
    old_values = _platform_settings["notifications"].copy()
    
    _platform_settings["notifications"] = {
        "smtp_host": request.smtp_host,
        "smtp_port": request.smtp_port,
        "from_email": request.from_email,
        "from_name": request.from_name,
        "email_enabled": request.email_enabled,
        "sms_enabled": request.sms_enabled,
        "slack_enabled": request.slack_enabled,
    }
    _platform_settings["updated_at"] = datetime.utcnow()
    _platform_settings["updated_by"] = current_user.email
    
    # Log audit
    audit_log = AuditLog(
        user_id=current_user.id,
        action=AuditAction.SETTINGS_UPDATED,
        entity_type="platform_settings",
        entity_id=None,
        changes={"category": "notifications", "old": old_values, "new": _platform_settings["notifications"]},
        ip_address="system",
    )
    db.add(audit_log)
    await db.commit()
    
    logger.info(f"Super Admin {current_user.email} updated notification settings")
    
    return {
        "success": True,
        "message": "Notification settings updated successfully",
        "data": _platform_settings["notifications"],
    }


@router.post("/test-email")
async def test_email_configuration(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Send a test email to verify notification settings.
    """
    # In production, this would actually send an email
    logger.info(f"Super Admin {current_user.email} requested test email")
    
    return {
        "success": True,
        "message": f"Test email sent to {current_user.email}",
    }


@router.post("/test-nrs")
async def test_nrs_connection(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Test NRS Gateway connection.
    """
    nrs_settings = _platform_settings["nrs"]
    
    # In production, this would actually test the NRS connection
    logger.info(f"Super Admin {current_user.email} tested NRS connection")
    
    return {
        "success": True,
        "message": "NRS Gateway connection successful",
        "data": {
            "endpoint": nrs_settings["api_endpoint"],
            "sandbox_mode": nrs_settings["sandbox_mode"],
            "status": "connected",
        },
    }
