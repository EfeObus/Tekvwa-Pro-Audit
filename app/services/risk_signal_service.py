"""
Tekvwa Pro Audit - Risk Signal Service

Service layer for managing risk signals and platform monitoring.
Super Admin only feature for early warning and risk detection.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.risk_signal import (
    RiskSignal,
    RiskSignalComment,
    RiskSeverity,
    RiskCategory,
    RiskStatus,
    RiskSignalType,
)
from app.models.organization import Organization
from app.models.user import User


class RiskSignalService:
    """Service for managing risk signals."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_risk_signal(
        self,
        organization_id: uuid.UUID,
        signal_type: RiskSignalType,
        category: RiskCategory,
        severity: RiskSeverity,
        title: str,
        description: str,
        detected_by_id: Optional[uuid.UUID] = None,
        risk_score: Optional[float] = None,
        confidence_score: Optional[float] = None,
        evidence: Optional[Dict[str, Any]] = None,
        recommended_actions: Optional[List[str]] = None,
        auto_detected: bool = False,
        ml_model_id: Optional[uuid.UUID] = None,
    ) -> RiskSignal:
        """Create a new risk signal."""
        # Generate signal code
        signal_code = await self._generate_signal_code()
        
        # Calculate risk score if not provided
        if risk_score is None:
            risk_score = self._calculate_risk_score(severity, category)
        
        risk_signal = RiskSignal(
            signal_code=signal_code,
            organization_id=organization_id,
            signal_type=signal_type,
            category=category,
            severity=severity,
            status=RiskStatus.OPEN,
            title=title,
            description=description,
            risk_score=risk_score,
            confidence_score=confidence_score,
            auto_detected=auto_detected,
            detected_at=datetime.utcnow(),
            detected_by_id=detected_by_id,
            ml_model_id=ml_model_id,
            evidence=evidence or {},
            recommended_actions=recommended_actions or [],
        )
        
        # Set initial priority and SLA based on severity
        risk_signal.requires_immediate_action = severity == RiskSeverity.CRITICAL
        
        self.db.add(risk_signal)
        await self.db.commit()
        await self.db.refresh(risk_signal)
        
        return risk_signal
    
    async def get_risk_signal(self, signal_id: uuid.UUID) -> Optional[RiskSignal]:
        """Get a risk signal by ID."""
        result = await self.db.execute(
            select(RiskSignal).where(RiskSignal.id == signal_id)
        )
        return result.scalar_one_or_none()
    
    async def get_risk_signal_by_code(self, signal_code: str) -> Optional[RiskSignal]:
        """Get a risk signal by code."""
        result = await self.db.execute(
            select(RiskSignal).where(RiskSignal.signal_code == signal_code)
        )
        return result.scalar_one_or_none()
    
    async def get_all_risk_signals(
        self,
        status: Optional[RiskStatus] = None,
        severity: Optional[RiskSeverity] = None,
        category: Optional[RiskCategory] = None,
        organization_id: Optional[uuid.UUID] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[RiskSignal]:
        """Get all risk signals with optional filters."""
        query = select(RiskSignal)
        
        conditions = []
        if status:
            conditions.append(RiskSignal.status == status)
        if severity:
            conditions.append(RiskSignal.severity == severity)
        if category:
            conditions.append(RiskSignal.category == category)
        if organization_id:
            conditions.append(RiskSignal.organization_id == organization_id)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        query = query.order_by(desc(RiskSignal.detected_at))
        query = query.offset(offset).limit(limit)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_recent_risk_signals(
        self,
        days: int = 7,
        limit: int = 10,
    ) -> List[RiskSignal]:
        """Get recently detected risk signals."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        result = await self.db.execute(
            select(RiskSignal)
            .where(RiskSignal.detected_at >= cutoff)
            .order_by(desc(RiskSignal.detected_at))
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_risk_signals_stats(self) -> Dict[str, Any]:
        """Get statistics for risk signals."""
        # Critical signals
        critical = await self.db.execute(
            select(func.count(RiskSignal.id)).where(
                and_(
                    RiskSignal.severity == RiskSeverity.CRITICAL,
                    RiskSignal.status.in_([RiskStatus.OPEN, RiskStatus.ACKNOWLEDGED])
                )
            )
        )
        critical_count = critical.scalar() or 0
        
        # High priority signals
        high = await self.db.execute(
            select(func.count(RiskSignal.id)).where(
                and_(
                    RiskSignal.severity == RiskSeverity.HIGH,
                    RiskSignal.status.in_([RiskStatus.OPEN, RiskStatus.ACKNOWLEDGED])
                )
            )
        )
        high_count = high.scalar() or 0
        
        # Medium signals
        medium = await self.db.execute(
            select(func.count(RiskSignal.id)).where(
                and_(
                    RiskSignal.severity == RiskSeverity.MEDIUM,
                    RiskSignal.status.in_([RiskStatus.OPEN, RiskStatus.ACKNOWLEDGED])
                )
            )
        )
        medium_count = medium.scalar() or 0
        
        # Mitigated today
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        mitigated = await self.db.execute(
            select(func.count(RiskSignal.id)).where(
                and_(
                    RiskSignal.status == RiskStatus.RESOLVED,
                    RiskSignal.resolved_at >= today
                )
            )
        )
        mitigated_today = mitigated.scalar() or 0
        
        # Change from yesterday (simplified)
        yesterday = today - timedelta(days=1)
        yesterday_signals = await self.db.execute(
            select(func.count(RiskSignal.id)).where(
                and_(
                    RiskSignal.detected_at >= yesterday,
                    RiskSignal.detected_at < today
                )
            )
        )
        yesterday_count = yesterday_signals.scalar() or 0
        
        today_signals = await self.db.execute(
            select(func.count(RiskSignal.id)).where(
                RiskSignal.detected_at >= today
            )
        )
        today_count = today_signals.scalar() or 0
        
        change = today_count - yesterday_count
        
        return {
            "critical": critical_count,
            "high": high_count,
            "medium": medium_count,
            "mitigated_today": mitigated_today,
            "change_from_yesterday": change,
            "trend": "up" if change > 0 else ("down" if change < 0 else "stable"),
        }
    
    async def get_signals_by_category(self) -> Dict[str, int]:
        """Get count of signals by category."""
        result = await self.db.execute(
            select(RiskSignal.category, func.count(RiskSignal.id))
            .where(RiskSignal.status.in_([RiskStatus.OPEN, RiskStatus.ACKNOWLEDGED]))
            .group_by(RiskSignal.category)
        )
        return {str(row[0]): row[1] for row in result.all()}
    
    async def acknowledge_signal(
        self,
        signal_id: uuid.UUID,
        acknowledged_by_id: uuid.UUID,
    ) -> RiskSignal:
        """Acknowledge a risk signal."""
        signal = await self.get_risk_signal(signal_id)
        if not signal:
            raise ValueError(f"Risk signal {signal_id} not found")
        
        signal.acknowledged = True
        signal.acknowledged_at = datetime.utcnow()
        signal.acknowledged_by_id = acknowledged_by_id
        
        await self.db.commit()
        await self.db.refresh(signal)
        
        return signal
    
    async def assign_signal(
        self,
        signal_id: uuid.UUID,
        assigned_to_id: uuid.UUID,
        assigned_by_id: uuid.UUID,
    ) -> RiskSignal:
        """Assign a risk signal to a staff member."""
        signal = await self.get_risk_signal(signal_id)
        if not signal:
            raise ValueError(f"Risk signal {signal_id} not found")
        
        signal.assigned_to_id = assigned_to_id
        signal.status = RiskStatus.ACKNOWLEDGED
        
        await self.db.commit()
        await self.db.refresh(signal)
        
        return signal
    
    async def update_signal_status(
        self,
        signal_id: uuid.UUID,
        status: RiskStatus,
        resolution_notes: Optional[str] = None,
        resolved_by_id: Optional[uuid.UUID] = None,
    ) -> RiskSignal:
        """Update the status of a risk signal."""
        signal = await self.get_risk_signal(signal_id)
        if not signal:
            raise ValueError(f"Risk signal {signal_id} not found")
        
        signal.status = status
        
        if status in [RiskStatus.RESOLVED, RiskStatus.RESOLVED, RiskStatus.FALSE_POSITIVE]:
            signal.resolved_at = datetime.utcnow()
            signal.resolved_by_id = resolved_by_id
            signal.resolution_notes = resolution_notes
        
        await self.db.commit()
        await self.db.refresh(signal)
        
        return signal
    
    async def add_comment(
        self,
        signal_id: uuid.UUID,
        comment_text: str,
        staff_id: uuid.UUID,
    ) -> RiskSignalComment:
        """Add a comment to a risk signal."""
        signal = await self.get_risk_signal(signal_id)
        if not signal:
            raise ValueError(f"Risk signal {signal_id} not found")
        
        comment = RiskSignalComment(
            risk_signal_id=signal_id,
            staff_id=staff_id,
            comment=comment_text,
        )
        
        self.db.add(comment)
        await self.db.commit()
        await self.db.refresh(comment)
        
        return comment
    
    async def _generate_signal_code(self) -> str:
        """Generate a unique signal code."""
        today = datetime.utcnow().strftime("%Y%m%d")
        
        result = await self.db.execute(
            select(func.count(RiskSignal.id)).where(
                RiskSignal.signal_code.like(f"RS-{today}-%")
            )
        )
        count = (result.scalar() or 0) + 1
        
        return f"RS-{today}-{count:04d}"
    
    def _calculate_risk_score(self, severity: RiskSeverity, category: RiskCategory) -> float:
        """Calculate a risk score based on severity and category."""
        severity_weights = {
            RiskSeverity.CRITICAL: 1.0,
            RiskSeverity.HIGH: 0.75,
            RiskSeverity.MEDIUM: 0.5,
            RiskSeverity.LOW: 0.25,
            RiskSeverity.INFO: 0.1,
        }
        
        category_weights = {
            RiskCategory.SECURITY: 1.0,
            RiskCategory.FRAUD: 0.95,
            RiskCategory.FINANCIAL: 0.85,
            RiskCategory.COMPLIANCE: 0.8,
            RiskCategory.REPUTATIONAL: 0.7,
            RiskCategory.OPERATIONAL: 0.6,
            RiskCategory.DATA_QUALITY: 0.5,
            RiskCategory.PERFORMANCE: 0.4,
        }
        
        severity_score = severity_weights.get(severity, 0.5)
        category_score = category_weights.get(category, 0.5)
        
        return round((severity_score * 0.6 + category_score * 0.4) * 100, 1)
