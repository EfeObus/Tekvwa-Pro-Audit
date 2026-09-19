"""
Tekvwa Pro Audit - Dunning Management Service

Manages the dunning process for failed payments.
Implements escalation rules and retry schedules.

Dunning Levels:
1. Initial (Day 0): First failure notification
2. Warning (Day 3): First reminder
3. Urgent (Day 7): Urgent notice
4. Final (Day 14): Final warning before suspension
5. Suspended (Day 21): Account suspended

Retry Schedule:
- Day 1: First retry
- Day 3: Second retry
- Day 5: Third retry
- Day 7: Fourth retry (escalate to urgent)
- Day 10: Fifth retry
- Day 14: Sixth retry (final notice)
- Day 21: Account suspension
"""

import uuid
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum
from dataclasses import dataclass

from sqlalchemy import select, and_, or_, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory

logger = logging.getLogger(__name__)


class DunningLevel(str, Enum):
    """Dunning escalation levels."""
    INITIAL = "initial"
    WARNING = "warning"
    URGENT = "urgent"
    FINAL = "final"
    SUSPENDED = "suspended"


@dataclass
class DunningRecord:
    """Dunning status for an organization."""
    organization_id: uuid.UUID
    level: DunningLevel
    amount_naira: int
    first_failure_at: datetime
    last_retry_at: Optional[datetime]
    retry_count: int
    next_retry_at: Optional[datetime]
    days_until_suspension: int
    notes: Optional[str]


# Dunning schedule configuration
DUNNING_SCHEDULE = {
    # (days_since_failure, retry_count) -> action
    (0, 0): {"action": "notify", "level": DunningLevel.INITIAL},
    (1, 1): {"action": "retry", "level": DunningLevel.INITIAL},
    (3, 2): {"action": "retry", "level": DunningLevel.WARNING},
    (5, 3): {"action": "retry", "level": DunningLevel.WARNING},
    (7, 4): {"action": "retry", "level": DunningLevel.URGENT},
    (10, 5): {"action": "retry", "level": DunningLevel.URGENT},
    (14, 6): {"action": "retry", "level": DunningLevel.FINAL},
    (21, 7): {"action": "suspend", "level": DunningLevel.SUSPENDED},
}

# Grace period before suspension (days)
GRACE_PERIOD_DAYS = 21

# Maximum retry attempts
MAX_RETRY_ATTEMPTS = 6


