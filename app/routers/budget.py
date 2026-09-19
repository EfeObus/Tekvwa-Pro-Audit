"""
Tekvwa Pro Audit - Budget Management Router

API endpoints for budget planning, monitoring, and variance analysis.

SKU Requirement: PROFESSIONAL tier or higher (Feature.BUDGET_MANAGEMENT)
"""

from datetime import date
from decimal import Decimal
from typing import List, Optional, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, get_current_entity_id, require_feature
from app.models.user import User
from app.models.sku_enums import Feature
from app.services.budget_service import BudgetService

# Feature gate - requires Professional tier or higher
budget_feature_gate = require_feature([Feature.BUDGET_MANAGEMENT])

router = APIRouter(
    prefix="/api/v1/entities/{entity_id}/budgets",
    tags=["Budget Management"],
    dependencies=[Depends(budget_feature_gate)],
)


# ============================================================================
# Schemas
# ============================================================================

class BudgetCreate(BaseModel):
    """Create a new budget."""
    name: str = Field(..., min_length=1, max_length=255)
    fiscal_year: int = Field(..., ge=2000, le=2100)
    start_date: date
    end_date: date
    period_type: str = Field(default="monthly", description="monthly, quarterly, or annual")
    description: Optional[str] = None


class BudgetUpdate(BaseModel):
    """Update budget properties."""
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class BudgetResponse(BaseModel):
    """Budget response."""
    id: UUID
    entity_id: UUID
    name: str
    description: Optional[str]
    fiscal_year: int
    period_type: str
    start_date: date
    end_date: date
    total_revenue_budget: float
    total_expense_budget: float
    total_capex_budget: float
    status: str
    approved_by_id: Optional[UUID]
    approved_at: Optional[str]
    created_by_id: UUID
    
    model_config = ConfigDict(from_attributes=True)


class BudgetLineItemCreate(BaseModel):
    """Create a budget line item."""
    account_name: str = Field(..., min_length=1)
    line_type: str = Field(..., description="revenue, expense, or capex")
    account_code: Optional[str] = None
    category_id: Optional[UUID] = None
    dimension_id: Optional[UUID] = None
    monthly_amounts: Optional[Dict[str, float]] = None
    total_budget: Optional[float] = None
    notes: Optional[str] = None


class BudgetLineItemUpdate(BaseModel):
    """Update a budget line item."""
    account_name: Optional[str] = None
    account_code: Optional[str] = None
    jan_amount: Optional[float] = None
    feb_amount: Optional[float] = None
    mar_amount: Optional[float] = None
    apr_amount: Optional[float] = None
    may_amount: Optional[float] = None
    jun_amount: Optional[float] = None
    jul_amount: Optional[float] = None
    aug_amount: Optional[float] = None
    sep_amount: Optional[float] = None
    oct_amount: Optional[float] = None
    nov_amount: Optional[float] = None
    dec_amount: Optional[float] = None
    notes: Optional[str] = None


class BudgetLineItemResponse(BaseModel):
    """Budget line item response."""
    id: UUID
    budget_id: UUID
    account_code: Optional[str]
    account_name: str
    line_type: str
    category_id: Optional[UUID]
    dimension_id: Optional[UUID]
    jan_amount: float
    feb_amount: float
    mar_amount: float
    apr_amount: float
    may_amount: float
    jun_amount: float
    jul_amount: float
    aug_amount: float
    sep_amount: float
    oct_amount: float
    nov_amount: float
    dec_amount: float
    total_budget: float
    notes: Optional[str]
    
    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Budget CRUD Endpoints
# ============================================================================

