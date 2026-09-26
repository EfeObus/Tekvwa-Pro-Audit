"""
Tekvwa Pro Audit - Dashboard API Router

World-class organizational dashboards with NTAA 2025 compliance.

RBAC Permission Matrix:
- Owner: Full access to all dashboard widgets
- Admin: Financial + team management
- Accountant: Financial (Maker role for WREN)
- External Accountant: View + File, WREN Checker (Final)
- Auditor: View-only access
- Payroll Manager: Payroll widgets only
- Inventory Manager: Inventory widgets only
- Viewer: Limited read-only
"""

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import get_current_active_user, require_entity_access
from app.models.user import User, UserRole
from app.models.organization import OrganizationType
from app.services.dashboard_service import DashboardService
from app.utils.permissions import (
    OrganizationPermission,
    has_organization_permission,
    get_organization_permissions,
)


router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])


# ===========================================
# PERMISSION DECORATORS
# ===========================================

def require_permission(permission: OrganizationPermission):
    """Decorator factory for checking organization permissions."""
    async def permission_check(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        if current_user.is_platform_staff:
            # Platform staff have special access
            return current_user
        
        if not has_organization_permission(current_user.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission.value} required"
            )
        return current_user
    return permission_check


# ===========================================
# MAIN DASHBOARD ENDPOINTS
# ===========================================

