"""
Tekvwa Pro Audit - Customer Service

Business logic for customer management.
"""

import uuid
from typing import List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceStatus


class CustomerService:
    """Service for customer operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_customers_for_entity(
        self,
        entity_id: uuid.UUID,
        search: Optional[str] = None,
        include_inactive: bool = False,
    ) -> List[Customer]:
        """Get all customers for an entity."""
        query = select(Customer).where(Customer.entity_id == entity_id)
        
        if search:
            search_term = f"%{search}%"
            query = query.where(
                (Customer.name.ilike(search_term)) |
                (Customer.tin.ilike(search_term)) |
                (Customer.email.ilike(search_term))
            )
        
        if not include_inactive:
            query = query.where(Customer.is_active == True)
        
        query = query.order_by(Customer.name)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_customer_by_id(
        self,
        customer_id: uuid.UUID,
        entity_id: uuid.UUID,
    ) -> Optional[Customer]:
        """Get customer by ID."""
        result = await self.db.execute(
            select(Customer)
            .where(Customer.id == customer_id)
            .where(Customer.entity_id == entity_id)
        )
        return result.scalar_one_or_none()
    
    async def create_customer(
        self,
        entity_id: uuid.UUID,
        name: str,
        tin: Optional[str] = None,
        contact_person: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        address: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        is_business: bool = False,
        notes: Optional[str] = None,
    ) -> Customer:
        """Create a new customer."""
        customer = Customer(
            entity_id=entity_id,
            name=name,
            tin=tin,
            contact_person=contact_person,
            email=email,
            phone=phone,
            address=address,
            city=city,
            state=state,
            is_business=is_business,
            notes=notes,
            is_active=True,
        )
        
        self.db.add(customer)
        await self.db.commit()
        await self.db.refresh(customer)
        
        return customer
    
    async def update_customer(
        self,
        customer: Customer,
        **kwargs,
    ) -> Customer:
        """Update a customer."""
        for key, value in kwargs.items():
            if value is not None and hasattr(customer, key):
                setattr(customer, key, value)
        
        await self.db.commit()
        await self.db.refresh(customer)
        
        return customer
    
    async def delete_customer(self, customer: Customer) -> bool:
        """Soft delete a customer."""
        customer.is_active = False
        await self.db.commit()
        return True
    
    async def get_customer_stats(
        self,
        customer: Customer,
    ) -> dict:
        """Get customer statistics (invoiced, paid, outstanding)."""
        # Get invoice totals
        result = await self.db.execute(
            select(
                func.count(Invoice.id).label("count"),
                func.coalesce(func.sum(Invoice.total_amount), 0).label("total_invoiced"),
                func.coalesce(func.sum(Invoice.amount_paid), 0).label("total_paid"),
            )
            .where(Invoice.customer_id == customer.id)
        )
        
        row = result.one()
        
        total_invoiced = float(row.total_invoiced)
        total_paid = float(row.total_paid)
        
        return {
            "invoice_count": row.count,
            "total_invoiced": total_invoiced,
            "total_paid": total_paid,
            "outstanding_balance": total_invoiced - total_paid,
        }
