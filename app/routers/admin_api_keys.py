"""
Tekvwa Pro Audit - Platform API Keys Router

Super Admin endpoints for managing platform API keys.
Used for external integrations and partner access.
"""

import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import require_super_admin
from app.models.user import User
from app.models.audit_consolidated import AuditLog, AuditAction

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/api-keys",
    tags=["Admin - API Keys"],
)


# ========= SCHEMAS =========

class CreateAPIKeyRequest(BaseModel):
    """Request to create a new API key."""
    name: str = Field(..., min_length=3, max_length=100, description="Descriptive name for the key")
    description: Optional[str] = Field(None, max_length=500)
    scopes: List[str] = Field(default=["read"], description="API scopes/permissions")
    expires_in_days: Optional[int] = Field(None, ge=1, le=365, description="Days until expiry (null = never)")
    rate_limit_per_minute: int = Field(default=60, ge=1, le=1000)


class APIKeyResponse(BaseModel):
    """API key response (without full key after creation)."""
    id: str
    name: str
    description: Optional[str]
    masked_key: str
    scopes: List[str]
    is_active: bool
    created_at: datetime
    created_by: str
    expires_at: Optional[datetime]
    last_used: Optional[datetime]
    usage_count: int
    rate_limit_per_minute: int


class APIKeyCreatedResponse(BaseModel):
    """Response when creating an API key (includes full key ONCE)."""
    id: str
    name: str
    api_key: str  # Full key - shown only once
    masked_key: str
    scopes: List[str]
    expires_at: Optional[datetime]
    warning: str = "Save this key securely. It won't be shown again."


