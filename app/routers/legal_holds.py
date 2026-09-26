"""
Tekvwa Pro Audit - Legal Holds Router

API endpoints for managing legal holds.
Super Admin only feature for compliance and data preservation.
"""

import uuid
from typing import List, Optional
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import require_super_admin, require_feature
from app.models.user import User
from app.models.legal_hold import LegalHoldStatus, LegalHoldType, DataScope
from app.models.sku import Feature
from app.services.legal_hold_service import LegalHoldService

# Feature gate for legal holds (ENTERPRISE tier - WORM vault access)
legal_holds_feature_gate = require_feature([Feature.WORM_VAULT])

router = APIRouter(
    prefix="/legal-holds",
    tags=["Legal Holds"],
    dependencies=[Depends(legal_holds_feature_gate)],
)


# ===========================================
# REQUEST/RESPONSE SCHEMAS
# ===========================================

class CreateLegalHoldRequest(BaseModel):
    """Request schema for creating a legal hold."""
    organization_id: uuid.UUID
    matter_name: str = Field(..., min_length=1, max_length=255)
    matter_reference: Optional[str] = Field(None, max_length=100)
    hold_type: LegalHoldType
    data_scope: DataScope
    preservation_start_date: date
    preservation_end_date: Optional[date] = None
    legal_counsel_name: Optional[str] = Field(None, max_length=255)
    legal_counsel_email: Optional[str] = Field(None, max_length=255)
    legal_counsel_phone: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None
    internal_notes: Optional[str] = None
    entity_ids: Optional[List[str]] = None


class LegalHoldResponse(BaseModel):
    """Response schema for legal hold."""
    id: uuid.UUID
    hold_number: str
    organization_id: uuid.UUID
    matter_name: str
    matter_reference: Optional[str]
    hold_type: str
    status: str
    data_scope: str
    preservation_start_date: date
    preservation_end_date: Optional[date]
    hold_start_date: Optional[str]
    hold_end_date: Optional[str]
    legal_counsel_name: Optional[str]
    legal_counsel_email: Optional[str]
    description: Optional[str]
    records_preserved_count: Optional[int]
    created_at: str
    
    class Config:
        from_attributes = True


class LegalHoldListResponse(BaseModel):
    """Response schema for legal hold list."""
    holds: List[LegalHoldResponse]
    total: int


class LegalHoldStatsResponse(BaseModel):
    """Response schema for legal hold statistics."""
    active: int
    pending_release: int
    tenants_affected: int
    records_count: int


class ReleaseLegalHoldRequest(BaseModel):
    """Request schema for releasing a legal hold."""
    release_reason: str = Field(..., min_length=1, max_length=1000)


# ===========================================
# API ENDPOINTS
# ===========================================

@router.post("", response_model=LegalHoldResponse, status_code=status.HTTP_201_CREATED)
async def create_legal_hold(
    request: CreateLegalHoldRequest,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Create a new legal hold (Super Admin only)."""
    service = LegalHoldService(db)
    
    try:
        hold = await service.create_legal_hold(
            organization_id=request.organization_id,
            matter_name=request.matter_name,
            hold_type=request.hold_type,
            data_scope=request.data_scope,
            preservation_start_date=request.preservation_start_date,
            created_by_id=current_user.id,
            matter_reference=request.matter_reference,
            preservation_end_date=request.preservation_end_date,
            legal_counsel_name=request.legal_counsel_name,
            legal_counsel_email=request.legal_counsel_email,
            legal_counsel_phone=request.legal_counsel_phone,
            description=request.description,
            internal_notes=request.internal_notes,
            entity_ids=request.entity_ids,
        )
        
        return _format_legal_hold(hold)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("", response_model=LegalHoldListResponse)
async def list_legal_holds(
    status_filter: Optional[LegalHoldStatus] = Query(None, alias="status"),
    organization_id: Optional[uuid.UUID] = None,
    hold_type: Optional[LegalHoldType] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """List all legal holds (Super Admin only)."""
    service = LegalHoldService(db)
    
    holds = await service.get_all_legal_holds(
        status=status_filter,
        organization_id=organization_id,
        hold_type=hold_type,
        limit=limit,
        offset=offset,
    )
    
    return {
        "holds": [_format_legal_hold(h) for h in holds],
        "total": len(holds),
    }


@router.get("/stats", response_model=LegalHoldStatsResponse)
async def get_legal_hold_stats(
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Get legal hold statistics (Super Admin only)."""
    service = LegalHoldService(db)
    stats = await service.get_legal_holds_stats()
    return stats


@router.get("/{hold_id}", response_model=LegalHoldResponse)
async def get_legal_hold(
    hold_id: uuid.UUID,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Get a specific legal hold (Super Admin only)."""
    service = LegalHoldService(db)
    hold = await service.get_legal_hold(hold_id)
    
    if not hold:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Legal hold not found",
        )
    
    return _format_legal_hold(hold)


@router.post("/{hold_id}/request-release", response_model=LegalHoldResponse)
async def request_release(
    hold_id: uuid.UUID,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Request release of a legal hold (Super Admin only)."""
    service = LegalHoldService(db)
    
    try:
        hold = await service.request_release(hold_id)
        return _format_legal_hold(hold)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{hold_id}/release", response_model=LegalHoldResponse)
async def release_legal_hold(
    hold_id: uuid.UUID,
    request: ReleaseLegalHoldRequest,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Release a legal hold (Super Admin only)."""
    service = LegalHoldService(db)
    
    try:
        hold = await service.release_legal_hold(
            hold_id=hold_id,
            released_by_id=current_user.id,
            release_reason=request.release_reason,
        )
        return _format_legal_hold(hold)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/check/{organization_id}")
async def check_organization_hold(
    organization_id: uuid.UUID,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Check if organization has any active legal holds (Super Admin only)."""
    service = LegalHoldService(db)
    has_hold = await service.check_organization_has_hold(organization_id)
    
    return {"organization_id": str(organization_id), "has_active_hold": has_hold}


def _format_legal_hold(hold) -> dict:
    """Format legal hold for response."""
    return {
        "id": hold.id,
        "hold_number": hold.hold_number,
        "organization_id": hold.organization_id,
        "matter_name": hold.matter_name,
        "matter_reference": hold.matter_reference,
        "hold_type": hold.hold_type,
        "status": hold.status,
        "data_scope": hold.data_scope,
        "preservation_start_date": hold.preservation_start_date,
        "preservation_end_date": hold.preservation_end_date,
        "hold_start_date": hold.hold_start_date.isoformat() if hold.hold_start_date else None,
        "hold_end_date": hold.hold_end_date.isoformat() if hold.hold_end_date else None,
        "legal_counsel_name": hold.legal_counsel_name,
        "legal_counsel_email": hold.legal_counsel_email,
        "description": hold.description,
        "records_preserved_count": hold.records_preserved_count,
        "created_at": hold.created_at.isoformat() if hold.created_at else None,
    }
