"""
Tekvwa Pro Audit - Sales Router

API endpoints for sales recording with inventory integration.
Provides:
- Product lookup for POS-style sales
- Customer search and quick-add
- Sale recording with automatic stock deduction
- Sales reports and analytics
"""

from datetime import date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import get_current_active_user
from app.models.user import User
from app.models.invoice import VATTreatment
from app.services.sales_service import SalesService, SaleLineItem
from app.services.entity_service import EntityService
from app.services.audit_service import AuditService
from app.models.audit_consolidated import AuditAction


router = APIRouter()


# ===========================================
# SCHEMAS
# ===========================================

class ProductSearchResult(BaseModel):
    """Product search result for dropdown."""
    id: str
    sku: str
    name: str
    description: Optional[str]
    category: Optional[str]
    unit_price: float
    unit_cost: float
    quantity_available: int
    unit_of_measure: str
    barcode: Optional[str]
    is_low_stock: bool


class CustomerSearchResult(BaseModel):
    """Customer search result for dropdown."""
    id: str
    name: str
    email: Optional[str]
    phone: Optional[str]
    tin: Optional[str]
    address: Optional[str]
    city: Optional[str]
    state: Optional[str]
    is_vat_registered: bool
    payment_terms_days: int
    credit_limit: Optional[float]
    outstanding_balance: float
    is_business: bool


class QuickCustomerCreate(BaseModel):
    """Schema for quick customer creation during sales."""
    name: str = Field(..., min_length=1, max_length=255)
    email: Optional[str] = None
    phone: Optional[str] = None
    tin: Optional[str] = None
    address: Optional[str] = None


class QuickCustomerResponse(BaseModel):
    """Response for quick customer creation."""
    id: str
    name: str
    email: Optional[str]
    phone: Optional[str]
    tin: Optional[str]


class SaleLineItemRequest(BaseModel):
    """Line item in a sale."""
    inventory_item_id: Optional[UUID] = None
    description: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)
    vat_rate: float = Field(7.5, ge=0, le=100)
    discount_percent: float = Field(0, ge=0, le=100)


class RecordSaleRequest(BaseModel):
    """Request to record a sale."""
    customer_id: Optional[UUID] = None
    line_items: List[SaleLineItemRequest] = Field(..., min_length=1)
    sale_date: Optional[date] = None
    payment_method: Optional[str] = None
    reference: Optional[str] = None
    notes: Optional[str] = None
    create_invoice: bool = True
    vat_treatment: str = "standard"


class SaleResponse(BaseModel):
    """Response after recording a sale."""
    success: bool
    invoice_id: Optional[str]
    invoice_number: Optional[str]
    total_amount: float
    vat_amount: float
    message: str


class SalesSummaryResponse(BaseModel):
    """Sales summary for dashboard."""
    total_sales: float
    total_vat_collected: float
    total_discount_given: float
    sales_count: int
    top_products: List[dict]
    top_customers: List[dict]


class RecentSaleResponse(BaseModel):
    """Recent sale for list display."""
    id: str
    invoice_number: str
    customer_name: str
    invoice_date: str
    total_amount: float
    status: str
    payment_status: str


# ===========================================
# HELPER FUNCTIONS
# ===========================================

