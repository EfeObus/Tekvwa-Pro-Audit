"""
Tekvwa Pro Audit - Compliance Penalty Tracker (2026 Tax Reform)

Tracks and calculates penalties under the Nigeria 2026 Tax Reform Act.

Penalty Schedule:
- Late Filing: ₦100,000 (first month) + ₦50,000 (each subsequent month)
- Unregistered Vendor Contract: ₦5,000,000
- E-Invoice Non-Compliance: Various penalties per NRS regulations
- B2C Reporting Late: Penalties per 24-hour window violations

This module helps businesses:
1. Track potential penalties before they occur
2. Calculate cumulative penalties for late filings
3. Generate penalty liability reports
4. Provide early warning alerts
"""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.models.base import BaseModel


class PenaltyType(str, Enum):
    """Types of penalties under 2026 Tax Reform."""
    LATE_FILING = "late_filing"                    # ₦100K first month, ₦50K subsequent
    UNREGISTERED_VENDOR = "unregistered_vendor"    # ₦5,000,000
    B2C_LATE_REPORTING = "b2c_late_reporting"      # 24-hour window violation
    E_INVOICE_NONCOMPLIANCE = "e_invoice_noncompliance"  # NRS violations
    INVALID_TIN = "invalid_tin"                     # Using invalid TIN
    MISSING_RECORDS = "missing_records"             # Failure to maintain digital records
    NRS_ACCESS_DENIAL = "nrs_access_denial"         # Denying NRS technology access
    VAT_NON_REMITTANCE = "vat_non_remittance"       # Late VAT remittance
    PAYE_NON_REMITTANCE = "paye_non_remittance"     # Late PAYE remittance
    WHT_NON_REMITTANCE = "wht_non_remittance"       # Late WHT remittance


class PenaltyStatus(str, Enum):
    """Status of a penalty."""
    POTENTIAL = "potential"      # Warning - penalty may occur
    INCURRED = "incurred"        # Penalty has been incurred
    PAID = "paid"                # Penalty has been paid
    WAIVED = "waived"            # Penalty was waived by authorities
    DISPUTED = "disputed"        # Under dispute with NRS


# Penalty rates and amounts per 2026 Tax Reform
PENALTY_SCHEDULE = {
    PenaltyType.LATE_FILING: {
        "first_month": Decimal("100000"),      # ₦100,000
        "subsequent_month": Decimal("50000"),   # ₦50,000 per month
        "description": "Failure to file returns on time",
    },
    PenaltyType.UNREGISTERED_VENDOR: {
        "fixed_amount": Decimal("5000000"),     # ₦5,000,000
        "description": "Awarding contracts to entities not registered for tax",
    },
    PenaltyType.B2C_LATE_REPORTING: {
        "per_transaction": Decimal("10000"),    # ₦10,000 per transaction
        "max_daily": Decimal("500000"),         # ₦500,000 max per day
        "description": "Failure to report B2C transactions within 24 hours",
    },
    PenaltyType.E_INVOICE_NONCOMPLIANCE: {
        "per_invoice": Decimal("50000"),        # ₦50,000 per invoice
        "description": "Non-compliance with e-invoicing requirements",
    },
    PenaltyType.INVALID_TIN: {
        "per_occurrence": Decimal("25000"),     # ₦25,000 per occurrence
        "description": "Use of invalid TIN in transactions",
    },
    PenaltyType.MISSING_RECORDS: {
        "per_year": Decimal("100000"),          # ₦100,000 per year
        "description": "Failure to maintain verifiable digital records",
    },
    PenaltyType.NRS_ACCESS_DENIAL: {
        "fixed_amount": Decimal("1000000"),     # ₦1,000,000
        "description": "Denying NRS access to deploy technology for tax assessment",
    },
    PenaltyType.VAT_NON_REMITTANCE: {
        "percentage": Decimal("10"),            # 10% of tax due
        "monthly_interest": Decimal("2"),       # 2% monthly interest
        "description": "Late VAT remittance",
    },
    PenaltyType.PAYE_NON_REMITTANCE: {
        "percentage": Decimal("10"),            # 10% of tax due
        "monthly_interest": Decimal("2"),       # 2% monthly interest
        "description": "Late PAYE remittance",
    },
    PenaltyType.WHT_NON_REMITTANCE: {
        "percentage": Decimal("10"),            # 10% of tax due
        "monthly_interest": Decimal("2"),       # 2% monthly interest
        "description": "Late WHT remittance",
    },
}


