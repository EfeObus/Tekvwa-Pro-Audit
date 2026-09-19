"""
Tekvwa Pro Audit - Emergency Control Models

Models for platform emergency controls including:
- Kill switches (platform-wide and feature-specific)
- Emergency tenant suspensions
- Read-only mode
- Maintenance mode

These are CRITICAL security features for Super Admin only.
"""

import uuid
from datetime import datetime
from typing import Optional, List
from enum import Enum

from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class EmergencyActionType(str, Enum):
    """Types of emergency actions."""
    READ_ONLY_MODE = "read_only_mode"               # Platform-wide read-only
    MAINTENANCE_MODE = "maintenance_mode"           # Full maintenance mode
    FEATURE_KILL_SWITCH = "feature_kill_switch"     # Disable specific feature
    TENANT_EMERGENCY_SUSPEND = "tenant_emergency_suspend"  # Emergency tenant suspension
    USER_EMERGENCY_SUSPEND = "user_emergency_suspend"      # Emergency user suspension
    API_RATE_LIMIT_OVERRIDE = "api_rate_limit_override"    # Emergency rate limiting
    LOGIN_LOCKDOWN = "login_lockdown"               # Disable all non-admin logins


class FeatureKey(str, Enum):
    """Platform features that can be disabled via kill switch."""
    # Core financial features
    TRANSACTIONS = "transactions"
    PAYMENTS = "payments"
    INVOICING = "invoicing"
    PAYROLL = "payroll"
    REPORTS = "reports"
    
    # Tax & Compliance
    TAX_FILING = "tax_filing"
    NRS_SUBMISSION = "nrs_submission"
    AUDIT_LOGS = "audit_logs"
    AUDIT_REPORTS = "audit_reports"
    
    # Banking features
    BANK_RECONCILIATION = "bank_reconciliation"
    EXPENSE_CLAIMS = "expense_claims"
    
    # User & Access features
    USER_REGISTRATION = "user_registration"
    USER_SIGNUP = "user_signup"
    API_ACCESS = "api_access"
    
    # Operations
    BULK_OPERATIONS = "bulk_operations"
    EXPORTS = "exports"
    FILE_UPLOADS = "file_uploads"
    INTEGRATIONS = "integrations"
    
    # AI/ML features
    ML_PROCESSING = "ml_processing"
    ML_INFERENCE = "ml_inference"
    
    # Other
    NOTIFICATIONS = "notifications"


class EmergencyControl(BaseModel):
    """
    Emergency Control Model.
    
    Tracks all emergency control actions including kill switches,
    read-only mode, and emergency suspensions.
    
    Retention: 7 years per Nigerian compliance requirements.
    """
    
    __tablename__ = "emergency_controls"
    
    # Action identification
    action_type: Mapped[EmergencyActionType] = mapped_column(
        SQLEnum(EmergencyActionType, name="emergency_action_type"),
        nullable=False,
        index=True,
    )
    
    # Target of the action (feature key, tenant id, user id, etc.)
    target_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Type of target: 'platform', 'feature', 'tenant', 'user'",
    )
    target_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="ID of the target (feature key, tenant UUID, user UUID)",
    )
    
    # Who initiated this action
    initiated_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
    )
    
    # Reason is REQUIRED for all emergency actions
    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Mandatory reason for the emergency action",
    )
    
    # Timing
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Who ended the action (if applicable)
    ended_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    end_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Reason for ending the emergency action",
    )
    
    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )
    
    # Additional metadata
    affected_count: Mapped[Optional[int]] = mapped_column(
        nullable=True,
        comment="Number of users/tenants affected",
    )
    action_metadata: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Additional action metadata",
    )
    
    # Relationships
    initiated_by = relationship(
        "User",
        foreign_keys=[initiated_by_id],
        backref="emergency_controls_initiated",
    )
    ended_by = relationship(
        "User",
        foreign_keys=[ended_by_id],
        backref="emergency_controls_ended",
    )
    
    def __repr__(self) -> str:
        return f"<EmergencyControl({self.action_type.value}, target={self.target_type}:{self.target_id}, active={self.is_active})>"


class PlatformStatus(BaseModel):
    """
    Platform Status Model.
    
    Single-row table tracking current platform operational status.
    Used for quick lookups without scanning emergency_controls.
    """
    
    __tablename__ = "platform_status"
    
    # Global status flags
    is_read_only: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Platform in read-only mode",
    )
    is_maintenance_mode: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Platform in maintenance mode",
    )
    is_login_locked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Non-admin logins disabled",
    )
    
    # Maintenance message
    maintenance_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Message to show users during maintenance",
    )
    maintenance_expected_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Disabled features (array of feature keys)
    disabled_features: Mapped[Optional[List[str]]] = mapped_column(
        JSONB,
        default=list,
        nullable=True,
        comment="List of disabled feature keys",
    )
    
    # Last status change tracking
    last_changed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_changed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Relationships
    last_changed_by = relationship("User", backref="platform_status_changes")
    
    def __repr__(self) -> str:
        status = []
        if self.is_read_only:
            status.append("READ_ONLY")
        if self.is_maintenance_mode:
            status.append("MAINTENANCE")
        if self.is_login_locked:
            status.append("LOGIN_LOCKED")
        return f"<PlatformStatus({', '.join(status) or 'NORMAL'})>"
    
    def is_feature_disabled(self, feature_key: str) -> bool:
        """Check if a specific feature is disabled."""
        if not self.disabled_features:
            return False
        return feature_key in self.disabled_features
