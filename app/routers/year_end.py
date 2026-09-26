"""
Tekvwa Pro Audit - Year-End Closing Router

API endpoints for fiscal year-end closing operations including:
- Year-end checklist validation
- Closing entries generation
- Period locking/unlocking
- Opening balance creation
- Year-end summary reports
"""

import uuid
from datetime import date
from typing import Optional, List
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.dependencies import get_current_user, get_current_entity_id, require_feature, require_entity_access
from app.models.user import User
from app.models.entity import BusinessEntity
from app.models.sku import Feature
from app.services.year_end_closing_service import YearEndClosingService

# Feature gate for year-end closing (PROFESSIONAL tier - advanced reports)
year_end_feature_gate = require_feature([Feature.ADVANCED_REPORTS])

router = APIRouter(
    prefix="/api/v1/year-end",
    tags=["Year-End Closing"],
    dependencies=[Depends(year_end_feature_gate)],
)


# =============================================================================
# SCHEMAS
# =============================================================================

class ChecklistResponse(BaseModel):
    """Year-end checklist response"""
    fiscal_year: dict
    checks: List[dict]
    warnings: List[str]
    blocking_issues: List[str]
    can_close: bool
    summary: dict


class GenerateClosingEntriesRequest(BaseModel):
    """Request to generate closing entries"""
    fiscal_year_id: uuid.UUID
    closing_date: date


class ClosingEntriesResponse(BaseModel):
    """Response from closing entries generation"""
    fiscal_year_id: str
    fiscal_year_name: str
    closing_date: str
    summary: dict
    closing_entries: List[dict]
    accounts_closed: dict
    status: str
    next_step: str


class CloseFiscalYearRequest(BaseModel):
    """Request to close fiscal year"""
    fiscal_year_id: uuid.UUID
    force_close: bool = Field(default=False, description="Force close even with blocking issues")


class CloseFiscalYearResponse(BaseModel):
    """Response from closing fiscal year"""
    success: bool
    message: str
    fiscal_year_id: Optional[str] = None
    fiscal_year_name: Optional[str] = None
    closed_at: Optional[str] = None
    closing_entries_posted: Optional[int] = None
    warnings: Optional[List[str]] = None
    blocking_issues: Optional[List[str]] = None


class CreateOpeningBalancesRequest(BaseModel):
    """Request to create opening balances"""
    new_fiscal_year_id: uuid.UUID
    prior_fiscal_year_id: uuid.UUID


class OpeningBalancesResponse(BaseModel):
    """Response from creating opening balances"""
    success: bool
    message: str
    entry_id: Optional[str] = None
    entry_number: Optional[str] = None
    total_debits: Optional[float] = None
    total_credits: Optional[float] = None
    accounts_carried_forward: Optional[int] = None
    is_balanced: Optional[bool] = None


class LockPeriodRequest(BaseModel):
    """Request to lock a period"""
    period_id: uuid.UUID
    lock_reason: Optional[str] = None


class UnlockPeriodRequest(BaseModel):
    """Request to unlock a period"""
    period_id: uuid.UUID
    unlock_reason: str = Field(..., min_length=10, description="Reason for unlocking (min 10 chars)")


class PeriodLockResponse(BaseModel):
    """Response from period lock/unlock"""
    success: bool
    period_id: str
    period_name: str
    is_locked: bool
    message: str
    locked_at: Optional[str] = None
    unlock_reason: Optional[str] = None


class LockedPeriod(BaseModel):
    """Locked period info"""
    period_id: str
    period_name: str
    start_date: str
    end_date: str
    locked_at: Optional[str]
    locked_by_id: Optional[str]


