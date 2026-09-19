"""
Tekvwa Pro Audit - Organization User Management Service

Service for managing users within an organization.
Handles user invitation, role assignment, and access control.
"""

import uuid
from typing import List, Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User, UserRole, UserEntityAccess
from app.models.organization import Organization
from app.models.entity import BusinessEntity
from app.utils.security import get_password_hash, generate_random_password
from app.utils.permissions import (
    OrganizationPermission,
    has_organization_permission,
    is_organization_role_higher_or_equal,
)


class OrganizationUserService:
    """Service for managing organization users."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_organization_users(
        self,
        requesting_user: User,
        organization_id: uuid.UUID,
        include_inactive: bool = False,
    ) -> List[User]:
        """
        Get all users in an organization.
        
        Args:
            requesting_user: User making the request (must be org admin)
            organization_id: Organization to get users for
            include_inactive: Whether to include deactivated users
        """
        # Verify requesting user has permission
        if requesting_user.is_platform_staff:
            # Platform staff can view users
            pass
        elif requesting_user.organization_id != organization_id:
            raise PermissionError("Cannot view users from another organization")
        elif not has_organization_permission(requesting_user.role, OrganizationPermission.MANAGE_USERS):
            raise PermissionError("You don't have permission to manage users")
        
        query = select(User).where(
            and_(
                User.organization_id == organization_id,
                User.is_platform_staff == False
            )
        )
        
        if not include_inactive:
            query = query.where(User.is_active == True)
        
        result = await self.db.execute(
            query.options(
                selectinload(User.entity_access).selectinload(UserEntityAccess.entity)
            ).order_by(User.created_at.desc())
        )
        
        return list(result.scalars().all())
    
    async def invite_user(
        self,
        requesting_user: User,
        email: str,
        first_name: str,
        last_name: str,
        role: UserRole,
        phone_number: Optional[str] = None,
        entity_ids: Optional[List[uuid.UUID]] = None,
    ) -> tuple[User, str]:
        """
        Invite a new user to the organization.
        
        Args:
            requesting_user: User making the invitation (must be admin/owner)
            email: Email for the new user
            first_name: First name
            last_name: Last name
            role: Role to assign
            phone_number: Optional phone number
            entity_ids: Optional list of entity IDs to grant access to
            
        Returns:
            Tuple of (new_user, temporary_password)
        """
        if requesting_user.is_platform_staff:
            raise PermissionError("Platform staff cannot invite organization users directly")
        
        if not has_organization_permission(requesting_user.role, OrganizationPermission.MANAGE_USERS):
            raise PermissionError("You don't have permission to invite users")
        
        # Cannot invite someone with higher role
        if is_organization_role_higher_or_equal(role, requesting_user.role) and requesting_user.role != UserRole.OWNER:
            raise PermissionError(f"Cannot invite user with role: {role.value}")
        
        # Check if email already exists
        existing = await self.db.execute(
            select(User).where(User.email == email.lower())
        )
        if existing.scalar_one_or_none():
            raise ValueError("Email already registered")
        
        # Generate temporary password
        temp_password = generate_random_password()
        
        # Create user
        # IMPORTANT: Invited users MUST reset password on first login
        # Invited users skip email verification (admin vouches for them)
        new_user = User(
            email=email.lower(),
            hashed_password=get_password_hash(temp_password),
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
            organization_id=requesting_user.organization_id,
            role=role,
            is_platform_staff=False,
            is_active=True,
            is_verified=True,  # Invited users are pre-verified (admin vouches for them)
            is_invited_user=True,  # Mark as invited (skip email verification)
            must_reset_password=True,  # Force password change on first login (RBAC requirement)
        )
        
        self.db.add(new_user)
        await self.db.flush()
        
        # Grant entity access
        if entity_ids:
            for entity_id in entity_ids:
                # Verify entity belongs to org
                entity_result = await self.db.execute(
                    select(BusinessEntity).where(
                        and_(
                            BusinessEntity.id == entity_id,
                            BusinessEntity.organization_id == requesting_user.organization_id
                        )
                    )
                )
                entity = entity_result.scalar_one_or_none()
                if entity:
                    access = UserEntityAccess(
                        user_id=new_user.id,
                        entity_id=entity_id,
                        can_write=role in [UserRole.OWNER, UserRole.ADMIN, UserRole.ACCOUNTANT],
                        can_delete=role in [UserRole.OWNER, UserRole.ADMIN],
                    )
                    self.db.add(access)
        else:
            # Grant access to all entities in the organization
            entities_result = await self.db.execute(
                select(BusinessEntity).where(
                    BusinessEntity.organization_id == requesting_user.organization_id
                )
            )
            for entity in entities_result.scalars().all():
                access = UserEntityAccess(
                    user_id=new_user.id,
                    entity_id=entity.id,
                    can_write=role in [UserRole.OWNER, UserRole.ADMIN, UserRole.ACCOUNTANT],
                    can_delete=role in [UserRole.OWNER, UserRole.ADMIN],
                )
                self.db.add(access)
        
        await self.db.commit()
        await self.db.refresh(new_user)
        
        return new_user, temp_password
    
    async def update_user_role(
        self,
        requesting_user: User,
        target_user_id: uuid.UUID,
        new_role: UserRole,
    ) -> User:
        """
        Update a user's role within the organization.
        """
        if requesting_user.is_platform_staff:
            raise PermissionError("Platform staff cannot modify organization user roles directly")
        
        if not has_organization_permission(requesting_user.role, OrganizationPermission.MANAGE_USERS):
            raise PermissionError("You don't have permission to manage users")
        
        if requesting_user.id == target_user_id:
            raise ValueError("Cannot change your own role")
        
        # Get target user
        result = await self.db.execute(
            select(User).where(User.id == target_user_id)
        )
        target_user = result.scalar_one_or_none()
        
        if not target_user:
            raise ValueError("User not found")
        
        if target_user.organization_id != requesting_user.organization_id:
            raise PermissionError("Cannot modify users from another organization")
        
        # Only owner can change to owner role
        if new_role == UserRole.OWNER and requesting_user.role != UserRole.OWNER:
            raise PermissionError("Only owners can promote to owner role")
        
        # Cannot demote someone with equal or higher role (unless you're owner)
        if requesting_user.role != UserRole.OWNER:
            if is_organization_role_higher_or_equal(target_user.role, requesting_user.role):
                raise PermissionError("Cannot modify users with equal or higher role")
        
        target_user.role = new_role
        await self.db.commit()
        await self.db.refresh(target_user)
        
        return target_user
    
    async def deactivate_user(
        self,
        requesting_user: User,
        target_user_id: uuid.UUID,
    ) -> User:
        """Deactivate a user within the organization."""
        if requesting_user.is_platform_staff:
            raise PermissionError("Platform staff cannot deactivate organization users directly")
        
        if not has_organization_permission(requesting_user.role, OrganizationPermission.MANAGE_USERS):
            raise PermissionError("You don't have permission to manage users")
        
        if requesting_user.id == target_user_id:
            raise ValueError("Cannot deactivate yourself")
        
        result = await self.db.execute(
            select(User).where(User.id == target_user_id)
        )
        target_user = result.scalar_one_or_none()
        
        if not target_user:
            raise ValueError("User not found")
        
        if target_user.organization_id != requesting_user.organization_id:
            raise PermissionError("Cannot modify users from another organization")
        
        # Cannot deactivate owner (unless you're also owner)
        if target_user.role == UserRole.OWNER and requesting_user.role != UserRole.OWNER:
            raise PermissionError("Only owners can deactivate other owners")
        
        target_user.is_active = False
        await self.db.commit()
        await self.db.refresh(target_user)
        
        return target_user
    
    async def reactivate_user(
        self,
        requesting_user: User,
        target_user_id: uuid.UUID,
    ) -> User:
        """Reactivate a deactivated user."""
        if not has_organization_permission(requesting_user.role, OrganizationPermission.MANAGE_USERS):
            raise PermissionError("You don't have permission to manage users")
        
        result = await self.db.execute(
            select(User).where(User.id == target_user_id)
        )
        target_user = result.scalar_one_or_none()
        
        if not target_user:
            raise ValueError("User not found")
        
        if target_user.organization_id != requesting_user.organization_id:
            raise PermissionError("Cannot modify users from another organization")
        
        target_user.is_active = True
        await self.db.commit()
        await self.db.refresh(target_user)
        
        return target_user
    
    async def update_entity_access(
        self,
        requesting_user: User,
        target_user_id: uuid.UUID,
        entity_id: uuid.UUID,
        can_write: bool,
        can_delete: bool,
    ) -> UserEntityAccess:
        """Update a user's access level for a specific entity."""
        if not has_organization_permission(requesting_user.role, OrganizationPermission.MANAGE_USERS):
            raise PermissionError("You don't have permission to manage users")
        
        # Verify user and entity are in the same org
        user_result = await self.db.execute(
            select(User).where(User.id == target_user_id)
        )
        target_user = user_result.scalar_one_or_none()
        
        if not target_user or target_user.organization_id != requesting_user.organization_id:
            raise ValueError("User not found or not in your organization")
        
        entity_result = await self.db.execute(
            select(BusinessEntity).where(BusinessEntity.id == entity_id)
        )
        entity = entity_result.scalar_one_or_none()
        
        if not entity or entity.organization_id != requesting_user.organization_id:
            raise ValueError("Entity not found or not in your organization")
        
        # Find or create access record
        access_result = await self.db.execute(
            select(UserEntityAccess).where(
                and_(
                    UserEntityAccess.user_id == target_user_id,
                    UserEntityAccess.entity_id == entity_id
                )
            )
        )
        access = access_result.scalar_one_or_none()
        
        if access:
            access.can_write = can_write
            access.can_delete = can_delete
        else:
            access = UserEntityAccess(
                user_id=target_user_id,
                entity_id=entity_id,
                can_write=can_write,
                can_delete=can_delete,
            )
            self.db.add(access)
        
        await self.db.commit()
        await self.db.refresh(access)
        
        return access
    
    async def toggle_impersonation_permission(
        self,
        user: User,
        allow: bool,
    ) -> User:
        """Toggle whether CSR can impersonate this user."""
        user.can_be_impersonated = allow
        await self.db.commit()
        await self.db.refresh(user)
        return user
