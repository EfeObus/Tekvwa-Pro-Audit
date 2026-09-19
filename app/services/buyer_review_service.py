"""
Tekvwa Pro Audit - Buyer Review Service

Handles the 72-hour buyer confirmation window for NRS e-invoices.
Per the Nigeria Tax Administration Act 2025, buyers have 72 hours
to accept or reject e-invoices via the NRS portal.
"""

import uuid
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import Optional, List, Dict, Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.invoice import Invoice, InvoiceStatus, BuyerStatus
from app.models.tax_2026 import CreditNote, CreditNoteStatus
from app.config import settings


class BuyerReviewService:
    """
    Service for managing the 72-hour buyer review window.
    
    When an e-invoice is submitted to NRS, the buyer has 72 hours to:
    1. Accept the invoice (buyer_status = ACCEPTED)
    2. Reject the invoice (buyer_status = REJECTED)
    
    If rejected, a Credit Note must be automatically generated
    to reverse the VAT liability.
    """
    
    REVIEW_WINDOW_HOURS = 72
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def set_review_deadline(self, invoice: Invoice) -> Invoice:
        """
        Set the 72-hour review deadline when invoice is submitted to NRS.
        
        Called when invoice is successfully submitted to NRS.
        """
        if invoice.nrs_submitted_at:
            invoice.dispute_deadline = invoice.nrs_submitted_at + timedelta(hours=self.REVIEW_WINDOW_HOURS)
            invoice.buyer_status = BuyerStatus.PENDING
            await self.db.commit()
        return invoice
    
    async def get_invoices_pending_review(
        self,
        entity_id: uuid.UUID,
    ) -> List[Invoice]:
        """Get all invoices pending buyer review."""
        result = await self.db.execute(
            select(Invoice)
            .options(selectinload(Invoice.customer))
            .where(
                and_(
                    Invoice.entity_id == entity_id,
                    Invoice.buyer_status == BuyerStatus.PENDING,
                    Invoice.nrs_irn.isnot(None),  # Only NRS-submitted invoices
                )
            )
            .order_by(Invoice.dispute_deadline.asc())
        )
        return list(result.scalars().all())
    
    async def get_overdue_reviews(
        self,
        entity_id: uuid.UUID,
    ) -> List[Invoice]:
        """Get invoices where 72-hour window has passed without response."""
        now = datetime.utcnow()
        result = await self.db.execute(
            select(Invoice)
            .options(selectinload(Invoice.customer))
            .where(
                and_(
                    Invoice.entity_id == entity_id,
                    Invoice.buyer_status == BuyerStatus.PENDING,
                    Invoice.dispute_deadline < now,
                )
            )
        )
        return list(result.scalars().all())
    
    async def get_auto_accepted_invoices(
        self,
        entity_id: uuid.UUID,
    ) -> List[Invoice]:
        """Get invoices auto-accepted after 72-hour window expired without response."""
        result = await self.db.execute(
            select(Invoice)
            .options(selectinload(Invoice.customer))
            .where(
                and_(
                    Invoice.entity_id == entity_id,
                    Invoice.buyer_status == BuyerStatus.AUTO_ACCEPTED,
                    Invoice.nrs_irn.isnot(None),
                )
            )
            .order_by(Invoice.buyer_response_at.desc())
        )
        return list(result.scalars().all())
    
    async def process_buyer_response(
        self,
        invoice_id: uuid.UUID,
        accepted: bool,
        rejection_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process buyer's response to invoice.
        
        If rejected, automatically creates a Credit Note.
        """
        result = await self.db.execute(
            select(Invoice)
            .options(selectinload(Invoice.customer), selectinload(Invoice.entity))
            .where(Invoice.id == invoice_id)
        )
        invoice = result.scalar_one_or_none()
        
        if not invoice:
            raise ValueError("Invoice not found")
        
        if invoice.buyer_status != BuyerStatus.PENDING:
            raise ValueError(f"Invoice already processed: {invoice.buyer_status}")
        
        invoice.buyer_response_at = datetime.utcnow()
        
        if accepted:
            invoice.buyer_status = BuyerStatus.ACCEPTED
            invoice.status = InvoiceStatus.ACCEPTED
            await self.db.commit()
            return {
                "success": True,
                "action": "accepted",
                "invoice_id": str(invoice.id),
                "message": "Invoice accepted by buyer",
            }
        else:
            # Rejected - create credit note
            invoice.buyer_status = BuyerStatus.REJECTED
            invoice.status = InvoiceStatus.REJECTED
            invoice.dispute_reason = rejection_reason
            invoice.is_disputed = True
            
            credit_note = await self._create_credit_note(invoice, rejection_reason)
            
            invoice.credit_note_id = credit_note.id
            
            await self.db.commit()
            
            return {
                "success": True,
                "action": "rejected",
                "invoice_id": str(invoice.id),
                "credit_note_id": str(credit_note.id),
                "credit_note_number": credit_note.credit_note_number,
                "message": "Invoice rejected, credit note created",
            }
    
    async def _create_credit_note(
        self,
        invoice: Invoice,
        reason: Optional[str] = None,
    ) -> CreditNote:
        """Create a credit note for a rejected invoice."""
        # Generate credit note number
        credit_note_number = await self._generate_credit_note_number(invoice.entity_id)
        
        credit_note = CreditNote(
            entity_id=invoice.entity_id,
            original_invoice_id=invoice.id,
            credit_note_number=credit_note_number,
            issue_date=date.today(),
            reason=reason or f"Buyer rejection of invoice {invoice.invoice_number}",
            subtotal=invoice.subtotal,
            vat_amount=invoice.vat_amount,
            total_amount=invoice.total_amount,
            status=CreditNoteStatus.DRAFT,
        )
        
        self.db.add(credit_note)
        await self.db.flush()
        
        return credit_note
    
    async def _generate_credit_note_number(self, entity_id: uuid.UUID) -> str:
        """Generate next credit note number."""
        result = await self.db.execute(
            select(CreditNote)
            .where(CreditNote.entity_id == entity_id)
            .order_by(CreditNote.created_at.desc())
            .limit(1)
        )
        last_note = result.scalar_one_or_none()
        
        if last_note:
            # Extract number and increment
            try:
                num = int(last_note.credit_note_number.split("-")[-1])
                next_num = num + 1
            except (ValueError, IndexError):
                next_num = 1
        else:
            next_num = 1
        
        year = datetime.now().year
        return f"CN-{year}-{next_num:05d}"
    
    async def poll_nrs_for_responses(self, entity_id: uuid.UUID) -> List[Dict[str, Any]]:
        """
        Poll NRS API for buyer responses.
        
        This would be called by a background task to check for
        buyer responses on pending invoices.
        """
        # Get pending invoices
        pending = await self.get_invoices_pending_review(entity_id)
        
        results = []
        for invoice in pending:
            if invoice.nrs_irn:
                # In production, call NRS API here
                # response = await self._check_nrs_status(invoice.nrs_irn)
                # For now, just check if deadline passed
                
                if invoice.dispute_deadline and datetime.utcnow() > invoice.dispute_deadline:
                    # Auto-accept if no response within 72 hours
                    result = await self._auto_accept_invoice(invoice)
                    results.append(result)
        
        return results
    
    async def _auto_accept_invoice(self, invoice: Invoice) -> Dict[str, Any]:
        """Auto-accept an invoice when 72-hour window expires without response."""
        invoice.buyer_status = BuyerStatus.AUTO_ACCEPTED
        invoice.status = InvoiceStatus.ACCEPTED
        invoice.buyer_response_at = datetime.utcnow()
        await self.db.commit()
        
        return {
            "success": True,
            "action": "auto_accepted",
            "auto_accepted": True,
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "message": "Invoice auto-accepted (72-hour window expired)",
        }
    
    async def get_credit_notes(
        self,
        entity_id: uuid.UUID,
        status: Optional[CreditNoteStatus] = None,
    ) -> List[CreditNote]:
        """Get credit notes for an entity."""
        query = select(CreditNote).where(CreditNote.entity_id == entity_id)
        
        if status:
            query = query.where(CreditNote.status == status)
        
        query = query.order_by(CreditNote.created_at.desc())
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def submit_credit_note_to_nrs(
        self,
        credit_note_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Submit a credit note to NRS."""
        result = await self.db.execute(
            select(CreditNote)
            .where(CreditNote.id == credit_note_id)
        )
        credit_note = result.scalar_one_or_none()
        
        if not credit_note:
            raise ValueError("Credit note not found")
        
        if credit_note.status != CreditNoteStatus.DRAFT:
            raise ValueError("Credit note already submitted")
        
        # In production, call NRS API here
        # response = await nrs_client.submit_credit_note(credit_note)
        
        # For now, simulate successful submission
        credit_note.status = CreditNoteStatus.SUBMITTED
        credit_note.nrs_submitted_at = datetime.utcnow()
        credit_note.nrs_irn = f"CN-NRS-{uuid.uuid4().hex[:12].upper()}"
        
        await self.db.commit()
        
        return {
            "success": True,
            "credit_note_id": str(credit_note.id),
            "nrs_irn": credit_note.nrs_irn,
        }
