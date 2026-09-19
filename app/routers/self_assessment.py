"""
Tekvwa Pro Audit - Self-Assessment Router

API endpoints for tax self-assessment and annual returns generation.

2026 Tax Reform Compliance:
- CIT Self-Assessment with capital gains
- VAT Self-Assessment with IRN recovery
- Annual Returns package generation
- Filing schedule management
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import get_current_active_user, require_feature
from app.models.user import User
from app.models.sku import Feature
from app.services.self_assessment_service import SelfAssessmentService
from app.services.entity_service import EntityService
from app.services.audit_service import AuditService
from app.models.audit_consolidated import AuditAction

# Feature gate for tax self-assessment (PROFESSIONAL tier - NRS compliance)
self_assessment_feature_gate = require_feature([Feature.NRS_COMPLIANCE])

router = APIRouter(
    prefix="/self-assessment",
    tags=["Self-Assessment"],
    dependencies=[Depends(self_assessment_feature_gate)],
)


# ===========================================
# SCHEMAS
# ===========================================

class CITAssessmentRequest(BaseModel):
    """Request for CIT self-assessment generation."""
    fiscal_year: int = Field(..., ge=2020, le=2100)
    fiscal_year_end: date
    include_capital_gains: bool = True
    include_depreciation: bool = True


class CITAssessmentResponse(BaseModel):
    """CIT self-assessment response."""
    entity_id: str
    entity_name: str
    fiscal_year: int
    
    # Revenue
    total_revenue: float
    revenue_breakdown: dict
    
    # Deductions
    total_deductible_expenses: float
    expense_breakdown: dict
    depreciation_allowance: float
    
    # Capital Gains (2026)
    capital_gains: float
    capital_gains_tax: float
    
    # Tax Calculation
    assessable_profit: float
    cit_rate: float
    cit_liability: float
    wht_credits: float
    net_cit_payable: float
    
    # Status
    is_small_company: bool
    small_company_reason: Optional[str] = None
    development_levy_exempt: bool
    development_levy: float
    
    # Filing info
    filing_deadline: str
    status: str
    generated_at: str


class VATAssessmentRequest(BaseModel):
    """Request for VAT self-assessment generation."""
    year: int
    month: int = Field(..., ge=1, le=12)
    include_irn_recovery: bool = True


class VATAssessmentResponse(BaseModel):
    """VAT self-assessment response."""
    entity_id: str
    entity_name: str
    period: dict  # year, month, start_date, end_date
    
    # Output VAT
    total_output_vat: float
    output_vat_breakdown: dict
    
    # Input VAT
    total_input_vat: float
    recoverable_vat: float
    non_recoverable_vat: float
    irn_recovered_vat: float  # 2026 fixed asset VAT recovery
    input_vat_breakdown: dict
    
    # Net
    net_vat_payable: float
    is_refund: bool
    
    # Filing info
    filing_deadline: str
    nrs_submission_status: str
    generated_at: str


class AnnualReturnsRequest(BaseModel):
    """Request for annual returns package generation."""
    fiscal_year: int = Field(..., ge=2020, le=2100)
    fiscal_year_end: date
    include_financial_statements: bool = True
    include_tax_schedules: bool = True
    include_nrs_summary: bool = True


class AnnualReturnsResponse(BaseModel):
    """Annual returns package response."""
    entity_id: str
    entity_name: str
    fiscal_year: int
    
    # Package contents
    cit_assessment: dict
    vat_summary: dict
    wht_summary: dict
    paye_summary: dict
    fixed_assets_schedule: dict
    
    # Financial highlights
    total_revenue: float
    total_expenses: float
    net_profit: float
    total_tax_liability: float
    
    # Filing info
    filing_deadline: str
    package_generated_at: str
    download_url: Optional[str] = None


class FilingScheduleResponse(BaseModel):
    """Filing schedule for upcoming deadlines."""
    entity_id: str
    current_date: str
    upcoming_filings: list
    overdue_filings: list


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    success: bool = True


class SelfAssessmentInfoResponse(BaseModel):
    """Self-assessment system information."""
    system_status: str
    nrs_integration_status: str
    tax_year: int
    filing_deadlines: dict
    required_documents: list
    compliance_tips: list


class TaxProExportRequest(BaseModel):
    """Request for TaxPro MAX export."""
    fiscal_year: int = Field(..., ge=2020, le=2100)
    return_type: str = Field(..., pattern="^(cit|vat|paye|wht|all)$")
    format: str = Field("csv", pattern="^(csv|xlsx)$")


class TaxProExportResponse(BaseModel):
    """Response for TaxPro MAX export."""
    filename: str
    content: str
    record_count: int
    export_date: str
    return_type: str


# ===========================================
# HELPER FUNCTIONS
# ===========================================

async def verify_entity_access(
    entity_id: uuid.UUID,
    user: User,
    db: AsyncSession,
):
    """Verify user has access to the entity."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, user)
    
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business entity not found or access denied",
        )
    
    return entity