class UpdateAPIKeyRequest(BaseModel):
    """Request to update an API key."""
    name: Optional[str] = Field(None, min_length=3, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    scopes: Optional[List[str]] = None
    rate_limit_per_minute: Optional[int] = Field(None, ge=1, le=1000)


# ========= In-memory store =========

_api_keys: List[Dict[str, Any]] = [
    {
        "id": str(uuid4()),
        "name": "Production Integration",
        "description": "Main production API key for core services",
        "key_hash": "hashed_key_placeholder",
        "masked_key": "tvk_prod_****3a7f",
        "scopes": ["read", "write", "admin"],
        "is_active": True,
        "created_at": datetime.utcnow() - timedelta(days=90),
        "created_by": "info@tekvwa.org",
        "expires_at": None,
        "last_used": datetime.utcnow() - timedelta(hours=2),
        "usage_count": 15420,
        "rate_limit_per_minute": 100,
    },
    {
        "id": str(uuid4()),
        "name": "Partner Access",
        "description": "Limited read-only access for partner integrations",
        "key_hash": "hashed_key_placeholder",
        "masked_key": "tvk_part_****8b2c",
        "scopes": ["read"],
        "is_active": True,
        "created_at": datetime.utcnow() - timedelta(days=30),
        "created_by": "info@tekvwa.org",
        "expires_at": datetime.utcnow() + timedelta(days=335),
        "last_used": datetime.utcnow() - timedelta(days=5),
        "usage_count": 1203,
        "rate_limit_per_minute": 30,
    },
]


def _generate_api_key(prefix: str = "tvk") -> tuple:
    """Generate a secure API key and return (full_key, masked_key, hash)."""
    random_part = secrets.token_hex(24)
    full_key = f"{prefix}_{random_part}"
    masked_key = f"{prefix}_****{random_part[-4:]}"
    # In production, use proper hashing
    key_hash = f"hash_{secrets.token_hex(16)}"
    return full_key, masked_key, key_hash


# ========= ENDPOINTS =========

@router.get("")
async def list_api_keys(
    include_revoked: bool = Query(False),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    List all platform API keys.
    """
    keys = _api_keys.copy()
    
    if not include_revoked:
        keys = [k for k in keys if k["is_active"]]
    
    # Remove sensitive data
    safe_keys = []
    for key in keys:
        safe_key = {k: v for k, v in key.items() if k != "key_hash"}
        safe_keys.append(safe_key)
    
    return {
        "success": True,
        "data": {
            "keys": safe_keys,
            "total": len(safe_keys),
            "active_count": len([k for k in keys if k["is_active"]]),
        },
    }


@router.post("")
async def create_api_key(
    request: CreateAPIKeyRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Generate a new platform API key.
    
    WARNING: The full API key is only shown ONCE in the response.
    """
    # Generate key
    full_key, masked_key, key_hash = _generate_api_key()
    
    expires_at = None
    if request.expires_in_days:
        expires_at = datetime.utcnow() + timedelta(days=request.expires_in_days)
    
    new_key = {
        "id": str(uuid4()),
        "name": request.name,
        "description": request.description,
        "key_hash": key_hash,
        "masked_key": masked_key,
        "scopes": request.scopes,
        "is_active": True,
        "created_at": datetime.utcnow(),
        "created_by": current_user.email,
        "expires_at": expires_at,
        "last_used": None,
        "usage_count": 0,
        "rate_limit_per_minute": request.rate_limit_per_minute,
    }
    
    _api_keys.append(new_key)
    
    # Log audit
    audit_log = AuditLog(
        user_id=current_user.id,
        action=AuditAction.API_KEY_CREATED,
        entity_type="api_key",
        entity_id=None,
        changes={"name": request.name, "scopes": request.scopes},
        ip_address="system",
    )
    db.add(audit_log)
    await db.commit()
    
    logger.info(f"Super Admin {current_user.email} created API key '{request.name}'")
    
    return {
        "success": True,
        "data": {
            "id": new_key["id"],
            "name": new_key["name"],
            "api_key": full_key,
            "masked_key": masked_key,
            "scopes": new_key["scopes"],
            "expires_at": expires_at.isoformat() if expires_at else None,
            "warning": "Save this key securely. It won't be shown again.",
        },
    }


@router.get("/{key_id}")
async def get_api_key(
    key_id: str,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Get details of a specific API key.
    """
    key = next((k for k in _api_keys if k["id"] == key_id), None)
    
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    
    safe_key = {k: v for k, v in key.items() if k != "key_hash"}
    
    return {
        "success": True,
        "data": safe_key,
    }


@router.put("/{key_id}")
async def update_api_key(
    key_id: str,
    request: UpdateAPIKeyRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Update an API key's metadata (not the key itself).
    """
    key = next((k for k in _api_keys if k["id"] == key_id), None)
    
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    
    if not key["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot update a revoked API key",
        )
    
    old_values = {"name": key["name"], "scopes": key["scopes"]}
    
    if request.name:
        key["name"] = request.name
    if request.description is not None:
        key["description"] = request.description
    if request.scopes:
        key["scopes"] = request.scopes
    if request.rate_limit_per_minute:
        key["rate_limit_per_minute"] = request.rate_limit_per_minute
    
    # Log audit
    audit_log = AuditLog(
        user_id=current_user.id,
        action=AuditAction.API_KEY_UPDATED,
        entity_type="api_key",
        entity_id=None,
        changes={"key_id": key_id, "old": old_values, "new": {"name": key["name"], "scopes": key["scopes"]}},
        ip_address="system",
    )
    db.add(audit_log)
    await db.commit()
    
    logger.info(f"Super Admin {current_user.email} updated API key '{key['name']}'")
    
    safe_key = {k: v for k, v in key.items() if k != "key_hash"}
    
    return {
        "success": True,
        "message": "API key updated",
        "data": safe_key,
    }


@router.post("/{key_id}/revoke")
async def revoke_api_key(
    key_id: str,
    reason: Optional[str] = Query(None, max_length=500),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Revoke an API key (cannot be undone).
    """
    key = next((k for k in _api_keys if k["id"] == key_id), None)
    
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    
    if not key["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API key is already revoked",
        )
    
    key["is_active"] = False
    key["revoked_at"] = datetime.utcnow()
    key["revoked_by"] = current_user.email
    key["revoke_reason"] = reason
    
    # Log audit
    audit_log = AuditLog(
        user_id=current_user.id,
        action=AuditAction.API_KEY_REVOKED,
        entity_type="api_key",
        entity_id=None,
        changes={"key_id": key_id, "name": key["name"], "reason": reason},
        ip_address="system",
    )
    db.add(audit_log)
    await db.commit()
    
    logger.warning(f"Super Admin {current_user.email} revoked API key '{key['name']}'")
    
    return {
        "success": True,
        "message": "API key revoked",
    }


@router.post("/{key_id}/regenerate")
async def regenerate_api_key(
    key_id: str,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Regenerate an API key (creates new key, old one stops working immediately).
    """
    key = next((k for k in _api_keys if k["id"] == key_id), None)
    
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    
    if not key["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot regenerate a revoked API key",
        )
    
    # Generate new key
    full_key, masked_key, key_hash = _generate_api_key()
    
    key["key_hash"] = key_hash
    key["masked_key"] = masked_key
    key["usage_count"] = 0
    key["last_used"] = None
    
    # Log audit
    audit_log = AuditLog(
        user_id=current_user.id,
        action=AuditAction.API_KEY_REGENERATED,
        entity_type="api_key",
        entity_id=None,
        changes={"key_id": key_id, "name": key["name"]},
        ip_address="system",
    )
    db.add(audit_log)
    await db.commit()
    
    logger.info(f"Super Admin {current_user.email} regenerated API key '{key['name']}'")
    
    return {
        "success": True,
        "data": {
            "id": key["id"],
            "name": key["name"],
            "api_key": full_key,
            "masked_key": masked_key,
            "warning": "Save this key securely. It won't be shown again.",
        },
    }


@router.get("/{key_id}/usage")
async def get_api_key_usage(
    key_id: str,
    days: int = Query(30, ge=1, le=90),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Get usage statistics for an API key.
    """
    key = next((k for k in _api_keys if k["id"] == key_id), None)
    
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    
    # Generate mock usage data
    usage_data = []
    for i in range(days):
        date = datetime.utcnow() - timedelta(days=i)
        usage_data.append({
            "date": date.strftime("%Y-%m-%d"),
            "requests": key["usage_count"] // days + (i % 5) * 10,
            "errors": (i % 3),
        })
    
    return {
        "success": True,
        "data": {
            "key_id": key_id,
            "name": key["name"],
            "total_usage": key["usage_count"],
            "last_used": key["last_used"].isoformat() if key["last_used"] else None,
            "daily_usage": usage_data,
        },
    }


@router.get("/scopes/available")
async def list_available_scopes(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    List all available API scopes/permissions.
    """
    scopes = [
        {"name": "read", "description": "Read-only access to resources"},
        {"name": "write", "description": "Create and update resources"},
        {"name": "delete", "description": "Delete resources"},
        {"name": "admin", "description": "Administrative operations"},
        {"name": "users:read", "description": "Read user information"},
        {"name": "users:write", "description": "Create/update users"},
        {"name": "organizations:read", "description": "Read organization data"},
        {"name": "organizations:write", "description": "Manage organizations"},
        {"name": "transactions:read", "description": "Read financial transactions"},
        {"name": "transactions:write", "description": "Create transactions"},
        {"name": "reports:read", "description": "Generate and read reports"},
        {"name": "audit:read", "description": "Read audit logs"},
        {"name": "billing:read", "description": "Read billing information"},
        {"name": "billing:write", "description": "Manage billing"},
    ]
    
    return {
        "success": True,
        "data": scopes,
    }