@router.post("", response_model=dict)
async def create_budget(
    data: BudgetCreate,
    entity_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new budget for the entity.
    
    Budgets can be created with different period types:
    - monthly: Monthly budget tracking
    - quarterly: Quarterly budget tracking
    - annual: Annual budget only
    """
    service = BudgetService(db)
    
    budget = await service.create_budget(
        entity_id=entity_id,
        name=data.name,
        fiscal_year=data.fiscal_year,
        start_date=data.start_date,
        end_date=data.end_date,
        created_by_id=current_user.id,
        period_type=data.period_type,
        description=data.description
    )
    
    return {
        "id": str(budget.id),
        "name": budget.name,
        "fiscal_year": budget.fiscal_year,
        "status": budget.status,
        "message": "Budget created successfully"
    }


@router.get("")
async def list_budgets(
    entity_id: UUID = Path(...),
    fiscal_year: Optional[int] = Query(None),
    status: Optional[str] = Query(None, description="draft, submitted, approved, active, closed"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all budgets for the entity."""
    service = BudgetService(db)
    budgets = await service.get_budgets_for_entity(
        entity_id=entity_id,
        fiscal_year=fiscal_year,
        status=status
    )
    
    return {
        "items": [
            {
                "id": str(b.id),
                "name": b.name,
                "fiscal_year": b.fiscal_year,
                "period_type": b.period_type.value if b.period_type else "monthly",
                "start_date": b.start_date.isoformat(),
                "end_date": b.end_date.isoformat(),
                "total_revenue_budget": float(b.total_revenue_budget or 0),
                "total_expense_budget": float(b.total_expense_budget or 0),
                "total_capex_budget": float(b.total_capex_budget or 0),
                "status": b.status
            }
            for b in budgets
        ],
        "total": len(budgets)
    }


@router.get("/active")
async def get_active_budget(
    entity_id: UUID = Path(...),
    as_of_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get the currently active budget for the entity."""
    try:
        service = BudgetService(db)
        budget = await service.get_active_budget(entity_id, as_of_date)
        
        if not budget:
            raise HTTPException(status_code=404, detail="No active budget found")
        
        return {
            "id": str(budget.id),
            "name": budget.name,
            "fiscal_year": budget.fiscal_year,
            "period_type": budget.period_type.value if budget.period_type else "monthly",
            "start_date": budget.start_date.isoformat(),
            "end_date": budget.end_date.isoformat(),
            "total_revenue_budget": float(budget.total_revenue_budget or 0),
            "total_expense_budget": float(budget.total_expense_budget or 0),
            "total_capex_budget": float(budget.total_capex_budget or 0),
            "status": budget.status,
            "line_items_count": len(budget.line_items) if budget.line_items else 0
        }
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error(f"Error getting active budget: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving active budget: {str(e)}")


@router.get("/{budget_id}")
async def get_budget(
    budget_id: UUID = Path(...),
    entity_id: UUID = Path(...),
    include_line_items: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific budget with optional line items."""
    service = BudgetService(db)
    budget = await service.get_budget(budget_id, include_line_items)
    
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    
    response = {
        "id": str(budget.id),
        "entity_id": str(budget.entity_id),
        "name": budget.name,
        "description": budget.description,
        "fiscal_year": budget.fiscal_year,
        "period_type": budget.period_type.value if budget.period_type else "monthly",
        "start_date": budget.start_date.isoformat(),
        "end_date": budget.end_date.isoformat(),
        "total_revenue_budget": float(budget.total_revenue_budget or 0),
        "total_expense_budget": float(budget.total_expense_budget or 0),
        "total_capex_budget": float(budget.total_capex_budget or 0),
        "status": budget.status,
        "approved_by_id": str(budget.approved_by_id) if budget.approved_by_id else None,
        "approved_at": budget.approved_at.isoformat() if budget.approved_at else None,
        "created_by_id": str(budget.created_by_id)
    }
    
    if include_line_items:
        response["line_items"] = [
            {
                "id": str(item.id),
                "account_code": item.account_code,
                "account_name": item.account_name,
                "line_type": item.line_type,
                "category_id": str(item.category_id) if item.category_id else None,
                "dimension_id": str(item.dimension_id) if item.dimension_id else None,
                "monthly_amounts": {
                    "jan": float(item.jan_amount or 0),
                    "feb": float(item.feb_amount or 0),
                    "mar": float(item.mar_amount or 0),
                    "apr": float(item.apr_amount or 0),
                    "may": float(item.may_amount or 0),
                    "jun": float(item.jun_amount or 0),
                    "jul": float(item.jul_amount or 0),
                    "aug": float(item.aug_amount or 0),
                    "sep": float(item.sep_amount or 0),
                    "oct": float(item.oct_amount or 0),
                    "nov": float(item.nov_amount or 0),
                    "dec": float(item.dec_amount or 0)
                },
                "total_budget": float(item.total_budget or 0),
                "notes": item.notes
            }
            for item in budget.line_items
        ]
    
    return response


@router.patch("/{budget_id}")
async def update_budget(
    data: BudgetUpdate,
    budget_id: UUID = Path(...),
    entity_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update budget properties."""
    service = BudgetService(db)
    
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    budget = await service.update_budget(budget_id, **updates)
    
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    
    return {"message": "Budget updated successfully", "id": str(budget.id)}


# ============================================================================
# Approval Workflow Integration Endpoints
# ============================================================================

class BudgetSubmitForApproval(BaseModel):
    """Submit budget for approval request."""
    workflow_id: Optional[UUID] = None
    comments: Optional[str] = None


class BudgetApprovalDecision(BaseModel):
    """Approval decision for a budget."""
    approved: bool
    comments: Optional[str] = None


class BudgetRevisionCreate(BaseModel):
    """Create a budget revision."""
    revision_reason: str = Field(..., min_length=1)
    copy_line_items: bool = True


@router.post("/{budget_id}/submit-for-approval")
async def submit_budget_for_approval(
    data: BudgetSubmitForApproval,
    budget_id: UUID = Path(...),
    entity_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Submit a budget for M-of-N approval workflow.
    
    If no workflow is configured for budgets, the budget will be auto-approved.
    """
    service = BudgetService(db)
    
    try:
        result = await service.submit_budget_for_approval(
            budget_id=budget_id,
            submitted_by_id=current_user.id,
            workflow_id=data.workflow_id,
            comments=data.comments,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{budget_id}/approval-decision")
async def process_budget_approval_decision(
    data: BudgetApprovalDecision,
    budget_id: UUID = Path(...),
    entity_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Process an approval or rejection decision for a pending budget.
    
    This endpoint is called when an approver makes a decision.
    M-of-N approval tracking is handled automatically.
    """
    service = BudgetService(db)
    
    try:
        result = await service.process_budget_approval(
            budget_id=budget_id,
            approver_id=current_user.id,
            approved=data.approved,
            comments=data.comments,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{budget_id}/approval-status")
async def get_budget_approval_status(
    budget_id: UUID = Path(...),
    entity_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get the current approval status of a budget.
    
    Includes approval history, current approvals count, and workflow details.
    """
    service = BudgetService(db)
    
    try:
        return await service.get_budget_approval_status(budget_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{budget_id}/revisions")
async def create_budget_revision(
    data: BudgetRevisionCreate,
    budget_id: UUID = Path(...),
    entity_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new revision of an existing budget.
    
    This creates a new version with full tracking of changes.
    The original budget is marked as not current.
    """
    service = BudgetService(db)
    
    try:
        new_budget = await service.create_budget_revision(
            budget_id=budget_id,
            created_by_id=current_user.id,
            revision_reason=data.revision_reason,
            copy_line_items=data.copy_line_items,
        )
        return {
            "message": f"Created revision v{new_budget.version}",
            "id": str(new_budget.id),
            "version": new_budget.version,
            "parent_budget_id": str(budget_id),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{budget_id}/version-history")
async def get_budget_version_history(
    budget_id: UUID = Path(...),
    entity_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get the full version history of a budget.
    
    Returns all versions from the first version to the specified budget.
    """
    service = BudgetService(db)
    
    try:
        history = await service.get_budget_version_history(budget_id)
        return {
            "budget_id": str(budget_id),
            "version_count": len(history),
            "versions": history,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================================
# Legacy Simple Approval (kept for backward compatibility)
# ============================================================================

@router.post("/{budget_id}/approve")
async def approve_budget(
    budget_id: UUID = Path(...),
    entity_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Simple budget approval (legacy).
    
    For M-of-N approval workflow, use /submit-for-approval instead.
    """
    service = BudgetService(db)
    budget = await service.approve_budget(budget_id, current_user.id)
    
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    
    return {
        "message": "Budget approved successfully",
        "id": str(budget.id),
        "status": budget.status
    }


@router.post("/{budget_id}/activate")
async def activate_budget(
    budget_id: UUID = Path(...),
    entity_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Activate an approved budget."""
    service = BudgetService(db)
    budget = await service.activate_budget(budget_id)
    
    if not budget:
        raise HTTPException(
            status_code=400, 
            detail="Budget not found or not in approved status"
        )
    
    return {
        "message": "Budget activated successfully",
        "id": str(budget.id),
        "status": budget.status
    }


# ============================================================================
# Budget Line Item Endpoints
# ============================================================================

@router.post("/{budget_id}/line-items")
async def add_budget_line_item(
    data: BudgetLineItemCreate,
    budget_id: UUID = Path(...),
    entity_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add a line item to a budget."""
    service = BudgetService(db)
    
    monthly_amounts = None
    if data.monthly_amounts:
        monthly_amounts = {
            k: Decimal(str(v)) for k, v in data.monthly_amounts.items()
        }
    
    item = await service.add_budget_line_item(
        budget_id=budget_id,
        account_name=data.account_name,
        line_type=data.line_type,
        account_code=data.account_code,
        category_id=data.category_id,
        dimension_id=data.dimension_id,
        monthly_amounts=monthly_amounts,
        total_budget=Decimal(str(data.total_budget)) if data.total_budget else None,
        notes=data.notes
    )
    
    return {
        "id": str(item.id),
        "account_name": item.account_name,
        "total_budget": float(item.total_budget or 0),
        "message": "Line item added successfully"
    }


@router.get("/{budget_id}/line-items")
async def list_budget_line_items(
    budget_id: UUID = Path(...),
    entity_id: UUID = Path(...),
    line_type: Optional[str] = Query(None, description="revenue, expense, or capex"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all line items for a budget."""
    service = BudgetService(db)
    budget = await service.get_budget(budget_id, include_line_items=True)
    
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    
    items = budget.line_items
    if line_type:
        items = [i for i in items if i.line_type == line_type]
    
    return {
        "items": [
            {
                "id": str(item.id),
                "account_code": item.account_code,
                "account_name": item.account_name,
                "line_type": item.line_type,
                "total_budget": float(item.total_budget or 0),
                "monthly_amounts": {
                    "jan": float(item.jan_amount or 0),
                    "feb": float(item.feb_amount or 0),
                    "mar": float(item.mar_amount or 0),
                    "apr": float(item.apr_amount or 0),
                    "may": float(item.may_amount or 0),
                    "jun": float(item.jun_amount or 0),
                    "jul": float(item.jul_amount or 0),
                    "aug": float(item.aug_amount or 0),
                    "sep": float(item.sep_amount or 0),
                    "oct": float(item.oct_amount or 0),
                    "nov": float(item.nov_amount or 0),
                    "dec": float(item.dec_amount or 0)
                }
            }
            for item in items
        ],
        "total": len(items),
        "summary": {
            "revenue_total": sum(float(i.total_budget or 0) for i in items if i.line_type == "revenue"),
            "expense_total": sum(float(i.total_budget or 0) for i in items if i.line_type == "expense"),
            "capex_total": sum(float(i.total_budget or 0) for i in items if i.line_type == "capex")
        }
    }


@router.patch("/{budget_id}/line-items/{line_item_id}")
async def update_budget_line_item(
    data: BudgetLineItemUpdate,
    budget_id: UUID = Path(...),
    line_item_id: UUID = Path(...),
    entity_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a budget line item."""
    service = BudgetService(db)
    
    updates = {}
    for field in ['account_name', 'account_code', 'notes']:
        if getattr(data, field) is not None:
            updates[field] = getattr(data, field)
    
    for month in ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']:
        field = f"{month}_amount"
        if getattr(data, field) is not None:
            updates[field] = Decimal(str(getattr(data, field)))
    
    item = await service.update_budget_line_item(line_item_id, **updates)
    
    if not item:
        raise HTTPException(status_code=404, detail="Line item not found")
    
    return {"message": "Line item updated successfully", "id": str(item.id)}


@router.delete("/{budget_id}/line-items/{line_item_id}")
async def delete_budget_line_item(
    budget_id: UUID = Path(...),
    line_item_id: UUID = Path(...),
    entity_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a budget line item."""
    service = BudgetService(db)
    success = await service.delete_budget_line_item(line_item_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Line item not found")
    
    return {"message": "Line item deleted successfully"}


@router.post("/{budget_id}/import-accounts")
async def import_chart_of_accounts(
    budget_id: UUID = Path(...),
    entity_id: UUID = Path(...),
    account_types: List[str] = Query(default=["revenue", "expense"]),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Import chart of accounts as budget line items.
    
    Creates line items from existing accounts for quick budget setup.
    """
    service = BudgetService(db)
    count = await service.import_chart_of_accounts_to_budget(
        budget_id=budget_id,
        entity_id=entity_id,
        account_types=account_types
    )
    
    return {
        "message": f"Imported {count} accounts as budget line items",
        "imported_count": count
    }


# ============================================================================
# Budget vs Actual Analysis
# ============================================================================

@router.get("/{budget_id}/variance")
async def get_budget_variance(
    budget_id: UUID = Path(...),
    entity_id: UUID = Path(...),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    through_month: Optional[int] = Query(None, ge=1, le=12),
    group_by: str = Query(default="account", description="account, category, or dimension"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate comprehensive Budget vs Actual variance analysis.
    
    Provides detailed comparison of budgeted vs actual amounts with:
    - Line-item level variance analysis
    - Favorable/unfavorable classification
    - Percentage variances
    - Variance alerts for significant deviations
    - Remaining budget calculations
    """
    service = BudgetService(db)
    
    try:
        result = await service.get_budget_vs_actual(
            entity_id=entity_id,
            budget_id=budget_id,
            start_date=start_date,
            end_date=end_date,
            through_month=through_month,
            group_by=group_by
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{budget_id}/variance/ytd")
async def get_budget_variance_ytd(
    budget_id: UUID = Path(...),
    entity_id: UUID = Path(...),
    group_by: str = Query(default="account", description="account, category, or dimension"),
    alert_threshold: float = Query(default=10.0, ge=0, le=100, description="Variance % threshold for alerts"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get Year-To-Date (YTD) budget variance analysis.
    
    Automatically calculates variance from budget start through the current month.
    
    Returns:
    - YTD budget amounts per line item
    - YTD actual amounts
    - Variance (favorable/unfavorable)
    - Percentage variance
    - Alerts for items exceeding threshold
    - Remaining budget for the year
    """
    from datetime import date as date_type
    
    service = BudgetService(db)
    
    try:
        # Get budget to determine fiscal year
        budget = await service.get_budget(entity_id, budget_id)
        if not budget:
            raise HTTPException(status_code=404, detail="Budget not found")
        
        # Calculate through current month
        today = date_type.today()
        current_month = today.month
        
        # If we're past the budget end date, use full year
        if today > budget.end_date:
            current_month = 12
        
        result = await service.get_budget_vs_actual(
            entity_id=entity_id,
            budget_id=budget_id,
            through_month=current_month,
            group_by=group_by
        )
        
        # Add YTD-specific fields
        result["ytd_summary"] = {
            "through_month": current_month,
            "month_name": ["January", "February", "March", "April", "May", "June",
                          "July", "August", "September", "October", "November", "December"][current_month - 1],
            "alert_threshold_percent": alert_threshold,
            "items_over_budget": 0,
            "items_under_budget": 0,
            "total_favorable_variance": 0,
            "total_unfavorable_variance": 0,
        }
        
        # Process variance alerts
        alerts = []
        for item in result.get("line_items", []):
            variance_pct = item.get("variance_percent", 0)
            variance_amt = item.get("variance_amount", 0)
            
            if abs(variance_pct) >= alert_threshold:
                alert = {
                    "account_name": item.get("account_name"),
                    "account_code": item.get("account_code"),
                    "variance_percent": variance_pct,
                    "variance_amount": variance_amt,
                    "is_favorable": item.get("is_favorable", variance_amt >= 0),
                    "severity": "high" if abs(variance_pct) >= 25 else "medium" if abs(variance_pct) >= 15 else "low"
                }
                alerts.append(alert)
            
            if variance_amt > 0:
                result["ytd_summary"]["items_under_budget"] += 1
                result["ytd_summary"]["total_favorable_variance"] += variance_amt
            elif variance_amt < 0:
                result["ytd_summary"]["items_over_budget"] += 1
                result["ytd_summary"]["total_unfavorable_variance"] += abs(variance_amt)
        
        result["variance_alerts"] = sorted(alerts, key=lambda x: abs(x["variance_percent"]), reverse=True)
        
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{budget_id}/forecast")
async def get_budget_forecast(
    budget_id: UUID = Path(...),
    entity_id: UUID = Path(...),
    forecast_months: int = Query(default=3, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Forecast future budget performance based on current trends.
    
    Uses year-to-date actuals to project:
    - Full year revenue/expense projections
    - Projected variances
    - Risk assessment
    - Confidence levels based on data availability
    """
    service = BudgetService(db)
    
    try:
        result = await service.forecast_budget_performance(
            entity_id=entity_id,
            budget_id=budget_id,
            forecast_months=forecast_months
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{budget_id}/department-summary")
async def get_department_budget_summary(
    budget_id: UUID = Path(...),
    entity_id: UUID = Path(...),
    dimension_type: str = Query(default="department"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get budget summary grouped by department or other dimension.
    
    Useful for departmental budget reviews and responsibility accounting.
    """
    service = BudgetService(db)
    
    try:
        result = await service.get_department_budget_summary(
            entity_id=entity_id,
            budget_id=budget_id,
            dimension_type=dimension_type
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================================
# Budget Comparison
# ============================================================================

@router.post("/compare")
async def compare_budgets(
    budget_ids: List[UUID],
    entity_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Compare multiple budgets (e.g., year-over-year comparison).
    
    Useful for:
    - Year-over-year budget growth analysis
    - Comparing actual vs revised budgets
    - Multi-scenario budget analysis
    """
    service = BudgetService(db)
    
    try:
        result = await service.compare_budgets(
            entity_id=entity_id,
            budget_ids=budget_ids
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# Actuals Sync
# ============================================================================

@router.post("/{budget_id}/sync-actuals")
async def sync_actuals_to_budget(
    budget_id: UUID = Path(...),
    entity_id: UUID = Path(...),
    sync_date: Optional[date] = Query(default=None, description="Sync through this date (defaults to today)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Sync actual amounts from GL/transactions to budget.
    
    This updates:
    - Budget line item actual columns (jan_actual through dec_actual)
    - Line item variance calculations
    - Budget period actual amounts and variances
    
    Should be run periodically to keep variance tracking current.
    Typically scheduled daily or weekly.
    """
    service = BudgetService(db)
    
    try:
        result = await service.sync_actuals_to_budget(
            budget_id=budget_id,
            entity_id=entity_id,
            sync_date=sync_date,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