@dataclass
class PenaltyCalculation:
    """Result of penalty calculation."""
    penalty_type: PenaltyType
    base_amount: Decimal
    additional_amount: Decimal
    total_amount: Decimal
    months_late: int
    description: str
    breakdown: List[Dict[str, Any]]


class PenaltyRecord(BaseModel):
    """
    Database model for tracking compliance penalties.
    """
    
    __tablename__ = "penalty_records"
    
    # Entity
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Penalty Details
    penalty_type: Mapped[PenaltyType] = mapped_column(
        SQLEnum(PenaltyType),
        nullable=False,
        index=True,
    )
    status: Mapped[PenaltyStatus] = mapped_column(
        SQLEnum(PenaltyStatus),
        default=PenaltyStatus.POTENTIAL,
        nullable=False,
    )
    
    # Amounts
    base_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    additional_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0"),
        nullable=False,
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    
    # Dates
    incurred_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    paid_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    
    # Related Filing/Transaction
    related_filing_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    related_filing_period: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    related_transaction_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Description
    description: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Payment
    payment_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Calculation Breakdown (JSON)
    calculation_breakdown: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    def __repr__(self) -> str:
        return f"<PenaltyRecord(id={self.id}, type={self.penalty_type}, amount={self.total_amount})>"


class CompliancePenaltyService:
    """
    Service for calculating and tracking compliance penalties.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def calculate_late_filing_penalty(
        self,
        original_due_date: date,
        filing_date: Optional[date] = None,
    ) -> PenaltyCalculation:
        """
        Calculate late filing penalty.
        
        Rate: ₦100,000 for first month + ₦50,000 for each subsequent month
        
        Args:
            original_due_date: Original filing deadline
            filing_date: Actual filing date (defaults to today)
        
        Returns:
            PenaltyCalculation with breakdown
        """
        filing_date = filing_date or date.today()
        
        if filing_date <= original_due_date:
            return PenaltyCalculation(
                penalty_type=PenaltyType.LATE_FILING,
                base_amount=Decimal("0"),
                additional_amount=Decimal("0"),
                total_amount=Decimal("0"),
                months_late=0,
                description="Filing is on time - no penalty",
                breakdown=[],
            )
        
        # Calculate months late
        days_late = (filing_date - original_due_date).days
        months_late = max(1, (days_late + 29) // 30)  # Round up to months
        
        # Calculate penalty
        first_month = PENALTY_SCHEDULE[PenaltyType.LATE_FILING]["first_month"]
        subsequent_month = PENALTY_SCHEDULE[PenaltyType.LATE_FILING]["subsequent_month"]
        
        breakdown = [
            {"month": 1, "amount": float(first_month), "description": "First month penalty"},
        ]
        
        additional = Decimal("0")
        for month in range(2, months_late + 1):
            additional += subsequent_month
            breakdown.append({
                "month": month,
                "amount": float(subsequent_month),
                "description": f"Month {month} penalty",
            })
        
        total = first_month + additional
        
        return PenaltyCalculation(
            penalty_type=PenaltyType.LATE_FILING,
            base_amount=first_month,
            additional_amount=additional,
            total_amount=total,
            months_late=months_late,
            description=f"Late filing penalty: {months_late} month(s) late",
            breakdown=breakdown,
        )
    
    def calculate_unregistered_vendor_penalty(
        self,
        contract_amount: Decimal,
    ) -> PenaltyCalculation:
        """
        Calculate penalty for awarding contract to unregistered vendor.
        
        Fixed penalty: ₦5,000,000
        
        Args:
            contract_amount: Value of the contract awarded
        
        Returns:
            PenaltyCalculation
        """
        penalty = PENALTY_SCHEDULE[PenaltyType.UNREGISTERED_VENDOR]["fixed_amount"]
        
        return PenaltyCalculation(
            penalty_type=PenaltyType.UNREGISTERED_VENDOR,
            base_amount=penalty,
            additional_amount=Decimal("0"),
            total_amount=penalty,
            months_late=0,
            description=f"Penalty for awarding ₦{contract_amount:,.2f} contract to unregistered vendor",
            breakdown=[{
                "type": "fixed_penalty",
                "amount": float(penalty),
                "description": "Fixed penalty for unregistered vendor contract",
            }],
        )
    
    def calculate_b2c_late_reporting_penalty(
        self,
        unreported_transactions: int,
        transaction_dates: List[date],
    ) -> PenaltyCalculation:
        """
        Calculate penalty for late B2C transaction reporting.
        
        Rate: ₦10,000 per transaction, max ₦500,000 per day
        
        Args:
            unreported_transactions: Number of transactions not reported within 24 hours
            transaction_dates: Dates of the transactions
        
        Returns:
            PenaltyCalculation
        """
        per_transaction = PENALTY_SCHEDULE[PenaltyType.B2C_LATE_REPORTING]["per_transaction"]
        max_daily = PENALTY_SCHEDULE[PenaltyType.B2C_LATE_REPORTING]["max_daily"]
        
        # Group by date and apply daily cap
        from collections import Counter
        date_counts = Counter(transaction_dates)
        
        total = Decimal("0")
        breakdown = []
        
        for trans_date, count in date_counts.items():
            daily_penalty = min(per_transaction * count, max_daily)
            total += daily_penalty
            breakdown.append({
                "date": trans_date.isoformat(),
                "transactions": count,
                "penalty": float(daily_penalty),
                "capped": daily_penalty == max_daily,
            })
        
        return PenaltyCalculation(
            penalty_type=PenaltyType.B2C_LATE_REPORTING,
            base_amount=total,
            additional_amount=Decimal("0"),
            total_amount=total,
            months_late=0,
            description=f"B2C late reporting penalty for {unreported_transactions} transactions",
            breakdown=breakdown,
        )
    
    def calculate_tax_remittance_penalty(
        self,
        penalty_type: PenaltyType,
        tax_amount: Decimal,
        due_date: date,
        payment_date: Optional[date] = None,
    ) -> PenaltyCalculation:
        """
        Calculate penalty for late tax remittance (VAT, PAYE, WHT).
        
        Rate: 10% of tax due + 2% monthly interest
        
        Args:
            penalty_type: Type of tax (VAT, PAYE, WHT)
            tax_amount: Amount of tax due
            due_date: Original due date
            payment_date: Actual payment date (defaults to today)
        
        Returns:
            PenaltyCalculation
        """
        if penalty_type not in [
            PenaltyType.VAT_NON_REMITTANCE,
            PenaltyType.PAYE_NON_REMITTANCE,
            PenaltyType.WHT_NON_REMITTANCE,
        ]:
            raise ValueError(f"Invalid penalty type for tax remittance: {penalty_type}")
        
        payment_date = payment_date or date.today()
        
        if payment_date <= due_date:
            return PenaltyCalculation(
                penalty_type=penalty_type,
                base_amount=Decimal("0"),
                additional_amount=Decimal("0"),
                total_amount=Decimal("0"),
                months_late=0,
                description="Payment on time - no penalty",
                breakdown=[],
            )
        
        schedule = PENALTY_SCHEDULE[penalty_type]
        
        # Base penalty (10% of tax)
        base_penalty = tax_amount * (schedule["percentage"] / 100)
        
        # Calculate months late
        days_late = (payment_date - due_date).days
        months_late = max(1, (days_late + 29) // 30)
        
        # Monthly interest
        monthly_rate = schedule["monthly_interest"] / 100
        interest = tax_amount * monthly_rate * months_late
        
        total = base_penalty + interest
        
        return PenaltyCalculation(
            penalty_type=penalty_type,
            base_amount=base_penalty,
            additional_amount=interest,
            total_amount=total,
            months_late=months_late,
            description=f"Late {penalty_type.value.replace('_', ' ')} penalty",
            breakdown=[
                {"type": "base_penalty", "amount": float(base_penalty), "rate": "10%"},
                {"type": "interest", "amount": float(interest), "rate": f"2% x {months_late} months"},
            ],
        )
    
    async def create_penalty_record(
        self,
        entity_id: uuid.UUID,
        calculation: PenaltyCalculation,
        related_filing_type: Optional[str] = None,
        related_filing_period: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> PenaltyRecord:
        """
        Create a penalty record in the database.
        """
        record = PenaltyRecord(
            entity_id=entity_id,
            penalty_type=calculation.penalty_type,
            status=PenaltyStatus.INCURRED,
            base_amount=calculation.base_amount,
            additional_amount=calculation.additional_amount,
            total_amount=calculation.total_amount,
            incurred_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            related_filing_type=related_filing_type,
            related_filing_period=related_filing_period,
            description=calculation.description,
            notes=notes,
            calculation_breakdown={"breakdown": calculation.breakdown},
        )
        
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        
        return record
    
    async def get_entity_penalties(
        self,
        entity_id: uuid.UUID,
        status: Optional[PenaltyStatus] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[PenaltyRecord]:
        """
        Get penalty records for an entity.
        """
        query = select(PenaltyRecord).where(PenaltyRecord.entity_id == entity_id)
        
        if status:
            query = query.where(PenaltyRecord.status == status)
        if start_date:
            query = query.where(PenaltyRecord.incurred_date >= start_date)
        if end_date:
            query = query.where(PenaltyRecord.incurred_date <= end_date)
        
        query = query.order_by(PenaltyRecord.incurred_date.desc())
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_penalty_summary(
        self,
        entity_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Get summary of penalties for an entity.
        """
        penalties = await self.get_entity_penalties(entity_id)
        
        total_incurred = sum(
            p.total_amount for p in penalties 
            if p.status == PenaltyStatus.INCURRED
        )
        total_paid = sum(
            p.total_amount for p in penalties 
            if p.status == PenaltyStatus.PAID
        )
        total_outstanding = sum(
            p.total_amount for p in penalties 
            if p.status in [PenaltyStatus.INCURRED, PenaltyStatus.DISPUTED]
        )
        
        by_type = {}
        for p in penalties:
            type_name = p.penalty_type.value
            if type_name not in by_type:
                by_type[type_name] = {"count": 0, "total": Decimal("0")}
            by_type[type_name]["count"] += 1
            by_type[type_name]["total"] += p.total_amount
        
        return {
            "total_penalties": len(penalties),
            "total_incurred": float(total_incurred),
            "total_paid": float(total_paid),
            "total_outstanding": float(total_outstanding),
            "by_type": {k: {"count": v["count"], "total": float(v["total"])} for k, v in by_type.items()},
            "penalties": [
                {
                    "id": str(p.id),
                    "type": p.penalty_type.value,
                    "status": p.status.value,
                    "amount": float(p.total_amount),
                    "incurred_date": p.incurred_date.isoformat(),
                    "description": p.description,
                }
                for p in penalties[:10]  # Latest 10
            ],
        }
    
    def get_penalty_rates(self) -> Dict[str, Any]:
        """
        Get current penalty rates for display.
        """
        return {
            penalty_type.value: {
                **{k: float(v) if isinstance(v, Decimal) else v for k, v in rates.items()},
            }
            for penalty_type, rates in PENALTY_SCHEDULE.items()
        }