async def verify_entity_access(
    entity_id: UUID,
    user: User,
    db: AsyncSession,
) -> None:
    """Verify user has access to the entity."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, user)
    
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business entity not found or access denied",
        )


# ===========================================
# PRODUCT ENDPOINTS
# ===========================================

@router.get(
    "/{entity_id}/sales/products",
    response_model=List[ProductSearchResult],
    summary="Search products for sale",
    description="Search inventory items for POS-style product selection",
)
async def search_products(
    entity_id: UUID,
    search: Optional[str] = Query(None, description="Search by name, SKU, or barcode"),
    category: Optional[str] = Query(None),
    in_stock_only: bool = Query(True),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Search products available for sale."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = SalesService(db)
    items = await service.get_sellable_items(
        entity_id=entity_id,
        search=search,
        category=category,
        in_stock_only=in_stock_only,
        limit=limit,
    )
    
    return items


@router.get(
    "/{entity_id}/sales/products/barcode/{barcode}",
    response_model=ProductSearchResult,
    summary="Get product by barcode",
    description="Lookup product by barcode scan",
)
async def get_product_by_barcode(
    entity_id: UUID,
    barcode: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get product by barcode for POS scanning."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = SalesService(db)
    item = await service.get_item_by_barcode(entity_id, barcode)
    
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No product found with barcode: {barcode}",
        )
    
    return item


@router.get(
    "/{entity_id}/sales/categories",
    response_model=List[str],
    summary="Get product categories",
)
async def get_categories(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get all product categories for filtering."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = SalesService(db)
    return await service.get_inventory_categories(entity_id)


# ===========================================
# CUSTOMER ENDPOINTS
# ===========================================

@router.get(
    "/{entity_id}/sales/customers",
    response_model=List[CustomerSearchResult],
    summary="Search customers for sale",
    description="Search customers for invoice selection",
)
async def search_customers(
    entity_id: UUID,
    search: Optional[str] = Query(None, description="Search by name, email, phone, or TIN"),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Search customers for sales dropdown."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = SalesService(db)
    customers = await service.get_customers_for_dropdown(
        entity_id=entity_id,
        search=search,
        limit=limit,
    )
    
    return customers


@router.post(
    "/{entity_id}/sales/customers/quick",
    response_model=QuickCustomerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Quick-add customer",
    description="Quickly create a customer during checkout",
)
async def quick_add_customer(
    entity_id: UUID,
    request: QuickCustomerCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Quickly create a customer during sales process."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = SalesService(db)
    customer = await service.quick_create_customer(
        entity_id=entity_id,
        name=request.name,
        email=request.email,
        phone=request.phone,
        tin=request.tin,
        address=request.address,
    )
    
    # Audit logging
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="customer",
        entity_id=str(customer.id),
        action=AuditAction.CREATE,
        user_id=current_user.id,
        new_values={
            "name": customer.name,
            "email": customer.email,
            "source": "quick_add_sales",
        }
    )
    
    await db.commit()
    
    return QuickCustomerResponse(
        id=str(customer.id),
        name=customer.name,
        email=customer.email,
        phone=customer.phone,
        tin=customer.tin,
    )


# ===========================================
# SALES RECORDING ENDPOINTS
# ===========================================

@router.post(
    "/{entity_id}/sales/record",
    response_model=SaleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a sale",
    description="Record a sale with automatic inventory deduction and invoice creation",
)
async def record_sale(
    entity_id: UUID,
    request: RecordSaleRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Record a sale.
    
    This endpoint:
    - Creates an invoice (if create_invoice=True)
    - Deducts inventory stock
    - Records stock movements
    - Creates income transaction
    """
    await verify_entity_access(entity_id, current_user, db)
    
    # Convert request to SaleLineItem objects
    line_items = [
        SaleLineItem(
            inventory_item_id=item.inventory_item_id,
            description=item.description,
            quantity=item.quantity,
            unit_price=Decimal(str(item.unit_price)),
            vat_rate=Decimal(str(item.vat_rate)),
            discount_percent=Decimal(str(item.discount_percent)),
        )
        for item in request.line_items
    ]
    
    # Convert VAT treatment
    try:
        vat_treatment = VATTreatment(request.vat_treatment)
    except ValueError:
        vat_treatment = VATTreatment.STANDARD
    
    service = SalesService(db)
    
    try:
        invoice, transactions = await service.record_sale(
            entity_id=entity_id,
            user_id=current_user.id,
            customer_id=request.customer_id,
            line_items=line_items,
            sale_date=request.sale_date,
            payment_method=request.payment_method,
            reference=request.reference,
            notes=request.notes,
            create_invoice=request.create_invoice,
            vat_treatment=vat_treatment,
        )
        
        total_amount = sum(item.total for item in line_items)
        vat_amount = sum(item.vat_amount for item in line_items) if vat_treatment == VATTreatment.STANDARD else Decimal("0")
        
        # Audit logging
        audit_service = AuditService(db)
        await audit_service.log_action(
            business_entity_id=entity_id,
            entity_type="sale",
            entity_id=str(invoice.id) if invoice else None,
            action=AuditAction.CREATE,
            user_id=current_user.id,
            new_values={
                "invoice_number": invoice.invoice_number if invoice else None,
                "total_amount": str(total_amount),
                "vat_amount": str(vat_amount),
                "items_count": len(line_items),
                "customer_id": str(request.customer_id) if request.customer_id else None,
            }
        )
        
        return SaleResponse(
            success=True,
            invoice_id=str(invoice.id) if invoice else None,
            invoice_number=invoice.invoice_number if invoice else None,
            total_amount=float(total_amount),
            vat_amount=float(vat_amount),
            message="Sale recorded successfully",
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to record sale: {str(e)}",
        )


