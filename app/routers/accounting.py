"""
Tekvwa Pro Audit - Accounting Router

API endpoints for Chart of Accounts and General Ledger operations.
This is the central accounting API that all financial modules integrate with.

SKU Usage Metering:
- Journal entry creation counts toward transaction limits
"""

import uuid
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, get_current_entity_id, require_within_usage_limit, require_entity_access
from app.models.user import User
from app.models.entity import BusinessEntity
from app.models.accounting import (
    AccountType, JournalEntryStatus, JournalEntryType, FiscalPeriodStatus
)
from app.models.audit_consolidated import AuditAction
from app.models.sku import UsageMetricType
from app.schemas.accounting import (
    ChartOfAccountsCreate, ChartOfAccountsUpdate, ChartOfAccountsResponse,
    ChartOfAccountsTree,
    FiscalYearCreate, FiscalYearResponse,
    FiscalPeriodCreate, FiscalPeriodUpdate, FiscalPeriodResponse,
    JournalEntryCreate, JournalEntryUpdate, JournalEntryResponse,
    JournalEntryListResponse,
    TrialBalanceReport, IncomeStatementReport, BalanceSheetReport,
    CashFlowStatementReport,
    AccountLedgerReport,
    GLPostingRequest, GLPostingResponse,
    PeriodCloseChecklist, PeriodCloseRequest, PeriodCloseResponse,
    FixedAssetRegisterSummary, GLFixedAssetValidation, EnhancedBalanceSheetReport,
)
from app.services.accounting_service import AccountingService
from app.services.audit_service import AuditService
from app.services.metering_service import MeteringService


router = APIRouter(prefix="/api/v1/entities/{entity_id}/accounting", tags=["Accounting"])


# ============================================================================
# CHART OF ACCOUNTS ENDPOINTS
# ============================================================================

