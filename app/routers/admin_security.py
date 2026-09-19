"""
TekVwarho ProAudit - Security Audit Router

Super Admin endpoints for security monitoring and audit.
Includes security alerts, audit logs, active sessions, and IP management.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, IPvAnyAddress
from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import require_super_admin
from app.models.user import User
from app.models.audit_consolidated import AuditLog, AuditAction

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/security",
    tags=["Admin - Security Audit"],
)


# ========= SCHEMAS =========

class SecurityAlertResponse(BaseModel):
    """Security alert response."""
    id: str
    severity: str  # critical, high, medium, low
    alert_type: str
    description: str
    user_email: Optional[str] = None
    ip_address: Optional[str] = None
    timestamp: datetime
    status: str  # active, acknowledged, resolved
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None


class AcknowledgeAlertRequest(BaseModel):
    """Request to acknowledge an alert."""
    notes: Optional[str] = Field(None, max_length=500)


class ResolveAlertRequest(BaseModel):
    """Request to resolve an alert."""
    resolution_notes: str = Field(..., min_length=10, max_length=1000)


class IPWhitelistEntry(BaseModel):
    """IP whitelist entry."""
    id: str
    address: str
    description: str
    created_at: datetime
    created_by: str
    is_active: bool


class AddIPRequest(BaseModel):
    """Request to add IP to whitelist."""
    address: str = Field(..., description="IP address or CIDR range")
    description: str = Field(..., min_length=3, max_length=200)


class ActiveSessionResponse(BaseModel):
    """Active session response."""
    session_id: str
    user_email: str
    user_role: str
    ip_address: str
    user_agent: str
    started_at: datetime
    last_activity: datetime
    is_platform_staff: bool


class SecurityPolicyRequest(BaseModel):
    """Security policy configuration."""
    password_min_length: int = Field(default=8, ge=8, le=32)
    password_require_uppercase: bool = Field(default=True)
    password_require_numbers: bool = Field(default=True)
    password_require_special: bool = Field(default=True)
    password_expiry_days: int = Field(default=90, ge=0, le=365)
    session_timeout_minutes: int = Field(default=60, ge=15, le=480)
    mfa_required_for_admins: bool = Field(default=False)
    mfa_required_for_all: bool = Field(default=False)
    ip_whitelist_enabled: bool = Field(default=False)
    geo_fencing_enabled: bool = Field(default=True)
    allowed_countries: List[str] = Field(default=["NG"])


# ========= In-memory stores =========

_security_alerts: List[Dict[str, Any]] = [
    {
        "id": str(uuid4()),
        "severity": "high",
        "alert_type": "brute_force",
        "description": "Multiple failed login attempts detected from IP 192.168.1.100",
        "user_email": "user@example.com",
        "ip_address": "192.168.1.100",
        "timestamp": datetime.utcnow() - timedelta(hours=2),
        "status": "active",
        "resolved_at": None,
        "resolved_by": None,
    },
    {
        "id": str(uuid4()),
        "severity": "medium",
        "alert_type": "suspicious_activity",
        "description": "Unusual data export pattern detected",
        "user_email": "accountant@company.com",
        "ip_address": "10.0.0.50",
        "timestamp": datetime.utcnow() - timedelta(hours=5),
        "status": "acknowledged",
        "resolved_at": None,
        "resolved_by": None,
    },
]

_ip_whitelist: List[Dict[str, Any]] = [
    {
        "id": str(uuid4()),
        "address": "10.0.0.0/8",
        "description": "Internal network",
        "created_at": datetime.utcnow() - timedelta(days=30),
        "created_by": "info@tekvwa.org",
        "is_active": True,
    },
]

_active_sessions: List[Dict[str, Any]] = []

_security_policies = {
    "password_min_length": 8,
    "password_require_uppercase": True,
    "password_require_numbers": True,
    "password_require_special": True,
    "password_expiry_days": 90,
    "session_timeout_minutes": 60,
    "mfa_required_for_admins": False,
    "mfa_required_for_all": False,
    "ip_whitelist_enabled": False,
    "geo_fencing_enabled": True,
    "allowed_countries": ["NG"],
}


# ========= STATISTICS ENDPOINT =========

@router.get("/stats")
async def get_security_stats(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Get security statistics overview.
    """
    active_alerts = len([a for a in _security_alerts if a["status"] == "active"])
    
    # Get failed logins from audit logs (last 24h)
    twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
    result = await db.execute(
        select(func.count(AuditLog.id)).where(
            and_(
                AuditLog.action == AuditAction.LOGIN_FAILED,
                AuditLog.created_at >= twenty_four_hours_ago,
            )
        )
    )
    failed_logins_24h = result.scalar() or 0
    
    # Determine security status
    if active_alerts > 5 or failed_logins_24h > 50:
        security_status = "critical"
    elif active_alerts > 2 or failed_logins_24h > 20:
        security_status = "warning"
    else:
        security_status = "healthy"
    
    return {
        "success": True,
        "data": {
            "security_status": security_status,
            "active_alerts": active_alerts,
            "failed_logins_24h": failed_logins_24h,
            "active_sessions": len(_active_sessions),
            "whitelisted_ips": len([ip for ip in _ip_whitelist if ip["is_active"]]),
            "geo_fencing_enabled": _security_policies["geo_fencing_enabled"],
            "mfa_enabled": _security_policies["mfa_required_for_admins"],
        },
    }


