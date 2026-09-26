"""
Tekvwa Pro Audit - Payroll Models

Complete payroll system with Nigerian compliance:
- PAYE (Pay As You Earn) - Personal Income Tax
- Pension (Contributory Pension Scheme - PenCom regulated)
- NHF (National Housing Fund - 2.5% of basic)
- NSITF (Nigeria Social Insurance Trust Fund)
- ITF (Industrial Training Fund - 1% for companies with 5+ employees)
- Development Levy

Nigerian Statutory Deductions:
1. Employee Pension: 8% of Basic, Housing, Transport
2. Employer Pension: 10% of Basic, Housing, Transport
3. NHF: 2.5% of Basic Salary (Employee contribution)
4. NSITF: 1% of monthly payroll (Employer contribution)
5. ITF: 1% of annual payroll (Employer contribution for 5+ employees)
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Optional, List

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
    Enum as SQLEnum, JSON, UniqueConstraint, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, AuditMixin

if TYPE_CHECKING:
    from app.models.entity import BusinessEntity
    from app.models.user import User


# ===========================================
# ENUMS
# ===========================================

class EmploymentType(str, Enum):
    """Employment type classification."""
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    CONTRACT = "CONTRACT"
    INTERN = "INTERN"
    PROBATION = "PROBATION"
    CONSULTANT = "CONSULTANT"


class EmploymentStatus(str, Enum):
    """Employment status."""
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    TERMINATED = "TERMINATED"
    RESIGNED = "RESIGNED"
    RETIRED = "RETIRED"
    SUSPENDED = "SUSPENDED"
    ON_LEAVE = "ON_LEAVE"


class PayrollStatus(str, Enum):
    """Payroll processing status."""
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class PayrollFrequency(str, Enum):
    """Payroll frequency."""
    WEEKLY = "WEEKLY"
    BI_WEEKLY = "BI_WEEKLY"
    MONTHLY = "MONTHLY"


class PayItemType(str, Enum):
    """Type of pay item."""
    EARNING = "earning"
    DEDUCTION = "deduction"
    EMPLOYER_CONTRIBUTION = "employer_contribution"
    REIMBURSEMENT = "reimbursement"


class PayItemCategory(str, Enum):
    """Category of pay items for Nigerian compliance."""
    # Earnings
    BASIC_SALARY = "basic_salary"
    HOUSING_ALLOWANCE = "housing_allowance"
    TRANSPORT_ALLOWANCE = "transport_allowance"
    MEAL_ALLOWANCE = "meal_allowance"
    UTILITY_ALLOWANCE = "utility_allowance"
    LEAVE_ALLOWANCE = "leave_allowance"
    MEDICAL_ALLOWANCE = "medical_allowance"
    CLOTHING_ALLOWANCE = "clothing_allowance"
    FURNITURE_ALLOWANCE = "furniture_allowance"
    ENTERTAINMENT_ALLOWANCE = "entertainment_allowance"
    DOMESTIC_ALLOWANCE = "domestic_allowance"
    CAR_ALLOWANCE = "car_allowance"
    HARDSHIP_ALLOWANCE = "hardship_allowance"
    OVERTIME = "overtime"
    BONUS = "bonus"
    COMMISSION = "commission"
    THIRTEENTH_MONTH = "thirteenth_month"
    GRATUITY = "gratuity"
    ARREARS = "arrears"
    OTHER_EARNING = "other_earning"
    
    # Statutory Deductions
    PAYE_TAX = "paye_tax"
    PENSION_EMPLOYEE = "pension_employee"
    NHF = "nhf"
    
    # Voluntary Deductions
    LOAN_REPAYMENT = "loan_repayment"
    COOPERATIVE_DEDUCTION = "cooperative_deduction"
    SALARY_ADVANCE = "salary_advance"
    UNION_DUES = "union_dues"
    INSURANCE_PREMIUM = "insurance_premium"
    OTHER_DEDUCTION = "other_deduction"
    
    # Employer Contributions (not deducted from employee)
    PENSION_EMPLOYER = "pension_employer"
    NSITF = "nsitf"
    ITF = "itf"
    HMO = "hmo"
    GROUP_LIFE = "group_life"


class BankName(str, Enum):
    """Nigerian banks."""
    ACCESS_BANK = "access_bank"
    CITIBANK = "citibank"
    ECOBANK = "ecobank"
    FIDELITY_BANK = "fidelity_bank"
    FIRST_BANK = "first_bank"
    FCMB = "fcmb"
    GLOBUS_BANK = "globus_bank"
    GTBANK = "gtbank"
    HERITAGE_BANK = "heritage_bank"
    KEYSTONE_BANK = "keystone_bank"
    POLARIS_BANK = "polaris_bank"
    PROVIDUS_BANK = "providus_bank"
    STANBIC_IBTC = "stanbic_ibtc"
    STANDARD_CHARTERED = "standard_chartered"
    STERLING_BANK = "sterling_bank"
    SUNTRUST_BANK = "suntrust_bank"
    TITAN_TRUST_BANK = "titan_trust_bank"
    UNION_BANK = "union_bank"
    UBA = "uba"
    UNITY_BANK = "unity_bank"
    WEMA_BANK = "wema_bank"
    ZENITH_BANK = "zenith_bank"
    OPAY = "opay"
    PALMPAY = "palmpay"
    KUDA = "kuda"
    MONIEPOINT = "moniepoint"
    VFD_MICROFINANCE = "vfd_microfinance"
    OTHER = "other"


class PensionFundAdministrator(str, Enum):
    """Nigerian PFAs (Pension Fund Administrators)."""
    AIICO_PENSION = "aiico_pension"
    APT_PENSION = "apt_pension"
    ARM_PENSION = "arm_pension"
    CRUSADER_STERLING = "crusader_sterling"
    FIDELITY_PENSION = "fidelity_pension"
    FIRST_GUARANTEE = "first_guarantee"
    IEI_ANCHOR = "iei_anchor"
    LEADWAY_PENSURE = "leadway_pensure"
    NLPC_PENSION = "nlpc_pension"
    NUPEMCO = "nupemco"
    OAK_PENSIONS = "oak_pensions"
    PAL_PENSIONS = "pal_pensions"
    PREMIUM_PENSION = "premium_pension"
    RADIX_PENSION = "radix_pension"
    SIGMA_PENSIONS = "sigma_pensions"
    STANBIC_IBTC_PENSION = "stanbic_ibtc_pension"
    TANGERINE_APT = "tangerine_apt"
    TRUSTFUND_PENSIONS = "trustfund_pensions"
    VERITAS_GLANVILLS = "veritas_glanvills"
    OTHER = "other"


# ===========================================
# EMPLOYEE MODEL
# ===========================================

class Employee(BaseModel, AuditMixin):
    """
    Employee model for payroll management.
    
    Nigerian Compliance Fields:
    - TIN (Tax Identification Number) - Required for PAYE
    - Pension PIN (RSA Pin) - Required for pension contributions
    - NHF Number - Required for NHF contributions
    - BVN - Bank Verification Number
    - NIN - National Identification Number
    """
    
    __tablename__ = "employees"

    # Overrides AuditMixin's created_by_id/updated_by_id — this table's migration added a real
    # FK to users.id that the mixin doesn't declare (docs/REMEDIATION_LOG.md, Finding 49).
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )
    updated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )

    # Entity relationship
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Link to user account (optional - employee may not have system access)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Employee identification
    employee_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Internal employee ID/staff number",
    )
    
    # Personal Information
    title: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    middle_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    marital_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # Address
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lga: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Nigerian Identification & Compliance
    nin: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
        comment="National Identification Number",
    )
    bvn: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
        comment="Bank Verification Number",
    )
    tin: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
        comment="Tax Identification Number (required for PAYE)",
    )
    tax_state: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        comment="State where PAYE tax is remitted",
    )
    
    # Pension
    pension_pin: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True,
        comment="RSA PIN (Retirement Savings Account Pin)",
    )
    pfa: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        comment="Pension Fund Administrator",
    )
    pfa_other: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        comment="PFA name if 'other' is selected",
    )
    pension_start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_pension_exempt: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="Exempt from pension contributions",
    )
    
    # NHF
    nhf_number: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True,
        comment="National Housing Fund Number",
    )
    is_nhf_exempt: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="Exempt from NHF contributions",
    )
    
    # Employment Details
    employment_type: Mapped[str] = mapped_column(
        String(30),
        default=EmploymentType.FULL_TIME.value,
        nullable=False,
    )
    employment_status: Mapped[str] = mapped_column(
        String(30),
        default=EmploymentStatus.ACTIVE.value,
        nullable=False,
    )
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    job_title: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    job_grade: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    hire_date: Mapped[date] = mapped_column(Date, nullable=False)
    confirmation_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    termination_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    termination_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Pay Structure
    payroll_frequency: Mapped[str] = mapped_column(
        String(30),
        default=PayrollFrequency.MONTHLY.value,
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(String(3), default="NGN", nullable=False)
    
    # Base Salary Components
    basic_salary: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        comment="Monthly basic salary",
    )
    housing_allowance: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        comment="Monthly housing allowance",
    )
    transport_allowance: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        comment="Monthly transport allowance",
    )
    meal_allowance: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        comment="Monthly meal allowance",
    )
    utility_allowance: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        comment="Monthly utility allowance",
    )
    
    # Optional Allowances (stored as JSON for flexibility)
    other_allowances: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True,
        comment="Other monthly allowances as key-value pairs",
    )
    
    # Leave Entitlements
    annual_leave_days: Mapped[int] = mapped_column(
        Integer, default=21, nullable=False,
        comment="Annual leave entitlement in days",
    )
    sick_leave_days: Mapped[int] = mapped_column(
        Integer, default=12, nullable=False,
        comment="Sick leave entitlement in days",
    )
    
    # Emergency Contact
    emergency_contact_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    emergency_contact_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    emergency_contact_relationship: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Next of Kin (for statutory records)
    next_of_kin_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    next_of_kin_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    next_of_kin_relationship: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    next_of_kin_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 2026 Tax Reform - Rent Relief
    annual_rent_paid: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
        comment="Annual rent for 2026 Rent Relief calculation",
    )
    has_life_insurance: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    monthly_insurance_premium: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Leave Balance Tracking
    leave_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2),
        default=Decimal("0.00"),
        nullable=False,
        comment="Current leave balance in days",
    )
    
    # Metadata
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    entity: Mapped["BusinessEntity"] = relationship(
        "BusinessEntity",
        back_populates="employees",
    )
    bank_accounts: Mapped[List["EmployeeBankAccount"]] = relationship(
        "EmployeeBankAccount",
        back_populates="employee",
        cascade="all, delete-orphan",
    )
    payslips: Mapped[List["Payslip"]] = relationship(
        "Payslip",
        back_populates="employee",
        cascade="all, delete-orphan",
    )
    loans: Mapped[List["EmployeeLoan"]] = relationship(
        "EmployeeLoan",
        back_populates="employee",
        cascade="all, delete-orphan",
    )
    leaves: Mapped[List["EmployeeLeave"]] = relationship(
        "EmployeeLeave",
        back_populates="employee",
        cascade="all, delete-orphan",
    )
    
    __table_args__ = (
        UniqueConstraint('entity_id', 'employee_id', name='uq_employee_entity_id'),
    )
    
    @property
    def full_name(self) -> str:
        """Get employee's full name."""
        parts = [self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        parts.append(self.last_name)
        return " ".join(parts)
    
    @property
    def monthly_gross(self) -> Decimal:
        """Calculate monthly gross salary."""
        gross = self.basic_salary + self.housing_allowance + self.transport_allowance
        if self.other_allowances:
            for value in self.other_allowances.values():
                gross += Decimal(str(value))
        return gross
    
    @property
    def annual_gross(self) -> Decimal:
        """Calculate annual gross salary."""
        return self.monthly_gross * 12
    
    @property
    def pensionable_earnings(self) -> Decimal:
        """
        Calculate pensionable earnings (Basic + Housing + Transport).
        Per PenCom regulations.
        """
        return self.basic_salary + self.housing_allowance + self.transport_allowance
    
    def __repr__(self) -> str:
        return f"<Employee(id={self.id}, employee_id={self.employee_id}, name={self.full_name})>"


# ===========================================
# EMPLOYEE BANK ACCOUNT
# ===========================================

class EmployeeBankAccount(BaseModel):
    """Employee bank account for salary payments."""
    
    __tablename__ = "employee_bank_accounts"
    
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    bank_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    bank_name_other: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        comment="Bank name if 'other' is selected",
    )
    account_number: Mapped[str] = mapped_column(
        String(20), nullable=False,
    )
    account_name: Mapped[str] = mapped_column(
        String(200), nullable=False,
    )
    bank_code: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True,
        comment="CBN bank code for transfers",
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
        comment="Primary account for salary payment",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )
    
    # Relationship
    employee: Mapped["Employee"] = relationship(
        "Employee", back_populates="bank_accounts",
    )
    
    def __repr__(self) -> str:
        return f"<EmployeeBankAccount(employee_id={self.employee_id}, bank={self.bank_name})>"