@router.get("/chart-of-accounts", response_model=List[ChartOfAccountsResponse])
async def list_chart_of_accounts(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    account_type: Optional[AccountType] = Query(None, description="Filter by account type"),
    is_active: bool = Query(True, description="Filter by active status"),
    include_headers: bool = Query(True, description="Include header accounts"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get chart of accounts for entity."""
    service = AccountingService(db)
    accounts = await service.get_chart_of_accounts(
        entity_id=entity_id,
        account_type=account_type,
        is_active=is_active,
        include_headers=include_headers,
    )
    return accounts


@router.get("/chart-of-accounts/tree", response_model=ChartOfAccountsTree)
async def get_chart_of_accounts_tree(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get chart of accounts as hierarchical tree."""
    service = AccountingService(db)
    accounts = await service.get_chart_of_accounts(entity_id=entity_id)
    
    # Build tree structure
    accounts_by_id = {acc.id: acc for acc in accounts}
    root_accounts = [acc for acc in accounts if acc.parent_id is None]
    
    def build_children(account):
        children = [acc for acc in accounts if acc.parent_id == account.id]
        return [
            ChartOfAccountsTree(
                id=child.id,
                account_code=child.account_code,
                account_name=child.account_name,
                account_type=child.account_type,
                account_sub_type=child.account_sub_type,
                normal_balance=child.normal_balance,
                current_balance=child.current_balance,
                level=child.level,
                is_header=child.is_header,
                is_active=child.is_active,
                children=build_children(child),
            )
            for child in sorted(children, key=lambda x: x.account_code)
        ]
    
    # Create top-level tree
    tree = ChartOfAccountsTree(
        id=uuid.UUID('00000000-0000-0000-0000-000000000000'),
        account_code="ROOT",
        account_name="Chart of Accounts",
        account_type=AccountType.ASSET,
        normal_balance=None,
        current_balance=None,
        level=0,
        is_header=True,
        is_active=True,
        children=[
            ChartOfAccountsTree(
                id=acc.id,
                account_code=acc.account_code,
                account_name=acc.account_name,
                account_type=acc.account_type,
                account_sub_type=acc.account_sub_type,
                normal_balance=acc.normal_balance,
                current_balance=acc.current_balance,
                level=acc.level,
                is_header=acc.is_header,
                is_active=acc.is_active,
                children=build_children(acc),
            )
            for acc in sorted(root_accounts, key=lambda x: x.account_code)
        ],
    )
    
    return tree


@router.post("/chart-of-accounts", response_model=ChartOfAccountsResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    data: ChartOfAccountsCreate = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new account in the chart of accounts."""
    service = AccountingService(db)
    try:
        account = await service.create_account(
            entity_id=entity_id,
            data=data,
            user_id=current_user.id,
        )
        
        # Audit log for account creation
        audit_service = AuditService(db)
        await audit_service.log_action(
            business_entity_id=entity_id,
            entity_type="chart_of_accounts",
            entity_id=str(account.id),
            action=AuditAction.CREATE,
            user_id=current_user.id,
            new_values={
                "account_code": data.account_code,
                "account_name": data.account_name,
                "account_type": data.account_type.value if hasattr(data.account_type, 'value') else str(data.account_type),
            },
        )
        
        await db.commit()
        return account
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/chart-of-accounts/{account_id}", response_model=ChartOfAccountsResponse)
async def get_account(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    account_id: uuid.UUID = Path(..., description="Account ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get account by ID."""
    service = AccountingService(db)
    account = await service.get_account_by_id(account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


@router.put("/chart-of-accounts/{account_id}", response_model=ChartOfAccountsResponse)
async def update_account(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    account_id: uuid.UUID = Path(..., description="Account ID"),
    data: ChartOfAccountsUpdate = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an account."""
    service = AccountingService(db)
    try:
        account = await service.update_account(
            account_id=account_id,
            data=data,
            user_id=current_user.id,
        )
        await db.commit()
        return account
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/chart-of-accounts/initialize", response_model=List[ChartOfAccountsResponse])
async def initialize_chart_of_accounts(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Initialize default Nigerian Chart of Accounts for the entity."""
    service = AccountingService(db)
    
    # Check if accounts already exist
    existing = await service.get_chart_of_accounts(entity_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chart of Accounts already exists. Cannot reinitialize.",
        )
    
    accounts = await service.create_default_chart_of_accounts(
        entity_id=entity_id,
        user_id=current_user.id,
    )
    await db.commit()
    return accounts


# ============================================================================
# FISCAL YEAR & PERIOD ENDPOINTS
# ============================================================================

@router.get("/fiscal-years", response_model=List[FiscalYearResponse])
async def list_fiscal_years(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all fiscal years for entity."""
    service = AccountingService(db)
    return await service.get_fiscal_years(entity_id)


@router.post("/fiscal-years", response_model=FiscalYearResponse, status_code=status.HTTP_201_CREATED)
async def create_fiscal_year(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    data: FiscalYearCreate = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new fiscal year with monthly periods."""
    service = AccountingService(db)
    try:
        fiscal_year = await service.create_fiscal_year(
            entity_id=entity_id,
            data=data,
            user_id=current_user.id,
        )
        await db.commit()
        return fiscal_year
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/fiscal-years/current", response_model=FiscalYearResponse)
async def get_current_fiscal_year(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current fiscal year for entity."""
    service = AccountingService(db)
    fiscal_year = await service.get_current_fiscal_year(entity_id)
    if not fiscal_year:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No current fiscal year found. Please create a fiscal year first.",
        )
    return fiscal_year


@router.get("/fiscal-periods/for-date", response_model=FiscalPeriodResponse)
async def get_period_for_date(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    entry_date: date = Query(..., description="Date to find period for"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get fiscal period for a specific date."""
    service = AccountingService(db)
    period = await service.get_fiscal_period_for_date(entity_id, entry_date)
    if not period:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No fiscal period found for date {entry_date}",
        )
    return period


# ============================================================================
# JOURNAL ENTRY ENDPOINTS
# ============================================================================

@router.get("/journal-entries", response_model=JournalEntryListResponse)
async def list_journal_entries(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    start_date: Optional[date] = Query(None, description="Filter from date"),
    end_date: Optional[date] = Query(None, description="Filter to date"),
    status: Optional[JournalEntryStatus] = Query(None, description="Filter by status"),
    entry_type: Optional[JournalEntryType] = Query(None, description="Filter by type"),
    limit: int = Query(100, ge=1, le=500, description="Limit results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get journal entries with filtering and pagination."""
    service = AccountingService(db)
    entries, total = await service.get_journal_entries(
        entity_id=entity_id,
        start_date=start_date,
        end_date=end_date,
        status=status,
        entry_type=entry_type,
        limit=limit,
        offset=offset,
    )
    # Calculate pagination values
    page = (offset // limit) + 1 if limit > 0 else 1
    total_pages = (total + limit - 1) // limit if limit > 0 else 1
    
    return JournalEntryListResponse(
        items=entries,
        total=total,
        page=page,
        page_size=limit,
        total_pages=total_pages,
    )


@router.post("/journal-entries", response_model=JournalEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_journal_entry(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    data: JournalEntryCreate = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _limit_check: User = Depends(require_within_usage_limit(UsageMetricType.TRANSACTIONS)),
):
    """Create a new journal entry."""
    service = AccountingService(db)
    try:
        entry = await service.create_journal_entry(
            entity_id=entity_id,
            data=data,
            user_id=current_user.id,
        )
        
        # Audit log for journal entry creation
        audit_service = AuditService(db)
        await audit_service.log_action(
            business_entity_id=entity_id,
            entity_type="journal_entry",
            entity_id=str(entry.id),
            action=AuditAction.CREATE,
            user_id=current_user.id,
            new_values={
                "entry_number": entry.entry_number,
                "description": data.description,
                "total_amount": float(entry.total_debit) if hasattr(entry, 'total_debit') else 0,
                "entry_type": data.entry_type.value if hasattr(data.entry_type, 'value') else str(data.entry_type),
            },
        )
        
        # Record usage metering for SKU tier limits
        # Journal entries count as transactions
        if current_user.organization_id:
            metering_service = MeteringService(db)
            await metering_service.record_transaction(
                organization_id=current_user.organization_id,
                entity_id=entity_id,
                user_id=current_user.id,
                transaction_id=str(entry.id),
            )
        
        await db.commit()
        return entry
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/journal-entries/{entry_id}", response_model=JournalEntryResponse)
async def get_journal_entry(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    entry_id: uuid.UUID = Path(..., description="Journal Entry ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get journal entry by ID."""
    service = AccountingService(db)
    entry = await service.get_journal_entry_by_id(entry_id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Journal entry not found")
    return entry


@router.post("/journal-entries/{entry_id}/post", response_model=JournalEntryResponse)
async def post_journal_entry(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    entry_id: uuid.UUID = Path(..., description="Journal Entry ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Post a draft journal entry to the GL."""
    service = AccountingService(db)
    try:
        entry = await service.post_journal_entry(
            entry_id=entry_id,
            user_id=current_user.id,
        )
        
        # Audit log for journal entry posting
        audit_service = AuditService(db)
        await audit_service.log_action(
            business_entity_id=entity_id,
            entity_type="journal_entry",
            entity_id=str(entry.id),
            action=AuditAction.UPDATE,
            user_id=current_user.id,
            new_values={
                "status": "POSTED",
                "posted_at": entry.posted_at.isoformat() if entry.posted_at else None,
            },
        )
        
        await db.commit()
        return entry
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/journal-entries/{entry_id}/reverse", response_model=JournalEntryResponse)
async def reverse_journal_entry(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    entry_id: uuid.UUID = Path(..., description="Journal Entry ID"),
    reversal_date: date = Query(..., description="Date for reversal entry"),
    reason: str = Query(..., min_length=5, description="Reason for reversal"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reverse a posted journal entry."""
    service = AccountingService(db)
    try:
        entry = await service.reverse_journal_entry(
            entry_id=entry_id,
            reversal_date=reversal_date,
            reason=reason,
            user_id=current_user.id,
        )
        await db.commit()
        return entry
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ============================================================================
# GL INTEGRATION ENDPOINT (FOR OTHER MODULES)
# ============================================================================

@router.post("/gl/post", response_model=GLPostingResponse)
async def post_to_general_ledger(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    request: GLPostingRequest = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Post a document from another module to the General Ledger.
    This is the main integration point for all financial modules.
    
    Used by:
    - Sales/Invoices module
    - Purchases/Vendors module
    - Receipts module
    - Payments module
    - Payroll module
    - Fixed Assets module
    - Inventory module
    - Bank Reconciliation module
    """
    service = AccountingService(db)
    response = await service.post_to_gl(
        entity_id=entity_id,
        request=request,
        user_id=current_user.id,
    )
    
    if response.success:
        await db.commit()
    else:
        await db.rollback()
    
    return response


# ============================================================================
# FINANCIAL REPORTS ENDPOINTS
# ============================================================================

@router.get("/reports/trial-balance", response_model=TrialBalanceReport)
async def get_trial_balance(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    as_of_date: date = Query(..., description="Report date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate Trial Balance report."""
    service = AccountingService(db)
    return await service.get_trial_balance(entity_id, as_of_date)


@router.get("/reports/income-statement", response_model=IncomeStatementReport)
async def get_income_statement(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    start_date: date = Query(..., description="Period start date"),
    end_date: date = Query(..., description="Period end date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate Income Statement (P&L) report."""
    service = AccountingService(db)
    return await service.get_income_statement(entity_id, start_date, end_date)


@router.get("/reports/balance-sheet", response_model=BalanceSheetReport)
async def get_balance_sheet(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    as_of_date: date = Query(..., description="Report date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate Balance Sheet report."""
    service = AccountingService(db)
    return await service.get_balance_sheet(entity_id, as_of_date)


@router.get("/reports/cash-flow-statement", response_model=CashFlowStatementReport)
async def get_cash_flow_statement(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    start_date: date = Query(..., description="Start date of reporting period"),
    end_date: date = Query(..., description="End date of reporting period"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate Cash Flow Statement report using indirect method.
    
    This report shows:
    - Operating Activities: Net income adjusted for non-cash items and working capital changes
    - Investing Activities: Asset purchases, disposals, and investments
    - Financing Activities: Debt, equity, and dividend transactions
    """
    service = AccountingService(db)
    return await service.get_cash_flow_statement(entity_id, start_date, end_date)


# ============================================================================
# PERIOD CLOSE ENDPOINTS
# ============================================================================

@router.get("/periods/{period_id}/close-checklist", response_model=PeriodCloseChecklist)
async def get_period_close_checklist(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    period_id: uuid.UUID = Path(..., description="Fiscal Period ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get checklist for closing a fiscal period."""
    service = AccountingService(db)
    try:
        return await service.get_period_close_checklist(entity_id, period_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/periods/close", response_model=PeriodCloseResponse)
async def close_fiscal_period(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    request: PeriodCloseRequest = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Close a fiscal period."""
    service = AccountingService(db)
    response = await service.close_period(
        entity_id=entity_id,
        request=request,
        user_id=current_user.id,
    )
    
    if response.success:
        await db.commit()
    else:
        await db.rollback()
    
    return response


# ============================================================================
# FIXED ASSET INTEGRATION ENDPOINTS
# ============================================================================

@router.get("/fixed-assets/summary", response_model=FixedAssetRegisterSummary)
async def get_fixed_asset_summary(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    as_of_date: date = Query(..., description="Report date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get fixed asset summary for Balance Sheet reporting.
    
    Returns detailed breakdown of all fixed assets including:
    - Total acquisition cost
    - Accumulated depreciation
    - Net book value
    - Breakdown by category
    - Individual asset details
    
    This data is pulled directly from the Fixed Asset Register
    to ensure consistency with financial statements.
    """
    service = AccountingService(db)
    return await service.get_fixed_asset_summary(entity_id, as_of_date)


@router.get("/fixed-assets/validate", response_model=GLFixedAssetValidation)
async def validate_fixed_asset_gl_balances(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    as_of_date: date = Query(..., description="Validation date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Validate GL balances against Fixed Asset Register totals.
    
    Compares:
    - GL Fixed Asset accounts vs Register total cost
    - GL Accumulated Depreciation vs Register depreciation
    - Net book values
    
    Returns:
    - Validation status (pass/fail)
    - Variance amounts
    - Issues identified
    - Recommendations for resolution
    
    Use this endpoint before period close to ensure fixed asset
    balances are accurate and reconciled.
    """
    service = AccountingService(db)
    return await service.validate_fixed_asset_gl_balances(entity_id, as_of_date)


@router.get("/reports/balance-sheet-enhanced", response_model=EnhancedBalanceSheetReport)
async def get_enhanced_balance_sheet(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    as_of_date: date = Query(..., description="Report date"),
    include_fixed_asset_details: bool = Query(True, description="Include detailed fixed asset breakdown"),
    validate_fixed_assets: bool = Query(True, description="Validate GL vs Fixed Asset Register"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate enhanced Balance Sheet with fixed asset details.
    
    This comprehensive report includes:
    - Standard Balance Sheet format (Assets, Liabilities, Equity)
    - Fixed Asset Register summary by category
    - GL vs Register validation results
    - Depreciation policy notes
    - 2026 Tax compliance notes (capital gains, VAT recovery)
    
    The enhanced balance sheet ensures that fixed asset values
    shown in the Balance Sheet can be traced back to the
    Fixed Asset Register, providing audit assurance.
    """
    service = AccountingService(db)
    return await service.get_enhanced_balance_sheet(
        entity_id=entity_id,
        as_of_date=as_of_date,
        include_fixed_asset_details=include_fixed_asset_details,
        validate_fixed_assets=validate_fixed_assets,
    )


# ============================================================================
# SOURCE SYSTEM INTEGRATION ENDPOINTS - ACCOUNTING READS FROM OTHER MODULES
# ============================================================================

@router.get("/source-systems/inventory")
async def get_inventory_summary_for_gl(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    as_of_date: date = Query(..., description="Report date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get inventory summary for GL account 1140 reconciliation.
    
    Reads from: Inventory system
    Maps to: GL 1140 - Inventory
    
    Returns:
    - Total inventory value (should match GL 1140)
    - Item counts (total, active, low stock)
    - Breakdown by category
    - Valuation method
    """
    service = AccountingService(db)
    return await service.get_inventory_summary_for_gl(entity_id, as_of_date)


@router.get("/source-systems/accounts-receivable")
async def get_ar_aging_summary(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    as_of_date: date = Query(..., description="Report date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get Accounts Receivable aging for GL account 1130 reconciliation.
    
    Reads from: Invoice/Customer system
    Maps to: GL 1130 - Accounts Receivable
    
    Returns:
    - Total receivables (should match GL 1130)
    - Aging buckets (Current, 31-60, 61-90, 90+ days)
    - Customer counts
    - Top 10 customers by balance
    """
    service = AccountingService(db)
    return await service.get_ar_aging_summary(entity_id, as_of_date)


@router.get("/source-systems/accounts-payable")
async def get_ap_aging_summary(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    as_of_date: date = Query(..., description="Report date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get Accounts Payable aging for GL account 2110 reconciliation.
    
    Reads from: Vendor/Transaction system
    Maps to: GL 2110 - Accounts Payable
    
    Returns:
    - Total payables (should match GL 2110)
    - Aging buckets (Current, 31-60, 61-90, 90+ days)
    - Vendor counts
    - Top 10 vendors by balance
    """
    service = AccountingService(db)
    return await service.get_ap_aging_summary(entity_id, as_of_date)


@router.get("/source-systems/payroll")
async def get_payroll_summary_for_gl(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    period_start: date = Query(..., description="Period start date"),
    period_end: date = Query(..., description="Period end date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get payroll summary for GL reconciliation.
    
    Reads from: Payroll system
    Maps to: 
    - GL 5200 - Salaries & Wages (gross)
    - GL 5210 - Employer Pension
    - GL 5220 - Employer NSITF
    - GL 2150 - PAYE Payable
    - GL 2160 - Pension Payable
    - GL 2170 - NHF Payable
    - GL 2190 - Salaries Payable (net)
    
    Returns:
    - Expense totals (gross salary, employer contributions)
    - Liability totals (PAYE, pension, NHF, net payable)
    - Employee count
    - Payroll run count
    """
    service = AccountingService(db)
    return await service.get_payroll_summary_for_gl(entity_id, period_start, period_end)


@router.get("/source-systems/bank")
async def get_bank_summary_for_gl(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    as_of_date: date = Query(..., description="Report date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get bank account summary for GL account 1120 reconciliation.
    
    Reads from: Bank Reconciliation system
    Maps to: GL 1120 - Bank Accounts
    
    Returns:
    - Total bank balance (should match GL 1120)
    - Individual account balances
    - Last reconciliation date
    - Outstanding items (deposits, checks)
    """
    service = AccountingService(db)
    return await service.get_bank_summary_for_gl(entity_id, as_of_date)


@router.get("/source-systems/expense-claims")
async def get_expense_claims_summary_for_gl(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    as_of_date: date = Query(..., description="Report date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get expense claims summary for GL reconciliation.
    
    Reads from: Expense Claims system
    
    Returns:
    - Pending claims total
    - Approved claims total
    - Paid claims total
    - Claims by category
    """
    service = AccountingService(db)
    return await service.get_expense_claims_summary_for_gl(entity_id, as_of_date)


@router.get("/source-systems/summary")
async def get_gl_source_system_summary(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    as_of_date: date = Query(..., description="Report date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get comprehensive GL summary with ALL source system data.
    
    This is the MASTER endpoint for reconciling GL accounts with source systems.
    It pulls data from:
    - Inventory (GL 1140)
    - Accounts Receivable (GL 1130)
    - Accounts Payable (GL 2110)
    - Payroll (GL 2150-2190, 5200-5230)
    - Bank Accounts (GL 1120)
    - Fixed Assets (GL 1210, 1220)
    - Expense Claims
    
    Returns:
    - All source system summaries
    - GL validation results for each account
    - Discrepancy count and details
    - Overall reconciliation status
    
    Use this endpoint for:
    - Month-end close preparation
    - Audit preparation
    - Financial statement preparation
    - Identifying data integrity issues
    """
    service = AccountingService(db)
    return await service.get_gl_source_system_summary(entity_id, as_of_date)


@router.post("/sync-from-source-systems")
async def sync_gl_from_source_systems(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    as_of_date: Optional[date] = Query(None, description="Sync as of date (defaults to today)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    SYNC GL balances from all source systems.
    
    This endpoint reads data from all source systems and updates
    the Chart of Accounts current_balance fields directly.
    
    Source Systems synced:
    - Inventory → GL 1140
    - Invoices/AR → GL 1130, 4100, 2130
    - Transactions/AP → GL 2110, 1160
    - Fixed Assets → GL 1210, 1220
    - Payroll → GL 5200, 5210, 5220, 2150, 2160, 2170, 2180, 2190
    - Bank Accounts → GL 1120
    - Stock Movements → GL 5100 (COGS)
    
    Returns:
    - List of accounts updated with old/new balances
    - Summary of synced totals
    - Any errors encountered
    
    Use this endpoint:
    - During initial setup
    - To reconcile GL after data import
    - When GL balances are out of sync with source systems
    
    WARNING: This overwrites current GL balances with source system values.
    """
    service = AccountingService(db)
    return await service.sync_gl_from_source_systems(entity_id, current_user.id, as_of_date)


@router.post("/recalculate-balances")
async def recalculate_gl_balances(
    entity_id: uuid.UUID = Path(..., description="Entity ID"),
    _entity_access: BusinessEntity = Depends(require_entity_access),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Recalculate all GL account balances from posted journal entries.
    
    This endpoint recalculates current_balance, ytd_debit, and ytd_credit
    for all accounts based on the sum of posted journal entry lines.
    
    Use this endpoint:
    - When balances are out of sync with journal entries
    - After manual database corrections
    - As part of period close verification
    
    Returns:
    - List of accounts with old and new balances
    - Total debits and credits per account
    """
    service = AccountingService(db)
    return await service.recalculate_gl_balances_from_journal_entries(entity_id)