# ===========================================
# SALES REPORTS ENDPOINTS
# ===========================================

@router.get(
    "/{entity_id}/sales/summary",
    response_model=SalesSummaryResponse,
    summary="Get sales summary",
)
async def get_sales_summary(
    entity_id: UUID,
    start_date: date = Query(...),
    end_date: date = Query(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get sales summary for a date range."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = SalesService(db)
    summary = await service.get_sales_summary(
        entity_id=entity_id,
        start_date=start_date,
        end_date=end_date,
    )
    
    return SalesSummaryResponse(
        total_sales=float(summary.total_sales),
        total_vat_collected=float(summary.total_vat_collected),
        total_discount_given=float(summary.total_discount_given),
        sales_count=summary.sales_count,
        top_products=summary.top_products,
        top_customers=summary.top_customers,
    )


@router.get(
    "/{entity_id}/sales/recent",
    response_model=List[RecentSaleResponse],
    summary="Get recent sales",
)
async def get_recent_sales(
    entity_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get recent sales for dashboard display."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = SalesService(db)
    sales = await service.get_recent_sales(entity_id, limit)
    
    return sales


# ===========================================
# REFUND ENDPOINTS
# ===========================================

class RefundLineItem(BaseModel):
    """Line item for a refund."""
    line_item_id: UUID = Field(..., description="Original invoice line item ID")
    quantity: int = Field(..., gt=0, description="Quantity to refund")
    reason: Optional[str] = None


class RefundRequest(BaseModel):
    """Request to process a refund."""
    invoice_id: UUID = Field(..., description="Original invoice ID")
    line_items: List[RefundLineItem] = Field(..., min_length=1)
    refund_date: Optional[date] = None
    refund_method: str = Field("original_method", description="Refund payment method")
    reason: str = Field(..., min_length=1, max_length=500)
    restock_items: bool = Field(True, description="Return items to inventory")
    notes: Optional[str] = None


class RefundResponse(BaseModel):
    """Response after processing a refund."""
    refund_id: str
    credit_note_number: Optional[str]
    refund_amount: float
    vat_refunded: float
    items_restocked: bool
    message: str


@router.post(
    "/{entity_id}/sales/refund",
    response_model=RefundResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Process a sales refund",
)
async def process_refund(
    entity_id: UUID,
    request: RefundRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Process a sales refund (return).
    
    This endpoint:
    - Creates a credit note linked to the original invoice
    - Optionally restocks returned items
    - Records refund transaction
    - Updates customer balance
    
    2026 Compliance:
    - Credit notes must reference original invoice IRN
    - Requires NRS notification for e-invoice scenarios
    """
    await verify_entity_access(entity_id, current_user, db)
    
    from datetime import date as date_type
    import uuid
    
    service = SalesService(db)
    
    try:
        # Get original invoice
        from app.services.invoice_service import InvoiceService
        invoice_service = InvoiceService(db)
        original_invoice = await invoice_service.get_invoice_by_id(request.invoice_id)
        
        if not original_invoice:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Original invoice not found",
            )
        
        if original_invoice.entity_id != entity_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invoice does not belong to this entity",
            )
        
        # Process refund
        refund_result = await service.process_refund(
            entity_id=entity_id,
            user_id=current_user.id,
            invoice_id=request.invoice_id,
            line_items=[
                {
                    "line_item_id": item.line_item_id,
                    "quantity": item.quantity,
                    "reason": item.reason,
                }
                for item in request.line_items
            ],
            refund_date=request.refund_date or date_type.today(),
            refund_method=request.refund_method,
            reason=request.reason,
            restock_items=request.restock_items,
            notes=request.notes,
        )
        
        await db.commit()
        
        return RefundResponse(
            refund_id=str(refund_result.get("refund_id", uuid.uuid4())),
            credit_note_number=refund_result.get("credit_note_number"),
            refund_amount=float(refund_result.get("refund_amount", 0)),
            vat_refunded=float(refund_result.get("vat_refunded", 0)),
            items_restocked=request.restock_items,
            message="Refund processed successfully",
        )
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to process refund: {str(e)}",
        )


# ===========================================
# DAILY REPORT & REGISTER ENDPOINTS
# ===========================================

class PaymentBreakdown(BaseModel):
    """Payment method breakdown."""
    method: str
    amount: float
    transaction_count: int


class DailyReportResponse(BaseModel):
    """Daily sales report response."""
    entity_id: str
    report_date: date
    opening_balance: float
    total_sales: float
    total_refunds: float
    net_sales: float
    vat_collected: float
    discount_given: float
    transaction_count: int
    refund_count: int
    payment_breakdown: List[PaymentBreakdown]
    top_selling_items: List[dict]
    hourly_sales: List[dict]
    closing_balance: float
    variance: float  # Difference between expected and actual cash
    generated_at: str


@router.get(
    "/{entity_id}/sales/daily-report",
    response_model=DailyReportResponse,
    summary="Get daily sales report",
)
async def get_daily_report(
    entity_id: UUID,
    report_date: Optional[date] = Query(None, description="Report date (defaults to today)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get comprehensive daily sales report.
    
    Includes:
    - Sales and refund totals
    - Payment method breakdown
    - Hourly sales distribution
    - Top selling items
    - Cash drawer reconciliation data
    
    Use this for end-of-day reporting and shift handovers.
    """
    from datetime import date as date_type, datetime
    
    await verify_entity_access(entity_id, current_user, db)
    
    effective_date = report_date or date_type.today()
    
    service = SalesService(db)
    
    try:
        report_data = await service.get_daily_report(
            entity_id=entity_id,
            report_date=effective_date,
        )
    except Exception:
        # Fallback structure
        report_data = {
            "opening_balance": 0,
            "total_sales": 0,
            "total_refunds": 0,
            "vat_collected": 0,
            "discount_given": 0,
            "transaction_count": 0,
            "refund_count": 0,
            "payment_breakdown": [],
            "top_selling_items": [],
            "hourly_sales": [],
            "closing_balance": 0,
            "variance": 0,
        }
    
    return DailyReportResponse(
        entity_id=str(entity_id),
        report_date=effective_date,
        opening_balance=report_data.get("opening_balance", 0),
        total_sales=report_data.get("total_sales", 0),
        total_refunds=report_data.get("total_refunds", 0),
        net_sales=report_data.get("total_sales", 0) - report_data.get("total_refunds", 0),
        vat_collected=report_data.get("vat_collected", 0),
        discount_given=report_data.get("discount_given", 0),
        transaction_count=report_data.get("transaction_count", 0),
        refund_count=report_data.get("refund_count", 0),
        payment_breakdown=[
            PaymentBreakdown(**p) for p in report_data.get("payment_breakdown", [])
        ],
        top_selling_items=report_data.get("top_selling_items", []),
        hourly_sales=report_data.get("hourly_sales", []),
        closing_balance=report_data.get("closing_balance", 0),
        variance=report_data.get("variance", 0),
        generated_at=datetime.now().isoformat(),
    )


class OpenRegisterRequest(BaseModel):
    """Request to open cash register."""
    opening_balance: float = Field(..., ge=0, description="Opening cash balance")
    register_id: Optional[str] = Field(None, description="Register identifier")
    notes: Optional[str] = None


class CloseRegisterRequest(BaseModel):
    """Request to close cash register."""
    actual_cash: float = Field(..., ge=0, description="Actual cash counted")
    register_id: Optional[str] = Field(None, description="Register identifier")
    notes: Optional[str] = None


class RegisterStatusResponse(BaseModel):
    """Cash register status response."""
    register_id: str
    is_open: bool
    opened_at: Optional[str]
    opened_by: Optional[str]
    opening_balance: float
    expected_cash: float
    transaction_count: int
    total_sales: float
    total_refunds: float


class CloseRegisterResponse(BaseModel):
    """Response after closing register."""
    register_id: str
    closed_at: str
    closed_by: str
    opening_balance: float
    expected_cash: float
    actual_cash: float
    variance: float
    variance_percent: float
    transaction_count: int
    total_sales: float
    total_refunds: float
    shift_duration_hours: float
    message: str


@router.post(
    "/{entity_id}/sales/register/open",
    response_model=RegisterStatusResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Open cash register",
)
async def open_register(
    entity_id: UUID,
    request: OpenRegisterRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Open cash register for the shift.
    
    Records opening balance for end-of-day reconciliation.
    Only one register can be open per entity at a time.
    """
    from datetime import datetime
    import uuid
    
    await verify_entity_access(entity_id, current_user, db)
    
    service = SalesService(db)
    
    try:
        register_data = await service.open_register(
            entity_id=entity_id,
            user_id=current_user.id,
            opening_balance=Decimal(str(request.opening_balance)),
            register_id=request.register_id,
            notes=request.notes,
        )
        
        await db.commit()
        
        return RegisterStatusResponse(
            register_id=register_data.get("register_id", str(uuid.uuid4())),
            is_open=True,
            opened_at=datetime.now().isoformat(),
            opened_by=current_user.email,
            opening_balance=request.opening_balance,
            expected_cash=request.opening_balance,
            transaction_count=0,
            total_sales=0,
            total_refunds=0,
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to open register: {str(e)}",
        )


@router.get(
    "/{entity_id}/sales/register/status",
    response_model=RegisterStatusResponse,
    summary="Get register status",
)
async def get_register_status(
    entity_id: UUID,
    register_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get current status of the cash register."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = SalesService(db)
    
    try:
        status_data = await service.get_register_status(
            entity_id=entity_id,
            register_id=register_id,
        )
        
        return RegisterStatusResponse(
            register_id=status_data.get("register_id", "default"),
            is_open=status_data.get("is_open", False),
            opened_at=status_data.get("opened_at"),
            opened_by=status_data.get("opened_by"),
            opening_balance=status_data.get("opening_balance", 0),
            expected_cash=status_data.get("expected_cash", 0),
            transaction_count=status_data.get("transaction_count", 0),
            total_sales=status_data.get("total_sales", 0),
            total_refunds=status_data.get("total_refunds", 0),
        )
    except Exception:
        # Return closed status if no register found
        return RegisterStatusResponse(
            register_id=register_id or "default",
            is_open=False,
            opened_at=None,
            opened_by=None,
            opening_balance=0,
            expected_cash=0,
            transaction_count=0,
            total_sales=0,
            total_refunds=0,
        )


@router.post(
    "/{entity_id}/sales/register/close",
    response_model=CloseRegisterResponse,
    summary="Close cash register",
)
async def close_register(
    entity_id: UUID,
    request: CloseRegisterRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Close cash register and reconcile.
    
    Compares actual cash count against expected balance.
    Records variance for audit trail.
    Generates end-of-shift report.
    """
    from datetime import datetime
    
    await verify_entity_access(entity_id, current_user, db)
    
    service = SalesService(db)
    
    try:
        close_data = await service.close_register(
            entity_id=entity_id,
            user_id=current_user.id,
            actual_cash=Decimal(str(request.actual_cash)),
            register_id=request.register_id,
            notes=request.notes,
        )
        
        await db.commit()
        
        opening_balance = close_data.get("opening_balance", 0)
        expected_cash = close_data.get("expected_cash", 0)
        variance = request.actual_cash - expected_cash
        variance_percent = (variance / expected_cash * 100) if expected_cash > 0 else 0
        
        return CloseRegisterResponse(
            register_id=close_data.get("register_id", "default"),
            closed_at=datetime.now().isoformat(),
            closed_by=current_user.email,
            opening_balance=opening_balance,
            expected_cash=expected_cash,
            actual_cash=request.actual_cash,
            variance=variance,
            variance_percent=variance_percent,
            transaction_count=close_data.get("transaction_count", 0),
            total_sales=close_data.get("total_sales", 0),
            total_refunds=close_data.get("total_refunds", 0),
            shift_duration_hours=close_data.get("shift_duration_hours", 0),
            message="Register closed successfully" + 
                    (f". Variance of ₦{abs(variance):,.2f} recorded." if variance != 0 else ""),
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to close register: {str(e)}",
        )