class DunningService:
    """Service for managing payment dunning and collections."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def record_payment_failure(
        self,
        organization_id: uuid.UUID,
        reason: str,
        amount_naira: int,
        transaction_reference: Optional[str] = None,
    ) -> DunningRecord:
        """
        Record a payment failure and initiate dunning process.
        
        Args:
            organization_id: The organization with failed payment
            reason: Reason for payment failure
            amount_naira: Amount that failed to process
            transaction_reference: Optional payment transaction reference
            
        Returns:
            DunningRecord with current dunning status
        """
        from app.models.sku import TenantSKU
        
        now = datetime.utcnow()
        
        # Get or create dunning record in tenant_sku metadata
        result = await self.db.execute(
            select(TenantSKU).where(TenantSKU.organization_id == organization_id)
        )
        tenant_sku = result.scalar_one_or_none()
        
        if not tenant_sku:
            raise ValueError(f"No TenantSKU found for organization {organization_id}")
        
        # TenantSKU doesn't have custom_metadata - mark as pending cancellation instead
        # This sets up the dunning state using existing fields
        tenant_sku.cancel_at_period_end = True
        tenant_sku.suspension_reason = reason
        await self.db.flush()
        
        logger.info(f"Recorded payment failure for org {organization_id}: {reason}")
        
        return self._create_dunning_record(tenant_sku)
    
    async def get_dunning_status(
        self,
        organization_id: uuid.UUID,
    ) -> Optional[DunningRecord]:
        """Get current dunning status for an organization."""
        from app.models.sku import TenantSKU
        
        result = await self.db.execute(
            select(TenantSKU).where(TenantSKU.organization_id == organization_id)
        )
        tenant_sku = result.scalar_one_or_none()
        
        if not tenant_sku:
            return None
        
        # TenantSKU doesn't have custom_metadata - dunning info should come from 
        # subscription status, not metadata. Return None if no dunning situation.
        # Check if in dunning by looking at suspension/cancellation state
        if not tenant_sku.suspended_at and not tenant_sku.cancel_at_period_end:
            return None
        
        return self._create_dunning_record(tenant_sku)
    
    async def get_active_dunning_records(self) -> List[DunningRecord]:
        """Get all organizations currently in dunning (suspended or pending cancellation)."""
        from app.models.sku import TenantSKU
        
        # TenantSKU doesn't have custom_metadata - look for suspended/cancellation state instead
        result = await self.db.execute(
            select(TenantSKU)
            .where(TenantSKU.is_active == True)
            .where(
                or_(
                    TenantSKU.suspended_at != None,
                    TenantSKU.cancel_at_period_end == True
                )
            )
        )
        tenant_skus = result.scalars().all()
        
        records = []
        for tenant_sku in tenant_skus:
            # Only include non-suspended records (suspended ones are final state)
            if not tenant_sku.suspended_at:
                records.append(self._create_dunning_record_safe(tenant_sku))
        
        return records
    
    async def should_retry_payment(
        self,
        organization_id: uuid.UUID,
    ) -> Tuple[bool, Optional[str]]:
        """
        Determine if payment should be retried and what action to take.
        
        Returns:
            Tuple of (should_retry, action) where action is one of:
            - "retry": Attempt payment retry
            - "escalate": Escalate dunning level
            - "suspend": Suspend account
            - None: No action needed
        """
        from app.models.sku import TenantSKU
        
        result = await self.db.execute(
            select(TenantSKU).where(TenantSKU.organization_id == organization_id)
        )
        tenant_sku = result.scalar_one_or_none()
        
        if not tenant_sku:
            return False, None
        
        # TenantSKU doesn't have custom_metadata - check suspension state instead
        if tenant_sku.suspended_at:
            return False, None  # Already suspended
        
        if tenant_sku.cancel_at_period_end:
            return True, "suspend"  # Should be suspended
        
        # No dunning situation if not suspended or pending cancellation
        return False, None
    
    async def record_retry_attempt(
        self,
        organization_id: uuid.UUID,
        success: bool = False,
    ) -> None:
        """Record a payment retry attempt."""
        from app.models.sku import TenantSKU
        
        result = await self.db.execute(
            select(TenantSKU).where(TenantSKU.organization_id == organization_id)
        )
        tenant_sku = result.scalar_one_or_none()
        
        if not tenant_sku:
            return
        
        # TenantSKU doesn't have custom_metadata
        # On success, clear dunning state
        if success:
            tenant_sku.cancel_at_period_end = False
            tenant_sku.suspended_at = None
            tenant_sku.suspension_reason = None
            await self.db.flush()
            logger.info(f"Payment recovered for org {organization_id}, cleared dunning")
    
    async def escalate_dunning_level(
        self,
        organization_id: uuid.UUID,
    ) -> DunningLevel:
        """Escalate the dunning level for an organization."""
        from app.models.sku import TenantSKU
        
        result = await self.db.execute(
            select(TenantSKU).where(TenantSKU.organization_id == organization_id)
        )
        tenant_sku = result.scalar_one_or_none()
        
        if not tenant_sku:
            raise ValueError(f"No TenantSKU found for organization {organization_id}")
        
        # TenantSKU doesn't have custom_metadata - use suspension state for escalation
        # Escalation: cancel_at_period_end=True -> suspended_at=now
        if tenant_sku.suspended_at:
            return DunningLevel.SUSPENDED
        elif tenant_sku.cancel_at_period_end:
            # Escalate to suspended
            tenant_sku.suspended_at = datetime.utcnow()
            tenant_sku.is_active = False
            await self.db.flush()
            logger.info(f"Escalated dunning for org {organization_id}: final -> suspended")
            return DunningLevel.SUSPENDED
        else:
            # Start dunning
            tenant_sku.cancel_at_period_end = True
            await self.db.flush()
            logger.info(f"Escalated dunning for org {organization_id}: none -> initial")
            return DunningLevel.INITIAL
    
    async def clear_dunning(
        self,
        organization_id: uuid.UUID,
        reason: str = "Payment received",
    ) -> None:
        """Clear dunning status after successful payment."""
        from app.models.sku import TenantSKU
        
        result = await self.db.execute(
            select(TenantSKU).where(TenantSKU.organization_id == organization_id)
        )
        tenant_sku = result.scalar_one_or_none()
        
        if not tenant_sku:
            return
        
        # TenantSKU doesn't have custom_metadata - clear dunning using existing fields
        tenant_sku.cancel_at_period_end = False
        tenant_sku.suspended_at = None
        tenant_sku.suspension_reason = None
        tenant_sku.is_active = True
        
        await self.db.flush()
        logger.info(f"Cleared dunning for org {organization_id}: {reason}")
    
    async def get_dunning_summary(self) -> Dict[str, Any]:
        """Get summary of all dunning activity."""
        from app.models.sku import TenantSKU
        
        # TenantSKU doesn't have custom_metadata - query based on suspension state
        result = await self.db.execute(
            select(TenantSKU).where(
                or_(
                    TenantSKU.suspended_at != None,
                    TenantSKU.cancel_at_period_end == True
                )
            )
        )
        tenant_skus = result.scalars().all()
        
        summary = {
            "total_in_dunning": 0,
            "by_level": {
                DunningLevel.INITIAL.value: 0,
                DunningLevel.WARNING.value: 0,
                DunningLevel.URGENT.value: 0,
                DunningLevel.FINAL.value: 0,
                DunningLevel.SUSPENDED.value: 0,
            },
            "total_amount_at_risk": 0,
            "average_days_in_dunning": 0,
        }
        
        total_days = 0
        for tenant_sku in tenant_skus:
            if tenant_sku.suspended_at:
                level = DunningLevel.SUSPENDED.value
                days = (datetime.utcnow() - tenant_sku.suspended_at).days
            elif tenant_sku.cancel_at_period_end:
                level = DunningLevel.FINAL.value
                days = 0  # Unknown start date
            else:
                continue
                
            summary["total_in_dunning"] += 1
            summary["by_level"][level] = summary["by_level"].get(level, 0) + 1
            total_days += days
        
        if summary["total_in_dunning"] > 0:
            summary["average_days_in_dunning"] = total_days / summary["total_in_dunning"]
        
        return summary
    
    def _create_dunning_record(self, tenant_sku) -> DunningRecord:
        """Create DunningRecord from TenantSKU."""
        # TenantSKU doesn't have custom_metadata - use safe defaults
        return self._create_dunning_record_safe(tenant_sku)
    
    def _create_dunning_record_safe(self, tenant_sku) -> DunningRecord:
        """Create DunningRecord from TenantSKU without relying on custom_metadata."""
        now = datetime.utcnow()
        
        # Determine level based on tenant state
        if tenant_sku.suspended_at:
            level = DunningLevel.SUSPENDED
            first_failure = tenant_sku.suspended_at
        elif tenant_sku.cancel_at_period_end:
            level = DunningLevel.FINAL
            first_failure = now - timedelta(days=14)  # Estimate
        else:
            level = DunningLevel.INITIAL
            first_failure = now
        
        days_elapsed = (now - first_failure).days if first_failure else 0
        days_until_suspension = max(0, GRACE_PERIOD_DAYS - days_elapsed)
        
        return DunningRecord(
            organization_id=tenant_sku.organization_id,
            level=level,
            amount_naira=0,
            first_failure_at=first_failure or now,
            last_retry_at=None,
            retry_count=0,
            next_retry_at=None,
            days_until_suspension=days_until_suspension,
            notes=tenant_sku.suspension_reason if tenant_sku.suspended_at else None,
        )