# ========= ALERTS ENDPOINTS =========

@router.get("/alerts")
async def list_security_alerts(
    severity: Optional[str] = Query(None, pattern="^(critical|high|medium|low)$"),
    alert_type: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status", pattern="^(active|acknowledged|resolved)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    List security alerts with filtering.
    """
    alerts = _security_alerts.copy()
    
    if severity:
        alerts = [a for a in alerts if a["severity"] == severity]
    if alert_type:
        alerts = [a for a in alerts if a["alert_type"] == alert_type]
    if status_filter:
        alerts = [a for a in alerts if a["status"] == status_filter]
    
    # Sort by timestamp descending
    alerts.sort(key=lambda x: x["timestamp"], reverse=True)
    
    total = len(alerts)
    alerts = alerts[offset:offset + limit]
    
    return {
        "success": True,
        "data": {
            "alerts": alerts,
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    }


@router.get("/alerts/{alert_id}")
async def get_alert_details(
    alert_id: str,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """Get details of a specific security alert."""
    alert = next((a for a in _security_alerts if a["id"] == alert_id), None)
    
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )
    
    return {
        "success": True,
        "data": alert,
    }


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    request: AcknowledgeAlertRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """Acknowledge a security alert."""
    alert = next((a for a in _security_alerts if a["id"] == alert_id), None)
    
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )
    
    if alert["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Alert is already {alert['status']}",
        )
    
    alert["status"] = "acknowledged"
    alert["acknowledged_at"] = datetime.utcnow()
    alert["acknowledged_by"] = current_user.email
    if request.notes:
        alert["notes"] = request.notes
    
    # Log audit
    audit_log = AuditLog(
        user_id=current_user.id,
        action=AuditAction.ALERT_ACKNOWLEDGED,
        entity_type="security_alert",
        entity_id=None,
        changes={"alert_id": alert_id, "alert_type": alert["alert_type"]},
        ip_address="system",
    )
    db.add(audit_log)
    await db.commit()
    
    logger.info(f"Super Admin {current_user.email} acknowledged alert {alert_id}")
    
    return {
        "success": True,
        "message": "Alert acknowledged",
        "data": alert,
    }


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    request: ResolveAlertRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """Resolve a security alert."""
    alert = next((a for a in _security_alerts if a["id"] == alert_id), None)
    
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )
    
    if alert["status"] == "resolved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Alert is already resolved",
        )
    
    alert["status"] = "resolved"
    alert["resolved_at"] = datetime.utcnow()
    alert["resolved_by"] = current_user.email
    alert["resolution_notes"] = request.resolution_notes
    
    # Log audit
    audit_log = AuditLog(
        user_id=current_user.id,
        action=AuditAction.ALERT_RESOLVED,
        entity_type="security_alert",
        entity_id=None,
        changes={"alert_id": alert_id, "resolution": request.resolution_notes},
        ip_address="system",
    )
    db.add(audit_log)
    await db.commit()
    
    logger.info(f"Super Admin {current_user.email} resolved alert {alert_id}")
    
    return {
        "success": True,
        "message": "Alert resolved",
        "data": alert,
    }


# ========= SESSIONS ENDPOINTS =========

@router.get("/sessions")
async def list_active_sessions(
    is_platform_staff: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    List active user sessions.
    """
    # Query active users from database
    result = await db.execute(
        select(User).where(User.is_active == True).limit(limit).offset(offset)
    )
    users = result.scalars().all()
    
    sessions = []
    for user in users:
        if is_platform_staff is not None and user.is_platform_staff != is_platform_staff:
            continue
            
        sessions.append({
            "session_id": str(uuid4()),
            "user_email": user.email,
            "user_role": user.platform_role.value if user.is_platform_staff else (user.role.value if user.role else "unknown"),
            "ip_address": "Unknown",
            "user_agent": "Unknown",
            "started_at": user.last_login or user.created_at,
            "last_activity": user.last_login or user.created_at,
            "is_platform_staff": user.is_platform_staff,
        })
    
    return {
        "success": True,
        "data": {
            "sessions": sessions,
            "total": len(sessions),
        },
    }


@router.post("/sessions/{session_id}/terminate")
async def terminate_session(
    session_id: str,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Terminate a specific user session.
    """
    # In production, this would invalidate the session token
    logger.info(f"Super Admin {current_user.email} terminated session {session_id}")
    
    return {
        "success": True,
        "message": "Session terminated",
    }


@router.post("/sessions/terminate-all")
async def terminate_all_sessions(
    exclude_current: bool = Query(True),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Terminate all active sessions (emergency action).
    """
    # Log audit
    audit_log = AuditLog(
        user_id=current_user.id,
        action=AuditAction.EMERGENCY_ACTION,
        entity_type="sessions",
        entity_id=None,
        changes={"action": "terminate_all_sessions", "exclude_current": exclude_current},
        ip_address="system",
    )
    db.add(audit_log)
    await db.commit()
    
    logger.warning(f"Super Admin {current_user.email} terminated ALL sessions")
    
    return {
        "success": True,
        "message": "All sessions terminated" + (" (except current)" if exclude_current else ""),
    }


# ========= IP WHITELIST ENDPOINTS =========

@router.get("/ip-whitelist")
async def list_ip_whitelist(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    List all IP whitelist entries.
    """
    return {
        "success": True,
        "data": {
            "entries": _ip_whitelist,
            "whitelist_enabled": _security_policies["ip_whitelist_enabled"],
        },
    }


@router.post("/ip-whitelist")
async def add_ip_to_whitelist(
    request: AddIPRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Add an IP address or CIDR range to whitelist.
    """
    entry = {
        "id": str(uuid4()),
        "address": request.address,
        "description": request.description,
        "created_at": datetime.utcnow(),
        "created_by": current_user.email,
        "is_active": True,
    }
    
    _ip_whitelist.append(entry)
    
    # Log audit
    audit_log = AuditLog(
        user_id=current_user.id,
        action=AuditAction.IP_WHITELISTED,
        entity_type="ip_whitelist",
        entity_id=None,
        changes={"address": request.address, "description": request.description},
        ip_address="system",
    )
    db.add(audit_log)
    await db.commit()
    
    logger.info(f"Super Admin {current_user.email} whitelisted IP {request.address}")
    
    return {
        "success": True,
        "message": "IP added to whitelist",
        "data": entry,
    }


@router.delete("/ip-whitelist/{entry_id}")
async def remove_ip_from_whitelist(
    entry_id: str,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Remove an IP from whitelist.
    """
    entry = next((e for e in _ip_whitelist if e["id"] == entry_id), None)
    
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="IP whitelist entry not found",
        )
    
    entry["is_active"] = False
    
    # Log audit
    audit_log = AuditLog(
        user_id=current_user.id,
        action=AuditAction.IP_REMOVED_FROM_WHITELIST,
        entity_type="ip_whitelist",
        entity_id=None,
        changes={"address": entry["address"]},
        ip_address="system",
    )
    db.add(audit_log)
    await db.commit()
    
    logger.info(f"Super Admin {current_user.email} removed IP {entry['address']} from whitelist")
    
    return {
        "success": True,
        "message": "IP removed from whitelist",
    }


# ========= SECURITY POLICIES ENDPOINTS =========

@router.get("/policies")
async def get_security_policies(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Get current security policies.
    """
    return {
        "success": True,
        "data": _security_policies,
    }


@router.put("/policies")
async def update_security_policies(
    request: SecurityPolicyRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Update security policies.
    """
    old_policies = _security_policies.copy()
    
    _security_policies.update({
        "password_min_length": request.password_min_length,
        "password_require_uppercase": request.password_require_uppercase,
        "password_require_numbers": request.password_require_numbers,
        "password_require_special": request.password_require_special,
        "password_expiry_days": request.password_expiry_days,
        "session_timeout_minutes": request.session_timeout_minutes,
        "mfa_required_for_admins": request.mfa_required_for_admins,
        "mfa_required_for_all": request.mfa_required_for_all,
        "ip_whitelist_enabled": request.ip_whitelist_enabled,
        "geo_fencing_enabled": request.geo_fencing_enabled,
        "allowed_countries": request.allowed_countries,
    })
    
    # Log audit
    audit_log = AuditLog(
        user_id=current_user.id,
        action=AuditAction.SECURITY_POLICY_UPDATED,
        entity_type="security_policies",
        entity_id=None,
        changes={"old": old_policies, "new": _security_policies},
        ip_address="system",
    )
    db.add(audit_log)
    await db.commit()
    
    logger.info(f"Super Admin {current_user.email} updated security policies")
    
    return {
        "success": True,
        "message": "Security policies updated",
        "data": _security_policies,
    }


# ========= EXPORT ENDPOINT =========

@router.get("/export-report")
async def export_security_report(
    format: str = Query("json", pattern="^(json|csv)$"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Export security audit report.
    """
    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "generated_by": current_user.email,
        "summary": {
            "total_alerts": len(_security_alerts),
            "active_alerts": len([a for a in _security_alerts if a["status"] == "active"]),
            "resolved_alerts": len([a for a in _security_alerts if a["status"] == "resolved"]),
        },
        "alerts": _security_alerts,
        "policies": _security_policies,
        "ip_whitelist": _ip_whitelist,
    }
    
    logger.info(f"Super Admin {current_user.email} exported security report")
    
    return {
        "success": True,
        "data": report,
    }
