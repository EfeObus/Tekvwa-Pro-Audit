"""
Tekvwa Pro Audit - Bank Reconciliation API Router

Comprehensive API endpoints for Nigerian bank reconciliation operations.
Supports:
- Bank account management with API integrations (Mono, Okra, Stitch)
- Statement import (CSV, API sync)
- Transaction matching (auto, manual, rule-based)
- Nigerian charge detection and management
- Reconciliation workflow (draft → review → approve/reject)
- Adjustment management
- Reporting
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any
from io import StringIO
import csv

from fastapi import APIRouter, Depends, HTTPException, status, Query, Body, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, get_current_entity_id, require_feature, record_usage_event
from app.models.entity import BusinessEntity
from app.models.sku import Feature, UsageMetricType
from app.models.user import User
from app.models.bank_reconciliation import (
    BankAccountType, BankAccountCurrency, BankStatementSource,
    ReconciliationStatus, MatchStatus, MatchType, AdjustmentType,
    UnmatchedItemType,
)
from app.services.bank_reconciliation_service import (
    BankReconciliationService, get_bank_reconciliation_service,
)
from app.services.bank_integration_service import BankIntegrationService
from app.services.matching_engine import MatchingConfig
from app.services.audit_service import AuditService
from app.models.audit_consolidated import AuditAction
from app.schemas.bank_reconciliation import (
    BankAccountCreate, BankAccountUpdate, BankAccountResponse,
    BankStatementTransactionResponse, BankStatementImportCreate,
    BankReconciliationCreate, BankReconciliationUpdate, BankReconciliationResponse,
    BankReconciliationDetailResponse,
    ReconciliationAdjustmentCreate, ReconciliationAdjustmentResponse,
    UnmatchedItemCreate, UnmatchedItemUpdate, UnmatchedItemResponse,
    ManualMatchRequest, AutoMatchConfig, AutoMatchResult,
    BankChargeRuleCreate, BankChargeRuleUpdate, BankChargeRuleResponse,
    MatchingRuleCreate, MatchingRuleUpdate, MatchingRuleResponse,
    MonoConnectRequest, OkraConnectRequest, BankSyncRequest, BankSyncResponse,
    ReconciliationSummaryReport,
)

# Feature gate for bank reconciliation - requires Professional tier or higher
bank_recon_feature_gate = require_feature([Feature.BANK_RECONCILIATION])

router = APIRouter(
    prefix="/bank-reconciliation",
    tags=["Bank Reconciliation"],
    dependencies=[Depends(bank_recon_feature_gate)],
)


# Helper to get entity
async def get_entity(entity_id: uuid.UUID, db: AsyncSession) -> BusinessEntity:
    """Get entity from ID."""
    from sqlalchemy import select
    result = await db.execute(
        select(BusinessEntity).where(BusinessEntity.id == entity_id)
    )
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


# =============================================================================
# BANK ACCOUNT ENDPOINTS
# =============================================================================

@router.get("/accounts", response_model=List[BankAccountResponse])
async def list_bank_accounts(
    is_active: Optional[bool] = Query(True, description="Filter by active status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get all bank accounts for the current entity."""
    service = get_bank_reconciliation_service(db)
    accounts = await service.get_bank_accounts(
        entity_id=entity_id,
        is_active=is_active,
    )
    return accounts


