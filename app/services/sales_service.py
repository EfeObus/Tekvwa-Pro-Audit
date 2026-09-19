"""
Tekvwa Pro Audit - Sales Recording Service

Business logic for recording sales, integrating inventory with invoicing.
Provides robust sales recording with:
- Inventory-linked line items
- Customer management
- Real-time stock updates
- Multi-currency support
- Tax calculation (VAT, WHT)
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.customer import Customer
from app.models.inventory import InventoryItem, StockMovement, StockMovementType
from app.models.invoice import Invoice, InvoiceLineItem, InvoiceStatus, VATTreatment
from app.models.transaction import Transaction, TransactionType


@dataclass
class SaleLineItem:
    """Represents a line item in a sale."""
    inventory_item_id: Optional[uuid.UUID]
    description: str
    quantity: int
    unit_price: Decimal
    vat_rate: Decimal = Decimal("7.5")
    discount_percent: Decimal = Decimal("0")
    
    @property
    def subtotal(self) -> Decimal:
        """Calculate subtotal before VAT and discount."""
        return Decimal(str(self.quantity)) * self.unit_price
    
    @property
    def discount_amount(self) -> Decimal:
        """Calculate discount amount."""
        return self.subtotal * (self.discount_percent / Decimal("100"))
    
    @property
    def taxable_amount(self) -> Decimal:
        """Amount subject to VAT after discount."""
        return self.subtotal - self.discount_amount
    
    @property
    def vat_amount(self) -> Decimal:
        """Calculate VAT amount."""
        return self.taxable_amount * (self.vat_rate / Decimal("100"))
    
    @property
    def total(self) -> Decimal:
        """Calculate total including VAT."""
        return self.taxable_amount + self.vat_amount


@dataclass
class SalesSummary:
    """Summary of sales for a period."""
    total_sales: Decimal
    total_vat_collected: Decimal
    total_discount_given: Decimal
    sales_count: int
    top_products: List[Dict[str, Any]]
    top_customers: List[Dict[str, Any]]
    sales_by_category: Dict[str, Decimal]


class SalesService:
    """
    Service for sales recording and management.
    
    Integrates inventory items with invoicing for seamless sales recording.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # =========================================
    # INVENTORY ITEM LOOKUP (For Sales)
    # =========================================
    
    async def get_sellable_items(
        self,
        entity_id: uuid.UUID,
        search: Optional[str] = None,
        category: Optional[str] = None,
        in_stock_only: bool = True,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get inventory items available for sale.
        
        Returns items formatted for sales dropdown/autocomplete.
        """
        query = select(InventoryItem).where(
            and_(
                InventoryItem.entity_id == entity_id,
                InventoryItem.is_active == True,
            )
        )
        
        if in_stock_only:
            query = query.where(InventoryItem.quantity_on_hand > 0)
        
        if search:
            search_term = f"%{search.lower()}%"
            query = query.where(
                or_(
                    func.lower(InventoryItem.name).like(search_term),
                    func.lower(InventoryItem.sku).like(search_term),
                    func.lower(InventoryItem.barcode).like(search_term) if InventoryItem.barcode else False,
                )
            )
        
        if category:
            query = query.where(InventoryItem.category == category)
        
        query = query.order_by(InventoryItem.name).limit(limit)
        
        result = await self.db.execute(query)
        items = result.scalars().all()
        
        return [
            {
                "id": str(item.id),
                "sku": item.sku,
                "name": item.name,
                "description": item.description,
                "category": item.category,
                "unit_price": float(item.unit_price),
                "unit_cost": float(item.unit_cost),
                "quantity_available": item.quantity_on_hand,
                "unit_of_measure": item.unit_of_measure,
                "barcode": item.barcode,
                "is_low_stock": item.quantity_on_hand <= item.reorder_level,
            }
            for item in items
        ]
    
    async def get_item_by_barcode(
        self,
        entity_id: uuid.UUID,
        barcode: str,
    ) -> Optional[Dict[str, Any]]:
        """Get an inventory item by barcode scan."""
        result = await self.db.execute(
            select(InventoryItem).where(
                and_(
                    InventoryItem.entity_id == entity_id,
                    InventoryItem.barcode == barcode,
                    InventoryItem.is_active == True,
                )
            )
        )
        item = result.scalar_one_or_none()
        
        if not item:
            return None
        
        return {
            "id": str(item.id),
            "sku": item.sku,
            "name": item.name,
            "description": item.description,
            "unit_price": float(item.unit_price),
            "quantity_available": item.quantity_on_hand,
            "unit_of_measure": item.unit_of_measure,
        }
    
    async def get_inventory_categories(
        self,
        entity_id: uuid.UUID,
    ) -> List[str]:
        """Get all inventory categories for filtering."""
        result = await self.db.execute(
            select(InventoryItem.category)
            .where(
                and_(
                    InventoryItem.entity_id == entity_id,
                    InventoryItem.category.isnot(None),
                    InventoryItem.is_active == True,
                )
            )
            .distinct()
            .order_by(InventoryItem.category)
        )
        categories = result.scalars().all()
        return [c for c in categories if c]
    
    # =========================================
    # CUSTOMER LOOKUP (For Sales)
    # =========================================
    
    async def get_customers_for_dropdown(
        self,
        entity_id: uuid.UUID,
        search: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get customers formatted for dropdown/autocomplete.
        
        Includes key info needed during sales: name, TIN, payment terms.
        """
        query = select(Customer).where(
            and_(
                Customer.entity_id == entity_id,
                Customer.is_active == True,
            )
        )
        
        if search:
            search_term = f"%{search.lower()}%"
            query = query.where(
                or_(
                    func.lower(Customer.name).like(search_term),
                    func.lower(Customer.email).like(search_term) if Customer.email else False,
                    func.lower(Customer.tin).like(search_term) if Customer.tin else False,
                    func.lower(Customer.phone).like(search_term) if Customer.phone else False,
                )
            )
        
        query = query.order_by(Customer.name).limit(limit)
        
        result = await self.db.execute(query)
        customers = result.scalars().all()
        
        return [
            {
                "id": str(c.id),
                "name": c.name,
                "email": c.email,
                "phone": c.phone,
                "tin": c.tin,
                "address": c.address,
                "city": c.city,
                "state": c.state,
                "is_vat_registered": c.is_vat_registered,
                "payment_terms_days": c.payment_terms_days,
                "credit_limit": float(c.credit_limit) if c.credit_limit else None,
                "outstanding_balance": float(c.outstanding_balance) if hasattr(c, 'outstanding_balance') else 0,
                "is_business": c.is_business if hasattr(c, 'is_business') else bool(c.tin),
            }
            for c in customers
        ]
    
    async def quick_create_customer(
        self,
        entity_id: uuid.UUID,
        name: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        tin: Optional[str] = None,
        address: Optional[str] = None,
    ) -> Customer:
        """
        Quickly create a new customer during sales process.
        
        Minimal required fields for fast checkout.
        """
        customer = Customer(
            entity_id=entity_id,
            name=name,
            email=email,
            phone=phone,
            tin=tin,
            address=address,
            is_business=bool(tin),
            is_active=True,
        )
        
        self.db.add(customer)
        await self.db.flush()
        
        return customer
    
    # =========================================
    # SALES RECORDING
    # =========================================
    
    async def record_sale(
        self,
        entity_id: uuid.UUID,
        user_id: uuid.UUID,
        customer_id: Optional[uuid.UUID],
        line_items: List[SaleLineItem],
        sale_date: Optional[date] = None,
        payment_method: Optional[str] = None,
        reference: Optional[str] = None,
        notes: Optional[str] = None,
        create_invoice: bool = True,
        vat_treatment: VATTreatment = VATTreatment.STANDARD,
    ) -> Tuple[Optional[Invoice], List[Transaction]]:
        """
        Record a sale with inventory deduction.
        
        This method:
        1. Creates invoice (if requested)
        2. Creates income transaction(s)
        3. Deducts inventory stock
        4. Records stock movements
        
        Returns: (Invoice or None, list of Transactions)
        """
        sale_date = sale_date or date.today()
        transactions = []
        invoice = None
        
        # Calculate totals
        subtotal = sum(item.subtotal for item in line_items)
        total_discount = sum(item.discount_amount for item in line_items)
        total_vat = sum(item.vat_amount for item in line_items) if vat_treatment == VATTreatment.STANDARD else Decimal("0")
        grand_total = subtotal - total_discount + total_vat
        
        # Create Invoice
        if create_invoice:
            # Generate invoice number
            invoice_number = await self._generate_invoice_number(entity_id)
            due_date = sale_date  # Cash sale, or add customer payment terms
            
            if customer_id:
                customer = await self.db.get(Customer, customer_id)
                if customer:
                    from datetime import timedelta
                    due_date = sale_date + timedelta(days=customer.payment_terms_days)
            
            invoice = Invoice(
                entity_id=entity_id,
                customer_id=customer_id,
                invoice_number=invoice_number,
                invoice_date=sale_date,
                due_date=due_date,
                subtotal=subtotal,
                discount_amount=total_discount,
                vat_amount=total_vat,
                total_amount=grand_total,
                vat_treatment=vat_treatment,
                vat_rate=Decimal("7.5") if vat_treatment == VATTreatment.STANDARD else Decimal("0"),
                status=InvoiceStatus.DRAFT,
                notes=notes,
                created_by=user_id,
            )
            self.db.add(invoice)
            await self.db.flush()
            
            # Add line items
            for idx, item in enumerate(line_items, start=1):
                line = InvoiceLineItem(
                    invoice_id=invoice.id,
                    line_number=idx,
                    description=item.description,
                    quantity=int(item.quantity),
                    unit_price=item.unit_price,
                    vat_rate=item.vat_rate if vat_treatment == VATTreatment.STANDARD else Decimal("0"),
                    discount_percent=item.discount_percent,
                    subtotal=item.subtotal,
                    vat_amount=item.vat_amount if vat_treatment == VATTreatment.STANDARD else Decimal("0"),
                    total_amount=item.total if vat_treatment == VATTreatment.STANDARD else item.taxable_amount,
                )
                self.db.add(line)
        
        # Deduct inventory and create stock movements
        for item in line_items:
            if item.inventory_item_id:
                inv_item = await self.db.get(InventoryItem, item.inventory_item_id)
                if inv_item:
                    # Deduct stock
                    inv_item.quantity_on_hand = max(0, inv_item.quantity_on_hand - item.quantity)
                    
                    # Record stock movement
                    movement = StockMovement(
                        item_id=inv_item.id,
                        movement_type=StockMovementType.SALE,
                        quantity=-item.quantity,  # Negative for outbound
                        unit_cost=inv_item.unit_cost,
                        reference=invoice.invoice_number if invoice else reference,
                        notes=f"Sale: {item.description}",
                        movement_date=sale_date,
                        created_by=user_id,
                    )
                    self.db.add(movement)
        
        # Create income transaction
        transaction = Transaction(
            entity_id=entity_id,
            transaction_date=sale_date,
            transaction_type=TransactionType.INCOME,
            description=f"Sale: {reference or (invoice.invoice_number if invoice else 'Cash Sale')}",
            amount=subtotal - total_discount,
            vat_amount=total_vat,
            vat_rate=Decimal("7.5") if vat_treatment == VATTreatment.STANDARD else Decimal("0"),
            vat_treatment=vat_treatment,
            reference=invoice.invoice_number if invoice else reference,
            customer_id=customer_id,
            invoice_id=invoice.id if invoice else None,
            created_by=user_id,
        )
        self.db.add(transaction)
        transactions.append(transaction)
        
        await self.db.commit()
        
        return invoice, transactions
    
    async def _generate_invoice_number(self, entity_id: uuid.UUID) -> str:
        """Generate next invoice number for entity."""
        result = await self.db.execute(
            select(func.count(Invoice.id))
            .where(Invoice.entity_id == entity_id)
        )
        count = result.scalar() or 0
        
        # Format: INV-YYYYMMDD-XXXX
        today = date.today()
        return f"INV-{today.strftime('%Y%m%d')}-{count + 1:04d}"
    
    # =========================================
    # SALES REPORTS
    # =========================================
    
    async def get_sales_summary(
        self,
        entity_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> SalesSummary:
        """Get sales summary for a date range."""
        # Get total sales
        result = await self.db.execute(
            select(
                func.sum(Invoice.total_amount),
                func.sum(Invoice.vat_amount),
                func.sum(Invoice.discount_amount),
                func.count(Invoice.id),
            )
            .where(
                and_(
                    Invoice.entity_id == entity_id,
                    Invoice.invoice_date >= start_date,
                    Invoice.invoice_date <= end_date,
                    Invoice.status != InvoiceStatus.CANCELLED,
                )
            )
        )
        row = result.fetchone()
        
        total_sales = row[0] or Decimal("0")
        total_vat = row[1] or Decimal("0")
        total_discount = row[2] or Decimal("0")
        sales_count = row[3] or 0
        
        # Get top products (by quantity sold)
        top_products_query = (
            select(
                InvoiceLineItem.description,
                func.sum(InvoiceLineItem.quantity).label('total_qty'),
                func.sum(InvoiceLineItem.total).label('total_revenue'),
            )
            .join(Invoice, Invoice.id == InvoiceLineItem.invoice_id)
            .where(
                and_(
                    Invoice.entity_id == entity_id,
                    Invoice.invoice_date >= start_date,
                    Invoice.invoice_date <= end_date,
                    Invoice.status != InvoiceStatus.CANCELLED,
                )
            )
            .group_by(InvoiceLineItem.description)
            .order_by(func.sum(InvoiceLineItem.total).desc())
            .limit(10)
        )
        result = await self.db.execute(top_products_query)
        top_products = [
            {"name": r[0], "quantity": int(r[1]), "revenue": float(r[2])}
            for r in result.fetchall()
        ]
        
        # Get top customers
        top_customers_query = (
            select(
                Customer.name,
                func.sum(Invoice.total_amount).label('total_spent'),
                func.count(Invoice.id).label('order_count'),
            )
            .join(Invoice, Invoice.customer_id == Customer.id)
            .where(
                and_(
                    Invoice.entity_id == entity_id,
                    Invoice.invoice_date >= start_date,
                    Invoice.invoice_date <= end_date,
                    Invoice.status != InvoiceStatus.CANCELLED,
                )
            )
            .group_by(Customer.id, Customer.name)
            .order_by(func.sum(Invoice.total_amount).desc())
            .limit(10)
        )
        result = await self.db.execute(top_customers_query)
        top_customers = [
            {"name": r[0], "total_spent": float(r[1]), "order_count": int(r[2])}
            for r in result.fetchall()
        ]
        
        return SalesSummary(
            total_sales=total_sales,
            total_vat_collected=total_vat,
            total_discount_given=total_discount,
            sales_count=sales_count,
            top_products=top_products,
            top_customers=top_customers,
            sales_by_category={},  # Can be extended
        )
    
    async def get_recent_sales(
        self,
        entity_id: uuid.UUID,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get recent sales/invoices."""
        result = await self.db.execute(
            select(Invoice)
            .options(selectinload(Invoice.customer))
            .where(Invoice.entity_id == entity_id)
            .order_by(Invoice.created_at.desc())
            .limit(limit)
        )
        invoices = result.scalars().all()
        
        return [
            {
                "id": str(inv.id),
                "invoice_number": inv.invoice_number,
                "customer_name": inv.customer.name if inv.customer else "Walk-in Customer",
                "invoice_date": inv.invoice_date.isoformat(),
                "total_amount": float(inv.total_amount),
                "status": inv.status.value,
                "payment_status": "Paid" if inv.status == InvoiceStatus.PAID else "Pending",
            }
            for inv in invoices
        ]
