"""
Tekvwa Pro Audit - Tax Router

API endpoints for tax management (VAT, PAYE, WHT, CIT).
"""

from datetime import date
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.database import get_async_session
from app.dependencies import get_current_active_user
from app.models.user import User
from app.services.entity_service import EntityService
from app.services.tax_calculators.vat_service import VATService, VATCalculator, NIGERIA_VAT_RATE
from app.services.audit_service import AuditService
from app.models.audit_consolidated import AuditAction
from app.schemas.auth import MessageResponse


router = APIRouter()


# ===========================================
# REQUEST/RESPONSE SCHEMAS
# ===========================================

class VATCalculationRequest(BaseModel):
    """Schema for VAT calculation request."""
    amount: float = Field(..., gt=0)
    vat_rate: float = Field(7.5, ge=0, le=100)
    is_inclusive: bool = Field(False, description="True if amount includes VAT")


class VATCalculationResponse(BaseModel):
    """Schema for VAT calculation response."""
    net_amount: float
    vat_amount: float
    total_amount: float
    vat_rate: float


class VATRecordResponse(BaseModel):
    """Schema for VAT record response."""
    id: UUID
    entity_id: UUID
    period_start: date
    period_end: date
    output_vat: float
    input_vat_total: float
    input_vat_recoverable: float
    input_vat_non_recoverable: float
    net_vat_payable: float
    is_refund_due: bool
    is_filed: bool


class VATReturnResponse(BaseModel):
    """Schema for VAT return preparation response."""
    period: dict
    output_vat: dict
    input_vat: dict
    net_vat_payable: float
    is_refund_due: bool
    is_filed: bool
    vat_record_id: str


class VATPeriodSummaryResponse(BaseModel):
    """Schema for VAT period summary."""
    period_start: date
    period_end: date
    output_vat: float
    input_vat_total: float
    input_vat_recoverable: float
    input_vat_non_recoverable: float
    net_vat_payable: float
    is_refund: bool


# ===========================================
# HELPER FUNCTIONS
# ===========================================

async def verify_entity_access(
    entity_id: UUID,
    user: User,
    db: AsyncSession,
) -> None:
    """Verify user has access to the entity."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, user)
    
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business entity not found",
        )
    
    has_access = any(
        access.entity_id == entity_id 
        for access in user.entity_access
    )
    
    if not has_access and entity.organization_id != user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this business entity",
        )


# ===========================================
# VAT CALCULATION ENDPOINTS
# ===========================================

@router.post(
    "/vat/calculate",
    response_model=VATCalculationResponse,
    summary="Calculate VAT",
    tags=["Tax - VAT"],
)
async def calculate_vat(
    request: VATCalculationRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    Calculate VAT for a given amount.
    
    - Use `is_inclusive=False` to add VAT to the amount
    - Use `is_inclusive=True` to extract VAT from an inclusive amount
    
    Nigeria standard VAT rate is 7.5%.
    """
    from decimal import Decimal
    
    net_amount, vat_amount, total_amount = VATCalculator.calculate_vat(
        Decimal(str(request.amount)),
        Decimal(str(request.vat_rate)),
        request.is_inclusive,
    )
    
    return VATCalculationResponse(
        net_amount=float(net_amount),
        vat_amount=float(vat_amount),
        total_amount=float(total_amount),
        vat_rate=request.vat_rate,
    )


# ===========================================
# VAT PERIOD ENDPOINTS
# ===========================================

