"""
Tekvwa Pro Audit - Risk Signals Router

API endpoints for managing risk signals.
Super Admin only feature for platform monitoring and early warning.
"""

import uuid
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import require_super_admin, require_feature
from app.models.user import User
from app.models.risk_signal import (
    RiskSeverity,
    RiskCategory,
    RiskStatus,
    RiskSignalType,
)
from app.models.sku import Feature
from app.services.risk_signal_service import RiskSignalService

# Feature gate for risk signals (ENTERPRISE tier - WORM vault for compliance)
risk_signals_feature_gate = require_feature([Feature.WORM_VAULT])

router = APIRouter(
    prefix="/risk-signals",
    tags=["Risk Signals"],
    dependencies=[Depends(risk_signals_feature_gate)],
)


# ===========================================
# REQUEST/RESPONSE SCHEMAS
# ===========================================

class CreateRiskSignalRequest(BaseModel):
    """Request schema for creating a risk signal."""
    organization_id: uuid.UUID
    signal_type: RiskSignalType
    category: RiskCategory
    severity: RiskSeverity
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    risk_score: Optional[float] = Field(None, ge=0, le=100)
    confidence_score: Optional[float] = Field(None, ge=0, le=100)
    evidence: Optional[Dict[str, Any]] = None
    recommended_actions: Optional[List[str]] = None


class RiskSignalResponse(BaseModel):
    """Response schema for risk signal."""
    id: uuid.UUID
    signal_code: str
    organization_id: uuid.UUID
    signal_type: str
    category: str
    severity: str
    status: str
    title: str
    description: str
    risk_score: Optional[float]
    confidence_score: Optional[float]
    detected_at: str
    acknowledged: bool
    requires_immediate_action: bool
    auto_detected: bool
    created_at: str
    
    class Config:
        from_attributes = True


class RiskSignalListResponse(BaseModel):
    """Response schema for risk signal list."""
    signals: List[RiskSignalResponse]
    total: int


class RiskSignalStatsResponse(BaseModel):
    """Response schema for risk signal statistics."""
    critical: int
    high: int
    medium: int
    mitigated_today: int
    change_from_yesterday: int
    trend: str


class UpdateStatusRequest(BaseModel):
    """Request schema for updating risk signal status."""
    status: RiskStatus
    resolution_notes: Optional[str] = None


class AssignSignalRequest(BaseModel):
    """Request schema for assigning a risk signal."""
    assigned_to_id: uuid.UUID


class AddCommentRequest(BaseModel):
    """Request schema for adding a comment."""
    comment: str = Field(..., min_length=1)


# ===========================================
# API ENDPOINTS
# ===========================================

