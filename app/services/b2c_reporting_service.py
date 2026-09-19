"""
Tekvwa Pro Audit - B2C Real-time Reporting Service

Handles automatic reporting of B2C transactions > ₦50,000 to NRS within 24 hours.
Per the Nigeria Tax Administration Act 2025, high-value B2C transactions must be
reported to NRS in real-time to enable tax compliance monitoring.
"""

import uuid
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import Optional, List, Dict, Any

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.invoice import Invoice, InvoiceStatus
from app.models.entity import BusinessEntity
from app.services.nrs_service import get_nrs_client
from app.config import settings


class B2CReportingService:
    """
    Service for managing B2C real-time reporting to NRS.
    
    2026 Compliance Requirements:
    - B2C transactions over ₦50,000 must be reported within 24 hours
    - Penalty: ₦10,000 per late transaction (max ₦500,000/day)
    - Required for retail, hospitality, and consumer-facing businesses
    """
    
    DEFAULT_THRESHOLD = Decimal("50000.00")
    REPORTING_WINDOW_HOURS = 24
    LATE_PENALTY_PER_TRANSACTION = Decimal("10000.00")
    MAX_DAILY_PENALTY = Decimal("500000.00")
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.nrs_client = get_nrs_client()
    
    async def get_entity_settings(self, entity_id: uuid.UUID) -> Dict[str, Any]:
        """Get B2C reporting settings for an entity."""
        result = await self.db.execute(
            select(BusinessEntity).where(BusinessEntity.id == entity_id)
        )
        entity = result.scalar_one_or_none()
        
        if not entity:
            raise ValueError("Entity not found")
        
        return {
            "entity_id": str(entity_id),
            "b2c_realtime_reporting_enabled": entity.b2c_realtime_reporting_enabled,
            "b2c_reporting_threshold": float(entity.b2c_reporting_threshold),
            "entity_name": entity.name,
            "tin": entity.tin,
        }
    
    async def update_entity_settings(
        self,
        entity_id: uuid.UUID,
        enabled: bool,
        threshold: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """Update B2C reporting settings for an entity."""
        result = await self.db.execute(
            select(BusinessEntity).where(BusinessEntity.id == entity_id)
        )
        entity = result.scalar_one_or_none()
        
        if not entity:
            raise ValueError("Entity not found")
        
        entity.b2c_realtime_reporting_enabled = enabled
        if threshold is not None:
            entity.b2c_reporting_threshold = threshold
        
        await self.db.commit()
        
        return await self.get_entity_settings(entity_id)
    
    async def get_pending_b2c_reports(
        self,
        entity_id: uuid.UUID,
    ) -> List[Invoice]:
        """Get B2C transactions pending reporting (not yet reported)."""
        result = await self.db.execute(
            select(Invoice)
            .options(selectinload(Invoice.customer))
            .where(
                and_(
                    Invoice.entity_id == entity_id,
                    Invoice.is_b2c_reportable == True,
                    Invoice.b2c_reported_at.is_(None),
                    Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.ACCEPTED, InvoiceStatus.PAID]),
                )
            )
            .order_by(Invoice.created_at.asc())
        )
        return list(result.scalars().all())
    
    async def get_overdue_b2c_reports(
        self,
        entity_id: uuid.UUID,
    ) -> List[Invoice]:
        """Get B2C transactions past the 24-hour reporting deadline."""
        now = datetime.utcnow()
        result = await self.db.execute(
            select(Invoice)
            .options(selectinload(Invoice.customer))
            .where(
                and_(
                    Invoice.entity_id == entity_id,
                    Invoice.is_b2c_reportable == True,
                    Invoice.b2c_reported_at.is_(None),
                    Invoice.b2c_report_deadline < now,
                )
            )
            .order_by(Invoice.b2c_report_deadline.asc())
        )
        return list(result.scalars().all())
    
    async def get_reported_b2c_transactions(
        self,
        entity_id: uuid.UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Invoice]:
        """Get successfully reported B2C transactions."""
        query = select(Invoice).options(selectinload(Invoice.customer)).where(
            and_(
                Invoice.entity_id == entity_id,
                Invoice.is_b2c_reportable == True,
                Invoice.b2c_reported_at.isnot(None),
            )
        )
        
        if start_date:
            query = query.where(Invoice.created_at >= datetime.combine(start_date, datetime.min.time()))
        if end_date:
            query = query.where(Invoice.created_at <= datetime.combine(end_date, datetime.max.time()))
        
        result = await self.db.execute(query.order_by(Invoice.b2c_reported_at.desc()))
        return list(result.scalars().all())
    
    async def check_and_flag_b2c_reportable(
        self,
        invoice: Invoice,
        entity: BusinessEntity,
    ) -> Invoice:
        """
        Check if invoice is B2C and above threshold, flag for reporting.
        
        Called when invoice is created or finalized.
        """
        if not entity.b2c_realtime_reporting_enabled:
            return invoice
        
        # Check if B2C (customer is not a business or no customer TIN)
        is_b2c = not invoice.is_b2b
        
        # Check if above threshold
        above_threshold = invoice.total_amount >= entity.b2c_reporting_threshold
        
        if is_b2c and above_threshold:
            invoice.is_b2c_reportable = True
            invoice.b2c_report_deadline = datetime.utcnow() + timedelta(hours=self.REPORTING_WINDOW_HOURS)
            await self.db.commit()
        
        return invoice
    
    async def submit_b2c_report(
        self,
        invoice_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Submit a single B2C transaction to NRS."""
        result = await self.db.execute(
            select(Invoice)
            .options(selectinload(Invoice.entity), selectinload(Invoice.customer))
            .where(Invoice.id == invoice_id)
        )
        invoice = result.scalar_one_or_none()
        
        if not invoice:
            raise ValueError("Invoice not found")
        
        if not invoice.is_b2c_reportable:
            raise ValueError("Invoice is not B2C reportable")
        
        if invoice.b2c_reported_at:
            return {
                "success": True,
                "already_reported": True,
                "invoice_id": str(invoice.id),
                "report_reference": invoice.b2c_report_reference,
                "reported_at": invoice.b2c_reported_at.isoformat(),
            }
        
        entity = invoice.entity
        customer_name = invoice.customer.name if invoice.customer else "Walk-in Customer"
        
        # Submit to NRS
        response = await self.nrs_client.submit_b2c_transaction_report(
            seller_tin=entity.tin,
            seller_name=entity.name,
            transaction_date=invoice.invoice_date.isoformat(),
            transaction_reference=invoice.invoice_number,
            customer_name=customer_name,
            transaction_amount=float(invoice.total_amount),
            vat_amount=float(invoice.vat_amount),
            payment_method="cash",  # Default, could be enhanced
            customer_phone=invoice.customer.phone if invoice.customer else None,
            customer_email=invoice.customer.email if invoice.customer else None,
        )
        
        if response.get("success"):
            invoice.b2c_reported_at = datetime.utcnow()
            invoice.b2c_report_reference = response.get("report_reference")
            await self.db.commit()
            
            return {
                "success": True,
                "invoice_id": str(invoice.id),
                "invoice_number": invoice.invoice_number,
                "report_reference": invoice.b2c_report_reference,
                "reported_at": invoice.b2c_reported_at.isoformat(),
                "amount": float(invoice.total_amount),
            }
        else:
            return {
                "success": False,
                "invoice_id": str(invoice.id),
                "error": response.get("message", "B2C reporting failed"),
            }
    
    async def submit_all_pending_reports(
        self,
        entity_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Submit all pending B2C reports for an entity."""
        pending = await self.get_pending_b2c_reports(entity_id)
        
        results = []
        success_count = 0
        failed_count = 0
        
        for invoice in pending:
            try:
                result = await self.submit_b2c_report(invoice.id)
                results.append(result)
                if result.get("success"):
                    success_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                results.append({
                    "success": False,
                    "invoice_id": str(invoice.id),
                    "error": str(e),
                })
                failed_count += 1
        
        return {
            "total_processed": len(pending),
            "success_count": success_count,
            "failed_count": failed_count,
            "results": results,
        }
    
    async def get_b2c_summary(
        self,
        entity_id: uuid.UUID,
        year: int,
        month: int,
    ) -> Dict[str, Any]:
        """Get B2C reporting summary for a month."""
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)
        
        # Get all reportable B2C transactions for the period
        result = await self.db.execute(
            select(Invoice).where(
                and_(
                    Invoice.entity_id == entity_id,
                    Invoice.is_b2c_reportable == True,
                    Invoice.created_at >= datetime.combine(start_date, datetime.min.time()),
                    Invoice.created_at <= datetime.combine(end_date, datetime.max.time()),
                )
            )
        )
        invoices = list(result.scalars().all())
        
        reported = [inv for inv in invoices if inv.b2c_reported_at]
        pending = [inv for inv in invoices if not inv.b2c_reported_at and (not inv.b2c_report_deadline or inv.b2c_report_deadline >= datetime.utcnow())]
        overdue = [inv for inv in invoices if not inv.b2c_reported_at and inv.b2c_report_deadline and inv.b2c_report_deadline < datetime.utcnow()]
        
        # Calculate potential penalties
        overdue_penalty = min(
            len(overdue) * self.LATE_PENALTY_PER_TRANSACTION,
            self.MAX_DAILY_PENALTY
        )
        
        return {
            "period": {"year": year, "month": month},
            "total_reportable": len(invoices),
            "reported_on_time": len(reported),
            "pending": len(pending),
            "overdue": len(overdue),
            "total_amount_reported": sum(float(inv.total_amount) for inv in reported),
            "total_amount_pending": sum(float(inv.total_amount) for inv in pending),
            "total_amount_overdue": sum(float(inv.total_amount) for inv in overdue),
            "potential_penalty": float(overdue_penalty),
            "penalty_per_transaction": float(self.LATE_PENALTY_PER_TRANSACTION),
            "max_daily_penalty": float(self.MAX_DAILY_PENALTY),
        }
    
    async def get_compliance_thresholds(self) -> Dict[str, Any]:
        """Get B2C reporting compliance thresholds."""
        return {
            "default_threshold": float(self.DEFAULT_THRESHOLD),
            "reporting_window_hours": self.REPORTING_WINDOW_HOURS,
            "late_penalty_per_transaction": float(self.LATE_PENALTY_PER_TRANSACTION),
            "max_daily_penalty": float(self.MAX_DAILY_PENALTY),
            "description": "B2C transactions over ₦50,000 must be reported to NRS within 24 hours",
            "compliance_reference": "Nigeria Tax Administration Act 2025, Section 42",
        }