class YearEndSummaryResponse(BaseModel):
    """Year-end summary report response"""
    fiscal_year: dict
    financial_highlights: dict
    activity_summary: dict
    period_summary: List[dict]
    closing_status: dict
    generated_at: str


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def resolve_and_verify_entity_id(
    db: AsyncSession,
    entity_id: Optional[uuid.UUID],
    user: User,
) -> uuid.UUID:
    """
    Resolve entity_id from the parameter or the user's own organization, verifying access either way.

    Replaces the deleted `resolve_entity_id` (Finding 18, docs/IMPLEMENTATION_ROADMAP.md Phase 2
    Section 2.1) -- a confirmed fake safety net that returned a caller-supplied entity_id completely
    unvalidated, only checking anything on the fallback path (no entity_id given at all). Uses
    `require_entity_access` for the same access-check consistency as every other migrated router;
    entity_id is optional here (unlike a plain path param elsewhere), so this can't be a Depends().
    """
    if entity_id is not None:
        entity = await require_entity_access(entity_id=entity_id, current_user=user, db=db)
        return entity.id

    if user.organization_id:
        result = await db.execute(
            select(BusinessEntity).where(
                BusinessEntity.organization_id == user.organization_id
            ).limit(1)
        )
        entity = result.scalar_one_or_none()
        if entity:
            return entity.id

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Entity ID is required"
    )


# =============================================================================
# ENDPOINTS - CHECKLIST
# =============================================================================