@router.get("")
async def get_dashboard(
    entity_id: Optional[uuid.UUID] = Query(None, description="Entity ID to load dashboard for"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get the complete dashboard for the current user.
    
    Returns organization-type-specific dashboard with:
    - Tax Health Score (Red/Amber/Green)
    - NRS Connection Status
    - Compliance Calendar
    - Liquidity Ratio
    - Organization-specific widgets
    - World-class compliance modules
    - Permission-based view restrictions
    """
    service = DashboardService(db)
    
    try:
        dashboard = await service.get_dashboard(current_user, entity_id)
        return dashboard
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/tax-health")
async def get_tax_health_score(
    entity_id: uuid.UUID = Query(..., description="Entity ID"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get real-time Tax Health Score.
    
    Red/Amber/Green indicator based on:
    - Missing TINs
    - Unfiled VAT
    - Unverified WREN expenses
    - Approaching deadlines
    """
    service = DashboardService(db)
    
    # Get entity
    entity = await service._get_entity_if_accessible(current_user, entity_id)
    if not entity and not current_user.is_platform_staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied"
        )
    
    tax_health = await service._get_tax_health_score(entity, current_user.role)
    return tax_health


@router.get("/nrs-status")
async def get_nrs_status(
    entity_id: uuid.UUID = Query(..., description="Entity ID"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get NRS Connection Status - heartbeat monitor.
    
    Shows if the app is currently synced with Nigeria Revenue Service.
    """
    service = DashboardService(db)
    
    entity = await service._get_entity_if_accessible(current_user, entity_id)
    if not entity and not current_user.is_platform_staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied"
        )
    
    nrs_status = await service._get_nrs_connection_status(entity)
    return nrs_status


@router.get("/compliance-calendar")
async def get_compliance_calendar(
    entity_id: uuid.UUID = Query(..., description="Entity ID"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get Compliance Calendar with automatic countdowns.
    
    - VAT: 21st of every month
    - PAYE: 10th of every month
    - CIT: 6 months after fiscal year end
    - WHT: 21st of every month
    """
    service = DashboardService(db)
    
    entity = await service._get_entity_if_accessible(current_user, entity_id)
    if not entity and not current_user.is_platform_staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied"
        )
    
    calendar = await service._get_compliance_calendar(entity)
    return calendar


@router.get("/liquidity-ratio")
async def get_liquidity_ratio(
    entity_id: uuid.UUID = Query(..., description="Entity ID"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get Liquidity Ratio - Cash Runway tracking.
    
    Formula: Cash / Average Monthly Expenses
    2026 "Cash Runway" requirement.
    """
    # Check permissions
    if not current_user.is_platform_staff:
        if not has_organization_permission(current_user.role, OrganizationPermission.VIEW_REPORTS):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: view_reports required"
            )
    
    service = DashboardService(db)
    
    entity = await service._get_entity_if_accessible(current_user, entity_id)
    if not entity and not current_user.is_platform_staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied"
        )
    
    liquidity = await service._get_liquidity_ratio(entity)
    return liquidity


# ===========================================
# ORGANIZATION-TYPE-SPECIFIC ENDPOINTS
# ===========================================

@router.get("/sme")
async def get_sme_dashboard(
    entity_id: uuid.UUID = Query(..., description="Entity ID"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get SME & Small Business Dashboard widgets.
    
    Focus: Threshold Tracking & Input VAT Recovery.
    - Threshold Monitor: Progress towards ₦50M/₦100M limits
    - VAT Recovery Tracker: Input VAT Credits
    - WREN Validator: Uncategorized expense queue
    """
    service = DashboardService(db)
    
    entity = await service._get_entity_if_accessible(current_user, entity_id)
    if not entity and not current_user.is_platform_staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied"
        )
    
    sme_data = await service._get_sme_dashboard(entity, current_user)
    return sme_data


@router.get("/school")
async def get_school_dashboard(
    entity_id: uuid.UUID = Query(..., description="Entity ID"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get School Management Dashboard widgets.
    
    Focus: Payroll Compliance & WHT.
    - Teacher PAYE Summary: 2026 progressive bands
    - Fee Collection vs VAT: Tuition (Exempt) vs Taxable
    - Vendor WHT Vault: 5-10% WHT tracking
    """
    # Check payroll permission for full access
    has_payroll = current_user.is_platform_staff or has_organization_permission(
        current_user.role, OrganizationPermission.VIEW_PAYROLL
    )
    
    service = DashboardService(db)
    
    entity = await service._get_entity_if_accessible(current_user, entity_id)
    if not entity and not current_user.is_platform_staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied"
        )
    
    school_data = await service._get_school_dashboard(entity, current_user)
    
    # Apply permission restrictions
    if not has_payroll:
        # Remove sensitive payroll data
        if "teacher_paye" in school_data:
            school_data["teacher_paye"]["total_monthly_payroll"] = None
            school_data["teacher_paye"]["total_paye_liability"] = None
    
    return school_data


@router.get("/nonprofit")
async def get_nonprofit_dashboard(
    entity_id: uuid.UUID = Query(..., description="Entity ID"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get Non-Profit (NGO) Dashboard widgets.
    
    Focus: Fund Separation & Mission Efficiency.
    - Return on Mission (ROM): Program vs Admin spending
    - Restricted vs Unrestricted Funds
    - Donor Transparency Portal
    """
    service = DashboardService(db)
    
    entity = await service._get_entity_if_accessible(current_user, entity_id)
    if not entity and not current_user.is_platform_staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied"
        )
    
    nonprofit_data = await service._get_nonprofit_dashboard(entity, current_user)
    return nonprofit_data


@router.get("/individual")
async def get_individual_dashboard(
    entity_id: uuid.UUID = Query(..., description="Entity ID"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get Individual/Freelancer Dashboard widgets.
    
    Focus: Progressive Tax & Personal Reliefs.
    - Tax-Free Band Tracker: ₦800,000 allowance usage
    - Relief Document Vault: Rent, NHIA, Pension
    - Hustle vs Personal Toggle: Business/Personal separation
    """
    service = DashboardService(db)
    
    entity = await service._get_entity_if_accessible(current_user, entity_id)
    if not entity and not current_user.is_platform_staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied"
        )
    
    individual_data = await service._get_individual_dashboard(entity, current_user)
    return individual_data


# ===========================================
# WREN VALIDATION ENDPOINTS
# ===========================================

@router.get("/wren/pending")
async def get_pending_wren_expenses(
    entity_id: uuid.UUID = Query(..., description="Entity ID"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get pending WREN expenses requiring categorization/verification.
    
    WREN = Wholly, Exclusively, Reasonably, Necessarily for business.
    
    Maker-Checker SoD:
    - Maker (Accountant): Categorizes expense
    - Checker (External Accountant): Verifies categorization
    - Cannot verify own transactions
    """
    # Check WREN permission
    if not current_user.is_platform_staff:
        if not has_organization_permission(current_user.role, OrganizationPermission.VERIFY_WREN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: verify_wren required"
            )
    
    service = DashboardService(db)
    
    entity = await service._get_entity_if_accessible(current_user, entity_id)
    if not entity and not current_user.is_platform_staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied"
        )
    
    sme_data = await service._get_sme_dashboard(entity, current_user)
    return sme_data.get("wren_validator", {})


@router.post("/wren/{transaction_id}/categorize")
async def categorize_wren_expense(
    transaction_id: uuid.UUID,
    category_id: uuid.UUID = Query(..., description="Category to assign"),
    is_personal: bool = Query(False, description="Is this a personal expense?"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Categorize an expense (Maker action in WREN process).
    
    Only Maker roles can categorize:
    - Owner
    - Admin
    - Accountant
    
    External Accountant is Checker, not Maker.
    """
    # Check permission - must be Maker
    allowed_makers = [UserRole.OWNER, UserRole.ADMIN, UserRole.ACCOUNTANT]
    
    if not current_user.is_platform_staff:
        if current_user.role not in allowed_makers:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only Maker roles (Owner, Admin, Accountant) can categorize expenses"
            )
    
    # TODO: Implement categorization logic
    return {
        "success": True,
        "message": "Expense categorized successfully",
        "transaction_id": str(transaction_id),
        "category_id": str(category_id),
        "is_personal": is_personal,
        "next_step": "Awaiting Checker verification" if not current_user.is_platform_staff else "Complete",
    }


@router.post("/wren/{transaction_id}/verify")
async def verify_wren_expense(
    transaction_id: uuid.UUID,
    approved: bool = Query(..., description="Approve or reject categorization"),
    notes: Optional[str] = Query(None, description="Verification notes"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Verify a categorized expense (Checker action in WREN process).
    
    Checker roles:
    - Owner
    - Admin
    - Accountant
    - External Accountant
    
    CRITICAL: Checker cannot verify their own transactions (SoD enforcement).
    """
    # Check permission
    if not current_user.is_platform_staff:
        if not has_organization_permission(current_user.role, OrganizationPermission.VERIFY_WREN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: verify_wren required"
            )
    
    # TODO: Implement verification logic with SoD check
    # - Get transaction
    # - Check if current_user.id == transaction.created_by_id
    # - If same, raise 403 "Cannot verify your own transactions (SoD)"
    
    return {
        "success": True,
        "message": "Expense verification recorded" if approved else "Expense categorization rejected",
        "transaction_id": str(transaction_id),
        "verified_by": str(current_user.id),
        "approved": approved,
        "notes": notes,
    }


# ===========================================
# THRESHOLD MONITORING
# ===========================================

@router.get("/thresholds")
async def get_threshold_status(
    entity_id: uuid.UUID = Query(..., description="Entity ID"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get comprehensive threshold monitoring status.
    
    Thresholds tracked:
    - ₦50M: Small Company (0% CIT)
    - ₦100M: Medium Company (20% CIT) / Dev Levy Exemption
    - ₦250M: Fixed Assets limit
    - ₦25M: VAT Registration
    """
    service = DashboardService(db)
    
    entity = await service._get_entity_if_accessible(current_user, entity_id)
    if not entity and not current_user.is_platform_staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied"
        )
    
    sme_data = await service._get_sme_dashboard(entity, current_user)
    return {
        "threshold_monitor": sme_data.get("threshold_monitor", {}),
        "alerts": [],  # Would include threshold breach alerts
    }


# ===========================================
# VIEW PERMISSIONS
# ===========================================

@router.get("/permissions")
async def get_dashboard_permissions(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get current user's dashboard view permissions.
    
    Returns permission level for each dashboard widget:
    - full: Complete access
    - view_file: View + file tax returns
    - view: Read-only
    - draft_only: Can create drafts only
    - no_access: Widget hidden
    """
    from sqlalchemy import select
    from app.models.organization import Organization
    
    service = DashboardService(db)
    
    org_type = OrganizationType.SMALL_BUSINESS
    if current_user.organization_id:
        result = await db.execute(
            select(Organization).where(Organization.id == current_user.organization_id)
        )
        org = result.scalar_one_or_none()
        if org:
            org_type = org.organization_type
    
    permissions = service._get_view_restrictions(current_user.role, org_type)
    
    return {
        "user_role": current_user.role.value if current_user.role else None,
        "organization_type": org_type.value,
        "view_permissions": permissions,
        "organization_permissions": [
            p.value for p in get_organization_permissions(current_user.role)
        ] if current_user.role else [],
    }


# ===========================================
# QUICK ACTIONS
# ===========================================

@router.get("/quick-actions")
async def get_quick_actions(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get role-based quick actions for the dashboard.
    """
    from sqlalchemy import select
    from app.models.organization import Organization
    
    service = DashboardService(db)
    
    org_type = OrganizationType.SMALL_BUSINESS
    if current_user.organization_id:
        result = await db.execute(
            select(Organization).where(Organization.id == current_user.organization_id)
        )
        org = result.scalar_one_or_none()
        if org:
            org_type = org.organization_type
    
    actions = service._get_quick_actions_for_role(current_user.role, org_type)
    
    return {
        "actions": actions,
        "user_role": current_user.role.value if current_user.role else None,
        "organization_type": org_type.value,
    }


# ===========================================
# WIDGET MANAGEMENT ENDPOINTS
# ===========================================

from pydantic import BaseModel, Field
from typing import List, Dict, Any
from enum import Enum


class WidgetType(str, Enum):
    """Available dashboard widget types."""
    TAX_HEALTH = "tax_health"
    NRS_STATUS = "nrs_status"
    COMPLIANCE_CALENDAR = "compliance_calendar"
    LIQUIDITY_RATIO = "liquidity_ratio"
    THRESHOLD_MONITOR = "threshold_monitor"
    WREN_QUEUE = "wren_queue"
    VAT_RECOVERY = "vat_recovery"
    REVENUE_CHART = "revenue_chart"
    EXPENSE_BREAKDOWN = "expense_breakdown"
    BANK_BALANCE = "bank_balance"
    INVOICES_OUTSTANDING = "invoices_outstanding"
    PAYABLES_DUE = "payables_due"
    RECENT_TRANSACTIONS = "recent_transactions"
    KPI_SUMMARY = "kpi_summary"
    ALERTS = "alerts"
    QUICK_ACTIONS = "quick_actions"


class WidgetSize(str, Enum):
    """Widget display sizes."""
    SMALL = "small"      # 1x1 grid
    MEDIUM = "medium"    # 2x1 grid
    LARGE = "large"      # 2x2 grid
    WIDE = "wide"        # 3x1 grid
    FULL = "full"        # Full width


class WidgetConfig(BaseModel):
    """Widget configuration model."""
    widget_type: WidgetType
    size: WidgetSize = WidgetSize.MEDIUM
    position: int = Field(..., ge=0, description="Position in dashboard grid")
    visible: bool = True
    collapsed: bool = False
    refresh_interval_seconds: int = Field(default=300, ge=60, le=3600)
    custom_settings: Optional[Dict[str, Any]] = None


class WidgetLayoutRequest(BaseModel):
    """Request to update widget layout."""
    widgets: List[WidgetConfig]


class WidgetLayoutResponse(BaseModel):
    """Response with widget layout."""
    widgets: List[Dict[str, Any]]
    updated_at: str


class AvailableWidgetResponse(BaseModel):
    """Available widget information."""
    widget_type: str
    name: str
    description: str
    default_size: str
    requires_permission: Optional[str] = None
    available_for_org_types: List[str]


@router.get("/widgets")
async def get_widget_layout(
    entity_id: Optional[uuid.UUID] = Query(None, description="Entity ID"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get current user's widget layout configuration.
    
    Returns personalized widget arrangement including:
    - Widget types and positions
    - Size configurations
    - Visibility settings
    - Refresh intervals
    """
    from sqlalchemy import select
    from app.models.organization import Organization
    
    # Get organization type for default widgets
    org_type = OrganizationType.SMALL_BUSINESS
    if current_user.organization_id:
        result = await db.execute(
            select(Organization).where(Organization.id == current_user.organization_id)
        )
        org = result.scalar_one_or_none()
        if org:
            org_type = org.organization_type
    
    # Default widget layout based on organization type
    default_widgets = _get_default_widgets_for_org_type(org_type, current_user.role)
    
    # TODO: Fetch user's custom layout from database
    # For now, return defaults
    
    return {
        "widgets": default_widgets,
        "organization_type": org_type.value,
        "is_customized": False,
        "updated_at": None,
    }


@router.put("/widgets")
async def update_widget_layout(
    layout: WidgetLayoutRequest,
    entity_id: Optional[uuid.UUID] = Query(None, description="Entity ID"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Save user's custom widget layout.
    
    Allows users to:
    - Reorder widgets
    - Resize widgets
    - Hide/show widgets
    - Configure refresh intervals
    """
    # Validate widgets are available for user's role
    for widget in layout.widgets:
        if not _can_user_access_widget(widget.widget_type, current_user.role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Widget '{widget.widget_type.value}' not available for your role"
            )
    
    # TODO: Save to database
    # For now, return success response
    
    return {
        "success": True,
        "message": "Widget layout saved successfully",
        "widgets": [w.model_dump() for w in layout.widgets],
        "updated_at": date.today().isoformat(),
    }


@router.get("/widgets/available")
async def get_available_widgets(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get list of available widgets for current user.
    
    Based on user role and organization type, returns
    widgets that can be added to the dashboard.
    """
    from sqlalchemy import select
    from app.models.organization import Organization
    
    org_type = OrganizationType.SMALL_BUSINESS
    if current_user.organization_id:
        result = await db.execute(
            select(Organization).where(Organization.id == current_user.organization_id)
        )
        org = result.scalar_one_or_none()
        if org:
            org_type = org.organization_type
    
    all_widgets = [
        {
            "widget_type": WidgetType.TAX_HEALTH.value,
            "name": "Tax Health Score",
            "description": "Red/Amber/Green compliance indicator",
            "default_size": WidgetSize.MEDIUM.value,
            "requires_permission": None,
            "available_for_org_types": ["all"],
        },
        {
            "widget_type": WidgetType.NRS_STATUS.value,
            "name": "NRS Connection",
            "description": "Nigeria Revenue Service sync status",
            "default_size": WidgetSize.SMALL.value,
            "requires_permission": None,
            "available_for_org_types": ["all"],
        },
        {
            "widget_type": WidgetType.COMPLIANCE_CALENDAR.value,
            "name": "Compliance Calendar",
            "description": "Upcoming tax filing deadlines",
            "default_size": WidgetSize.LARGE.value,
            "requires_permission": None,
            "available_for_org_types": ["all"],
        },
        {
            "widget_type": WidgetType.LIQUIDITY_RATIO.value,
            "name": "Liquidity Ratio",
            "description": "Cash runway monitoring",
            "default_size": WidgetSize.MEDIUM.value,
            "requires_permission": "view_reports",
            "available_for_org_types": ["all"],
        },
        {
            "widget_type": WidgetType.THRESHOLD_MONITOR.value,
            "name": "Threshold Monitor",
            "description": "₦50M/₦100M threshold tracking",
            "default_size": WidgetSize.WIDE.value,
            "requires_permission": None,
            "available_for_org_types": ["small_business", "medium_company"],
        },
        {
            "widget_type": WidgetType.WREN_QUEUE.value,
            "name": "WREN Queue",
            "description": "Pending expense categorizations",
            "default_size": WidgetSize.MEDIUM.value,
            "requires_permission": "verify_wren",
            "available_for_org_types": ["all"],
        },
        {
            "widget_type": WidgetType.VAT_RECOVERY.value,
            "name": "VAT Recovery",
            "description": "Input VAT credit tracker",
            "default_size": WidgetSize.MEDIUM.value,
            "requires_permission": "view_reports",
            "available_for_org_types": ["all"],
        },
        {
            "widget_type": WidgetType.REVENUE_CHART.value,
            "name": "Revenue Chart",
            "description": "Income trends visualization",
            "default_size": WidgetSize.LARGE.value,
            "requires_permission": "view_reports",
            "available_for_org_types": ["all"],
        },
        {
            "widget_type": WidgetType.EXPENSE_BREAKDOWN.value,
            "name": "Expense Breakdown",
            "description": "Spending by category",
            "default_size": WidgetSize.LARGE.value,
            "requires_permission": "view_reports",
            "available_for_org_types": ["all"],
        },
        {
            "widget_type": WidgetType.BANK_BALANCE.value,
            "name": "Bank Balance",
            "description": "Current account balances",
            "default_size": WidgetSize.MEDIUM.value,
            "requires_permission": "view_bank",
            "available_for_org_types": ["all"],
        },
        {
            "widget_type": WidgetType.INVOICES_OUTSTANDING.value,
            "name": "Outstanding Invoices",
            "description": "Accounts receivable summary",
            "default_size": WidgetSize.MEDIUM.value,
            "requires_permission": "view_invoices",
            "available_for_org_types": ["all"],
        },
        {
            "widget_type": WidgetType.PAYABLES_DUE.value,
            "name": "Payables Due",
            "description": "Accounts payable summary",
            "default_size": WidgetSize.MEDIUM.value,
            "requires_permission": "view_expenses",
            "available_for_org_types": ["all"],
        },
        {
            "widget_type": WidgetType.RECENT_TRANSACTIONS.value,
            "name": "Recent Transactions",
            "description": "Latest transaction feed",
            "default_size": WidgetSize.WIDE.value,
            "requires_permission": "view_transactions",
            "available_for_org_types": ["all"],
        },
        {
            "widget_type": WidgetType.KPI_SUMMARY.value,
            "name": "KPI Summary",
            "description": "Key performance indicators",
            "default_size": WidgetSize.FULL.value,
            "requires_permission": "view_reports",
            "available_for_org_types": ["all"],
        },
        {
            "widget_type": WidgetType.ALERTS.value,
            "name": "Alerts",
            "description": "Compliance and threshold alerts",
            "default_size": WidgetSize.MEDIUM.value,
            "requires_permission": None,
            "available_for_org_types": ["all"],
        },
        {
            "widget_type": WidgetType.QUICK_ACTIONS.value,
            "name": "Quick Actions",
            "description": "Frequently used actions",
            "default_size": WidgetSize.SMALL.value,
            "requires_permission": None,
            "available_for_org_types": ["all"],
        },
    ]
    
    # Filter by permissions and org type
    available = []
    for widget in all_widgets:
        # Check org type
        if "all" not in widget["available_for_org_types"]:
            if org_type.value not in widget["available_for_org_types"]:
                continue
        
        # Check permission
        if widget["requires_permission"]:
            try:
                perm = OrganizationPermission(widget["requires_permission"])
                if not current_user.is_platform_staff:
                    if not has_organization_permission(current_user.role, perm):
                        continue
            except ValueError:
                pass  # Permission not in enum, allow
        
        available.append(widget)
    
    return {
        "available_widgets": available,
        "total": len(available),
    }


@router.post("/widgets/{widget_type}/refresh")
async def refresh_widget(
    widget_type: WidgetType,
    entity_id: uuid.UUID = Query(..., description="Entity ID"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Force refresh data for a specific widget.
    
    Bypasses cache and fetches fresh data.
    """
    if not _can_user_access_widget(widget_type, current_user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Widget '{widget_type.value}' not available for your role"
        )
    
    service = DashboardService(db)
    entity = await service._get_entity_if_accessible(current_user, entity_id)
    
    if not entity and not current_user.is_platform_staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied"
        )
    
    # Fetch fresh data based on widget type
    data = {}
    if widget_type == WidgetType.TAX_HEALTH:
        data = await service._get_tax_health_score(entity, current_user.role)
    elif widget_type == WidgetType.NRS_STATUS:
        data = await service._get_nrs_connection_status(entity)
    elif widget_type == WidgetType.COMPLIANCE_CALENDAR:
        data = await service._get_compliance_calendar(entity)
    elif widget_type == WidgetType.LIQUIDITY_RATIO:
        data = await service._get_liquidity_ratio(entity)
    elif widget_type == WidgetType.THRESHOLD_MONITOR:
        sme_data = await service._get_sme_dashboard(entity, current_user)
        data = sme_data.get("threshold_monitor", {})
    elif widget_type == WidgetType.WREN_QUEUE:
        sme_data = await service._get_sme_dashboard(entity, current_user)
        data = sme_data.get("wren_validator", {})
    else:
        # Return placeholder for other widgets
        data = {"message": f"Data for {widget_type.value}", "refreshed_at": date.today().isoformat()}
    
    return {
        "widget_type": widget_type.value,
        "data": data,
        "refreshed_at": date.today().isoformat(),
        "cached": False,
    }


# ===========================================
# ALERT CONFIGURATION ENDPOINTS
# ===========================================

class AlertType(str, Enum):
    """Types of dashboard alerts."""
    THRESHOLD_WARNING = "threshold_warning"
    THRESHOLD_BREACH = "threshold_breach"
    DEADLINE_APPROACHING = "deadline_approaching"
    DEADLINE_OVERDUE = "deadline_overdue"
    WREN_PENDING = "wren_pending"
    NRS_DISCONNECTED = "nrs_disconnected"
    TAX_HEALTH_DECLINE = "tax_health_decline"
    LOW_LIQUIDITY = "low_liquidity"
    LARGE_TRANSACTION = "large_transaction"
    FAILED_FILING = "failed_filing"


class AlertPriority(str, Enum):
    """Alert priority levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertConfigRequest(BaseModel):
    """Alert configuration request."""
    alert_type: AlertType
    enabled: bool = True
    priority: AlertPriority = AlertPriority.MEDIUM
    threshold_value: Optional[float] = None
    threshold_days: Optional[int] = None
    notify_email: bool = True
    notify_in_app: bool = True
    notify_sms: bool = False


class AlertResponse(BaseModel):
    """Alert item response."""
    id: str
    alert_type: str
    priority: str
    title: str
    message: str
    created_at: str
    is_read: bool = False
    entity_id: Optional[str] = None
    action_url: Optional[str] = None


@router.get("/alerts")
async def get_alerts(
    entity_id: Optional[uuid.UUID] = Query(None, description="Filter by entity"),
    priority: Optional[AlertPriority] = Query(None, description="Filter by priority"),
    unread_only: bool = Query(False, description="Show only unread alerts"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get active alerts for current user.
    
    Returns compliance alerts, threshold warnings, and
    deadline notifications based on alert configuration.
    """
    service = DashboardService(db)
    
    # Generate alerts based on current state
    alerts = []
    
    # Get entities user has access to
    if entity_id:
        entity = await service._get_entity_if_accessible(current_user, entity_id)
        if entity:
            entity_alerts = await _generate_entity_alerts(service, entity, current_user)
            alerts.extend(entity_alerts)
    else:
        # Get alerts for all accessible entities
        # TODO: Fetch user's entities from database
        pass
    
    # Apply filters
    if priority:
        alerts = [a for a in alerts if a.get("priority") == priority.value]
    
    if unread_only:
        alerts = [a for a in alerts if not a.get("is_read", False)]
    
    # Sort by priority and date
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    alerts.sort(key=lambda a: (priority_order.get(a.get("priority", "low"), 4), a.get("created_at", "")))
    
    return {
        "alerts": alerts[:limit],
        "total": len(alerts),
        "unread_count": len([a for a in alerts if not a.get("is_read", False)]),
    }


@router.get("/alerts/config")
async def get_alert_configuration(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get user's alert configuration settings.
    """
    # Default alert configurations
    default_configs = [
        {
            "alert_type": AlertType.THRESHOLD_WARNING.value,
            "enabled": True,
            "priority": AlertPriority.MEDIUM.value,
            "threshold_value": 80,  # Warn at 80% of threshold
            "notify_email": True,
            "notify_in_app": True,
            "notify_sms": False,
            "description": "Warning when approaching ₦50M/₦100M thresholds",
        },
        {
            "alert_type": AlertType.THRESHOLD_BREACH.value,
            "enabled": True,
            "priority": AlertPriority.CRITICAL.value,
            "threshold_value": 100,
            "notify_email": True,
            "notify_in_app": True,
            "notify_sms": True,
            "description": "Alert when threshold is exceeded",
        },
        {
            "alert_type": AlertType.DEADLINE_APPROACHING.value,
            "enabled": True,
            "priority": AlertPriority.HIGH.value,
            "threshold_days": 7,
            "notify_email": True,
            "notify_in_app": True,
            "notify_sms": False,
            "description": "Filing deadline approaching within days",
        },
        {
            "alert_type": AlertType.DEADLINE_OVERDUE.value,
            "enabled": True,
            "priority": AlertPriority.CRITICAL.value,
            "threshold_days": 0,
            "notify_email": True,
            "notify_in_app": True,
            "notify_sms": True,
            "description": "Missed filing deadline",
        },
        {
            "alert_type": AlertType.WREN_PENDING.value,
            "enabled": True,
            "priority": AlertPriority.MEDIUM.value,
            "threshold_value": 10,  # Warn when 10+ pending
            "notify_email": False,
            "notify_in_app": True,
            "notify_sms": False,
            "description": "WREN categorizations pending review",
        },
        {
            "alert_type": AlertType.NRS_DISCONNECTED.value,
            "enabled": True,
            "priority": AlertPriority.HIGH.value,
            "notify_email": True,
            "notify_in_app": True,
            "notify_sms": False,
            "description": "NRS connection lost",
        },
        {
            "alert_type": AlertType.TAX_HEALTH_DECLINE.value,
            "enabled": True,
            "priority": AlertPriority.MEDIUM.value,
            "notify_email": True,
            "notify_in_app": True,
            "notify_sms": False,
            "description": "Tax health score decreased",
        },
        {
            "alert_type": AlertType.LOW_LIQUIDITY.value,
            "enabled": True,
            "priority": AlertPriority.HIGH.value,
            "threshold_value": 2,  # Less than 2 months runway
            "notify_email": True,
            "notify_in_app": True,
            "notify_sms": True,
            "description": "Cash runway below threshold months",
        },
        {
            "alert_type": AlertType.LARGE_TRANSACTION.value,
            "enabled": False,
            "priority": AlertPriority.MEDIUM.value,
            "threshold_value": 1000000,  # ₦1M
            "notify_email": True,
            "notify_in_app": True,
            "notify_sms": False,
            "description": "Transaction exceeds amount threshold",
        },
        {
            "alert_type": AlertType.FAILED_FILING.value,
            "enabled": True,
            "priority": AlertPriority.CRITICAL.value,
            "notify_email": True,
            "notify_in_app": True,
            "notify_sms": True,
            "description": "Tax filing submission failed",
        },
    ]
    
    # TODO: Fetch user's custom settings from database
    
    return {
        "configurations": default_configs,
        "is_customized": False,
    }


@router.put("/alerts/config")
async def update_alert_configuration(
    configs: List[AlertConfigRequest],
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Update user's alert configuration settings.
    """
    # TODO: Save to database
    
    return {
        "success": True,
        "message": "Alert configuration updated",
        "updated_count": len(configs),
    }


@router.post("/alerts/{alert_id}/read")
async def mark_alert_read(
    alert_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """Mark a single alert as read."""
    # TODO: Update in database
    
    return {
        "success": True,
        "alert_id": str(alert_id),
        "is_read": True,
    }


@router.post("/alerts/read-all")
async def mark_all_alerts_read(
    entity_id: Optional[uuid.UUID] = Query(None, description="Entity ID filter"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """Mark all alerts as read."""
    if entity_id is not None:
        # entity_id is an optional filter here, so require_entity_access can't be used as a Depends()
        # -- it would make the parameter mandatory. Check inline instead, same 404-on-mismatch contract.
        await require_entity_access(entity_id=entity_id, current_user=current_user, db=db)

    # TODO: Update in database

    return {
        "success": True,
        "message": "All alerts marked as read",
    }


@router.delete("/alerts/{alert_id}")
async def dismiss_alert(
    alert_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """Dismiss/delete an alert."""
    # TODO: Delete from database
    
    return {
        "success": True,
        "alert_id": str(alert_id),
        "dismissed": True,
    }


# ===========================================
# KPI ENDPOINTS
# ===========================================

class KPIPeriod(str, Enum):
    """KPI reporting periods."""
    TODAY = "today"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"
    YTD = "ytd"
    CUSTOM = "custom"


class KPICategory(str, Enum):
    """KPI categories."""
    REVENUE = "revenue"
    EXPENSES = "expenses"
    PROFIT = "profit"
    TAX = "tax"
    COMPLIANCE = "compliance"
    OPERATIONS = "operations"
    LIQUIDITY = "liquidity"


@router.get("/kpis")
async def get_kpis(
    entity_id: uuid.UUID = Query(..., description="Entity ID"),
    period: KPIPeriod = Query(KPIPeriod.MONTH, description="Reporting period"),
    categories: Optional[List[KPICategory]] = Query(None, description="Filter by categories"),
    start_date: Optional[date] = Query(None, description="Custom period start"),
    end_date: Optional[date] = Query(None, description="Custom period end"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get Key Performance Indicators for entity.
    
    Returns KPIs across categories:
    - Revenue: Total sales, average invoice, growth
    - Expenses: Total spend, WREN compliance rate
    - Profit: Net margin, gross margin
    - Tax: Effective tax rate, VAT recovery
    - Compliance: Tax health score, filing rate
    - Operations: Transaction volume, processing time
    - Liquidity: Cash runway, current ratio
    """
    # Check permission
    if not current_user.is_platform_staff:
        if not has_organization_permission(current_user.role, OrganizationPermission.VIEW_REPORTS):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: view_reports required"
            )
    
    service = DashboardService(db)
    entity = await service._get_entity_if_accessible(current_user, entity_id)
    
    if not entity and not current_user.is_platform_staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied"
        )
    
    # Calculate date range based on period
    from datetime import timedelta
    today = date.today()
    
    if period == KPIPeriod.CUSTOM:
        if not start_date or not end_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_date and end_date required for custom period"
            )
        period_start = start_date
        period_end = end_date
    else:
        period_end = today
        if period == KPIPeriod.TODAY:
            period_start = today
        elif period == KPIPeriod.WEEK:
            period_start = today - timedelta(days=7)
        elif period == KPIPeriod.MONTH:
            period_start = today.replace(day=1)
        elif period == KPIPeriod.QUARTER:
            quarter_month = ((today.month - 1) // 3) * 3 + 1
            period_start = today.replace(month=quarter_month, day=1)
        elif period == KPIPeriod.YEAR:
            period_start = today.replace(month=1, day=1)
        elif period == KPIPeriod.YTD:
            period_start = today.replace(month=1, day=1)
    
    # Generate KPIs (placeholder data)
    kpis = {
        "period": {
            "type": period.value,
            "start_date": period_start.isoformat(),
            "end_date": period_end.isoformat(),
        },
        "revenue": {
            "total_revenue": 15500000.00,
            "invoice_count": 47,
            "average_invoice": 329787.23,
            "growth_percent": 12.5,
            "previous_period": 13777777.78,
            "trend": "up",
        },
        "expenses": {
            "total_expenses": 8750000.00,
            "transaction_count": 156,
            "wren_compliance_rate": 94.2,
            "uncategorized_count": 9,
            "growth_percent": 5.3,
            "trend": "up",
        },
        "profit": {
            "gross_profit": 6750000.00,
            "gross_margin_percent": 43.5,
            "net_profit": 4250000.00,
            "net_margin_percent": 27.4,
            "ebitda": 5100000.00,
        },
        "tax": {
            "vat_collected": 1162500.00,
            "vat_paid": 656250.00,
            "vat_net": 506250.00,
            "vat_recovery_rate": 56.4,
            "paye_liability": 425000.00,
            "wht_deducted": 87500.00,
            "effective_tax_rate": 24.7,
        },
        "compliance": {
            "tax_health_score": 85,
            "tax_health_status": "green",
            "filings_on_time": 11,
            "filings_late": 1,
            "filing_rate_percent": 91.7,
            "pending_wren": 9,
            "nrs_sync_status": "connected",
        },
        "operations": {
            "total_transactions": 203,
            "receipts_attached_rate": 87.2,
            "average_processing_days": 2.3,
            "automation_rate": 65.0,
        },
        "liquidity": {
            "cash_balance": 8500000.00,
            "cash_runway_months": 4.7,
            "current_ratio": 2.1,
            "quick_ratio": 1.8,
            "receivables_outstanding": 3200000.00,
            "payables_due": 1850000.00,
        },
    }
    
    # Filter by categories if specified
    if categories:
        filtered_kpis = {"period": kpis["period"]}
        for cat in categories:
            if cat.value in kpis:
                filtered_kpis[cat.value] = kpis[cat.value]
        kpis = filtered_kpis
    
    return kpis


@router.get("/kpis/{category}")
async def get_kpi_detail(
    category: KPICategory,
    entity_id: uuid.UUID = Query(..., description="Entity ID"),
    period: KPIPeriod = Query(KPIPeriod.MONTH, description="Reporting period"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get detailed KPI breakdown for a specific category.
    
    Returns detailed drill-down data with historical trends.
    """
    if not current_user.is_platform_staff:
        if not has_organization_permission(current_user.role, OrganizationPermission.VIEW_REPORTS):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: view_reports required"
            )
    
    service = DashboardService(db)
    entity = await service._get_entity_if_accessible(current_user, entity_id)
    
    if not entity and not current_user.is_platform_staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied"
        )
    
    # Return detailed data based on category
    if category == KPICategory.REVENUE:
        return {
            "category": "revenue",
            "summary": {
                "total": 15500000.00,
                "growth_percent": 12.5,
            },
            "breakdown": {
                "by_type": [
                    {"type": "product_sales", "amount": 10850000.00, "percent": 70.0},
                    {"type": "services", "amount": 3875000.00, "percent": 25.0},
                    {"type": "other", "amount": 775000.00, "percent": 5.0},
                ],
                "by_customer": [
                    {"customer": "Acme Corp", "amount": 3500000.00},
                    {"customer": "Beta Ltd", "amount": 2800000.00},
                    {"customer": "Gamma Inc", "amount": 2100000.00},
                ],
            },
            "trend": [
                {"month": "Jan", "amount": 12000000.00},
                {"month": "Feb", "amount": 13500000.00},
                {"month": "Mar", "amount": 15500000.00},
            ],
        }
    elif category == KPICategory.TAX:
        return {
            "category": "tax",
            "summary": {
                "total_liability": 1018750.00,
                "effective_rate": 24.7,
            },
            "breakdown": {
                "vat": {
                    "collected": 1162500.00,
                    "paid": 656250.00,
                    "net": 506250.00,
                    "recovery_rate": 56.4,
                },
                "paye": {
                    "liability": 425000.00,
                    "employees": 12,
                    "average_per_employee": 35416.67,
                },
                "wht": {
                    "deducted": 87500.00,
                    "transactions": 8,
                },
                "cit": {
                    "estimated": 0,  # Calculated at year end
                    "rate_applicable": 25,
                },
            },
        }
    else:
        return {
            "category": category.value,
            "message": "Detailed breakdown not yet implemented",
        }


@router.get("/kpis/comparison")
async def compare_kpis(
    entity_id: uuid.UUID = Query(..., description="Entity ID"),
    current_period: KPIPeriod = Query(KPIPeriod.MONTH),
    compare_period: KPIPeriod = Query(KPIPeriod.MONTH),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Compare KPIs between two periods.
    
    Returns side-by-side comparison with change percentages.
    """
    if not current_user.is_platform_staff:
        if not has_organization_permission(current_user.role, OrganizationPermission.VIEW_REPORTS):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: view_reports required"
            )
    
    # Placeholder comparison data
    return {
        "current_period": current_period.value,
        "compare_period": compare_period.value,
        "comparison": {
            "revenue": {
                "current": 15500000.00,
                "previous": 13777777.78,
                "change_amount": 1722222.22,
                "change_percent": 12.5,
            },
            "expenses": {
                "current": 8750000.00,
                "previous": 8306451.61,
                "change_amount": 443548.39,
                "change_percent": 5.3,
            },
            "net_profit": {
                "current": 4250000.00,
                "previous": 3471326.16,
                "change_amount": 778673.84,
                "change_percent": 22.4,
            },
            "tax_health": {
                "current": 85,
                "previous": 78,
                "change_amount": 7,
                "change_percent": 9.0,
            },
        },
    }


# ===========================================
# DASHBOARD PREFERENCES
# ===========================================

class DashboardPreferences(BaseModel):
    """User's dashboard preferences."""
    default_entity_id: Optional[uuid.UUID] = None
    default_period: KPIPeriod = KPIPeriod.MONTH
    theme: str = "system"
    compact_mode: bool = False
    show_tooltips: bool = True
    auto_refresh: bool = True
    refresh_interval_minutes: int = Field(default=5, ge=1, le=60)
    chart_type: str = "bar"
    currency_format: str = "NGN"
    date_format: str = "DD/MM/YYYY"


@router.get("/preferences")
async def get_dashboard_preferences(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """Get user's dashboard preferences."""
    # TODO: Fetch from database
    
    return {
        "preferences": {
            "default_entity_id": None,
            "default_period": KPIPeriod.MONTH.value,
            "theme": "system",
            "compact_mode": False,
            "show_tooltips": True,
            "auto_refresh": True,
            "refresh_interval_minutes": 5,
            "chart_type": "bar",
            "currency_format": "NGN",
            "date_format": "DD/MM/YYYY",
        },
        "is_customized": False,
    }


@router.put("/preferences")
async def update_dashboard_preferences(
    preferences: DashboardPreferences,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """Update user's dashboard preferences."""
    # TODO: Save to database
    
    return {
        "success": True,
        "message": "Preferences updated",
        "preferences": preferences.model_dump(),
    }


# ===========================================
# REAL-TIME METRICS ENDPOINT
# ===========================================

@router.get("/metrics/realtime")
async def get_realtime_metrics(
    entity_id: uuid.UUID = Query(..., description="Entity ID"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get real-time dashboard metrics.
    
    Lightweight endpoint for frequent polling or SSE updates.
    Returns only frequently-changing metrics.
    """
    service = DashboardService(db)
    entity = await service._get_entity_if_accessible(current_user, entity_id)
    
    if not entity and not current_user.is_platform_staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied"
        )
    
    # Get critical real-time data
    tax_health = await service._get_tax_health_score(entity, current_user.role)
    nrs_status = await service._get_nrs_connection_status(entity)
    
    return {
        "timestamp": date.today().isoformat(),
        "tax_health": {
            "score": tax_health.get("score", 0),
            "status": tax_health.get("status", "unknown"),
        },
        "nrs": {
            "connected": nrs_status.get("connected", False),
            "last_sync": nrs_status.get("last_sync"),
        },
        "pending_actions": {
            "wren_categorizations": 9,
            "invoices_awaiting_payment": 12,
            "approaching_deadlines": 2,
        },
        "today": {
            "transactions": 7,
            "revenue": 450000.00,
            "expenses": 125000.00,
        },
    }


@router.get("/metrics/summary")
async def get_metrics_summary(
    entity_id: uuid.UUID = Query(..., description="Entity ID"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get compact metrics summary for mobile/widgets.
    
    Returns minimal data set for performance.
    """
    service = DashboardService(db)
    entity = await service._get_entity_if_accessible(current_user, entity_id)
    
    if not entity and not current_user.is_platform_staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied"
        )
    
    return {
        "tax_health_score": 85,
        "tax_health_status": "green",
        "nrs_connected": True,
        "days_to_next_deadline": 8,
        "pending_wren": 9,
        "mtd_revenue": 15500000.00,
        "mtd_expenses": 8750000.00,
        "cash_balance": 8500000.00,
    }


# ===========================================
# HELPER FUNCTIONS
# ===========================================

def _get_default_widgets_for_org_type(org_type: OrganizationType, role: Optional[UserRole]) -> List[Dict[str, Any]]:
    """Get default widget layout based on organization type."""
    base_widgets = [
        {"widget_type": "tax_health", "size": "medium", "position": 0, "visible": True},
        {"widget_type": "nrs_status", "size": "small", "position": 1, "visible": True},
        {"widget_type": "compliance_calendar", "size": "large", "position": 2, "visible": True},
        {"widget_type": "alerts", "size": "medium", "position": 3, "visible": True},
        {"widget_type": "quick_actions", "size": "small", "position": 4, "visible": True},
    ]
    
    # Add org-type specific widgets
    if org_type == OrganizationType.SMALL_BUSINESS:
        base_widgets.extend([
            {"widget_type": "threshold_monitor", "size": "wide", "position": 5, "visible": True},
            {"widget_type": "vat_recovery", "size": "medium", "position": 6, "visible": True},
            {"widget_type": "wren_queue", "size": "medium", "position": 7, "visible": True},
        ])
    elif org_type == OrganizationType.SCHOOL:
        base_widgets.extend([
            {"widget_type": "payables_due", "size": "medium", "position": 5, "visible": True},
            {"widget_type": "revenue_chart", "size": "large", "position": 6, "visible": True},
        ])
    
    # Add financial widgets for allowed roles
    if role in [UserRole.OWNER, UserRole.ADMIN, UserRole.ACCOUNTANT]:
        base_widgets.extend([
            {"widget_type": "liquidity_ratio", "size": "medium", "position": 8, "visible": True},
            {"widget_type": "kpi_summary", "size": "full", "position": 9, "visible": True},
        ])
    
    return base_widgets


def _can_user_access_widget(widget_type: WidgetType, role: Optional[UserRole]) -> bool:
    """Check if user role can access a widget type."""
    # Define restricted widgets
    financial_widgets = {
        WidgetType.LIQUIDITY_RATIO,
        WidgetType.REVENUE_CHART,
        WidgetType.EXPENSE_BREAKDOWN,
        WidgetType.KPI_SUMMARY,
        WidgetType.BANK_BALANCE,
    }
    
    wren_widgets = {WidgetType.WREN_QUEUE}
    
    # Viewers have limited access
    if role == UserRole.VIEWER:
        if widget_type in financial_widgets or widget_type in wren_widgets:
            return False
    
    return True


async def _generate_entity_alerts(service, entity, user) -> List[Dict[str, Any]]:
    """Generate alerts for an entity based on current state."""
    alerts = []
    
    # Get tax health
    tax_health = await service._get_tax_health_score(entity, user.role)
    if tax_health.get("status") == "red":
        alerts.append({
            "id": str(uuid.uuid4()),
            "alert_type": AlertType.TAX_HEALTH_DECLINE.value,
            "priority": AlertPriority.HIGH.value,
            "title": "Tax Health Critical",
            "message": f"Tax health score has dropped to {tax_health.get('score', 0)}. Immediate action required.",
            "created_at": date.today().isoformat(),
            "is_read": False,
            "entity_id": str(entity.id) if entity else None,
            "action_url": "/dashboard/tax-health",
        })
    
    # Check NRS status
    nrs_status = await service._get_nrs_connection_status(entity)
    if not nrs_status.get("connected", True):
        alerts.append({
            "id": str(uuid.uuid4()),
            "alert_type": AlertType.NRS_DISCONNECTED.value,
            "priority": AlertPriority.HIGH.value,
            "title": "NRS Disconnected",
            "message": "Connection to Nigeria Revenue Service has been lost. E-invoicing may be affected.",
            "created_at": date.today().isoformat(),
            "is_read": False,
            "entity_id": str(entity.id) if entity else None,
            "action_url": "/settings/integrations",
        })
    
    # Check compliance calendar
    calendar = await service._get_compliance_calendar(entity)
    for deadline in calendar.get("upcoming", []):
        days_remaining = deadline.get("days_remaining", 999)
        if days_remaining <= 0:
            alerts.append({
                "id": str(uuid.uuid4()),
                "alert_type": AlertType.DEADLINE_OVERDUE.value,
                "priority": AlertPriority.CRITICAL.value,
                "title": f"{deadline.get('type', 'Filing')} Overdue",
                "message": f"{deadline.get('description', 'Filing deadline')} was due on {deadline.get('due_date', 'unknown')}.",
                "created_at": date.today().isoformat(),
                "is_read": False,
                "entity_id": str(entity.id) if entity else None,
                "action_url": f"/filings/{deadline.get('type', '').lower()}",
            })
        elif days_remaining <= 7:
            alerts.append({
                "id": str(uuid.uuid4()),
                "alert_type": AlertType.DEADLINE_APPROACHING.value,
                "priority": AlertPriority.HIGH.value,
                "title": f"{deadline.get('type', 'Filing')} Due Soon",
                "message": f"{deadline.get('description', 'Filing deadline')} is due in {days_remaining} days.",
                "created_at": date.today().isoformat(),
                "is_read": False,
                "entity_id": str(entity.id) if entity else None,
                "action_url": f"/filings/{deadline.get('type', '').lower()}",
            })
    
    return alerts
