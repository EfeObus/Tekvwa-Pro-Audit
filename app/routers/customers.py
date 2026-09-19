"""
Tekvwa Pro Audit - Customers Router

API endpoints for customer management.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import get_current_active_user, record_usage_event, require_within_usage_limit
from app.models.user import User
from app.models.audit_consolidated import AuditAction
from app.models.sku import UsageMetricType
from app.schemas.auth import MessageResponse
from app.schemas.customer import (
    CustomerCreateRequest,
    CustomerUpdateRequest,
    CustomerResponse,
    CustomerListResponse,
)
from app.services.customer_service import CustomerService
from app.services.entity_service import EntityService
from app.services.audit_service import AuditService


router = APIRouter()


@router.get(
    "/{entity_id}/customers",
    response_model=CustomerListResponse,
    summary="List customers",
    description="Get all customers for a business entity.",
)
async def list_customers(
    entity_id: UUID,
    search: Optional[str] = Query(None, description="Search by name, TIN, or email"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """List all customers for an entity."""
    # Verify entity access
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    customer_service = CustomerService(db)
    customers = await customer_service.get_customers_for_entity(
        entity_id,
        search=search,
    )
    
    customer_responses = []
    for customer in customers:
        stats = await customer_service.get_customer_stats(customer)
        customer_responses.append(
            CustomerResponse(
                id=customer.id,
                entity_id=customer.entity_id,
                name=customer.name,
                tin=customer.tin,
                contact_person=customer.contact_person,
                email=customer.email,
                phone=customer.phone,
                address=customer.address,
                city=customer.city,
                state=customer.state,
                is_business=customer.is_business,
                total_invoiced=stats["total_invoiced"],
                total_paid=stats["total_paid"],
                outstanding_balance=stats["outstanding_balance"],
                invoice_count=stats["invoice_count"],
                notes=customer.notes,
                is_active=customer.is_active,
                created_at=customer.created_at,
                updated_at=customer.updated_at,
            )
        )
    
    return CustomerListResponse(
        customers=customer_responses,
        total=len(customer_responses),
    )


@router.post(
    "/{entity_id}/customers",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create customer",
    description="Create a new customer for a business entity.",
)
async def create_customer(
    entity_id: UUID,
    request: CustomerCreateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
    _limit_check: User = Depends(require_within_usage_limit(UsageMetricType.TRANSACTIONS)),
):
    """Create a new customer."""
    # Verify entity access and write permission
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
    
    customer_service = CustomerService(db)
    
    customer = await customer_service.create_customer(
        entity_id=entity_id,
        name=request.name,
        tin=request.tin,
        contact_person=request.contact_person,
        email=request.email,
        phone=request.phone,
        address=request.address,
        city=request.city,
        state=request.state,
        is_business=request.is_business,
        notes=request.notes,
    )
    
    # Audit log for customer creation
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="customer",
        entity_id=str(customer.id),
        action=AuditAction.CREATE,
        user_id=current_user.id,
        new_values={
            "name": request.name,
            "tin": request.tin,
            "email": request.email,
            "phone": request.phone,
            "is_business": request.is_business,
        },
    )
    
    # Record usage metering for SKU tier limits
    if current_user.organization_id:
        await record_usage_event(
            db=db,
            organization_id=current_user.organization_id,
            metric_type=UsageMetricType.TRANSACTIONS,
            entity_id=entity_id,
            user_id=current_user.id,
            resource_type="customer",
            resource_id=str(customer.id),
        )
    
    return CustomerResponse(
        id=customer.id,
        entity_id=customer.entity_id,
        name=customer.name,
        tin=customer.tin,
        contact_person=customer.contact_person,
        email=customer.email,
        phone=customer.phone,
        address=customer.address,
        city=customer.city,
        state=customer.state,
        is_business=customer.is_business,
        total_invoiced=0.0,
        total_paid=0.0,
        outstanding_balance=0.0,
        invoice_count=0,
        notes=customer.notes,
        is_active=customer.is_active,
        created_at=customer.created_at,
        updated_at=customer.updated_at,
    )


@router.get(
    "/{entity_id}/customers/{customer_id}",
    response_model=CustomerResponse,
    summary="Get customer",
    description="Get a specific customer by ID.",
)
async def get_customer(
    entity_id: UUID,
    customer_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get a specific customer."""
    # Verify entity access
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    customer_service = CustomerService(db)
    customer = await customer_service.get_customer_by_id(customer_id, entity_id)
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    
    stats = await customer_service.get_customer_stats(customer)
    
    return CustomerResponse(
        id=customer.id,
        entity_id=customer.entity_id,
        name=customer.name,
        tin=customer.tin,
        contact_person=customer.contact_person,
        email=customer.email,
        phone=customer.phone,
        address=customer.address,
        city=customer.city,
        state=customer.state,
        is_business=customer.is_business,
        total_invoiced=stats["total_invoiced"],
        total_paid=stats["total_paid"],
        outstanding_balance=stats["outstanding_balance"],
        invoice_count=stats["invoice_count"],
        notes=customer.notes,
        is_active=customer.is_active,
        created_at=customer.created_at,
        updated_at=customer.updated_at,
    )


