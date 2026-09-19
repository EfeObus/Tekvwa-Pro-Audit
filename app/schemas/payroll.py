"""
Tekvwa Pro Audit - Payroll Schemas

Pydantic schemas for payroll requests and responses.
Nigerian compliance ready.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any, Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


# ===========================================
# ENUMS AS LITERALS
# ===========================================

EmploymentTypeEnum = Literal[
    "FULL_TIME", "PART_TIME", "CONTRACT", "INTERN", "PROBATION", "CONSULTANT"
]

EmploymentStatusEnum = Literal[
    "ACTIVE", "INACTIVE", "TERMINATED", "RESIGNED", "RETIRED", "SUSPENDED", "ON_LEAVE"
]

PayrollStatusEnum = Literal[
    "DRAFT", "PENDING_APPROVAL", "APPROVED", "PROCESSING", "COMPLETED", "PAID", "CANCELLED"
]

PayrollFrequencyEnum = Literal["WEEKLY", "BI_WEEKLY", "MONTHLY"]

GenderEnum = Literal["male", "female", "other"]
MaritalStatusEnum = Literal["single", "married", "divorced", "widowed"]


# ===========================================
# BANK NAMES
# ===========================================

BankNameEnum = Literal[
    "access_bank", "citibank", "ecobank", "fidelity_bank", "first_bank", "fcmb",
    "globus_bank", "gtbank", "heritage_bank", "keystone_bank", "polaris_bank",
    "providus_bank", "stanbic_ibtc", "standard_chartered", "sterling_bank",
    "suntrust_bank", "titan_trust_bank", "union_bank", "uba", "unity_bank",
    "wema_bank", "zenith_bank", "opay", "palmpay", "kuda", "moniepoint",
    "vfd_microfinance", "other"
]

PFAEnum = Literal[
    "aiico_pension", "apt_pension", "arm_pension", "crusader_sterling",
    "fidelity_pension", "first_guarantee", "iei_anchor", "leadway_pensure",
    "nlpc_pension", "nupemco", "oak_pensions", "pal_pensions", "premium_pension",
    "radix_pension", "sigma_pensions", "stanbic_ibtc_pension", "tangerine_apt",
    "trustfund_pensions", "veritas_glanvills", "other"
]


# ===========================================
# BANK ACCOUNT SCHEMAS
# ===========================================

class BankAccountBase(BaseModel):
    """Base bank account schema."""
    bank_name: BankNameEnum
    bank_name_other: Optional[str] = None
    account_number: str = Field(..., min_length=10, max_length=10)
    account_name: str = Field(..., max_length=200)
    bank_code: Optional[str] = None
    is_primary: bool = True


class BankAccountCreate(BankAccountBase):
    """Create bank account request."""
    pass


class BankAccountResponse(BankAccountBase):
    """Bank account response."""
    id: UUID
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


# ===========================================
# EMPLOYEE SCHEMAS
# ===========================================

class EmployeeBase(BaseModel):
    """Base employee schema."""
    employee_id: str = Field(..., min_length=1, max_length=50)
    title: Optional[str] = None
    first_name: str = Field(..., min_length=1, max_length=100)
    middle_name: Optional[str] = None
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    phone_number: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[GenderEnum] = None
    marital_status: Optional[MaritalStatusEnum] = None
    
    # Address
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    lga: Optional[str] = None
    
    # Nigerian compliance
    nin: Optional[str] = Field(None, max_length=20)
    bvn: Optional[str] = Field(None, max_length=20)
    tin: Optional[str] = Field(None, max_length=20)
    tax_state: Optional[str] = None
    
    # Pension
    pension_pin: Optional[str] = Field(None, max_length=30)
    pfa: Optional[PFAEnum] = None
    pfa_other: Optional[str] = None
    pension_start_date: Optional[date] = None
    is_pension_exempt: bool = False
    
    # NHF
    nhf_number: Optional[str] = Field(None, max_length=30)
    is_nhf_exempt: bool = False
    
    # Employment
    employment_type: EmploymentTypeEnum = "FULL_TIME"
    employment_status: EmploymentStatusEnum = "ACTIVE"
    department: Optional[str] = None
    job_title: Optional[str] = None
    job_grade: Optional[str] = None
    hire_date: date
    confirmation_date: Optional[date] = None
    
    # Pay structure
    payroll_frequency: PayrollFrequencyEnum = "MONTHLY"
    currency: str = "NGN"
    basic_salary: Decimal = Field(..., ge=0)
    housing_allowance: Decimal = Field(default=Decimal("0"), ge=0)
    transport_allowance: Decimal = Field(default=Decimal("0"), ge=0)
    meal_allowance: Decimal = Field(default=Decimal("0"), ge=0)
    utility_allowance: Decimal = Field(default=Decimal("0"), ge=0)
    other_allowances: Optional[Dict[str, float]] = None
    
    # Leave
    annual_leave_days: int = Field(default=21, ge=0)
    sick_leave_days: int = Field(default=12, ge=0)
    
    # Emergency contact
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relationship: Optional[str] = None
    
    notes: Optional[str] = None


class EmployeeCreate(EmployeeBase):
    """Create employee request."""
    bank_accounts: Optional[List[BankAccountCreate]] = None


class EmployeeUpdate(BaseModel):
    """Update employee request."""
    title: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[GenderEnum] = None
    marital_status: Optional[MaritalStatusEnum] = None
    
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    lga: Optional[str] = None
    
    nin: Optional[str] = None
    bvn: Optional[str] = None
    tin: Optional[str] = None
    tax_state: Optional[str] = None
    
    pension_pin: Optional[str] = None
    pfa: Optional[PFAEnum] = None
    pfa_other: Optional[str] = None
    pension_start_date: Optional[date] = None
    is_pension_exempt: Optional[bool] = None
    
    nhf_number: Optional[str] = None
    is_nhf_exempt: Optional[bool] = None
    
    employment_type: Optional[EmploymentTypeEnum] = None
    employment_status: Optional[EmploymentStatusEnum] = None
    department: Optional[str] = None
    job_title: Optional[str] = None
    job_grade: Optional[str] = None
    confirmation_date: Optional[date] = None
    termination_date: Optional[date] = None
    termination_reason: Optional[str] = None
    
    payroll_frequency: Optional[PayrollFrequencyEnum] = None
    basic_salary: Optional[Decimal] = None
    housing_allowance: Optional[Decimal] = None
    transport_allowance: Optional[Decimal] = None
    meal_allowance: Optional[Decimal] = None
    utility_allowance: Optional[Decimal] = None
    other_allowances: Optional[Dict[str, float]] = None
    
    annual_leave_days: Optional[int] = None
    sick_leave_days: Optional[int] = None
    
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relationship: Optional[str] = None
    
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class EmployeeResponse(EmployeeBase):
    """Employee response."""
    id: UUID
    entity_id: UUID
    user_id: Optional[UUID] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    # Computed fields
    full_name: Optional[str] = None
    monthly_gross: Optional[Decimal] = None
    annual_gross: Optional[Decimal] = None
    pensionable_earnings: Optional[Decimal] = None
    
    # Related
    bank_accounts: List[BankAccountResponse] = []
    
    class Config:
        from_attributes = True


class EmployeeSummary(BaseModel):
    """Minimal employee info for lists."""
    id: UUID
    employee_id: str
    full_name: str
    email: str
    department: Optional[str] = None
    job_title: Optional[str] = None
    employment_status: str
    monthly_gross: Decimal
    
    class Config:
        from_attributes = True


# ===========================================
# PAYROLL RUN SCHEMAS
# ===========================================

class PayrollRunCreate(BaseModel):
    """Create payroll run request."""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    frequency: PayrollFrequencyEnum = "MONTHLY"
    period_start: date
    period_end: date
    payment_date: date
    
    # Optional: specify employee IDs to include (defaults to all active employees)
    employee_ids: Optional[List[UUID]] = None
    
    @model_validator(mode='after')
    def validate_dates(self):
        if self.period_end < self.period_start:
            raise ValueError("Period end must be after period start")
        if self.payment_date < self.period_end:
            raise ValueError("Payment date must be on or after period end")
        return self


class PayrollRunUpdate(BaseModel):
    """Update payroll run request."""
    name: Optional[str] = None
    description: Optional[str] = None
    payment_date: Optional[date] = None
    status: Optional[PayrollStatusEnum] = None


class PayrollRunSummary(BaseModel):
    """Payroll run summary for lists."""
    id: UUID
    payroll_code: str
    name: str
    status: str
    period_start: date
    period_end: date
    payment_date: date
    total_employees: int
    total_gross_pay: Decimal
    total_net_pay: Decimal
    total_deductions: Decimal
    created_at: datetime
    
    class Config:
        from_attributes = True


class PayrollRunResponse(PayrollRunSummary):
    """Full payroll run response."""
    entity_id: UUID
    description: Optional[str] = None
    frequency: str
    total_employer_contributions: Decimal
    total_paye: Decimal
    total_pension_employee: Decimal
    total_pension_employer: Decimal
    total_nhf: Decimal
    total_nsitf: Decimal
    total_itf: Decimal
    approved_by_id: Optional[UUID] = None
    approved_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ===========================================
# PAYSLIP SCHEMAS
# ===========================================

class PayslipItemResponse(BaseModel):
    """Payslip line item."""
    id: UUID
    item_type: str
    category: str
    name: str
    description: Optional[str] = None
    amount: Decimal
    is_percentage: bool
    percentage_value: Optional[Decimal] = None
    base_amount: Optional[Decimal] = None
    is_statutory: bool
    is_taxable: bool
    is_pensionable: bool
    
    class Config:
        from_attributes = True


class PayslipSummary(BaseModel):
    """Payslip summary for lists."""
    id: UUID
    payslip_number: str
    employee_id: UUID
    employee_name: str
    employee_staff_id: str
    gross_pay: Decimal
    total_deductions: Decimal
    net_pay: Decimal
    is_paid: bool
    
    class Config:
        from_attributes = True


class PayslipResponse(BaseModel):
    """Full payslip response."""
    id: UUID
    payroll_run_id: UUID
    employee_id: UUID
    payslip_number: str
    
    # Employee info
    employee_name: Optional[str] = None
    employee_staff_id: Optional[str] = None
    department: Optional[str] = None
    job_title: Optional[str] = None
    
    # Period
    days_in_period: int
    days_worked: int
    days_absent: int
    
    # Earnings
    basic_salary: Decimal
    housing_allowance: Decimal
    transport_allowance: Decimal
    other_earnings: Decimal
    gross_pay: Decimal
    
    # Deductions
    paye_tax: Decimal
    pension_employee: Decimal
    nhf: Decimal
    other_deductions: Decimal
    total_deductions: Decimal
    
    # Net
    net_pay: Decimal
    
    # Employer contributions
    pension_employer: Decimal
    nsitf: Decimal
    itf: Decimal
    
    # Tax breakdown
    consolidated_relief: Decimal
    taxable_income: Decimal
    tax_calculation: Optional[Dict[str, Any]] = None
    
    # Detailed breakdown
    earnings_breakdown: Optional[Dict[str, Any]] = None
    deductions_breakdown: Optional[Dict[str, Any]] = None
    
    # Payment
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    account_name: Optional[str] = None
    is_paid: bool
    paid_at: Optional[datetime] = None
    
    is_emailed: bool
    notes: Optional[str] = None
    
    # Items
    items: List[PayslipItemResponse] = []
    
    created_at: datetime
    
    class Config:
        from_attributes = True


# ===========================================
# PAYROLL CALCULATION SCHEMAS
# ===========================================

class SalaryBreakdownRequest(BaseModel):
    """Request for salary breakdown calculation."""
    basic_salary: Decimal = Field(..., gt=0)
    housing_allowance: Decimal = Field(default=Decimal("0"), ge=0)
    transport_allowance: Decimal = Field(default=Decimal("0"), ge=0)
    meal_allowance: Decimal = Field(default=Decimal("0"), ge=0)
    utility_allowance: Decimal = Field(default=Decimal("0"), ge=0)
    other_allowances: Optional[Dict[str, float]] = None
    
    # Optional overrides
    pension_percentage: Decimal = Field(default=Decimal("8"), ge=0, le=20)
    is_pension_exempt: bool = False
    is_nhf_exempt: bool = False


class SalaryBreakdownResponse(BaseModel):
    """Salary breakdown calculation result."""
    # Earnings
    basic_salary: Decimal
    housing_allowance: Decimal
    transport_allowance: Decimal
    meal_allowance: Decimal = Decimal("0")
    utility_allowance: Decimal = Decimal("0")
    other_allowances: Dict[str, Decimal]
    monthly_gross: Decimal
    annual_gross: Decimal
    
    # Reliefs (Annual)
    consolidated_relief_allowance: Decimal
    pension_relief: Decimal
    nhf_relief: Decimal
    total_reliefs: Decimal
    
    # Taxable
    annual_taxable_income: Decimal
    monthly_taxable_income: Decimal
    
    # Tax (PAYE)
    annual_paye: Decimal
    monthly_paye: Decimal
    paye_breakdown: List[Dict[str, Any]]
    effective_tax_rate: Decimal
    
    # Deductions (Monthly)
    pension_employee: Decimal
    nhf: Decimal
    total_monthly_deductions: Decimal
    
    # Net
    monthly_net_pay: Decimal
    annual_net_pay: Decimal
    
    # Employer contributions (Monthly)
    pension_employer: Decimal
    nsitf: Decimal
    itf: Decimal
    total_employer_cost: Decimal


# ===========================================
# STATUTORY REMITTANCE SCHEMAS
# ===========================================

class StatutoryRemittanceCreate(BaseModel):
    """Create statutory remittance record."""
    remittance_type: Literal["paye", "pension", "nhf", "nsitf", "itf"]
    period_month: int = Field(..., ge=1, le=12)
    period_year: int = Field(..., ge=2020)
    amount_due: Decimal
    due_date: date
    payroll_run_id: Optional[UUID] = None


class StatutoryRemittanceUpdate(BaseModel):
    """Update remittance payment status."""
    amount_paid: Optional[Decimal] = None
    is_paid: Optional[bool] = None
    payment_date: Optional[date] = None
    payment_reference: Optional[str] = None
    receipt_number: Optional[str] = None
    notes: Optional[str] = None


class StatutoryRemittanceResponse(BaseModel):
    """Statutory remittance response."""
    id: UUID
    entity_id: UUID
    payroll_run_id: Optional[UUID] = None
    remittance_type: str
    period_month: int
    period_year: int
    amount_due: Decimal
    amount_paid: Decimal
    due_date: date
    is_paid: bool
    payment_date: Optional[date] = None
    payment_reference: Optional[str] = None
    receipt_number: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


# ===========================================
# DASHBOARD & REPORTS
# ===========================================

class PayrollDashboardStats(BaseModel):
    """Payroll dashboard statistics."""
    total_employees: int
    active_employees: int
    total_monthly_payroll: Decimal
    total_annual_payroll: Decimal
    average_salary: Decimal
    
    # Current month
    current_month_gross: Decimal
    current_month_net: Decimal
    current_month_paye: Decimal
    current_month_pension: Decimal
    current_month_nhf: Decimal
    
    # By department
    department_breakdown: List[Dict[str, Any]]
    
    # Recent payroll runs
    recent_payroll_runs: List[PayrollRunSummary]
    
    # Pending remittances
    pending_remittances: List[StatutoryRemittanceResponse]


class PayrollReportRequest(BaseModel):
    """Request for payroll report."""
    report_type: Literal[
        "payroll_summary", "paye_schedule", "pension_schedule",
        "nhf_schedule", "bank_schedule", "variance_report"
    ]
    period_start: date
    period_end: date
    department: Optional[str] = None
    format: Literal["json", "csv", "pdf", "excel"] = "json"


class BankScheduleItem(BaseModel):
    """Bank schedule item for payments."""
    employee_id: str
    employee_name: str
    bank_name: str
    account_number: str
    account_name: str
    amount: Decimal
    narration: str


class BankScheduleResponse(BaseModel):
    """Bank schedule for salary payments."""
    payroll_code: str
    payment_date: date
    total_amount: Decimal
    total_employees: int
    items: List[BankScheduleItem]


# ===========================================
# BULK OPERATIONS
# ===========================================

class BulkEmployeeImport(BaseModel):
    """Bulk employee import from CSV/Excel."""
    employees: List[EmployeeCreate]


class BulkPayAdjustment(BaseModel):
    """Bulk pay adjustment."""
    employee_ids: List[UUID]
    adjustment_type: Literal["percentage", "fixed"]
    adjustment_value: Decimal
    apply_to: Literal["basic", "gross", "all_allowances"]
    effective_date: date
    notes: Optional[str] = None


# ===========================================
# COMMON RESPONSES
# ===========================================

class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    success: bool = True


class PaginatedResponse(BaseModel):
    """Paginated response wrapper."""
    items: List[Any]
    total: int
    page: int
    per_page: int
    pages: int


# ===========================================
# LOAN SCHEMAS
# ===========================================

LoanTypeEnum = Literal[
    "loan", "salary_advance", "cooperative", "equipment", "educational", "emergency", "other"
]

LoanStatusEnum = Literal[
    "pending", "approved", "active", "completed", "cancelled", "defaulted"
]


class LoanBase(BaseModel):
    """Base loan schema."""
    loan_type: LoanTypeEnum = "loan"
    description: Optional[str] = None
    principal_amount: Decimal = Field(..., gt=0)
    interest_rate: Decimal = Field(default=Decimal("0.00"), ge=0)
    tenure_months: int = Field(..., gt=0, le=60)
    start_date: date
    notes: Optional[str] = None


class LoanCreate(LoanBase):
    """Create loan request."""
    employee_id: UUID


class LoanUpdate(BaseModel):
    """Update loan request."""
    description: Optional[str] = None
    status: Optional[LoanStatusEnum] = None
    notes: Optional[str] = None


class LoanResponse(LoanBase):
    """Loan response schema."""
    id: UUID
    entity_id: UUID
    employee_id: UUID
    loan_reference: str
    total_amount: Decimal
    monthly_deduction: Decimal
    total_paid: Decimal
    balance: Decimal
    end_date: date
    status: str
    is_active: bool
    approved_by_id: Optional[UUID] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # Employee info (optional, for list views)
    employee_name: Optional[str] = None
    employee_id_code: Optional[str] = None
    
    class Config:
        from_attributes = True


class LoanSummary(BaseModel):
    """Loan summary for dashboard."""
    total_loans: int
    active_loans: int
    total_disbursed: Decimal
    total_outstanding: Decimal
    total_collected: Decimal

