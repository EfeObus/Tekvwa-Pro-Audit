"""
Tekvwa Pro Audit - Business Entity Model

Business entity model for multi-entity support within an organization.
"""

import uuid
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.user import UserEntityAccess
    from app.models.transaction import Transaction
    from app.models.invoice import Invoice
    from app.models.vendor import Vendor
    from app.models.customer import Customer
    from app.models.inventory import InventoryItem
    from app.models.notification import Notification
    from app.models.advanced_accounting import AccountingDimension
    from app.models.payroll import Employee, PayrollRun
    from app.models.bank_reconciliation import BankAccount
    from app.models.report_template import ReportTemplate


class BusinessType(str, Enum):
    """Business entity type for tax treatment."""
    BUSINESS_NAME = "business_name"      # Sole proprietorship - taxed under PIT
    LIMITED_COMPANY = "limited_company"  # Limited liability - taxed under CIT


class BusinessEntity(BaseModel):
    """
    Business Entity model - represents a single business/company.
    
    Each entity has its own ledger, transactions, invoices, etc.
    This enables multi-entity accounting within a single organization.
    """
    
    __tablename__ = "business_entities"
    
    # Organization
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    # Business Info
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tin: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        index=True,
        comment="Tax Identification Number",
    )
    rc_number: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="CAC Registration Number",
    )
    
    # Address
    address_line1: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lga: Mapped[Optional[str]] = mapped_column(
        String(100), 
        nullable=True, 
        comment="Local Government Area"
    )
    country: Mapped[str] = mapped_column(String(100), default="Nigeria", nullable=False)
    
    # Contact
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Financial Settings
    fiscal_year_start_month: Mapped[int] = mapped_column(
        Integer,
        default=1,  # January
        nullable=False,
        comment="Month when fiscal year starts (1-12)",
    )
    currency: Mapped[str] = mapped_column(String(3), default="NGN", nullable=False)
    
    # Tax Settings
    is_vat_registered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    vat_registration_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    annual_turnover_threshold: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="True if turnover <= ₦50M (0% CIT eligible)",
    )
    
    # 2026 Tax Reform - Business Type (PIT vs CIT)
    business_type: Mapped[BusinessType] = mapped_column(
        SQLEnum(BusinessType),
        default=BusinessType.LIMITED_COMPANY,
        nullable=False,
        comment="Business Name (PIT) or Limited Company (CIT)",
    )
    
    # 2026 Tax Reform - Development Levy Thresholds
    annual_turnover: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=True,
        comment="Annual turnover for Development Levy calculation",
    )
    fixed_assets_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=True,
        comment="Fixed assets value for Development Levy exemption",
    )
    is_development_levy_exempt: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Exempt if turnover <= ₦100M AND assets <= ₦250M",
    )
    
    # 2026 Tax Reform - B2C Real-time Reporting
    b2c_realtime_reporting_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Enable 24-hour NRS reporting for B2C transactions > ₦50,000",
    )
    b2c_reporting_threshold: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("50000.00"),
        nullable=False,
        comment="Threshold for B2C real-time reporting (default ₦50,000)",
    )
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="entities",
    )
    user_access: Mapped[List["UserEntityAccess"]] = relationship(
        "UserEntityAccess",
        back_populates="entity",
        cascade="all, delete-orphan",
    )
    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction",
        back_populates="entity",
        cascade="all, delete-orphan",
    )
    invoices: Mapped[List["Invoice"]] = relationship(
        "Invoice",
        back_populates="entity",
        cascade="all, delete-orphan",
    )
    vendors: Mapped[List["Vendor"]] = relationship(
        "Vendor",
        back_populates="entity",
        cascade="all, delete-orphan",
    )
    customers: Mapped[List["Customer"]] = relationship(
        "Customer",
        back_populates="entity",
        cascade="all, delete-orphan",
    )
    inventory_items: Mapped[List["InventoryItem"]] = relationship(
        "InventoryItem",
        back_populates="entity",
        cascade="all, delete-orphan",
    )
    notifications: Mapped[List["Notification"]] = relationship(
        "Notification",
        back_populates="entity",
        cascade="all, delete-orphan",
    )
    dimensions: Mapped[List["AccountingDimension"]] = relationship(
        "AccountingDimension",
        back_populates="entity",
        cascade="all, delete-orphan",
    )
    employees: Mapped[List["Employee"]] = relationship(
        "Employee",
        back_populates="entity",
        cascade="all, delete-orphan",
    )
    payroll_runs: Mapped[List["PayrollRun"]] = relationship(
        "PayrollRun",
        back_populates="entity",
        cascade="all, delete-orphan",
    )
    bank_accounts: Mapped[List["BankAccount"]] = relationship(
        "BankAccount",
        back_populates="entity",
        cascade="all, delete-orphan",
    )
    report_templates: Mapped[List["ReportTemplate"]] = relationship(
        "ReportTemplate",
        back_populates="entity",
        cascade="all, delete-orphan",
    )
    
    @property
    def full_address(self) -> str:
        """Get full formatted address."""
        parts = [
            self.address_line1,
            self.address_line2,
            self.city,
            self.state,
            self.country,
        ]
        return ", ".join(filter(None, parts))
    
    def __repr__(self) -> str:
        return f"<BusinessEntity(id={self.id}, name={self.name}, tin={self.tin})>"
