"""
Tekvwa Pro Audit - Legal Hold Service

Service layer for managing legal holds.
Super Admin only feature for compliance and data preservation.
"""

import uuid
from datetime import datetime, date
from typing import Optional, List, Dict, Any

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.legal_hold import (
    LegalHold,
    LegalHoldNotification,
    LegalHoldStatus,
    LegalHoldType,
    DataScope,
)
from app.models.organization import Organization
from app.models.user import User


class LegalHoldService:
    """Service for managing legal holds."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_legal_hold(
        self,
        organization_id: uuid.UUID,
        matter_name: str,
        hold_type: LegalHoldType,
        data_scope: DataScope,
        preservation_start_date: date,
        created_by_id: uuid.UUID,
        matter_reference: Optional[str] = None,
        preservation_end_date: Optional[date] = None,
        legal_counsel_name: Optional[str] = None,
        legal_counsel_email: Optional[str] = None,
        legal_counsel_phone: Optional[str] = None,
        description: Optional[str] = None,
        internal_notes: Optional[str] = None,
        entity_ids: Optional[List[str]] = None,
    ) -> LegalHold:
        """Create a new legal hold."""
        # Generate hold number
        hold_number = await self._generate_hold_number()
        
        legal_hold = LegalHold(
            hold_number=hold_number,
            organization_id=organization_id,
            matter_name=matter_name,
            matter_reference=matter_reference,
            hold_type=hold_type,
            status=LegalHoldStatus.ACTIVE,
            data_scope=data_scope,
            preservation_start_date=preservation_start_date,
            preservation_end_date=preservation_end_date,
            hold_start_date=datetime.utcnow(),
            legal_counsel_name=legal_counsel_name,
            legal_counsel_email=legal_counsel_email,
            legal_counsel_phone=legal_counsel_phone,
            description=description,
            internal_notes=internal_notes,
            entity_ids=entity_ids,
            created_by_staff_id=created_by_id,
        )
        
        # Estimate records count
        legal_hold.records_preserved_count = await self._estimate_records_count(
            organization_id, data_scope, entity_ids
        )
        
        self.db.add(legal_hold)
        await self.db.commit()
        await self.db.refresh(legal_hold)
        
        return legal_hold
    
    async def get_legal_hold(self, hold_id: uuid.UUID) -> Optional[LegalHold]:
        """Get a legal hold by ID."""
        result = await self.db.execute(
            select(LegalHold).where(LegalHold.id == hold_id)
        )
        return result.scalar_one_or_none()
    
    async def get_legal_hold_by_number(self, hold_number: str) -> Optional[LegalHold]:
        """Get a legal hold by hold number."""
        result = await self.db.execute(
            select(LegalHold).where(LegalHold.hold_number == hold_number)
        )
        return result.scalar_one_or_none()
    
    async def get_all_legal_holds(
        self,
        status: Optional[LegalHoldStatus] = None,
        organization_id: Optional[uuid.UUID] = None,
        hold_type: Optional[LegalHoldType] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[LegalHold]:
        """Get all legal holds with optional filters."""
        query = select(LegalHold)
        
        conditions = []
        if status:
            conditions.append(LegalHold.status == status)
        if organization_id:
            conditions.append(LegalHold.organization_id == organization_id)
        if hold_type:
            conditions.append(LegalHold.hold_type == hold_type)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        query = query.order_by(LegalHold.hold_start_date.desc())
        query = query.offset(offset).limit(limit)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_active_holds_count(self) -> int:
        """Get count of active legal holds."""
        result = await self.db.execute(
            select(func.count(LegalHold.id)).where(
                LegalHold.status == LegalHoldStatus.ACTIVE
            )
        )
        return result.scalar() or 0
    
    async def get_legal_holds_stats(self) -> Dict[str, Any]:
        """Get statistics for legal holds."""
        # Active holds
        active_count = await self.get_active_holds_count()
        
        # Pending release
        pending_release = await self.db.execute(
            select(func.count(LegalHold.id)).where(
                LegalHold.status == LegalHoldStatus.PENDING_RELEASE
            )
        )
        pending_release_count = pending_release.scalar() or 0
        
        # Tenants affected
        tenants_result = await self.db.execute(
            select(func.count(func.distinct(LegalHold.organization_id))).where(
                LegalHold.status == LegalHoldStatus.ACTIVE
            )
        )
        tenants_affected = tenants_result.scalar() or 0
        
        # Total records preserved
        records_result = await self.db.execute(
            select(func.sum(LegalHold.records_preserved_count)).where(
                LegalHold.status == LegalHoldStatus.ACTIVE
            )
        )
        records_count = records_result.scalar() or 0
        
        return {
            "active": active_count,
            "pending_release": pending_release_count,
            "tenants_affected": tenants_affected,
            "records_count": records_count,
        }
    
    async def release_legal_hold(
        self,
        hold_id: uuid.UUID,
        released_by_id: uuid.UUID,
        release_reason: str,
    ) -> LegalHold:
        """Release a legal hold."""
        legal_hold = await self.get_legal_hold(hold_id)
        if not legal_hold:
            raise ValueError(f"Legal hold {hold_id} not found")
        
        if legal_hold.status == LegalHoldStatus.RELEASED:
            raise ValueError("Legal hold is already released")
        
        legal_hold.status = LegalHoldStatus.RELEASED
        legal_hold.hold_end_date = datetime.utcnow()
        legal_hold.released_by_staff_id = released_by_id
        legal_hold.release_reason = release_reason
        
        await self.db.commit()
        await self.db.refresh(legal_hold)
        
        return legal_hold
    
    async def request_release(
        self,
        hold_id: uuid.UUID,
    ) -> LegalHold:
        """Request release of a legal hold (sets to pending_release)."""
        legal_hold = await self.get_legal_hold(hold_id)
        if not legal_hold:
            raise ValueError(f"Legal hold {hold_id} not found")
        
        if legal_hold.status != LegalHoldStatus.ACTIVE:
            raise ValueError("Only active holds can be requested for release")
        
        legal_hold.status = LegalHoldStatus.PENDING_RELEASE
        
        await self.db.commit()
        await self.db.refresh(legal_hold)
        
        return legal_hold
    
    async def check_organization_has_hold(self, organization_id: uuid.UUID) -> bool:
        """Check if an organization has any active legal holds."""
        result = await self.db.execute(
            select(func.count(LegalHold.id)).where(
                and_(
                    LegalHold.organization_id == organization_id,
                    LegalHold.status == LegalHoldStatus.ACTIVE
                )
            )
        )
        count = result.scalar() or 0
        return count > 0
    
    async def _generate_hold_number(self) -> str:
        """Generate a unique hold number."""
        year = datetime.utcnow().year
        
        result = await self.db.execute(
            select(func.count(LegalHold.id)).where(
                LegalHold.hold_number.like(f"LH-{year}-%")
            )
        )
        count = (result.scalar() or 0) + 1
        
        return f"LH-{year}-{count:04d}"
    
    async def _estimate_records_count(
        self,
        organization_id: uuid.UUID,
        data_scope: DataScope,
        entity_ids: Optional[List[str]] = None,
    ) -> int:
        """Estimate the number of records under the hold."""
        # This is a simplified estimation
        # In production, you would query actual record counts
        base_count = 1000  # Base estimate
        
        if data_scope == DataScope.ALL_DATA:
            return base_count * 10
        elif data_scope == DataScope.FINANCIAL_RECORDS:
            return base_count * 5
        elif data_scope == DataScope.TAX_FILINGS:
            return base_count * 2
        elif data_scope == DataScope.PAYROLL_RECORDS:
            return base_count * 3
        elif data_scope == DataScope.AUDIT_LOGS:
            return base_count * 8
        elif data_scope == DataScope.SPECIFIC_ENTITIES:
            if entity_ids:
                return base_count * len(entity_ids)
            return base_count
        
        return base_count
