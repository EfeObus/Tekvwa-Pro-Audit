"""
Tekvwa Pro Audit - VAT Calculator Service

VAT calculation and recording service for Nigerian VAT compliance.

Nigeria VAT Rate (2026): 7.5%

Key Features:
- Input VAT tracking (recoverable based on WREN compliance)
- Output VAT tracking (from sales/invoices)
- VAT period management
- VAT return preparation
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

from sqlalchemy import select, func, and_, extract
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.tax import VATRecord, TaxPeriod, TaxPeriodType
from app.models.transaction import Transaction, TransactionType, WRENStatus
from app.models.invoice import Invoice, InvoiceStatus


class VATRate(str, Enum):
    """Nigerian VAT rates."""
    STANDARD = "7.5"
    ZERO_RATED = "0"
    EXEMPT = "exempt"


# VAT Rate constant
NIGERIA_VAT_RATE = Decimal("7.5")


class VATCalculator:
    """
    VAT calculation utilities.
    
    Nigeria VAT is 7.5% (standard rate).
    Zero-rated items include exports, basic food items, etc.
    Exempt items include medical services, educational services, etc.
    """
    
    # Zero-rated categories (VAT applies at 0%)
    ZERO_RATED_CATEGORIES = [
        "exports",
        "basic_food",
        "medical_equipment",
        "agricultural_produce",
        "baby_products",
    ]
    
    # Exempt categories (no VAT)
    EXEMPT_CATEGORIES = [
        "medical_services",
        "educational_services",
        "rental_residential",
        "religious_organizations",
    ]
    
    @staticmethod
    def calculate_vat(
        amount: Decimal,
        vat_rate: Decimal = NIGERIA_VAT_RATE,
        is_inclusive: bool = False,
    ) -> Tuple[Decimal, Decimal, Decimal]:
        """
        Calculate VAT from an amount.
        
        Args:
            amount: The base amount
            vat_rate: VAT percentage (default 7.5%)
            is_inclusive: If True, amount includes VAT already
            
        Returns:
            Tuple of (net_amount, vat_amount, total_amount)
        """
        if is_inclusive:
            # Extract VAT from inclusive amount
            divisor = 1 + (vat_rate / 100)
            net_amount = amount / divisor
            vat_amount = amount - net_amount
            total_amount = amount
        else:
            # Add VAT to net amount
            net_amount = amount
            vat_amount = amount * (vat_rate / 100)
            total_amount = amount + vat_amount
        
        # Round to 2 decimal places
        return (
            round(net_amount, 2),
            round(vat_amount, 2),
            round(total_amount, 2),
        )
    
    @staticmethod
    def is_vat_recoverable(
        wren_status: str,
        category_code: Optional[str] = None,
    ) -> bool:
        """
        Determine if input VAT is recoverable.
        
        VAT is only recoverable on WREN-compliant expenses:
        - W: Wholly for business
        - R: Reasonable for business
        - E: Exclusively for income generation
        - N: Necessary for operations
        
        Non-WREN expenses have non-recoverable VAT.
        """
        if wren_status in [WRENStatus.COMPLIANT, "compliant", "classified"]:
            return True
        return False


class VATService:
    """Service for VAT operations and recording."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.calculator = VATCalculator()
    
    # ===========================================
    # VAT PERIOD MANAGEMENT
    # ===========================================
    
    async def get_or_create_vat_period(
        self,
        entity_id: uuid.UUID,
        year: int,
        month: int,
    ) -> VATRecord:
        """Get or create VAT record for a specific month."""
        # Check if period exists
        result = await self.db.execute(
            select(VATRecord)
            .where(VATRecord.entity_id == entity_id)
            .where(extract('year', VATRecord.period_start) == year)
            .where(extract('month', VATRecord.period_start) == month)
        )
        vat_record = result.scalar_one_or_none()
        
        if vat_record:
            return vat_record
        
        # Create new VAT record for the period
        period_start = date(year, month, 1)
        if month == 12:
            period_end = date(year + 1, 1, 1)
        else:
            period_end = date(year, month + 1, 1)
        period_end = period_end.replace(day=1) - timedelta(days=1)
        
        vat_record = VATRecord(
            entity_id=entity_id,
            period_start=period_start,
            period_end=period_end,
            output_vat=Decimal("0"),
            input_vat_total=Decimal("0"),
            input_vat_recoverable=Decimal("0"),
            input_vat_non_recoverable=Decimal("0"),
            net_vat_payable=Decimal("0"),
        )
        
        self.db.add(vat_record)
        await self.db.commit()
        await self.db.refresh(vat_record)
        
        return vat_record
    
    async def get_vat_records_for_entity(
        self,
        entity_id: uuid.UUID,
        year: Optional[int] = None,
        is_filed: Optional[bool] = None,
    ) -> List[VATRecord]:
        """Get all VAT records for an entity."""
        query = select(VATRecord).where(VATRecord.entity_id == entity_id)
        
        if year:
            query = query.where(extract('year', VATRecord.period_start) == year)
        
        if is_filed is not None:
            query = query.where(VATRecord.is_filed == is_filed)
        
        query = query.order_by(VATRecord.period_start.desc())
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    # ===========================================
    # VAT CALCULATION FROM TRANSACTIONS/INVOICES
    # ===========================================
    
    async def calculate_period_vat(
        self,
        entity_id: uuid.UUID,
        year: int,
        month: int,
    ) -> Dict[str, Any]:
        """
        Calculate VAT for a specific period from transactions and invoices.
        
        Returns:
            Dict with output_vat, input_vat_details, and net_vat
        """
        period_start = date(year, month, 1)
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        period_end = next_month - timedelta(days=1)
        
        # Calculate Output VAT from invoices
        output_vat = await self._calculate_output_vat(
            entity_id, period_start, period_end
        )
        
        # Calculate Input VAT from expenses
        input_vat = await self._calculate_input_vat(
            entity_id, period_start, period_end
        )
        
        # Net VAT payable
        net_vat = output_vat - input_vat["recoverable"]
        
        return {
            "period_start": period_start,
            "period_end": period_end,
            "output_vat": float(output_vat),
            "input_vat_total": float(input_vat["total"]),
            "input_vat_recoverable": float(input_vat["recoverable"]),
            "input_vat_non_recoverable": float(input_vat["non_recoverable"]),
            "net_vat_payable": float(net_vat),
            "is_refund": net_vat < 0,
        }
    
    async def _calculate_output_vat(
        self,
        entity_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> Decimal:
        """Calculate output VAT from invoices."""
        result = await self.db.execute(
            select(func.coalesce(func.sum(Invoice.vat_amount), 0))
            .where(Invoice.entity_id == entity_id)
            .where(Invoice.invoice_date >= start_date)
            .where(Invoice.invoice_date <= end_date)
            .where(Invoice.status.not_in([InvoiceStatus.DRAFT, InvoiceStatus.CANCELLED]))
        )
        return Decimal(str(result.scalar() or 0))
    
    async def _calculate_input_vat(
        self,
        entity_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> Dict[str, Decimal]:
        """Calculate input VAT from expense transactions."""
        # Get all expense transactions with VAT
        result = await self.db.execute(
            select(Transaction)
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_date >= start_date)
            .where(Transaction.transaction_date <= end_date)
            .where(Transaction.transaction_type == TransactionType.EXPENSE)
            .where(Transaction.vat_amount > 0)
        )
        transactions = list(result.scalars().all())
        
        total = Decimal("0")
        recoverable = Decimal("0")
        non_recoverable = Decimal("0")
        
        for tx in transactions:
            vat_amount = tx.vat_amount or Decimal("0")
            total += vat_amount
            
            # Check if VAT is recoverable based on WREN status
            if self.calculator.is_vat_recoverable(tx.wren_status.value if tx.wren_status else "pending"):
                recoverable += vat_amount
            else:
                non_recoverable += vat_amount
        
        return {
            "total": total,
            "recoverable": recoverable,
            "non_recoverable": non_recoverable,
        }
    
    # ===========================================
    # VAT RECORD UPDATE
    # ===========================================
    
    async def update_vat_record(
        self,
        entity_id: uuid.UUID,
        year: int,
        month: int,
    ) -> VATRecord:
        """
        Update VAT record with calculated values from transactions/invoices.
        """
        vat_record = await self.get_or_create_vat_period(entity_id, year, month)
        
        # Calculate VAT
        vat_data = await self.calculate_period_vat(entity_id, year, month)
        
        # Update record
        vat_record.output_vat = Decimal(str(vat_data["output_vat"]))
        vat_record.input_vat_total = Decimal(str(vat_data["input_vat_total"]))
        vat_record.input_vat_recoverable = Decimal(str(vat_data["input_vat_recoverable"]))
        vat_record.input_vat_non_recoverable = Decimal(str(vat_data["input_vat_non_recoverable"]))
        vat_record.net_vat_payable = Decimal(str(vat_data["net_vat_payable"]))
        
        await self.db.commit()
        await self.db.refresh(vat_record)
        
        return vat_record
    
    async def mark_vat_filed(
        self,
        vat_record_id: uuid.UUID,
        entity_id: uuid.UUID,
    ) -> VATRecord:
        """Mark a VAT record as filed."""
        result = await self.db.execute(
            select(VATRecord)
            .where(VATRecord.id == vat_record_id)
            .where(VATRecord.entity_id == entity_id)
        )
        vat_record = result.scalar_one_or_none()
        
        if not vat_record:
            raise ValueError("VAT record not found")
        
        vat_record.is_filed = True
        
        await self.db.commit()
        await self.db.refresh(vat_record)
        
        return vat_record
    
    # ===========================================
    # VAT RETURN PREPARATION
    # ===========================================
    
    async def prepare_vat_return(
        self,
        entity_id: uuid.UUID,
        year: int,
        month: int,
    ) -> Dict[str, Any]:
        """
        Prepare VAT return data for filing.
        
        Returns structured data for FIRS VAT return form.
        """
        # Update VAT record with latest calculations
        vat_record = await self.update_vat_record(entity_id, year, month)
        
        # Get invoice breakdown
        invoice_summary = await self._get_invoice_summary_for_period(
            entity_id,
            vat_record.period_start,
            vat_record.period_end,
        )
        
        # Get expense breakdown
        expense_summary = await self._get_expense_summary_for_period(
            entity_id,
            vat_record.period_start,
            vat_record.period_end,
        )
        
        return {
            "period": {
                "year": year,
                "month": month,
                "start_date": vat_record.period_start.isoformat(),
                "end_date": vat_record.period_end.isoformat(),
            },
            "output_vat": {
                "total": float(vat_record.output_vat),
                "invoices": invoice_summary,
            },
            "input_vat": {
                "total": float(vat_record.input_vat_total),
                "recoverable": float(vat_record.input_vat_recoverable),
                "non_recoverable": float(vat_record.input_vat_non_recoverable),
                "expenses": expense_summary,
            },
            "net_vat_payable": float(vat_record.net_vat_payable),
            "is_refund_due": vat_record.net_vat_payable < 0,
            "is_filed": vat_record.is_filed,
            "vat_record_id": str(vat_record.id),
        }
    
    async def _get_invoice_summary_for_period(
        self,
        entity_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """Get invoice summary for VAT return."""
        result = await self.db.execute(
            select(
                func.count(Invoice.id).label("count"),
                func.coalesce(func.sum(Invoice.subtotal), 0).label("subtotal"),
                func.coalesce(func.sum(Invoice.vat_amount), 0).label("vat"),
                func.coalesce(func.sum(Invoice.total_amount), 0).label("total"),
            )
            .where(Invoice.entity_id == entity_id)
            .where(Invoice.invoice_date >= start_date)
            .where(Invoice.invoice_date <= end_date)
            .where(Invoice.status.not_in([InvoiceStatus.DRAFT, InvoiceStatus.CANCELLED]))
        )
        row = result.one()
        
        return {
            "invoice_count": row.count,
            "subtotal": float(row.subtotal),
            "vat_amount": float(row.vat),
            "total_amount": float(row.total),
        }
    
    async def _get_expense_summary_for_period(
        self,
        entity_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """Get expense summary for VAT return."""
        result = await self.db.execute(
            select(
                func.count(Transaction.id).label("count"),
                func.coalesce(func.sum(Transaction.amount), 0).label("amount"),
                func.coalesce(func.sum(Transaction.vat_amount), 0).label("vat"),
            )
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_date >= start_date)
            .where(Transaction.transaction_date <= end_date)
            .where(Transaction.transaction_type == TransactionType.EXPENSE)
        )
        row = result.one()
        
        return {
            "expense_count": row.count,
            "total_amount": float(row.amount),
            "total_vat": float(row.vat),
        }


# Add missing import
from datetime import timedelta