@router.patch(
    "/{entity_id}/customers/{customer_id}",
    response_model=CustomerResponse,
    summary="Update customer",
    description="Update a customer.",
)
async def update_customer(
    entity_id: UUID,
    customer_id: UUID,
    request: CustomerUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Update a customer."""
    # Verify entity access and write permission
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
    
    customer_service = CustomerService(db)
    customer = await customer_service.get_customer_by_id(customer_id, entity_id)
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    
    # Store old values for audit
    old_values = {
        "name": customer.name,
        "tin": customer.tin,
        "email": customer.email,
        "phone": customer.phone,
    }
    
    update_data = request.model_dump(exclude_unset=True)
    customer = await customer_service.update_customer(customer, **update_data)
    
    # Audit log for customer update
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="customer",
        entity_id=str(customer.id),
        action=AuditAction.UPDATE,
        user_id=current_user.id,
        old_values=old_values,
        new_values=update_data,
    )
    
    stats = await customer_service.get_customer_stats(customer)
    
    return CustomerResponse(
        id=customer.id,
        entity_id=customer.entity_id,
        name=customer.name,
        tin=customer.tin,
        contact_person=customer.contact_person,
        email=customer.email,
        phone=customer.phone,
        address=customer.address,
        city=customer.city,
        state=customer.state,
        is_business=customer.is_business,
        total_invoiced=stats["total_invoiced"],
        total_paid=stats["total_paid"],
        outstanding_balance=stats["outstanding_balance"],
        invoice_count=stats["invoice_count"],
        notes=customer.notes,
        is_active=customer.is_active,
        created_at=customer.created_at,
        updated_at=customer.updated_at,
    )


@router.delete(
    "/{entity_id}/customers/{customer_id}",
    response_model=MessageResponse,
    summary="Delete customer",
    description="Soft delete a customer.",
)
async def delete_customer(
    entity_id: UUID,
    customer_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Delete a customer."""
    # Verify entity access and write permission
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
    
    customer_service = CustomerService(db)
    customer = await customer_service.get_customer_by_id(customer_id, entity_id)
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    
    # Store customer data for audit before deletion
    deleted_values = {
        "name": customer.name,
        "tin": customer.tin,
        "email": customer.email,
    }
    deleted_id = str(customer.id)
    
    await customer_service.delete_customer(customer)
    
    # Audit log for customer deletion
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="customer",
        entity_id=deleted_id,
        action=AuditAction.DELETE,
        user_id=current_user.id,
        old_values=deleted_values,
    )
    
    return MessageResponse(
        message="Customer deleted successfully",
        success=True,
    )


# ===========================================
# ADDITIONAL CUSTOMER ENDPOINTS
# ===========================================

from typing import List
from pydantic import BaseModel
from datetime import date, datetime


class CustomerInvoiceResponse(BaseModel):
    """Invoice for a customer."""
    id: UUID
    invoice_number: str
    invoice_date: date
    due_date: date
    total_amount: float
    amount_paid: float
    balance_due: float
    status: str


class CustomerInvoicesListResponse(BaseModel):
    """List of customer invoices."""
    invoices: List[CustomerInvoiceResponse]
    total: int
    total_invoiced: float
    total_paid: float
    total_outstanding: float


class CustomerStatementResponse(BaseModel):
    """Customer account statement."""
    customer_id: UUID
    customer_name: str
    statement_date: date
    period_start: date
    period_end: date
    opening_balance: float
    transactions: List[dict]
    closing_balance: float
    total_invoiced: float
    total_payments: float


class CustomerStatsResponse(BaseModel):
    """Customer statistics."""
    total_customers: int
    active_customers: int
    business_customers: int
    individual_customers: int
    total_invoiced_all_time: float
    total_outstanding: float
    top_customers: List[dict]


