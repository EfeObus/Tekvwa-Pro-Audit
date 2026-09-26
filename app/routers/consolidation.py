"""
Tekvwa Pro Audit - Multi-Entity Consolidation Router

API endpoints for consolidated financial statements and multi-entity management.
Implements IFRS 10/11/28 consolidation requirements.
"""

from datetime import date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.dependencies import (
    get_current_user,
    get_current_entity_id,
    require_feature,
    require_entity_access,
    require_group_access,
)
from app.models.user import User
from app.models.entity import BusinessEntity
from app.models.advanced_accounting import EntityGroup
from app.services.consolidation_service import ConsolidationService
from app.services.feature_flags import Feature


router = APIRouter(
    prefix="/api/v1/consolidation",
    tags=["Consolidation"],
    dependencies=[Depends(require_feature([Feature.CONSOLIDATION]))]
)


# ============================================================================
# Schemas
# ============================================================================

class EntityGroupCreate(BaseModel):
    """Create an entity group for consolidation."""
    name: str = Field(..., min_length=1, max_length=255)
    parent_entity_id: UUID
    consolidation_currency: str = Field(default="NGN", max_length=3)
    fiscal_year_end_month: int = Field(default=12, ge=1, le=12)
    description: Optional[str] = None


class EntityGroupResponse(BaseModel):
    """Entity group response."""
    id: UUID
    organization_id: UUID
    name: str
    parent_entity_id: UUID
    consolidation_currency: str
    fiscal_year_end_month: int
    description: Optional[str]
    is_active: bool
    
    model_config = ConfigDict(from_attributes=True)


class GroupMemberAdd(BaseModel):
    """Add a member to an entity group."""
    entity_id: UUID
    ownership_percentage: Decimal = Field(..., ge=0, le=100)
    consolidation_method: str = Field(default="full", description="full, proportional, or equity")


class GroupMemberResponse(BaseModel):
    """Group member response."""
    id: str
    entity_id: str
    entity_name: str
    ownership_percentage: float
    consolidation_method: str
    is_parent: bool


class EliminationEntryCreate(BaseModel):
    """Create an elimination journal entry."""
    elimination_type: str
    description: str
    lines: List[dict]
    as_of_date: date


class ConsolidatedReportRequest(BaseModel):
    """Request for consolidated reports."""
    as_of_date: date
    include_eliminations: bool = True
    include_minority_interest: bool = True


# ============================================================================
# Entity Group Management Endpoints
# ============================================================================

async def get_organization_id_from_entity(
    entity_id: UUID,
    db: AsyncSession
) -> UUID:
    """Helper to get organization_id from entity."""
    result = await db.execute(
        select(BusinessEntity.organization_id).where(BusinessEntity.id == entity_id)
    )
    org_id = result.scalar_one_or_none()
    if not org_id:
        raise HTTPException(status_code=404, detail="Entity not found")
    return org_id


@router.post("/groups", response_model=EntityGroupResponse)
async def create_entity_group(
    data: EntityGroupCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: UUID = Depends(get_current_entity_id)
):
    """
    Create a new entity group for consolidation.
    
    An entity group represents a parent-subsidiary structure for
    consolidated financial statement preparation.
    """
    organization_id = await get_organization_id_from_entity(entity_id, db)
    service = ConsolidationService(db)
    
    group = await service.create_entity_group(
        organization_id=organization_id,
        name=data.name,
        parent_entity_id=data.parent_entity_id,
        consolidation_currency=data.consolidation_currency,
        fiscal_year_end_month=data.fiscal_year_end_month,
        description=data.description
    )
    
    return EntityGroupResponse.model_validate(group)


@router.get("/groups", response_model=List[EntityGroupResponse])
async def list_entity_groups(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: UUID = Depends(get_current_entity_id)
):
    """List all entity groups for the organization."""
    organization_id = await get_organization_id_from_entity(entity_id, db)
    service = ConsolidationService(db)
    groups = await service.get_entity_groups_for_org(organization_id)
    return [EntityGroupResponse.model_validate(g) for g in groups]