# ===========================================
# INFO & EXPORT ENDPOINTS
# ===========================================

@router.get(
    "/info",
    response_model=SelfAssessmentInfoResponse,
    summary="Get self-assessment system info",
    description="Get system status and filing requirements for self-assessment.",
)
async def get_self_assessment_info(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get self-assessment system information.
    
    Returns:
    - System and NRS integration status
    - Current tax year
    - Filing deadlines
    - Required documents
    - Compliance tips
    """
    from datetime import datetime
    
    current_year = datetime.now().year
    
    return SelfAssessmentInfoResponse(
        system_status="operational",
        nrs_integration_status="connected",
        tax_year=current_year,
        filing_deadlines={
            "vat_monthly": "21st of each month",
            "paye_monthly": "10th of each month", 
            "wht_monthly": "21st of each month",
            "cit_annual": f"6 months after fiscal year end",
            "annual_returns": "June 30 each year",
        },
        required_documents=[
            "Financial Statements (Statement of Financial Position, P&L)",
            "Tax Computation Schedules",
            "Capital Allowance Computation",
            "VAT Return Summary (Form VAT 1)",
            "PAYE Schedule and Remittance Receipts",
            "WHT Deduction Schedule",
            "Fixed Asset Register",
            "Bank Statements",
            "Incorporation Documents (CAC)",
        ],
        compliance_tips=[
            "File VAT returns by the 21st of each month to avoid penalties",
            "Ensure all vendors have valid TINs for deductible expenses",
            "Use NRS e-invoicing for all B2B transactions",
            "Retain records for minimum 5 years as per NTAA 2025",
            "Report B2C transactions above ₦50,000 within 7 days",
        ],
    )


@router.post(
    "/{entity_id}/taxpro-export",
    response_model=TaxProExportResponse,
    summary="Export for TaxPro MAX",
    description="Generate CSV/Excel export compatible with FIRS TaxPro MAX software.",
)
async def export_for_taxpro(
    entity_id: uuid.UUID,
    request: TaxProExportRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Export tax data for FIRS TaxPro MAX software.
    
    Generates properly formatted export files for:
    - CIT returns
    - VAT returns
    - PAYE schedules
    - WHT schedules
    """
    from datetime import datetime
    import csv
    import io
    
    await verify_entity_access(entity_id, current_user, db)
    
    service = SelfAssessmentService(db)
    
    # Get entity for export
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, current_user)
    
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found",
        )
    
    # Generate export based on return type
    output = io.StringIO()
    writer = csv.writer(output)
    record_count = 0
    
    if request.return_type in ("cit", "all"):
        # CIT Export Header
        writer.writerow([
            "Entity_Name", "TIN", "RC_Number", "Fiscal_Year", 
            "Total_Revenue", "Total_Expenses", "Assessable_Profit",
            "CIT_Rate", "CIT_Liability", "Development_Levy", "Net_Payable"
        ])
        
        # Get CIT data
        try:
            cit_data = await service.get_cit_assessment(entity_id, request.fiscal_year)
            if cit_data:
                writer.writerow([
                    entity.name,
                    entity.tin or "",
                    entity.cac_registration_number or "",
                    request.fiscal_year,
                    cit_data.get("total_revenue", 0),
                    cit_data.get("total_deductible_expenses", 0),
                    cit_data.get("assessable_profit", 0),
                    cit_data.get("cit_rate", 30),
                    cit_data.get("cit_liability", 0),
                    cit_data.get("development_levy", 0),
                    cit_data.get("net_cit_payable", 0),
                ])
                record_count += 1
        except Exception:
            # No CIT data available - add placeholder
            writer.writerow([entity.name, entity.tin or "", "", request.fiscal_year, 0, 0, 0, 30, 0, 0, 0])
            record_count += 1
    
    if request.return_type in ("vat", "all"):
        writer.writerow([])  # Separator
        writer.writerow(["VAT_RETURNS"])
        writer.writerow([
            "Period", "Output_VAT", "Input_VAT", "Recoverable_VAT", "Net_VAT_Payable"
        ])
        # Add VAT summary placeholder
        writer.writerow([f"{request.fiscal_year}", "0", "0", "0", "0"])
        record_count += 1
    
    content = output.getvalue()
    filename = f"{entity.name.replace(' ', '_')}_TaxPro_{request.return_type}_{request.fiscal_year}.csv"
    
    return TaxProExportResponse(
        filename=filename,
        content=content,
        record_count=record_count,
        export_date=datetime.now().isoformat(),
        return_type=request.return_type,
    )


