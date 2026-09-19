"""
Tekvwa Pro Audit - Notification Model

Model for storing user notifications.

Notification Types:
- Tax deadline reminders
- Low stock alerts
- Invoice status updates
- Compliance warnings
- System announcements
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.entity import BusinessEntity


class NotificationType(str, Enum):
    """Types of notifications."""
    # Tax & Compliance
    TAX_DEADLINE = "tax_deadline"
    VAT_REMINDER = "vat_reminder"
    PAYE_REMINDER = "paye_reminder"
    WHT_REMINDER = "wht_reminder"
    CIT_REMINDER = "cit_reminder"
    COMPLIANCE_WARNING = "compliance_warning"
    
    # Invoice
    INVOICE_CREATED = "invoice_created"
    INVOICE_SENT = "invoice_sent"
    INVOICE_PAID = "invoice_paid"
    INVOICE_OVERDUE = "invoice_overdue"
    INVOICE_DISPUTED = "invoice_disputed"
    NRS_SUBMISSION_SUCCESS = "nrs_submission_success"
    NRS_SUBMISSION_FAILED = "nrs_submission_failed"
    
    # Inventory
    LOW_STOCK_ALERT = "low_stock_alert"
    STOCK_WRITE_OFF = "stock_write_off"
    
    # System
    SYSTEM_ANNOUNCEMENT = "system_announcement"
    SECURITY_ALERT = "security_alert"
    
    # General
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"


class NotificationPriority(str, Enum):
    """Priority levels for notifications."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationChannel(str, Enum):
    """Delivery channels for notifications."""
    IN_APP = "in_app"
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"


class Notification(BaseModel):
    """
    Notification model for storing user notifications.
    
    Supports multiple delivery channels and priority levels.
    """
    
    __tablename__ = "notifications"
    
    # Recipient
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Optional entity association
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    
    # Notification content
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Type and priority
    notification_type: Mapped[NotificationType] = mapped_column(
        SQLEnum(NotificationType),
        default=NotificationType.INFO,
        nullable=False,
        index=True,
    )
    priority: Mapped[NotificationPriority] = mapped_column(
        SQLEnum(NotificationPriority),
        default=NotificationPriority.NORMAL,
        nullable=False,
    )
    
    # Delivery channels (can have multiple)
    channels: Mapped[list] = mapped_column(
        JSONB,
        default=["in_app"],
        nullable=False,
        comment="List of delivery channels",
    )
    
    # Status tracking
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )
    read_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Email delivery status
    email_sent: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    email_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Action link (optional)
    action_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="URL for notification action button",
    )
    action_label: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Label for action button",
    )
    
    # Additional data (JSON)
    extra_data: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Additional notification data",
    )
    
    # Expiry
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Notification expiry time",
    )
    
    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="notifications",
    )
    entity: Mapped[Optional["BusinessEntity"]] = relationship(
        "BusinessEntity",
        back_populates="notifications",
    )
    
    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, type={self.notification_type}, user={self.user_id})>"
    
    def mark_as_read(self) -> None:
        """Mark notification as read."""
        if not self.is_read:
            self.is_read = True
            self.read_at = datetime.utcnow()
    
    def mark_email_sent(self) -> None:
        """Mark email as sent."""
        if not self.email_sent:
            self.email_sent = True
            self.email_sent_at = datetime.utcnow()
    
    @property
    def is_expired(self) -> bool:
        """Check if notification has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at