@router.get("/groups/{group_id}")
async def get_entity_group(
    group_id: UUID,
    _group_access: EntityGroup = Depends(require_group_access),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get details of a specific entity group."""
    service = ConsolidationService(db)
    
    group = await service.get_entity_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Entity group not found")
    
    members = await service.get_group_members(group_id)
    
    return {
        "id": str(group.id),
        "name": group.name,
        "organization_id": str(group.organization_id),
        "parent_entity_id": str(group.parent_entity_id),
        "consolidation_currency": group.consolidation_currency,
        "fiscal_year_end_month": group.fiscal_year_end_month,
        "description": group.description,
        "is_active": group.is_active,
        "members": members
    }


@router.post("/groups/{group_id}/members", response_model=GroupMemberResponse)
async def add_group_member(
    group_id: UUID,
    data: GroupMemberAdd,
    _group_access: EntityGroup = Depends(require_group_access),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Add an entity as a member of the consolidation group.
    
    The consolidation method is automatically determined based on ownership:
    - >50%: Full consolidation (subsidiaries)
    - 20-50%: Equity method (associates) or proportional (joint ventures)
    - <20%: Equity method (investments)
    """
    service = ConsolidationService(db)
    
    # Verify group exists
    group = await service.get_entity_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Entity group not found")
    
    member = await service.add_group_member(
        group_id=group_id,
        entity_id=data.entity_id,
        ownership_percentage=data.ownership_percentage,
        consolidation_method=data.consolidation_method
    )
    
    return {
        "id": str(member.id),
        "entity_id": str(member.entity_id),
        "entity_name": "",  # Would need to fetch
        "ownership_percentage": float(member.ownership_percentage),
        "consolidation_method": member.consolidation_method,
        "is_parent": member.is_parent
    }


@router.get("/groups/{group_id}/members", response_model=List[GroupMemberResponse])
async def list_group_members(
    group_id: UUID,
    _group_access: EntityGroup = Depends(require_group_access),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all members of an entity group."""
    service = ConsolidationService(db)
    return await service.get_group_members(group_id)


# ============================================================================
# Consolidated Financial Statements
# ============================================================================

@router.get("/groups/{group_id}/trial-balance")
async def get_consolidated_trial_balance(
    group_id: UUID,
    as_of_date: date = Query(default=None),
    include_eliminations: bool = Query(default=True),
    _group_access: EntityGroup = Depends(require_group_access),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate consolidated trial balance for the entity group.
    
    This aggregates trial balances from all member entities,
    applies ownership percentages, and generates elimination entries.
    
    Parameters:
    - as_of_date: Date for the trial balance (defaults to today)
    - include_eliminations: Whether to apply intercompany eliminations
    
    Returns consolidated trial balance with:
    - Aggregated account balances
    - Entity-by-entity contributions
    - Elimination entries
    - Minority interest calculations
    """
    if not as_of_date:
        as_of_date = date.today()
    
    service = ConsolidationService(db)
    
    try:
        result = await service.get_consolidated_trial_balance(
            group_id=group_id,
            as_of_date=as_of_date,
            include_eliminations=include_eliminations
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/groups/{group_id}/balance-sheet")
async def get_consolidated_balance_sheet(
    group_id: UUID,
    as_of_date: date = Query(default=None),
    _group_access: EntityGroup = Depends(require_group_access),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate consolidated balance sheet.
    
    Presents the financial position of the group as if it were
    a single economic entity, including:
    - Consolidated assets (current and non-current)
    - Consolidated liabilities (current and non-current)
    - Equity attributable to owners of the parent
    - Non-controlling (minority) interests
    
    Compliant with IFRS 10 presentation requirements.
    """
    if not as_of_date:
        as_of_date = date.today()
    
    service = ConsolidationService(db)
    
    try:
        return await service.get_consolidated_balance_sheet(
            group_id=group_id,
            as_of_date=as_of_date
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/groups/{group_id}/income-statement")
async def get_consolidated_income_statement(
    group_id: UUID,
    start_date: date = Query(...),
    end_date: date = Query(...),
    _group_access: EntityGroup = Depends(require_group_access),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate consolidated income statement for a period.
    
    Shows the combined results of operations for the group:
    - Revenue (net of intercompany sales)
    - Cost of goods sold (net of intercompany purchases)
    - Operating expenses
    - Net income attributable to:
      - Owners of the parent
      - Non-controlling interests
    
    Compliant with IFRS 10 presentation requirements.
    """
    service = ConsolidationService(db)
    
    try:
        return await service.get_consolidated_income_statement(
            group_id=group_id,
            start_date=start_date,
            end_date=end_date
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/groups/{group_id}/cash-flow-statement")
async def get_consolidated_cash_flow_statement(
    group_id: UUID,
    start_date: date = Query(...),
    end_date: date = Query(...),
    _group_access: EntityGroup = Depends(require_group_access),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate consolidated statement of cash flows (indirect method).
    
    Shows cash flows from:
    - Operating activities
    - Investing activities
    - Financing activities
    
    Net of intercompany cash flows per IFRS 10.
    """
    service = ConsolidationService(db)
    
    try:
        return await service.get_consolidated_cash_flow_statement(
            group_id=group_id,
            start_date=start_date,
            end_date=end_date
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================================
# Consolidation Worksheet & Reports
# ============================================================================

@router.get("/groups/{group_id}/worksheet")
async def get_consolidation_worksheet(
    group_id: UUID,
    as_of_date: date = Query(default=None),
    _group_access: EntityGroup = Depends(require_group_access),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate full consolidation worksheet.
    
    The worksheet shows:
    - Individual entity columns with trial balance data
    - Elimination entries column
    - Consolidated totals column
    
    This is useful for audit trail and review of consolidation adjustments.
    """
    if not as_of_date:
        as_of_date = date.today()
    
    service = ConsolidationService(db)
    
    try:
        return await service.get_consolidation_worksheet(
            group_id=group_id,
            as_of_date=as_of_date
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/groups/{group_id}/segment-report")
async def get_segment_report(
    group_id: UUID,
    start_date: date = Query(...),
    end_date: date = Query(...),
    segment_by: str = Query(default="entity", description="entity, geography, or business_line"),
    _group_access: EntityGroup = Depends(require_group_access),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate segment reporting per IFRS 8.
    
    Provides disaggregated information about:
    - Revenue by segment
    - Operating profit by segment
    - Assets by segment
    
    Segments can be based on:
    - Entity (each subsidiary as a segment)
    - Geography (by operating region)
    - Business line (by product/service category)
    """
    service = ConsolidationService(db)
    
    try:
        return await service.get_segment_reporting(
            group_id=group_id,
            start_date=start_date,
            end_date=end_date,
            segment_by=segment_by
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================================
# Elimination Entries
# ============================================================================

@router.post("/groups/{group_id}/eliminations")
async def create_elimination_entry(
    group_id: UUID,
    data: EliminationEntryCreate,
    _group_access: EntityGroup = Depends(require_group_access),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a manual elimination journal entry.
    
    Use this for:
    - Complex eliminations not auto-generated
    - Unrealized profit adjustments
    - Investment elimination entries
    - Goodwill adjustments
    
    Note: These entries are for consolidation purposes only
    and do not affect individual entity books.
    """
    service = ConsolidationService(db)
    
    try:
        return await service.create_elimination_journal_entry(
            group_id=group_id,
            elimination_type=data.elimination_type,
            lines=data.lines,
            as_of_date=data.as_of_date,
            description=data.description,
            created_by_id=current_user.id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/groups/{group_id}/eliminations")
async def list_elimination_entries(
    group_id: UUID,
    as_of_date: date = Query(default=None),
    _group_access: EntityGroup = Depends(require_group_access),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List auto-generated elimination entries for review.
    
    Shows all intercompany transactions that need to be eliminated
    during consolidation, grouped by type.
    """
    if not as_of_date:
        as_of_date = date.today()
    
    service = ConsolidationService(db)
    eliminations = await service._generate_elimination_entries(group_id, as_of_date)
    
    return {
        "group_id": str(group_id),
        "as_of_date": as_of_date.isoformat(),
        "eliminations": eliminations,
        "total_elimination_amount": sum(e.get("amount", 0) for e in eliminations)
    }


# ============================================================================
# Currency Translation (for foreign subsidiaries)
# ============================================================================

@router.get("/groups/{group_id}/currency-translation")
async def get_currency_translation_report(
    group_id: UUID,
    entity_id: UUID = Query(...),
    functional_currency: str = Query(..., description="Entity's functional currency"),
    presentation_currency: str = Query(default="NGN", description="Group presentation currency"),
    as_of_date: date = Query(default=None),
    _group_access: EntityGroup = Depends(require_group_access),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _entity_access: BusinessEntity = Depends(require_entity_access),
):
    """
    Generate currency translation report for foreign subsidiary per IAS 21.
    
    Translation method:
    - Assets/Liabilities: Closing rate at balance sheet date
    - Income/Expenses: Average rate for the period
    - Equity: Historical rates
    
    Translation differences are recognized in other comprehensive income
    (cumulative translation adjustment - CTA).
    """
    if not as_of_date:
        as_of_date = date.today()
    
    service = ConsolidationService(db)
    
    return await service.translate_foreign_subsidiary(
        entity_id=entity_id,
        functional_currency=functional_currency,
        presentation_currency=presentation_currency,
        exchange_rate_date=as_of_date
    )


# ============================================================================
# Minority Interest
# ============================================================================

@router.get("/groups/{group_id}/minority-interest")
async def get_minority_interest_report(
    group_id: UUID,
    as_of_date: date = Query(default=None),
    _group_access: EntityGroup = Depends(require_group_access),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate minority (non-controlling) interest report.
    
    Shows:
    - Minority interest in net assets by subsidiary
    - Minority share of current period profit/loss
    - Cumulative minority interest balance
    
    Per IFRS 10, non-controlling interests are presented in equity,
    separately from equity attributable to owners of the parent.
    """
    if not as_of_date:
        as_of_date = date.today()
    
    service = ConsolidationService(db)
    
    try:
        trial_balance = await service.get_consolidated_trial_balance(
            group_id=group_id,
            as_of_date=as_of_date
        )
        return {
            "group_id": str(group_id),
            "as_of_date": as_of_date.isoformat(),
            "minority_interest": trial_balance.get("minority_interest", {})
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================================
# CTA (Cumulative Translation Adjustment) Tracking - IAS 21 / OCI
# ============================================================================

@router.get("/groups/{group_id}/translation-history")
async def get_translation_history(
    group_id: UUID,
    entity_id: Optional[UUID] = Query(default=None, description="Filter by specific entity"),
    start_date: Optional[date] = Query(default=None, description="Start date for history"),
    end_date: Optional[date] = Query(default=None, description="End date for history"),
    _group_access: EntityGroup = Depends(require_group_access),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get currency translation history for OCI reporting.
    
    Returns historical CTA movements showing:
    - Translation dates and rates used
    - Pre/post translation amounts
    - Period and cumulative translation adjustments
    
    IAS 21 Compliance:
    - Full audit trail of translation adjustments
    - Supports year-over-year CTA movement analysis
    """
    if entity_id is not None:
        # entity_id is an optional filter here (unlike the other group_id endpoints, which take a
        # required entity_id), so require_entity_access can't be used as a Depends() -- it would make
        # the parameter mandatory. Check inline instead, same 404-on-mismatch contract.
        await require_entity_access(entity_id=entity_id, current_user=current_user, db=db)

    service = ConsolidationService(db)

    try:
        history = await service.get_translation_history(
            group_id=group_id,
            entity_id=entity_id,
            start_date=start_date,
            end_date=end_date,
        )
        return {
            "group_id": str(group_id),
            "entity_id": str(entity_id) if entity_id else None,
            "period": {
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
            },
            "translation_records": history,
            "record_count": len(history),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/groups/{group_id}/oci-cta-report")
async def get_oci_cta_report(
    group_id: UUID,
    as_of_date: date = Query(default=None, description="Reporting date"),
    comparative_date: Optional[date] = Query(default=None, description="Prior period date for comparison"),
    _group_access: EntityGroup = Depends(require_group_access),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate OCI report for Cumulative Translation Adjustments.
    
    Per IAS 1, this report shows:
    - Beginning CTA balance
    - Current period translation movement
    - Ending CTA balance
    - Breakdown by foreign subsidiary
    
    The CTA is classified as "items that may be reclassified to profit or loss"
    and is recycled upon disposal of the foreign operation.
    """
    if not as_of_date:
        as_of_date = date.today()
    
    service = ConsolidationService(db)
    
    try:
        return await service.get_oci_cta_report(
            group_id=group_id,
            as_of_date=as_of_date,
            comparative_date=comparative_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/groups/{group_id}/cta-disposal")
async def recycle_cta_on_disposal(
    group_id: UUID,
    entity_id: UUID = Query(..., description="Entity being disposed"),
    disposal_date: date = Query(..., description="Date of disposal"),
    disposal_percentage: float = Query(default=100, ge=0, le=100, description="% being disposed"),
    _group_access: EntityGroup = Depends(require_group_access),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _entity_access: BusinessEntity = Depends(require_entity_access),
):
    """
    Recycle CTA to profit/loss on disposal of foreign subsidiary.
    
    IAS 21 para 48-49 requires:
    - Full disposal: 100% of CTA recycled to P&L
    - Partial disposal (loss of control): Proportionate recycling
    
    Journal Entry Created:
    - Dr: CTA (OCI/Equity)
    - Cr: FX Gain/Loss (P&L)
    (or vice versa if CTA was negative)
    """
    service = ConsolidationService(db)
    
    try:
        return await service.recycle_cta_on_disposal(
            group_id=group_id,
            entity_id=entity_id,
            disposal_date=disposal_date,
            disposal_percentage=Decimal(str(disposal_percentage)),
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/groups/{group_id}/translate-subsidiaries")
async def translate_all_subsidiaries(
    group_id: UUID,
    translation_date: date = Query(default=None, description="Translation date (defaults to today)"),
    _group_access: EntityGroup = Depends(require_group_access),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Translate all foreign currency subsidiaries in the group.
    
    This is typically run at period-end to update:
    - Balance sheet items at closing rate
    - Income statement items at average rate
    - Equity items at historical rate
    
    Translation adjustments are recorded in OCI (CTA).
    """
    if not translation_date:
        translation_date = date.today()
    
    service = ConsolidationService(db)
    
    try:
        return await service.translate_all_subsidiaries(
            group_id=group_id,
            translation_date=translation_date,
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
