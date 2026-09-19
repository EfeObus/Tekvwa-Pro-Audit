"""
Tekvwa Pro Audit - Upsell Router

API endpoints for managing upsell opportunities.
Super Admin only feature for revenue expansion tracking.
"""

import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import require_super_admin
from app.models.user import User
from app.models.upsell import (
    UpsellType,
    UpsellStatus,
    UpsellPriority,
    UpsellSignal,
)
from app.services.upsell_service import UpsellService


router = APIRouter(prefix="/upsell", tags=["Upsell"])


# ===========================================
# REQUEST/RESPONSE SCHEMAS
# ===========================================

class CreateUpsellOpportunityRequest(BaseModel):
    """Request schema for creating an upsell opportunity."""
    organization_id: uuid.UUID
    upsell_type: UpsellType
    signal: UpsellSignal
    priority: UpsellPriority
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    estimated_mrr_increase: Decimal = Field(..., ge=0)
    assigned_to_id: Optional[uuid.UUID] = None
    target_product: Optional[str] = None
    current_product: Optional[str] = None
    signal_data: Optional[Dict[str, Any]] = None
    confidence_score: Optional[float] = Field(None, ge=0, le=100)


class UpsellOpportunityResponse(BaseModel):
    """Response schema for upsell opportunity."""
    id: uuid.UUID
    opportunity_code: str
    organization_id: uuid.UUID
    upsell_type: str
    signal: str
    status: str
    priority: str
    title: str
    description: str
    estimated_mrr_increase: float
    estimated_arr_increase: float
    actual_mrr_increase: Optional[float]
    current_product: Optional[str]
    target_product: Optional[str]
    assigned_to_id: Optional[uuid.UUID]
    confidence_score: Optional[float]
    identified_at: Optional[str]
    closed_at: Optional[str]
    created_at: str
    
    class Config:
        from_attributes = True


class UpsellListResponse(BaseModel):
    """Response schema for upsell opportunity list."""
    opportunities: List[UpsellOpportunityResponse]
    total: int


class UpsellStatsResponse(BaseModel):
    """Response schema for upsell statistics."""
    pipeline_value: float
    hot_opportunities: int
    won_this_month: int
    won_mrr_this_month: float
    conversion_rate: float


class UpdateStatusRequest(BaseModel):
    """Request schema for updating opportunity status."""
    status: UpsellStatus
    actual_mrr_increase: Optional[Decimal] = Field(None, ge=0)
    lost_reason: Optional[str] = None


class AssignOpportunityRequest(BaseModel):
    """Request schema for assigning an opportunity."""
    assigned_to_id: uuid.UUID


class AddActivityRequest(BaseModel):
    """Request schema for adding an activity."""
    activity_type: str = Field(..., min_length=1, max_length=50)
    description: str = Field(..., min_length=1)
    outcome: Optional[str] = None
    next_action: Optional[str] = None
    next_action_date: Optional[datetime] = None


# ===========================================
# API ENDPOINTS
# ===========================================

