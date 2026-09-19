"""
Tekvwa Pro Audit - Advanced Accounting Router

API endpoints that serve as aliases/aggregators for advanced accounting features.
Maps frontend-expected URLs to backend services.
"""

from datetime import date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.advanced_accounting import EntityGroup, EntityGroupMember
from app.services.consolidation_service import ConsolidationService


router = APIRouter(
    prefix="/api/v1/advanced",
    tags=["Advanced Accounting"]
)


# ============================================================================
# Schemas
# ============================================================================

class EntityGroupResponse(BaseModel):
    """Entity group response."""
    id: str
    organization_id: str
    name: str
    parent_entity_id: str
    consolidation_currency: str
    fiscal_year_end_month: int
    description: Optional[str] = None
    is_active: bool
    
    model_config = ConfigDict(from_attributes=True)


class EntityGroupCreate(BaseModel):
    """Create an entity group for consolidation."""
    name: str = Field(..., min_length=1, max_length=255)
    parent_entity_id: UUID
    consolidation_currency: str = Field(default="NGN", max_length=3)
    fiscal_year_end_month: int = Field(default=12, ge=1, le=12)
    description: Optional[str] = None


class GroupMemberResponse(BaseModel):
    """Group member response."""
    id: str
    entity_id: str
    entity_name: str
    ownership_percentage: float
    consolidation_method: str
    is_parent: bool


class GroupMemberAdd(BaseModel):
    """Add a member to an entity group."""
    entity_id: UUID
    ownership_percentage: Decimal = Field(..., ge=0, le=100)
    consolidation_method: str = Field(default="full", description="full, proportional, or equity")


# ============================================================================
# Entity Group Endpoints (Aliased for Frontend Compatibility)
# ============================================================================

@router.get("/entity-groups", response_model=List[EntityGroupResponse])
async def list_entity_groups(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all entity groups for the user's organization.
    
    This endpoint provides backwards compatibility for frontend calls
    that expect /api/v1/advanced/entity-groups
    """
    if not current_user.organization_id:
        return []
    
    try:
        service = ConsolidationService(db)
        groups = await service.get_entity_groups_for_org(current_user.organization_id)
        
        return [
            EntityGroupResponse(
                id=str(group.id),
                organization_id=str(group.organization_id),
                name=group.name,
                parent_entity_id=str(group.parent_entity_id),
                consolidation_currency=group.consolidation_currency or "NGN",
                fiscal_year_end_month=group.fiscal_year_end_month or 12,
                description=group.description,
                is_active=group.is_active
            )
            for group in groups
        ]
    except Exception as e:
        # Return empty list if no groups exist or service fails
        import logging
        logging.warning(f"Error fetching entity groups: {e}")
        return []


@router.post("/entity-groups", response_model=EntityGroupResponse)
async def create_entity_group(
    data: EntityGroupCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new entity group for consolidation."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User must belong to an organization")
    
    service = ConsolidationService(db)
    
    try:
        group = await service.create_entity_group(
            organization_id=current_user.organization_id,
            name=data.name,
            parent_entity_id=data.parent_entity_id,
            consolidation_currency=data.consolidation_currency,
            fiscal_year_end_month=data.fiscal_year_end_month,
            description=data.description,
            created_by=current_user.id
        )
        
        return EntityGroupResponse(
            id=str(group.id),
            organization_id=str(group.organization_id),
            name=group.name,
            parent_entity_id=str(group.parent_entity_id),
            consolidation_currency=group.consolidation_currency or "NGN",
            fiscal_year_end_month=group.fiscal_year_end_month or 12,
            description=group.description,
            is_active=group.is_active
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/entity-groups/{group_id}", response_model=EntityGroupResponse)
async def get_entity_group(
    group_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific entity group."""
    service = ConsolidationService(db)
    group = await service.get_entity_group(group_id)
    
    if not group:
        raise HTTPException(status_code=404, detail="Entity group not found")
    
    # Verify user has access
    if current_user.organization_id and group.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return EntityGroupResponse(
        id=str(group.id),
        organization_id=str(group.organization_id),
        name=group.name,
        parent_entity_id=str(group.parent_entity_id),
        consolidation_currency=group.consolidation_currency or "NGN",
        fiscal_year_end_month=group.fiscal_year_end_month or 12,
        description=group.description,
        is_active=group.is_active
    )


@router.get("/entity-groups/{group_id}/members", response_model=List[GroupMemberResponse])
async def list_group_members(
    group_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all members of an entity group."""
    service = ConsolidationService(db)
    
    # Verify group exists
    group = await service.get_entity_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Entity group not found")
    
    # Verify user has access
    if current_user.organization_id and group.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    members = await service.get_group_members(group_id)
    
    return [
        GroupMemberResponse(
            id=str(member.get("id", "")),
            entity_id=str(member.get("entity_id", "")),
            entity_name=member.get("entity_name", ""),
            ownership_percentage=float(member.get("ownership_percentage", 100)),
            consolidation_method=member.get("consolidation_method", "full"),
            is_parent=member.get("is_parent", False)
        )
        for member in (members if members else [])
    ]


@router.post("/entity-groups/{group_id}/members", response_model=GroupMemberResponse)
async def add_group_member(
    group_id: UUID = Path(...),
    data: GroupMemberAdd = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add a member entity to a group."""
    service = ConsolidationService(db)
    
    # Verify group exists
    group = await service.get_entity_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Entity group not found")
    
    # Verify user has access
    if current_user.organization_id and group.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        member = await service.add_group_member(
            group_id=group_id,
            entity_id=data.entity_id,
            ownership_percentage=data.ownership_percentage,
            consolidation_method=data.consolidation_method
        )
        
        return GroupMemberResponse(
            id=str(member.id) if hasattr(member, 'id') else str(member.get("id", "")),
            entity_id=str(member.entity_id) if hasattr(member, 'entity_id') else str(member.get("entity_id", "")),
            entity_name=member.entity.name if hasattr(member, 'entity') and member.entity else member.get("entity_name", ""),
            ownership_percentage=float(member.ownership_percentage) if hasattr(member, 'ownership_percentage') else float(member.get("ownership_percentage", 100)),
            consolidation_method=member.consolidation_method if hasattr(member, 'consolidation_method') else member.get("consolidation_method", "full"),
            is_parent=member.is_parent if hasattr(member, 'is_parent') else member.get("is_parent", False)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
