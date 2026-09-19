"""
Tekvwa Pro Audit - Invoice Service

Business logic for invoice management with NRS e-invoicing support.
Includes full GL integration for double-entry accounting.
Multi-currency support with IAS 21 compliance.
"""

import json
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Tuple, Dict, Any, TYPE_CHECKING

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.invoice import Invoice, InvoiceLineItem, InvoiceStatus, VATTreatment
from app.models.customer import Customer
from app.models.entity import BusinessEntity
from app.models.accounting import ChartOfAccounts, AccountType

if TYPE_CHECKING:
    from app.services.accounting_service import AccountingService
    from app.services.fx_service import FXService


# ===========================================
# GL ACCOUNT CODES (Nigerian Standard COA)
# ===========================================
GL_ACCOUNTS = {
    # Assets
    "ACCOUNTS_RECEIVABLE": "1130",
    "BANK": "1120",
    "WHT_RECEIVABLE": "1170",
    "VAT_RECEIVABLE": "1160",
    # Liabilities
    "VAT_PAYABLE": "2130",
    "WHT_PAYABLE": "2140",
    # Revenue
    "SALES_REVENUE": "4100",
    "SERVICE_REVENUE": "4200",
    "INTEREST_INCOME": "4300",
}


class InvoiceService:
    """Service for invoice operations."""
    
    # NRS dispute window (72 hours)
    DISPUTE_WINDOW_HOURS = 72
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # ===========================================
    # INVOICE NUMBER GENERATION
    # ===========================================
    
    async def generate_invoice_number(self, entity_id: uuid.UUID) -> str:
        """
        Generate unique invoice number for entity.
        
        Format: INV-YYYYMM-NNNN (e.g., INV-202601-0001)
        """
        today = date.today()
        prefix = f"INV-{today.year}{today.month:02d}"
        
        # Get count of invoices for this month
        result = await self.db.execute(
            select(func.count(Invoice.id))
            .where(Invoice.entity_id == entity_id)
            .where(Invoice.invoice_number.like(f"{prefix}%"))
        )
        count = result.scalar() or 0
        
        # Generate next number
        next_number = count + 1
        return f"{prefix}-{next_number:04d}"
    
    # ===========================================
    # CRUD OPERATIONS
    # ===========================================
    
    async def get_invoices_for_entity(
        self,
        entity_id: uuid.UUID,
        status: Optional[InvoiceStatus] = None,
        customer_id: Optional[uuid.UUID] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        is_overdue: Optional[bool] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Invoice], int]:
        """Get invoices for an entity with filters."""
        query = (
            select(Invoice)
            .options(
                selectinload(Invoice.customer),
                selectinload(Invoice.line_items),
            )
            .where(Invoice.entity_id == entity_id)
        )
        
        # Apply filters
        if status:
            query = query.where(Invoice.status == status)
        
        if customer_id:
            query = query.where(Invoice.customer_id == customer_id)
        
        if start_date:
            query = query.where(Invoice.invoice_date >= start_date)
        
        if end_date:
            query = query.where(Invoice.invoice_date <= end_date)
        
        if is_overdue is True:
            today = date.today()
            query = query.where(
                and_(
                    Invoice.due_date < today,
                    Invoice.status.not_in([InvoiceStatus.PAID, InvoiceStatus.CANCELLED])
                )
            )
        
        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    Invoice.invoice_number.ilike(search_term),
                    Invoice.notes.ilike(search_term),
                )
            )
        
        # Count total
        count_query = (
            select(func.count(Invoice.id))
            .where(Invoice.entity_id == entity_id)
        )
        if status:
            count_query = count_query.where(Invoice.status == status)
        if customer_id:
            count_query = count_query.where(Invoice.customer_id == customer_id)
        
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0
        
        # Pagination
        offset = (page - 1) * page_size
        query = query.order_by(Invoice.invoice_date.desc(), Invoice.created_at.desc())
        query = query.limit(page_size).offset(offset)
        
        result = await self.db.execute(query)
        invoices = list(result.scalars().all())
        
        return invoices, total
    
    async def get_invoice_by_id(
        self,
        invoice_id: uuid.UUID,
        entity_id: uuid.UUID,
    ) -> Optional[Invoice]:
        """Get invoice by ID."""
        result = await self.db.execute(
            select(Invoice)
            .options(
                selectinload(Invoice.customer),
                selectinload(Invoice.line_items),
            )
            .where(Invoice.id == invoice_id)
            .where(Invoice.entity_id == entity_id)
        )
        return result.scalar_one_or_none()
    
    async def get_invoice_by_number(
        self,
        invoice_number: str,
        entity_id: uuid.UUID,
    ) -> Optional[Invoice]:
        """Get invoice by invoice number."""
        result = await self.db.execute(
            select(Invoice)
            .options(
                selectinload(Invoice.customer),
                selectinload(Invoice.line_items),
            )
            .where(Invoice.invoice_number == invoice_number)
            .where(Invoice.entity_id == entity_id)
        )
        return result.scalar_one_or_none()
    
    async def create_invoice(
        self,
        entity_id: uuid.UUID,
        user_id: uuid.UUID,
        invoice_date: date,
        due_date: date,
        line_items_data: List[dict],
        customer_id: Optional[uuid.UUID] = None,
        vat_treatment: VATTreatment = VATTreatment.STANDARD,
        vat_rate: float = 7.5,
        discount_amount: float = 0,
        notes: Optional[str] = None,
        terms: Optional[str] = None,
        currency: str = "NGN",
        exchange_rate: Optional[float] = None,
        exchange_rate_source: Optional[str] = None,
    ) -> Invoice:
        """
        Create a new invoice with line items.
        
        Multi-Currency Support (IAS 21):
        - currency: Invoice currency (NGN, USD, EUR, GBP)
        - exchange_rate: Rate at invoice date (1 FC = X NGN). Auto-fetched if not provided.
        - exchange_rate_source: Rate source (CBN, manual, spot, contract)
        """
        # Generate invoice number
        invoice_number = await self.generate_invoice_number(entity_id)
        
        # Handle exchange rate for foreign currency invoices
        final_exchange_rate = Decimal("1.000000")
        final_rate_source = exchange_rate_source
        
        if currency != "NGN":
            if exchange_rate is not None:
                final_exchange_rate = Decimal(str(exchange_rate))
                final_rate_source = exchange_rate_source or "manual"
            else:
                # Auto-fetch rate from FXService
                from app.services.fx_service import FXService
                fx_service = FXService(self.db)
                fetched_rate = await fx_service.get_exchange_rate(
                    from_currency=currency,
                    to_currency="NGN",
                    rate_date=invoice_date
                )
                if fetched_rate is None:
                    raise ValueError(
                        f"No exchange rate found for {currency}/NGN on {invoice_date}. "
                        f"Please provide an exchange rate or add the rate to the system."
                    )
                final_exchange_rate = fetched_rate
                final_rate_source = "system"
        
        # Calculate totals in original currency
        subtotal = Decimal("0")
        total_vat = Decimal("0")
        
        for item in line_items_data:
            item_subtotal = Decimal(str(item['quantity'])) * Decimal(str(item['unit_price']))
            item_vat = Decimal("0")
            
            if vat_treatment == VATTreatment.STANDARD:
                item_vat = item_subtotal * (Decimal(str(item.get('vat_rate', vat_rate))) / 100)
            
            subtotal += item_subtotal
            total_vat += item_vat
        
        total_amount = subtotal + total_vat - Decimal(str(discount_amount))
        
        # Calculate functional currency amounts (NGN) - IAS 21
        functional_subtotal = (subtotal * final_exchange_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        functional_vat_amount = (total_vat * final_exchange_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        functional_total_amount = (total_amount * final_exchange_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        
        # Create invoice with FX fields
        invoice = Invoice(
            entity_id=entity_id,
            invoice_number=invoice_number,
            customer_id=customer_id,
            invoice_date=invoice_date,
            due_date=due_date,
            # Original currency amounts
            currency=currency,
            exchange_rate=final_exchange_rate,
            exchange_rate_source=final_rate_source,
            subtotal=subtotal,
            vat_amount=total_vat,
            discount_amount=Decimal(str(discount_amount)),
            total_amount=total_amount,
            # Functional currency amounts (NGN)
            functional_subtotal=functional_subtotal,
            functional_vat_amount=functional_vat_amount,
            functional_total_amount=functional_total_amount,
            functional_amount_paid=Decimal("0.00"),
            # FX gain/loss tracking
            realized_fx_gain_loss=Decimal("0.00"),
            unrealized_fx_gain_loss=Decimal("0.00"),
            # Other fields
            vat_treatment=vat_treatment,
            vat_rate=Decimal(str(vat_rate)),
            status=InvoiceStatus.DRAFT,
            notes=notes,
            terms=terms,
            created_by=user_id,
            updated_by=user_id,
        )
        
        self.db.add(invoice)
        await self.db.flush()  # Get the invoice ID
        
        # Create line items
        for idx, item_data in enumerate(line_items_data):
            item_subtotal = Decimal(str(item_data['quantity'])) * Decimal(str(item_data['unit_price']))
            item_vat = Decimal("0")
            
            if vat_treatment == VATTreatment.STANDARD:
                item_vat = item_subtotal * (Decimal(str(item_data.get('vat_rate', vat_rate))) / 100)
            
            line_item = InvoiceLineItem(
                invoice_id=invoice.id,
                description=item_data['description'],
                quantity=Decimal(str(item_data['quantity'])),
                unit_price=Decimal(str(item_data['unit_price'])),
                subtotal=item_subtotal,
                vat_amount=item_vat,
                total=item_subtotal + item_vat,
                sort_order=idx,
            )
            self.db.add(line_item)
        
        await self.db.commit()
        await self.db.refresh(invoice)
        
        # Load relationships
        return await self.get_invoice_by_id(invoice.id, entity_id)
    
    async def update_invoice(
        self,
        invoice_id: uuid.UUID,
        entity_id: uuid.UUID,
        user_id: uuid.UUID,
        **update_data,
    ) -> Optional[Invoice]:
        """Update an invoice (only if in DRAFT status)."""
        invoice = await self.get_invoice_by_id(invoice_id, entity_id)
        
        if not invoice:
            return None
        
        if invoice.status != InvoiceStatus.DRAFT:
            raise ValueError("Can only update invoices in DRAFT status")
        
        # Update fields
        allowed_fields = [
            'customer_id', 'invoice_date', 'due_date',
            'vat_treatment', 'vat_rate', 'discount_amount',
            'notes', 'terms'
        ]
        
        for field in allowed_fields:
            if field in update_data and update_data[field] is not None:
                setattr(invoice, field, update_data[field])
        
        invoice.updated_by = user_id
        
        await self.db.commit()
        await self.db.refresh(invoice)
        
        return invoice
    
    async def delete_invoice(
        self,
        invoice_id: uuid.UUID,
        entity_id: uuid.UUID,
    ) -> bool:
        """Delete an invoice (only if in DRAFT status)."""
        invoice = await self.get_invoice_by_id(invoice_id, entity_id)
        
        if not invoice:
            return False
        
        if invoice.status != InvoiceStatus.DRAFT:
            raise ValueError("Can only delete invoices in DRAFT status")
        
        await self.db.delete(invoice)
        await self.db.commit()
        
        return True
    
    # ===========================================
    # LINE ITEM OPERATIONS
    # ===========================================
    
    async def add_line_item(
        self,
        invoice_id: uuid.UUID,
        entity_id: uuid.UUID,
        user_id: uuid.UUID,
        description: str,
        quantity: float,
        unit_price: float,
        vat_rate: float = 7.5,
    ) -> Invoice:
        """Add a line item to an invoice."""
        invoice = await self.get_invoice_by_id(invoice_id, entity_id)
        
        if not invoice:
            raise ValueError("Invoice not found")
        
        if invoice.status != InvoiceStatus.DRAFT:
            raise ValueError("Can only modify invoices in DRAFT status")
        
        # Calculate line item totals
        item_subtotal = Decimal(str(quantity)) * Decimal(str(unit_price))
        item_vat = Decimal("0")
        
        if invoice.vat_treatment == VATTreatment.STANDARD:
            item_vat = item_subtotal * (Decimal(str(vat_rate)) / 100)
        
        # Get next sort order
        max_order = max([li.sort_order for li in invoice.line_items], default=-1)
        
        line_item = InvoiceLineItem(
            invoice_id=invoice.id,
            description=description,
            quantity=Decimal(str(quantity)),
            unit_price=Decimal(str(unit_price)),
            subtotal=item_subtotal,
            vat_amount=item_vat,
            total=item_subtotal + item_vat,
            sort_order=max_order + 1,
        )
        
        self.db.add(line_item)
        
        # Recalculate invoice totals
        await self._recalculate_invoice_totals(invoice, user_id)
        
        return await self.get_invoice_by_id(invoice_id, entity_id)
    
    async def remove_line_item(
        self,
        invoice_id: uuid.UUID,
        line_item_id: uuid.UUID,
        entity_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Invoice:
        """Remove a line item from an invoice."""
        invoice = await self.get_invoice_by_id(invoice_id, entity_id)
        
        if not invoice:
            raise ValueError("Invoice not found")
        
        if invoice.status != InvoiceStatus.DRAFT:
            raise ValueError("Can only modify invoices in DRAFT status")
        
        if len(invoice.line_items) <= 1:
            raise ValueError("Invoice must have at least one line item")
        
        # Find and remove line item
        line_item = next(
            (li for li in invoice.line_items if li.id == line_item_id),
            None
        )
        
        if not line_item:
            raise ValueError("Line item not found")
        
        await self.db.delete(line_item)
        
        # Recalculate invoice totals
        await self._recalculate_invoice_totals(invoice, user_id)
        
        return await self.get_invoice_by_id(invoice_id, entity_id)
    
    async def _recalculate_invoice_totals(
        self,
        invoice: Invoice,
        user_id: uuid.UUID,
    ):
        """Recalculate invoice totals from line items."""
        await self.db.flush()
        
        # Reload line items
        result = await self.db.execute(
            select(InvoiceLineItem)
            .where(InvoiceLineItem.invoice_id == invoice.id)
        )
        line_items = list(result.scalars().all())
        
        subtotal = sum(li.subtotal for li in line_items)
        vat_amount = sum(li.vat_amount for li in line_items)
        total_amount = subtotal + vat_amount - invoice.discount_amount
        
        invoice.subtotal = subtotal
        invoice.vat_amount = vat_amount
        invoice.total_amount = total_amount
        invoice.updated_by = user_id
        
        await self.db.commit()
    
    # ===========================================
    # STATUS MANAGEMENT
    # ===========================================
    
    async def finalize_invoice(
        self,
        invoice_id: uuid.UUID,
        entity_id: uuid.UUID,
        user_id: uuid.UUID,
        post_to_gl: bool = True,
    ) -> Invoice:
        """
        Finalize a draft invoice (move to PENDING status).
        
        When post_to_gl=True (default), creates GL journal entry:
            Dr Accounts Receivable (1130)
            Cr Sales Revenue (4100)
            Cr VAT Payable (2130) - if applicable
        """
        invoice = await self.get_invoice_by_id(invoice_id, entity_id)
        
        if not invoice:
            raise ValueError("Invoice not found")
        
        if invoice.status != InvoiceStatus.DRAFT:
            raise ValueError("Can only finalize DRAFT invoices")
        
        invoice.status = InvoiceStatus.PENDING
        invoice.updated_by = user_id
        
        await self.db.commit()
        await self.db.refresh(invoice)
        
        # Post to General Ledger
        if post_to_gl:
            gl_result = await self._post_invoice_to_gl(invoice, entity_id, user_id)
            if not gl_result.get("success"):
                # Log warning but don't fail invoice finalization
                import logging
                logging.warning(f"Invoice {invoice.invoice_number} GL posting failed: {gl_result.get('message')}")
        
        return invoice
    
    async def _post_invoice_to_gl(
        self,
        invoice: Invoice,
        entity_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Post invoice to General Ledger.
        
        Creates double-entry journal:
            Dr Accounts Receivable    (Total Amount)
            Cr Sales Revenue          (Subtotal)
            Cr VAT Payable            (VAT Amount) - if applicable
        """
        from app.services.accounting_service import AccountingService
        from app.schemas.accounting import GLPostingRequest, JournalEntryLineCreate
        
        accounting_service = AccountingService(self.db)
        
        # Get GL account IDs
        ar_account = await self._get_gl_account_id(entity_id, GL_ACCOUNTS["ACCOUNTS_RECEIVABLE"])
        revenue_account = await self._get_gl_account_id(entity_id, GL_ACCOUNTS["SALES_REVENUE"])
        vat_account = await self._get_gl_account_id(entity_id, GL_ACCOUNTS["VAT_PAYABLE"])
        
        if not ar_account or not revenue_account:
            return {
                "success": False,
                "message": "Required GL accounts not found (AR or Revenue). Initialize Chart of Accounts first.",
            }
        
        # Build journal entry lines
        lines = []
        
        # Debit: Accounts Receivable (total amount)
        lines.append(JournalEntryLineCreate(
            account_id=ar_account,
            description=f"Invoice {invoice.invoice_number} - {invoice.customer.name if invoice.customer else 'Customer'}",
            debit_amount=invoice.total_amount,
            credit_amount=Decimal("0.00"),
            customer_id=invoice.customer_id,
        ))
        
        # Credit: Sales Revenue (subtotal)
        lines.append(JournalEntryLineCreate(
            account_id=revenue_account,
            description=f"Sales - Invoice {invoice.invoice_number}",
            debit_amount=Decimal("0.00"),
            credit_amount=invoice.subtotal,
            customer_id=invoice.customer_id,
        ))
        
        # Credit: VAT Payable (if applicable)
        if invoice.vat_amount > 0 and vat_account:
            lines.append(JournalEntryLineCreate(
                account_id=vat_account,
                description=f"VAT Output - Invoice {invoice.invoice_number}",
                debit_amount=Decimal("0.00"),
                credit_amount=invoice.vat_amount,
            ))
        
        # Create GL posting request
        gl_request = GLPostingRequest(
            source_module="invoices",
            source_document_type="invoice",
            source_document_id=invoice.id,
            source_reference=invoice.invoice_number,
            entry_date=invoice.invoice_date,
            description=f"Invoice {invoice.invoice_number} - {invoice.customer.name if invoice.customer else 'Customer'}",
            lines=lines,
            auto_post=True,
        )
        
        # Post to GL
        result = await accounting_service.post_to_gl(entity_id, gl_request, user_id)
        
        return {
            "success": result.success,
            "journal_entry_id": str(result.journal_entry_id) if result.journal_entry_id else None,
            "entry_number": result.entry_number,
            "message": result.message,
        }
    
    async def _get_gl_account_id(
        self,
        entity_id: uuid.UUID,
        account_code: str,
    ) -> Optional[uuid.UUID]:
        """Get GL account ID by account code."""
        result = await self.db.execute(
            select(ChartOfAccounts.id).where(
                and_(
                    ChartOfAccounts.entity_id == entity_id,
                    ChartOfAccounts.account_code == account_code,
                    ChartOfAccounts.is_header == False,
                )
            )
        )
        account = result.scalar_one_or_none()
        return account
    
    async def cancel_invoice(
        self,
        invoice_id: uuid.UUID,
        entity_id: uuid.UUID,
        user_id: uuid.UUID,
        reason: Optional[str] = None,
    ) -> Invoice:
        """Cancel an invoice."""
        invoice = await self.get_invoice_by_id(invoice_id, entity_id)
        
        if not invoice:
            raise ValueError("Invoice not found")
        
        if invoice.status in [InvoiceStatus.PAID, InvoiceStatus.CANCELLED]:
            raise ValueError("Cannot cancel a PAID or already CANCELLED invoice")
        
        invoice.status = InvoiceStatus.CANCELLED
        if reason:
            invoice.notes = f"{invoice.notes or ''}\n\nCancelled: {reason}".strip()
        invoice.updated_by = user_id
        
        await self.db.commit()
        await self.db.refresh(invoice)
        
        return invoice
    
    # ===========================================
    # PAYMENT RECORDING
    # ===========================================
    
    async def record_payment(
        self,
        invoice_id: uuid.UUID,
        entity_id: uuid.UUID,
        user_id: uuid.UUID,
        amount: float,
        payment_date: date,
        payment_method: str = "bank_transfer",
        reference: Optional[str] = None,
        notes: Optional[str] = None,
        bank_account_id: Optional[uuid.UUID] = None,
        wht_amount: float = 0,
        post_to_gl: bool = True,
        # Multi-currency payment support (IAS 21 compliant)
        payment_currency: Optional[str] = None,
        payment_exchange_rate: Optional[float] = None,
        fx_service: Optional["FXService"] = None,
    ) -> Invoice:
        """
        Record a payment against an invoice with multi-currency support.
        
        When post_to_gl=True (default), creates GL journal entry:
            Dr Bank (1120)                - Cash received (functional currency)
            Dr WHT Receivable (1170)      - If WHT deducted
            Cr Accounts Receivable (1130) - Reduce AR
            Dr/Cr FX Gain/Loss (4500)     - If FX difference exists
        
        Multi-Currency Logic (IAS 21):
        - If payment is in a different currency or rate differs from booking rate,
          calculate realized FX gain/loss
        - Realized FX Gain/Loss = Payment Amount in Functional Currency - 
          Equivalent Invoice Amount at Booking Rate
        
        Args:
            amount: Payment amount in the payment currency
            wht_amount: Amount withheld by customer (WHT deduction)
            payment_currency: Currency of the payment (defaults to invoice currency)
            payment_exchange_rate: Exchange rate for payment (auto-fetched if not provided)
            fx_service: Optional FXService instance for rate lookup
        """
        invoice = await self.get_invoice_by_id(invoice_id, entity_id)
        
        if not invoice:
            raise ValueError("Invoice not found")
        
        if invoice.status == InvoiceStatus.CANCELLED:
            raise ValueError("Cannot record payment on cancelled invoice")
        
        if invoice.status == InvoiceStatus.DRAFT:
            raise ValueError("Cannot record payment on draft invoice")
        
        payment_amount = Decimal(str(amount))
        wht_decimal = Decimal(str(wht_amount))
        total_settled = payment_amount + wht_decimal
        
        # ===========================================
        # MULTI-CURRENCY PAYMENT PROCESSING (IAS 21)
        # ===========================================
        invoice_currency = invoice.currency or "NGN"
        payment_currency = payment_currency or invoice_currency
        functional_currency = "NGN"
        
        # Determine if this is a foreign currency transaction
        is_fx_payment = payment_currency != functional_currency
        
        # Get exchange rates
        invoice_rate = Decimal(str(invoice.exchange_rate)) if invoice.exchange_rate else Decimal("1.0")
        
        if payment_exchange_rate:
            payment_rate = Decimal(str(payment_exchange_rate))
        elif is_fx_payment and fx_service:
            # Auto-fetch rate from FX service
            rate_result = await fx_service.get_exchange_rate(
                from_currency=payment_currency,
                to_currency=functional_currency,
                rate_date=payment_date,
            )
            if rate_result:
                payment_rate = Decimal(str(rate_result.rate))
            else:
                # Fallback to invoice rate if same currency, else raise error
                if payment_currency == invoice_currency:
                    payment_rate = invoice_rate
                else:
                    raise ValueError(f"Exchange rate not available for {payment_currency} to {functional_currency}")
        else:
            # Use invoice rate if same currency, or 1.0 for NGN
            if payment_currency == invoice_currency:
                payment_rate = invoice_rate
            elif payment_currency == functional_currency:
                payment_rate = Decimal("1.0")
            else:
                payment_rate = invoice_rate  # Fallback
        
        # Calculate functional currency amounts
        if payment_currency == functional_currency:
            functional_payment = payment_amount
            functional_wht = wht_decimal
        else:
            functional_payment = (payment_amount * payment_rate).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            functional_wht = (wht_decimal * payment_rate).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        
        functional_total_settled = functional_payment + functional_wht
        
        # ===========================================
        # REALIZED FX GAIN/LOSS CALCULATION (IAS 21)
        # ===========================================
        realized_fx_gain_loss = Decimal("0.00")
        
        # Calculate FX gain/loss only for foreign currency invoices/payments
        if invoice_currency != functional_currency or payment_currency != functional_currency:
            # The FX gain/loss is the difference between:
            # 1. Payment amount converted at payment date rate
            # 2. Payment amount converted at invoice booking rate
            
            if payment_currency == invoice_currency:
                # Payment in same currency as invoice - compare rates
                payment_at_booking_rate = (payment_amount * invoice_rate).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                payment_at_payment_rate = functional_payment
                
                # Positive = gain (received more NGN than expected)
                # Negative = loss (received less NGN than expected)
                realized_fx_gain_loss = payment_at_payment_rate - payment_at_booking_rate
            elif payment_currency != invoice_currency:
                # Cross-currency payment (e.g., EUR invoice paid in USD)
                # Convert payment to invoice currency first, then compare
                # This is a more complex scenario - for now, record the functional difference
                invoice_amount_in_functional = (payment_amount * invoice_rate).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                ) if payment_currency == invoice_currency else functional_payment
                
                realized_fx_gain_loss = functional_payment - invoice_amount_in_functional
        
        # ===========================================
        # UPDATE INVOICE BALANCES
        # ===========================================
        new_amount_paid = invoice.amount_paid + total_settled
        
        if new_amount_paid > invoice.total_amount:
            raise ValueError("Payment amount exceeds invoice balance")
        
        invoice.amount_paid = new_amount_paid
        
        # Update functional currency tracking
        current_functional_paid = invoice.functional_amount_paid or Decimal("0.00")
        invoice.functional_amount_paid = current_functional_paid + functional_total_settled
        
        # Accumulate realized FX gain/loss
        current_realized_fx = invoice.realized_fx_gain_loss or Decimal("0.00")
        invoice.realized_fx_gain_loss = current_realized_fx + realized_fx_gain_loss
        
        # Update status based on payment
        if new_amount_paid >= invoice.total_amount:
            invoice.status = InvoiceStatus.PAID
        elif new_amount_paid > 0:
            invoice.status = InvoiceStatus.PARTIALLY_PAID
        
        # ===========================================
        # ADD PAYMENT NOTE
        # ===========================================
        currency_symbol = "₦" if payment_currency == "NGN" else payment_currency
        payment_note = f"Payment received: {currency_symbol}{amount:,.2f} on {payment_date} via {payment_method}"
        if wht_amount > 0:
            wht_symbol = "₦" if payment_currency == "NGN" else payment_currency
            payment_note += f" (WHT deducted: {wht_symbol}{wht_amount:,.2f})"
        if reference:
            payment_note += f" (Ref: {reference})"
        
        # Add FX details to note
        if is_fx_payment or realized_fx_gain_loss != 0:
            payment_note += f"\n  Exchange Rate: {payment_rate}"
            payment_note += f" | Functional Amount: ₦{functional_payment:,.2f}"
            if realized_fx_gain_loss > 0:
                payment_note += f" | FX Gain: ₦{realized_fx_gain_loss:,.2f}"
            elif realized_fx_gain_loss < 0:
                payment_note += f" | FX Loss: ₦{abs(realized_fx_gain_loss):,.2f}"
        
        invoice.notes = f"{invoice.notes or ''}\n\n{payment_note}".strip()
        
        invoice.updated_by = user_id
        
        await self.db.commit()
        await self.db.refresh(invoice)
        
        # Post to General Ledger
        if post_to_gl:
            gl_result = await self._post_payment_to_gl(
                invoice, entity_id, user_id, 
                functional_payment,  # Use functional amount for GL
                functional_wht,
                payment_date, reference, bank_account_id,
                realized_fx_gain_loss=realized_fx_gain_loss,  # Pass FX gain/loss
            )
            if not gl_result.get("success"):
                import logging
                logging.warning(f"Payment GL posting failed for invoice {invoice.invoice_number}: {gl_result.get('message')}")
        
        return invoice
    
    async def _post_payment_to_gl(
        self,
        invoice: Invoice,
        entity_id: uuid.UUID,
        user_id: uuid.UUID,
        cash_amount: Decimal,
        wht_amount: Decimal,
        payment_date: date,
        reference: Optional[str],
        bank_account_id: Optional[uuid.UUID],
        realized_fx_gain_loss: Decimal = Decimal("0.00"),
    ) -> Dict[str, Any]:
        """
        Post payment receipt to General Ledger with FX gain/loss handling.
        
        Creates double-entry journal:
            Dr Bank                   (Cash Amount)
            Dr WHT Receivable         (WHT Amount) - if applicable
            Dr FX Loss                (FX Loss) - if applicable
            Cr Accounts Receivable    (Total Settled at booking rate)
            Cr FX Gain                (FX Gain) - if applicable
            
        IAS 21 Compliance:
        - FX gains/losses are recognized in profit or loss
        - Exchange differences arising on settlement are recognized in the period
        """
        from app.services.accounting_service import AccountingService
        from app.schemas.accounting import GLPostingRequest, JournalEntryLineCreate
        
        accounting_service = AccountingService(self.db)
        
        # Get GL account IDs
        ar_account = await self._get_gl_account_id(entity_id, GL_ACCOUNTS["ACCOUNTS_RECEIVABLE"])
        bank_account = await self._get_gl_account_id(entity_id, GL_ACCOUNTS["BANK"])
        wht_account = await self._get_gl_account_id(entity_id, GL_ACCOUNTS["WHT_RECEIVABLE"])
        
        if not ar_account or not bank_account:
            return {
                "success": False,
                "message": "Required GL accounts not found (AR or Bank). Initialize Chart of Accounts first.",
            }
        
        # Get FX Gain/Loss account (4500 series - typically 4500 for gain, 5500 for loss)
        # Using a single FX Gain/Loss account with Dr for loss, Cr for gain
        fx_gain_loss_account = await self._get_gl_account_id(entity_id, "4500")  # FX Gain/Loss
        
        total_settled = cash_amount + wht_amount
        
        # Build journal entry lines
        lines = []
        
        # Debit: Bank (cash received in functional currency)
        lines.append(JournalEntryLineCreate(
            account_id=bank_account,
            description=f"Receipt - Invoice {invoice.invoice_number}",
            debit_amount=cash_amount,
            credit_amount=Decimal("0.00"),
            customer_id=invoice.customer_id,
        ))
        
        # Debit: WHT Receivable (if WHT deducted)
        if wht_amount > 0 and wht_account:
            lines.append(JournalEntryLineCreate(
                account_id=wht_account,
                description=f"WHT Deducted - Invoice {invoice.invoice_number}",
                debit_amount=wht_amount,
                credit_amount=Decimal("0.00"),
                customer_id=invoice.customer_id,
            ))
        
        # Handle FX Gain/Loss (IAS 21)
        # If FX loss (negative): Debit FX Loss account
        # If FX gain (positive): Credit FX Gain account
        if realized_fx_gain_loss != 0 and fx_gain_loss_account:
            if realized_fx_gain_loss < 0:
                # FX Loss - Debit
                lines.append(JournalEntryLineCreate(
                    account_id=fx_gain_loss_account,
                    description=f"Realized FX Loss - Invoice {invoice.invoice_number}",
                    debit_amount=abs(realized_fx_gain_loss),
                    credit_amount=Decimal("0.00"),
                    customer_id=invoice.customer_id,
                ))
            else:
                # FX Gain - Credit
                lines.append(JournalEntryLineCreate(
                    account_id=fx_gain_loss_account,
                    description=f"Realized FX Gain - Invoice {invoice.invoice_number}",
                    debit_amount=Decimal("0.00"),
                    credit_amount=realized_fx_gain_loss,
                    customer_id=invoice.customer_id,
                ))
        
        # Credit: Accounts Receivable
        # When there's FX gain/loss, the AR credit equals cash + WHT + FX loss (or - FX gain)
        # This ensures the journal balances
        ar_credit_amount = total_settled
        if realized_fx_gain_loss < 0:
            # FX Loss: AR was recorded at booking rate, we received less
            ar_credit_amount = total_settled + abs(realized_fx_gain_loss)
        elif realized_fx_gain_loss > 0:
            # FX Gain: AR was recorded at booking rate, we received more
            ar_credit_amount = total_settled - realized_fx_gain_loss
        
        lines.append(JournalEntryLineCreate(
            account_id=ar_account,
            description=f"Payment - Invoice {invoice.invoice_number}",
            debit_amount=Decimal("0.00"),
            credit_amount=ar_credit_amount,
            customer_id=invoice.customer_id,
        ))
        
        # Create GL posting request
        description = f"Payment Receipt - Invoice {invoice.invoice_number}"
        if realized_fx_gain_loss > 0:
            description += f" (FX Gain: ₦{realized_fx_gain_loss:,.2f})"
        elif realized_fx_gain_loss < 0:
            description += f" (FX Loss: ₦{abs(realized_fx_gain_loss):,.2f})"
        
        gl_request = GLPostingRequest(
            source_module="receipts",
            source_document_type="payment",
            source_document_id=invoice.id,
            source_reference=reference or f"PMT-{invoice.invoice_number}",
            entry_date=payment_date,
            description=description,
            lines=lines,
            auto_post=True,
        )
        
        # Post to GL
        result = await accounting_service.post_to_gl(entity_id, gl_request, user_id)
        
        return {
            "success": result.success,
            "journal_entry_id": str(result.journal_entry_id) if result.journal_entry_id else None,
            "entry_number": result.entry_number,
            "message": result.message,
        }
    
    # ===========================================
    # NRS E-INVOICING
    # ===========================================
    
    async def submit_to_nrs(
        self,
        invoice_id: uuid.UUID,
        entity_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Submit invoice to NRS for IRN generation.
        
        Uses the NRS API client to submit the invoice and obtain an IRN.
        """
        from app.services.nrs_service import get_nrs_client
        
        invoice = await self.get_invoice_by_id(invoice_id, entity_id)
        
        if not invoice:
            raise ValueError("Invoice not found")
        
        if invoice.status not in [InvoiceStatus.PENDING, InvoiceStatus.REJECTED]:
            raise ValueError("Can only submit PENDING or REJECTED invoices to NRS")
        
        # Get entity details for seller information
        entity_result = await self.db.execute(
            select(BusinessEntity).where(BusinessEntity.id == entity_id)
        )
        entity = entity_result.scalar_one_or_none()
        
        if not entity:
            raise ValueError("Business entity not found")
        
        if not entity.tin:
            raise ValueError("Business entity TIN is required for NRS submission")
        
        # Validate B2B requirements
        buyer_tin = None
        buyer_name = "Walk-in Customer"
        buyer_address = None
        
        if invoice.customer:
            buyer_name = invoice.customer.name
            buyer_address = invoice.customer.address
            
            if invoice.customer.is_business:
                if not invoice.customer.tin:
                    raise ValueError("B2B invoices require customer TIN for NRS submission")
                buyer_tin = invoice.customer.tin
        
        # Prepare line items
        line_items = [
            {
                "description": li.description,
                "quantity": float(li.quantity),
                "unit_price": float(li.unit_price),
                "vat_amount": float(li.vat_amount),
                "total": float(li.total),
            }
            for li in invoice.line_items
        ]
        
        # Build seller address
        seller_address = ", ".join(filter(None, [
            entity.address_line1,
            entity.address_line2,
            entity.city,
            entity.state,
            entity.country,
        ]))
        
        # Submit to NRS
        nrs_client = get_nrs_client()
        result = await nrs_client.submit_invoice(
            seller_tin=entity.tin,
            seller_name=entity.legal_name or entity.name,
            seller_address=seller_address or "Nigeria",
            buyer_name=buyer_name,
            buyer_tin=buyer_tin,
            buyer_address=buyer_address,
            invoice_number=invoice.invoice_number,
            invoice_date=invoice.invoice_date.strftime("%Y-%m-%d"),
            subtotal=float(invoice.subtotal),
            vat_amount=float(invoice.vat_amount),
            total_amount=float(invoice.total_amount),
            line_items=line_items,
            vat_rate=float(invoice.vat_rate),
        )
        
        if result.success:
            invoice.status = InvoiceStatus.SUBMITTED
            invoice.nrs_irn = result.irn
            invoice.nrs_qr_code_data = result.qr_code_data
            invoice.nrs_submitted_at = result.submission_timestamp
            invoice.dispute_deadline = result.dispute_deadline
            invoice.nrs_response = json.dumps(result.raw_response) if result.raw_response else None
            invoice.updated_by = user_id
            
            await self.db.commit()
            await self.db.refresh(invoice)
            
            return {
                "success": True,
                "invoice_id": str(invoice.id),
                "nrs_irn": result.irn,
                "qr_code_data": result.qr_code_data,
                "message": result.message,
                "submitted_at": result.submission_timestamp,
                "dispute_deadline": result.dispute_deadline,
            }
        else:
            # Mark as rejected if submission failed
            invoice.status = InvoiceStatus.REJECTED
            invoice.nrs_response = json.dumps(result.raw_response) if result.raw_response else result.message
            invoice.updated_by = user_id
            
            await self.db.commit()
            
            return {
                "success": False,
                "invoice_id": str(invoice.id),
                "message": result.message,
                "error_code": result.response_code,
            }
    
    # ===========================================
    # STATISTICS & REPORTING
    # ===========================================
    
    async def get_invoice_summary(
        self,
        entity_id: uuid.UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Get invoice summary statistics."""
        today = date.today()
        
        # Base query
        base_query = select(Invoice).where(Invoice.entity_id == entity_id)
        
        if start_date:
            base_query = base_query.where(Invoice.invoice_date >= start_date)
        if end_date:
            base_query = base_query.where(Invoice.invoice_date <= end_date)
        
        result = await self.db.execute(base_query)
        invoices = list(result.scalars().all())
        
        # Calculate statistics
        summary = {
            "total_invoices": len(invoices),
            "total_draft": 0,
            "total_pending": 0,
            "total_submitted": 0,
            "total_accepted": 0,
            "total_paid": 0,
            "total_overdue": 0,
            "total_invoiced": Decimal("0"),
            "total_collected": Decimal("0"),
            "total_outstanding": Decimal("0"),
            "total_vat_collected": Decimal("0"),
            "period_start": start_date,
            "period_end": end_date,
        }
        
        for inv in invoices:
            # Count by status
            if inv.status == InvoiceStatus.DRAFT:
                summary["total_draft"] += 1
            elif inv.status == InvoiceStatus.PENDING:
                summary["total_pending"] += 1
            elif inv.status == InvoiceStatus.SUBMITTED:
                summary["total_submitted"] += 1
            elif inv.status == InvoiceStatus.ACCEPTED:
                summary["total_accepted"] += 1
            elif inv.status == InvoiceStatus.PAID:
                summary["total_paid"] += 1
            
            # Check overdue
            if inv.due_date < today and inv.status not in [InvoiceStatus.PAID, InvoiceStatus.CANCELLED]:
                summary["total_overdue"] += 1
            
            # Financial totals (exclude drafts and cancelled)
            if inv.status not in [InvoiceStatus.DRAFT, InvoiceStatus.CANCELLED]:
                summary["total_invoiced"] += inv.total_amount
                summary["total_collected"] += inv.amount_paid
                summary["total_outstanding"] += (inv.total_amount - inv.amount_paid)
                
                # VAT from paid invoices
                if inv.status == InvoiceStatus.PAID:
                    summary["total_vat_collected"] += inv.vat_amount
        
        # Convert Decimals to floats for JSON serialization
        summary["total_invoiced"] = float(summary["total_invoiced"])
        summary["total_collected"] = float(summary["total_collected"])
        summary["total_outstanding"] = float(summary["total_outstanding"])
        summary["total_vat_collected"] = float(summary["total_vat_collected"])
        
        return summary
    
    # ===========================================
    # NRS CANCELLATION (NTAA 2025 - 72-Hour Lock)
    # ===========================================
    
    async def cancel_nrs_submission(
        self,
        invoice_id: uuid.UUID,
        entity_id: uuid.UUID,
        user_id: uuid.UUID,
        reason: str,
    ) -> Invoice:
        """
        Cancel an NRS submission during the 72-hour window.
        
        NTAA 2025 Compliance:
        - Only allowed during the 72-hour buyer review window
        - Only Owner can cancel (permission check done at router level)
        - After window expires, Credit Note is required
        
        Args:
            invoice_id: Invoice to cancel NRS for
            entity_id: Entity ID for authorization
            user_id: User ID (Owner) performing cancellation
            reason: Cancellation reason (required)
            
        Returns:
            Updated invoice
            
        Raises:
            ValueError: If invoice not found or not cancellable
        """
        invoice = await self.get_invoice_by_id(invoice_id, entity_id)
        
        if not invoice:
            raise ValueError("Invoice not found")
        
        if not invoice.is_nrs_locked:
            raise ValueError("Invoice has not been submitted to NRS")
        
        # Check 72-hour window
        if invoice.nrs_lock_expires_at:
            from datetime import timezone
            now = datetime.now(timezone.utc)
            if now > invoice.nrs_lock_expires_at:
                raise ValueError(
                    "72-hour window has expired. A Credit Note is required to modify this invoice."
                )
        
        # Cancel the NRS submission
        invoice.is_nrs_locked = False
        invoice.nrs_cancelled_by_id = user_id
        invoice.nrs_cancellation_reason = reason
        invoice.status = InvoiceStatus.DRAFT  # Return to draft for correction
        
        # Add cancellation note
        cancellation_note = f"\n\nNRS Submission Cancelled: {reason}\nCancelled by user ID: {user_id}"
        invoice.notes = f"{invoice.notes or ''}{cancellation_note}".strip()
        
        invoice.updated_by = user_id
        
        await self.db.commit()
        await self.db.refresh(invoice)
        
        return invoice