@router.post("", response_model=RiskSignalResponse, status_code=status.HTTP_201_CREATED)
async def create_risk_signal(
    request: CreateRiskSignalRequest,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Create a new risk signal (Super Admin only)."""
    service = RiskSignalService(db)
    
    try:
        signal = await service.create_risk_signal(
            organization_id=request.organization_id,
            signal_type=request.signal_type,
            category=request.category,
            severity=request.severity,
            title=request.title,
            description=request.description,
            detected_by_id=current_user.id,
            risk_score=request.risk_score,
            confidence_score=request.confidence_score,
            evidence=request.evidence,
            recommended_actions=request.recommended_actions,
            auto_detected=False,
        )
        
        return _format_risk_signal(signal)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("", response_model=RiskSignalListResponse)
async def list_risk_signals(
    status_filter: Optional[RiskStatus] = Query(None, alias="status"),
    severity: Optional[RiskSeverity] = None,
    category: Optional[RiskCategory] = None,
    organization_id: Optional[uuid.UUID] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """List all risk signals (Super Admin only)."""
    service = RiskSignalService(db)
    
    signals = await service.get_all_risk_signals(
        status=status_filter,
        severity=severity,
        category=category,
        organization_id=organization_id,
        limit=limit,
        offset=offset,
    )
    
    return {
        "signals": [_format_risk_signal(s) for s in signals],
        "total": len(signals),
    }


@router.get("/stats", response_model=RiskSignalStatsResponse)
async def get_risk_signal_stats(
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Get risk signal statistics (Super Admin only)."""
    service = RiskSignalService(db)
    stats = await service.get_risk_signals_stats()
    return stats


@router.get("/recent")
async def get_recent_signals(
    days: int = Query(7, ge=1, le=30),
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Get recently detected risk signals (Super Admin only)."""
    service = RiskSignalService(db)
    signals = await service.get_recent_risk_signals(days=days, limit=limit)
    
    return {
        "signals": [_format_risk_signal(s) for s in signals],
        "total": len(signals),
    }


@router.get("/by-category")
async def get_signals_by_category(
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Get risk signals grouped by category (Super Admin only)."""
    service = RiskSignalService(db)
    by_category = await service.get_signals_by_category()
    return {"by_category": by_category}


@router.get("/{signal_id}", response_model=RiskSignalResponse)
async def get_risk_signal(
    signal_id: uuid.UUID,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Get a specific risk signal (Super Admin only)."""
    service = RiskSignalService(db)
    signal = await service.get_risk_signal(signal_id)
    
    if not signal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Risk signal not found",
        )
    
    return _format_risk_signal(signal)


@router.post("/{signal_id}/acknowledge", response_model=RiskSignalResponse)
async def acknowledge_signal(
    signal_id: uuid.UUID,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Acknowledge a risk signal (Super Admin only)."""
    service = RiskSignalService(db)
    
    try:
        signal = await service.acknowledge_signal(
            signal_id=signal_id,
            acknowledged_by_id=current_user.id,
        )
        return _format_risk_signal(signal)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{signal_id}/assign", response_model=RiskSignalResponse)
async def assign_signal(
    signal_id: uuid.UUID,
    request: AssignSignalRequest,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Assign a risk signal to a staff member (Super Admin only)."""
    service = RiskSignalService(db)
    
    try:
        signal = await service.assign_signal(
            signal_id=signal_id,
            assigned_to_id=request.assigned_to_id,
            assigned_by_id=current_user.id,
        )
        return _format_risk_signal(signal)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.put("/{signal_id}/status", response_model=RiskSignalResponse)
async def update_signal_status(
    signal_id: uuid.UUID,
    request: UpdateStatusRequest,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Update risk signal status (Super Admin only)."""
    service = RiskSignalService(db)
    
    try:
        signal = await service.update_signal_status(
            signal_id=signal_id,
            status=request.status,
            resolution_notes=request.resolution_notes,
            resolved_by_id=current_user.id,
        )
        return _format_risk_signal(signal)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{signal_id}/comments")
async def add_comment(
    signal_id: uuid.UUID,
    request: AddCommentRequest,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Add a comment to a risk signal (Super Admin only)."""
    service = RiskSignalService(db)
    
    try:
        comment = await service.add_comment(
            signal_id=signal_id,
            comment_text=request.comment,
            staff_id=current_user.id,
        )
        return {
            "id": str(comment.id),
            "comment": comment.comment,
            "created_at": comment.created_at.isoformat() if comment.created_at else None,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


def _format_risk_signal(signal) -> dict:
    """Format risk signal for response."""
    return {
        "id": signal.id,
        "signal_code": signal.signal_code,
        "organization_id": signal.organization_id,
        "signal_type": signal.signal_type.value if signal.signal_type else None,
        "category": signal.category.value if signal.category else None,
        "severity": signal.severity.value if signal.severity else None,
        "status": signal.status.value if signal.status else None,
        "title": signal.title,
        "description": signal.description,
        "risk_score": signal.risk_score,
        "confidence_score": signal.confidence_score,
        "detected_at": signal.detected_at.isoformat() if signal.detected_at else None,
        "acknowledged": signal.acknowledged,
        "requires_immediate_action": signal.requires_immediate_action,
        "auto_detected": signal.auto_detected,
        "created_at": signal.created_at.isoformat() if signal.created_at else None,
    }