@router.post("/accounts", response_model=BankAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_bank_account(
    account_data: BankAccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Create a new bank account for reconciliation."""
    service = get_bank_reconciliation_service(db)
    
    account = await service.create_bank_account(
        entity_id=entity_id,
        bank_name=account_data.bank_name,
        account_name=account_data.account_name,
        account_number=account_data.account_number,
        account_type=account_data.account_type,
        currency=account_data.currency,
        opening_balance=account_data.opening_balance,
        opening_balance_date=account_data.opening_balance_date,
        gl_account_code=account_data.gl_account_code,
        bank_code=account_data.bank_code,
        sort_code=account_data.sort_code,
        notes=account_data.notes,
        created_by_id=current_user.id,
        mono_account_id=account_data.mono_account_id,
        okra_account_id=account_data.okra_account_id,
        stitch_account_id=account_data.stitch_account_id,
    )
    
    # Audit logging
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="bank_account",
        entity_id=str(account.id),
        action=AuditAction.CREATE,
        user_id=current_user.id,
        new_values={
            "bank_name": account_data.bank_name,
            "account_name": account_data.account_name,
            "account_number": account_data.account_number[-4:] if account_data.account_number else None,  # Last 4 digits only
        }
    )
    
    # Record usage metering for transaction tracking
    if current_user.organization_id:
        await record_usage_event(
            db=db,
            organization_id=current_user.organization_id,
            metric_type=UsageMetricType.TRANSACTIONS,
            entity_id=entity_id,
            user_id=current_user.id,
            resource_type="bank_account",
            resource_id=str(account.id),
        )
    
    return account


@router.get("/accounts/{account_id}", response_model=BankAccountResponse)
async def get_bank_account(
    account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get a specific bank account by ID."""
    service = get_bank_reconciliation_service(db)
    account = await service.get_bank_account(
        account_id=account_id,
        entity_id=entity_id,
    )
    if not account:
        raise HTTPException(status_code=404, detail="Bank account not found")
    return account


@router.patch("/accounts/{account_id}", response_model=BankAccountResponse)
async def update_bank_account(
    account_id: uuid.UUID,
    updates: BankAccountUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Update a bank account."""
    service = get_bank_reconciliation_service(db)
    
    # Verify account belongs to entity
    account = await service.get_bank_account(account_id, entity_id)
    if not account:
        raise HTTPException(status_code=404, detail="Bank account not found")
    
    update_dict = updates.model_dump(exclude_unset=True)
    updated = await service.update_bank_account(account_id, **update_dict)
    return updated


# =============================================================================
# GL LINKAGE ENDPOINTS
# =============================================================================

@router.get("/accounts/{account_id}/gl-linkage")
async def validate_bank_gl_linkage(
    account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Validate the GL linkage for a specific bank account.
    
    Returns validation details including whether the bank account
    is properly linked to a valid GL account.
    """
    service = get_bank_reconciliation_service(db)
    return await service.validate_gl_linkage(account_id, entity_id)


@router.get("/gl-linkage/validate-all")
async def validate_all_gl_linkages(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Validate GL linkage for all bank accounts of the entity.
    
    Returns a summary of validation results including:
    - Total accounts
    - Linked accounts (valid)
    - Unlinked accounts (need GL code)
    - Invalid linkages (GL code doesn't exist)
    - List of issues with recommendations
    """
    service = get_bank_reconciliation_service(db)
    return await service.validate_all_bank_gl_linkages(entity_id)


@router.post("/accounts/{account_id}/link-gl")
async def link_bank_to_gl_account(
    account_id: uuid.UUID,
    gl_account_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Link a bank account to a GL account.
    
    The GL account must exist in the Chart of Accounts.
    This enables proper accounting integration for bank reconciliation.
    """
    service = get_bank_reconciliation_service(db)
    result = await service.link_bank_to_gl(account_id, gl_account_code, entity_id)
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    
    return result


# =============================================================================
# BANK INTEGRATION ENDPOINTS (Mono, Okra, Stitch)
# =============================================================================

@router.post("/accounts/{account_id}/connect/mono")
async def connect_mono_account(
    account_id: uuid.UUID,
    connect_data: MonoConnectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Connect a Mono account using the authorization code.
    
    Flow:
    1. Frontend uses Mono Connect widget to get auth code
    2. Pass auth code here to exchange for account ID
    3. Account is linked for automatic statement fetching
    """
    service = get_bank_reconciliation_service(db)
    
    # Verify account belongs to entity
    account = await service.get_bank_account(account_id, entity_id)
    if not account:
        raise HTTPException(status_code=404, detail="Bank account not found")
    
    try:
        integration = BankIntegrationService(db)
        mono_account = await integration.mono_exchange_token(connect_data.code)
        
        # Update bank account with Mono ID
        await service.update_bank_account(
            account_id,
            mono_account_id=mono_account["id"],
            mono_connected_at=datetime.utcnow(),
        )
        
        return {
            "success": True,
            "message": "Mono account connected successfully",
            "mono_account_id": mono_account["id"],
        }
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to connect Mono account: {str(e)}"
        )


@router.post("/accounts/{account_id}/connect/okra")
async def connect_okra_account(
    account_id: uuid.UUID,
    connect_data: OkraConnectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Connect an Okra account using the record ID from Okra widget.
    """
    service = get_bank_reconciliation_service(db)
    
    account = await service.get_bank_account(account_id, entity_id)
    if not account:
        raise HTTPException(status_code=404, detail="Bank account not found")
    
    try:
        await service.update_bank_account(
            account_id,
            okra_account_id=connect_data.record_id,
            okra_connected_at=datetime.utcnow(),
        )
        
        return {
            "success": True,
            "message": "Okra account connected successfully",
            "okra_account_id": connect_data.record_id,
        }
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to connect Okra account: {str(e)}"
        )


@router.post("/accounts/{account_id}/sync", response_model=BankSyncResponse)
async def sync_bank_transactions(
    account_id: uuid.UUID,
    sync_request: BankSyncRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Sync transactions from connected bank API (Mono/Okra).
    
    Fetches new transactions and imports them with Nigerian charge detection.
    """
    service = get_bank_reconciliation_service(db)
    
    account = await service.get_bank_account(account_id, entity_id)
    if not account:
        raise HTTPException(status_code=404, detail="Bank account not found")
    
    # Determine which API to use
    integration = BankIntegrationService(db)
    
    try:
        if account.mono_account_id:
            result = await integration.mono_sync_bank_account(
                account_id=account_id,
                mono_account_id=account.mono_account_id,
                start_date=sync_request.start_date,
                end_date=sync_request.end_date,
                reconciliation_id=sync_request.reconciliation_id,
            )
        elif account.okra_account_id:
            result = await integration.okra_sync_bank_account(
                account_id=account_id,
                okra_account_id=account.okra_account_id,
                start_date=sync_request.start_date,
                end_date=sync_request.end_date,
                reconciliation_id=sync_request.reconciliation_id,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="No bank API connected. Please connect Mono or Okra first."
            )
        
        return BankSyncResponse(
            success=True,
            imported_count=result.get("imported", 0),
            duplicate_count=result.get("duplicates_skipped", 0),
            charges_detected=result.get("charges_detected", 0),
            message="Sync completed successfully",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Sync failed: {str(e)}")


# =============================================================================
# STATEMENT IMPORT ENDPOINTS
# =============================================================================

@router.post("/accounts/{account_id}/import/csv")
async def import_csv_statement(
    account_id: uuid.UUID,
    file: UploadFile = File(...),
    reconciliation_id: Optional[uuid.UUID] = Query(None),
    date_column: str = Query("Date", description="CSV column name for date"),
    description_column: str = Query("Description", description="CSV column name for description"),
    debit_column: str = Query("Debit", description="CSV column name for debit amount"),
    credit_column: str = Query("Credit", description="CSV column name for credit amount"),
    balance_column: Optional[str] = Query(None, description="CSV column name for balance"),
    reference_column: Optional[str] = Query(None, description="CSV column name for reference"),
    date_format: str = Query("%Y-%m-%d", description="Date format string"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Import bank statement from CSV file.
    
    Supports various Nigerian bank statement formats with configurable column mapping.
    Auto-detects Nigerian bank charges (EMTL, Stamp Duty, VAT, etc.).
    """
    service = get_bank_reconciliation_service(db)
    
    account = await service.get_bank_account(account_id, entity_id)
    if not account:
        raise HTTPException(status_code=404, detail="Bank account not found")
    
    # Read CSV file
    try:
        content = await file.read()
        content_str = content.decode("utf-8-sig")  # Handle BOM
        
        integration = BankIntegrationService(db)
        
        # Create import record
        import_record = await service.create_statement_import(
            bank_account_id=account_id,
            source=BankStatementSource.CSV_IMPORT,
            period_start=date.today(),  # Will be updated after parsing
            period_end=date.today(),
            imported_by_id=current_user.id,
            file_name=file.filename,
            file_size=len(content),
        )
        
        # Parse and import
        column_mapping = {
            "date": date_column,
            "description": description_column,
            "debit": debit_column,
            "credit": credit_column,
            "balance": balance_column,
            "reference": reference_column,
        }
        
        transactions = integration.import_csv_statement(
            csv_content=content_str,
            column_mapping=column_mapping,
            date_format=date_format,
        )
        
        # Import transactions
        result = await service.import_statement_transactions(
            bank_account_id=account_id,
            reconciliation_id=reconciliation_id,
            transactions=transactions,
            source=BankStatementSource.CSV_IMPORT,
            import_id=import_record.id,
            auto_detect_charges=True,
        )
        
        return {
            "success": True,
            "import_id": str(import_record.id),
            "file_name": file.filename,
            **result,
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV import failed: {str(e)}")


@router.post("/accounts/{account_id}/transactions/manual")
async def add_manual_transaction(
    account_id: uuid.UUID,
    transaction_date: date = Body(...),
    description: str = Body(...),
    debit_amount: Decimal = Body(Decimal("0")),
    credit_amount: Decimal = Body(Decimal("0")),
    reference: Optional[str] = Body(None),
    reconciliation_id: Optional[uuid.UUID] = Body(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Add a manual bank transaction entry."""
    service = get_bank_reconciliation_service(db)
    
    account = await service.get_bank_account(account_id, entity_id)
    if not account:
        raise HTTPException(status_code=404, detail="Bank account not found")
    
    result = await service.import_statement_transactions(
        bank_account_id=account_id,
        reconciliation_id=reconciliation_id,
        transactions=[{
            "transaction_date": transaction_date,
            "description": description,
            "debit_amount": debit_amount,
            "credit_amount": credit_amount,
            "reference": reference,
        }],
        source=BankStatementSource.MANUAL_ENTRY,
        auto_detect_charges=True,
    )
    
    return {"success": True, **result}


# =============================================================================
# RECONCILIATION ENDPOINTS
# =============================================================================

@router.get("/reconciliations", response_model=List[BankReconciliationResponse])
async def list_reconciliations(
    account_id: Optional[uuid.UUID] = Query(None, description="Filter by bank account"),
    status_filter: Optional[ReconciliationStatus] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get reconciliations with optional filtering."""
    service = get_bank_reconciliation_service(db)
    
    reconciliations = await service.get_reconciliations(
        bank_account_id=account_id,
        entity_id=entity_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return reconciliations


@router.post("/reconciliations", response_model=BankReconciliationResponse, status_code=status.HTTP_201_CREATED)
async def create_reconciliation(
    recon_data: BankReconciliationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Create a new bank reconciliation."""
    service = get_bank_reconciliation_service(db)
    
    # Verify bank account belongs to entity
    account = await service.get_bank_account(recon_data.bank_account_id, entity_id)
    if not account:
        raise HTTPException(status_code=404, detail="Bank account not found")
    
    reconciliation = await service.create_reconciliation(
        bank_account_id=recon_data.bank_account_id,
        reconciliation_date=recon_data.reconciliation_date,
        period_start=recon_data.period_start,
        period_end=recon_data.period_end,
        statement_opening_balance=recon_data.statement_opening_balance,
        statement_closing_balance=recon_data.statement_closing_balance,
        book_opening_balance=recon_data.book_opening_balance,
        book_closing_balance=recon_data.book_closing_balance,
        reference=recon_data.reference,
        created_by_id=current_user.id,
    )
    
    # Audit logging
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="bank_reconciliation",
        entity_id=str(reconciliation.id),
        action=AuditAction.CREATE,
        user_id=current_user.id,
        new_values={
            "reconciliation_date": str(recon_data.reconciliation_date),
            "period": f"{recon_data.period_start} to {recon_data.period_end}",
            "bank_account_id": str(recon_data.bank_account_id),
        }
    )
    
    return reconciliation


@router.get("/reconciliations/{reconciliation_id}", response_model=BankReconciliationDetailResponse)
async def get_reconciliation(
    reconciliation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific reconciliation with full details."""
    service = get_bank_reconciliation_service(db)
    
    reconciliation = await service.get_reconciliation(reconciliation_id)
    if not reconciliation:
        raise HTTPException(status_code=404, detail="Reconciliation not found")
    
    # Get related data
    adjustments = await service.get_adjustments(reconciliation_id)
    transactions = await service.get_statement_transactions(
        reconciliation_id=reconciliation_id,
        limit=100,
    )
    unmatched = await service.get_unmatched_items(reconciliation_id)
    
    return BankReconciliationDetailResponse(
        **reconciliation.__dict__,
        adjustments=adjustments,
        transactions=transactions,
        unmatched_items=unmatched,
    )


# =============================================================================
# MATCHING ENDPOINTS
# =============================================================================

@router.post("/reconciliations/{reconciliation_id}/auto-match", response_model=AutoMatchResult)
async def auto_match_transactions(
    reconciliation_id: uuid.UUID,
    config: Optional[AutoMatchConfig] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Run auto-matching on unmatched transactions.
    
    Uses intelligent matching algorithms:
    - Exact matching (amount + date)
    - Fuzzy matching (configurable tolerance)
    - Rule-based matching (user-defined rules)
    - One-to-many matching
    - Many-to-one matching
    """
    service = get_bank_reconciliation_service(db)
    
    reconciliation = await service.get_reconciliation(reconciliation_id)
    if not reconciliation:
        raise HTTPException(status_code=404, detail="Reconciliation not found")
    
    # Get entity ID from bank account
    account = await service.get_bank_account(reconciliation.bank_account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Bank account not found")
    
    # Build matching config
    matching_config = None
    if config:
        matching_config = MatchingConfig(
            date_tolerance_days=config.date_tolerance_days or 3,
            amount_tolerance_percent=config.amount_tolerance_percent or Decimal("0.01"),
            min_confidence=config.min_confidence or 70.0,
            enable_fuzzy=config.enable_fuzzy if config.enable_fuzzy is not None else True,
            enable_one_to_many=config.enable_one_to_many if config.enable_one_to_many is not None else True,
            enable_many_to_one=config.enable_many_to_one if config.enable_many_to_one is not None else True,
        )
    
    result = await service.auto_match_transactions(
        reconciliation_id=reconciliation_id,
        entity_id=account.entity_id,
        config=matching_config,
    )
    
    # Audit logging
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=account.entity_id,
        entity_type="bank_reconciliation",
        entity_id=str(reconciliation_id),
        action=AuditAction.UPDATE,
        user_id=current_user.id,
        new_values={
            "action": "auto_match",
            "matches_found": result.get("matched_count", 0),
            "total_processed": result.get("total_processed", 0),
        }
    )
    
    return AutoMatchResult(**result)


@router.get("/reconciliations/{reconciliation_id}/gl-transactions")
async def get_gl_transactions_for_reconciliation(
    reconciliation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Get GL journal entry lines for the bank account in this reconciliation.
    
    Returns GL transactions that affect the linked bank GL account,
    suitable for matching against bank statement transactions.
    """
    service = get_bank_reconciliation_service(db)
    
    reconciliation = await service.get_reconciliation(reconciliation_id, entity_id)
    if not reconciliation:
        raise HTTPException(status_code=404, detail="Reconciliation not found")
    
    # Validate GL linkage
    linkage = await service.validate_gl_linkage(reconciliation.bank_account_id, entity_id)
    if not linkage.get("valid"):
        raise HTTPException(
            status_code=400, 
            detail=f"Bank account not linked to GL: {linkage.get('error')}"
        )
    
    gl_transactions = await service.get_gl_transactions_for_bank(
        entity_id=entity_id,
        bank_account_id=reconciliation.bank_account_id,
        start_date=reconciliation.period_start,
        end_date=reconciliation.period_end,
    )
    
    return {
        "reconciliation_id": str(reconciliation_id),
        "gl_account_code": linkage.get("gl_account_code"),
        "gl_account_name": linkage.get("gl_account_name"),
        "period_start": reconciliation.period_start,
        "period_end": reconciliation.period_end,
        "transaction_count": len(gl_transactions),
        "transactions": gl_transactions,
    }


@router.post("/reconciliations/{reconciliation_id}/match-to-gl")
async def match_statement_to_gl_entry(
    reconciliation_id: uuid.UUID,
    statement_transaction_id: uuid.UUID,
    journal_entry_line_id: uuid.UUID,
    match_notes: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Match a bank statement transaction to a GL journal entry line.
    
    Creates a direct link between the statement transaction and the GL entry,
    enabling full audit trail from bank to books.
    """
    service = get_bank_reconciliation_service(db)
    
    result = await service.match_statement_to_gl(
        reconciliation_id=reconciliation_id,
        entity_id=entity_id,
        statement_transaction_id=statement_transaction_id,
        journal_entry_line_id=journal_entry_line_id,
        match_notes=match_notes,
    )
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    
    return result


@router.post("/reconciliations/{reconciliation_id}/auto-match-gl")
async def auto_match_to_gl_entries(
    reconciliation_id: uuid.UUID,
    amount_tolerance: Optional[float] = 0.01,
    date_tolerance_days: Optional[int] = 3,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Automatically match unmatched statement transactions to GL journal entries.
    
    Uses intelligent matching based on:
    - Amount (with configurable tolerance)
    - Date (with configurable tolerance in days)
    - Reference matching
    
    This matches bank statement transactions directly to GL entries instead
    of sub-ledger transactions, useful for reconciling bank GL account.
    """
    service = get_bank_reconciliation_service(db)
    
    # Validate GL linkage first
    reconciliation = await service.get_reconciliation(reconciliation_id, entity_id)
    if not reconciliation:
        raise HTTPException(status_code=404, detail="Reconciliation not found")
    
    linkage = await service.validate_gl_linkage(reconciliation.bank_account_id, entity_id)
    if not linkage.get("valid"):
        raise HTTPException(
            status_code=400, 
            detail=f"Bank account not linked to GL: {linkage.get('error')}. Link the bank account to a GL account before GL matching."
        )
    
    result = await service.auto_match_to_gl(
        reconciliation_id=reconciliation_id,
        entity_id=entity_id,
        amount_tolerance=Decimal(str(amount_tolerance)),
        date_tolerance_days=date_tolerance_days,
    )
    
    return result


@router.post("/reconciliations/{reconciliation_id}/manual-match")
async def manual_match_transactions(
    reconciliation_id: uuid.UUID,
    match_request: ManualMatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Manually match statement transaction(s) with book transaction(s).
    
    Supports:
    - One-to-one: Single statement txn to single book txn
    - One-to-many: Single statement txn to multiple book txns
    - Many-to-one: Multiple statement txns to single book txn
    """
    service = get_bank_reconciliation_service(db)
    
    reconciliation = await service.get_reconciliation(reconciliation_id)
    if not reconciliation:
        raise HTTPException(status_code=404, detail="Reconciliation not found")
    
    if len(match_request.statement_transaction_ids) == 1:
        # One-to-one or one-to-many
        result = await service.match_transactions(
            statement_transaction_id=match_request.statement_transaction_ids[0],
            book_transaction_ids=match_request.book_transaction_ids,
            matched_by_id=current_user.id,
            notes=match_request.notes,
        )
        return {"success": True, "matched_count": 1}
    else:
        # Many-to-one
        if len(match_request.book_transaction_ids) != 1:
            raise HTTPException(
                status_code=400,
                detail="Many-to-one matching requires exactly one book transaction"
            )
        
        results = await service.match_many_to_one(
            statement_transaction_ids=match_request.statement_transaction_ids,
            book_transaction_id=match_request.book_transaction_ids[0],
            matched_by_id=current_user.id,
            notes=match_request.notes,
        )
        return {"success": True, "matched_count": len(results)}


@router.post("/transactions/{transaction_id}/unmatch")
async def unmatch_transaction(
    transaction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Unmatch a previously matched transaction."""
    service = get_bank_reconciliation_service(db)
    
    try:
        await service.unmatch_transaction(transaction_id)
        return {"success": True, "message": "Transaction unmatched"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# =============================================================================
# TRANSACTION ENDPOINTS
# =============================================================================

@router.get("/reconciliations/{reconciliation_id}/transactions", response_model=List[BankStatementTransactionResponse])
async def get_reconciliation_transactions(
    reconciliation_id: uuid.UUID,
    match_status: Optional[MatchStatus] = Query(None),
    is_bank_charge: Optional[bool] = Query(None),
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get transactions for a reconciliation with filtering."""
    service = get_bank_reconciliation_service(db)
    
    transactions = await service.get_statement_transactions(
        reconciliation_id=reconciliation_id,
        match_status=match_status,
        is_bank_charge=is_bank_charge,
        limit=limit,
        offset=offset,
    )
    return transactions


# =============================================================================
# ADJUSTMENT ENDPOINTS
# =============================================================================

@router.get("/reconciliations/{reconciliation_id}/adjustments", response_model=List[ReconciliationAdjustmentResponse])
async def get_reconciliation_adjustments(
    reconciliation_id: uuid.UUID,
    adjustment_type: Optional[AdjustmentType] = Query(None),
    is_posted: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get adjustments for a reconciliation."""
    service = get_bank_reconciliation_service(db)
    
    adjustments = await service.get_adjustments(
        reconciliation_id=reconciliation_id,
        adjustment_type=adjustment_type,
        is_posted=is_posted,
    )
    return adjustments


@router.post("/reconciliations/{reconciliation_id}/adjustments", response_model=ReconciliationAdjustmentResponse, status_code=status.HTTP_201_CREATED)
async def add_adjustment(
    reconciliation_id: uuid.UUID,
    adjustment_data: ReconciliationAdjustmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add an adjustment to a reconciliation."""
    service = get_bank_reconciliation_service(db)
    
    try:
        adjustment = await service.add_adjustment(
            reconciliation_id=reconciliation_id,
            adjustment_type=adjustment_data.adjustment_type,
            amount=adjustment_data.amount,
            description=adjustment_data.description,
            reference=adjustment_data.reference,
            affects_bank=adjustment_data.affects_bank,
            affects_book=adjustment_data.affects_book,
            statement_transaction_id=adjustment_data.statement_transaction_id,
            gl_account_code=adjustment_data.gl_account_code,
            created_by_id=current_user.id,
        )
        return adjustment
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/adjustments/{adjustment_id}")
async def delete_adjustment(
    adjustment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an adjustment."""
    service = get_bank_reconciliation_service(db)
    
    try:
        success = await service.delete_adjustment(adjustment_id)
        if not success:
            raise HTTPException(status_code=404, detail="Adjustment not found")
        return {"success": True, "message": "Adjustment deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reconciliations/{reconciliation_id}/adjustments/auto-create-charges")
async def auto_create_charge_adjustments(
    reconciliation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Automatically create adjustments for detected bank charges.
    
    Creates adjustments for:
    - EMTL (Electronic Money Transfer Levy)
    - Stamp Duty
    - Bank charges
    - SMS fees
    - Maintenance fees
    - VAT/WHT
    """
    service = get_bank_reconciliation_service(db)
    
    adjustments = await service.auto_create_charge_adjustments(
        reconciliation_id=reconciliation_id,
        created_by_id=current_user.id,
    )
    
    return {
        "success": True,
        "adjustments_created": len(adjustments),
        "adjustment_ids": [str(a.id) for a in adjustments],
    }


@router.post("/reconciliations/{reconciliation_id}/adjustments/post")
async def post_adjustments(
    reconciliation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Post all unposted adjustments to the general ledger."""
    service = get_bank_reconciliation_service(db)
    
    result = await service.post_adjustments(
        reconciliation_id=reconciliation_id,
        posted_by_id=current_user.id,
    )
    
    return result


# =============================================================================
# WORKFLOW ENDPOINTS
# =============================================================================

@router.post("/reconciliations/{reconciliation_id}/submit")
async def submit_for_review(
    reconciliation_id: uuid.UUID,
    notes: Optional[str] = Body(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a reconciliation for review."""
    service = get_bank_reconciliation_service(db)
    
    try:
        reconciliation = await service.submit_for_review(
            reconciliation_id=reconciliation_id,
            submitted_by_id=current_user.id,
            notes=notes,
        )
        return {
            "success": True,
            "status": reconciliation.status.value,
            "message": "Reconciliation submitted for review",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reconciliations/{reconciliation_id}/approve")
async def approve_reconciliation(
    reconciliation_id: uuid.UUID,
    notes: Optional[str] = Body(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve a reconciliation."""
    service = get_bank_reconciliation_service(db)
    
    try:
        reconciliation = await service.approve_reconciliation(
            reconciliation_id=reconciliation_id,
            approved_by_id=current_user.id,
            notes=notes,
        )
        return {
            "success": True,
            "status": reconciliation.status.value,
            "message": "Reconciliation approved",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reconciliations/{reconciliation_id}/reject")
async def reject_reconciliation(
    reconciliation_id: uuid.UUID,
    reason: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reject a reconciliation back to draft."""
    service = get_bank_reconciliation_service(db)
    
    try:
        reconciliation = await service.reject_reconciliation(
            reconciliation_id=reconciliation_id,
            rejected_by_id=current_user.id,
            reason=reason,
        )
        return {
            "success": True,
            "status": reconciliation.status.value,
            "message": "Reconciliation rejected",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reconciliations/{reconciliation_id}/reopen")
async def reopen_reconciliation(
    reconciliation_id: uuid.UUID,
    reason: Optional[str] = Body(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reopen a rejected reconciliation for corrections."""
    service = get_bank_reconciliation_service(db)
    
    try:
        reconciliation = await service.reopen_reconciliation(
            reconciliation_id=reconciliation_id,
            reopened_by_id=current_user.id,
            reason=reason,
        )
        return {
            "success": True,
            "status": reconciliation.status.value,
            "message": "Reconciliation reopened",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reconciliations/{reconciliation_id}/complete")
async def complete_reconciliation(
    reconciliation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a reconciliation as completed."""
    service = get_bank_reconciliation_service(db)
    
    try:
        reconciliation = await service.complete_reconciliation(
            reconciliation_id=reconciliation_id,
            completed_by_id=current_user.id,
        )
        return {
            "success": True,
            "status": reconciliation.status.value,
            "message": "Reconciliation completed",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# UNMATCHED ITEMS ENDPOINTS
# =============================================================================

@router.get("/reconciliations/{reconciliation_id}/unmatched-items", response_model=List[UnmatchedItemResponse])
async def get_unmatched_items(
    reconciliation_id: uuid.UUID,
    item_type: Optional[UnmatchedItemType] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get unmatched items for a reconciliation."""
    service = get_bank_reconciliation_service(db)
    
    items = await service.get_unmatched_items(
        reconciliation_id=reconciliation_id,
        item_type=item_type,
        status=status_filter,
    )
    return items


@router.post("/reconciliations/{reconciliation_id}/unmatched-items/auto-create")
async def auto_create_unmatched_items(
    reconciliation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Automatically create unmatched item records from unmatched transactions."""
    service = get_bank_reconciliation_service(db)
    
    items = await service.auto_create_unmatched_items(
        reconciliation_id=reconciliation_id,
        created_by_id=current_user.id,
    )
    
    return {
        "success": True,
        "items_created": len(items),
        "item_ids": [str(item.id) for item in items],
    }


@router.post("/unmatched-items/{item_id}/resolve")
async def resolve_unmatched_item(
    item_id: uuid.UUID,
    resolution: str = Body(...),
    notes: Optional[str] = Body(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark an unmatched item as resolved."""
    service = get_bank_reconciliation_service(db)
    
    try:
        item = await service.resolve_unmatched_item(
            item_id=item_id,
            resolution=resolution,
            resolved_by_id=current_user.id,
            notes=notes,
        )
        return {"success": True, "item": item}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# =============================================================================
# RULES MANAGEMENT ENDPOINTS
# =============================================================================

@router.get("/charge-rules", response_model=List[BankChargeRuleResponse])
async def get_charge_rules(
    is_active: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get charge detection rules for the entity."""
    service = get_bank_reconciliation_service(db)
    rules = await service.get_charge_rules(entity_id, is_active)
    return rules


@router.post("/charge-rules", response_model=BankChargeRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_charge_rule(
    rule_data: BankChargeRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Create a new charge detection rule."""
    service = get_bank_reconciliation_service(db)
    
    rule = await service.create_charge_rule(
        entity_id=entity_id,
        name=rule_data.name,
        description=rule_data.description,
        pattern=rule_data.pattern,
        charge_type=rule_data.charge_type,
        fixed_amount=rule_data.fixed_amount,
        percentage=rule_data.percentage,
        min_amount=rule_data.min_amount,
        max_amount=rule_data.max_amount,
        gl_account_code=rule_data.gl_account_code,
        priority=rule_data.priority,
        created_by_id=current_user.id,
    )
    return rule


@router.get("/matching-rules", response_model=List[MatchingRuleResponse])
async def get_matching_rules(
    is_active: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get matching rules for the entity."""
    service = get_bank_reconciliation_service(db)
    rules = await service.get_matching_rules(entity_id, is_active)
    return rules


@router.post("/matching-rules", response_model=MatchingRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_matching_rule(
    rule_data: MatchingRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Create a new matching rule."""
    service = get_bank_reconciliation_service(db)
    
    rule = await service.create_matching_rule(
        entity_id=entity_id,
        name=rule_data.name,
        description=rule_data.description,
        bank_pattern=rule_data.bank_pattern,
        book_pattern=rule_data.book_pattern,
        match_type=rule_data.match_type,
        date_tolerance_days=rule_data.date_tolerance_days,
        amount_tolerance_percent=rule_data.amount_tolerance_percent,
        priority=rule_data.priority,
        created_by_id=current_user.id,
    )
    return rule


# =============================================================================
# REPORTING ENDPOINTS
# =============================================================================

@router.get("/summary", response_model=ReconciliationSummaryReport)
async def get_reconciliation_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get reconciliation summary for all accounts in the entity."""
    service = get_bank_reconciliation_service(db)
    summary = await service.get_reconciliation_summary(entity_id)
    return summary


@router.get("/reconciliations/{reconciliation_id}/report")
async def get_reconciliation_report(
    reconciliation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a comprehensive reconciliation report for audit purposes."""
    service = get_bank_reconciliation_service(db)
    
    try:
        report = await service.generate_reconciliation_report(reconciliation_id)
        return report
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# =============================================================================
# GL INTEGRATION ENDPOINTS
# =============================================================================

@router.post("/reconciliations/{reconciliation_id}/create-journal-entries")
async def create_gl_journal_entries(
    reconciliation_id: uuid.UUID,
    auto_post: bool = Query(True, description="Auto-post journal entries"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Create general ledger journal entries from reconciliation adjustments.
    
    This creates proper double-entry journal entries for:
    - Bank charges (Dr Bank Charges / Cr Bank)
    - EMTL (Dr EMTL Expense / Cr Bank)  
    - Stamp Duty (Dr Statutory Charges / Cr Bank)
    - VAT on charges (Dr Input VAT / Cr Bank)
    - WHT deductions (Dr WHT Receivable / Cr Bank)
    - Interest earned (Dr Bank / Cr Interest Income)
    
    Nigerian Tax Compliance: Auto-posts charges to correct tax accounts.
    """
    service = get_bank_reconciliation_service(db)
    
    try:
        result = await service.create_gl_journal_entries(
            reconciliation_id=reconciliation_id,
            entity_id=entity_id,
            user_id=current_user.id,
            auto_post=auto_post,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/accounts/{account_id}/outstanding-items")
async def get_outstanding_items_for_carryforward(
    account_id: uuid.UUID,
    as_of_date: date = Query(..., description="Get items outstanding as of this date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Get outstanding items for carry-forward to next period.
    
    Returns:
    - Deposits in transit
    - Outstanding cheques
    - Other unresolved items
    
    These items should be reviewed and carried forward in the next reconciliation.
    """
    service = get_bank_reconciliation_service(db)
    
    # Verify account belongs to entity
    account = await service.get_bank_account(account_id, entity_id)
    if not account:
        raise HTTPException(status_code=404, detail="Bank account not found")
    
    result = await service.get_outstanding_items_for_carryforward(
        bank_account_id=account_id,
        as_of_date=as_of_date,
    )
    return result


@router.get("/validate-for-period-close")
async def validate_reconciliation_for_period_close(
    period_end_date: date = Query(..., description="Period end date to validate against"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Validate that all bank accounts are reconciled for period close.
    
    This is required for month-end close workflow:
    1. All bank accounts must have a completed/approved reconciliation
    2. The reconciliation must cover up to the period end date
    3. All adjustments must be posted to GL
    
    Returns validation result with blocking issues if any.
    """
    service = get_bank_reconciliation_service(db)
    
    result = await service.validate_reconciliation_for_period_close(
        entity_id=entity_id,
        period_end_date=period_end_date,
    )
    return result