@router.get(
    "/{entity_id}/vat",
    response_model=List[VATRecordResponse],
    summary="List VAT records",
    tags=["Tax - VAT"],
)
async def list_vat_records(
    entity_id: UUID,
    year: Optional[int] = Query(None, description="Filter by year"),
    is_filed: Optional[bool] = Query(None, description="Filter by filed status"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    List all VAT records for a business entity.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    vat_service = VATService(db)
    records = await vat_service.get_vat_records_for_entity(
        entity_id=entity_id,
        year=year,
        is_filed=is_filed,
    )
    
    return [
        VATRecordResponse(
            id=rec.id,
            entity_id=rec.entity_id,
            period_start=rec.period_start,
            period_end=rec.period_end,
            output_vat=float(rec.output_vat),
            input_vat_total=float(rec.input_vat_total),
            input_vat_recoverable=float(rec.input_vat_recoverable),
            input_vat_non_recoverable=float(rec.input_vat_non_recoverable),
            net_vat_payable=float(rec.net_vat_payable),
            is_refund_due=rec.net_vat_payable < 0,
            is_filed=rec.is_filed,
        )
        for rec in records
    ]


@router.get(
    "/{entity_id}/vat/{year}/{month}",
    response_model=VATPeriodSummaryResponse,
    summary="Get VAT for period",
    tags=["Tax - VAT"],
)
async def get_vat_for_period(
    entity_id: UUID,
    year: int,
    month: int = Path(..., ge=1, le=12),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get calculated VAT summary for a specific month.
    
    Calculates VAT from invoices (output) and expenses (input).
    """
    await verify_entity_access(entity_id, current_user, db)
    
    vat_service = VATService(db)
    vat_data = await vat_service.calculate_period_vat(entity_id, year, month)
    
    return VATPeriodSummaryResponse(
        period_start=vat_data["period_start"],
        period_end=vat_data["period_end"],
        output_vat=vat_data["output_vat"],
        input_vat_total=vat_data["input_vat_total"],
        input_vat_recoverable=vat_data["input_vat_recoverable"],
        input_vat_non_recoverable=vat_data["input_vat_non_recoverable"],
        net_vat_payable=vat_data["net_vat_payable"],
        is_refund=vat_data["is_refund"],
    )


@router.post(
    "/{entity_id}/vat/{year}/{month}/update",
    response_model=VATRecordResponse,
    summary="Update VAT record",
    tags=["Tax - VAT"],
)
async def update_vat_record(
    entity_id: UUID,
    year: int,
    month: int = Path(..., ge=1, le=12),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Update/recalculate VAT record for a period.
    
    Recalculates VAT from all invoices and transactions in the period.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    vat_service = VATService(db)
    vat_record = await vat_service.update_vat_record(entity_id, year, month)
    
    # Audit logging for VAT update
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="vat_record",
        entity_id=str(vat_record.id),
        action=AuditAction.UPDATE,
        user_id=current_user.id,
        new_values={
            "period": f"{year}-{month:02d}",
            "output_vat": float(vat_record.output_vat),
            "input_vat_total": float(vat_record.input_vat_total),
            "net_vat_payable": float(vat_record.net_vat_payable),
        }
    )
    
    return VATRecordResponse(
        id=vat_record.id,
        entity_id=vat_record.entity_id,
        period_start=vat_record.period_start,
        period_end=vat_record.period_end,
        output_vat=float(vat_record.output_vat),
        input_vat_total=float(vat_record.input_vat_total),
        input_vat_recoverable=float(vat_record.input_vat_recoverable),
        input_vat_non_recoverable=float(vat_record.input_vat_non_recoverable),
        net_vat_payable=float(vat_record.net_vat_payable),
        is_refund_due=vat_record.net_vat_payable < 0,
        is_filed=vat_record.is_filed,
    )


@router.get(
    "/{entity_id}/vat/{year}/{month}/return",
    response_model=VATReturnResponse,
    summary="Prepare VAT return",
    tags=["Tax - VAT"],
)
async def prepare_vat_return(
    entity_id: UUID,
    year: int,
    month: int = Path(..., ge=1, le=12),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Prepare VAT return data for FIRS filing.
    
    Returns structured data suitable for VAT return form.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    vat_service = VATService(db)
    return_data = await vat_service.prepare_vat_return(entity_id, year, month)
    
    return VATReturnResponse(**return_data)


@router.post(
    "/{entity_id}/vat/{vat_record_id}/mark-filed",
    response_model=VATRecordResponse,
    summary="Mark VAT as filed",
    tags=["Tax - VAT"],
)
async def mark_vat_filed(
    entity_id: UUID,
    vat_record_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Mark a VAT record as filed with FIRS.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    vat_service = VATService(db)
    
    try:
        vat_record = await vat_service.mark_vat_filed(vat_record_id, entity_id)
        
        # Audit logging for VAT filing
        audit_service = AuditService(db)
        await audit_service.log_action(
            business_entity_id=entity_id,
            entity_type="vat_record",
            entity_id=str(vat_record_id),
            action=AuditAction.UPDATE,
            user_id=current_user.id,
            old_values={"is_filed": False},
            new_values={
                "is_filed": True,
                "filed_by": current_user.email,
                "net_vat_payable": float(vat_record.net_vat_payable),
            }
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    
    return VATRecordResponse(
        id=vat_record.id,
        entity_id=vat_record.entity_id,
        period_start=vat_record.period_start,
        period_end=vat_record.period_end,
        output_vat=float(vat_record.output_vat),
        input_vat_total=float(vat_record.input_vat_total),
        input_vat_recoverable=float(vat_record.input_vat_recoverable),
        input_vat_non_recoverable=float(vat_record.input_vat_non_recoverable),
        net_vat_payable=float(vat_record.net_vat_payable),
        is_refund_due=vat_record.net_vat_payable < 0,
        is_filed=vat_record.is_filed,
    )


# ===========================================
# PAYE SCHEMAS
# ===========================================

class PAYECalculationRequest(BaseModel):
    """Schema for PAYE calculation request."""
    gross_annual_income: float = Field(..., gt=0)
    basic_salary: Optional[float] = Field(None, gt=0, description="Basic salary for NHF calc (defaults to 60% of gross)")
    pension_percentage: float = Field(8.0, ge=0, le=8, description="Pension contribution %")
    other_reliefs: float = Field(0, ge=0, description="Other tax-exempt allowances")


class PAYECalculationResponse(BaseModel):
    """Schema for PAYE calculation response."""
    gross_annual_income: float
    basic_salary: float
    reliefs: dict
    taxable_income: float
    annual_tax: float
    monthly_tax: float
    effective_rate: float
    tax_bands: list
    net_annual_income: float
    net_monthly_income: float


class PAYERecordCreateRequest(BaseModel):
    """Schema for creating a PAYE record."""
    employee_name: str = Field(..., min_length=1)
    employee_tin: Optional[str] = None
    period_year: int = Field(..., ge=2020, le=2100)
    period_month: int = Field(..., ge=1, le=12)
    gross_salary: float = Field(..., gt=0)
    pension_contribution: float = Field(0, ge=0)
    nhf_contribution: float = Field(0, ge=0)
    other_reliefs: float = Field(0, ge=0)


class PAYERecordResponse(BaseModel):
    """Schema for PAYE record response."""
    id: UUID
    entity_id: UUID
    employee_name: str
    employee_tin: Optional[str]
    period_year: int
    period_month: int
    gross_salary: float
    consolidated_relief: float
    pension_contribution: float
    nhf_contribution: float
    other_reliefs: float
    taxable_income: float
    tax_amount: float


class PAYESummaryResponse(BaseModel):
    """Schema for PAYE period summary."""
    period: dict
    employee_count: int
    total_gross_salary: float
    total_paye_tax: float


# ===========================================
# PAYE CALCULATION ENDPOINTS
# ===========================================

@router.post(
    "/paye/calculate",
    response_model=PAYECalculationResponse,
    summary="Calculate PAYE",
    tags=["Tax - PAYE"],
)
async def calculate_paye(
    request: PAYECalculationRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    Calculate PAYE tax for given income.
    
    Uses Nigeria 2026 tax bands:
    - ₦0 - ₦800,000: 0%
    - ₦800,001 - ₦2,400,000: 15%
    - ₦2,400,001 - ₦4,800,000: 20%
    - ₦4,800,001 - ₦7,200,000: 25%
    - Above ₦7,200,000: 30%
    """
    from app.services.tax_calculators.paye_service import PAYECalculator
    
    calculator = PAYECalculator()
    result = calculator.calculate_paye(
        gross_annual_income=request.gross_annual_income,
        basic_salary=request.basic_salary,
        pension_percentage=request.pension_percentage,
        other_reliefs=request.other_reliefs,
    )
    
    return PAYECalculationResponse(**result)


# ===========================================
# PAYE RECORD ENDPOINTS
# ===========================================

@router.get(
    "/{entity_id}/paye",
    response_model=List[PAYERecordResponse],
    summary="List PAYE records",
    tags=["Tax - PAYE"],
)
async def list_paye_records(
    entity_id: UUID,
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None, ge=1, le=12),
    employee_tin: Optional[str] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    List all PAYE records for a business entity.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    from app.services.tax_calculators.paye_service import PAYEService
    
    paye_service = PAYEService(db)
    records = await paye_service.get_paye_records_for_entity(
        entity_id=entity_id,
        year=year,
        month=month,
        employee_tin=employee_tin,
    )
    
    return [
        PAYERecordResponse(
            id=rec.id,
            entity_id=rec.entity_id,
            employee_name=rec.employee_name,
            employee_tin=rec.employee_tin,
            period_year=rec.period_year,
            period_month=rec.period_month,
            gross_salary=float(rec.gross_salary),
            consolidated_relief=float(rec.consolidated_relief),
            pension_contribution=float(rec.pension_contribution),
            nhf_contribution=float(rec.nhf_contribution),
            other_reliefs=float(rec.other_reliefs),
            taxable_income=float(rec.taxable_income),
            tax_amount=float(rec.tax_amount),
        )
        for rec in records
    ]


@router.post(
    "/{entity_id}/paye",
    response_model=PAYERecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create PAYE record",
    tags=["Tax - PAYE"],
)
async def create_paye_record(
    entity_id: UUID,
    request: PAYERecordCreateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Create a PAYE record for an employee.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    from app.services.tax_calculators.paye_service import PAYEService
    
    paye_service = PAYEService(db)
    record = await paye_service.create_paye_record(
        entity_id=entity_id,
        employee_name=request.employee_name,
        employee_tin=request.employee_tin,
        period_year=request.period_year,
        period_month=request.period_month,
        gross_salary=request.gross_salary,
        pension_contribution=request.pension_contribution,
        nhf_contribution=request.nhf_contribution,
        other_reliefs=request.other_reliefs,
    )
    
    return PAYERecordResponse(
        id=record.id,
        entity_id=record.entity_id,
        employee_name=record.employee_name,
        employee_tin=record.employee_tin,
        period_year=record.period_year,
        period_month=record.period_month,
        gross_salary=float(record.gross_salary),
        consolidated_relief=float(record.consolidated_relief),
        pension_contribution=float(record.pension_contribution),
        nhf_contribution=float(record.nhf_contribution),
        other_reliefs=float(record.other_reliefs),
        taxable_income=float(record.taxable_income),
        tax_amount=float(record.tax_amount),
    )


@router.get(
    "/{entity_id}/paye/{year}/{month}/summary",
    response_model=PAYESummaryResponse,
    summary="Get PAYE summary",
    tags=["Tax - PAYE"],
)
async def get_paye_summary(
    entity_id: UUID,
    year: int,
    month: int = Path(..., ge=1, le=12),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get PAYE summary for a period (for FIRS filing).
    """
    await verify_entity_access(entity_id, current_user, db)
    
    from app.services.tax_calculators.paye_service import PAYEService
    
    paye_service = PAYEService(db)
    summary = await paye_service.get_paye_summary_for_period(entity_id, year, month)
    
    return PAYESummaryResponse(**summary)


# ===========================================
# WHT SCHEMAS
# ===========================================

class WHTCalculationRequest(BaseModel):
    """Schema for WHT calculation request."""
    gross_amount: float = Field(..., gt=0)
    service_type: str = Field(..., description="Type of service (dividends, interest, rent, royalties, professional_services, contract_supply, consultancy, technical_services, management_fees, director_fees, construction, other)")
    payee_type: str = Field("company", description="Whether payee is 'individual' or 'company'")


class WHTCalculationResponse(BaseModel):
    """Schema for WHT calculation response."""
    gross_amount: float
    wht_rate: float
    wht_amount: float
    net_amount: float
    service_type: str
    payee_type: str


class WHTGrossFromNetRequest(BaseModel):
    """Schema for calculating gross from net amount."""
    net_amount: float = Field(..., gt=0)
    service_type: str = Field(...)
    payee_type: str = Field("company")


class WHTRateResponse(BaseModel):
    """Schema for WHT rate info."""
    service_type: str
    individual_rate: float
    company_rate: float


class WHTSummaryResponse(BaseModel):
    """Schema for WHT period summary."""
    period_start: str
    period_end: str
    transaction_count: int
    total_gross_payments: float
    total_wht_deducted: float


class WHTVendorSummaryResponse(BaseModel):
    """Schema for WHT by vendor."""
    vendor_id: str
    vendor_name: str
    vendor_tin: Optional[str]
    total_gross_paid: float
    total_wht_deducted: float


# ===========================================
# WHT CALCULATION ENDPOINTS
# ===========================================

@router.post(
    "/wht/calculate",
    response_model=WHTCalculationResponse,
    summary="Calculate WHT",
    tags=["Tax - WHT"],
)
async def calculate_wht(
    request: WHTCalculationRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    Calculate Withholding Tax for a payment.
    
    WHT is deducted at source when making payments to vendors/contractors.
    
    **Nigerian WHT Rates:**
    - Dividends, Interest, Rent, Royalties: 10%
    - Professional Services: 10% (individual), 5% (company)
    - Contract/Supply, Consultancy, Construction: 5%
    - Technical Services, Management Fees, Director Fees: 10%
    """
    from app.services.tax_calculators.wht_service import (
        WHTCalculator, WHTServiceType, PayeeType
    )
    
    try:
        service_type = WHTServiceType(request.service_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid service type. Valid types: {[t.value for t in WHTServiceType]}",
        )
    
    try:
        payee_type = PayeeType(request.payee_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payee type. Use 'individual' or 'company'.",
        )
    
    result = WHTCalculator.calculate_wht(
        gross_amount=request.gross_amount,
        service_type=service_type,
        payee_type=payee_type,
    )
    
    return WHTCalculationResponse(**result)


@router.post(
    "/wht/calculate-gross",
    response_model=WHTCalculationResponse,
    summary="Calculate gross from net",
    tags=["Tax - WHT"],
)
async def calculate_gross_from_net(
    request: WHTGrossFromNetRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    Calculate gross amount when vendor quotes a net amount.
    
    This is useful when a vendor says "I want to receive ₦X net",
    and you need to calculate the gross amount and WHT.
    """
    from app.services.tax_calculators.wht_service import (
        WHTCalculator, WHTServiceType, PayeeType
    )
    
    try:
        service_type = WHTServiceType(request.service_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid service type. Valid types: {[t.value for t in WHTServiceType]}",
        )
    
    try:
        payee_type = PayeeType(request.payee_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payee type. Use 'individual' or 'company'.",
        )
    
    result = WHTCalculator.calculate_gross_from_net(
        net_amount=request.net_amount,
        service_type=service_type,
        payee_type=payee_type,
    )
    
    return WHTCalculationResponse(**result)


@router.get(
    "/wht/rates",
    response_model=List[WHTRateResponse],
    summary="Get all WHT rates",
    tags=["Tax - WHT"],
)
async def get_wht_rates(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get all Nigerian WHT rates by service type.
    """
    from app.services.tax_calculators.wht_service import WHTCalculator
    
    rates = WHTCalculator.get_all_wht_rates()
    return [WHTRateResponse(**rate) for rate in rates]


# ===========================================
# WHT TRACKING ENDPOINTS
# ===========================================

@router.get(
    "/{entity_id}/wht/summary",
    response_model=WHTSummaryResponse,
    summary="Get WHT summary",
    tags=["Tax - WHT"],
)
async def get_wht_summary(
    entity_id: UUID,
    start_date: date = Query(...),
    end_date: date = Query(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get WHT summary for a date range.
    
    Summarizes all WHT deducted from expense transactions.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    from app.services.tax_calculators.wht_service import WHTService
    
    wht_service = WHTService(db)
    summary = await wht_service.get_wht_summary_for_period(
        entity_id=entity_id,
        start_date=start_date,
        end_date=end_date,
    )
    
    return WHTSummaryResponse(**summary)


@router.get(
    "/{entity_id}/wht/by-vendor",
    response_model=List[WHTVendorSummaryResponse],
    summary="Get WHT by vendor",
    tags=["Tax - WHT"],
)
async def get_wht_by_vendor(
    entity_id: UUID,
    start_date: date = Query(...),
    end_date: date = Query(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get WHT breakdown by vendor for certificate generation.
    
    This data can be used to generate WHT certificates for vendors.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    from app.services.tax_calculators.wht_service import WHTService
    
    wht_service = WHTService(db)
    vendors = await wht_service.get_wht_by_vendor(
        entity_id=entity_id,
        start_date=start_date,
        end_date=end_date,
    )
    
    return [WHTVendorSummaryResponse(**v) for v in vendors]


# ===========================================
# CIT SCHEMAS
# ===========================================

class CITCalculationRequest(BaseModel):
    """Schema for CIT calculation request."""
    gross_turnover: float = Field(..., gt=0, description="Annual gross revenue/turnover")
    assessable_profit: float = Field(..., description="Taxable profit after allowable deductions")
    is_new_company: bool = Field(False, description="Is company in first 4 years of operation")
    company_age_years: int = Field(5, ge=0, description="Years since incorporation")
    claim_minimum_tax_exemption: bool = Field(False, description="Claim exemption from minimum tax")


class CITCalculationResponse(BaseModel):
    """Schema for CIT calculation response."""
    gross_turnover: float
    assessable_profit: float
    company_size: str
    cit_rate: float
    cit_on_profit: float
    minimum_tax: float
    is_minimum_tax_exempt: bool
    minimum_tax_applied: bool
    final_cit: float
    tertiary_education_tax: float
    total_tax_liability: float
    effective_rate: float


class CITProvisionalResponse(BaseModel):
    """Schema for provisional tax calculation."""
    gross_turnover: float
    assessable_profit: float
    company_size: str
    cit_rate: float
    final_cit: float
    tertiary_education_tax: float
    total_tax_liability: float
    first_installment: float
    second_installment: float
    first_installment_due: str
    second_installment_due: str


class CITThresholdResponse(BaseModel):
    """Schema for CIT threshold info."""
    company_size: str
    turnover_min: float
    turnover_max: Optional[float]
    cit_rate: float


class CITAdjustmentsRequest(BaseModel):
    """Schema for CIT adjustments."""
    add_backs: float = Field(0, ge=0, description="Non-deductible expenses to add back")
    further_deductions: float = Field(0, ge=0, description="Additional deductions allowed")
    capital_allowances: float = Field(0, ge=0, description="Capital allowances claimed")
    is_new_company: bool = Field(False)
    company_age_years: int = Field(5, ge=0)


class CITEntityCalculationResponse(BaseModel):
    """Schema for entity CIT calculation."""
    entity_id: str
    fiscal_year: int
    period_start: str
    period_end: str
    financial_data: dict
    cit_calculation: CITCalculationResponse


# ===========================================
# CIT CALCULATION ENDPOINTS
# ===========================================

@router.post(
    "/cit/calculate",
    response_model=CITCalculationResponse,
    summary="Calculate CIT",
    tags=["Tax - CIT"],
)
async def calculate_cit(
    request: CITCalculationRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    Calculate Company Income Tax (CIT).
    
    Uses Nigeria 2026 Tax Reform rates:
    - **Small companies (≤₦25M turnover):** 0%
    - **Medium companies (₦25M - ₦100M):** 20%
    - **Large companies (>₦100M):** 30%
    
    Also calculates:
    - Tertiary Education Tax (TET): 3% of assessable profit
    - Minimum tax (0.5% of turnover) if applicable
    """
    from app.services.tax_calculators.cit_service import CITCalculator
    
    result = CITCalculator.calculate_cit(
        gross_turnover=request.gross_turnover,
        assessable_profit=request.assessable_profit,
        is_new_company=request.is_new_company,
        company_age_years=request.company_age_years,
        claim_minimum_tax_exemption=request.claim_minimum_tax_exemption,
    )
    
    return CITCalculationResponse(**result)


@router.post(
    "/cit/provisional",
    response_model=CITProvisionalResponse,
    summary="Calculate provisional CIT",
    tags=["Tax - CIT"],
)
async def calculate_provisional_cit(
    request: CITCalculationRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    Calculate provisional tax installments.
    
    Provisional tax is paid in advance during the year in 2 installments:
    - First installment: Within 3 months of year start
    - Second installment: Within 6 months of year start
    """
    from app.services.tax_calculators.cit_service import CITCalculator
    
    result = CITCalculator.calculate_provisional_tax(
        estimated_turnover=request.gross_turnover,
        estimated_profit=request.assessable_profit,
    )
    
    return CITProvisionalResponse(**result)


@router.get(
    "/cit/thresholds",
    response_model=List[CITThresholdResponse],
    summary="Get CIT thresholds",
    tags=["Tax - CIT"],
)
async def get_cit_thresholds(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get all CIT thresholds for reference.
    
    Shows company size classifications and corresponding tax rates.
    """
    from app.services.tax_calculators.cit_service import CITCalculator
    
    thresholds = CITCalculator.get_cit_thresholds()
    return [CITThresholdResponse(**t) for t in thresholds]


# ===========================================
# CIT ENTITY ENDPOINTS
# ===========================================

@router.get(
    "/{entity_id}/cit/{fiscal_year}",
    response_model=CITEntityCalculationResponse,
    summary="Calculate CIT for entity",
    tags=["Tax - CIT"],
)
async def calculate_cit_for_entity(
    entity_id: UUID,
    fiscal_year: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Calculate CIT for a business entity for a fiscal year.
    
    Automatically gathers financial data from invoices and transactions.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    from app.services.tax_calculators.cit_service import CITService
    
    cit_service = CITService(db)
    result = await cit_service.calculate_cit_for_entity(
        entity_id=entity_id,
        fiscal_year=fiscal_year,
    )
    
    return CITEntityCalculationResponse(**result)


@router.post(
    "/{entity_id}/cit/{fiscal_year}",
    response_model=CITEntityCalculationResponse,
    summary="Calculate CIT with adjustments",
    tags=["Tax - CIT"],
)
async def calculate_cit_with_adjustments(
    entity_id: UUID,
    fiscal_year: int,
    adjustments: CITAdjustmentsRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Calculate CIT for an entity with tax adjustments.
    
    Allows specifying:
    - Add-backs (non-deductible expenses)
    - Further deductions
    - Capital allowances
    """
    await verify_entity_access(entity_id, current_user, db)
    
    from app.services.tax_calculators.cit_service import CITService
    
    cit_service = CITService(db)
    result = await cit_service.calculate_cit_for_entity(
        entity_id=entity_id,
        fiscal_year=fiscal_year,
        adjustments={
            "add_backs": adjustments.add_backs,
            "further_deductions": adjustments.further_deductions,
            "capital_allowances": adjustments.capital_allowances,
            "is_new_company": adjustments.is_new_company,
            "company_age_years": adjustments.company_age_years,
        },
    )
    
    return CITEntityCalculationResponse(**result)


# ===========================================
# ADDITIONAL PAYE ENDPOINTS
# ===========================================

class PAYERecordUpdateRequest(BaseModel):
    """Schema for updating a PAYE record."""
    employee_name: Optional[str] = None
    employee_tin: Optional[str] = None
    gross_salary: Optional[float] = Field(None, gt=0)
    pension_contribution: Optional[float] = Field(None, ge=0)
    nhf_contribution: Optional[float] = Field(None, ge=0)
    other_reliefs: Optional[float] = Field(None, ge=0)


class PAYEBatchCreateRequest(BaseModel):
    """Schema for batch creating PAYE records."""
    period_year: int = Field(...)
    period_month: int = Field(..., ge=1, le=12)
    records: List[dict] = Field(..., description="List of employee PAYE data")


class PAYEAnnualSummaryResponse(BaseModel):
    """Schema for annual PAYE summary."""
    entity_id: UUID
    year: int
    total_employees: int
    total_gross_salary: float
    total_paye_tax: float
    total_pension: float
    total_nhf: float
    monthly_breakdown: List[dict]


class TaxFilingCalendarResponse(BaseModel):
    """Schema for tax filing calendar."""
    upcoming_deadlines: List[dict]
    overdue: List[dict]


@router.patch(
    "/{entity_id}/paye/{paye_id}",
    response_model=PAYERecordResponse,
    summary="Update PAYE record",
    tags=["Tax - PAYE"],
)
async def update_paye_record(
    entity_id: UUID,
    paye_id: UUID,
    request: PAYERecordUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Update a PAYE record."""
    await verify_entity_access(entity_id, current_user, db)
    
    from sqlalchemy import select
    from app.models.tax import PAYERecord
    
    result = await db.execute(
        select(PAYERecord).where(
            PAYERecord.id == paye_id,
            PAYERecord.entity_id == entity_id,
        )
    )
    record = result.scalar_one_or_none()
    
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PAYE record not found",
        )
    
    # Update fields
    if request.employee_name is not None:
        record.employee_name = request.employee_name
    if request.employee_tin is not None:
        record.employee_tin = request.employee_tin
    if request.gross_salary is not None:
        record.gross_salary = request.gross_salary
    if request.pension_contribution is not None:
        record.pension_contribution = request.pension_contribution
    if request.nhf_contribution is not None:
        record.nhf_contribution = request.nhf_contribution
    if request.other_reliefs is not None:
        record.other_reliefs = request.other_reliefs
    
    # Recalculate tax
    from app.services.tax_calculators.paye_service import PAYECalculator
    calculator = PAYECalculator()
    
    # Calculate consolidated relief (20% of gross + 200,000)
    annual_gross = float(record.gross_salary) * 12
    cra = (0.2 * annual_gross) + 200000
    record.consolidated_relief = cra / 12
    
    # Calculate taxable income
    total_reliefs = (
        float(record.consolidated_relief) +
        float(record.pension_contribution) +
        float(record.nhf_contribution) +
        float(record.other_reliefs)
    )
    record.taxable_income = max(0, float(record.gross_salary) - total_reliefs)
    
    # Calculate tax
    calc_result = calculator.calculate(float(record.taxable_income) * 12)
    record.tax_amount = calc_result["tax"] / 12
    
    await db.commit()
    await db.refresh(record)
    
    return PAYERecordResponse(
        id=record.id,
        entity_id=record.entity_id,
        employee_name=record.employee_name,
        employee_tin=record.employee_tin,
        period_year=record.period_year,
        period_month=record.period_month,
        gross_salary=float(record.gross_salary),
        consolidated_relief=float(record.consolidated_relief),
        pension_contribution=float(record.pension_contribution),
        nhf_contribution=float(record.nhf_contribution),
        other_reliefs=float(record.other_reliefs),
        taxable_income=float(record.taxable_income),
        tax_amount=float(record.tax_amount),
    )


@router.delete(
    "/{entity_id}/paye/{paye_id}",
    response_model=MessageResponse,
    summary="Delete PAYE record",
    tags=["Tax - PAYE"],
)
async def delete_paye_record(
    entity_id: UUID,
    paye_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Delete a PAYE record."""
    await verify_entity_access(entity_id, current_user, db)
    
    from sqlalchemy import select, delete
    from app.models.tax import PAYERecord
    
    result = await db.execute(
        select(PAYERecord).where(
            PAYERecord.id == paye_id,
            PAYERecord.entity_id == entity_id,
        )
    )
    record = result.scalar_one_or_none()
    
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PAYE record not found",
        )
    
    await db.execute(
        delete(PAYERecord).where(PAYERecord.id == paye_id)
    )
    await db.commit()
    
    return MessageResponse(message="PAYE record deleted successfully")


@router.post(
    "/{entity_id}/paye/batch",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Batch create PAYE records",
    tags=["Tax - PAYE"],
    description="Create multiple PAYE records for a monthly payroll run.",
)
async def batch_create_paye_records(
    entity_id: UUID,
    request: PAYEBatchCreateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Batch create PAYE records for monthly payroll."""
    await verify_entity_access(entity_id, current_user, db)
    
    from app.services.tax_calculators.paye_service import PAYEService
    
    paye_service = PAYEService(db)
    
    created_count = 0
    errors = []
    
    for emp_data in request.records:
        try:
            await paye_service.create_paye_record(
                entity_id=entity_id,
                employee_name=emp_data.get("employee_name", "Unknown"),
                employee_tin=emp_data.get("employee_tin"),
                period_year=request.period_year,
                period_month=request.period_month,
                gross_salary=emp_data.get("gross_salary", 0),
                pension_contribution=emp_data.get("pension_contribution", 0),
                nhf_contribution=emp_data.get("nhf_contribution", 0),
                other_reliefs=emp_data.get("other_reliefs", 0),
            )
            created_count += 1
        except Exception as e:
            errors.append(f"{emp_data.get('employee_name', 'Unknown')}: {str(e)}")
    
    message = f"Created {created_count} PAYE records for {request.period_year}-{request.period_month:02d}"
    if errors:
        message += f". Errors: {len(errors)}"
    
    return MessageResponse(message=message)


@router.get(
    "/{entity_id}/paye/{year}/annual-summary",
    response_model=PAYEAnnualSummaryResponse,
    summary="Get annual PAYE summary",
    tags=["Tax - PAYE"],
    description="Get annual PAYE summary for filing.",
)
async def get_annual_paye_summary(
    entity_id: UUID,
    year: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get annual PAYE summary."""
    await verify_entity_access(entity_id, current_user, db)
    
    from sqlalchemy import select, func
    from app.models.tax import PAYERecord
    
    # Get all records for the year
    query = select(PAYERecord).where(
        PAYERecord.entity_id == entity_id,
        PAYERecord.period_year == year,
    )
    result = await db.execute(query)
    records = result.scalars().all()
    
    # Calculate totals
    total_gross = sum(float(r.gross_salary) for r in records)
    total_tax = sum(float(r.tax_amount) for r in records)
    total_pension = sum(float(r.pension_contribution) for r in records)
    total_nhf = sum(float(r.nhf_contribution) for r in records)
    
    # Get unique employee count
    unique_employees = len(set(r.employee_tin or r.employee_name for r in records))
    
    # Monthly breakdown
    monthly_data = {}
    for r in records:
        month = r.period_month
        if month not in monthly_data:
            monthly_data[month] = {
                "month": month,
                "employee_count": 0,
                "total_gross": 0,
                "total_tax": 0,
            }
        monthly_data[month]["employee_count"] += 1
        monthly_data[month]["total_gross"] += float(r.gross_salary)
        monthly_data[month]["total_tax"] += float(r.tax_amount)
    
    monthly_breakdown = [monthly_data[m] for m in sorted(monthly_data.keys())]
    
    return PAYEAnnualSummaryResponse(
        entity_id=entity_id,
        year=year,
        total_employees=unique_employees,
        total_gross_salary=total_gross,
        total_paye_tax=total_tax,
        total_pension=total_pension,
        total_nhf=total_nhf,
        monthly_breakdown=monthly_breakdown,
    )


@router.get(
    "/{entity_id}/tax/filing-calendar",
    response_model=TaxFilingCalendarResponse,
    summary="Get tax filing calendar",
    tags=["Tax Management"],
    description="Get upcoming and overdue tax filing deadlines.",
)
async def get_tax_filing_calendar(
    entity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get tax filing calendar with deadlines."""
    await verify_entity_access(entity_id, current_user, db)
    
    from datetime import datetime
    today = date.today()
    
    # Generate filing deadlines
    upcoming = []
    overdue = []
    
    # VAT (21st of each month for previous month)
    current_month = today.month
    current_year = today.year
    
    # VAT for previous month
    vat_deadline = date(current_year, current_month, 21)
    if today <= vat_deadline:
        upcoming.append({
            "type": "VAT",
            "description": f"VAT Return for {(current_month - 1) if current_month > 1 else 12}/{current_year if current_month > 1 else current_year - 1}",
            "deadline": vat_deadline.isoformat(),
            "days_remaining": (vat_deadline - today).days,
        })
    else:
        overdue.append({
            "type": "VAT",
            "description": f"VAT Return for {(current_month - 1) if current_month > 1 else 12}/{current_year if current_month > 1 else current_year - 1}",
            "deadline": vat_deadline.isoformat(),
            "days_overdue": (today - vat_deadline).days,
        })
    
    # PAYE (10th of each month for previous month)
    paye_deadline = date(current_year, current_month, 10)
    if today <= paye_deadline:
        upcoming.append({
            "type": "PAYE",
            "description": f"PAYE Remittance for {(current_month - 1) if current_month > 1 else 12}/{current_year if current_month > 1 else current_year - 1}",
            "deadline": paye_deadline.isoformat(),
            "days_remaining": (paye_deadline - today).days,
        })
    
    # WHT (21st of each month)
    wht_deadline = date(current_year, current_month, 21)
    if today <= wht_deadline:
        upcoming.append({
            "type": "WHT",
            "description": f"WHT Remittance for {(current_month - 1) if current_month > 1 else 12}/{current_year if current_month > 1 else current_year - 1}",
            "deadline": wht_deadline.isoformat(),
            "days_remaining": (wht_deadline - today).days,
        })
    
    # CIT (6 months after fiscal year end - assuming Dec year end)
    cit_deadline = date(current_year, 6, 30)
    if current_month <= 6 and today <= cit_deadline:
        upcoming.append({
            "type": "CIT",
            "description": f"CIT Return for {current_year - 1}",
            "deadline": cit_deadline.isoformat(),
            "days_remaining": (cit_deadline - today).days,
        })
    
    # Sort by deadline
    upcoming.sort(key=lambda x: x["deadline"])
    overdue.sort(key=lambda x: x["deadline"], reverse=True)
    
    return TaxFilingCalendarResponse(
        upcoming_deadlines=upcoming,
        overdue=overdue,
    )


@router.get(
    "/{entity_id}/wht/{year}/annual-report",
    summary="Get annual WHT report",
    tags=["Tax - WHT"],
    description="Get annual WHT summary report.",
)
async def get_annual_wht_report(
    entity_id: UUID,
    year: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get annual WHT report."""
    await verify_entity_access(entity_id, current_user, db)
    
    from sqlalchemy import select, func
    from app.models.transaction import Transaction, TransactionType
    from app.models.vendor import Vendor
    
    # Get all expense transactions for the year with WHT
    query = select(Transaction).where(
        Transaction.entity_id == entity_id,
        Transaction.transaction_type == TransactionType.EXPENSE,
        Transaction.is_deleted == False,
    ).where(
        func.extract('year', Transaction.transaction_date) == year
    )
    
    result = await db.execute(query)
    transactions = result.scalars().all()
    
    # Group by vendor
    vendor_wht = {}
    for txn in transactions:
        if txn.vendor_id:
            vendor_id = str(txn.vendor_id)
            if vendor_id not in vendor_wht:
                vendor_wht[vendor_id] = {
                    "vendor_id": vendor_id,
                    "vendor_name": txn.vendor.name if txn.vendor else "Unknown",
                    "vendor_tin": txn.vendor.tin if txn.vendor else None,
                    "total_payments": 0,
                    "total_wht": 0,
                    "wht_rate": float(txn.vendor.default_wht_rate or 0) if txn.vendor else 0,
                }
            vendor_wht[vendor_id]["total_payments"] += float(txn.amount)
            vendor_wht[vendor_id]["total_wht"] += float(txn.amount) * (vendor_wht[vendor_id]["wht_rate"] / 100)
    
    total_payments = sum(v["total_payments"] for v in vendor_wht.values())
    total_wht = sum(v["total_wht"] for v in vendor_wht.values())
    
    return {
        "entity_id": str(entity_id),
        "year": year,
        "total_payments": total_payments,
        "total_wht_deducted": total_wht,
        "vendor_count": len(vendor_wht),
        "vendors": list(vendor_wht.values()),
    }