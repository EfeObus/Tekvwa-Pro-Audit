"""
Tekvwa Pro Audit - Usage Metering Service

Service for tracking and managing usage metrics for billing and limit enforcement.
Tracks: transactions, users, entities, API calls, OCR pages, storage, ML inferences.
"""

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any
from uuid import UUID
from calendar import monthrange

from sqlalchemy import select, func, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sku import (
    UsageRecord,
    UsageEvent,
    UsageMetricType,
    SKUTier,
    TenantSKU,
    TIER_LIMITS,
)

logger = logging.getLogger(__name__)


class MeteringService:
    """
    Service for tracking and reporting usage metrics.
    
    Usage metrics are tracked at two levels:
    1. UsageEvent: Real-time individual events (high volume)
    2. UsageRecord: Aggregated period summaries (for billing)
    
    Usage:
        service = MeteringService(db)
        
        # Record a usage event
        await service.record_event(org_id, UsageMetricType.TRANSACTIONS, quantity=1)
        
        # Get current usage for a metric
        usage = await service.get_current_usage(org_id, UsageMetricType.TRANSACTIONS)
        
        # Check if within limits
        is_ok = await service.is_within_limit(org_id, UsageMetricType.TRANSACTIONS)
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # ===========================================
    # USAGE RECORDING
    # ===========================================
    
    async def record_event(
        self,
        organization_id: UUID,
        metric_type: UsageMetricType,
        quantity: int = 1,
        entity_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> UsageEvent:
        """
        Record a usage event.
        
        This creates an individual event record that will be aggregated
        into periodic usage summaries.
        
        Args:
            organization_id: Organization this usage belongs to
            metric_type: Type of usage metric
            quantity: Amount to record (default 1)
            entity_id: Optional business entity ID
            user_id: User who triggered this usage
            resource_type: Type of resource (e.g., "invoice", "transaction")
            resource_id: ID of the specific resource
            metadata: Additional contextual data
        
        Returns:
            The created UsageEvent
        """
        event = UsageEvent(
            organization_id=organization_id,
            entity_id=entity_id,
            user_id=user_id,
            metric_type=metric_type,
            quantity=quantity,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata,
        )
        
        self.db.add(event)
        await self.db.flush()
        
        # Also update the current period's usage record
        await self._update_period_usage(organization_id, metric_type, quantity)
        
        return event
    
    async def record_transaction(
        self,
        organization_id: UUID,
        entity_id: UUID,
        user_id: Optional[UUID] = None,
        transaction_id: Optional[str] = None,
    ) -> None:
        """Convenience method to record a transaction."""
        await self.record_event(
            organization_id=organization_id,
            metric_type=UsageMetricType.TRANSACTIONS,
            entity_id=entity_id,
            user_id=user_id,
            resource_type="transaction",
            resource_id=transaction_id,
        )
    
    async def record_invoice(
        self,
        organization_id: UUID,
        entity_id: UUID,
        user_id: Optional[UUID] = None,
        invoice_id: Optional[str] = None,
    ) -> None:
        """Convenience method to record an invoice."""
        await self.record_event(
            organization_id=organization_id,
            metric_type=UsageMetricType.INVOICES,
            entity_id=entity_id,
            user_id=user_id,
            resource_type="invoice",
            resource_id=invoice_id,
        )
    
    async def record_api_call(
        self,
        organization_id: UUID,
        user_id: Optional[UUID] = None,
        endpoint: Optional[str] = None,
    ) -> None:
        """Convenience method to record an API call."""
        await self.record_event(
            organization_id=organization_id,
            metric_type=UsageMetricType.API_CALLS,
            user_id=user_id,
            resource_type="api_call",
            metadata={"endpoint": endpoint} if endpoint else None,
        )
    
    async def record_ocr_pages(
        self,
        organization_id: UUID,
        pages: int,
        user_id: Optional[UUID] = None,
        document_id: Optional[str] = None,
    ) -> None:
        """Convenience method to record OCR page usage."""
        await self.record_event(
            organization_id=organization_id,
            metric_type=UsageMetricType.OCR_PAGES,
            quantity=pages,
            user_id=user_id,
            resource_type="ocr_document",
            resource_id=document_id,
        )
    
    async def record_ml_inference(
        self,
        organization_id: UUID,
        model_type: str,
        user_id: Optional[UUID] = None,
    ) -> None:
        """Convenience method to record ML inference usage."""
        await self.record_event(
            organization_id=organization_id,
            metric_type=UsageMetricType.ML_INFERENCES,
            user_id=user_id,
            resource_type="ml_inference",
            metadata={"model_type": model_type},
        )
    
    async def update_storage_usage(
        self,
        organization_id: UUID,
        storage_mb: Decimal,
    ) -> None:
        """Update storage usage (absolute value, not increment)."""
        period = self._get_current_period()
        
        record = await self._get_or_create_usage_record(
            organization_id=organization_id,
            period_start=period[0],
            period_end=period[1],
        )
        
        record.storage_used_mb = storage_mb
        await self.db.flush()
    
    async def update_user_count(
        self,
        organization_id: UUID,
        user_count: int,
    ) -> None:
        """Update active user count (absolute value)."""
        period = self._get_current_period()
        
        record = await self._get_or_create_usage_record(
            organization_id=organization_id,
            period_start=period[0],
            period_end=period[1],
        )
        
        record.users_count = user_count
        await self.db.flush()
    
    async def update_entity_count(
        self,
        organization_id: UUID,
        entity_count: int,
    ) -> None:
        """Update entity count (absolute value)."""
        period = self._get_current_period()
        
        record = await self._get_or_create_usage_record(
            organization_id=organization_id,
            period_start=period[0],
            period_end=period[1],
        )
        
        record.entities_count = entity_count
        await self.db.flush()
    
    async def update_employee_count(
        self,
        organization_id: UUID,
        employee_count: int,
    ) -> None:
        """Update employee count (absolute value)."""
        period = self._get_current_period()
        
        record = await self._get_or_create_usage_record(
            organization_id=organization_id,
            period_start=period[0],
            period_end=period[1],
        )
        
        record.employees_count = employee_count
        await self.db.flush()
    
    # ===========================================
    # USAGE RETRIEVAL
    # ===========================================
    
    async def get_current_usage(
        self,
        organization_id: UUID,
        metric: UsageMetricType,
    ) -> int:
        """
        Get current usage for a metric in the current billing period.
        
        Args:
            organization_id: Organization to check
            metric: The metric to retrieve
        
        Returns:
            Current usage count
        """
        period = self._get_current_period()
        
        result = await self.db.execute(
            select(UsageRecord).where(
                and_(
                    UsageRecord.organization_id == organization_id,
                    UsageRecord.period_start == period[0],
                    UsageRecord.period_end == period[1],
                )
            )
        )
        record = result.scalar_one_or_none()
        
        if not record:
            return 0
        
        # Map metric to field
        metric_field_map = {
            UsageMetricType.TRANSACTIONS: record.transactions_count,
            UsageMetricType.USERS: record.users_count,
            UsageMetricType.ENTITIES: record.entities_count,
            UsageMetricType.INVOICES: record.invoices_count,
            UsageMetricType.API_CALLS: record.api_calls_count,
            UsageMetricType.OCR_PAGES: record.ocr_pages_count,
            UsageMetricType.STORAGE_MB: int(record.storage_used_mb),
            UsageMetricType.ML_INFERENCES: record.ml_inferences_count,
            UsageMetricType.EMPLOYEES: record.employees_count,
        }
        
        return metric_field_map.get(metric, 0)
    
    async def get_all_current_usage(
        self,
        organization_id: UUID,
    ) -> Dict[str, int]:
        """
        Get all current usage metrics for an organization.
        
        Returns:
            Dictionary of metric name to usage count
        """
        usage = {}
        for metric in UsageMetricType:
            usage[metric.value] = await self.get_current_usage(organization_id, metric)
        return usage
    
    async def get_usage_history(
        self,
        organization_id: UUID,
        months: int = 12,
    ) -> List[UsageRecord]:
        """
        Get usage history for the past N months.
        
        Args:
            organization_id: Organization to check
            months: Number of months to retrieve
        
        Returns:
            List of UsageRecord objects
        """
        cutoff_date = date.today() - timedelta(days=months * 31)
        
        result = await self.db.execute(
            select(UsageRecord)
            .where(
                and_(
                    UsageRecord.organization_id == organization_id,
                    UsageRecord.period_start >= cutoff_date,
                )
            )
            .order_by(UsageRecord.period_start.desc())
        )
        
        return list(result.scalars().all())
    
    async def get_usage_for_period(
        self,
        organization_id: UUID,
        period_start: date,
        period_end: date,
    ) -> Optional[UsageRecord]:
        """Get usage record for a specific period."""
        result = await self.db.execute(
            select(UsageRecord).where(
                and_(
                    UsageRecord.organization_id == organization_id,
                    UsageRecord.period_start == period_start,
                    UsageRecord.period_end == period_end,
                )
            )
        )
        return result.scalar_one_or_none()
    
    # ===========================================
    # LIMIT CHECKING
    # ===========================================
    
    async def is_within_limit(
        self,
        organization_id: UUID,
        metric: UsageMetricType,
    ) -> bool:
        """
        Check if current usage is within limits.
        
        Args:
            organization_id: Organization to check
            metric: The metric to check
        
        Returns:
            True if within limits, False if exceeded
        """
        from app.services.feature_flags import FeatureFlagService
        
        current_usage = await self.get_current_usage(organization_id, metric)
        
        feature_service = FeatureFlagService(self.db)
        limit = await feature_service.get_limit(organization_id, metric)
        
        # -1 means unlimited
        if limit == -1:
            return True
        
        return current_usage < limit
    
    async def get_usage_percentage(
        self,
        organization_id: UUID,
        metric: UsageMetricType,
    ) -> float:
        """
        Get usage as percentage of limit.
        
        Returns:
            Percentage (0-100+). Returns 0 for unlimited metrics.
        """
        from app.services.feature_flags import FeatureFlagService
        
        current_usage = await self.get_current_usage(organization_id, metric)
        
        feature_service = FeatureFlagService(self.db)
        limit = await feature_service.get_limit(organization_id, metric)
        
        if limit == -1 or limit == 0:
            return 0.0
        
        return (current_usage / limit) * 100
    
    async def get_usage_summary(
        self,
        organization_id: UUID,
    ) -> Dict[str, Any]:
        """
        Get comprehensive usage summary with limits and percentages.
        
        Returns:
            Dictionary with usage data, limits, and percentages
        """
        from app.services.feature_flags import FeatureFlagService
        
        feature_service = FeatureFlagService(self.db)
        tier = await feature_service.get_effective_tier(organization_id)
        
        summary = {
            "tier": tier.value,
            "period": self._get_current_period(),
            "metrics": {},
        }
        
        for metric in UsageMetricType:
            current = await self.get_current_usage(organization_id, metric)
            limit = await feature_service.get_limit(organization_id, metric)
            
            percentage = 0.0
            if limit > 0:
                percentage = (current / limit) * 100
            
            status = "ok"
            if limit != -1:
                if percentage >= 100:
                    status = "exceeded"
                elif percentage >= 90:
                    status = "critical"
                elif percentage >= 75:
                    status = "warning"
            
            summary["metrics"][metric.value] = {
                "current": current,
                "limit": limit if limit != -1 else "unlimited",
                "percentage": round(percentage, 2),
                "status": status,
            }
        
        return summary
    
    # ===========================================
    # BILLING SUPPORT
    # ===========================================
    
    async def get_unbilled_records(
        self,
        organization_id: Optional[UUID] = None,
    ) -> List[UsageRecord]:
        """Get all unbilled usage records."""
        query = select(UsageRecord).where(UsageRecord.is_billed == False)
        
        if organization_id:
            query = query.where(UsageRecord.organization_id == organization_id)
        
        # Only get completed periods (not current period)
        today = date.today()
        query = query.where(UsageRecord.period_end < today)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def mark_as_billed(
        self,
        record_id: UUID,
        invoice_reference: Optional[str] = None,
    ) -> None:
        """Mark a usage record as billed."""
        await self.db.execute(
            update(UsageRecord)
            .where(UsageRecord.id == record_id)
            .values(
                is_billed=True,
                billed_at=datetime.utcnow(),
                invoice_reference=invoice_reference,
            )
        )
        await self.db.flush()
    
    # ===========================================
    # INTERNAL HELPERS
    # ===========================================
    
    def _get_current_period(self) -> tuple[date, date]:
        """Get the current billing period (monthly)."""
        today = date.today()
        period_start = date(today.year, today.month, 1)
        last_day = monthrange(today.year, today.month)[1]
        period_end = date(today.year, today.month, last_day)
        return (period_start, period_end)
    
    async def _get_or_create_usage_record(
        self,
        organization_id: UUID,
        period_start: date,
        period_end: date,
    ) -> UsageRecord:
        """Get existing usage record or create new one."""
        result = await self.db.execute(
            select(UsageRecord).where(
                and_(
                    UsageRecord.organization_id == organization_id,
                    UsageRecord.period_start == period_start,
                    UsageRecord.period_end == period_end,
                )
            )
        )
        record = result.scalar_one_or_none()
        
        if not record:
            record = UsageRecord(
                organization_id=organization_id,
                period_start=period_start,
                period_end=period_end,
            )
            self.db.add(record)
            await self.db.flush()
        
        return record
    
    async def _update_period_usage(
        self,
        organization_id: UUID,
        metric_type: UsageMetricType,
        quantity: int,
    ) -> None:
        """Update the current period's usage record for a metric."""
        period = self._get_current_period()
        
        record = await self._get_or_create_usage_record(
            organization_id=organization_id,
            period_start=period[0],
            period_end=period[1],
        )
        
        # Increment the appropriate field
        if metric_type == UsageMetricType.TRANSACTIONS:
            record.transactions_count += quantity
        elif metric_type == UsageMetricType.INVOICES:
            record.invoices_count += quantity
        elif metric_type == UsageMetricType.API_CALLS:
            record.api_calls_count += quantity
        elif metric_type == UsageMetricType.OCR_PAGES:
            record.ocr_pages_count += quantity
        elif metric_type == UsageMetricType.ML_INFERENCES:
            record.ml_inferences_count += quantity
        
        await self.db.flush()
    
    async def aggregate_events_to_record(
        self,
        organization_id: UUID,
        period_start: date,
        period_end: date,
    ) -> UsageRecord:
        """
        Aggregate usage events into a period record.
        
        This is typically run as a scheduled task to consolidate
        events into billing records.
        """
        record = await self._get_or_create_usage_record(
            organization_id, period_start, period_end
        )
        
        # Aggregate each metric type
        for metric_type in UsageMetricType:
            result = await self.db.execute(
                select(func.sum(UsageEvent.quantity))
                .where(
                    and_(
                        UsageEvent.organization_id == organization_id,
                        UsageEvent.metric_type == metric_type,
                        UsageEvent.created_at >= datetime.combine(period_start, datetime.min.time()),
                        UsageEvent.created_at <= datetime.combine(period_end, datetime.max.time()),
                    )
                )
            )
            total = result.scalar() or 0
            
            # Update the appropriate field
            if metric_type == UsageMetricType.TRANSACTIONS:
                record.transactions_count = total
            elif metric_type == UsageMetricType.INVOICES:
                record.invoices_count = total
            elif metric_type == UsageMetricType.API_CALLS:
                record.api_calls_count = total
            elif metric_type == UsageMetricType.OCR_PAGES:
                record.ocr_pages_count = total
            elif metric_type == UsageMetricType.ML_INFERENCES:
                record.ml_inferences_count = total
        
        await self.db.flush()
        return record
