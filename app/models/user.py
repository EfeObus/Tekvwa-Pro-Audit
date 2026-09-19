"""
TekVwarho ProAudit - User Model

User model with role-based access control.

RBAC Hierarchy:
1. Platform Staff (Internal TekVwarho employees):
   - Super Admin: Full root access, hardcoded credentials
   - Admin: Operational access, approves verification documents
   - IT/Developer: Backend and infrastructure access
   - Customer Service (CSR): View-only or impersonation access
   - Marketing: Analytics and communication dashboards

2. Organization Users (External customers):
   - Owner: Full access to their organization
   - Admin: Administrative access within organization
   - Accountant: Financial data access (internal)
   - External Accountant: External firm access (filing + reports only)
   - Auditor: Read-only access
   - Payroll Manager: Payroll access
   - Inventory Manager: Inventory access
   - Viewer: Limited read-only

NTAA 2025 Compliance Features:
- Time-limited CSR impersonation (24-hour tokens per NDPA)
- Maker-Checker SoD for WREN expense verification
- External Accountant role for outsourced accounting firms
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.entity import BusinessEntity
    from app.models.notification import Notification


# ===========================================
# PLATFORM STAFF ROLES (Internal TekVwarho Employees)
# ===========================================

class PlatformRole(str, Enum):
    """
    Platform-level roles for TekVwarho internal staff.
    These users manage the multi-tenant platform.
    """
    SUPER_ADMIN = "super_admin"      # Full root access to entire platform
    ADMIN = "admin"                   # High-level operational access
    IT_DEVELOPER = "it_developer"     # Backend and infrastructure access
    CUSTOMER_SERVICE = "customer_service"  # View-only or impersonation access
    MARKETING = "marketing"           # Analytics and communication dashboards


# ===========================================
# ORGANIZATION USER ROLES (External Customers)
# ===========================================

class UserRole(str, Enum):
    """
    User roles for organization-level RBAC.
    
    NTAA 2025 Updates:
    - Added EXTERNAL_ACCOUNTANT for outsourced accounting firms
    """
    OWNER = "owner"                        # Full access to organization
    ADMIN = "admin"                        # Administrative access
    ACCOUNTANT = "accountant"              # Financial data access (internal)
    EXTERNAL_ACCOUNTANT = "external_accountant"  # External firm access (like QuickBooks "Invite Accountant")
    AUDITOR = "auditor"                    # Read-only access
    PAYROLL_MANAGER = "payroll_manager"    # Payroll access
    INVENTORY_MANAGER = "inventory_manager"  # Inventory access
    VIEWER = "viewer"                      # Limited read-only


class User(BaseModel):
    """
    User model for authentication and authorization.
    
    Users can be either:
    1. Platform Staff: Internal TekVwarho employees (is_platform_staff=True)
    2. Organization Users: External customers (is_platform_staff=False)
    
    Platform staff have platform_role set and organization_id is NULL.
    Organization users have role set and belong to an organization.
    """
    
    __tablename__ = "users"
    
    # Basic Info
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # Organization (NULL for platform staff)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,  # Changed to True for platform staff
    )
    
    # ===========================================
    # RBAC FIELDS
    # ===========================================
    
    # Organization-level role (for external customers)
    role: Mapped[Optional[UserRole]] = mapped_column(
        SQLEnum(UserRole),
        default=UserRole.VIEWER,
        nullable=True,  # NULL for platform staff
    )
    
    # Platform staff flag and role
    is_platform_staff: Mapped[bool] = mapped_column(
        Boolean, 
        default=False, 
        nullable=False,
        index=True,
        comment="True for internal TekVwarho employees"
    )
    platform_role: Mapped[Optional[PlatformRole]] = mapped_column(
        SQLEnum(PlatformRole, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=True,  # NULL for organization users
        comment="Role for platform staff only"
    )
    
    # Staff onboarding info
    onboarded_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="ID of user who onboarded this staff member"
    )
    staff_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Internal notes about staff member"
    )
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    must_reset_password: Mapped[bool] = mapped_column(
        Boolean, 
        default=False, 
        nullable=False,
        comment="Force password reset on next login (for newly onboarded staff)"
    )
    
    # Email Verification
    email_verification_token: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Token for email verification"
    )
    email_verification_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When verification email was last sent"
    )
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When email was verified"
    )
    is_invited_user: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="True if user was invited (skip email verification)"
    )
    
    # Impersonation (for CSR access with user permission)
    # NDPA Compliance: Time-limited tokens (24 hours max)
    can_be_impersonated: Mapped[bool] = mapped_column(
        Boolean, 
        default=False, 
        nullable=False,
        comment="Whether CSR can impersonate this user (requires user permission)"
    )
    impersonation_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When impersonation permission expires (24-hour max per NDPA)"
    )
    impersonation_granted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When impersonation was granted"
    )
    
    # Relationships
    organization: Mapped[Optional["Organization"]] = relationship(
        "Organization",
        back_populates="users",
        foreign_keys=[organization_id],
    )
    entity_access: Mapped[List["UserEntityAccess"]] = relationship(
        "UserEntityAccess",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    onboarded_by: Mapped[Optional["User"]] = relationship(
        "User",
        remote_side="User.id",
        foreign_keys=[onboarded_by_id],
    )
    notifications: Mapped[List["Notification"]] = relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    
    @property
    def full_name(self) -> str:
        """Get user's full name."""
        return f"{self.first_name} {self.last_name}"
    
    @property
    def is_super_admin(self) -> bool:
        """Check if user is a super admin."""
        return self.is_platform_staff and self.platform_role == PlatformRole.SUPER_ADMIN
    
    @property
    def is_admin(self) -> bool:
        """Check if user is a platform admin."""
        return self.is_platform_staff and self.platform_role == PlatformRole.ADMIN
    
    @property
    def effective_role(self) -> str:
        """Get the effective role (platform or organization)."""
        if self.is_platform_staff:
            return f"platform:{self.platform_role.value}" if self.platform_role else "platform:unknown"
        return f"org:{self.role.value}" if self.role else "org:unknown"
    
    def can_onboard_role(self, target_role: "PlatformRole") -> bool:
        """
        Check if this user can onboard someone with the target platform role.
        
        Hierarchy:
        - Super Admin: Can onboard Admin, IT, CSR, Marketing
        - Admin: Can onboard IT, CSR, Marketing
        - Others: Cannot onboard anyone
        """
        if not self.is_platform_staff or not self.platform_role:
            return False
        
        onboarding_permissions = {
            PlatformRole.SUPER_ADMIN: [
                PlatformRole.ADMIN, 
                PlatformRole.IT_DEVELOPER, 
                PlatformRole.CUSTOMER_SERVICE, 
                PlatformRole.MARKETING
            ],
            PlatformRole.ADMIN: [
                PlatformRole.IT_DEVELOPER, 
                PlatformRole.CUSTOMER_SERVICE, 
                PlatformRole.MARKETING
            ],
        }
        
        allowed_roles = onboarding_permissions.get(self.platform_role, [])
        return target_role in allowed_roles
    
    def __repr__(self) -> str:
        if self.is_platform_staff:
            return f"<User(id={self.id}, email={self.email}, platform_role={self.platform_role})>"
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"


class UserEntityAccess(BaseModel):
    """
    Many-to-many relationship between users and business entities.
    Allows users to have access to specific entities within their organization.
    """
    
    __tablename__ = "user_entity_access"
    
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    # Access level for this specific entity
    can_write: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    can_delete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="entity_access")
    entity: Mapped["BusinessEntity"] = relationship("BusinessEntity", back_populates="user_access")