# ===========================================
# PAYROLL RUN
# ===========================================

class PayrollRun(BaseModel, AuditMixin):
    """
    Payroll run/batch for processing employee salaries.
    
    A payroll run represents a single pay period processing.
    """
    
    __tablename__ = "payroll_runs"

    # Overrides AuditMixin's created_by_id/updated_by_id (Finding 49, docs/REMEDIATION_LOG.md).
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )
    updated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )

    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Payroll identification
    payroll_code: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="Unique payroll run code e.g., PAY-2026-01",
    )
    name: Mapped[str] = mapped_column(
        String(200), nullable=False,
        comment="Descriptive name e.g., 'January 2026 Payroll'",
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Pay Period
    frequency: Mapped[str] = mapped_column(
        String(30),
        default=PayrollFrequency.MONTHLY.value,
        nullable=False,
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    payment_date: Mapped[date] = mapped_column(
        Date, nullable=False,
        comment="Date employees will be paid",
    )
    
    # Status
    status: Mapped[str] = mapped_column(
        String(30),
        default=PayrollStatus.DRAFT.value,
        nullable=False,
    )
    
    # Summary (calculated)
    total_employees: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    total_gross_pay: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    total_deductions: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    total_net_pay: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    total_employer_contributions: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Statutory Totals
    total_paye: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    total_pension_employee: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    total_pension_employer: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    total_nhf: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    total_nsitf: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    total_itf: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Approval workflow
    approved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    locked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Relationships
    entity: Mapped["BusinessEntity"] = relationship(
        "BusinessEntity",
        back_populates="payroll_runs",
    )
    payslips: Mapped[List["Payslip"]] = relationship(
        "Payslip",
        back_populates="payroll_run",
        cascade="all, delete-orphan",
    )
    
    __table_args__ = (
        UniqueConstraint('entity_id', 'payroll_code', name='uq_payroll_entity_code'),
    )
    
    def __repr__(self) -> str:
        return f"<PayrollRun(id={self.id}, code={self.payroll_code}, status={self.status})>"


# ===========================================
# PAYSLIP
# ===========================================

class Payslip(BaseModel):
    """
    Individual employee payslip for a payroll run.
    """
    
    __tablename__ = "payslips"
    
    payroll_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payroll_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Payslip Reference
    payslip_number: Mapped[str] = mapped_column(
        String(50), nullable=False,
    )
    
    # Days worked (for pro-rata calculations)
    days_in_period: Mapped[int] = mapped_column(
        Integer, default=30, nullable=False,
    )
    days_worked: Mapped[int] = mapped_column(
        Integer, default=30, nullable=False,
    )
    days_absent: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    
    # Earnings
    basic_salary: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    housing_allowance: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    transport_allowance: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    meal_allowance: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    utility_allowance: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    overtime_pay: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    bonus: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    other_earnings: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    gross_pay: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )

    # Deductions
    paye_tax: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    pension_employee: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    nhf: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    loan_deduction: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    salary_advance_deduction: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    cooperative_deduction: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    union_dues: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    other_deductions: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    total_deductions: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Net Pay
    net_pay: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Employer Contributions (not deducted from employee)
    pension_employer: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    nsitf: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
        comment="NSITF contribution (1% of payroll - employer)",
    )
    itf: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
        comment="ITF contribution (1% of annual payroll / 12 - employer)",
    )
    hmo_employer: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    group_life_insurance: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )

    # Relief calculations (for PAYE)
    consolidated_relief: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    rent_relief: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    pension_relief: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    nhf_relief: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    taxable_income: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Detailed breakdown stored as JSON
    earnings_breakdown: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True,
    )
    deductions_breakdown: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True,
    )
    tax_calculation: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True,
        comment="Detailed PAYE calculation breakdown",
    )
    
    # Payment details
    bank_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    account_number: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    account_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    paid_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    payment_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Email/notifications
    is_emailed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    emailed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    payroll_run: Mapped["PayrollRun"] = relationship(
        "PayrollRun", back_populates="payslips",
    )
    employee: Mapped["Employee"] = relationship(
        "Employee", back_populates="payslips",
    )
    items: Mapped[List["PayslipItem"]] = relationship(
        "PayslipItem",
        back_populates="payslip",
        cascade="all, delete-orphan",
    )
    
    __table_args__ = (
        UniqueConstraint('payroll_run_id', 'employee_id', name='uq_payslip_run_employee'),
    )
    
    def __repr__(self) -> str:
        return f"<Payslip(id={self.id}, number={self.payslip_number}, net={self.net_pay})>"