@router.get(
    "/checklist/{fiscal_year_id}",
    response_model=ChecklistResponse,
    summary="Get Year-End Checklist",
    description="Get comprehensive year-end closing checklist with validation"
)
async def get_year_end_checklist(
    fiscal_year_id: uuid.UUID,
    entity_id: Optional[uuid.UUID] = Query(None, description="Entity ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    
):
    """Get year-end closing checklist."""
    try:
        resolved_entity_id = await resolve_and_verify_entity_id(db, entity_id, current_user)
        service = YearEndClosingService(db)
        
        checklist = await service.get_year_end_checklist(
            entity_id=resolved_entity_id,
            fiscal_year_id=fiscal_year_id
        )
        
        return checklist
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# =============================================================================
# ENDPOINTS - CLOSING ENTRIES
# =============================================================================

@router.post(
    "/closing-entries",
    response_model=ClosingEntriesResponse,
    summary="Generate Closing Entries",
    description="Generate year-end closing journal entries"
)
async def generate_closing_entries(
    request: GenerateClosingEntriesRequest,
    entity_id: Optional[uuid.UUID] = Query(None, description="Entity ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    
):
    """Generate closing entries for year-end."""
    try:
        resolved_entity_id = await resolve_and_verify_entity_id(db, entity_id, current_user)
        service = YearEndClosingService(db)
        
        result = await service.generate_closing_entries(
            entity_id=resolved_entity_id,
            fiscal_year_id=request.fiscal_year_id,
            closing_date=request.closing_date,
            created_by_id=current_user.id
        )
        
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/closing-entries/{fiscal_year_id}",
    summary="Get Closing Entries",
    description="Get existing closing entries for a fiscal year"
)
async def get_closing_entries(
    fiscal_year_id: uuid.UUID,
    entity_id: Optional[uuid.UUID] = Query(None, description="Entity ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    
):
    """Get existing closing entries for a fiscal year."""
    from sqlalchemy import select, and_
    from app.models.accounting import JournalEntry, JournalEntryType, FiscalYear
    
    try:
        resolved_entity_id = await resolve_and_verify_entity_id(db, entity_id, current_user)
        
        # Get fiscal year
        fy_result = await db.execute(
            select(FiscalYear).where(FiscalYear.id == fiscal_year_id)
        )
        fiscal_year = fy_result.scalar_one_or_none()
        
        if not fiscal_year:
            raise HTTPException(status_code=404, detail="Fiscal year not found")
        
        # Get closing entries
        result = await db.execute(
            select(JournalEntry).where(
                and_(
                    JournalEntry.entity_id == resolved_entity_id,
                    JournalEntry.entry_type == JournalEntryType.CLOSING_ENTRY,
                    JournalEntry.entry_date >= fiscal_year.start_date,
                    JournalEntry.entry_date <= fiscal_year.end_date
                )
            ).order_by(JournalEntry.entry_date)
        )
        entries = list(result.scalars().all())
        
        return {
            "fiscal_year_id": str(fiscal_year_id),
            "fiscal_year_name": fiscal_year.year_name,
            "closing_entries": [
                {
                    "id": str(e.id),
                    "entry_number": e.entry_number,
                    "entry_date": e.entry_date.isoformat(),
                    "description": e.description,
                    "status": e.status.value,
                    "total_amount": float(e.total_amount) if e.total_amount else 0
                }
                for e in entries
            ],
            "total_entries": len(entries)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# =============================================================================
# ENDPOINTS - CLOSE FISCAL YEAR
# =============================================================================

@router.post(
    "/close-fiscal-year",
    response_model=CloseFiscalYearResponse,
    summary="Close Fiscal Year",
    description="Close a fiscal year after all validations pass"
)
async def close_fiscal_year(
    request: CloseFiscalYearRequest,
    entity_id: Optional[uuid.UUID] = Query(None, description="Entity ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    
):
    """Close a fiscal year."""
    try:
        resolved_entity_id = await resolve_and_verify_entity_id(db, entity_id, current_user)
        service = YearEndClosingService(db)
        
        result = await service.close_fiscal_year(
            entity_id=resolved_entity_id,
            fiscal_year_id=request.fiscal_year_id,
            closed_by_id=current_user.id,
            force_close=request.force_close
        )
        
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/reopen-fiscal-year/{fiscal_year_id}",
    summary="Reopen Fiscal Year",
    description="Reopen a closed fiscal year (requires admin permission)"
)
async def reopen_fiscal_year(
    fiscal_year_id: uuid.UUID,
    reopen_reason: str = Query(..., min_length=20, description="Reason for reopening (min 20 chars)"),
    entity_id: Optional[uuid.UUID] = Query(None, description="Entity ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    
):
    """Reopen a closed fiscal year."""
    from sqlalchemy import select, and_
    from app.models.accounting import FiscalYear

    try:
        resolved_entity_id = await resolve_and_verify_entity_id(db, entity_id, current_user)

        # Get fiscal year (scoped to the verified entity -- this endpoint previously accepted
        # entity_id but never used it for anything, letting any fiscal_year_id be reopened
        # regardless of which organization it actually belonged to)
        result = await db.execute(
            select(FiscalYear).where(
                and_(
                    FiscalYear.id == fiscal_year_id,
                    FiscalYear.entity_id == resolved_entity_id,
                )
            )
        )
        fiscal_year = result.scalar_one_or_none()
        
        if not fiscal_year:
            raise HTTPException(status_code=404, detail="Fiscal year not found")
        
        if not fiscal_year.is_closed:
            raise HTTPException(status_code=400, detail="Fiscal year is not closed")
        
        # Reopen
        fiscal_year.is_closed = False
        fiscal_year.closed_at = None
        fiscal_year.closed_by_id = None
        
        await db.commit()
        
        return {
            "success": True,
            "fiscal_year_id": str(fiscal_year_id),
            "fiscal_year_name": fiscal_year.year_name,
            "reopen_reason": reopen_reason,
            "reopened_by_id": str(current_user.id),
            "message": f"Fiscal year {fiscal_year.year_name} has been reopened"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# =============================================================================
# ENDPOINTS - OPENING BALANCES
# =============================================================================

@router.post(
    "/opening-balances",
    response_model=OpeningBalancesResponse,
    summary="Create Opening Balances",
    description="Create opening balance entries for new fiscal year"
)
async def create_opening_balances(
    request: CreateOpeningBalancesRequest,
    entity_id: Optional[uuid.UUID] = Query(None, description="Entity ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    
):
    """Create opening balances for new fiscal year."""
    try:
        resolved_entity_id = await resolve_and_verify_entity_id(db, entity_id, current_user)
        service = YearEndClosingService(db)
        
        result = await service.create_opening_balances(
            entity_id=resolved_entity_id,
            new_fiscal_year_id=request.new_fiscal_year_id,
            prior_fiscal_year_id=request.prior_fiscal_year_id,
            created_by_id=current_user.id
        )
        
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/opening-balances/{fiscal_year_id}",
    summary="Get Opening Balances",
    description="Get opening balance entry for a fiscal year"
)
async def get_opening_balances(
    fiscal_year_id: uuid.UUID,
    entity_id: Optional[uuid.UUID] = Query(None, description="Entity ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    
):
    """Get opening balance entry for a fiscal year."""
    from sqlalchemy import select, and_
    from app.models.accounting import JournalEntry, JournalEntryLine, JournalEntryType, FiscalYear
    
    try:
        resolved_entity_id = await resolve_and_verify_entity_id(db, entity_id, current_user)
        
        # Get fiscal year
        fy_result = await db.execute(
            select(FiscalYear).where(FiscalYear.id == fiscal_year_id)
        )
        fiscal_year = fy_result.scalar_one_or_none()
        
        if not fiscal_year:
            raise HTTPException(status_code=404, detail="Fiscal year not found")
        
        # Get opening balance entry
        result = await db.execute(
            select(JournalEntry).where(
                and_(
                    JournalEntry.entity_id == resolved_entity_id,
                    JournalEntry.entry_type == JournalEntryType.OPENING_BALANCE,
                    JournalEntry.entry_date == fiscal_year.start_date
                )
            )
        )
        entry = result.scalar_one_or_none()
        
        if not entry:
            return {
                "fiscal_year_id": str(fiscal_year_id),
                "has_opening_balances": False,
                "message": "No opening balance entry found"
            }
        
        # Get lines
        lines_result = await db.execute(
            select(JournalEntryLine).where(
                JournalEntryLine.journal_entry_id == entry.id
            ).order_by(JournalEntryLine.line_number)
        )
        lines = list(lines_result.scalars().all())
        
        return {
            "fiscal_year_id": str(fiscal_year_id),
            "has_opening_balances": True,
            "entry": {
                "id": str(entry.id),
                "entry_number": entry.entry_number,
                "entry_date": entry.entry_date.isoformat(),
                "total_amount": float(entry.total_amount) if entry.total_amount else 0
            },
            "lines_count": len(lines),
            "total_debits": sum(float(l.debit_amount or 0) for l in lines),
            "total_credits": sum(float(l.credit_amount or 0) for l in lines)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# =============================================================================
# ENDPOINTS - PERIOD LOCKING
# =============================================================================

@router.post(
    "/lock-period",
    response_model=PeriodLockResponse,
    summary="Lock Period",
    description="Lock a fiscal period to prevent changes"
)
async def lock_period(
    request: LockPeriodRequest,
    entity_id: Optional[uuid.UUID] = Query(None, description="Entity ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    
):
    """Lock a fiscal period."""
    try:
        resolved_entity_id = await resolve_and_verify_entity_id(db, entity_id, current_user)
        service = YearEndClosingService(db)
        
        result = await service.lock_period(
            entity_id=resolved_entity_id,
            period_id=request.period_id,
            locked_by_id=current_user.id,
            lock_reason=request.lock_reason
        )
        
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/unlock-period",
    response_model=PeriodLockResponse,
    summary="Unlock Period",
    description="Unlock a previously locked period"
)
async def unlock_period(
    request: UnlockPeriodRequest,
    entity_id: Optional[uuid.UUID] = Query(None, description="Entity ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    
):
    """Unlock a fiscal period."""
    try:
        resolved_entity_id = await resolve_and_verify_entity_id(db, entity_id, current_user)
        service = YearEndClosingService(db)
        
        result = await service.unlock_period(
            entity_id=resolved_entity_id,
            period_id=request.period_id,
            unlocked_by_id=current_user.id,
            unlock_reason=request.unlock_reason
        )
        
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/locked-periods",
    response_model=List[LockedPeriod],
    summary="Get Locked Periods",
    description="Get all locked periods for an entity"
)
async def get_locked_periods(
    fiscal_year_id: Optional[uuid.UUID] = Query(None, description="Filter by fiscal year"),
    entity_id: Optional[uuid.UUID] = Query(None, description="Entity ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    
):
    """Get all locked periods."""
    try:
        resolved_entity_id = await resolve_and_verify_entity_id(db, entity_id, current_user)
        service = YearEndClosingService(db)
        
        periods = await service.get_locked_periods(
            entity_id=resolved_entity_id,
            fiscal_year_id=fiscal_year_id
        )
        
        return periods
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# =============================================================================
# ENDPOINTS - REPORTS
# =============================================================================

@router.get(
    "/summary-report/{fiscal_year_id}",
    response_model=YearEndSummaryResponse,
    summary="Get Year-End Summary Report",
    description="Generate comprehensive year-end summary report"
)
async def get_year_end_summary_report(
    fiscal_year_id: uuid.UUID,
    entity_id: Optional[uuid.UUID] = Query(None, description="Entity ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    
):
    """Get year-end summary report."""
    try:
        resolved_entity_id = await resolve_and_verify_entity_id(db, entity_id, current_user)
        service = YearEndClosingService(db)
        
        report = await service.get_year_end_summary_report(
            entity_id=resolved_entity_id,
            fiscal_year_id=fiscal_year_id
        )
        
        return report
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/fiscal-years",
    summary="List Fiscal Years",
    description="List all fiscal years for an entity"
)
async def list_fiscal_years(
    include_closed: bool = Query(True, description="Include closed fiscal years"),
    entity_id: Optional[uuid.UUID] = Query(None, description="Entity ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    
):
    """List all fiscal years."""
    from sqlalchemy import select
    from app.models.accounting import FiscalYear
    
    try:
        resolved_entity_id = await resolve_and_verify_entity_id(db, entity_id, current_user)
        
        query = select(FiscalYear).where(
            FiscalYear.entity_id == resolved_entity_id
        )
        
        if not include_closed:
            query = query.where(FiscalYear.is_closed == False)
        
        result = await db.execute(query.order_by(FiscalYear.start_date.desc()))
        years = list(result.scalars().all())
        
        return {
            "fiscal_years": [
                {
                    "id": str(y.id),
                    "year_name": y.year_name,
                    "start_date": y.start_date.isoformat(),
                    "end_date": y.end_date.isoformat(),
                    "is_closed": y.is_closed,
                    "closed_at": y.closed_at.isoformat() if y.closed_at else None,
                    "is_current": y.start_date <= date.today() <= y.end_date
                }
                for y in years
            ],
            "total": len(years)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/periods/{fiscal_year_id}",
    summary="List Fiscal Periods",
    description="List all periods for a fiscal year"
)
async def list_fiscal_periods(
    fiscal_year_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    
):
    """List all periods in a fiscal year."""
    from sqlalchemy import select
    from app.models.accounting import FiscalPeriod, FiscalYear
    
    try:
        # Verify fiscal year exists
        fy_result = await db.execute(
            select(FiscalYear).where(FiscalYear.id == fiscal_year_id)
        )
        fiscal_year = fy_result.scalar_one_or_none()
        
        if not fiscal_year:
            raise HTTPException(status_code=404, detail="Fiscal year not found")
        
        # Get periods
        result = await db.execute(
            select(FiscalPeriod).where(
                FiscalPeriod.fiscal_year_id == fiscal_year_id
            ).order_by(FiscalPeriod.period_number)
        )
        periods = list(result.scalars().all())
        
        return {
            "fiscal_year": {
                "id": str(fiscal_year.id),
                "year_name": fiscal_year.year_name,
                "is_closed": fiscal_year.is_closed
            },
            "periods": [
                {
                    "id": str(p.id),
                    "period_number": p.period_number,
                    "period_name": p.period_name,
                    "start_date": p.start_date.isoformat(),
                    "end_date": p.end_date.isoformat(),
                    "status": p.status.value,
                    "is_locked": p.is_locked,
                    "is_current": p.start_date <= date.today() <= p.end_date
                }
                for p in periods
            ],
            "summary": {
                "total_periods": len(periods),
                "open_periods": sum(1 for p in periods if p.status.value == "open"),
                "closed_periods": sum(1 for p in periods if p.status.value == "closed"),
                "locked_periods": sum(1 for p in periods if p.is_locked)
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
