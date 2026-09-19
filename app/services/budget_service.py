"""
Tekvwa Pro Audit - Budget Management Service

Comprehensive service for budget planning, monitoring, and variance analysis.
Includes:
- Budget creation and management
- Multi-period budget support (monthly, quarterly, annual)
- Budget vs Actual variance analysis
- Budget forecasting and projections
- Department/project-level budgeting
- Budget approval workflows with M-of-N support
- Revision tracking and version control
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum as PyEnum
from collections import defaultdict
import logging

from sqlalchemy import select, func, and_, or_, case, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.advanced_accounting import (
    Budget, BudgetLineItem, BudgetPeriodType, AccountingDimension,
    BudgetPeriod, ApprovalWorkflow, ApprovalRequest, ApprovalStatus
)
from app.models.accounting import ChartOfAccounts, AccountType, AccountBalance
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)


class BudgetStatus(str, PyEnum):
    """Budget lifecycle statuses"""
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    ACTIVE = "active"
    REVISED = "revised"
    CLOSED = "closed"


class VarianceType(str, PyEnum):
    """Types of budget variances"""
    FAVORABLE = "favorable"
    UNFAVORABLE = "unfavorable"
    ON_TARGET = "on_target"


class BudgetService:
    """Service for budget operations and variance analysis."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # =========================================================================
    # BUDGET CRUD OPERATIONS
    # =========================================================================
    
    async def create_budget(
        self,
        entity_id: uuid.UUID,
        name: str,
        fiscal_year: int,
        start_date: date,
        end_date: date,
        created_by_id: uuid.UUID,
        period_type: str = "monthly",
        description: Optional[str] = None
    ) -> Budget:
        """Create a new budget."""
        budget = Budget(
            entity_id=entity_id,
            name=name,
            description=description,
            fiscal_year=fiscal_year,
            period_type=BudgetPeriodType(period_type),
            start_date=start_date,
            end_date=end_date,
            status=BudgetStatus.DRAFT.value,
            created_by_id=created_by_id
        )
        self.db.add(budget)
        await self.db.commit()
        await self.db.refresh(budget)
        return budget
    
    async def get_budget(
        self,
        budget_id: uuid.UUID,
        include_line_items: bool = True
    ) -> Optional[Budget]:
        """Get a budget by ID."""
        query = select(Budget).where(Budget.id == budget_id)
        if include_line_items:
            query = query.options(selectinload(Budget.line_items))
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_budgets_for_entity(
        self,
        entity_id: uuid.UUID,
        fiscal_year: Optional[int] = None,
        status: Optional[str] = None
    ) -> List[Budget]:
        """Get all budgets for an entity."""
        query = select(Budget).where(Budget.entity_id == entity_id)
        
        if fiscal_year:
            query = query.where(Budget.fiscal_year == fiscal_year)
        if status:
            query = query.where(Budget.status == status)
        
        query = query.order_by(Budget.fiscal_year.desc(), Budget.name)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_active_budget(
        self,
        entity_id: uuid.UUID,
        as_of_date: Optional[date] = None
    ) -> Optional[Budget]:
        """Get the active budget for an entity as of a date."""
        if not as_of_date:
            as_of_date = date.today()
        
        result = await self.db.execute(
            select(Budget).where(
                and_(
                    Budget.entity_id == entity_id,
                    Budget.status == "active",
                    Budget.start_date <= as_of_date,
                    Budget.end_date >= as_of_date
                )
            ).options(selectinload(Budget.line_items))
        )
        return result.scalar_one_or_none()
    
    async def update_budget(
        self,
        budget_id: uuid.UUID,
        **updates
    ) -> Optional[Budget]:
        """Update budget properties."""
        budget = await self.get_budget(budget_id, include_line_items=False)
        if not budget:
            return None
        
        for key, value in updates.items():
            if hasattr(budget, key):
                setattr(budget, key, value)
        
        await self.db.commit()
        await self.db.refresh(budget)
        return budget
    
    async def approve_budget(
        self,
        budget_id: uuid.UUID,
        approved_by_id: uuid.UUID
    ) -> Optional[Budget]:
        """Approve a budget."""
        budget = await self.get_budget(budget_id, include_line_items=False)
        if not budget:
            return None
        
        budget.status = BudgetStatus.APPROVED.value
        budget.approved_by_id = approved_by_id
        budget.approved_at = datetime.utcnow()
        
        await self.db.commit()
        await self.db.refresh(budget)
        return budget
    
    async def activate_budget(
        self,
        budget_id: uuid.UUID
    ) -> Optional[Budget]:
        """Activate an approved budget."""
        budget = await self.get_budget(budget_id, include_line_items=False)
        if not budget or budget.status != BudgetStatus.APPROVED.value:
            return None
        
        # Deactivate any other active budgets for this entity/year
        await self.db.execute(
            update(Budget).where(
                and_(
                    Budget.entity_id == budget.entity_id,
                    Budget.fiscal_year == budget.fiscal_year,
                    Budget.status == BudgetStatus.ACTIVE.value
                )
            ).values(status=BudgetStatus.CLOSED.value)
        )
        
        budget.status = BudgetStatus.ACTIVE.value
        await self.db.commit()
        await self.db.refresh(budget)
        return budget
    
    # =========================================================================
    # APPROVAL WORKFLOW INTEGRATION
    # =========================================================================
    
    async def submit_budget_for_approval(
        self,
        budget_id: uuid.UUID,
        submitted_by_id: uuid.UUID,
        workflow_id: Optional[uuid.UUID] = None,
        comments: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Submit a budget for approval through the M-of-N approval workflow.
        
        If no workflow_id is provided, will try to find a matching budget approval workflow.
        """
        budget = await self.get_budget(budget_id, include_line_items=False)
        if not budget:
            raise ValueError("Budget not found")
        
        if budget.status not in [BudgetStatus.DRAFT.value, "draft"]:
            raise ValueError(f"Budget cannot be submitted (status: {budget.status})")
        
        # Find or validate workflow
        if workflow_id:
            workflow_result = await self.db.execute(
                select(ApprovalWorkflow).where(ApprovalWorkflow.id == workflow_id)
            )
            workflow = workflow_result.scalar_one_or_none()
            if not workflow:
                raise ValueError("Approval workflow not found")
        else:
            # Try to find a budget approval workflow for this entity
            workflow_result = await self.db.execute(
                select(ApprovalWorkflow).where(
                    and_(
                        ApprovalWorkflow.entity_id == budget.entity_id,
                        ApprovalWorkflow.trigger_type == "budget",
                        ApprovalWorkflow.is_active == True,
                    )
                )
            )
            workflow = workflow_result.scalar_one_or_none()
            
            if not workflow:
                # Auto-approve if no workflow configured
                logger.info(f"No approval workflow for budget {budget_id}, auto-approving")
                budget.status = BudgetStatus.APPROVED.value
                budget.approved_at = datetime.utcnow()
                budget.approved_by_id = submitted_by_id
                await self.db.commit()
                
                return {
                    "success": True,
                    "budget_id": str(budget_id),
                    "status": "approved",
                    "message": "No approval workflow configured - auto-approved",
                    "auto_approved": True,
                }
        
        # Calculate total budget amount for threshold checking
        total_amount = (
            Decimal(str(budget.total_revenue_budget or 0)) +
            Decimal(str(budget.total_expense_budget or 0)) +
            Decimal(str(budget.total_capex_budget or 0))
        )
        
        # Create approval request via ApprovalWorkflowService
        from app.services.approval_workflow import ApprovalWorkflowService
        approval_service = ApprovalWorkflowService()
        
        approval_request = await approval_service.submit_for_approval(
            db=self.db,
            entity_id=budget.entity_id,
            workflow_type="budget",
            resource_type="budget",
            resource_id=budget_id,
            amount=total_amount,
            submitted_by=submitted_by_id,
            context={
                "budget_name": budget.name,
                "fiscal_year": budget.fiscal_year,
                "total_revenue": float(budget.total_revenue_budget or 0),
                "total_expense": float(budget.total_expense_budget or 0),
                "total_capex": float(budget.total_capex_budget or 0),
                "comments": comments,
            }
        )
        
        # Update budget status and link to approval request
        budget.status = "pending_approval"
        budget.approval_workflow_id = workflow.id
        budget.approval_request_id = approval_request.id
        budget.required_approvers = workflow.required_approvers
        budget.current_approvals = 0
        
        if budget.approval_notes:
            approval_history = budget.approval_notes
        else:
            approval_history = []
        
        approval_history.append({
            "action": "submitted",
            "by": str(submitted_by_id),
            "at": datetime.utcnow().isoformat(),
            "comments": comments,
        })
        budget.approval_notes = approval_history
        
        await self.db.commit()
        await self.db.refresh(budget)
        
        logger.info(f"Budget {budget_id} submitted for approval via workflow {workflow.name}")
        
        return {
            "success": True,
            "budget_id": str(budget_id),
            "approval_request_id": str(approval_request.id),
            "status": "pending_approval",
            "workflow_name": workflow.name,
            "required_approvers": workflow.required_approvers,
            "message": f"Submitted for approval ({workflow.required_approvers} approver(s) required)",
        }
    
    async def process_budget_approval(
        self,
        budget_id: uuid.UUID,
        approver_id: uuid.UUID,
        approved: bool,
        comments: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process an approval decision for a budget.
        Called by the approval workflow when a decision is made.
        """
        budget = await self.get_budget(budget_id, include_line_items=False)
        if not budget:
            raise ValueError("Budget not found")
        
        if budget.status != "pending_approval":
            raise ValueError(f"Budget is not pending approval (status: {budget.status})")
        
        # Update approval notes
        if budget.approval_notes:
            approval_history = budget.approval_notes
        else:
            approval_history = []
        
        approval_history.append({
            "action": "approved" if approved else "rejected",
            "by": str(approver_id),
            "at": datetime.utcnow().isoformat(),
            "comments": comments,
        })
        budget.approval_notes = approval_history
        
        if approved:
            budget.current_approvals = (budget.current_approvals or 0) + 1
            
            # Check if fully approved
            if budget.current_approvals >= budget.required_approvers:
                budget.status = BudgetStatus.APPROVED.value
                budget.approved_by_id = approver_id
                budget.approved_at = datetime.utcnow()
                
                logger.info(f"Budget {budget_id} fully approved ({budget.current_approvals}/{budget.required_approvers})")
                
                await self.db.commit()
                return {
                    "success": True,
                    "budget_id": str(budget_id),
                    "status": "approved",
                    "current_approvals": budget.current_approvals,
                    "required_approvers": budget.required_approvers,
                    "message": "Budget fully approved",
                }
            else:
                await self.db.commit()
                return {
                    "success": True,
                    "budget_id": str(budget_id),
                    "status": "pending_approval",
                    "current_approvals": budget.current_approvals,
                    "required_approvers": budget.required_approvers,
                    "message": f"Approval recorded ({budget.current_approvals}/{budget.required_approvers})",
                }
        else:
            # Rejected
            budget.status = BudgetStatus.DRAFT.value  # Back to draft for revision
            budget.current_approvals = 0
            
            logger.info(f"Budget {budget_id} rejected by {approver_id}: {comments}")
            
            await self.db.commit()
            return {
                "success": True,
                "budget_id": str(budget_id),
                "status": "draft",
                "message": f"Budget rejected: {comments}",
                "rejection_reason": comments,
            }
    
    async def get_budget_approval_status(
        self,
        budget_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Get the current approval status of a budget."""
        budget = await self.get_budget(budget_id, include_line_items=False)
        if not budget:
            raise ValueError("Budget not found")
        
        result = {
            "budget_id": str(budget_id),
            "budget_name": budget.name,
            "status": budget.status,
            "current_approvals": budget.current_approvals or 0,
            "required_approvers": budget.required_approvers or 0,
            "approval_history": budget.approval_notes or [],
        }
        
        if budget.approval_workflow_id:
            workflow_result = await self.db.execute(
                select(ApprovalWorkflow).where(ApprovalWorkflow.id == budget.approval_workflow_id)
            )
            workflow = workflow_result.scalar_one_or_none()
            if workflow:
                result["workflow"] = {
                    "id": str(workflow.id),
                    "name": workflow.name,
                    "description": workflow.description,
                }
        
        if budget.approved_at:
            result["approved_at"] = budget.approved_at.isoformat()
        
        return result
    
    # =========================================================================
    # BUDGET REVISION / VERSION CONTROL
    # =========================================================================
    
    async def create_budget_revision(
        self,
        budget_id: uuid.UUID,
        created_by_id: uuid.UUID,
        revision_reason: str,
        copy_line_items: bool = True,
    ) -> Budget:
        """
        Create a new revision of an existing budget.
        
        This creates a new version with a link to the previous version,
        allowing full history tracking.
        """
        original = await self.get_budget(budget_id, include_line_items=copy_line_items)
        if not original:
            raise ValueError("Original budget not found")
        
        # Mark original as not current version
        original.is_current_version = False
        
        # Create new revision
        new_version = Budget(
            entity_id=original.entity_id,
            name=original.name,
            description=original.description,
            fiscal_year=original.fiscal_year,
            period_type=original.period_type,
            start_date=original.start_date,
            end_date=original.end_date,
            total_revenue_budget=original.total_revenue_budget,
            total_expense_budget=original.total_expense_budget,
            total_capex_budget=original.total_capex_budget,
            status=BudgetStatus.DRAFT.value,
            created_by_id=created_by_id,
            # Revision tracking
            version=original.version + 1,
            parent_budget_id=original.id,
            revision_reason=revision_reason,
            revision_date=datetime.utcnow(),
            is_current_version=True,
            # Copy other settings
            currency=original.currency,
            variance_threshold_pct=original.variance_threshold_pct,
            variance_threshold_amt=original.variance_threshold_amt,
        )
        
        self.db.add(new_version)
        await self.db.flush()  # Get the ID
        
        # Copy line items if requested
        if copy_line_items and original.line_items:
            for item in original.line_items:
                new_item = BudgetLineItem(
                    budget_id=new_version.id,
                    category_id=item.category_id,
                    dimension_id=item.dimension_id,
                    account_code=item.account_code,
                    account_name=item.account_name,
                    line_type=item.line_type,
                    gl_account_id=item.gl_account_id,
                    jan_amount=item.jan_amount,
                    feb_amount=item.feb_amount,
                    mar_amount=item.mar_amount,
                    apr_amount=item.apr_amount,
                    may_amount=item.may_amount,
                    jun_amount=item.jun_amount,
                    jul_amount=item.jul_amount,
                    aug_amount=item.aug_amount,
                    sep_amount=item.sep_amount,
                    oct_amount=item.oct_amount,
                    nov_amount=item.nov_amount,
                    dec_amount=item.dec_amount,
                    total_budget=item.total_budget,
                    period_allocations=item.period_allocations,
                    notes=item.notes,
                )
                self.db.add(new_item)
        
        await self.db.commit()
        await self.db.refresh(new_version)
        
        logger.info(f"Created budget revision v{new_version.version} from {budget_id}")
        
        return new_version
    
    async def get_budget_version_history(
        self,
        budget_id: uuid.UUID,
    ) -> List[Dict[str, Any]]:
        """
        Get the full version history of a budget.
        Traces back through parent_budget_id links.
        """
        history = []
        current_id = budget_id
        
        while current_id:
            budget = await self.get_budget(current_id, include_line_items=False)
            if not budget:
                break
            
            history.append({
                "id": str(budget.id),
                "version": budget.version,
                "status": budget.status,
                "is_current_version": budget.is_current_version,
                "revision_reason": budget.revision_reason,
                "revision_date": budget.revision_date.isoformat() if budget.revision_date else None,
                "created_at": budget.created_at.isoformat() if budget.created_at else None,
                "approved_at": budget.approved_at.isoformat() if budget.approved_at else None,
            })
            
            current_id = budget.parent_budget_id
        
        # Return in chronological order (oldest first)
        return list(reversed(history))
    
    # =========================================================================
    # BUDGET LINE ITEMS
    # =========================================================================
    
    async def add_budget_line_item(
        self,
        budget_id: uuid.UUID,
        account_name: str,
        line_type: str,  # revenue, expense, capex
        account_code: Optional[str] = None,
        category_id: Optional[uuid.UUID] = None,
        dimension_id: Optional[uuid.UUID] = None,
        monthly_amounts: Optional[Dict[str, Decimal]] = None,
        total_budget: Optional[Decimal] = None,
        notes: Optional[str] = None
    ) -> BudgetLineItem:
        """Add a line item to a budget."""
        # Calculate total if monthly amounts provided
        if monthly_amounts:
            calc_total = sum(monthly_amounts.values())
        elif total_budget:
            calc_total = total_budget
        else:
            calc_total = Decimal("0")
        
        line_item = BudgetLineItem(
            budget_id=budget_id,
            account_code=account_code,
            account_name=account_name,
            line_type=line_type,
            category_id=category_id,
            dimension_id=dimension_id,
            total_budget=calc_total,
            notes=notes
        )
        
        # Set monthly amounts
        if monthly_amounts:
            months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 
                      'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
            for month in months:
                setattr(line_item, f"{month}_amount", 
                        monthly_amounts.get(month, Decimal("0")))
        elif total_budget:
            # Distribute evenly across months
            monthly = total_budget / 12
            for month in ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
                          'jul', 'aug', 'sep', 'oct', 'nov', 'dec']:
                setattr(line_item, f"{month}_amount", monthly)
        
        self.db.add(line_item)
        await self.db.commit()
        await self.db.refresh(line_item)
        
        # Update budget totals
        await self._update_budget_totals(budget_id)
        
        return line_item
    
    async def update_budget_line_item(
        self,
        line_item_id: uuid.UUID,
        **updates
    ) -> Optional[BudgetLineItem]:
        """Update a budget line item."""
        result = await self.db.execute(
            select(BudgetLineItem).where(BudgetLineItem.id == line_item_id)
        )
        line_item = result.scalar_one_or_none()
        if not line_item:
            return None
        
        for key, value in updates.items():
            if hasattr(line_item, key):
                setattr(line_item, key, value)
        
        # Recalculate total if monthly amounts changed
        months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
                  'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
        line_item.total_budget = sum(
            getattr(line_item, f"{m}_amount") or Decimal("0") for m in months
        )
        
        await self.db.commit()
        await self.db.refresh(line_item)
        
        # Update budget totals
        await self._update_budget_totals(line_item.budget_id)
        
        return line_item
    
    async def delete_budget_line_item(
        self,
        line_item_id: uuid.UUID
    ) -> bool:
        """Delete a budget line item."""
        result = await self.db.execute(
            select(BudgetLineItem).where(BudgetLineItem.id == line_item_id)
        )
        line_item = result.scalar_one_or_none()
        if not line_item:
            return False
        
        budget_id = line_item.budget_id
        await self.db.delete(line_item)
        await self.db.commit()
        
        # Update budget totals
        await self._update_budget_totals(budget_id)
        
        return True
    
    async def _update_budget_totals(self, budget_id: uuid.UUID):
        """Update budget total amounts from line items."""
        budget = await self.get_budget(budget_id, include_line_items=True)
        if not budget:
            return
        
        revenue_total = Decimal("0")
        expense_total = Decimal("0")
        capex_total = Decimal("0")
        
        for item in budget.line_items:
            if item.line_type == "revenue":
                revenue_total += item.total_budget or Decimal("0")
            elif item.line_type == "expense":
                expense_total += item.total_budget or Decimal("0")
            elif item.line_type == "capex":
                capex_total += item.total_budget or Decimal("0")
        
        budget.total_revenue_budget = revenue_total
        budget.total_expense_budget = expense_total
        budget.total_capex_budget = capex_total
        
        await self.db.commit()
    
    async def import_chart_of_accounts_to_budget(
        self,
        budget_id: uuid.UUID,
        entity_id: uuid.UUID,
        account_types: Optional[List[str]] = None
    ) -> int:
        """Import chart of accounts as budget line items."""
        if not account_types:
            account_types = ["revenue", "expense"]
        
        # Get accounts
        type_mapping = {
            "revenue": AccountType.REVENUE,
            "expense": AccountType.EXPENSE,
            "asset": AccountType.ASSET
        }
        
        account_type_enums = [type_mapping.get(t) for t in account_types if t in type_mapping]
        
        result = await self.db.execute(
            select(ChartOfAccounts).where(
                and_(
                    ChartOfAccounts.entity_id == entity_id,
                    ChartOfAccounts.account_type.in_(account_type_enums),
                    ChartOfAccounts.is_active == True,
                    ChartOfAccounts.is_header == False
                )
            )
        )
        accounts = result.scalars().all()
        
        count = 0
        for account in accounts:
            line_type = "expense"
            if account.account_type == AccountType.REVENUE:
                line_type = "revenue"
            elif account.account_type == AccountType.ASSET:
                line_type = "capex"
            
            line_item = BudgetLineItem(
                budget_id=budget_id,
                account_code=account.account_code,
                account_name=account.account_name,
                line_type=line_type,
                total_budget=Decimal("0")
            )
            self.db.add(line_item)
            count += 1
        
        await self.db.commit()
        return count
    
    # =========================================================================
    # VARIANCE ANALYSIS
    # =========================================================================
    
    async def get_budget_vs_actual(
        self,
        entity_id: uuid.UUID,
        budget_id: uuid.UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        through_month: Optional[int] = None,
        group_by: str = "account"  # account, category, dimension
    ) -> Dict[str, Any]:
        """
        Comprehensive Budget vs Actual variance analysis.
        
        Returns detailed comparison of budgeted vs actual amounts
        with variance calculations and trend analysis.
        """
        budget = await self.get_budget(budget_id, include_line_items=True)
        if not budget:
            raise ValueError("Budget not found")
        
        # Determine date range
        if not start_date:
            start_date = budget.start_date
        if not end_date:
            if through_month:
                end_date = date(budget.fiscal_year, through_month, 28)
            else:
                end_date = min(budget.end_date, date.today())
        
        # Get actual transactions
        actuals = await self._get_actual_amounts(
            entity_id, start_date, end_date, group_by
        )
        
        # Build variance report
        months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
                  'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
        
        # Calculate which months are in range
        start_month = start_date.month
        end_month = end_date.month
        months_in_range = months[start_month-1:end_month]
        
        line_items_analysis = []
        summary = {
            "revenue": {"budget": Decimal("0"), "actual": Decimal("0"), "variance": Decimal("0")},
            "expense": {"budget": Decimal("0"), "actual": Decimal("0"), "variance": Decimal("0")},
            "capex": {"budget": Decimal("0"), "actual": Decimal("0"), "variance": Decimal("0")}
        }
        
        for item in budget.line_items:
            # Calculate YTD budget
            ytd_budget = sum(
                getattr(item, f"{month}_amount") or Decimal("0")
                for month in months_in_range
            )
            
            # Get actual from actuals dict
            key = item.account_code or str(item.category_id) or item.account_name
            ytd_actual = actuals.get(key, {}).get(item.line_type, Decimal("0"))
            
            variance = ytd_actual - ytd_budget
            variance_pct = (variance / ytd_budget * 100) if ytd_budget else Decimal("0")
            
            # Determine variance status
            if item.line_type == "revenue":
                variance_type = VarianceType.FAVORABLE if variance >= 0 else VarianceType.UNFAVORABLE
            else:
                variance_type = VarianceType.FAVORABLE if variance <= 0 else VarianceType.UNFAVORABLE
            
            # Monthly breakdown
            monthly_breakdown = []
            for month in months:
                month_budget = getattr(item, f"{month}_amount") or Decimal("0")
                monthly_breakdown.append({
                    "month": month,
                    "budget": float(month_budget),
                    "actual": 0,  # Would need per-month actuals
                    "variance": 0
                })
            
            analysis = {
                "id": str(item.id),
                "account_code": item.account_code,
                "account_name": item.account_name,
                "line_type": item.line_type,
                "annual_budget": float(item.total_budget or Decimal("0")),
                "ytd_budget": float(ytd_budget),
                "ytd_actual": float(ytd_actual),
                "variance": float(variance),
                "variance_percentage": float(variance_pct.quantize(Decimal("0.01"))),
                "variance_type": variance_type.value,
                "monthly_breakdown": monthly_breakdown,
                "remaining_budget": float((item.total_budget or Decimal("0")) - ytd_actual),
                "percent_utilized": float(
                    (ytd_actual / item.total_budget * 100).quantize(Decimal("0.01"))
                    if item.total_budget else Decimal("0")
                )
            }
            line_items_analysis.append(analysis)
            
            # Update summary
            if item.line_type in summary:
                summary[item.line_type]["budget"] += ytd_budget
                summary[item.line_type]["actual"] += ytd_actual
                summary[item.line_type]["variance"] += variance
        
        # Calculate summary percentages
        for line_type in summary:
            budget_amt = summary[line_type]["budget"]
            actual_amt = summary[line_type]["actual"]
            variance_amt = summary[line_type]["variance"]
            
            summary[line_type]["variance_percentage"] = float(
                (variance_amt / budget_amt * 100).quantize(Decimal("0.01"))
                if budget_amt else Decimal("0")
            )
            summary[line_type]["budget"] = float(budget_amt)
            summary[line_type]["actual"] = float(actual_amt)
            summary[line_type]["variance"] = float(variance_amt)
        
        # Calculate overall performance metrics
        total_revenue = summary["revenue"]["actual"]
        total_expense = summary["expense"]["actual"]
        budgeted_revenue = summary["revenue"]["budget"]
        budgeted_expense = summary["expense"]["budget"]
        
        return {
            "budget_id": str(budget_id),
            "budget_name": budget.name,
            "fiscal_year": budget.fiscal_year,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "months_analyzed": len(months_in_range)
            },
            "summary": summary,
            "performance_metrics": {
                "actual_net_income": float(total_revenue - total_expense),
                "budgeted_net_income": float(budgeted_revenue - budgeted_expense),
                "net_income_variance": float(
                    (total_revenue - total_expense) - (budgeted_revenue - budgeted_expense)
                ),
                "revenue_achievement": float(
                    (total_revenue / budgeted_revenue * 100).quantize(Decimal("0.01"))
                    if budgeted_revenue else Decimal("0")
                ),
                "expense_control": float(
                    (budgeted_expense / total_expense * 100).quantize(Decimal("0.01"))
                    if total_expense else Decimal("0")
                )
            },
            "line_items": line_items_analysis,
            "variance_summary": {
                "favorable_count": sum(1 for li in line_items_analysis if li["variance_type"] == "favorable"),
                "unfavorable_count": sum(1 for li in line_items_analysis if li["variance_type"] == "unfavorable"),
                "total_line_items": len(line_items_analysis)
            },
            "alerts": self._generate_variance_alerts(line_items_analysis),
            "generated_at": datetime.utcnow().isoformat()
        }
    
    async def _get_actual_amounts(
        self,
        entity_id: uuid.UUID,
        start_date: date,
        end_date: date,
        group_by: str
    ) -> Dict[str, Dict[str, Decimal]]:
        """Get actual transaction amounts grouped by account/category."""
        # Get income
        income_query = select(
            Transaction.category_id,
            func.sum(Transaction.amount).label("total")
        ).where(
            and_(
                Transaction.entity_id == entity_id,
                Transaction.transaction_date >= start_date,
                Transaction.transaction_date <= end_date,
                Transaction.transaction_type == "income"
            )
        ).group_by(Transaction.category_id)
        
        income_result = await self.db.execute(income_query)
        
        # Get expenses
        expense_query = select(
            Transaction.category_id,
            func.sum(Transaction.amount).label("total")
        ).where(
            and_(
                Transaction.entity_id == entity_id,
                Transaction.transaction_date >= start_date,
                Transaction.transaction_date <= end_date,
                Transaction.transaction_type == "expense"
            )
        ).group_by(Transaction.category_id)
        
        expense_result = await self.db.execute(expense_query)
        
        actuals = {}
        for row in income_result.all():
            key = str(row[0]) if row[0] else "uncategorized"
            if key not in actuals:
                actuals[key] = {}
            actuals[key]["revenue"] = row[1] or Decimal("0")
        
        for row in expense_result.all():
            key = str(row[0]) if row[0] else "uncategorized"
            if key not in actuals:
                actuals[key] = {}
            actuals[key]["expense"] = row[1] or Decimal("0")
        
        return actuals
    
    def _generate_variance_alerts(
        self,
        line_items: List[Dict]
    ) -> List[Dict[str, Any]]:
        """Generate alerts for significant variances."""
        alerts = []
        
        for item in line_items:
            variance_pct = abs(item["variance_percentage"])
            
            # Alert thresholds
            if variance_pct > 50 and item["variance_type"] == "unfavorable":
                alerts.append({
                    "severity": "critical",
                    "account": item["account_name"],
                    "message": f"Significant unfavorable variance of {item['variance_percentage']:.1f}%",
                    "recommended_action": "Immediate review required. Consider budget revision."
                })
            elif variance_pct > 25 and item["variance_type"] == "unfavorable":
                alerts.append({
                    "severity": "warning",
                    "account": item["account_name"],
                    "message": f"Notable unfavorable variance of {item['variance_percentage']:.1f}%",
                    "recommended_action": "Review spending patterns and identify root cause."
                })
            elif item["percent_utilized"] > 90:
                alerts.append({
                    "severity": "info",
                    "account": item["account_name"],
                    "message": f"Budget {item['percent_utilized']:.1f}% utilized",
                    "recommended_action": "Monitor closely to avoid overrun."
                })
        
        return sorted(alerts, key=lambda x: {"critical": 0, "warning": 1, "info": 2}[x["severity"]])
    
    # =========================================================================
    # BUDGET FORECASTING
    # =========================================================================
    
    async def forecast_budget_performance(
        self,
        entity_id: uuid.UUID,
        budget_id: uuid.UUID,
        forecast_months: int = 3
    ) -> Dict[str, Any]:
        """
        Forecast future budget performance based on current trends.
        
        Uses historical actuals to project future performance.
        """
        budget = await self.get_budget(budget_id, include_line_items=True)
        if not budget:
            raise ValueError("Budget not found")
        
        # Get current variance analysis
        variance = await self.get_budget_vs_actual(entity_id, budget_id)
        
        # Calculate monthly run rate
        months_elapsed = variance["period"]["months_analyzed"]
        
        forecasts = []
        for item in variance["line_items"]:
            if months_elapsed > 0:
                monthly_run_rate = item["ytd_actual"] / months_elapsed
                projected_annual = monthly_run_rate * 12
                projected_variance = projected_annual - item["annual_budget"]
            else:
                monthly_run_rate = 0
                projected_annual = 0
                projected_variance = item["annual_budget"]
            
            forecasts.append({
                "account_name": item["account_name"],
                "line_type": item["line_type"],
                "annual_budget": item["annual_budget"],
                "ytd_actual": item["ytd_actual"],
                "monthly_run_rate": float(monthly_run_rate),
                "projected_annual": float(projected_annual),
                "projected_variance": float(projected_variance),
                "projected_variance_pct": float(
                    (projected_variance / item["annual_budget"] * 100)
                    if item["annual_budget"] else 0
                ),
                "confidence": "high" if months_elapsed >= 6 else "medium" if months_elapsed >= 3 else "low"
            })
        
        # Overall projections
        total_projected_revenue = sum(f["projected_annual"] for f in forecasts if f["line_type"] == "revenue")
        total_projected_expense = sum(f["projected_annual"] for f in forecasts if f["line_type"] == "expense")
        total_budget_revenue = sum(f["annual_budget"] for f in forecasts if f["line_type"] == "revenue")
        total_budget_expense = sum(f["annual_budget"] for f in forecasts if f["line_type"] == "expense")
        
        return {
            "budget_id": str(budget_id),
            "budget_name": budget.name,
            "fiscal_year": budget.fiscal_year,
            "forecast_basis": {
                "months_elapsed": months_elapsed,
                "data_through": variance["period"]["end_date"],
                "methodology": "Linear projection based on YTD run rate"
            },
            "overall_projection": {
                "revenue": {
                    "budgeted": float(total_budget_revenue),
                    "projected": float(total_projected_revenue),
                    "variance": float(total_projected_revenue - total_budget_revenue)
                },
                "expense": {
                    "budgeted": float(total_budget_expense),
                    "projected": float(total_projected_expense),
                    "variance": float(total_projected_expense - total_budget_expense)
                },
                "net_income": {
                    "budgeted": float(total_budget_revenue - total_budget_expense),
                    "projected": float(total_projected_revenue - total_projected_expense),
                    "variance": float(
                        (total_projected_revenue - total_projected_expense) -
                        (total_budget_revenue - total_budget_expense)
                    )
                }
            },
            "line_item_forecasts": forecasts,
            "risk_assessment": self._assess_budget_risk(forecasts),
            "generated_at": datetime.utcnow().isoformat()
        }
    
    def _assess_budget_risk(
        self,
        forecasts: List[Dict]
    ) -> Dict[str, Any]:
        """Assess overall budget risk based on forecasts."""
        high_risk_items = [f for f in forecasts if abs(f["projected_variance_pct"]) > 25 and f["line_type"] == "expense"]
        medium_risk_items = [f for f in forecasts if 10 < abs(f["projected_variance_pct"]) <= 25 and f["line_type"] == "expense"]
        
        total_projected_overrun = sum(
            max(0, f["projected_variance"]) 
            for f in forecasts if f["line_type"] == "expense"
        )
        
        if len(high_risk_items) > 3 or total_projected_overrun > 1000000:
            risk_level = "high"
            recommendation = "Immediate budget review and cost containment measures recommended"
        elif len(high_risk_items) > 0 or len(medium_risk_items) > 5:
            risk_level = "medium"
            recommendation = "Monitor spending closely and implement preventive controls"
        else:
            risk_level = "low"
            recommendation = "Budget performance on track, continue regular monitoring"
        
        return {
            "overall_risk_level": risk_level,
            "high_risk_item_count": len(high_risk_items),
            "medium_risk_item_count": len(medium_risk_items),
            "projected_total_overrun": float(total_projected_overrun),
            "recommendation": recommendation
        }
    
    # =========================================================================
    # DEPARTMENT/PROJECT BUDGETS
    # =========================================================================
    
    async def get_department_budget_summary(
        self,
        entity_id: uuid.UUID,
        budget_id: uuid.UUID,
        dimension_type: str = "department"
    ) -> Dict[str, Any]:
        """
        Get budget summary by department or other dimension.
        """
        budget = await self.get_budget(budget_id, include_line_items=True)
        if not budget:
            raise ValueError("Budget not found")
        
        # Group line items by dimension
        by_dimension = defaultdict(lambda: {
            "budget": Decimal("0"),
            "items": []
        })
        
        for item in budget.line_items:
            dim_id = str(item.dimension_id) if item.dimension_id else "unassigned"
            by_dimension[dim_id]["budget"] += item.total_budget or Decimal("0")
            by_dimension[dim_id]["items"].append({
                "account_name": item.account_name,
                "line_type": item.line_type,
                "budget": float(item.total_budget or Decimal("0"))
            })
        
        # Get dimension names
        if budget.line_items:
            dim_ids = [item.dimension_id for item in budget.line_items if item.dimension_id]
            if dim_ids:
                dim_result = await self.db.execute(
                    select(AccountingDimension).where(AccountingDimension.id.in_(dim_ids))
                )
                dimensions = {str(d.id): d.name for d in dim_result.scalars().all()}
            else:
                dimensions = {}
        else:
            dimensions = {}
        
        summary = []
        for dim_id, data in by_dimension.items():
            summary.append({
                "dimension_id": dim_id if dim_id != "unassigned" else None,
                "dimension_name": dimensions.get(dim_id, "Unassigned"),
                "total_budget": float(data["budget"]),
                "line_item_count": len(data["items"]),
                "items": data["items"]
            })
        
        return {
            "budget_id": str(budget_id),
            "budget_name": budget.name,
            "dimension_type": dimension_type,
            "departments": summary,
            "total_budget": float(sum(d["total_budget"] for d in summary)),
            "generated_at": datetime.utcnow().isoformat()
        }
    
    # =========================================================================
    # BUDGET COMPARISON
    # =========================================================================
    
    async def compare_budgets(
        self,
        entity_id: uuid.UUID,
        budget_ids: List[uuid.UUID]
    ) -> Dict[str, Any]:
        """
        Compare multiple budgets (e.g., year-over-year comparison).
        """
        budgets = []
        for bid in budget_ids:
            budget = await self.get_budget(bid, include_line_items=True)
            if budget:
                budgets.append(budget)
        
        if len(budgets) < 2:
            raise ValueError("At least two budgets required for comparison")
        
        # Build comparison matrix
        comparison = defaultdict(lambda: {})
        for budget in budgets:
            budget_key = f"{budget.fiscal_year} - {budget.name}"
            for item in budget.line_items:
                key = item.account_code or item.account_name
                comparison[key][budget_key] = float(item.total_budget or Decimal("0"))
        
        # Calculate year-over-year changes
        rows = []
        budget_keys = [f"{b.fiscal_year} - {b.name}" for b in budgets]
        
        for account_key, values in comparison.items():
            row = {
                "account": account_key,
                "values": values
            }
            
            # Calculate change between consecutive budgets
            changes = []
            for i in range(1, len(budget_keys)):
                current = values.get(budget_keys[i], 0)
                previous = values.get(budget_keys[i-1], 0)
                change = current - previous
                change_pct = (change / previous * 100) if previous else 0
                changes.append({
                    "from": budget_keys[i-1],
                    "to": budget_keys[i],
                    "change": change,
                    "change_percentage": round(change_pct, 2)
                })
            
            row["changes"] = changes
            rows.append(row)
        
        return {
            "entity_id": str(entity_id),
            "budgets_compared": [
                {"id": str(b.id), "name": f"{b.fiscal_year} - {b.name}"} 
                for b in budgets
            ],
            "comparison": rows,
            "summary": {
                "total_accounts": len(rows),
                "budget_totals": {
                    f"{b.fiscal_year} - {b.name}": float(
                        (b.total_revenue_budget or 0) + (b.total_expense_budget or 0)
                    )
                    for b in budgets
                }
            },
            "generated_at": datetime.utcnow().isoformat()
        }
    
    # =========================================================================
    # ACTUALS SYNC - Update budget with actual GL data
    # =========================================================================
    
    async def sync_actuals_to_budget(
        self,
        budget_id: uuid.UUID,
        entity_id: uuid.UUID,
        sync_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Sync actual amounts from GL/transactions to budget line items and periods.
        
        This updates:
        - BudgetLineItem monthly actual columns (jan_actual, feb_actual, etc.)
        - BudgetLineItem variance fields
        - BudgetPeriod actual amounts
        
        Should be run periodically (daily/weekly) to keep budget tracking current.
        """
        budget = await self.get_budget(budget_id, include_line_items=True)
        if not budget:
            raise ValueError("Budget not found")
        
        if not sync_date:
            sync_date = date.today()
        
        # Get actuals by month and account
        monthly_actuals = await self._get_monthly_actuals_detailed(
            entity_id=entity_id,
            start_date=budget.start_date,
            end_date=min(budget.end_date, sync_date),
        )
        
        months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
                  'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
        
        items_updated = 0
        
        for item in budget.line_items:
            # Match by GL account or account code
            key = str(item.gl_account_id) if item.gl_account_id else item.account_code
            if not key:
                continue
            
            item_actuals = monthly_actuals.get(key, {})
            total_actual = Decimal("0")
            total_budget = Decimal("0")
            
            for month in months:
                month_num = months.index(month) + 1
                actual = item_actuals.get(month_num, Decimal("0"))
                budget_amt = getattr(item, f"{month}_amount") or Decimal("0")
                
                # Update monthly actual
                setattr(item, f"{month}_actual", actual)
                total_actual += actual
                total_budget += budget_amt
            
            # Update totals and variance
            item.total_actual = total_actual
            item.total_variance = total_actual - total_budget
            
            if total_budget != 0:
                item.variance_pct = float((item.total_variance / total_budget * 100))
            else:
                item.variance_pct = 0
            
            # Determine if favorable
            if item.line_type == "revenue":
                item.is_favorable = item.total_variance >= 0
            else:  # expense, capex
                item.is_favorable = item.total_variance <= 0
            
            items_updated += 1
        
        # Update budget periods if they exist
        periods_result = await self.db.execute(
            select(BudgetPeriod).where(BudgetPeriod.budget_id == budget_id)
        )
        periods = list(periods_result.scalars().all())
        
        periods_updated = 0
        for period in periods:
            period_actuals = await self._get_period_actuals_detailed(
                entity_id=entity_id,
                start_date=period.start_date,
                end_date=min(period.end_date, sync_date),
            )
            
            period.actual_revenue = Decimal(str(period_actuals.get("revenue", 0)))
            period.actual_expense = Decimal(str(period_actuals.get("expense", 0)))
            period.actual_capex = Decimal(str(period_actuals.get("capex", 0)))
            period.actual_net_income = period.actual_revenue - period.actual_expense
            
            # Calculate variance
            period.revenue_variance = period.actual_revenue - (period.budgeted_revenue or Decimal("0"))
            period.expense_variance = period.actual_expense - (period.budgeted_expense or Decimal("0"))
            
            if period.budgeted_revenue and period.budgeted_revenue != 0:
                period.revenue_variance_pct = float(
                    (period.revenue_variance / period.budgeted_revenue * 100)
                )
            if period.budgeted_expense and period.budgeted_expense != 0:
                period.expense_variance_pct = float(
                    (period.expense_variance / period.budgeted_expense * 100)
                )
            
            period.last_actuals_sync = datetime.utcnow()
            periods_updated += 1
        
        # Update budget forecast date
        budget.actuals_through_date = sync_date
        
        await self.db.commit()
        
        logger.info(f"Synced actuals for budget {budget_id}: {items_updated} items, {periods_updated} periods")
        
        return {
            "success": True,
            "budget_id": str(budget_id),
            "sync_date": sync_date.isoformat(),
            "line_items_updated": items_updated,
            "periods_updated": periods_updated,
            "message": f"Synced actuals through {sync_date.isoformat()}",
        }
    
    async def _get_monthly_actuals_detailed(
        self,
        entity_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> Dict[str, Dict[int, Decimal]]:
        """
        Get actual amounts by GL account/category and month.
        
        Returns: {account_key: {month_num: amount}}
        """
        query = select(
            Transaction.category_id,
            func.extract('month', Transaction.transaction_date).label('month'),
            Transaction.transaction_type,
            func.sum(Transaction.amount).label('total')
        ).where(
            and_(
                Transaction.entity_id == entity_id,
                Transaction.transaction_date >= start_date,
                Transaction.transaction_date <= end_date,
            )
        ).group_by(
            Transaction.category_id,
            func.extract('month', Transaction.transaction_date),
            Transaction.transaction_type
        )
        
        result = await self.db.execute(query)
        
        actuals = {}
        for row in result.all():
            category_id, month, tx_type, total = row
            key = str(category_id) if category_id else "uncategorized"
            
            if key not in actuals:
                actuals[key] = {}
            
            actuals[key][int(month)] = total or Decimal("0")
        
        return actuals
    
    async def _get_period_actuals_detailed(
        self,
        entity_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> Dict[str, Decimal]:
        """Get total actuals for a period by type."""
        result = {
            "revenue": Decimal("0"),
            "expense": Decimal("0"),
            "capex": Decimal("0"),
        }
        
        query = select(
            Transaction.transaction_type,
            func.sum(Transaction.amount).label('total')
        ).where(
            and_(
                Transaction.entity_id == entity_id,
                Transaction.transaction_date >= start_date,
                Transaction.transaction_date <= end_date,
            )
        ).group_by(Transaction.transaction_type)
        
        rows = await self.db.execute(query)
        
        for row in rows.all():
            tx_type, total = row
            if tx_type == "income":
                result["revenue"] = total or Decimal("0")
            elif tx_type == "expense":
                result["expense"] = total or Decimal("0")
        
        return result