@router.post("", response_model=UpsellOpportunityResponse, status_code=status.HTTP_201_CREATED)
async def create_upsell_opportunity(
    request: CreateUpsellOpportunityRequest,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Create a new upsell opportunity (Super Admin only)."""
    service = UpsellService(db)
    
    try:
        opportunity = await service.create_opportunity(
            organization_id=request.organization_id,
            upsell_type=request.upsell_type,
            signal=request.signal,
            priority=request.priority,
            title=request.title,
            description=request.description,
            estimated_mrr_increase=request.estimated_mrr_increase,
            assigned_to_id=request.assigned_to_id,
            target_product=request.target_product,
            current_product=request.current_product,
            signal_data=request.signal_data,
            confidence_score=request.confidence_score,
            auto_detected=False,
        )
        
        return _format_upsell_opportunity(opportunity)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("", response_model=UpsellListResponse)
async def list_upsell_opportunities(
    status_filter: Optional[UpsellStatus] = Query(None, alias="status"),
    priority: Optional[UpsellPriority] = None,
    upsell_type: Optional[UpsellType] = None,
    organization_id: Optional[uuid.UUID] = None,
    assigned_to_id: Optional[uuid.UUID] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """List all upsell opportunities (Super Admin only)."""
    service = UpsellService(db)
    
    opportunities = await service.get_all_opportunities(
        status=status_filter,
        priority=priority,
        upsell_type=upsell_type,
        organization_id=organization_id,
        assigned_to_id=assigned_to_id,
        limit=limit,
        offset=offset,
    )
    
    return {
        "opportunities": [_format_upsell_opportunity(o) for o in opportunities],
        "total": len(opportunities),
    }


@router.get("/stats", response_model=UpsellStatsResponse)
async def get_upsell_stats(
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Get upsell statistics (Super Admin only)."""
    service = UpsellService(db)
    stats = await service.get_upsell_stats()
    return stats


@router.get("/by-type")
async def get_opportunities_by_type(
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Get upsell opportunities grouped by type (Super Admin only)."""
    service = UpsellService(db)
    by_type = await service.get_opportunities_by_type()
    return {"by_type": by_type}


@router.get("/{opportunity_id}", response_model=UpsellOpportunityResponse)
async def get_upsell_opportunity(
    opportunity_id: uuid.UUID,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Get a specific upsell opportunity (Super Admin only)."""
    service = UpsellService(db)
    opportunity = await service.get_opportunity(opportunity_id)
    
    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upsell opportunity not found",
        )
    
    return _format_upsell_opportunity(opportunity)


@router.put("/{opportunity_id}/status", response_model=UpsellOpportunityResponse)
async def update_opportunity_status(
    opportunity_id: uuid.UUID,
    request: UpdateStatusRequest,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Update upsell opportunity status (Super Admin only)."""
    service = UpsellService(db)
    
    try:
        opportunity = await service.update_status(
            opportunity_id=opportunity_id,
            status=request.status,
            actual_mrr_increase=request.actual_mrr_increase,
            lost_reason=request.lost_reason,
        )
        return _format_upsell_opportunity(opportunity)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{opportunity_id}/assign", response_model=UpsellOpportunityResponse)
async def assign_opportunity(
    opportunity_id: uuid.UUID,
    request: AssignOpportunityRequest,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Assign an upsell opportunity (Super Admin only)."""
    service = UpsellService(db)
    
    try:
        opportunity = await service.assign_opportunity(
            opportunity_id=opportunity_id,
            assigned_to_id=request.assigned_to_id,
        )
        return _format_upsell_opportunity(opportunity)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{opportunity_id}/activities")
async def add_activity(
    opportunity_id: uuid.UUID,
    request: AddActivityRequest,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Add an activity to an upsell opportunity (Super Admin only)."""
    service = UpsellService(db)
    
    try:
        activity = await service.add_activity(
            opportunity_id=opportunity_id,
            activity_type=request.activity_type,
            description=request.description,
            staff_id=current_user.id,
            outcome=request.outcome,
            next_action=request.next_action,
            next_action_date=request.next_action_date,
        )
        return {
            "id": str(activity.id),
            "activity_type": activity.activity_type,
            "description": activity.description,
            "outcome": activity.outcome,
            "next_action": activity.next_action,
            "created_at": activity.created_at.isoformat() if activity.created_at else None,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/{opportunity_id}/activities")
async def get_activities(
    opportunity_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Get activities for an upsell opportunity (Super Admin only)."""
    service = UpsellService(db)
    
    # Verify opportunity exists
    opportunity = await service.get_opportunity(opportunity_id)
    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upsell opportunity not found",
        )
    
    activities = await service.get_activities(opportunity_id, limit=limit)
    
    return {
        "activities": [
            {
                "id": str(a.id),
                "activity_type": a.activity_type,
                "description": a.description,
                "outcome": a.outcome,
                "next_action": a.next_action,
                "next_action_date": a.next_action_date.isoformat() if a.next_action_date else None,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in activities
        ],
        "total": len(activities),
    }


def _format_upsell_opportunity(opportunity) -> dict:
    """Format upsell opportunity for response."""
    return {
        "id": opportunity.id,
        "opportunity_code": opportunity.opportunity_code,
        "organization_id": opportunity.organization_id,
        "upsell_type": opportunity.upsell_type.value if opportunity.upsell_type else None,
        "signal": opportunity.signal.value if opportunity.signal else None,
        "status": opportunity.status.value if opportunity.status else None,
        "priority": opportunity.priority.value if opportunity.priority else None,
        "title": opportunity.title,
        "description": opportunity.description,
        "estimated_mrr_increase": float(opportunity.estimated_mrr_increase) if opportunity.estimated_mrr_increase else 0,
        "estimated_arr_increase": float(opportunity.estimated_arr_increase) if opportunity.estimated_arr_increase else 0,
        "actual_mrr_increase": float(opportunity.actual_mrr_increase) if opportunity.actual_mrr_increase else None,
        "current_product": opportunity.current_product,
        "target_product": opportunity.target_product,
        "assigned_to_id": opportunity.assigned_to_id,
        "confidence_score": opportunity.confidence_score,
        "identified_at": opportunity.identified_at.isoformat() if opportunity.identified_at else None,
        "closed_at": opportunity.closed_at.isoformat() if opportunity.closed_at else None,
        "created_at": opportunity.created_at.isoformat() if opportunity.created_at else None,
    }
