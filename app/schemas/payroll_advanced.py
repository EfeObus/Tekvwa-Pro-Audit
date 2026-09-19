"""
Tekvwa Pro Audit - Advanced Payroll Schemas

Pydantic schemas for world-class payroll features:
- Compliance Status Engine
- Payroll Change Impact Preview
- Exception Engine
- Decision Logs
- YTD Ledger
- Opening Balance Import
- Payslip Explanations
- CTC Analytics
- What-If Simulator
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ===========================================
# COMPLIANCE STATUS SCHEMAS
# ===========================================

class ComplianceStatusItem(BaseModel):
    """Single remittance type compliance status."""
    remittance_type: Literal["paye", "pension", "nhf", "nsitf", "itf"]
    status: Literal["on_time", "overdue", "partially_paid", "penalty_risk", "not_due", "exempt"]
    amount_due: Decimal
    amount_paid: Decimal
    due_date: Optional[date] = None
    days_overdue: int = 0
    penalty_estimate: Decimal = Decimal("0.00")
    human_message: str = ""


class ComplianceSnapshotResponse(BaseModel):
    """Complete compliance snapshot response."""
    id: UUID
    entity_id: UUID
    period_month: int
    period_year: int
    
    # Status Items
    paye_status: ComplianceStatusItem
    pension_status: ComplianceStatusItem
    nhf_status: ComplianceStatusItem
    nsitf_status: ComplianceStatusItem
    itf_status: ComplianceStatusItem
    
    # Total Exposure
    total_penalty_exposure: Decimal
    
    # Summary
    overall_status: Literal["compliant", "at_risk", "overdue"]
    summary_message: str
    
    snapshot_date: datetime

    class Config:
        from_attributes = True


class ComplianceSnapshotCreate(BaseModel):
    """Create/update compliance snapshot."""
    period_month: int = Field(..., ge=1, le=12)
    period_year: int = Field(..., ge=2020, le=2050)
    paye_tax_state: Optional[str] = None
    
    @field_validator('period_month')
    @classmethod
    def validate_month(cls, v: int) -> int:
        if not 1 <= v <= 12:
            raise ValueError('Month must be between 1 and 12')
        return v


# ===========================================
# PAYROLL IMPACT PREVIEW SCHEMAS
# ===========================================

class VarianceDriver(BaseModel):
    """Single variance driver in impact preview."""
    category: Literal[
        "new_hires", "terminations", "salary_increase", "salary_decrease",
        "loan_repayment", "loan_completed", "leave_deduction", "tax_band_movement",
        "allowance_change", "arrears", "bonus", "other"
    ]
    description: str
    amount: Decimal
    affected_employees: int = 0


class PayrollImpactPreviewResponse(BaseModel):
    """Payroll impact preview before approval."""
    id: UUID
    payroll_run_id: UUID
    previous_payroll_id: Optional[UUID] = None
    
    # Current Totals
    current_gross: Decimal
    current_net: Decimal
    current_paye: Decimal
    current_employer_cost: Decimal
    current_employee_count: int
    
    # Previous Totals
    previous_gross: Decimal
    previous_net: Decimal
    previous_paye: Decimal
    previous_employer_cost: Decimal
    previous_employee_count: int
    
    # Variances
    gross_variance: Decimal
    gross_variance_percent: Decimal
    net_variance: Decimal
    paye_variance: Decimal
    employer_cost_variance: Decimal
    
    # Top 5 Variance Drivers
    variance_drivers: List[VarianceDriver]
    
    # New Hires / Terminations
    new_hires_count: int
    new_hires_cost: Decimal
    terminations_count: int
    terminations_savings: Decimal
    
    # Human-Readable Summary
    impact_summary: str
    
    generated_at: datetime

    class Config:
        from_attributes = True


class PayrollImpactPreviewRequest(BaseModel):
    """Request to generate impact preview."""
    payroll_run_id: UUID


# ===========================================
# PAYROLL EXCEPTION SCHEMAS
# ===========================================

class PayrollExceptionBase(BaseModel):
    """Base exception schema."""
    exception_code: Literal[
        "NEGATIVE_NET_PAY", "DUPLICATE_BVN", "DUPLICATE_ACCOUNT", "BELOW_MINIMUM_WAGE",
        "MISSING_TIN", "MISSING_PENSION_PIN", "MISSING_NHF_NUMBER", "MISSING_BANK_ACCOUNT",
        "ZERO_PAYE_HIGH_INCOME", "PENSION_BELOW_MINIMUM", "LARGE_VARIANCE",
        "BANK_ACCOUNT_MISMATCH", "NEW_HIRE_PRORATION", "EXIT_PRORATION",
        "SALARY_CHANGE", "TAX_BAND_MOVEMENT"
    ]
    severity: Literal["critical", "warning", "info"]
    title: str
    description: str
    related_field: Optional[str] = None
    current_value: Optional[str] = None
    expected_value: Optional[str] = None


class PayrollExceptionResponse(PayrollExceptionBase):
    """Exception response with acknowledgement status."""
    id: UUID
    payroll_run_id: UUID
    payslip_id: Optional[UUID] = None
    employee_id: Optional[UUID] = None
    employee_name: Optional[str] = None
    
    requires_acknowledgement: bool
    is_acknowledged: bool
    acknowledged_by_id: Optional[UUID] = None
    acknowledged_by_name: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    acknowledgement_note: Optional[str] = None
    
    is_resolved: bool
    resolved_at: Optional[datetime] = None
    
    created_at: datetime

    class Config:
        from_attributes = True


class AcknowledgeExceptionRequest(BaseModel):
    """Request to acknowledge an exception."""
    acknowledgement_note: Optional[str] = None


class ExceptionSummary(BaseModel):
    """Summary of exceptions for a payroll run."""
    payroll_run_id: UUID
    total_exceptions: int
    critical_count: int
    warning_count: int
    info_count: int
    unacknowledged_count: int
    can_approve: bool
    blocking_exceptions: List[PayrollExceptionResponse]


# ===========================================
# DECISION LOG SCHEMAS
# ===========================================

class DecisionLogCreate(BaseModel):
    """Create a new decision log entry."""
    decision_type: Literal["approval", "adjustment", "exception_override", "note"]
    category: Literal["payroll", "salary", "deduction", "exception", "approval", "other"]
    title: str = Field(..., max_length=255)
    description: str
    context_data: Optional[Dict[str, Any]] = None
    payroll_run_id: Optional[UUID] = None
    payslip_id: Optional[UUID] = None
    employee_id: Optional[UUID] = None


class DecisionLogResponse(BaseModel):
    """Decision log response."""
    id: UUID
    entity_id: UUID
    payroll_run_id: Optional[UUID] = None
    payslip_id: Optional[UUID] = None
    employee_id: Optional[UUID] = None
    
    decision_type: str
    category: str
    title: str
    description: str
    context_data: Dict[str, Any]
    
    created_by_id: UUID
    created_by_name: str
    created_by_role: str
    created_at: datetime
    
    is_locked: bool
    content_hash: str
    
    # Frontend convenience fields (extracted from context_data)
    employee_name: Optional[str] = None
    original_value: Optional[float] = None
    new_value: Optional[float] = None
    justification: Optional[str] = None
    impact_preview: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class DecisionLogListResponse(BaseModel):
    """List of decision logs."""
    logs: List[DecisionLogResponse]
    total: int
    page: int
    page_size: int


# ===========================================
# YTD LEDGER SCHEMAS
# ===========================================

class YTDLedgerResponse(BaseModel):
    """YTD payroll ledger for an employee."""
    id: UUID
    entity_id: UUID
    employee_id: UUID
    employee_name: Optional[str] = None
    tax_year: int
    
    # YTD Earnings
    ytd_gross: Decimal
    ytd_basic: Decimal
    ytd_housing: Decimal
    ytd_transport: Decimal
    ytd_other_earnings: Decimal
    
    # YTD Deductions
    ytd_paye: Decimal
    ytd_pension_employee: Decimal
    ytd_nhf: Decimal
    ytd_other_deductions: Decimal
    ytd_total_deductions: Decimal
    
    # YTD Net
    ytd_net: Decimal
    
    # YTD Employer Contributions
    ytd_pension_employer: Decimal
    ytd_nsitf: Decimal
    ytd_itf: Decimal
    
    # Total CTC
    ytd_total_employer_cost: Decimal
    
    months_processed: int
    last_updated: datetime
    
    # Opening Balance Info
    has_opening_balance: bool
    opening_balance_date: Optional[date] = None

    class Config:
        from_attributes = True


class YTDLedgerSummary(BaseModel):
    """Summary of YTD ledger for entity."""
    entity_id: UUID
    tax_year: int
    total_employees: int
    
    total_ytd_gross: Decimal
    total_ytd_paye: Decimal
    total_ytd_pension: Decimal
    total_ytd_net: Decimal
    total_ytd_employer_cost: Decimal
    
    average_ytd_gross: Decimal
    average_ytd_net: Decimal


# ===========================================
# OPENING BALANCE IMPORT SCHEMAS
# ===========================================

class OpeningBalanceCreate(BaseModel):
    """Create opening balance for an employee."""
    employee_id: UUID
    tax_year: int = Field(..., ge=2020, le=2050)
    effective_date: date
    months_covered: int = Field(..., ge=1, le=12)
    
    # Prior YTD Values
    prior_ytd_gross: Decimal = Field(..., ge=0)
    prior_ytd_paye: Decimal = Field(..., ge=0)
    prior_ytd_pension_employee: Decimal = Field(..., ge=0)
    prior_ytd_pension_employer: Decimal = Field(..., ge=0)
    prior_ytd_nhf: Decimal = Field(default=Decimal("0.00"), ge=0)
    prior_ytd_net: Decimal = Field(..., ge=0)
    
    source_system: Optional[str] = None
    notes: Optional[str] = None


class OpeningBalanceResponse(OpeningBalanceCreate):
    """Opening balance response."""
    id: UUID
    entity_id: UUID
    import_batch_id: str
    source_file: Optional[str] = None
    
    is_verified: bool
    verified_by_id: Optional[UUID] = None
    verified_at: Optional[datetime] = None
    
    is_applied: bool
    applied_at: Optional[datetime] = None
    
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BulkOpeningBalanceImport(BaseModel):
    """Bulk import opening balances."""
    tax_year: int
    effective_date: date
    source_system: str = "Manual Import"
    balances: List[OpeningBalanceCreate]


class OpeningBalanceImportResult(BaseModel):
    """Result of opening balance import."""
    import_batch_id: str
    total_records: int
    successful: int
    failed: int
    errors: List[Dict[str, str]]


# ===========================================
# PAYSLIP EXPLANATION SCHEMAS
# ===========================================

class PayslipExplanationResponse(BaseModel):
    """Human-readable payslip explanation."""
    id: UUID
    payslip_id: UUID
    
    has_changes: bool
    
    # Explanations
    gross_explanation: str
    deduction_explanation: str
    tax_explanation: str
    net_explanation: str
    full_explanation: str
    
    variance_notes: Optional[str] = None
    
    generated_at: datetime

    class Config:
        from_attributes = True


# ===========================================
# VARIANCE LOG SCHEMAS
# ===========================================

class VarianceLogResponse(BaseModel):
    """Employee variance log entry."""
    id: UUID
    entity_id: UUID
    employee_id: UUID
    employee_name: Optional[str] = None
    payslip_id: UUID
    
    variance_type: str
    previous_value: Decimal
    current_value: Decimal
    variance_amount: Decimal
    variance_percent: Decimal
    
    reason_code: Optional[str] = None
    reason_note: Optional[str] = None
    
    is_flagged: bool
    flag_threshold_percent: Decimal
    
    created_at: datetime

    class Config:
        from_attributes = True


class VarianceReasonUpdate(BaseModel):
    """Update variance reason code."""
    reason_code: Literal[
        "new_hire", "termination", "salary_increase", "salary_decrease",
        "promotion", "allowance_change", "loan_repayment", "loan_completed",
        "leave_deduction", "tax_band_change", "arrears_paid", "bonus_payment", "other"
    ]
    reason_note: Optional[str] = None


# ===========================================
# CTC ANALYTICS SCHEMAS
# ===========================================

class DepartmentCTC(BaseModel):
    """CTC breakdown by department."""
    department: str
    employee_count: int
    total_gross: Decimal
    total_employer_pension: Decimal
    total_nsitf: Decimal
    total_itf: Decimal
    total_hmo: Decimal
    total_other_benefits: Decimal
    total_ctc: Decimal
    average_ctc_per_employee: Decimal
    percentage_of_total: Decimal


class CTCSnapshotResponse(BaseModel):
    """Cost-to-Company snapshot response."""
    id: UUID
    entity_id: UUID
    snapshot_month: int
    snapshot_year: int
    
    # Company-Wide Totals
    total_employees: int
    total_gross_salary: Decimal
    total_pension_employer: Decimal
    total_nsitf: Decimal
    total_itf: Decimal
    total_hmo: Decimal
    total_group_life: Decimal
    total_other_benefits: Decimal
    
    # Total CTC
    total_ctc: Decimal
    average_ctc_per_employee: Decimal
    
    # Department Breakdown
    department_breakdown: List[DepartmentCTC]
    
    # Budget Tracking
    monthly_budget: Optional[Decimal] = None
    budget_variance: Decimal
    budget_variance_percent: Decimal
    
    snapshot_date: datetime

    class Config:
        from_attributes = True


class CTCTrendResponse(BaseModel):
    """CTC trend over time."""
    entity_id: UUID
    periods: List[Dict[str, Any]]  # month, year, total_ctc, employee_count


# ===========================================
# WHAT-IF SIMULATION SCHEMAS
# ===========================================

class SalaryIncreaseScenario(BaseModel):
    """Salary increase simulation parameters."""
    increase_type: Literal["percentage", "flat_amount"]
    increase_value: Decimal
    apply_to: Literal["all", "department", "employee_list"]
    department: Optional[str] = None
    employee_ids: Optional[List[UUID]] = None


class NewHireScenario(BaseModel):
    """New hire simulation parameters."""
    count: int
    average_gross_salary: Decimal
    department: Optional[str] = None


class TerminationScenario(BaseModel):
    """Termination simulation parameters."""
    employee_ids: List[UUID]


class WhatIfSimulationRequest(BaseModel):
    """What-If simulation request."""
    simulation_name: str = Field(..., max_length=255)
    description: Optional[str] = None
    scenario_type: Literal[
        "salary_increase", "new_hires", "terminations", "tax_reform", "custom"
    ]
    
    # Scenario Parameters (one of these)
    salary_increase: Optional[SalaryIncreaseScenario] = None
    new_hires: Optional[NewHireScenario] = None
    terminations: Optional[TerminationScenario] = None
    custom_parameters: Optional[Dict[str, Any]] = None
    
    save_simulation: bool = False


class WhatIfSimulationResponse(BaseModel):
    """What-If simulation response."""
    id: UUID
    entity_id: UUID
    simulation_name: str
    description: Optional[str] = None
    scenario_type: str
    parameters: Dict[str, Any]
    
    # Baseline
    baseline_gross: Decimal
    baseline_paye: Decimal
    baseline_employer_cost: Decimal
    baseline_ctc: Decimal
    
    # Projected
    projected_gross: Decimal
    projected_paye: Decimal
    projected_employer_cost: Decimal
    projected_ctc: Decimal
    
    # Impact
    gross_impact: Decimal
    paye_impact: Decimal
    employer_cost_impact: Decimal
    ctc_impact: Decimal
    gross_impact_percent: Decimal
    ctc_impact_percent: Decimal
    
    # Summary
    impact_summary: str
    
    is_saved: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ===========================================
# GHOST WORKER DETECTION SCHEMAS
# ===========================================

class GhostWorkerDetectionResponse(BaseModel):
    """Ghost worker detection result."""
    id: UUID
    entity_id: UUID
    detection_type: str
    
    employee_1_id: UUID
    employee_1_name: Optional[str] = None
    employee_2_id: UUID
    employee_2_name: Optional[str] = None
    
    duplicate_field: str
    duplicate_value: str
    severity: str
    
    is_resolved: bool
    resolution_note: Optional[str] = None
    resolved_by_id: Optional[UUID] = None
    resolved_at: Optional[datetime] = None
    
    detected_at: datetime

    class Config:
        from_attributes = True


class GhostWorkerScanResult(BaseModel):
    """Result of ghost worker scan."""
    entity_id: UUID
    scan_date: datetime
    total_employees_scanned: int
    detections_found: int
    critical_detections: int
    detections: List[GhostWorkerDetectionResponse]


class ResolveGhostWorkerRequest(BaseModel):
    """Request to resolve ghost worker detection."""
    resolution_note: str = Field(..., min_length=10)


# ===========================================
# PRORATION SETTINGS SCHEMAS
# ===========================================

class ProrationSettingsUpdate(BaseModel):
    """Update proration settings."""
    proration_mode: Literal["calendar_days", "working_days", "fixed_30_days"]
    apply_to_new_hires: bool = True
    apply_to_exits: bool = True
    apply_to_leave: bool = True


class ProrationSettingsResponse(BaseModel):
    """Proration settings response."""
    entity_id: UUID
    proration_mode: str
    apply_to_new_hires: bool
    apply_to_exits: bool
    apply_to_leave: bool
    working_days_per_month: int = 22


# ===========================================
# SMART VALIDATION SCHEMAS
# ===========================================

class ValidationResult(BaseModel):
    """Single validation result."""
    check_name: str
    passed: bool
    severity: Literal["critical", "warning", "info"]
    message: str
    affected_count: int = 0
    details: Optional[List[Dict[str, Any]]] = None


class SmartValidationResponse(BaseModel):
    """Smart validation response."""
    payroll_run_id: UUID
    validation_date: datetime
    
    total_checks: int
    passed_checks: int
    failed_checks: int
    
    can_approve: bool
    blocking_issues: int
    
    results: List[ValidationResult]
    summary: str
