"""
Tekvwa Pro Audit - Transactions Router

API endpoints for transaction (expense/income) recording.

NTAA 2025 Compliance:
- Maker-Checker Segregation of Duties for WREN verification
- Proper RBAC permission enforcement

SKU Usage Metering:
- Transaction creation is metered for SKU tier limits
"""

from datetime import date
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

from app.database import get_async_session
from app.dependencies import (
    get_current_active_user,
    require_organization_permission,
    require_within_usage_limit,
)
from app.models.user import User, UserRole
from app.models.transaction import TransactionType, WRENStatus
from app.models.audit_consolidated import AuditAction
from app.models.sku import UsageMetricType
from app.schemas.auth import MessageResponse
from app.services.transaction_service import TransactionService
from app.services.entity_service import EntityService
from app.services.audit_service import AuditService
from app.services.metering_service import MeteringService
from app.utils.permissions import OrganizationPermission, has_organization_permission


router = APIRouter()


class TransactionTypeEnum(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"


class TransactionCreateRequest(BaseModel):
    """Schema for creating a transaction."""
    transaction_type: TransactionTypeEnum
    transaction_date: date
    amount: float = Field(..., gt=0)
    vat_amount: float = Field(0, ge=0)
    description: str = Field(..., min_length=1, max_length=500)
    reference: Optional[str] = Field(None, max_length=100)
    category_id: UUID
    vendor_id: Optional[UUID] = None
    receipt_url: Optional[str] = None
    # Multi-currency support (IAS 21 compliant)
    currency: Optional[str] = Field("NGN", min_length=3, max_length=3)
    exchange_rate: Optional[float] = Field(None, gt=0)
    exchange_rate_source: Optional[str] = None


class TransactionResponse(BaseModel):
    """Schema for transaction response."""
    id: UUID
    entity_id: UUID
    transaction_type: str
    transaction_date: date
    amount: float
    vat_amount: float
    total_amount: float
    description: str
    reference: Optional[str] = None
    category_id: Optional[UUID] = None
    category_name: Optional[str] = None
    vendor_id: Optional[UUID] = None
    vendor_name: Optional[str] = None
    wren_status: str
    vat_recoverable: bool
    receipt_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    # Multi-currency fields
    currency: Optional[str] = None
    exchange_rate: Optional[float] = None
    exchange_rate_source: Optional[str] = None
    functional_amount: Optional[float] = None
    functional_vat_amount: Optional[float] = None
    functional_total_amount: Optional[float] = None
    realized_fx_gain_loss: Optional[float] = None

    class Config:
        from_attributes = True


class TransactionListResponse(BaseModel):
    """List of transactions response."""
    transactions: List[TransactionResponse]
    total: int
    total_amount: float
    total_vat: float


class TransactionSummaryResponse(BaseModel):
    """Transaction summary for a period."""
    period_start: date
    period_end: date
    total_income: float
    income_count: int
    income_vat_collected: float
    total_expenses: float
    expense_count: int
    expense_vat_paid: float
    net_amount: float
    vat_position: float
    wren_breakdown: dict


@router.get(
    "/{entity_id}/transactions",
    response_model=TransactionListResponse,
    summary="List transactions",
)
async def list_transactions(
    entity_id: UUID,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    transaction_type: Optional[str] = Query(None),
    category_id: Optional[UUID] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """List all transactions for an entity."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    transaction_service = TransactionService(db)
    transactions, total = await transaction_service.get_transactions_for_entity(
        entity_id,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
        category_id=category_id,
        limit=limit,
        offset=offset,
    )
    
    totals = await transaction_service.get_totals(
        entity_id,
        start_date=start_date,
        end_date=end_date,
        transaction_type=transaction_type,
    )
    
    transaction_responses = [
        TransactionResponse(
            id=t.id,
            entity_id=t.entity_id,
            transaction_type=t.transaction_type.value,
            transaction_date=t.transaction_date,
            amount=float(t.amount),
            vat_amount=float(t.vat_amount),
            total_amount=float(t.total_amount),
            description=t.description,
            reference=t.reference,
            category_id=t.category_id,
            category_name=t.category.name if t.category else None,
            vendor_id=t.vendor_id,
            vendor_name=t.vendor.name if t.vendor else None,
            wren_status=t.wren_status.value,
            vat_recoverable=t.vat_recoverable,
            receipt_url=t.receipt_url,
            created_at=t.created_at,
            updated_at=t.updated_at,
            currency=t.currency,
            exchange_rate=t.exchange_rate,
            exchange_rate_source=t.exchange_rate_source,
            functional_amount=t.functional_amount,
            functional_vat_amount=t.functional_vat_amount,
            functional_total_amount=t.functional_total_amount,
            realized_fx_gain_loss=t.realized_fx_gain_loss,
        )
        for t in transactions
    ]
    
    return TransactionListResponse(
        transactions=transaction_responses,
        total=total,
        total_amount=totals["total_amount"],
        total_vat=totals["total_vat"],
    )


@router.post(
    "/{entity_id}/transactions",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create transaction",
)
async def create_transaction(
    entity_id: UUID,
    request: TransactionCreateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
    _limit_check: User = Depends(require_within_usage_limit(UsageMetricType.TRANSACTIONS)),
):
    """
    Create a new transaction with multi-currency support.
    
    Multi-Currency Features (IAS 21 Compliant):
    - currency: Transaction currency (defaults to NGN)
    - exchange_rate: Exchange rate to functional currency (NGN)
    - Functional currency amounts auto-calculated for GL posting
    """
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    can_write = await entity_service.check_user_can_write(current_user, entity_id)
    if not can_write:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access denied for this entity",
        )
    
    transaction_service = TransactionService(db)
    
    # Get FX service for rate lookups if needed
    fx_service = None
    if request.currency and request.currency != "NGN":
        from app.services.fx_service import FXService
        fx_service = FXService(db)
    
    try:
        tx_type = TransactionType(request.transaction_type.value)
        
        transaction = await transaction_service.create_transaction(
            entity_id=entity_id,
            user_id=current_user.id,
            transaction_type=tx_type,
            transaction_date=request.transaction_date,
            amount=request.amount,
            vat_amount=request.vat_amount,
            description=request.description,
            reference=request.reference,
            category_id=request.category_id,
            vendor_id=request.vendor_id,
            receipt_url=request.receipt_url,
            # Multi-currency support
            currency=request.currency,
            exchange_rate=request.exchange_rate,
            exchange_rate_source=request.exchange_rate_source,
            fx_service=fx_service,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    # Audit log for transaction creation
    audit_service = AuditService(db)
    audit_values = {
        "transaction_type": request.transaction_type.value,
        "amount": float(request.amount),
        "vat_amount": float(request.vat_amount),
        "description": request.description,
        "reference": request.reference,
        "transaction_date": str(request.transaction_date),
    }
    # Add FX info to audit if foreign currency
    if request.currency and request.currency != "NGN":
        audit_values["currency"] = request.currency
        audit_values["exchange_rate"] = request.exchange_rate
    
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="transaction",
        entity_id=str(transaction.id),
        action=AuditAction.CREATE,
        user_id=current_user.id,
        new_values=audit_values,
    )
    
    # Record usage metering for SKU tier limits
    if current_user.organization_id:
        metering_service = MeteringService(db)
        await metering_service.record_transaction(
            organization_id=current_user.organization_id,
            entity_id=entity_id,
            user_id=current_user.id,
            transaction_id=str(transaction.id),
        )
    
    transaction = await transaction_service.get_transaction_by_id(transaction.id, entity_id)
    
    return TransactionResponse(
        id=transaction.id,
        entity_id=transaction.entity_id,
        transaction_type=transaction.transaction_type.value,
        transaction_date=transaction.transaction_date,
        amount=float(transaction.amount),
        vat_amount=float(transaction.vat_amount),
        total_amount=float(transaction.total_amount),
        description=transaction.description,
        reference=transaction.reference,
        category_id=transaction.category_id,
        category_name=transaction.category.name if transaction.category else None,
        vendor_id=transaction.vendor_id,
        vendor_name=transaction.vendor.name if transaction.vendor else None,
        wren_status=transaction.wren_status.value,
        vat_recoverable=transaction.vat_recoverable,
        receipt_url=transaction.receipt_url,
        created_at=transaction.created_at,
        updated_at=transaction.updated_at,
        # Multi-currency fields
        currency=transaction.currency,
        exchange_rate=transaction.exchange_rate,
        exchange_rate_source=transaction.exchange_rate_source,
        functional_amount=transaction.functional_amount,
        functional_vat_amount=transaction.functional_vat_amount,
        functional_total_amount=transaction.functional_total_amount,
        realized_fx_gain_loss=transaction.realized_fx_gain_loss,
    )


@router.get(
    "/{entity_id}/transactions/summary",
    response_model=TransactionSummaryResponse,
    summary="Get transaction summary",
)
async def get_transaction_summary(
    entity_id: UUID,
    start_date: date = Query(...),
    end_date: date = Query(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get transaction summary for a period."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    transaction_service = TransactionService(db)
    summary = await transaction_service.get_transaction_summary(
        entity_id,
        start_date,
        end_date,
    )
    
    return TransactionSummaryResponse(**summary)


@router.get(
    "/{entity_id}/transactions/{transaction_id}",
    response_model=TransactionResponse,
    summary="Get transaction",
)
async def get_transaction(
    entity_id: UUID,
    transaction_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get a specific transaction."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    transaction_service = TransactionService(db)
    transaction = await transaction_service.get_transaction_by_id(transaction_id, entity_id)
    
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )
    
    return TransactionResponse(
        id=transaction.id,
        entity_id=transaction.entity_id,
        transaction_type=transaction.transaction_type.value,
        transaction_date=transaction.transaction_date,
        amount=float(transaction.amount),
        vat_amount=float(transaction.vat_amount),
        total_amount=float(transaction.total_amount),
        description=transaction.description,
        reference=transaction.reference,
        category_id=transaction.category_id,
        category_name=transaction.category.name if transaction.category else None,
        vendor_id=transaction.vendor_id,
        vendor_name=transaction.vendor.name if transaction.vendor else None,
        wren_status=transaction.wren_status.value,
        vat_recoverable=transaction.vat_recoverable,
        receipt_url=transaction.receipt_url,
        created_at=transaction.created_at,
        updated_at=transaction.updated_at,
        currency=transaction.currency,
        exchange_rate=transaction.exchange_rate,
        exchange_rate_source=transaction.exchange_rate_source,
        functional_amount=transaction.functional_amount,
        functional_vat_amount=transaction.functional_vat_amount,
        functional_total_amount=transaction.functional_total_amount,
        realized_fx_gain_loss=transaction.realized_fx_gain_loss,
    )


class TransactionUpdateRequest(BaseModel):
    """Schema for updating a transaction."""
    transaction_date: Optional[date] = None
    amount: Optional[float] = Field(None, gt=0)
    vat_amount: Optional[float] = Field(None, ge=0)
    description: Optional[str] = Field(None, min_length=1, max_length=500)
    reference: Optional[str] = Field(None, max_length=100)
    category_id: Optional[UUID] = None


@router.patch(
    "/{entity_id}/transactions/{transaction_id}",
    response_model=TransactionResponse,
    summary="Update transaction",
)
async def update_transaction(
    entity_id: UUID,
    transaction_id: UUID,
    request: TransactionUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Update an existing transaction."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    can_write = await entity_service.check_user_can_write(current_user, entity_id)
    if not can_write:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access denied for this entity",
        )
    
    transaction_service = TransactionService(db)
    transaction = await transaction_service.get_transaction_by_id(transaction_id, entity_id)
    
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )
    
    # Store old values for audit
    old_values = {
        "amount": float(transaction.amount),
        "vat_amount": float(transaction.vat_amount),
        "description": transaction.description,
        "reference": transaction.reference,
        "transaction_date": str(transaction.transaction_date),
    }
    
    update_data = request.model_dump(exclude_unset=True)
    transaction = await transaction_service.update_transaction(transaction, **update_data)
    
    # Audit log for transaction update
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="transaction",
        entity_id=str(transaction.id),
        action=AuditAction.UPDATE,
        user_id=current_user.id,
        old_values=old_values,
        new_values=update_data,
    )
    
    # Reload with relationships
    transaction = await transaction_service.get_transaction_by_id(transaction.id, entity_id)
    
    return TransactionResponse(
        id=transaction.id,
        entity_id=transaction.entity_id,
        transaction_type=transaction.transaction_type.value,
        transaction_date=transaction.transaction_date,
        amount=float(transaction.amount),
        vat_amount=float(transaction.vat_amount),
        total_amount=float(transaction.total_amount),
        description=transaction.description,
        reference=transaction.reference,
        category_id=transaction.category_id,
        category_name=transaction.category.name if transaction.category else None,
        vendor_id=transaction.vendor_id,
        vendor_name=transaction.vendor.name if transaction.vendor else None,
        wren_status=transaction.wren_status.value,
        vat_recoverable=transaction.vat_recoverable,
        receipt_url=transaction.receipt_url,
        created_at=transaction.created_at,
        updated_at=transaction.updated_at,
        currency=transaction.currency,
        exchange_rate=transaction.exchange_rate,
        exchange_rate_source=transaction.exchange_rate_source,
        functional_amount=transaction.functional_amount,
        functional_vat_amount=transaction.functional_vat_amount,
        functional_total_amount=transaction.functional_total_amount,
        realized_fx_gain_loss=transaction.realized_fx_gain_loss,
    )


@router.delete(
    "/{entity_id}/transactions/{transaction_id}",
    response_model=MessageResponse,
    summary="Delete transaction",
)
async def delete_transaction(
    entity_id: UUID,
    transaction_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Delete a transaction."""
    # Check DELETE permission
    if not current_user.is_platform_staff:
        if not has_organization_permission(current_user.role, OrganizationPermission.DELETE_TRANSACTIONS):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Delete transactions permission required",
            )
    
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    can_write = await entity_service.check_user_can_write(current_user, entity_id)
    if not can_write:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access denied for this entity",
        )
    
    transaction_service = TransactionService(db)
    transaction = await transaction_service.get_transaction_by_id(transaction_id, entity_id)
    
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )
    
    # Store transaction data for audit before deletion
    deleted_values = {
        "transaction_type": transaction.transaction_type.value,
        "amount": float(transaction.amount),
        "vat_amount": float(transaction.vat_amount),
        "description": transaction.description,
        "reference": transaction.reference,
        "transaction_date": str(transaction.transaction_date),
    }
    deleted_id = str(transaction.id)
    
    await transaction_service.delete_transaction(transaction)
    
    # Audit log for transaction deletion
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="transaction",
        entity_id=deleted_id,
        action=AuditAction.DELETE,
        user_id=current_user.id,
        old_values=deleted_values,
    )
    
    return MessageResponse(
        message="Transaction deleted successfully",
        success=True,
    )


