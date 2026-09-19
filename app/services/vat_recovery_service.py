"""
Tekvwa Pro Audit - VAT Recovery Service (2026 Reform)

Handles the Advanced Input VAT Recovery rules under the 2026 Act.

Key 2026 Changes:
- VAT on SERVICES is now recoverable (previously restricted)
- VAT on FIXED ASSETS/Capital Expenditure is now recoverable
- Recovery ONLY allowed if vendor provided valid NRS e-invoice (IRN)
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Optional, List, Dict, Any

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tax_2026 import VATRecoveryRecord, VATRecoveryType
from app.models.transaction import Transaction, TransactionType
from app.config import settings


class VATRecoveryService:
    """
    Service for managing Input VAT Recovery under 2026 rules.
    
    The 2026 Nigeria Tax Administration Act significantly expands
    recoverable input VAT categories:
    
    1. Stock-in-Trade (existing): VAT on goods purchased for resale
    2. Services (NEW): VAT on services consumed in business operations
    3. Capital Expenditure (NEW): VAT on fixed assets
    
    CRITICAL RULE: Recovery is ONLY allowed if the vendor provided
    a valid NRS e-invoice with IRN. Without IRN, VAT is non-recoverable.
    """
    
    VAT_RATE = Decimal("0.075")  # 7.5%
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def record_vat_recovery(
        self,
        entity_id: uuid.UUID,
        transaction_id: Optional[uuid.UUID],
        vat_amount: Decimal,
        recovery_type: VATRecoveryType,
        vendor_irn: Optional[str],
        transaction_date: date,
        description: Optional[str] = None,
        vendor_name: Optional[str] = None,
        vendor_tin: Optional[str] = None,
    ) -> VATRecoveryRecord:
        """
        Record a VAT recovery entry with IRN validation.
        
        The recovery is automatically flagged as non-recoverable
        if no valid vendor IRN is provided.
        """
        # Determine recoverability
        has_valid_irn = bool(vendor_irn and len(vendor_irn) > 5)
        is_recoverable = has_valid_irn
        
        non_recovery_reason = None
        if not has_valid_irn:
            non_recovery_reason = "Vendor did not provide valid NRS e-invoice (IRN required for input VAT recovery under 2026 Act)"
        
        record = VATRecoveryRecord(
            entity_id=entity_id,
            transaction_id=transaction_id,
            vat_amount=vat_amount,
            recovery_type=recovery_type,
            is_recoverable=is_recoverable,
            non_recovery_reason=non_recovery_reason,
            vendor_irn=vendor_irn,
            has_valid_irn=has_valid_irn,
            description=description,
            vendor_name=vendor_name,
            vendor_tin=vendor_tin,
            transaction_date=transaction_date,
            recovery_period_year=transaction_date.year,
            recovery_period_month=transaction_date.month,
        )
        
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        
        return record
    
    async def get_recovery_summary(
        self,
        entity_id: uuid.UUID,
        year: int,
        month: int,
    ) -> Dict[str, Any]:
        """
        Get VAT recovery summary for a period.
        
        Returns breakdown by:
        - Recovery type (stock-in-trade, services, capital)
        - Recoverable vs non-recoverable amounts
        """
        result = await self.db.execute(
            select(
                VATRecoveryRecord.recovery_type,
                VATRecoveryRecord.is_recoverable,
                func.sum(VATRecoveryRecord.vat_amount).label("total"),
                func.count(VATRecoveryRecord.id).label("count"),
            )
            .where(
                and_(
                    VATRecoveryRecord.entity_id == entity_id,
                    VATRecoveryRecord.recovery_period_year == year,
                    VATRecoveryRecord.recovery_period_month == month,
                )
            )
            .group_by(VATRecoveryRecord.recovery_type, VATRecoveryRecord.is_recoverable)
        )
        
        rows = result.all()
        
        # Build summary
        by_type = {
            VATRecoveryType.STOCK_IN_TRADE: {"recoverable": Decimal("0"), "non_recoverable": Decimal("0"), "count": 0},
            VATRecoveryType.SERVICES: {"recoverable": Decimal("0"), "non_recoverable": Decimal("0"), "count": 0},
            VATRecoveryType.CAPITAL_EXPENDITURE: {"recoverable": Decimal("0"), "non_recoverable": Decimal("0"), "count": 0},
        }
        
        total_recoverable = Decimal("0")
        total_non_recoverable = Decimal("0")
        
        for row in rows:
            recovery_type, is_recoverable, total, count = row
            if is_recoverable:
                by_type[recovery_type]["recoverable"] += total
                total_recoverable += total
            else:
                by_type[recovery_type]["non_recoverable"] += total
                total_non_recoverable += total
            by_type[recovery_type]["count"] += count
        
        return {
            "year": year,
            "month": month,
            "total_recoverable": float(total_recoverable),
            "total_non_recoverable": float(total_non_recoverable),
            "total_input_vat": float(total_recoverable + total_non_recoverable),
            "by_type": {
                "stock_in_trade": {
                    "recoverable": float(by_type[VATRecoveryType.STOCK_IN_TRADE]["recoverable"]),
                    "non_recoverable": float(by_type[VATRecoveryType.STOCK_IN_TRADE]["non_recoverable"]),
                    "count": by_type[VATRecoveryType.STOCK_IN_TRADE]["count"],
                },
                "services": {
                    "recoverable": float(by_type[VATRecoveryType.SERVICES]["recoverable"]),
                    "non_recoverable": float(by_type[VATRecoveryType.SERVICES]["non_recoverable"]),
                    "count": by_type[VATRecoveryType.SERVICES]["count"],
                    "note": "NEW under 2026 Act: Services VAT now recoverable",
                },
                "capital_expenditure": {
                    "recoverable": float(by_type[VATRecoveryType.CAPITAL_EXPENDITURE]["recoverable"]),
                    "non_recoverable": float(by_type[VATRecoveryType.CAPITAL_EXPENDITURE]["non_recoverable"]),
                    "count": by_type[VATRecoveryType.CAPITAL_EXPENDITURE]["count"],
                    "note": "NEW under 2026 Act: Capital assets VAT now recoverable",
                },
            },
        }
    
    async def get_non_recoverable_records(
        self,
        entity_id: uuid.UUID,
        year: Optional[int] = None,
        month: Optional[int] = None,
    ) -> List[VATRecoveryRecord]:
        """
        Get records flagged as non-recoverable.
        
        Useful for audit and identifying vendors not compliant with NRS e-invoicing.
        """
        query = select(VATRecoveryRecord).where(
            and_(
                VATRecoveryRecord.entity_id == entity_id,
                VATRecoveryRecord.is_recoverable == False,
            )
        )
        
        if year:
            query = query.where(VATRecoveryRecord.recovery_period_year == year)
        if month:
            query = query.where(VATRecoveryRecord.recovery_period_month == month)
        
        query = query.order_by(VATRecoveryRecord.transaction_date.desc())
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_vendors_without_irn(
        self,
        entity_id: uuid.UUID,
        year: int,
    ) -> List[Dict[str, Any]]:
        """
        Get list of vendors who didn't provide NRS e-invoices.
        
        This helps businesses identify non-compliant vendors
        and request proper e-invoices for VAT recovery.
        """
        result = await self.db.execute(
            select(
                VATRecoveryRecord.vendor_name,
                VATRecoveryRecord.vendor_tin,
                func.sum(VATRecoveryRecord.vat_amount).label("lost_vat"),
                func.count(VATRecoveryRecord.id).label("transaction_count"),
            )
            .where(
                and_(
                    VATRecoveryRecord.entity_id == entity_id,
                    VATRecoveryRecord.recovery_period_year == year,
                    VATRecoveryRecord.has_valid_irn == False,
                )
            )
            .group_by(VATRecoveryRecord.vendor_name, VATRecoveryRecord.vendor_tin)
            .order_by(func.sum(VATRecoveryRecord.vat_amount).desc())
        )
        
        rows = result.all()
        
        return [
            {
                "vendor_name": row.vendor_name or "Unknown Vendor",
                "vendor_tin": row.vendor_tin,
                "lost_vat_recovery": float(row.lost_vat),
                "transaction_count": row.transaction_count,
                "recommendation": "Request NRS-compliant e-invoice for future transactions",
            }
            for row in rows
        ]
    
    async def auto_classify_transaction(
        self,
        transaction: Transaction,
    ) -> VATRecoveryType:
        """
        Automatically classify a transaction for VAT recovery type.
        
        Uses transaction category and description to determine
        if it's stock-in-trade, service, or capital expenditure.
        """
        # Check if it's an expense
        if transaction.transaction_type != TransactionType.EXPENSE:
            raise ValueError("Only expenses can have input VAT recovery")
        
        description = (transaction.description or "").lower()
        
        # Capital expenditure keywords
        capital_keywords = [
            "equipment", "machinery", "vehicle", "computer", "furniture",
            "building", "property", "asset", "capital", "fixed asset",
            "office equipment", "plant", "tools", "software license",
        ]
        
        # Service keywords
        service_keywords = [
            "service", "consulting", "legal", "accounting", "audit",
            "maintenance", "repair", "professional", "training", "subscription",
            "hosting", "software as service", "saas", "rent", "utility",
            "electricity", "internet", "phone", "marketing", "advertising",
        ]
        
        for keyword in capital_keywords:
            if keyword in description:
                return VATRecoveryType.CAPITAL_EXPENDITURE
        
        for keyword in service_keywords:
            if keyword in description:
                return VATRecoveryType.SERVICES
        
        # Default to stock-in-trade for goods/inventory
        return VATRecoveryType.STOCK_IN_TRADE
    
    async def get_all_records(
        self,
        entity_id: uuid.UUID,
        year: Optional[int] = None,
        month: Optional[int] = None,
        recovery_type: Optional[VATRecoveryType] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[VATRecoveryRecord]:
        """Get all VAT recovery records with filters."""
        query = select(VATRecoveryRecord).where(
            VATRecoveryRecord.entity_id == entity_id
        )
        
        if year:
            query = query.where(VATRecoveryRecord.recovery_period_year == year)
        if month:
            query = query.where(VATRecoveryRecord.recovery_period_month == month)
        if recovery_type:
            query = query.where(VATRecoveryRecord.recovery_type == recovery_type)
        
        query = query.order_by(VATRecoveryRecord.transaction_date.desc())
        query = query.limit(limit).offset(offset)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
