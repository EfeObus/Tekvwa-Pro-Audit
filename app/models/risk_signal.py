"""
Tekvwa Pro Audit - Risk Signal Model

Risk signals for platform monitoring and early warning system.
Tracks various risk indicators across tenants for proactive intervention.

Risk Categories:
- Financial Risk: Payment issues, unusual transactions
- Compliance Risk: Missed filings, audit findings
- Security Risk: Suspicious login patterns, data access
- Operational Risk: System errors, failed integrations
- Churn Risk: Declining usage, support issues
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional, List

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.user import User


class RiskSeverity(str, Enum):
    """Severity level of the risk signal."""
    CRITICAL = "critical"    # Immediate action required
    HIGH = "high"            # Urgent attention needed
    MEDIUM = "medium"        # Should be addressed soon
    LOW = "low"              # Monitor and track
    INFO = "info"            # Informational only


class RiskCategory(str, Enum):
    """Category of risk signal."""
    FINANCIAL = "financial"           # Payment/revenue related
    COMPLIANCE = "compliance"         # Regulatory compliance
    SECURITY = "security"             # Security threats
    OPERATIONAL = "operational"       # System/integration issues
    CHURN = "churn"                   # Customer retention risk
    FRAUD = "fraud"                   # Potential fraud indicators
    DATA_QUALITY = "data_quality"     # Data integrity issues
    REPUTATIONAL = "reputational"     # Brand/reputation risk
    PERFORMANCE = "performance"       # Platform performance risk


class RiskStatus(str, Enum):
    """Status of the risk signal."""
    OPEN = "open"                     # Newly detected, unassigned
    ACKNOWLEDGED = "acknowledged"     # Staff aware, investigating
    IN_PROGRESS = "in_progress"       # Being actively resolved
    RESOLVED = "resolved"             # Issue resolved
    ESCALATED = "escalated"           # Escalated to higher level
    FALSE_POSITIVE = "false_positive" # Determined to not be a risk
    MONITORING = "monitoring"         # Watching but no action needed


class RiskSignalType(str, Enum):
    """Specific types of risk signals."""
    # Financial Risks
    PAYMENT_FAILED = "payment_failed"
    PAYMENT_OVERDUE = "payment_overdue"
    UNUSUAL_TRANSACTION_VOLUME = "unusual_transaction_volume"
    REVENUE_DECLINE = "revenue_decline"
    
    # Compliance Risks
    MISSED_VAT_FILING = "missed_vat_filing"
    MISSED_PAYE_FILING = "missed_paye_filing"
    NRS_SUBMISSION_REJECTED = "nrs_submission_rejected"
    AUDIT_FINDING_UNRESOLVED = "audit_finding_unresolved"
    
    # Security Risks
    SUSPICIOUS_LOGIN = "suspicious_login"
    BRUTE_FORCE_ATTEMPT = "brute_force_attempt"
    UNUSUAL_DATA_ACCESS = "unusual_data_access"
    PERMISSION_ESCALATION = "permission_escalation"
    
    # Operational Risks
    API_INTEGRATION_FAILURE = "api_integration_failure"
    DATA_SYNC_ERROR = "data_sync_error"
    SYSTEM_ERROR_SPIKE = "system_error_spike"
    
    # Churn Risks
    USAGE_DECLINE = "usage_decline"
    SUPPORT_TICKET_SPIKE = "support_ticket_spike"
    FEATURE_ADOPTION_LOW = "feature_adoption_low"
    CONTRACT_EXPIRY_APPROACHING = "contract_expiry_approaching"
    
    # Fraud Risks
    ANOMALY_DETECTED = "anomaly_detected"
    DUPLICATE_INVOICE = "duplicate_invoice"
    UNUSUAL_VENDOR_ACTIVITY = "unusual_vendor_activity"
    
    # Data Quality
    MISSING_REQUIRED_DATA = "missing_required_data"
    DATA_VALIDATION_FAILURE = "data_validation_failure"


class RiskSignal(BaseModel):
    """
    Risk signal for platform monitoring.
    
    Used by Super Admin and Admin to track and respond to
    potential issues across the platform.
    """
    __tablename__ = "risk_signals"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    # Signal identification
    signal_code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Unique signal reference (e.g., RS-2026-0001)"
    )
    
    # Organization affected (optional - some signals are platform-wide)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    
    # Signal classification -- plain String, not native Postgres enums. Same
    # "converted for flexibility" pattern already documented in app/models/sku.py.
    signal_type: Mapped[RiskSignalType] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    category: Mapped[RiskCategory] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    severity: Mapped[RiskSeverity] = mapped_column(
        String(20),
        nullable=False,
        default=RiskSeverity.MEDIUM,
        index=True,
    )

    status: Mapped[RiskStatus] = mapped_column(
        String(20),
        nullable=False,
        default=RiskStatus.OPEN,
        index=True,
    )

    # Signal details
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Risk scoring
    risk_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Risk score 0-100, higher = more severe"
    )

    confidence_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="ML confidence in the signal 0.0-1.0"
    )

    auto_detected: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
    )

    # Detection details
    detected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )

    detected_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    ml_model_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="No FK constraint on the live table",
    )

    # Evidence and context
    evidence: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="JSON data supporting the signal"
    )

    recommended_actions: Mapped[Optional[List[str]]] = mapped_column(
        JSONB,
        nullable=True,
    )

    requires_immediate_action: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
    )

    # Acknowledgement
    acknowledged: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
    )

    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )

    acknowledged_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Assignment and resolution
    assigned_to_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )

    resolved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    resolution_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships
    organization: Mapped[Optional["Organization"]] = relationship(
        back_populates="risk_signals",
        lazy="selectin"
    )

    detected_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[detected_by_id],
        lazy="selectin"
    )

    acknowledged_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[acknowledged_by_id],
        lazy="selectin"
    )

    assigned_to: Mapped[Optional["User"]] = relationship(
        foreign_keys=[assigned_to_id],
        lazy="selectin"
    )

    resolved_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[resolved_by_id],
        lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<RiskSignal {self.signal_code}: {self.signal_type} ({self.severity})>"
    
    @property
    def is_open(self) -> bool:
        """Check if signal is still open."""
        return self.status in [RiskStatus.OPEN, RiskStatus.ACKNOWLEDGED, RiskStatus.IN_PROGRESS]
    
    @property
    def requires_action(self) -> bool:
        """Check if signal requires immediate action."""
        return self.is_open and self.severity in [RiskSeverity.CRITICAL, RiskSeverity.HIGH]


class RiskSignalComment(BaseModel):
    """Comments/notes on risk signals for tracking investigation progress."""
    __tablename__ = "risk_signal_comments"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    risk_signal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("risk_signals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    staff_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    comment: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Relationships
    risk_signal: Mapped["RiskSignal"] = relationship(lazy="selectin")
    staff: Mapped[Optional["User"]] = relationship(lazy="selectin")