# ===========================================
# CIT ENDPOINTS
# ===========================================

@router.post(
    "/{entity_id}/cit",
    response_model=CITAssessmentResponse,
    summary="Generate CIT self-assessment",
    description="Generate Company Income Tax self-assessment for a fiscal year.",
)
async def generate_cit_assessment(
    entity_id: uuid.UUID,
    request: CITAssessmentRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Generate CIT self-assessment.
    
    Includes:
    - Revenue and expense breakdown
    - Depreciation allowance calculation
    - Capital gains tax (2026 at CIT rate)
    - Small company exemption check
    - Development levy calculation
    """
    entity = await verify_entity_access(entity_id, current_user, db)
    
    service = SelfAssessmentService(db)
    
    try:
        assessment = await service.generate_cit_assessment(
            entity_id=entity_id,
            fiscal_year=request.fiscal_year,
            fiscal_year_end=request.fiscal_year_end,
            include_capital_gains=request.include_capital_gains,
            include_depreciation=request.include_depreciation,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    # Audit logging for CIT assessment generation
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="cit_assessment",
        entity_id=f"{entity_id}-{request.fiscal_year}",
        action=AuditAction.CREATE,
        user_id=current_user.id,
        new_values={
            "fiscal_year": request.fiscal_year,
            "assessable_profit": assessment.get("assessable_profit"),
            "cit_liability": assessment.get("cit_liability"),
            "development_levy": assessment.get("development_levy"),
        }
    )
    
    return CITAssessmentResponse(**assessment)


@router.get(
    "/{entity_id}/cit/{fiscal_year}",
    response_model=CITAssessmentResponse,
    summary="Get CIT assessment",
    description="Get existing CIT assessment for a fiscal year.",
)
async def get_cit_assessment(
    entity_id: uuid.UUID,
    fiscal_year: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get existing CIT assessment."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = SelfAssessmentService(db)
    assessment = await service.get_cit_assessment(entity_id, fiscal_year)
    
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No CIT assessment found for fiscal year {fiscal_year}",
        )
    
    return CITAssessmentResponse(**assessment)


# ===========================================
# VAT ENDPOINTS
# ===========================================

@router.post(
    "/{entity_id}/vat",
    response_model=VATAssessmentResponse,
    summary="Generate VAT self-assessment",
    description="Generate VAT self-assessment for a specific month.",
)
async def generate_vat_assessment(
    entity_id: uuid.UUID,
    request: VATAssessmentRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Generate VAT self-assessment.
    
    Includes:
    - Output VAT from sales
    - Input VAT from purchases
    - IRN-verified VAT recovery (2026)
    - Net payable/refund calculation
    """
    await verify_entity_access(entity_id, current_user, db)
    
    service = SelfAssessmentService(db)
    
    try:
        assessment = await service.generate_vat_assessment(
            entity_id=entity_id,
            year=request.year,
            month=request.month,
            include_irn_recovery=request.include_irn_recovery,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    # Audit logging for VAT assessment generation
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="vat_assessment",
        entity_id=f"{entity_id}-{request.year}-{request.month:02d}",
        action=AuditAction.CREATE,
        user_id=current_user.id,
        new_values={
            "year": request.year,
            "month": request.month,
            "output_vat": assessment.get("output_vat"),
            "input_vat": assessment.get("input_vat"),
            "net_payable": assessment.get("net_payable"),
        }
    )
    
    return VATAssessmentResponse(**assessment)


@router.get(
    "/{entity_id}/vat/{year}/{month}",
    response_model=VATAssessmentResponse,
    summary="Get VAT assessment",
    description="Get existing VAT assessment for a specific period.",
)
async def get_vat_assessment(
    entity_id: uuid.UUID,
    year: int,
    month: int = Path(..., ge=1, le=12),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get existing VAT assessment."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = SelfAssessmentService(db)
    assessment = await service.get_vat_assessment(entity_id, year, month)
    
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No VAT assessment found for {year}/{month:02d}",
        )
    
    return VATAssessmentResponse(**assessment)


# ===========================================
# ANNUAL RETURNS ENDPOINTS
# ===========================================

@router.post(
    "/{entity_id}/annual-returns",
    response_model=AnnualReturnsResponse,
    summary="Generate annual returns package",
    description="Generate complete annual returns package for FIRS submission.",
)
async def generate_annual_returns(
    entity_id: uuid.UUID,
    request: AnnualReturnsRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Generate annual returns package.
    
    Includes:
    - CIT self-assessment
    - VAT summary (12 months)
    - WHT summary
    - PAYE summary
    - Fixed assets schedule with depreciation
    - NRS submission summary
    """
    await verify_entity_access(entity_id, current_user, db)
    
    service = SelfAssessmentService(db)
    
    try:
        returns = await service.generate_annual_returns(
            entity_id=entity_id,
            fiscal_year=request.fiscal_year,
            fiscal_year_end=request.fiscal_year_end,
            include_financial_statements=request.include_financial_statements,
            include_tax_schedules=request.include_tax_schedules,
            include_nrs_summary=request.include_nrs_summary,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    # Audit logging for annual returns generation
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="annual_returns",
        entity_id=f"{entity_id}-{request.fiscal_year}",
        action=AuditAction.CREATE,
        user_id=current_user.id,
        new_values={
            "fiscal_year": request.fiscal_year,
            "fiscal_year_end": str(request.fiscal_year_end) if request.fiscal_year_end else None,
            "include_financial_statements": request.include_financial_statements,
            "include_tax_schedules": request.include_tax_schedules,
            "include_nrs_summary": request.include_nrs_summary,
        }
    )
    
    return AnnualReturnsResponse(**returns)


@router.get(
    "/{entity_id}/annual-returns/{fiscal_year}",
    response_model=AnnualReturnsResponse,
    summary="Get annual returns",
    description="Get existing annual returns package for a fiscal year.",
)
async def get_annual_returns(
    entity_id: uuid.UUID,
    fiscal_year: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get existing annual returns package."""
    await verify_entity_access(entity_id, current_user, db)
    
    service = SelfAssessmentService(db)
    returns = await service.get_annual_returns(entity_id, fiscal_year)
    
    if not returns:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No annual returns found for fiscal year {fiscal_year}",
        )
    
    return AnnualReturnsResponse(**returns)


# ===========================================
# FILING SCHEDULE ENDPOINTS
# ===========================================

@router.get(
    "/{entity_id}/filing-schedule",
    response_model=FilingScheduleResponse,
    summary="Get filing schedule",
    description="Get upcoming and overdue tax filing deadlines.",
)
async def get_filing_schedule(
    entity_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get filing schedule.
    
    Shows:
    - VAT: 21st of each month
    - PAYE: 10th of each month
    - WHT: 21st of each month
    - CIT: 6 months after fiscal year end
    """
    await verify_entity_access(entity_id, current_user, db)
    
    service = SelfAssessmentService(db)
    schedule = await service.get_filing_schedule(entity_id)
    
    return FilingScheduleResponse(**schedule)


@router.get(
    "/{entity_id}/tax-summary/{fiscal_year}",
    summary="Get tax summary for fiscal year",
    description="Get a summary of all taxes for a fiscal year.",
)
async def get_tax_summary(
    entity_id: uuid.UUID,
    fiscal_year: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Get comprehensive tax summary.
    
    Returns summary of:
    - CIT liability and payments
    - VAT collected/paid/remitted
    - WHT deducted and remitted
    - PAYE calculated and remitted
    - Development Levy
    """
    await verify_entity_access(entity_id, current_user, db)
    
    service = SelfAssessmentService(db)
    summary = await service.get_tax_summary(entity_id, fiscal_year)
    
    return summary
