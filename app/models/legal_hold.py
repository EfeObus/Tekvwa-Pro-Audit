"""
Tekvwa Pro Audit - Legal Hold Model

Legal holds for compliance and data preservation.
Used when legal proceedings require data to be preserved and not deleted.

NTAA 2025 Compliance:
- Data retention requirements for tax investigations
- FIRS audit support
- Corporate governance compliance
"""

import uuid
from datetime import datetime, date
from enum import Enum
from typing import TYPE_CHECKING, Optional, List

from sqlalchemy import Boolean, DateTime, Date, ForeignKey, String, Text, Integer, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, AuditMixin

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.user import User


class LegalHoldStatus(str, Enum):
    """Status of a legal hold."""
    ACTIVE = "active"                 # Currently in effect
    PENDING_RELEASE = "pending_release"  # Awaiting legal approval to release
    RELEASED = "released"             # Hold has been lifted
    EXPIRED = "expired"               # Hold expired without action


class LegalHoldType(str, Enum):
    """Type of legal matter requiring the hold."""
    TAX_INVESTIGATION = "tax_investigation"    # FIRS/NRS investigation
    LITIGATION = "litigation"                   # Civil or criminal litigation
    REGULATORY_AUDIT = "regulatory_audit"       # Regulatory compliance audit
    INTERNAL_INVESTIGATION = "internal_investigation"  # Internal fraud investigation
    CORPORATE_GOVERNANCE = "corporate_governance"      # Board/shareholder matters
    DATA_SUBJECT_REQUEST = "data_subject_request"      # NDPA data subject access
    OTHER = "other"


class DataScope(str, Enum):
    """Scope of data under the legal hold."""
    ALL_DATA = "all_data"                  # All organization data
    FINANCIAL_RECORDS = "financial_records"  # Transactions, invoices, etc.
    TAX_FILINGS = "tax_filings"            # VAT, PAYE, CIT filings
    PAYROLL_RECORDS = "payroll_records"    # Employee and payroll data
    AUDIT_LOGS = "audit_logs"              # System audit trails
    COMMUNICATIONS = "communications"       # Emails, notifications
    SPECIFIC_ENTITIES = "specific_entities"  # Specific business entities only


class LegalHold(BaseModel, AuditMixin):
    """
    Legal hold to preserve data for legal or compliance requirements.
    
    Super Admin only - prevents data deletion and modification
    for specified tenants during legal proceedings.
    """
    __tablename__ = "legal_holds"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    # Hold identification
    hold_number: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Unique hold reference (e.g., LH-2026-0001)"
    )
    
    matter_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Name of legal matter or case"
    )
    
    matter_reference: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="External case/matter reference number"
    )
    
    # Organization under hold
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),  # Cannot delete org under hold
        nullable=False,
        index=True,
    )
    
    # Hold details
    hold_type: Mapped[LegalHoldType] = mapped_column(
        SQLEnum(LegalHoldType),
        nullable=False,
        default=LegalHoldType.TAX_INVESTIGATION,
    )
    
    status: Mapped[LegalHoldStatus] = mapped_column(
        SQLEnum(LegalHoldStatus),
        nullable=False,
        default=LegalHoldStatus.ACTIVE,
        index=True,
    )
    
    data_scope: Mapped[DataScope] = mapped_column(
        SQLEnum(DataScope),
        nullable=False,
        default=DataScope.ALL_DATA,
    )
    
    # Date range for preserved data
    preservation_start_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="Start date of data to preserve"
    )
    
    preservation_end_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
        comment="End date of data to preserve (null = ongoing)"
    )
    
    # Hold dates
    hold_start_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the hold was initiated"
    )
    
    hold_end_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the hold was released"
    )
    
    # Legal contact
    legal_counsel_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    
    legal_counsel_email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    
    legal_counsel_phone: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    
    # Hold description and notes
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Detailed description of the legal hold"
    )
    
    internal_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Internal notes (not visible to tenant)"
    )
    
    # Specific entities under hold (if data_scope = SPECIFIC_ENTITIES)
    entity_ids: Mapped[Optional[List[str]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="List of specific entity IDs under hold"
    )
    
    # Statistics
    records_preserved_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Estimated count of records preserved"
    )
    
    # Staff who created/released
    created_by_staff_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    
    released_by_staff_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    
    release_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Reason for releasing the hold"
    )
    
    # Relationships
    organization: Mapped["Organization"] = relationship(
        back_populates="legal_holds",
        lazy="selectin"
    )
    
    created_by_staff: Mapped["User"] = relationship(
        foreign_keys=[created_by_staff_id],
        lazy="selectin"
    )
    
    released_by_staff: Mapped[Optional["User"]] = relationship(
        foreign_keys=[released_by_staff_id],
        lazy="selectin"
    )
    
    def __repr__(self) -> str:
        return f"<LegalHold {self.hold_number}: {self.matter_name} ({self.status.value})>"
    
    @property
    def is_active(self) -> bool:
        """Check if the hold is currently active."""
        return self.status == LegalHoldStatus.ACTIVE
    
    @property
    def days_active(self) -> int:
        """Number of days the hold has been active."""
        end = self.hold_end_date or datetime.now(self.hold_start_date.tzinfo)
        return (end - self.hold_start_date).days


class LegalHoldNotification(BaseModel):
    """
    Notifications sent regarding legal holds.
    Tracks acknowledgments from organization users.
    """
    __tablename__ = "legal_hold_notifications"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    legal_hold_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("legal_holds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    
    notification_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Type: hold_initiated, reminder, release_pending, released"
    )
    
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Relationships
    legal_hold: Mapped["LegalHold"] = relationship(lazy="selectin")
    recipient: Mapped["User"] = relationship(lazy="selectin")
