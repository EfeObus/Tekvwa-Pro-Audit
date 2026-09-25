"""
Tekvwa Pro Audit - Upsell Service

Service layer for managing upsell opportunities.
Super Admin only feature for revenue expansion tracking.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from decimal import Decimal

from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.upsell import (
    UpsellOpportunity,
    UpsellActivity,
    UpsellType,
    UpsellStatus,
    UpsellPriority,
    UpsellSignal,
)
from app.models.organization import Organization
from app.models.user import User


class UpsellService:
    """Service for managing upsell opportunities."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_opportunity(
        self,
        organization_id: uuid.UUID,
        upsell_type: UpsellType,
        signal: UpsellSignal,
        priority: UpsellPriority,
        title: str,
        description: str,
        estimated_mrr_increase: Decimal,
        assigned_to_id: Optional[uuid.UUID] = None,
        target_product: Optional[str] = None,
        current_product: Optional[str] = None,
        signal_data: Optional[Dict[str, Any]] = None,
        confidence_score: Optional[float] = None,
        auto_detected: bool = False,
    ) -> UpsellOpportunity:
        """Create a new upsell opportunity."""
        opportunity_code = await self._generate_opportunity_code()
        
        # Calculate estimated ARR
        estimated_arr_increase = estimated_mrr_increase * 12
        
        opportunity = UpsellOpportunity(
            opportunity_code=opportunity_code,
            organization_id=organization_id,
            upsell_type=upsell_type,
            signal=signal,
            status=UpsellStatus.IDENTIFIED,
            priority=priority,
            title=title,
            description=description,
            estimated_mrr_increase=estimated_mrr_increase,
            estimated_arr_increase=estimated_arr_increase,
            current_product=current_product,
            target_product=target_product,
            assigned_to_id=assigned_to_id,
            signal_data=signal_data or {},
            confidence_score=confidence_score,
            auto_detected=auto_detected,
            identified_at=datetime.utcnow(),
        )
        
        self.db.add(opportunity)
        await self.db.commit()
        await self.db.refresh(opportunity)
        
        return opportunity
    
    async def get_opportunity(self, opportunity_id: uuid.UUID) -> Optional[UpsellOpportunity]:
        """Get an upsell opportunity by ID."""
        result = await self.db.execute(
            select(UpsellOpportunity).where(UpsellOpportunity.id == opportunity_id)
        )
        return result.scalar_one_or_none()
    
    async def get_opportunity_by_code(self, code: str) -> Optional[UpsellOpportunity]:
        """Get an upsell opportunity by code."""
        result = await self.db.execute(
            select(UpsellOpportunity).where(UpsellOpportunity.opportunity_code == code)
        )
        return result.scalar_one_or_none()
    
    async def get_all_opportunities(
        self,
        status: Optional[UpsellStatus] = None,
        priority: Optional[UpsellPriority] = None,
        upsell_type: Optional[UpsellType] = None,
        organization_id: Optional[uuid.UUID] = None,
        assigned_to_id: Optional[uuid.UUID] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[UpsellOpportunity]:
        """Get all upsell opportunities with optional filters."""
        query = select(UpsellOpportunity)
        
        conditions = []
        if status:
            conditions.append(UpsellOpportunity.status == status)
        if priority:
            conditions.append(UpsellOpportunity.priority == priority)
        if upsell_type:
            conditions.append(UpsellOpportunity.upsell_type == upsell_type)
        if organization_id:
            conditions.append(UpsellOpportunity.organization_id == organization_id)
        if assigned_to_id:
            conditions.append(UpsellOpportunity.assigned_to_id == assigned_to_id)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        query = query.order_by(desc(UpsellOpportunity.identified_at))
        query = query.offset(offset).limit(limit)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_upsell_stats(self) -> Dict[str, Any]:
        """Get statistics for upsell opportunities."""
        # Total pipeline value (estimated MRR from active opportunities)
        pipeline = await self.db.execute(
            select(func.sum(UpsellOpportunity.estimated_mrr_increase)).where(
                UpsellOpportunity.status.in_([
                    UpsellStatus.IDENTIFIED,
                    UpsellStatus.QUALIFIED,
                    UpsellStatus.PROPOSAL_SENT,
                    UpsellStatus.NEGOTIATING,
                ])
            )
        )
        pipeline_value = pipeline.scalar() or Decimal("0")
        
        # Hot opportunities count
        hot = await self.db.execute(
            select(func.count(UpsellOpportunity.id)).where(
                and_(
                    UpsellOpportunity.priority == UpsellPriority.HOT,
                    UpsellOpportunity.status.in_([
                        UpsellStatus.IDENTIFIED,
                        UpsellStatus.QUALIFIED,
                        UpsellStatus.PROPOSAL_SENT,
                        UpsellStatus.NEGOTIATING,
                    ])
                )
            )
        )
        hot_count = hot.scalar() or 0
        
        # Won this month
        first_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        won = await self.db.execute(
            select(func.count(UpsellOpportunity.id)).where(
                and_(
                    UpsellOpportunity.status == UpsellStatus.WON,
                    UpsellOpportunity.closed_at >= first_of_month
                )
            )
        )
        won_count = won.scalar() or 0
        
        # Won MRR this month
        won_mrr = await self.db.execute(
            select(func.sum(UpsellOpportunity.actual_mrr_increase)).where(
                and_(
                    UpsellOpportunity.status == UpsellStatus.WON,
                    UpsellOpportunity.closed_at >= first_of_month
                )
            )
        )
        won_mrr_value = won_mrr.scalar() or Decimal("0")
        
        # Conversion rate
        total_closed = await self.db.execute(
            select(func.count(UpsellOpportunity.id)).where(
                UpsellOpportunity.status.in_([UpsellStatus.WON, UpsellStatus.LOST])
            )
        )
        total_closed_count = total_closed.scalar() or 0
        
        total_won = await self.db.execute(
            select(func.count(UpsellOpportunity.id)).where(
                UpsellOpportunity.status == UpsellStatus.WON
            )
        )
        total_won_count = total_won.scalar() or 0
        
        conversion_rate = (total_won_count / total_closed_count * 100) if total_closed_count > 0 else 0
        
        return {
            "pipeline_value": float(pipeline_value),
            "hot_opportunities": hot_count,
            "won_this_month": won_count,
            "won_mrr_this_month": float(won_mrr_value),
            "conversion_rate": round(conversion_rate, 1),
        }
    
    async def get_opportunities_by_type(self) -> Dict[str, int]:
        """Get count of opportunities by type."""
        result = await self.db.execute(
            select(UpsellOpportunity.upsell_type, func.count(UpsellOpportunity.id))
            .where(UpsellOpportunity.status.in_([
                UpsellStatus.IDENTIFIED,
                UpsellStatus.QUALIFIED,
                UpsellStatus.PROPOSAL_SENT,
                UpsellStatus.NEGOTIATING,
            ]))
            .group_by(UpsellOpportunity.upsell_type)
        )
        return {str(row[0].value): row[1] for row in result.all()}
    
    async def update_status(
        self,
        opportunity_id: uuid.UUID,
        status: UpsellStatus,
        actual_mrr_increase: Optional[Decimal] = None,
        lost_reason: Optional[str] = None,
    ) -> UpsellOpportunity:
        """Update the status of an upsell opportunity."""
        opportunity = await self.get_opportunity(opportunity_id)
        if not opportunity:
            raise ValueError(f"Upsell opportunity {opportunity_id} not found")

        opportunity.status = status

        if status in [UpsellStatus.WON, UpsellStatus.LOST]:
            opportunity.closed_at = datetime.utcnow()
            if status == UpsellStatus.WON and actual_mrr_increase is not None:
                opportunity.actual_mrr_increase = actual_mrr_increase
                opportunity.actual_arr_increase = actual_mrr_increase * 12
            if status == UpsellStatus.LOST and lost_reason:
                opportunity.lost_reason = lost_reason
        
        await self.db.commit()
        await self.db.refresh(opportunity)
        
        return opportunity
    
    async def assign_opportunity(
        self,
        opportunity_id: uuid.UUID,
        assigned_to_id: uuid.UUID,
    ) -> UpsellOpportunity:
        """Assign an upsell opportunity to a staff member."""
        opportunity = await self.get_opportunity(opportunity_id)
        if not opportunity:
            raise ValueError(f"Upsell opportunity {opportunity_id} not found")
        
        opportunity.assigned_to_id = assigned_to_id
        
        await self.db.commit()
        await self.db.refresh(opportunity)
        
        return opportunity
    
    async def add_activity(
        self,
        opportunity_id: uuid.UUID,
        activity_type: str,
        description: str,
        staff_id: uuid.UUID,
        outcome: Optional[str] = None,
        next_action: Optional[str] = None,
        next_action_date: Optional[datetime] = None,
    ) -> UpsellActivity:
        """Add an activity to an upsell opportunity."""
        opportunity = await self.get_opportunity(opportunity_id)
        if not opportunity:
            raise ValueError(f"Upsell opportunity {opportunity_id} not found")
        
        activity = UpsellActivity(
            upsell_opportunity_id=opportunity_id,
            activity_type=activity_type,
            description=description,
            performed_by_id=staff_id,
            outcome=outcome,
            next_action=next_action,
            next_action_date=next_action_date,
        )
        
        self.db.add(activity)
        
        # Update opportunity's next action
        if next_action:
            opportunity.next_action = next_action
            opportunity.next_action_date = next_action_date
        
        await self.db.commit()
        await self.db.refresh(activity)
        
        return activity
    
    async def get_activities(
        self,
        opportunity_id: uuid.UUID,
        limit: int = 50,
    ) -> List[UpsellActivity]:
        """Get activities for an upsell opportunity."""
        result = await self.db.execute(
            select(UpsellActivity)
            .where(UpsellActivity.upsell_opportunity_id == opportunity_id)
            .order_by(desc(UpsellActivity.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def _generate_opportunity_code(self) -> str:
        """Generate a unique opportunity code."""
        year = datetime.utcnow().year
        
        result = await self.db.execute(
            select(func.count(UpsellOpportunity.id)).where(
                UpsellOpportunity.opportunity_code.like(f"UPS-{year}-%")
            )
        )
        count = (result.scalar() or 0) + 1
        
        return f"UPS-{year}-{count:04d}"