# ===========================================
# PAYSLIP ITEM (LINE ITEM)
# ===========================================

class PayslipItem(BaseModel):
    """
    Individual earning or deduction line item on a payslip.
    """
    
    __tablename__ = "payslip_items"
    
    payslip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payslips.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    item_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    
    name: Mapped[str] = mapped_column(
        String(200), nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    
    # For percentage-based calculations
    is_percentage: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    percentage_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=5, scale=2), nullable=True,
    )
    base_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=15, scale=2), nullable=True,
        comment="Base amount the percentage was calculated on",
    )
    
    # Is this a statutory/mandatory item?
    is_statutory: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    is_taxable: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
        comment="Whether this earning is taxable for PAYE",
    )
    is_pensionable: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="Whether included in pensionable earnings",
    )
    
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    
    # Relationship
    payslip: Mapped["Payslip"] = relationship(
        "Payslip", back_populates="items",
    )
    
    def __repr__(self) -> str:
        return f"<PayslipItem(type={self.item_type}, name={self.name}, amount={self.amount})>"


# ===========================================
# STATUTORY REMITTANCE TRACKING
# ===========================================

class StatutoryRemittance(BaseModel, AuditMixin):
    """
    Track statutory remittances (PAYE, Pension, NHF, NSITF, ITF).
    """
    
    __tablename__ = "statutory_remittances"

    # Overrides AuditMixin's created_by_id/updated_by_id (Finding 49, docs/REMEDIATION_LOG.md).
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )
    updated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )

    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    payroll_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payroll_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    remittance_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="Type: paye, pension, nhf, nsitf, itf",
    )
    
    # Period
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Amount
    amount_due: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        nullable=False,
    )
    amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    
    # Due date
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Payment status
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    payment_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    payment_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Receipt/evidence
    receipt_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    receipt_file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    __table_args__ = (
        UniqueConstraint(
            'entity_id', 'remittance_type', 'period_month', 'period_year',
            name='uq_remittance_entity_type_period'
        ),
    )
    
    def __repr__(self) -> str:
        return f"<StatutoryRemittance(type={self.remittance_type}, period={self.period_month}/{self.period_year})>"


