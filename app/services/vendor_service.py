"""
Tekvwa Pro Audit - Vendor Service

Business logic for vendor management with TIN verification.
"""

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vendor import Vendor
from app.models.transaction import Transaction


class VendorService:
    """Service for vendor operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_vendors_for_entity(
        self,
        entity_id: uuid.UUID,
        search: Optional[str] = None,
        include_inactive: bool = False,
    ) -> List[Vendor]:
        """Get all vendors for an entity."""
        query = select(Vendor).where(Vendor.entity_id == entity_id)
        
        if search:
            search_term = f"%{search}%"
            query = query.where(
                (Vendor.name.ilike(search_term)) |
                (Vendor.tin.ilike(search_term)) |
                (Vendor.email.ilike(search_term))
            )
        
        if not include_inactive:
            query = query.where(Vendor.is_active == True)
        
        query = query.order_by(Vendor.name)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_vendor_by_id(
        self,
        vendor_id: uuid.UUID,
        entity_id: uuid.UUID,
    ) -> Optional[Vendor]:
        """Get vendor by ID."""
        result = await self.db.execute(
            select(Vendor)
            .where(Vendor.id == vendor_id)
            .where(Vendor.entity_id == entity_id)
        )
        return result.scalar_one_or_none()
    
    async def get_vendor_by_tin(
        self,
        tin: str,
        entity_id: uuid.UUID,
    ) -> Optional[Vendor]:
        """Get vendor by TIN."""
        result = await self.db.execute(
            select(Vendor)
            .where(Vendor.tin == tin)
            .where(Vendor.entity_id == entity_id)
        )
        return result.scalar_one_or_none()
    
    async def create_vendor(
        self,
        entity_id: uuid.UUID,
        name: str,
        tin: Optional[str] = None,
        contact_person: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        address: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        bank_name: Optional[str] = None,
        bank_account_number: Optional[str] = None,
        bank_account_name: Optional[str] = None,
        is_vat_registered: bool = False,
        default_wht_rate: Optional[float] = None,
        notes: Optional[str] = None,
    ) -> Vendor:
        """Create a new vendor."""
        # Check for duplicate TIN if provided
        if tin:
            existing = await self.get_vendor_by_tin(tin, entity_id)
            if existing:
                raise ValueError(f"Vendor with TIN '{tin}' already exists")
        
        vendor = Vendor(
            entity_id=entity_id,
            name=name,
            tin=tin,
            contact_person=contact_person,
            email=email,
            phone=phone,
            address=address,
            city=city,
            state=state,
            country="Nigeria",
            bank_name=bank_name,
            bank_account_number=bank_account_number,
            bank_account_name=bank_account_name,
            is_vat_registered=is_vat_registered,
            default_wht_rate=default_wht_rate,
            notes=notes,
            tin_verified=False,
            is_active=True,
        )
        
        self.db.add(vendor)
        await self.db.commit()
        await self.db.refresh(vendor)
        
        return vendor
    
    async def update_vendor(
        self,
        vendor: Vendor,
        **kwargs,
    ) -> Vendor:
        """Update a vendor."""
        # If TIN is being updated, reset verification
        if "tin" in kwargs and kwargs["tin"] != vendor.tin:
            vendor.tin_verified = False
            vendor.tin_verified_at = None
        
        for key, value in kwargs.items():
            if value is not None and hasattr(vendor, key):
                setattr(vendor, key, value)
        
        await self.db.commit()
        await self.db.refresh(vendor)
        
        return vendor
    
    async def delete_vendor(self, vendor: Vendor) -> bool:
        """Soft delete a vendor."""
        vendor.is_active = False
        await self.db.commit()
        return True
    
    async def verify_tin(
        self,
        vendor: Vendor,
    ) -> tuple[bool, str]:
        """
        Verify vendor TIN with FIRS/NRS.
        
        Uses the NRS API client to validate TIN against FIRS registry.
        
        Returns:
            Tuple of (verified: bool, message: str)
        """
        if not vendor.tin:
            return False, "No TIN provided"
        
        # Import NRS client
        from app.services.nrs_service import get_nrs_client
        
        nrs_client = get_nrs_client()
        result = await nrs_client.validate_tin(vendor.tin, vendor.name)
        
        if result.is_valid:
            vendor.tin_verified = True
            vendor.tin_verified_at = datetime.utcnow()
            
            # Update registered name if returned from NRS
            if result.registered_name and not vendor.trading_name:
                vendor.trading_name = result.registered_name
            
            await self.db.commit()
            await self.db.refresh(vendor)
            
            return True, result.message
        else:
            vendor.tin_verified = False
            vendor.tin_verified_at = None
            await self.db.commit()
            
            return False, result.message
    
    async def get_vendor_stats(
        self,
        vendor: Vendor,
    ) -> dict:
        """Get vendor statistics (total paid, transaction count)."""
        # Query transactions for this vendor
        result = await self.db.execute(
            select(
                func.count(Transaction.id).label("count"),
                func.coalesce(func.sum(Transaction.total_amount), 0).label("total"),
            )
            .where(Transaction.vendor_id == vendor.id)
        )
        
        row = result.one()
        
        return {
            "transaction_count": row.count,
            "total_paid": float(row.total),
        }
