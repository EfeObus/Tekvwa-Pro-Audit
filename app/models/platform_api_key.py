"""
Tekvwa Pro Audit - Platform API Key Model

Model for managing platform-level API keys for government gateways (NRS, JTB)
and external integrations. Only Super Admin can manage these keys.
"""

import uuid
import secrets
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum as SQLEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class ApiKeyType(str, Enum):
    """Type of API key."""
    NRS_GATEWAY = "nrs_gateway"  # Nigeria Revenue Service
    JTB_GATEWAY = "jtb_gateway"  # Joint Tax Board
    PAYSTACK = "paystack"
    FLUTTERWAVE = "flutterwave"
    SENDGRID = "sendgrid"
    CUSTOM = "custom"


class ApiKeyEnvironment(str, Enum):
    """Environment for API key."""
    SANDBOX = "sandbox"
    PRODUCTION = "production"


class PlatformApiKey(BaseModel):
    """
    Platform-level API keys for government gateways and integrations.
    
    These are managed by Super Admin only and are used platform-wide.
    """
    
    __tablename__ = "platform_api_keys"
    
    # Key identification
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    key_type: Mapped[ApiKeyType] = mapped_column(
        SQLEnum(ApiKeyType, name="apikeytype", create_type=False),
        nullable=False,
        default=ApiKeyType.CUSTOM
    )
    
    # Environment
    environment: Mapped[ApiKeyEnvironment] = mapped_column(
        SQLEnum(ApiKeyEnvironment, name="apikeyenvironment", create_type=False),
        nullable=False,
        default=ApiKeyEnvironment.SANDBOX
    )
    
    # API credentials (encrypted in production)
    api_key: Mapped[str] = mapped_column(String(512), nullable=False)  # The actual key
    api_secret: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)  # Optional secret
    client_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Masked key for display (e.g., "pk_live_****...****8a2c")
    masked_key: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Key hash for verification (SHA-256 hash of the full key)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    
    # Endpoint configuration
    api_endpoint: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    webhook_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # Connection tested
    
    # Usage tracking
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    usage_count: Mapped[int] = mapped_column(default=0, nullable=False)
    
    # Expiration
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Audit
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    revoked_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    @staticmethod
    def generate_key_hash(api_key: str) -> str:
        """Generate SHA-256 hash of the API key."""
        import hashlib
        return hashlib.sha256(api_key.encode()).hexdigest()
    
    @staticmethod
    def generate_masked_key(api_key: str) -> str:
        """Generate masked version of the API key for display."""
        if len(api_key) <= 8:
            return "****"
        return f"{api_key[:8]}****{api_key[-4:]}"
    
    @staticmethod
    def generate_platform_key() -> str:
        """Generate a new platform API key."""
        return f"tvp_{secrets.token_urlsafe(32)}"
    
    def revoke(self, revoked_by_id: uuid.UUID, reason: str = None):
        """Revoke this API key."""
        self.is_active = False
        self.revoked_by_id = revoked_by_id
        self.revoked_at = datetime.utcnow()
        self.revocation_reason = reason
    
    def record_usage(self):
        """Record that this key was used."""
        self.last_used_at = datetime.utcnow()
        self.usage_count += 1
    
    def is_expired(self) -> bool:
        """Check if the key has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at
    
    def is_valid(self) -> bool:
        """Check if the key is valid for use."""
        return self.is_active and not self.is_expired()
    
    def __repr__(self) -> str:
        return f"<PlatformApiKey {self.name} ({self.key_type.value})>"
