"""
Tekvwa Pro Audit - Payroll Router

API endpoints for payroll management with Nigerian compliance.

SKU REQUIREMENT: Pro Audit Professional tier or above
"""

import uuid
from datetime import date
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import (
    get_current_user, 
    get_current_active_user, 
    get_current_entity_id,
    require_feature,
    record_usage_event,
)
from app.models.user import User
from app.models.payroll import EmploymentStatus, PayrollStatus, PayrollFrequency
from app.models.audit_consolidated import AuditAction
from app.models.sku import Feature, UsageMetricType
from app.services.payroll_service import PayrollService
from app.services.audit_service import AuditService
from app.schemas.payroll import (
    # Employee schemas
    EmployeeCreate,
    EmployeeUpdate,
    EmployeeResponse,
    EmployeeSummary,
    BankAccountCreate,
    BankAccountResponse,
    # Payroll schemas
    PayrollRunCreate,
    PayrollRunUpdate,
    PayrollRunResponse,
    PayrollRunSummary,
    # Payslip schemas
    PayslipResponse,
    PayslipSummary,
    # Calculation schemas
    SalaryBreakdownRequest,
    SalaryBreakdownResponse,
    # Remittance schemas
    StatutoryRemittanceResponse,
    StatutoryRemittanceUpdate,
    # Loan schemas
    LoanCreate,
    LoanUpdate,
    LoanResponse,
    LoanSummary,
    # Other
    BankScheduleResponse,
    PayrollDashboardStats,
    MessageResponse,
)


router = APIRouter()

# Feature gate for all payroll endpoints
payroll_feature_gate = require_feature([Feature.PAYROLL])


# ===========================================
# EMPLOYEE ENDPOINTS
# ===========================================

@router.post(
    "/employees",
    response_model=EmployeeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new employee",
    description="Create a new employee with personal, compliance, and salary details. Requires Professional tier.",
)
async def create_employee(
    data: EmployeeCreate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(payroll_feature_gate),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Create a new employee."""
    service = PayrollService(db)
    
    try:
        employee = await service.create_employee(
            entity_id=entity_id,
            data=data.model_dump(),
            created_by_id=current_user.id,
        )
        
        # Audit log for employee creation
        audit_service = AuditService(db)
        await audit_service.log_action(
            business_entity_id=entity_id,
            entity_type="employee",
            entity_id=str(employee.id),
            action=AuditAction.CREATE,
            user_id=current_user.id,
            new_values={
                "employee_id": employee.employee_id,
                "first_name": data.first_name,
                "last_name": data.last_name,
                "email": data.email,
                "basic_salary": float(data.basic_salary) if data.basic_salary else 0,
            },
        )
        
        # Record usage metering for employee count tracking
        if current_user.organization_id:
            await record_usage_event(
                db=db,
                organization_id=current_user.organization_id,
                metric_type=UsageMetricType.EMPLOYEES,
                entity_id=entity_id,
                user_id=current_user.id,
                resource_type="employee",
                resource_id=str(employee.id),
            )
        
        # Add computed properties
        response = EmployeeResponse.model_validate(employee)
        response.full_name = employee.full_name
        response.monthly_gross = employee.monthly_gross
        response.annual_gross = employee.annual_gross
        response.pensionable_earnings = employee.pensionable_earnings
        
        return response
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/employees",
    response_model=dict,
    summary="List employees",
    description="Get paginated list of employees with optional filters.",
)
async def list_employees(
    status: Optional[str] = Query(None, description="Employment status filter"),
    department: Optional[str] = Query(None, description="Department filter"),
    search: Optional[str] = Query(None, description="Search by name, email, or ID"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """List employees with pagination and filters."""
    service = PayrollService(db)
    
    emp_status = None
    if status:
        try:
            emp_status = EmploymentStatus(status)
        except ValueError:
            pass
    
    employees, total = await service.list_employees(
        entity_id=entity_id,
        status=emp_status,
        department=department,
        search=search,
        page=page,
        per_page=per_page,
    )
    
    items = []
    for emp in employees:
        items.append({
            "id": str(emp.id),
            "employee_id": emp.employee_id,
            "full_name": emp.full_name,
            "email": emp.email,
            "department": emp.department,
            "job_title": emp.job_title,
            "employment_status": emp.employment_status,
            "monthly_gross": float(emp.monthly_gross),
            "basic_salary": float(emp.basic_salary),
            "tin": emp.tin,
        })
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@router.get(
    "/employees/departments",
    response_model=List[str],
    summary="Get departments",
    description="Get list of unique departments.",
)
async def get_departments(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get list of departments."""
    service = PayrollService(db)
    return await service.get_departments(entity_id)


@router.get(
    "/employees/{employee_id}",
    response_model=EmployeeResponse,
    summary="Get employee details",
)
async def get_employee(
    employee_id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get employee by ID."""
    service = PayrollService(db)
    employee = await service.get_employee(entity_id, employee_id)
    
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )
    
    response = EmployeeResponse.model_validate(employee)
    response.full_name = employee.full_name
    response.monthly_gross = employee.monthly_gross
    response.annual_gross = employee.annual_gross
    response.pensionable_earnings = employee.pensionable_earnings
    
    return response


@router.patch(
    "/employees/{employee_id}",
    response_model=EmployeeResponse,
    summary="Update employee",
)
async def update_employee(
    data: EmployeeUpdate,
    employee_id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Update employee details."""
    service = PayrollService(db)
    
    employee = await service.update_employee(
        entity_id=entity_id,
        employee_id=employee_id,
        data=data.model_dump(exclude_unset=True),
        updated_by_id=current_user.id,
    )
    
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )
    
    # Audit log for employee update
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="employee",
        entity_id=str(employee.id),
        action=AuditAction.UPDATE,
        user_id=current_user.id,
        new_values=data.model_dump(exclude_unset=True),
    )
    
    response = EmployeeResponse.model_validate(employee)
    response.full_name = employee.full_name
    response.monthly_gross = employee.monthly_gross
    response.annual_gross = employee.annual_gross
    response.pensionable_earnings = employee.pensionable_earnings
    
    return response