# ===========================================
# EMPLOYEE LOAN ENUMS
# ===========================================

class LoanType(str, Enum):
    """Type of loan or advance."""
    LOAN = "loan"
    SALARY_ADVANCE = "salary_advance"
    COOPERATIVE = "cooperative"
    EQUIPMENT = "equipment"
    EDUCATIONAL = "educational"
    EMERGENCY = "emergency"
    OTHER = "other"


class LoanStatus(str, Enum):
    """Loan status."""
    PENDING = "pending"
    APPROVED = "approved"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DEFAULTED = "defaulted"


class LeaveType(str, Enum):
    """Type of leave."""
    ANNUAL = "annual"
    SICK = "sick"
    MATERNITY = "maternity"
    PATERNITY = "paternity"
    STUDY = "study"
    COMPASSIONATE = "compassionate"
    UNPAID = "unpaid"
    SABBATICAL = "sabbatical"
    OTHER = "other"


class LeaveStatus(str, Enum):
    """Leave request status."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


# ===========================================
# EMPLOYEE LOANS & ADVANCES
# ===========================================

class EmployeeLoan(BaseModel, AuditMixin):
    """
    Track employee loans and salary advances with deduction schedules.
    """
    
    __tablename__ = "employee_loans"

    # Overrides AuditMixin's created_by_id only — this table's migration added a FK for
    # created_by_id but NOT updated_by_id (Finding 49, docs/REMEDIATION_LOG.md). updated_by_id
    # intentionally keeps inheriting the mixin's plain (no-FK) column. That column genuinely
    # exists on the live table (added by migration, see Finding 50 in docs/REMEDIATION_LOG.md,
    # 2026-09-25) -- a since-corrected earlier assumption here read "no FK" as "no column at all."
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )

    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    loan_type: Mapped[str] = mapped_column(
        String(50),
        default=LoanType.LOAN.value,
        nullable=False,
    )
    
    loan_reference: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="Unique loan reference e.g., LN-2026-001",
    )
    
    description: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True,
    )
    
    # Loan Amount
    principal_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
        comment="Original loan amount",
    )
    interest_rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2),
        default=Decimal("0.00"),
        nullable=False,
        comment="Annual interest rate percentage",
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
        comment="Principal + Total Interest",
    )
    
    # Deduction Schedule
    monthly_deduction: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    tenure_months: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Balance Tracking
    total_paid: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    
    # Dates
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Status
    status: Mapped[str] = mapped_column(
        String(30),
        default=LoanStatus.PENDING.value,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Approval
    approved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    employee: Mapped["Employee"] = relationship(
        "Employee", back_populates="loans",
    )
    repayments: Mapped[List["LoanRepayment"]] = relationship(
        "LoanRepayment",
        back_populates="loan",
        cascade="all, delete-orphan",
    )
    
    def __repr__(self) -> str:
        return f"<EmployeeLoan(ref={self.loan_reference}, amount={self.principal_amount}, balance={self.balance})>"


# ===========================================
# LOAN REPAYMENTS
# ===========================================

class LoanRepayment(BaseModel):
    """
    Individual loan repayment records (from payroll or manual).
    """
    
    __tablename__ = "loan_repayments"
    
    loan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employee_loans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    payslip_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payslips.id", ondelete="SET NULL"),
        nullable=True,
        comment="Link to payslip if deducted via payroll",
    )
    
    repayment_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    principal_portion: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    interest_portion: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0.00"),
        nullable=False,
    )
    balance_after: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    is_manual: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="True if not deducted via payroll",
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationship
    loan: Mapped["EmployeeLoan"] = relationship(
        "EmployeeLoan", back_populates="repayments",
    )
    
    def __repr__(self) -> str:
        return f"<LoanRepayment(loan_id={self.loan_id}, amount={self.amount}, date={self.repayment_date})>"


# ===========================================
# EMPLOYEE LEAVES
# ===========================================

class EmployeeLeave(BaseModel):
    """
    Track employee leave requests and approvals.
    """
    
    __tablename__ = "employee_leaves"
    
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    leave_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    days_requested: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2),
        nullable=False,
    )
    days_approved: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=5, scale=2),
        nullable=True,
    )
    
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    status: Mapped[str] = mapped_column(
        String(30),
        default=LeaveStatus.PENDING.value,
        nullable=False,
    )
    
    is_paid: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
        comment="Whether this is paid leave",
    )
    
    # Review
    reviewed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationship
    employee: Mapped["Employee"] = relationship(
        "Employee", back_populates="leaves",
    )
    
    def __repr__(self) -> str:
        return f"<EmployeeLeave(employee_id={self.employee_id}, type={self.leave_type}, status={self.status})>"


# ===========================================
# PAYROLL SETTINGS (Per Entity)
# ===========================================

class PayrollSettings(BaseModel):
    """
    Entity-level payroll configuration and settings.
    """
    
    __tablename__ = "payroll_settings"
    
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    
    # Company Info for Payslips
    company_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    company_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    company_logo_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Tax Settings
    tax_state: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        comment="State where PAYE is remitted",
    )
    tax_office: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    employer_tin: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # Pension Settings
    pfa_name: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        comment="Default PFA for new employees",
    )
    pension_employee_rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2),
        default=Decimal("8.00"),
        nullable=False,
    )
    pension_employer_rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2),
        default=Decimal("10.00"),
        nullable=False,
    )
    
    # NHF Settings
    nhf_rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2),
        default=Decimal("2.50"),
        nullable=False,
    )
    
    # NSITF/ITF Settings
    nsitf_rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2),
        default=Decimal("1.00"),
        nullable=False,
    )
    itf_rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2),
        default=Decimal("1.00"),
        nullable=False,
    )
    itf_applicable: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="True if company has 5+ employees or ₦50M+ turnover",
    )
    
    # Payment Settings
    default_payment_day: Mapped[int] = mapped_column(
        Integer, default=25, nullable=False,
    )
    prorate_new_employees: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )
    
    # Approval Workflow
    require_approval: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )
    auto_lock_after_days: Mapped[int] = mapped_column(
        Integer, default=30, nullable=False,
        comment="Days after payment date to lock payroll for audit",
    )
    
    # Payslip Settings
    payslip_template: Mapped[str] = mapped_column(
        String(50), default="standard", nullable=False,
    )
    email_payslips: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )
    
    def __repr__(self) -> str:
        return f"<PayrollSettings(entity_id={self.entity_id})>"

