"""
Tekvwa Pro Audit - Base Model

Base model class and mixins for all SQLAlchemy models.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TimestampMixin:
    """Mixin that adds created_at and updated_at timestamps."""
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AuditMixin:
    """Mixin that adds audit fields for tracking who created/updated records."""
    
    # NOTE: deliberately no ForeignKey('users.id') here. This mixin is shared by 16 models, but
    # only 7 of their tables actually have a matching FK constraint in the live migrated database
    # (see docs/REMEDIATION_LOG.md, Finding 49) — a migration was written for those 7 specifically,
    # never for the other 9. Adding the FK here would tell the ORM every subclass has a constraint
    # that most of them don't, which breaks schema-creation/teardown tooling that trusts this
    # metadata (confirmed: caused new failures when tried). The 7 that do have it override these
    # columns individually with an explicit ForeignKey — see ChartOfAccounts, JournalEntry,
    # RecurringJournalEntry, Employee, PayrollRun, StatutoryRemittance, EmployeeLoan.
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    updated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )


class BaseModel(Base, TimestampMixin):
    """
    Abstract base model with UUID primary key and timestamps.
    All models should inherit from this class.
    """
    
    __abstract__ = True
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(id={self.id})>"