@router.post(
    "/employees/{employee_id}/bank-accounts",
    response_model=BankAccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add bank account",
)
async def add_bank_account(
    data: BankAccountCreate,
    employee_id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Add bank account to employee."""
    service = PayrollService(db)
    
    try:
        account = await service.add_bank_account(
            entity_id=entity_id,
            employee_id=employee_id,
            data=data.model_dump(),
        )
        return BankAccountResponse.model_validate(account)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/employees/{employee_id}/payslips",
    response_model=List[PayslipSummary],
    summary="Get employee payslips",
)
async def get_employee_payslips(
    employee_id: uuid.UUID = Path(...),
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get all payslips for an employee."""
    service = PayrollService(db)
    payslips = await service.get_employee_payslips(entity_id, employee_id, year)
    
    return [
        PayslipSummary(
            id=p.id,
            payslip_number=p.payslip_number,
            employee_id=p.employee_id,
            employee_name=p.employee.full_name if p.employee else "N/A",
            employee_staff_id=p.employee.employee_id if p.employee else "N/A",
            gross_pay=p.gross_pay,
            total_deductions=p.total_deductions,
            net_pay=p.net_pay,
            is_paid=p.is_paid,
        )
        for p in payslips
    ]


# ===========================================
# SALARY CALCULATOR
# ===========================================

@router.post(
    "/calculate-salary",
    response_model=SalaryBreakdownResponse,
    summary="Calculate salary breakdown",
    description="Calculate complete salary breakdown including PAYE, pension, NHF, and employer contributions.",
)
async def calculate_salary_breakdown(
    data: SalaryBreakdownRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
):
    """Calculate salary breakdown with Nigerian compliance."""
    service = PayrollService(db)
    
    result = service.calculate_salary_breakdown(
        basic_salary=data.basic_salary,
        housing_allowance=data.housing_allowance,
        transport_allowance=data.transport_allowance,
        meal_allowance=data.meal_allowance,
        utility_allowance=data.utility_allowance,
        other_allowances=data.other_allowances,
        pension_percentage=data.pension_percentage,
        is_pension_exempt=data.is_pension_exempt,
        is_nhf_exempt=data.is_nhf_exempt,
    )
    
    return SalaryBreakdownResponse(**result)


# ===========================================
# PAYROLL RUN ENDPOINTS
# ===========================================

@router.post(
    "/payroll-runs",
    response_model=PayrollRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create payroll run",
    description="Create a new payroll run and generate payslips for employees.",
)
async def create_payroll_run(
    data: PayrollRunCreate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Create a new payroll run."""
    service = PayrollService(db)
    
    try:
        payroll = await service.create_payroll_run(
            entity_id=entity_id,
            name=data.name,
            period_start=data.period_start,
            period_end=data.period_end,
            payment_date=data.payment_date,
            frequency=PayrollFrequency(data.frequency),
            description=data.description,
            employee_ids=data.employee_ids,
            created_by_id=current_user.id,
        )
        
        # Audit log for payroll run creation
        audit_service = AuditService(db)
        await audit_service.log_action(
            business_entity_id=entity_id,
            entity_type="payroll_run",
            entity_id=str(payroll.id),
            action=AuditAction.CREATE,
            user_id=current_user.id,
            new_values={
                "name": data.name,
                "period_start": str(data.period_start),
                "period_end": str(data.period_end),
                "payment_date": str(data.payment_date),
                "frequency": data.frequency,
            },
        )
        
        return PayrollRunResponse.model_validate(payroll)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/payroll-runs",
    response_model=dict,
    summary="List payroll runs",
)
async def list_payroll_runs(
    status: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """List payroll runs with filters."""
    service = PayrollService(db)
    
    pay_status = None
    if status:
        try:
            pay_status = PayrollStatus(status)
        except ValueError:
            pass
    
    runs, total = await service.list_payroll_runs(
        entity_id=entity_id,
        status=pay_status,
        year=year,
        page=page,
        per_page=per_page,
    )
    
    return {
        "items": [PayrollRunSummary.model_validate(r) for r in runs],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@router.get(
    "/payroll-runs/{payroll_id}",
    response_model=PayrollRunResponse,
    summary="Get payroll run",
)
async def get_payroll_run(
    payroll_id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get payroll run details."""
    service = PayrollService(db)
    payroll = await service.get_payroll_run(entity_id, payroll_id)
    
    if not payroll:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payroll run not found",
        )
    
    return PayrollRunResponse.model_validate(payroll)


@router.post(
    "/payroll-runs/{payroll_id}/approve",
    response_model=PayrollRunResponse,
    summary="Approve payroll run",
)
async def approve_payroll_run(
    payroll_id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Approve a payroll run."""
    service = PayrollService(db)
    
    try:
        payroll = await service.approve_payroll(
            entity_id=entity_id,
            payroll_id=payroll_id,
            approved_by_id=current_user.id,
        )
        return PayrollRunResponse.model_validate(payroll)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/payroll-runs/{payroll_id}/process",
    response_model=PayrollRunResponse,
    summary="Process payroll run",
)
async def process_payroll_run(
    payroll_id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Process an approved payroll run."""
    service = PayrollService(db)
    
    try:
        payroll = await service.process_payroll(entity_id, payroll_id)
        return PayrollRunResponse.model_validate(payroll)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/payroll-runs/{payroll_id}/mark-paid",
    response_model=PayrollRunResponse,
    summary="Mark payroll as paid",
)
async def mark_payroll_paid(
    payroll_id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Mark a processed payroll as paid."""
    service = PayrollService(db)
    
    try:
        payroll = await service.mark_payroll_paid(entity_id, payroll_id)
        return PayrollRunResponse.model_validate(payroll)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/payroll-runs/{payroll_id}/payslips",
    response_model=List[PayslipSummary],
    summary="Get payslips for payroll run",
)
async def get_payroll_payslips(
    payroll_id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get all payslips for a payroll run."""
    service = PayrollService(db)
    payslips = await service.list_payslips_for_payroll(entity_id, payroll_id)
    
    return [
        PayslipSummary(
            id=p.id,
            payslip_number=p.payslip_number,
            employee_id=p.employee_id,
            employee_name=p.employee.full_name if p.employee else "N/A",
            employee_staff_id=p.employee.employee_id if p.employee else "N/A",
            gross_pay=p.gross_pay,
            total_deductions=p.total_deductions,
            net_pay=p.net_pay,
            is_paid=p.is_paid,
        )
        for p in payslips
    ]


@router.get(
    "/payroll-runs/{payroll_id}/bank-schedule",
    response_model=BankScheduleResponse,
    summary="Get bank payment schedule",
)
async def get_bank_schedule(
    payroll_id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Generate bank payment schedule for a payroll."""
    service = PayrollService(db)
    
    try:
        schedule = await service.generate_bank_schedule(entity_id, payroll_id)
        return BankScheduleResponse(**schedule)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# ===========================================
# PAYSLIP ENDPOINTS
# ===========================================

@router.get(
    "/payslips/{payslip_id}",
    response_model=PayslipResponse,
    summary="Get payslip details",
)
async def get_payslip(
    payslip_id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get detailed payslip."""
    service = PayrollService(db)
    payslip = await service.get_payslip(entity_id, payslip_id)
    
    if not payslip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payslip not found",
        )
    
    response = PayslipResponse.model_validate(payslip)
    if payslip.employee:
        response.employee_name = payslip.employee.full_name
        response.employee_staff_id = payslip.employee.employee_id
        response.department = payslip.employee.department
        response.job_title = payslip.employee.job_title
    
    return response


@router.get(
    "/payslips/{payslip_id}/pdf",
    summary="Download payslip PDF",
    description="Generate and download payslip as PDF.",
)
async def download_payslip_pdf(
    payslip_id: uuid.UUID = Path(...),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Download payslip as PDF."""
    from fastapi.responses import Response
    
    service = PayrollService(db)
    
    # Get payslip first to get the payslip number for filename
    payslip = await service.get_payslip(entity_id, payslip_id)
    if not payslip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payslip not found",
        )
    
    # Generate PDF
    pdf_bytes = await service.generate_payslip_pdf(entity_id, payslip_id)
    if not pdf_bytes:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate PDF",
        )
    
    # Create filename
    filename = f"payslip_{payslip.payslip_number}.pdf"
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        }
    )


# ===========================================
# REMITTANCE ENDPOINTS
# ===========================================

@router.get(
    "/remittances",
    response_model=List[StatutoryRemittanceResponse],
    summary="List statutory remittances",
)
async def list_remittances(
    remittance_type: Optional[str] = Query(None),
    is_paid: Optional[bool] = Query(None),
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """List statutory remittances."""
    service = PayrollService(db)
    
    remittances = await service.list_remittances(
        entity_id=entity_id,
        remittance_type=remittance_type,
        is_paid=is_paid,
        year=year,
    )
    
    return [StatutoryRemittanceResponse.model_validate(r) for r in remittances]


@router.post(
    "/remittances/{remittance_id}/mark-paid",
    response_model=StatutoryRemittanceResponse,
    summary="Mark remittance as paid",
)
async def mark_remittance_paid(
    remittance_id: uuid.UUID = Path(...),
    payment_date: date = Query(...),
    payment_reference: str = Query(...),
    receipt_number: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Mark a statutory remittance as paid."""
    service = PayrollService(db)
    
    try:
        remittance = await service.mark_remittance_paid(
            entity_id=entity_id,
            remittance_id=remittance_id,
            payment_date=payment_date,
            payment_reference=payment_reference,
            receipt_number=receipt_number,
        )
        return StatutoryRemittanceResponse.model_validate(remittance)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# ===========================================
# DASHBOARD
# ===========================================

@router.get(
    "/dashboard",
    response_model=dict,
    summary="Get payroll dashboard",
)
async def get_payroll_dashboard(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get payroll dashboard statistics."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        service = PayrollService(db)
        stats = await service.get_payroll_dashboard(entity_id)
        
        # Convert Decimal values to float for JSON serialization
        result = {
            "total_employees": stats["total_employees"],
            "active_employees": stats["active_employees"],
            "total_monthly_payroll": float(stats["total_monthly_payroll"]),
            "total_annual_payroll": float(stats["total_annual_payroll"]),
            "average_salary": float(stats["average_salary"]),
            "current_month_gross": float(stats["current_month_gross"]),
            "current_month_net": float(stats["current_month_net"]),
            "current_month_paye": float(stats["current_month_paye"]),
            "current_month_pension": float(stats["current_month_pension"]),
            "current_month_nhf": float(stats["current_month_nhf"]),
            "department_breakdown": stats["department_breakdown"],
            "recent_payroll_runs": [],
            "pending_remittances": [],
        }
        
        # Safely convert payroll runs
        for r in stats.get("recent_payroll_runs", []):
            try:
                result["recent_payroll_runs"].append({
                    "id": str(r.id),
                    "payroll_code": r.payroll_code,
                    "name": r.name,
                    "status": r.status.value if hasattr(r.status, 'value') else str(r.status),
                    "period_start": r.period_start.isoformat(),
                    "period_end": r.period_end.isoformat(),
                    "payment_date": r.payment_date.isoformat(),
                    "total_employees": r.total_employees,
                    "total_gross_pay": float(r.total_gross_pay),
                    "total_net_pay": float(r.total_net_pay),
                    "total_deductions": float(r.total_deductions),
                    "created_at": r.created_at.isoformat(),
                })
            except Exception as e:
                logger.error(f"Error serializing payroll run: {e}")
        
        # Safely convert remittances
        for r in stats.get("pending_remittances", []):
            try:
                result["pending_remittances"].append({
                    "id": str(r.id),
                    "remittance_type": r.remittance_type.value if hasattr(r.remittance_type, 'value') else str(r.remittance_type),
                    "period_start": r.period_start.isoformat() if r.period_start else None,
                    "period_end": r.period_end.isoformat() if r.period_end else None,
                    "due_date": r.due_date.isoformat() if r.due_date else None,
                    "amount": float(r.amount),
                    "is_paid": r.is_paid,
                })
            except Exception as e:
                logger.error(f"Error serializing remittance: {e}")
        
        return result
    except Exception as e:
        logger.error(f"Dashboard error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error loading dashboard: {str(e)}"
        )


# ===========================================
# LOAN ENDPOINTS
# ===========================================

@router.get("/loans", response_model=List[LoanResponse], tags=["Loans"])
async def list_loans(
    employee_id: Optional[uuid.UUID] = Query(None, description="Filter by employee"),
    status: Optional[str] = Query(None, description="Filter by loan status"),
    loan_type: Optional[str] = Query(None, description="Filter by loan type"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """List all loans for the entity."""
    service = PayrollService(db)
    loans = await service.get_loans(
        entity_id=entity_id,
        employee_id=employee_id,
        status=status,
        loan_type=loan_type,
    )
    return loans


@router.get("/loans/summary", response_model=LoanSummary, tags=["Loans"])
async def get_loan_summary(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get loan summary statistics."""
    service = PayrollService(db)
    return await service.get_loan_summary(entity_id=entity_id)


@router.get("/employees/{employee_id}/loans", response_model=List[LoanResponse], tags=["Loans"])
async def get_employee_loans(
    employee_id: uuid.UUID = Path(..., description="Employee ID"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get all loans for a specific employee."""
    service = PayrollService(db)
    loans = await service.get_loans(
        entity_id=entity_id,
        employee_id=employee_id,
    )
    return loans


@router.post("/loans", response_model=LoanResponse, status_code=status.HTTP_201_CREATED, tags=["Loans"])
async def create_loan(
    loan_data: LoanCreate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Create a new loan/salary advance for an employee."""
    service = PayrollService(db)
    loan = await service.create_loan(
        entity_id=entity_id,
        employee_id=loan_data.employee_id,
        loan_data=loan_data,
        created_by_id=current_user.id,
    )
    return loan


@router.get("/loans/{loan_id}", response_model=LoanResponse, tags=["Loans"])
async def get_loan(
    loan_id: uuid.UUID = Path(..., description="Loan ID"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get a specific loan by ID."""
    service = PayrollService(db)
    loan = await service.get_loan_by_id(entity_id=entity_id, loan_id=loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    return loan


@router.put("/loans/{loan_id}", response_model=LoanResponse, tags=["Loans"])
async def update_loan(
    loan_id: uuid.UUID,
    loan_data: LoanUpdate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Update a loan."""
    service = PayrollService(db)
    loan = await service.update_loan(
        entity_id=entity_id,
        loan_id=loan_id,
        loan_data=loan_data,
        updated_by_id=current_user.id,
    )
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    return loan


@router.post("/loans/{loan_id}/approve", response_model=LoanResponse, tags=["Loans"])
async def approve_loan(
    loan_id: uuid.UUID = Path(..., description="Loan ID"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Approve a pending loan."""
    service = PayrollService(db)
    loan = await service.approve_loan(
        entity_id=entity_id,
        loan_id=loan_id,
        approved_by_id=current_user.id,
    )
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    return loan


@router.post("/loans/{loan_id}/cancel", response_model=LoanResponse, tags=["Loans"])
async def cancel_loan(
    loan_id: uuid.UUID = Path(..., description="Loan ID"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Cancel a loan."""
    service = PayrollService(db)
    loan = await service.cancel_loan(
        entity_id=entity_id,
        loan_id=loan_id,
    )
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    return loan


@router.delete("/loans/{loan_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Loans"])
async def delete_loan(
    loan_id: uuid.UUID = Path(..., description="Loan ID"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Delete a loan (only pending loans can be deleted)."""
    service = PayrollService(db)
    success = await service.delete_loan(entity_id=entity_id, loan_id=loan_id)
    if not success:
        raise HTTPException(status_code=404, detail="Loan not found or cannot be deleted")