# ===========================================
# WREN VERIFICATION (NTAA 2025 - Maker-Checker SoD)
# ===========================================

class WRENVerifyRequest(BaseModel):
    """Request schema for WREN verification."""
    wren_status: str = Field(..., description="WREN status: compliant, non_compliant, review_required")
    notes: Optional[str] = Field(None, max_length=1000)


class WRENVerifyResponse(BaseModel):
    """Response schema for WREN verification."""
    transaction_id: UUID
    wren_status: str
    verified_by: str
    verified_at: datetime
    notes: Optional[str] = None
    message: str


@router.post(
    "/{entity_id}/transactions/{transaction_id}/verify-wren",
    response_model=WRENVerifyResponse,
    summary="Verify WREN status (Maker-Checker)",
    description="""
    Verify the WREN (Wholly, Reasonably, Exclusively, Necessarily) status of an expense.
    
    NTAA 2025 Compliance - Maker-Checker Segregation of Duties:
    - The verifier (Checker) CANNOT be the same person who created the transaction (Maker)
    - Only users with VERIFY_WREN permission can verify
    
    Required permission: VERIFY_WREN
    """,
)
async def verify_wren_status(
    entity_id: UUID,
    transaction_id: UUID,
    request: WRENVerifyRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Verify WREN status of a transaction (Maker-Checker SoD).
    
    The Checker cannot verify a transaction they created (Maker).
    """
    # Check VERIFY_WREN permission
    if not current_user.is_platform_staff:
        if not has_organization_permission(current_user.role, OrganizationPermission.VERIFY_WREN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="VERIFY_WREN permission required. Available to: Owner, Admin, Accountant, External Accountant",
            )
    
    # Validate WREN status
    try:
        wren_status = WRENStatus(request.wren_status)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid WREN status: {request.wren_status}. Valid: compliant, non_compliant, review_required",
        )
    
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    transaction_service = TransactionService(db)
    transaction = await transaction_service.get_transaction_by_id(transaction_id, entity_id)
    
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )
    
    # Check if transaction is an expense (only expenses need WREN verification)
    if transaction.transaction_type != TransactionType.EXPENSE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="WREN verification is only applicable to expenses",
        )
    
    # NTAA 2025: Maker-Checker Segregation of Duties
    # The Checker cannot verify a transaction they created (Maker)
    if transaction.created_by_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Maker-Checker SoD violation: You cannot verify a transaction you created",
        )
    
    # Perform WREN verification
    verified_transaction = await transaction_service.verify_wren_status(
        transaction=transaction,
        verifier_id=current_user.id,
        wren_status=wren_status,
        notes=request.notes,
    )
    
    return WRENVerifyResponse(
        transaction_id=verified_transaction.id,
        wren_status=verified_transaction.wren_status.value,
        verified_by=current_user.email,
        verified_at=verified_transaction.wren_verified_at,
        notes=verified_transaction.wren_notes,
        message=f"WREN status verified as {wren_status.value}",
    )


# ===========================================
# ADDITIONAL TRANSACTION ENDPOINTS
# ===========================================

class AttachReceiptRequest(BaseModel):
    """Request to attach a receipt to a transaction."""
    receipt_url: str = Field(..., description="URL or path to the receipt file")
    receipt_type: Optional[str] = Field("receipt", description="Type: receipt, invoice, contract, other")


class RecurringTransactionCreate(BaseModel):
    """Create a recurring transaction schedule."""
    transaction_type: TransactionTypeEnum
    amount: float = Field(..., gt=0)
    vat_amount: float = Field(0, ge=0)
    description: str = Field(..., min_length=1, max_length=500)
    category_id: UUID
    vendor_id: Optional[UUID] = None
    frequency: str = Field(..., description="daily, weekly, monthly, quarterly, yearly")
    start_date: date
    end_date: Optional[date] = None
    next_occurrence: Optional[date] = None


class RecurringTransactionResponse(BaseModel):
    """Response for recurring transaction."""
    id: UUID
    entity_id: UUID
    transaction_type: str
    amount: float
    description: str
    frequency: str
    start_date: date
    end_date: Optional[date]
    next_occurrence: date
    is_active: bool
    created_at: datetime


class ImportTransactionsRequest(BaseModel):
    """Request to import transactions."""
    format: str = Field("csv", description="csv, ofx, qif")
    date_format: str = Field("%Y-%m-%d", description="Date format in the file")
    default_category_id: Optional[UUID] = None


@router.post(
    "/{entity_id}/transactions/{transaction_id}/attach-receipt",
    response_model=TransactionResponse,
    summary="Attach receipt to transaction",
    description="Attach a receipt or supporting document to an existing transaction.",
)
async def attach_receipt(
    entity_id: UUID,
    transaction_id: UUID,
    request: AttachReceiptRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Attach a receipt/document to a transaction."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    transaction_service = TransactionService(db)
    transaction = await transaction_service.get_transaction_by_id(transaction_id, entity_id)
    
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )
    
    # Update receipt URL
    transaction.receipt_url = request.receipt_url
    await db.commit()
    await db.refresh(transaction)
    
    return transaction_to_response(transaction)


@router.get(
    "/{entity_id}/transactions/recurring",
    response_model=List[RecurringTransactionResponse],
    summary="List recurring transactions",
    description="Get all recurring transaction schedules for the entity.",
)
async def list_recurring_transactions(
    entity_id: UUID,
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """List recurring transactions."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    # In production, query RecurringTransaction table
    # For now, return empty list (model needs to be created)
    return []


@router.post(
    "/{entity_id}/transactions/recurring",
    response_model=RecurringTransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create recurring transaction",
    description="Create a recurring transaction schedule.",
)
async def create_recurring_transaction(
    entity_id: UUID,
    request: RecurringTransactionCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Create a recurring transaction."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    valid_frequencies = ["daily", "weekly", "monthly", "quarterly", "yearly"]
    if request.frequency not in valid_frequencies:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid frequency. Valid: {', '.join(valid_frequencies)}",
        )
    
    # Calculate next occurrence
    next_occurrence = request.next_occurrence or request.start_date
    
    # In production, create RecurringTransaction record
    # For now, return placeholder
    return RecurringTransactionResponse(
        id=UUID("00000000-0000-0000-0000-000000000000"),
        entity_id=entity_id,
        transaction_type=request.transaction_type.value,
        amount=request.amount,
        description=request.description,
        frequency=request.frequency,
        start_date=request.start_date,
        end_date=request.end_date,
        next_occurrence=next_occurrence,
        is_active=True,
        created_at=datetime.utcnow(),
    )


@router.post(
    "/{entity_id}/transactions/recurring/{recurring_id}/toggle",
    response_model=dict,
    summary="Toggle recurring transaction",
    description="Enable or disable a recurring transaction schedule.",
)
async def toggle_recurring_transaction(
    entity_id: UUID,
    recurring_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Toggle recurring transaction active status."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    # In production, query and toggle the RecurringTransaction record
    # For now, return success placeholder
    return {"message": "Recurring transaction toggled", "is_active": True}


@router.delete(
    "/{entity_id}/transactions/recurring/{recurring_id}",
    response_model=dict,
    summary="Delete recurring transaction",
    description="Delete a recurring transaction schedule.",
)
async def delete_recurring_transaction(
    entity_id: UUID,
    recurring_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Delete a recurring transaction."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    # In production, delete the RecurringTransaction record
    # For now, return success placeholder
    return {"message": "Recurring transaction deleted"}


@router.post(
    "/{entity_id}/transactions/{transaction_id}/duplicate",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Duplicate transaction",
    description="Create a copy of an existing transaction with today's date.",
)
async def duplicate_transaction(
    entity_id: UUID,
    transaction_id: UUID,
    new_date: Optional[date] = Query(None, description="Date for the new transaction"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Duplicate a transaction."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    transaction_service = TransactionService(db)
    original = await transaction_service.get_transaction_by_id(transaction_id, entity_id)
    
    if not original:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )
    
    # Create duplicate
    new_transaction = await transaction_service.create_transaction(
        entity_id=entity_id,
        user_id=current_user.id,
        transaction_type=original.transaction_type,
        transaction_date=new_date or date.today(),
        amount=float(original.amount),
        vat_amount=float(original.vat_amount),
        description=f"Copy of: {original.description}",
        category_id=original.category_id,
        vendor_id=original.vendor_id,
        reference=None,
        receipt_url=None,
    )
    
    return transaction_to_response(new_transaction)


@router.post(
    "/{entity_id}/transactions/import",
    response_model=dict,
    summary="Import transactions",
    description="Import transactions from a CSV or bank statement file.",
)
async def import_transactions(
    entity_id: UUID,
    file: UploadFile = None,
    request: ImportTransactionsRequest = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Import transactions from file."""
    from fastapi import File, UploadFile
    
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    # In production, parse file and create transactions
    # For now, return placeholder
    return {
        "message": "Transaction import endpoint ready",
        "supported_formats": ["csv", "ofx", "qif"],
        "instructions": "Upload a CSV file with columns: date, description, amount, type",
    }


@router.get(
    "/{entity_id}/transactions/pending-categorization",
    response_model=TransactionListResponse,
    summary="Get uncategorized transactions",
    description="Get transactions that need categorization.",
)
async def get_uncategorized_transactions(
    entity_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get transactions pending categorization."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    transaction_service = TransactionService(db)
    
    # Get transactions with no category
    from sqlalchemy import select
    from app.models.transaction import Transaction
    
    query = select(Transaction).where(
        Transaction.entity_id == entity_id,
        Transaction.category_id == None,
        Transaction.is_deleted == False,
    ).offset(skip).limit(limit)
    
    result = await db.execute(query)
    transactions = result.scalars().all()
    
    return TransactionListResponse(
        transactions=[transaction_to_response(t) for t in transactions],
        total=len(transactions),
        total_amount=sum(float(t.amount) for t in transactions),
        total_vat=sum(float(t.vat_amount) for t in transactions),
    )


@router.get(
    "/{entity_id}/transactions/pending-wren",
    response_model=TransactionListResponse,
    summary="Get transactions pending WREN verification",
    description="Get expense transactions that need WREN verification (for Checker role).",
)
async def get_pending_wren_transactions(
    entity_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get transactions pending WREN verification."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    from sqlalchemy import select
    from app.models.transaction import Transaction
    
    query = select(Transaction).where(
        Transaction.entity_id == entity_id,
        Transaction.transaction_type == TransactionType.EXPENSE,
        Transaction.wren_status == WRENStatus.PENDING,
        Transaction.is_deleted == False,
        Transaction.created_by_id != current_user.id,  # Maker-Checker: can't verify own
    ).offset(skip).limit(limit)
    
    result = await db.execute(query)
    transactions = result.scalars().all()
    
    return TransactionListResponse(
        transactions=[transaction_to_response(t) for t in transactions],
        total=len(transactions),
        total_amount=sum(float(t.amount) for t in transactions),
        total_vat=sum(float(t.vat_amount) for t in transactions),
    )


@router.post(
    "/{entity_id}/transactions/batch-categorize",
    response_model=MessageResponse,
    summary="Batch categorize transactions",
    description="Update category for multiple transactions at once.",
)
async def batch_categorize_transactions(
    entity_id: UUID,
    transaction_ids: List[UUID],
    category_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Batch update transaction categories."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    from sqlalchemy import update
    from app.models.transaction import Transaction
    
    result = await db.execute(
        update(Transaction)
        .where(
            Transaction.entity_id == entity_id,
            Transaction.id.in_(transaction_ids),
        )
        .values(category_id=category_id)
    )
    
    await db.commit()
    
    return MessageResponse(
        message=f"Updated {result.rowcount} transactions with new category",
    )


# Helper function (if not already defined)
def transaction_to_response(transaction) -> TransactionResponse:
    """Convert Transaction model to response."""
    return TransactionResponse(
        id=transaction.id,
        entity_id=transaction.entity_id,
        transaction_type=transaction.transaction_type.value,
        transaction_date=transaction.transaction_date,
        amount=float(transaction.amount),
        vat_amount=float(transaction.vat_amount),
        total_amount=float(transaction.total_amount),
        description=transaction.description,
        reference=transaction.reference,
        category_id=transaction.category_id,
        category_name=transaction.category.name if transaction.category else None,
        vendor_id=transaction.vendor_id,
        vendor_name=transaction.vendor.name if transaction.vendor else None,
        wren_status=transaction.wren_status.value if transaction.wren_status else "pending",
        vat_recoverable=transaction.vat_recoverable,
        receipt_url=transaction.receipt_url,
        created_at=transaction.created_at,
        updated_at=transaction.updated_at,
        currency=transaction.currency,
        exchange_rate=transaction.exchange_rate,
        exchange_rate_source=transaction.exchange_rate_source,
        functional_amount=transaction.functional_amount,
        functional_vat_amount=transaction.functional_vat_amount,
        functional_total_amount=transaction.functional_total_amount,
        realized_fx_gain_loss=transaction.realized_fx_gain_loss,
    )
