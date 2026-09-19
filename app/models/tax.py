"""
Tekvwa Pro Audit - Tax Models

Models for tax tracking (VAT, PAYE, CIT, WHT).
"""

import uuid
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class TaxPeriodType(str, Enum):
    """Tax period types."""
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUALLY = "annually"


class TaxPeriod(BaseModel):
    """
    Tax period model for tracking tax filing periods.
    """
    
    __tablename__ = "tax_periods"
    
    # Entity
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Period
    period_type: Mapped[TaxPeriodType] = mapped_column(
        SQLEnum(TaxPeriodType),
        nullable=False,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="1-12 for monthly, NULL for annual",
    )
    quarter: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="1-4 for quarterly, NULL otherwise",
    )
    
    # Dates
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Status
    is_filed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    filed_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    
    def __repr__(self) -> str:
        return f"<TaxPeriod(id={self.id}, type={self.period_type}, year={self.year})>"


class VATRecord(BaseModel):
    """
    VAT record for tracking VAT liability per period.
    """
    
    __tablename__ = "vat_records"
    
    # Entity
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Period
    tax_period_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tax_periods.id", ondelete="SET NULL"),
        nullable=True,
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Output VAT (collected from sales)
    output_vat: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal("0.00"),
    )
    
    # Input VAT (paid on purchases)
    input_vat_total: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal("0.00"),
    )
    input_vat_recoverable: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        comment="VAT recoverable (WREN compliant expenses)",
    )
    input_vat_non_recoverable: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal("0.00"),
    )
    
    # Net VAT
    net_vat_payable: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        comment="Output VAT - Recoverable Input VAT",
    )
    
    # Filing
    is_filed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    def __repr__(self) -> str:
        return f"<VATRecord(id={self.id}, period={self.period_start} to {self.period_end})>"


class PAYERecord(BaseModel):
    """
    PAYE (Pay As You Earn) record for employee tax tracking.
    
    Uses Nigeria 2026 tax bands:
    - ₦0 - ₦800,000: 0%
    - ₦800,001 - ₦2,400,000: 15%
    - ₦2,400,001 - ₦4,800,000: 20%
    - ₦4,800,001 - ₦7,200,000: 25%
    - Above ₦7,200,000: 30%
    """
    
    __tablename__ = "paye_records"
    
    # Entity
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Employee (future: link to employee table)
    employee_name: Mapped[str] = mapped_column(String(255), nullable=False)
    employee_tin: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # Period
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Gross Income
    gross_salary: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    
    # Reliefs (Annual consolidated relief = ₦200,000 + 20% of gross)
    consolidated_relief: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal("0.00"),
    )
    pension_contribution: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal("0.00"),
    )
    nhf_contribution: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal("0.00"),
    )
    other_reliefs: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal("0.00"),
    )
    
    # Taxable Income
    taxable_income: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    
    # Tax Calculated
    paye_tax: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    
    # Net Pay
    net_pay: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    
    def __repr__(self) -> str:
        return f"<PAYERecord(id={self.id}, employee={self.employee_name}, tax={self.paye_tax})>"


class CITRecord(BaseModel):
    """
    Corporate Income Tax record.
    
    2026 Rates:
    - Small business (≤₦50M turnover): 0%
    - Medium business (₦50M-₦100M): 0% (with conditions)
    - Large business: 30%
    - 4% Development Levy for companies with turnover > ₦100M
    """
    
    __tablename__ = "cit_records"
    
    # Entity
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Tax Year
    tax_year: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Turnover
    gross_turnover: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
    )
    
    # Assessable Profit
    assessable_profit: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
    )
    
    # Tax Calculation
    cit_rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2),
        nullable=False,
        comment="0, 20, or 30 percent",
    )
    cit_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
    )
    
    # Development Levy (4% for companies > ₦100M turnover)
    development_levy_applicable: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    development_levy: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
        default=Decimal("0.00"),
    )
    
    # Total
    total_tax_liability: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
    )
    
    # Status
    is_filed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    def __repr__(self) -> str:
        return f"<CITRecord(id={self.id}, year={self.tax_year}, liability={self.total_tax_liability})>"


class WHTRecord(BaseModel):
    """
    Withholding Tax record.
    
    Small business exemption: Transactions under ₦2M exempt from WHT.
    """
    
    __tablename__ = "wht_records"
    
    # Entity
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Transaction Reference
    transaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Details
    vendor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    vendor_tin: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # Amounts
    gross_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    wht_rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2),
        nullable=False,
        comment="5% or 10% depending on category",
    )
    wht_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    
    # Exemption
    is_exempt: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="True if transaction < ₦2M (small business exemption)",
    )
    
    # Date
    deduction_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Remittance
    is_remitted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    remittance_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    
    def __repr__(self) -> str:
        return f"<WHTRecord(id={self.id}, vendor={self.vendor_name}, amount={self.wht_amount})>"
