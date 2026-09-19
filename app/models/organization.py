"""
Tekvwa Pro Audit - Organization Model

Organization model for multi-tenancy support.

Organization Types:
- SME: Small and Medium Enterprises
- Small Business: Micro businesses
- School: Educational institutions
- Non-Profit: NGOs and charitable organizations
- Individual: Solo practitioners/freelancers

Verification Status:
- Pending: Awaiting document upload
- Submitted: Documents uploaded, awaiting review
- Verified: Documents approved by Admin
- Rejected: Documents rejected, needs resubmission
"""

from enum import Enum
from typing import TYPE_CHECKING, List, Optional
from datetime import datetime

import uuid

from sqlalchemy import Boolean, String, Text, Enum as SQLEnum, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.entity import BusinessEntity
    from app.models.sku import TenantSKU, UsageRecord
    from app.models.legal_hold import LegalHold
    from app.models.risk_signal import RiskSignal
    from app.models.upsell import UpsellOpportunity
    from app.models.support_ticket import SupportTicket


class SubscriptionTier(str, Enum):
    """
    DEPRECATED: Legacy subscription tiers for organizations.
    
    This enum is kept for backwards compatibility with existing database data.
    New code should use the TenantSKU model and SKUTier enum from app.models.sku
    for commercial feature gating.
    
    Migration Path:
    - FREE -> SKUTier.CORE (trial)
    - STARTER -> SKUTier.CORE
    - PROFESSIONAL -> SKUTier.PROFESSIONAL
    - ENTERPRISE -> SKUTier.ENTERPRISE
    """
    FREE = "free"           # Maps to CORE (trial)
    STARTER = "starter"     # Maps to CORE
    PROFESSIONAL = "professional"  # Maps to PROFESSIONAL
    ENTERPRISE = "enterprise"      # Maps to ENTERPRISE


class OrganizationType(str, Enum):
    """
    Organization types for differentiated features and compliance.
    Each type may have different tax obligations and reporting requirements.
    """
    SME = "sme"                       # Small and Medium Enterprises
    SMALL_BUSINESS = "small_business" # Micro businesses
    SCHOOL = "school"                 # Educational institutions
    NON_PROFIT = "non_profit"         # NGOs and charitable organizations  
    INDIVIDUAL = "individual"         # Solo practitioners/freelancers
    CORPORATION = "corporation"       # Large corporations


class VerificationStatus(str, Enum):
    """Verification status for organization documents."""
    PENDING = "pending"       # Awaiting document upload
    SUBMITTED = "submitted"   # Documents uploaded, awaiting review
    UNDER_REVIEW = "under_review"  # Currently being reviewed by admin
    VERIFIED = "verified"     # Documents approved by Admin
    REJECTED = "rejected"     # Documents rejected, needs resubmission


class Organization(BaseModel):
    """
    Organization model - top-level tenant.
    
    An organization can have multiple business entities and users.
    Organizations must be verified by platform admins before accessing
    full platform features.
    """
    
    __tablename__ = "organizations"
    
    # Basic Info
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )
    
    # Organization Type
    organization_type: Mapped[OrganizationType] = mapped_column(
        SQLEnum(OrganizationType, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        default=OrganizationType.SMALL_BUSINESS,
        nullable=False,
        comment="Type of organization for compliance and feature differentiation"
    )
    
    # Contact
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # Subscription
    subscription_tier: Mapped[SubscriptionTier] = mapped_column(
        SQLEnum(SubscriptionTier),
        default=SubscriptionTier.FREE,
        nullable=False,
    )
    
    # ===========================================
    # VERIFICATION FIELDS (For Admin Approval)
    # ===========================================
    
    verification_status: Mapped[VerificationStatus] = mapped_column(
        SQLEnum(VerificationStatus, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        default=VerificationStatus.PENDING,
        nullable=False,
        comment="Document verification status"
    )
    
    # Verification Documents Paths
    cac_document_path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Path to CAC registration document"
    )
    tin_document_path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Path to TIN certificate document"
    )
    additional_documents: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="JSON array of additional document paths"
    )
    
    # Verification Review
    verification_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Notes from admin during verification review"
    )
    verified_by_id: Mapped[Optional[str]] = mapped_column(
        String(36),  # UUID as string for flexibility
        nullable=True,
        comment="ID of admin who verified the organization"
    )
    
    # Referral Engine
    referral_code: Mapped[Optional[str]] = mapped_column(
        String(20),
        unique=True,
        nullable=True,
        index=True,
        comment="Unique referral code for marketing campaigns"
    )
    referred_by_code: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Referral code of the organization that referred this one"
    )
    
    # ===========================================
    # EMERGENCY SUSPENSION FIELDS (Super Admin)
    # ===========================================
    is_emergency_suspended: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Whether this organization is emergency suspended"
    )
    emergency_suspended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the organization was emergency suspended"
    )
    emergency_suspended_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="ID of admin who emergency suspended this organization"
    )
    emergency_suspension_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Reason for emergency suspension"
    )
    
    # Relationships
    users: Mapped[List["User"]] = relationship(
        "User",
        back_populates="organization",
        cascade="all, delete-orphan",
        foreign_keys="User.organization_id",
    )
    entities: Mapped[List["BusinessEntity"]] = relationship(
        "BusinessEntity",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    
    # SKU relationship (Commercial tier management)
    tenant_sku: Mapped[Optional["TenantSKU"]] = relationship(
        "TenantSKU",
        back_populates="organization",
        uselist=False,
        cascade="all, delete-orphan",
    )
    
    # Usage records relationship
    usage_records: Mapped[List["UsageRecord"]] = relationship(
        "UsageRecord",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    
    # Legal holds (Super Admin compliance feature)
    legal_holds: Mapped[List["LegalHold"]] = relationship(
        "LegalHold",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    
    # Risk signals (Platform monitoring)
    risk_signals: Mapped[List["RiskSignal"]] = relationship(
        "RiskSignal",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    
    # Upsell opportunities (Revenue growth tracking)
    upsell_opportunities: Mapped[List["UpsellOpportunity"]] = relationship(
        "UpsellOpportunity",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    
    # Support tickets
    support_tickets: Mapped[List["SupportTicket"]] = relationship(
        "SupportTicket",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    
    @property
    def is_verified(self) -> bool:
        """Check if organization is verified."""
        return self.verification_status == VerificationStatus.VERIFIED
    
    @property
    def requires_verification(self) -> bool:
        """Check if organization requires verification."""
        return self.verification_status in [
            VerificationStatus.PENDING, 
            VerificationStatus.REJECTED
        ]
    
    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, name={self.name}, type={self.organization_type})>"
