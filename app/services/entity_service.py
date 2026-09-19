"""
Tekvwa Pro Audit - Entity Service

Business logic for business entity management.
"""

import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import BusinessEntity
from app.models.user import User, UserEntityAccess


class EntityService:
    """Service for business entity operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def _is_admin_or_owner(self, user: User) -> bool:
        """Check if user is an admin or owner (or platform staff)."""
        # Platform staff have elevated access
        if user.is_platform_staff:
            return True
        # Check organization role
        if user.role and user.role.value in ["owner", "admin"]:
            return True
        return False
    
    def _is_owner(self, user: User) -> bool:
        """Check if user is an owner (or superadmin)."""
        # Platform superadmins have owner-level access
        if user.is_platform_staff and user.platform_role and user.platform_role.value == "SUPER_ADMIN":
            return True
        # Check organization role
        if user.role and user.role.value == "owner":
            return True
        return False
    
    async def get_entities_for_user(self, user: User) -> List[BusinessEntity]:
        """Get all entities the user has access to."""
        if self._is_admin_or_owner(user):
            # Owners, admins, and platform staff can see all entities in their organization
            # For platform staff without org, return empty (they should use specific entity access)
            if not user.organization_id:
                return []
            result = await self.db.execute(
                select(BusinessEntity)
                .where(BusinessEntity.organization_id == user.organization_id)
                .where(BusinessEntity.is_active == True)
                .order_by(BusinessEntity.name)
            )
            return list(result.scalars().all())
        else:
            # Other users can only see entities they have explicit access to
            entity_ids = [access.entity_id for access in user.entity_access]
            if not entity_ids:
                return []
            
            result = await self.db.execute(
                select(BusinessEntity)
                .where(BusinessEntity.id.in_(entity_ids))
                .where(BusinessEntity.is_active == True)
                .order_by(BusinessEntity.name)
            )
            return list(result.scalars().all())
    
    async def get_entity_by_id(
        self,
        entity_id: uuid.UUID,
        user: User,
    ) -> Optional[BusinessEntity]:
        """
        Get entity by ID if user has access.
        
        Returns:
            BusinessEntity if found and user has access, None otherwise
        """
        # Platform staff can access any entity
        if user.is_platform_staff:
            result = await self.db.execute(
                select(BusinessEntity)
                .where(BusinessEntity.id == entity_id)
            )
            return result.scalar_one_or_none()
        
        result = await self.db.execute(
            select(BusinessEntity)
            .where(BusinessEntity.id == entity_id)
            .where(BusinessEntity.organization_id == user.organization_id)
        )
        entity = result.scalar_one_or_none()
        
        if not entity:
            return None
        
        # Check user access
        if not self._is_admin_or_owner(user):
            entity_ids = [access.entity_id for access in user.entity_access]
            if entity_id not in entity_ids:
                return None
        
        return entity
    
    async def create_entity(
        self,
        user: User,
        name: str,
        legal_name: Optional[str] = None,
        tin: Optional[str] = None,
        rc_number: Optional[str] = None,
        address_line1: Optional[str] = None,
        address_line2: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        website: Optional[str] = None,
        fiscal_year_start_month: int = 1,
        currency: str = "NGN",
        is_vat_registered: bool = False,
        vat_registration_date = None,
        annual_turnover_threshold: bool = True,
    ) -> BusinessEntity:
        """Create a new business entity."""
        entity = BusinessEntity(
            organization_id=user.organization_id,
            name=name,
            legal_name=legal_name,
            tin=tin,
            rc_number=rc_number,
            address_line1=address_line1,
            address_line2=address_line2,
            city=city,
            state=state,
            country="Nigeria",
            email=email,
            phone=phone,
            website=website,
            fiscal_year_start_month=fiscal_year_start_month,
            currency=currency,
            is_vat_registered=is_vat_registered,
            vat_registration_date=vat_registration_date,
            annual_turnover_threshold=annual_turnover_threshold,
            is_active=True,
        )
        self.db.add(entity)
        await self.db.flush()
        
        # Grant creator access to the entity
        entity_access = UserEntityAccess(
            user_id=user.id,
            entity_id=entity.id,
            can_write=True,
            can_delete=True,
        )
        self.db.add(entity_access)
        
        await self.db.commit()
        await self.db.refresh(entity)
        
        return entity
    
    async def update_entity(
        self,
        entity: BusinessEntity,
        **kwargs,
    ) -> BusinessEntity:
        """Update a business entity."""
        for key, value in kwargs.items():
            if value is not None and hasattr(entity, key):
                setattr(entity, key, value)
        
        await self.db.commit()
        await self.db.refresh(entity)
        
        return entity
    
    async def delete_entity(self, entity: BusinessEntity) -> bool:
        """
        Soft delete a business entity.
        
        Note: Entities are soft-deleted (is_active=False) to preserve data integrity.
        """
        entity.is_active = False
        await self.db.commit()
        return True
    
    async def check_user_can_write(
        self,
        user: User,
        entity_id: uuid.UUID,
    ) -> bool:
        """Check if user has write access to entity."""
        if self._is_admin_or_owner(user):
            return True
        
        for access in user.entity_access:
            if access.entity_id == entity_id and access.can_write:
                return True
        
        return False
    
    async def check_user_can_delete(
        self,
        user: User,
        entity_id: uuid.UUID,
    ) -> bool:
        """Check if user has delete access to entity."""
        if self._is_owner(user):
            return True
        
        for access in user.entity_access:
            if access.entity_id == entity_id and access.can_delete:
                return True
        
        return False
