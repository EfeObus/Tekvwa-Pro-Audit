"""
Tekvwa Pro Audit - Upsell Opportunity Model

Tracks upsell and expansion opportunities for tenants.
Used by Super Admin to identify revenue growth potential.

Upsell Signals:
- Tier upgrade candidates (Core → Professional → Enterprise)
- Intelligence add-on candidates
- Feature adoption patterns suggesting upgrade need
- Usage approaching limits
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional, List
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, Numeric, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.user import User


class UpsellType(str, Enum):
    """Type of upsell opportunity."""
    TIER_UPGRADE = "tier_upgrade"              # Core → Professional → Enterprise
    INTELLIGENCE_ADDON = "intelligence_addon"  # Intelligence Add-on
    SEAT_EXPANSION = "seat_expansion"          # More user seats
    ENTITY_EXPANSION = "entity_expansion"      # More business entities
    STORAGE_UPGRADE = "storage_upgrade"        # Additional storage
    API_UPGRADE = "api_upgrade"                # Higher API limits
    SUPPORT_UPGRADE = "support_upgrade"        # Premium support
    TRAINING = "training"                      # Training/onboarding services


class UpsellStatus(str, Enum):
    """Status of the upsell opportunity."""
    IDENTIFIED = "identified"        # System detected opportunity
    QUALIFIED = "qualified"          # Staff verified opportunity
    CONTACTED = "contacted"          # Customer contacted
    PROPOSAL_SENT = "proposal_sent"  # Proposal/quote sent
    NEGOTIATING = "negotiating"      # In negotiation
    WON = "won"                      # Successfully converted
    LOST = "lost"                    # Opportunity lost
    DEFERRED = "deferred"            # Postponed for later
    NOT_INTERESTED = "not_interested"  # Customer declined


class UpsellPriority(str, Enum):
    """Priority of the opportunity."""
    HOT = "hot"           # High likelihood, high value
    WARM = "warm"         # Good potential
    COOL = "cool"         # Worth tracking
    COLD = "cold"         # Low priority


class UpsellSignal(str, Enum):
    """Signals that triggered the upsell opportunity."""
    USAGE_NEAR_LIMIT = "usage_near_limit"        # Approaching tier limits
    FEATURE_REQUEST = "feature_request"          # Requested premium feature
    HIGH_ENGAGEMENT = "high_engagement"          # Very active user
    GROWING_BUSINESS = "growing_business"        # Business growth indicators
    SUPPORT_INQUIRY = "support_inquiry"          # Asked about upgrade
    TRIAL_CONVERSION = "trial_conversion"        # Trial period ending
    COMPETITOR_MENTION = "competitor_mention"    # Mentioned competitors
    REFERRAL_ACTIVE = "referral_active"          # Referring other customers
    COMPLIANCE_NEED = "compliance_need"          # Needs compliance features
    ML_RECOMMENDATION = "ml_recommendation"      # ML model suggestion


class UpsellOpportunity(BaseModel):
    """
    Upsell opportunity tracking for revenue growth.
    """
    __tablename__ = "upsell_opportunities"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    # Opportunity identification
    opportunity_code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Unique code (e.g., UP-2026-0001)"
    )
    
    # Organization
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Opportunity details
    upsell_type: Mapped[UpsellType] = mapped_column(
        SQLEnum(UpsellType),
        nullable=False,
    )

    status: Mapped[UpsellStatus] = mapped_column(
        SQLEnum(UpsellStatus),
        nullable=False,
        default=UpsellStatus.IDENTIFIED,
        index=True,
    )

    priority: Mapped[UpsellPriority] = mapped_column(
        SQLEnum(UpsellPriority),
        nullable=False,
        default=UpsellPriority.WARM,
    )

    # Signal that triggered
    signal: Mapped[UpsellSignal] = mapped_column(
        SQLEnum(UpsellSignal),
        nullable=False,
    )

    # Current and target products (for tier upgrades)
    current_product: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    target_product: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    # Value
    estimated_mrr_increase: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2),
        nullable=True,
        comment="Estimated monthly revenue increase"
    )

    estimated_arr_increase: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2),
        nullable=True,
        comment="Estimated annual revenue increase"
    )

    actual_mrr_increase: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2),
        nullable=True,
        comment="Actual MRR increase once won"
    )

    actual_arr_increase: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2),
        nullable=True,
        comment="Actual ARR increase once won"
    )

    # Description
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Evidence
    signal_data: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Data that triggered the opportunity"
    )

    confidence_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="0-100 confidence in this opportunity"
    )

    auto_detected: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
    )

    # Timeline
    identified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Assignment
    assigned_to_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Outcome
    lost_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Next action
    next_action: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )

    next_action_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        back_populates="upsell_opportunities",
        lazy="selectin"
    )
    
    assigned_to: Mapped[Optional["User"]] = relationship(
        lazy="selectin"
    )
    
    def __repr__(self) -> str:
        return f"<UpsellOpportunity {self.opportunity_code}: {self.upsell_type.value} ({self.status.value})>"
    
    @property
    def is_open(self) -> bool:
        """Check if opportunity is still open."""
        return self.status in [
            UpsellStatus.IDENTIFIED, 
            UpsellStatus.QUALIFIED, 
            UpsellStatus.CONTACTED,
            UpsellStatus.PROPOSAL_SENT,
            UpsellStatus.NEGOTIATING
        ]
    

class UpsellActivity(BaseModel):
    """Activity log for upsell opportunities."""
    __tablename__ = "upsell_activities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    upsell_opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("upsell_opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    activity_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="call, email, meeting, note, status_change"
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    outcome: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    performed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    next_action: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )

    next_action_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    opportunity: Mapped["UpsellOpportunity"] = relationship(lazy="selectin")
    performed_by: Mapped[Optional["User"]] = relationship(lazy="selectin")