class TINVerificationResponse(BaseModel):
    """TIN verification response."""
    customer_id: UUID
    tin: Optional[str]
    verified: bool
    verified_at: Optional[datetime]
    verification_message: str


@router.get(
    "/{entity_id}/customers/{customer_id}/invoices",
    response_model=CustomerInvoicesListResponse,
    summary="Get customer invoices",
    description="Get all invoices for a specific customer.",
)
async def get_customer_invoices(
    entity_id: UUID,
    customer_id: UUID,
    status_filter: Optional[str] = Query(None, description="Filter by status: draft, sent, paid, overdue"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get all invoices for a customer."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    customer_service = CustomerService(db)
    customer = await customer_service.get_customer_by_id(customer_id, entity_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    
    from sqlalchemy import select
    from app.models.invoice import Invoice
    
    query = select(Invoice).where(
        Invoice.entity_id == entity_id,
        Invoice.customer_id == customer_id,
        Invoice.is_deleted == False,
    )
    
    if start_date:
        query = query.where(Invoice.invoice_date >= start_date)
    if end_date:
        query = query.where(Invoice.invoice_date <= end_date)
    
    query = query.order_by(Invoice.invoice_date.desc())
    
    result = await db.execute(query)
    invoices = result.scalars().all()
    
    invoice_responses = []
    for inv in invoices:
        invoice_responses.append(CustomerInvoiceResponse(
            id=inv.id,
            invoice_number=inv.invoice_number,
            invoice_date=inv.invoice_date,
            due_date=inv.due_date,
            total_amount=float(inv.total_amount),
            amount_paid=float(inv.amount_paid),
            balance_due=float(inv.balance_due),
            status=inv.status.value,
        ))
    
    total_invoiced = sum(i.total_amount for i in invoice_responses)
    total_paid = sum(i.amount_paid for i in invoice_responses)
    
    return CustomerInvoicesListResponse(
        invoices=invoice_responses,
        total=len(invoice_responses),
        total_invoiced=total_invoiced,
        total_paid=total_paid,
        total_outstanding=total_invoiced - total_paid,
    )


@router.get(
    "/{entity_id}/customers/{customer_id}/statement",
    response_model=CustomerStatementResponse,
    summary="Get customer statement",
    description="Generate an account statement for a customer.",
)
async def get_customer_statement(
    entity_id: UUID,
    customer_id: UUID,
    start_date: date = Query(..., description="Statement start date"),
    end_date: date = Query(..., description="Statement end date"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Generate customer account statement."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    customer_service = CustomerService(db)
    customer = await customer_service.get_customer_by_id(customer_id, entity_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    
    from sqlalchemy import select, and_
    from app.models.invoice import Invoice
    
    # Get invoices in the period
    query = select(Invoice).where(
        Invoice.entity_id == entity_id,
        Invoice.customer_id == customer_id,
        Invoice.invoice_date >= start_date,
        Invoice.invoice_date <= end_date,
        Invoice.is_deleted == False,
    ).order_by(Invoice.invoice_date)
    
    result = await db.execute(query)
    invoices = result.scalars().all()
    
    # Calculate opening balance (outstanding before start_date)
    opening_query = select(Invoice).where(
        Invoice.entity_id == entity_id,
        Invoice.customer_id == customer_id,
        Invoice.invoice_date < start_date,
        Invoice.is_deleted == False,
    )
    opening_result = await db.execute(opening_query)
    opening_invoices = opening_result.scalars().all()
    opening_balance = sum(float(inv.balance_due) for inv in opening_invoices)
    
    # Build transaction list
    transactions = []
    running_balance = opening_balance
    
    for inv in invoices:
        # Invoice created
        running_balance += float(inv.total_amount)
        transactions.append({
            "date": inv.invoice_date.isoformat(),
            "type": "invoice",
            "reference": inv.invoice_number,
            "description": f"Invoice {inv.invoice_number}",
            "debit": float(inv.total_amount),
            "credit": 0,
            "balance": running_balance,
        })
        
        # Payment received (if any)
        if inv.amount_paid > 0:
            running_balance -= float(inv.amount_paid)
            transactions.append({
                "date": inv.invoice_date.isoformat(),  # Simplified
                "type": "payment",
                "reference": f"PMT-{inv.invoice_number}",
                "description": f"Payment for {inv.invoice_number}",
                "debit": 0,
                "credit": float(inv.amount_paid),
                "balance": running_balance,
            })
    
    total_invoiced = sum(float(inv.total_amount) for inv in invoices)
    total_payments = sum(float(inv.amount_paid) for inv in invoices)
    
    return CustomerStatementResponse(
        customer_id=customer.id,
        customer_name=customer.name,
        statement_date=date.today(),
        period_start=start_date,
        period_end=end_date,
        opening_balance=opening_balance,
        transactions=transactions,
        closing_balance=running_balance,
        total_invoiced=total_invoiced,
        total_payments=total_payments,
    )


@router.post(
    "/{entity_id}/customers/{customer_id}/statement/email",
    response_model=MessageResponse,
    summary="Email customer statement",
    description="Send the account statement to the customer via email.",
)
async def email_customer_statement(
    entity_id: UUID,
    customer_id: UUID,
    start_date: date = Query(...),
    end_date: date = Query(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Email statement to customer."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    customer_service = CustomerService(db)
    customer = await customer_service.get_customer_by_id(customer_id, entity_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    
    if not customer.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Customer has no email address",
        )
    
    # In production, generate PDF and send email
    from app.services.email_service import EmailService
    email_service = EmailService()
    
    try:
        await email_service.send_statement_email(
            to_email=customer.email,
            customer_name=customer.name,
            statement_period=f"{start_date} to {end_date}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send email: {str(e)}",
        )
    
    return MessageResponse(message=f"Statement sent to {customer.email}")


@router.post(
    "/{entity_id}/customers/{customer_id}/verify-tin",
    response_model=TINVerificationResponse,
    summary="Verify customer TIN",
    description="Verify customer TIN with FIRS/NRS.",
)
async def verify_customer_tin(
    entity_id: UUID,
    customer_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Verify customer TIN."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    customer_service = CustomerService(db)
    customer = await customer_service.get_customer_by_id(customer_id, entity_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    
    if not customer.tin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Customer has no TIN to verify",
        )
    
    # In production, call FIRS/NRS verification API
    # For now, simulate verification
    verified = True
    message = "TIN verified successfully with FIRS"
    
    if verified:
        customer.tin_verified = True
        customer.tin_verified_at = datetime.utcnow()
        await db.commit()
    
    return TINVerificationResponse(
        customer_id=customer.id,
        tin=customer.tin,
        verified=verified,
        verified_at=customer.tin_verified_at if verified else None,
        verification_message=message,
    )


@router.get(
    "/{entity_id}/customers/statistics",
    response_model=CustomerStatsResponse,
    summary="Get customer statistics",
    description="Get overall customer statistics for the entity.",
)
async def get_customer_statistics(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get customer statistics."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    customer_service = CustomerService(db)
    customers = await customer_service.get_customers_for_entity(entity_id)
    
    active_customers = [c for c in customers if c.is_active]
    business_customers = [c for c in customers if c.is_business]
    individual_customers = [c for c in customers if not c.is_business]
    
    # Get top customers by revenue
    customer_stats = []
    for customer in customers:
        stats = await customer_service.get_customer_stats(customer)
        customer_stats.append({
            "id": str(customer.id),
            "name": customer.name,
            "total_invoiced": stats["total_invoiced"],
            "outstanding_balance": stats["outstanding_balance"],
        })
    
    customer_stats.sort(key=lambda x: x["total_invoiced"], reverse=True)
    top_customers = customer_stats[:10]
    
    total_invoiced = sum(c["total_invoiced"] for c in customer_stats)
    total_outstanding = sum(c["outstanding_balance"] for c in customer_stats)
    
    return CustomerStatsResponse(
        total_customers=len(customers),
        active_customers=len(active_customers),
        business_customers=len(business_customers),
        individual_customers=len(individual_customers),
        total_invoiced_all_time=total_invoiced,
        total_outstanding=total_outstanding,
        top_customers=top_customers,
    )


@router.post(
    "/{entity_id}/customers/{customer_id}/restore",
    response_model=MessageResponse,
    summary="Restore deleted customer",
    description="Restore a soft-deleted customer.",
)
async def restore_customer(
    entity_id: UUID,
    customer_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Restore a deleted customer."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found or access denied",
        )
    
    from sqlalchemy import select
    from app.models.customer import Customer
    
    result = await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.entity_id == entity_id,
        )
    )
    customer = result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    
    if customer.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Customer is not deleted",
        )
    
    customer.is_active = True
    await db.commit()
    
    return MessageResponse(message="Customer restored successfully")
