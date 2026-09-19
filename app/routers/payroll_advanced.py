"""
Tekvwa Pro Audit - Advanced Payroll Router

API endpoints for advanced payroll features:
- Compliance Status Engine
- Payroll Impact Preview
- Exception Management
- Decision Logs
- YTD Ledger
- Opening Balances
- What-If Simulations
- Ghost Worker Detection
"""

import uuid
from datetime import date
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, Body
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import get_current_user, get_current_active_user, get_current_entity_id, require_feature
from app.models.user import User
from app.models.sku_enums import Feature
from app.models.payroll import Employee
from app.services.payroll_advanced_service import PayrollAdvancedService
from app.services.audit_service import AuditService
from app.models.audit_consolidated import AuditAction
from app.schemas.payroll_advanced import (
    ComplianceSnapshotCreate,
    ComplianceSnapshotResponse,
    ComplianceStatusItem,
    PayrollImpactPreviewResponse,
    PayrollImpactPreviewRequest,
    VarianceDriver,
    PayrollExceptionBase,
    PayrollExceptionResponse,
    AcknowledgeExceptionRequest,
    ExceptionSummary,
    DecisionLogCreate,
    DecisionLogResponse,
    DecisionLogListResponse,
    YTDLedgerResponse,
    YTDLedgerSummary,
    OpeningBalanceCreate,
    OpeningBalanceResponse,
    PayslipExplanationResponse,
    VarianceLogResponse,
    VarianceReasonUpdate,
    CTCSnapshotResponse,
    CTCTrendResponse,
    WhatIfSimulationRequest,
    WhatIfSimulationResponse,
    GhostWorkerDetectionResponse,
    GhostWorkerScanResult,
    ResolveGhostWorkerRequest,
)

# Feature gate for advanced payroll - requires Professional tier or higher
payroll_advanced_feature_gate = require_feature([Feature.PAYROLL_ADVANCED])

router = APIRouter(dependencies=[Depends(payroll_advanced_feature_gate)])


# ===========================================
# COMPLIANCE SNAPSHOT ENDPOINTS
# ===========================================

@router.get(
    "/compliance/current",
    response_model=dict,
    summary="Get current compliance status",
    description="Get real-time compliance status for statutory remittances including PAYE, Pension, NHF, NSITF, ITF.",
)
async def get_current_compliance_status(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Get current compliance status dashboard.
    
    Returns:
    - Current month snapshot with status for each remittance type
    - YTD summary totals
    - Overall compliance status (compliant/at_risk/overdue)
    - Penalty exposure estimates
    """
    service = PayrollAdvancedService(db)
    return await service.get_current_compliance_status(entity_id)


@router.get(
    "/compliance/snapshots",
    response_model=dict,
    summary="List compliance snapshots",
    description="Get paginated list of compliance snapshots with optional year filter.",
)
async def list_compliance_snapshots(
    year: Optional[int] = Query(None, description="Filter by year"),
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=24),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """List compliance snapshots with pagination."""
    service = PayrollAdvancedService(db)
    
    snapshots, total = await service.list_compliance_snapshots(
        entity_id=entity_id,
        year=year,
        page=page,
        per_page=per_page,
    )
    
    items = [
        service._format_snapshot_response(s)
        for s in snapshots
    ]
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page > 0 else 0,
    }


@router.get(
    "/compliance/snapshots/{period_month}/{period_year}",
    response_model=dict,
    summary="Get compliance snapshot for period",
    description="Get compliance snapshot for a specific month/year.",
)
async def get_compliance_snapshot(
    period_month: int = Path(..., ge=1, le=12),
    period_year: int = Path(..., ge=2020, le=2050),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get compliance snapshot for a specific period."""
    service = PayrollAdvancedService(db)
    
    snapshot = await service.get_compliance_snapshot(
        entity_id=entity_id,
        period_month=period_month,
        period_year=period_year,
    )
    
    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Compliance snapshot not found for {period_month}/{period_year}",
        )
    
    return service._format_snapshot_response(snapshot)


@router.post(
    "/compliance/snapshots",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Generate compliance snapshot",
    description="Generate or refresh compliance snapshot for a specific period.",
)
async def generate_compliance_snapshot(
    data: ComplianceSnapshotCreate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Generate or update compliance snapshot for a period.
    
    This calculates:
    - Amounts due from payroll data
    - Amounts paid from remittance records
    - Days overdue based on statutory due dates
    - Estimated penalties for late payments
    """
    service = PayrollAdvancedService(db)
    
    snapshot = await service.generate_compliance_snapshot(
        entity_id=entity_id,
        period_month=data.period_month,
        period_year=data.period_year,
        paye_tax_state=data.paye_tax_state,
    )
    
    # Audit logging for compliance snapshot generation
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="compliance_snapshot",
        entity_id=str(snapshot.id),
        action=AuditAction.CREATE,
        user_id=current_user.id,
        new_values={
            "period_month": data.period_month,
            "period_year": data.period_year,
            "overall_status": snapshot.overall_status.value if hasattr(snapshot, 'overall_status') else None,
        }
    )
    
    return service._format_snapshot_response(snapshot)


@router.post(
    "/compliance/refresh/{year}",
    response_model=dict,
    summary="Refresh all compliance snapshots for year",
    description="Regenerate all compliance snapshots for a given year.",
)
async def refresh_compliance_snapshots(
    year: int = Path(..., ge=2020, le=2050),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Refresh all compliance snapshots for a year."""
    service = PayrollAdvancedService(db)
    
    snapshots = await service.refresh_all_compliance_snapshots(
        entity_id=entity_id,
        year=year,
    )
    
    return {
        "year": year,
        "snapshots_refreshed": len(snapshots),
        "message": f"Successfully refreshed {len(snapshots)} compliance snapshots for {year}",
    }


@router.get(
    "/compliance/calendar/{year}",
    response_model=dict,
    summary="Get compliance calendar",
    description="Get compliance calendar view for the year showing due dates and status for each month.",
)
async def get_compliance_calendar(
    year: int = Path(..., ge=2020, le=2050),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Get compliance calendar for the year.
    
    Shows:
    - Due dates for each remittance type per month
    - Current status (on_time, overdue, pending, etc.)
    - Penalty indicators
    """
    service = PayrollAdvancedService(db)
    return await service.get_compliance_calendar(entity_id, year)


# ===========================================
# PAYROLL IMPACT PREVIEW ENDPOINTS
# ===========================================

# NOTE: Static routes (/latest, /history) MUST come BEFORE parameterized routes (/{payroll_run_id})
# Otherwise FastAPI will try to parse "latest" or "history" as a UUID and return 422

@router.get(
    "/impact-preview/latest",
    response_model=dict,
    summary="Get latest impact preview",
    description="Get the most recent impact preview for the entity.",
)
async def get_latest_impact_preview(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Get the most recent impact preview.
    
    Useful for dashboard widgets to show latest payroll comparison.
    """
    service = PayrollAdvancedService(db)
    
    preview = await service.get_latest_impact_preview(entity_id)
    
    if not preview:
        return {
            "message": "No impact previews found",
            "has_preview": False,
        }
    
    response = service.format_impact_preview_response(preview)
    response["has_preview"] = True
    return response


@router.get(
    "/impact-preview/history",
    response_model=dict,
    summary="List impact preview history",
    description="Get paginated list of impact previews for the entity.",
)
async def list_impact_previews(
    year: Optional[int] = Query(None, description="Filter by year"),
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=50),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    List impact previews with pagination.
    
    Returns:
    - List of impact preview summaries with payroll run details
    - Total count and pagination info
    """
    service = PayrollAdvancedService(db)
    
    rows, total = await service.list_impact_previews(
        entity_id=entity_id,
        year=year,
        page=page,
        per_page=per_page,
    )
    
    # Each row is a tuple of (PayrollImpactPreview, PayrollRun)
    items = [
        service.format_impact_preview_response(preview, payroll_run)
        for preview, payroll_run in rows
    ]
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page > 0 else 0,
    }


@router.get(
    "/impact-preview/{payroll_run_id}",
    response_model=dict,
    summary="Get impact preview for payroll run",
    description="Get the impact preview analysis for a specific payroll run, comparing it to the previous period.",
)
async def get_impact_preview(
    payroll_run_id: uuid.UUID = Path(..., description="ID of the payroll run"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Get impact preview for a payroll run.
    
    Returns:
    - Current vs previous period totals
    - Variance analysis (gross, net, PAYE, employer cost)
    - Top 5 variance drivers (new hires, terminations, salary changes, etc.)
    - Human-readable impact summary
    """
    service = PayrollAdvancedService(db)
    
    preview = await service.get_impact_preview(
        entity_id=entity_id,
        payroll_run_id=payroll_run_id,
    )
    
    if not preview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Impact preview not found for payroll run {payroll_run_id}",
        )
    
    return service.format_impact_preview_response(preview)


@router.post(
    "/impact-preview/{payroll_run_id}",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Generate impact preview",
    description="Generate or refresh the impact preview for a payroll run.",
)
async def generate_impact_preview(
    payroll_run_id: uuid.UUID = Path(..., description="ID of the payroll run"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Generate impact preview for a payroll run.
    
    Calculates:
    - Comparison with previous period payroll run
    - Gross/Net/PAYE/Employer cost variances
    - New hires and terminations impact
    - Top 5 variance drivers with breakdown
    - Human-readable summary for stakeholders
    """
    service = PayrollAdvancedService(db)
    
    preview = await service.generate_impact_preview(
        entity_id=entity_id,
        payroll_run_id=payroll_run_id,
    )
    
    if not preview:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to generate impact preview. Ensure the payroll run exists.",
        )
    
    return service.format_impact_preview_response(preview)


# ===========================================
# PAYROLL EXCEPTION ENDPOINTS
# ===========================================

@router.get(
    "/exceptions/{payroll_run_id}/summary",
    response_model=dict,
    summary="Get exception summary for payroll run",
    description="Get summary of all exceptions for a payroll run including counts and approval status.",
)
async def get_exception_summary(
    payroll_run_id: uuid.UUID = Path(..., description="ID of the payroll run"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Get exception summary for a payroll run.
    
    Returns:
    - Total exception count by severity
    - Unacknowledged count
    - Whether payroll can be approved
    - List of blocking exceptions
    """
    service = PayrollAdvancedService(db)
    return await service.get_exception_summary(payroll_run_id)


@router.get(
    "/exceptions/{payroll_run_id}",
    response_model=dict,
    summary="List exceptions for payroll run",
    description="Get all exceptions for a specific payroll run with optional filters.",
)
async def list_exceptions(
    payroll_run_id: uuid.UUID = Path(..., description="ID of the payroll run"),
    severity: Optional[str] = Query(None, description="Filter by severity (critical, warning, info)"),
    acknowledged: Optional[bool] = Query(None, description="Filter by acknowledgement status"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    List all exceptions for a payroll run.
    
    Optional filters:
    - severity: critical, warning, info
    - acknowledged: true/false
    """
    service = PayrollAdvancedService(db)
    
    exceptions = await service.get_exceptions_for_payroll_run(
        payroll_run_id=payroll_run_id,
        severity=severity,
        acknowledged=acknowledged,
    )
    
    return {
        "payroll_run_id": str(payroll_run_id),
        "total": len(exceptions),
        "exceptions": [
            service.format_exception_response(e) for e in exceptions
        ],
    }


@router.get(
    "/exceptions/detail/{exception_id}",
    response_model=dict,
    summary="Get exception details",
    description="Get detailed information about a specific exception.",
)
async def get_exception_detail(
    exception_id: uuid.UUID = Path(..., description="ID of the exception"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get details of a specific exception."""
    service = PayrollAdvancedService(db)
    
    exception = await service.get_exception(exception_id)
    
    if not exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exception {exception_id} not found",
        )
    
    return service.format_exception_response(exception)


@router.post(
    "/exceptions/{payroll_run_id}/validate",
    response_model=dict,
    summary="Run payroll validation",
    description="Execute validation checks on a payroll run and generate exceptions.",
)
async def validate_payroll(
    payroll_run_id: uuid.UUID = Path(..., description="ID of the payroll run"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Run validation checks on a payroll run.
    
    Creates exceptions for:
    - Negative net pay
    - Below minimum wage
    - Missing required fields (TIN, Bank Account, etc.)
    - Duplicate bank accounts
    - Zero PAYE on high income
    """
    service = PayrollAdvancedService(db)
    
    exceptions = await service.validate_payroll_run(payroll_run_id)
    
    return {
        "payroll_run_id": str(payroll_run_id),
        "exceptions_created": len(exceptions),
        "exceptions": [
            service.format_exception_response(e) for e in exceptions
        ],
    }


@router.post(
    "/exceptions/{exception_id}/acknowledge",
    response_model=dict,
    summary="Acknowledge an exception",
    description="Mark an exception as acknowledged with optional note.",
)
async def acknowledge_exception(
    exception_id: uuid.UUID = Path(..., description="ID of the exception"),
    data: AcknowledgeExceptionRequest = None,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Acknowledge an exception.
    
    Acknowledging an exception indicates that the user has reviewed it
    and accepts the risk or has taken appropriate action.
    """
    service = PayrollAdvancedService(db)
    
    exception = await service.acknowledge_exception(
        exception_id=exception_id,
        user_id=current_user.id,
        acknowledgement_note=data.acknowledgement_note if data else None,
    )
    
    if not exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exception {exception_id} not found",
        )
    
    return {
        "message": "Exception acknowledged successfully",
        "exception": service.format_exception_response(exception),
    }


@router.post(
    "/exceptions/bulk-acknowledge",
    response_model=dict,
    summary="Bulk acknowledge exceptions",
    description="Acknowledge multiple exceptions at once.",
)
async def bulk_acknowledge_exceptions(
    exception_ids: List[uuid.UUID],
    acknowledgement_note: Optional[str] = None,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Bulk acknowledge multiple exceptions.
    
    Useful when approving a payroll with multiple warnings.
    """
    service = PayrollAdvancedService(db)
    
    result = await service.bulk_acknowledge_exceptions(
        exception_ids=exception_ids,
        user_id=current_user.id,
        acknowledgement_note=acknowledgement_note,
    )
    
    return result


@router.post(
    "/exceptions/{exception_id}/resolve",
    response_model=dict,
    summary="Resolve an exception",
    description="Mark an exception as resolved after the underlying issue is fixed.",
)
async def resolve_exception(
    exception_id: uuid.UUID = Path(..., description="ID of the exception"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Mark an exception as resolved."""
    service = PayrollAdvancedService(db)
    
    exception = await service.resolve_exception(exception_id)
    
    if not exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exception {exception_id} not found",
        )
    
    return {
        "message": "Exception resolved successfully",
        "exception": service.format_exception_response(exception),
    }


@router.post(
    "/exceptions/{payroll_run_id}/create",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Create manual exception",
    description="Manually create an exception for a payroll run.",
)
async def create_exception(
    payroll_run_id: uuid.UUID = Path(..., description="ID of the payroll run"),
    data: PayrollExceptionBase = Body(...),
    payslip_id: Optional[uuid.UUID] = None,
    employee_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Manually create an exception.
    
    Use this for custom exceptions not covered by automatic validation.
    """
    service = PayrollAdvancedService(db)
    
    exception = await service.create_exception(
        payroll_run_id=payroll_run_id,
        exception_code=data.exception_code,
        severity=data.severity,
        title=data.title,
        description=data.description,
        payslip_id=payslip_id,
        employee_id=employee_id,
        related_field=data.related_field,
        current_value=data.current_value,
        expected_value=data.expected_value,
    )
    
    return {
        "message": "Exception created successfully",
        "exception": service.format_exception_response(exception),
    }


# ===========================================
# DECISION LOG ENDPOINTS
# ===========================================

@router.get(
    "/decision-logs",
    response_model=dict,
    summary="List decision logs",
    description="Get paginated list of decision logs with optional filters.",
)
async def list_decision_logs(
    payroll_run_id: Optional[uuid.UUID] = Query(None, description="Filter by payroll run"),
    employee_id: Optional[uuid.UUID] = Query(None, description="Filter by employee"),
    decision_type: Optional[str] = Query(None, description="Filter by decision type"),
    category: Optional[str] = Query(None, description="Filter by category"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    List decision logs with filters.
    
    Filters:
    - payroll_run_id: Filter by specific payroll run
    - employee_id: Filter by specific employee
    - decision_type: approval, adjustment, exception_override, note
    - category: payroll, salary, deduction, exception, approval, other
    """
    service = PayrollAdvancedService(db)
    
    logs, total = await service.list_decision_logs(
        entity_id=entity_id,
        payroll_run_id=payroll_run_id,
        employee_id=employee_id,
        decision_type=decision_type,
        category=category,
        page=page,
        per_page=per_page,
    )
    
    return {
        "logs": [service.format_decision_log_response(log) for log in logs],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page > 0 else 0,
    }


@router.get(
    "/decision-logs/summary",
    response_model=dict,
    summary="Get decision log summary",
    description="Get summary statistics of decision logs.",
)
async def get_decision_log_summary(
    payroll_run_id: Optional[uuid.UUID] = Query(None, description="Filter by payroll run"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Get summary of decision logs.
    
    Returns:
    - Total count and breakdown by type/category
    - Locked vs unlocked counts
    - Recent logs
    """
    service = PayrollAdvancedService(db)
    return await service.get_decision_log_summary(entity_id, payroll_run_id)


@router.get(
    "/decision-logs/export",
    summary="Export decision logs to CSV",
    description="Export all decision logs to CSV format for audit trails.",
)
async def export_decision_logs_csv(
    payroll_run_id: Optional[uuid.UUID] = Query(None, description="Filter by payroll run"),
    decision_type: Optional[str] = Query(None, description="Filter by decision type"),
    from_date: Optional[date] = Query(None, description="Filter from date"),
    to_date: Optional[date] = Query(None, description="Filter to date"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Export decision logs to CSV format.
    
    Returns a CSV file containing:
    - Decision type, category
    - Title, description
    - Created by (name, role)
    - Timestamp
    - Lock status
    - Content hash for verification
    """
    import csv
    import io
    from fastapi.responses import StreamingResponse
    from datetime import datetime as dt
    
    service = PayrollAdvancedService(db)
    
    # Get logs using existing service method
    logs_response = await service.get_decision_logs(
        entity_id=entity_id,
        payroll_run_id=payroll_run_id,
        decision_type=decision_type,
        page=1,
        per_page=10000  # Export all
    )
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header row
    writer.writerow([
        "ID",
        "Decision Type",
        "Category",
        "Title",
        "Description",
        "Created By",
        "Created By Role",
        "Created At",
        "Is Locked",
        "Content Hash"
    ])
    
    # Data rows
    for log in logs_response.get("logs", []):
        created_at = log.get("created_at", "")
        if hasattr(created_at, 'isoformat'):
            created_at = created_at.isoformat()
        
        writer.writerow([
            str(log.get("id", "")),
            log.get("decision_type", ""),
            log.get("category", ""),
            log.get("title", ""),
            log.get("description", ""),
            log.get("created_by_name", ""),
            log.get("created_by_role", ""),
            created_at,
            "Yes" if log.get("is_locked") else "No",
            log.get("content_hash", "")[:16] + "..." if log.get("content_hash") else ""
        ])
    
    # Reset stream position
    output.seek(0)
    
    # Generate filename with timestamp
    timestamp = dt.now().strftime("%Y%m%d_%H%M%S")
    filename = f"decision_logs_export_{timestamp}.csv"
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.get(
    "/decision-logs/{log_id}",
    response_model=dict,
    summary="Get decision log details",
    description="Get detailed information about a specific decision log.",
)
async def get_decision_log(
    log_id: uuid.UUID = Path(..., description="ID of the decision log"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get details of a specific decision log."""
    service = PayrollAdvancedService(db)
    
    log = await service.get_decision_log(log_id)
    
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision log {log_id} not found",
        )
    
    return service.format_decision_log_response(log)


@router.post(
    "/decision-logs",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Create decision log",
    description="Create a new immutable decision log entry.",
)
async def create_decision_log(
    data: DecisionLogCreate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Create a new decision log entry.
    
    Decision logs are immutable audit records that track:
    - Payroll approvals
    - Salary adjustments
    - Exception overrides
    - General notes and decisions
    
    Once a payroll is completed, its logs are locked and cannot be modified.
    """
    service = PayrollAdvancedService(db)
    
    # Get user info for the log
    user_name = f"{current_user.first_name or ''} {current_user.last_name or ''}".strip() or current_user.email
    user_role = getattr(current_user, 'role', 'user') or 'user'
    
    log = await service.create_decision_log(
        entity_id=entity_id,
        user_id=current_user.id,
        user_name=user_name,
        user_role=user_role,
        decision_type=data.decision_type,
        category=data.category,
        title=data.title,
        description=data.description,
        payroll_run_id=data.payroll_run_id,
        payslip_id=data.payslip_id,
        employee_id=data.employee_id,
        context_data=data.context_data,
    )
    
    return {
        "message": "Decision log created successfully",
        "log": service.format_decision_log_response(log),
    }


@router.post(
    "/decision-logs/{payroll_run_id}/lock",
    response_model=dict,
    summary="Lock decision logs",
    description="Lock all decision logs for a completed payroll run.",
)
async def lock_decision_logs(
    payroll_run_id: uuid.UUID = Path(..., description="ID of the payroll run"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Lock all decision logs for a payroll run.
    
    This should be called when a payroll is finalized to ensure
    all related decision logs become immutable.
    """
    service = PayrollAdvancedService(db)
    
    locked_count = await service.lock_decision_logs_for_payroll(payroll_run_id)
    
    return {
        "message": f"{locked_count} decision log(s) locked successfully",
        "payroll_run_id": str(payroll_run_id),
        "locked_count": locked_count,
    }


@router.get(
    "/decision-logs/{log_id}/verify",
    response_model=dict,
    summary="Verify log integrity",
    description="Verify the integrity of a decision log by checking its hash.",
)
async def verify_decision_log(
    log_id: uuid.UUID = Path(..., description="ID of the decision log"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Verify the integrity of a decision log.
    
    Returns:
    - Hash verification status
    - Lock status
    - Integrity check result
    """
    service = PayrollAdvancedService(db)
    return await service.verify_log_integrity(log_id)


# ===========================================
# YTD LEDGER ENDPOINTS
# ===========================================

@router.get(
    "/ytd-ledger/summary",
    response_model=dict,
    summary="Get YTD ledger summary",
    description="Get summary statistics for YTD payroll ledgers.",
)
async def get_ytd_ledger_summary(
    tax_year: int = Query(..., ge=2020, le=2050, description="Tax year"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Get summary of YTD ledgers for a tax year.
    
    Returns:
    - Total employees with YTD data
    - Aggregate YTD totals (gross, PAYE, pension, net)
    - Average values per employee
    """
    service = PayrollAdvancedService(db)
    return await service.get_ytd_ledger_summary(entity_id, tax_year)


@router.get(
    "/ytd-ledger",
    response_model=dict,
    summary="List YTD ledgers",
    description="Get paginated list of YTD payroll ledgers for all employees.",
)
async def list_ytd_ledgers(
    tax_year: int = Query(..., ge=2020, le=2050, description="Tax year"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """List YTD ledgers with pagination."""
    service = PayrollAdvancedService(db)
    
    ledgers_with_names, total = await service.list_ytd_ledgers(
        entity_id=entity_id,
        tax_year=tax_year,
        page=page,
        per_page=per_page,
    )
    
    return {
        "items": [service.format_ytd_ledger_response(ledger, employee_name=name) for ledger, name in ledgers_with_names],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page > 0 else 0,
        "tax_year": tax_year,
    }


@router.get(
    "/ytd-ledger/{employee_id}",
    response_model=dict,
    summary="Get employee YTD ledger",
    description="Get YTD payroll ledger for a specific employee.",
)
async def get_employee_ytd_ledger(
    employee_id: uuid.UUID = Path(..., description="Employee ID"),
    tax_year: int = Query(..., ge=2020, le=2050, description="Tax year"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get YTD ledger for a specific employee."""
    service = PayrollAdvancedService(db)
    
    ledger = await service.get_ytd_ledger(entity_id, employee_id, tax_year)
    
    if not ledger:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"YTD ledger not found for employee {employee_id} in {tax_year}",
        )
    
    # Fetch employee name
    result = await db.execute(
        select(Employee.first_name, Employee.middle_name, Employee.last_name)
        .where(Employee.id == employee_id)
    )
    emp_row = result.first()
    
    employee_name = None
    if emp_row:
        name_parts = [emp_row.first_name]
        if emp_row.middle_name:
            name_parts.append(emp_row.middle_name)
        name_parts.append(emp_row.last_name)
        employee_name = " ".join(name_parts)
    
    return service.format_ytd_ledger_response(ledger, employee_name=employee_name)


@router.post(
    "/ytd-ledger/update-from-payroll/{payroll_run_id}",
    response_model=dict,
    summary="Update YTD ledgers from payroll",
    description="Update YTD ledgers from a completed payroll run.",
)
async def update_ytd_from_payroll(
    payroll_run_id: uuid.UUID = Path(..., description="Payroll run ID"),
    tax_year: int = Query(..., ge=2020, le=2050, description="Tax year"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Update YTD ledgers from a payroll run."""
    service = PayrollAdvancedService(db)
    
    updated_count = await service.update_ytd_ledger_from_payroll(
        entity_id=entity_id,
        payroll_run_id=payroll_run_id,
        tax_year=tax_year,
    )
    
    return {
        "message": f"Updated {updated_count} YTD ledger(s)",
        "updated_count": updated_count,
        "payroll_run_id": str(payroll_run_id),
        "tax_year": tax_year,
    }


# ===========================================
# OPENING BALANCE ENDPOINTS
# ===========================================

@router.get(
    "/opening-balances",
    response_model=dict,
    summary="List opening balances",
    description="Get paginated list of opening balance imports.",
)
async def list_opening_balances(
    tax_year: int = Query(..., ge=2020, le=2050, description="Tax year"),
    verified_only: bool = Query(False, description="Show only verified balances"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """List opening balances with pagination."""
    service = PayrollAdvancedService(db)
    
    balances, total = await service.list_opening_balances(
        entity_id=entity_id,
        tax_year=tax_year,
        verified_only=verified_only,
        page=page,
        per_page=per_page,
    )
    
    return {
        "items": [service.format_opening_balance_response(b) for b in balances],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page > 0 else 0,
        "tax_year": tax_year,
    }


@router.get(
    "/opening-balances/{employee_id}",
    response_model=dict,
    summary="Get employee opening balance",
    description="Get opening balance for a specific employee.",
)
async def get_employee_opening_balance(
    employee_id: uuid.UUID = Path(..., description="Employee ID"),
    tax_year: int = Query(..., ge=2020, le=2050, description="Tax year"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get opening balance for a specific employee."""
    service = PayrollAdvancedService(db)
    
    balance = await service.get_opening_balance(entity_id, employee_id, tax_year)
    
    if not balance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Opening balance not found for employee {employee_id}",
        )
    
    return service.format_opening_balance_response(balance)


@router.post(
    "/opening-balances",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Create opening balance",
    description="Create an opening balance import record.",
)
async def create_opening_balance(
    data: OpeningBalanceCreate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Create an opening balance for an employee."""
    service = PayrollAdvancedService(db)
    
    balance = await service.create_opening_balance(
        entity_id=entity_id,
        employee_id=data.employee_id,
        tax_year=data.tax_year,
        effective_date=data.effective_date,
        months_covered=data.months_covered,
        prior_ytd_gross=data.prior_ytd_gross,
        prior_ytd_paye=data.prior_ytd_paye,
        prior_ytd_pension_employee=data.prior_ytd_pension_employee,
        prior_ytd_pension_employer=data.prior_ytd_pension_employer,
        prior_ytd_nhf=data.prior_ytd_nhf,
        prior_ytd_net=data.prior_ytd_net,
        source_system=data.source_system,
        notes=data.notes,
    )
    
    return {
        "message": "Opening balance created successfully",
        "balance": service.format_opening_balance_response(balance),
    }


@router.post(
    "/opening-balances/{balance_id}/verify",
    response_model=dict,
    summary="Verify opening balance",
    description="Mark an opening balance as verified.",
)
async def verify_opening_balance(
    balance_id: uuid.UUID = Path(..., description="Opening balance ID"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Verify an opening balance."""
    service = PayrollAdvancedService(db)
    
    balance = await service.verify_opening_balance(balance_id, current_user.id)
    
    if not balance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Opening balance {balance_id} not found",
        )
    
    return {
        "message": "Opening balance verified successfully",
        "balance": service.format_opening_balance_response(balance),
    }


@router.post(
    "/opening-balances/apply/{tax_year}",
    response_model=dict,
    summary="Apply opening balances",
    description="Apply all verified opening balances to YTD ledgers.",
)
async def apply_opening_balances(
    tax_year: int = Path(..., ge=2020, le=2050, description="Tax year"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Apply verified opening balances to YTD ledgers."""
    service = PayrollAdvancedService(db)
    return await service.apply_opening_balances(entity_id, tax_year)


# ===========================================
# PAYSLIP EXPLANATION ENDPOINTS
# ===========================================

@router.get(
    "/payslip-explanation/{payslip_id}",
    response_model=dict,
    summary="Get payslip explanation",
    description="Get human-readable explanation for a payslip.",
)
async def get_payslip_explanation(
    payslip_id: uuid.UUID = Path(..., description="Payslip ID"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get explanation for a payslip."""
    service = PayrollAdvancedService(db)
    
    explanation = await service.get_payslip_explanation(payslip_id)
    
    if not explanation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Explanation not found for payslip {payslip_id}",
        )
    
    return service.format_payslip_explanation_response(explanation)


@router.post(
    "/payslip-explanation/{payslip_id}",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Generate payslip explanation",
    description="Generate human-readable explanation for a payslip.",
)
async def generate_payslip_explanation(
    payslip_id: uuid.UUID = Path(..., description="Payslip ID"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Generate explanation for a payslip."""
    service = PayrollAdvancedService(db)
    
    try:
        explanation = await service.generate_payslip_explanation(payslip_id)
        return {
            "message": "Explanation generated successfully",
            "explanation": service.format_payslip_explanation_response(explanation),
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


# ===========================================
# VARIANCE LOG ENDPOINTS
# ===========================================

@router.get(
    "/variance-logs",
    response_model=dict,
    summary="List variance logs",
    description="Get paginated list of employee variance logs.",
)
async def list_variance_logs(
    employee_id: Optional[uuid.UUID] = Query(None, description="Filter by employee"),
    flagged_only: bool = Query(False, description="Show only flagged variances"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """List variance logs with filters."""
    service = PayrollAdvancedService(db)
    
    logs, total = await service.list_variance_logs(
        entity_id=entity_id,
        employee_id=employee_id,
        flagged_only=flagged_only,
        page=page,
        per_page=per_page,
    )
    
    return {
        "items": [service.format_variance_log_response(l) for l in logs],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page > 0 else 0,
    }


@router.get(
    "/variance-logs/{log_id}",
    response_model=dict,
    summary="Get variance log details",
    description="Get details of a specific variance log.",
)
async def get_variance_log(
    log_id: uuid.UUID = Path(..., description="Variance log ID"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get a specific variance log."""
    service = PayrollAdvancedService(db)
    
    log = await service.get_variance_log(log_id)
    
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Variance log {log_id} not found",
        )
    
    return service.format_variance_log_response(log)


@router.put(
    "/variance-logs/{log_id}/reason",
    response_model=dict,
    summary="Update variance reason",
    description="Update the reason code for a variance log.",
)
async def update_variance_reason(
    log_id: uuid.UUID = Path(..., description="Variance log ID"),
    data: VarianceReasonUpdate = Body(...),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Update variance reason code."""
    service = PayrollAdvancedService(db)
    
    log = await service.update_variance_reason(
        log_id=log_id,
        reason_code=data.reason_code,
        reason_note=data.reason_note,
    )
    
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Variance log {log_id} not found",
        )
    
    return {
        "message": "Variance reason updated successfully",
        "log": service.format_variance_log_response(log),
    }


# ===========================================
# CTC (COST TO COMPANY) ENDPOINTS
# ===========================================

@router.get(
    "/ctc/trend",
    response_model=dict,
    summary="Get CTC trend",
    description="Get Cost-to-Company trend over time.",
)
async def get_ctc_trend(
    months: int = Query(12, ge=1, le=24, description="Number of months"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get CTC trend over past N months."""
    service = PayrollAdvancedService(db)
    
    trend = await service.get_ctc_trend(entity_id, months)
    
    return {
        "entity_id": str(entity_id),
        "periods": trend,
        "months_requested": months,
    }


@router.get(
    "/ctc/snapshots",
    response_model=dict,
    summary="List CTC snapshots",
    description="Get paginated list of CTC snapshots.",
)
async def list_ctc_snapshots(
    year: Optional[int] = Query(None, ge=2020, le=2050, description="Filter by year"),
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=24),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """List CTC snapshots with pagination."""
    service = PayrollAdvancedService(db)
    
    snapshots, total = await service.list_ctc_snapshots(
        entity_id=entity_id,
        year=year,
        page=page,
        per_page=per_page,
    )
    
    return {
        "items": [service.format_ctc_snapshot_response(s) for s in snapshots],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page > 0 else 0,
    }


@router.get(
    "/ctc/snapshots/{month}/{year}",
    response_model=dict,
    summary="Get CTC snapshot for period",
    description="Get CTC snapshot for a specific month/year.",
)
async def get_ctc_snapshot(
    month: int = Path(..., ge=1, le=12),
    year: int = Path(..., ge=2020, le=2050),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get CTC snapshot for a period."""
    service = PayrollAdvancedService(db)
    
    snapshot = await service.get_ctc_snapshot(entity_id, month, year)
    
    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"CTC snapshot not found for {month}/{year}",
        )
    
    return service.format_ctc_snapshot_response(snapshot)


@router.post(
    "/ctc/snapshots",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Generate CTC snapshot",
    description="Generate or refresh CTC snapshot for a period.",
)
async def generate_ctc_snapshot(
    month: int = Query(..., ge=1, le=12, description="Snapshot month"),
    year: int = Query(..., ge=2020, le=2050, description="Snapshot year"),
    monthly_budget: Optional[float] = Query(None, description="Monthly budget for comparison"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Generate CTC snapshot for a period."""
    service = PayrollAdvancedService(db)
    from decimal import Decimal
    
    snapshot = await service.generate_ctc_snapshot(
        entity_id=entity_id,
        snapshot_month=month,
        snapshot_year=year,
        monthly_budget=Decimal(str(monthly_budget)) if monthly_budget else None,
    )
    
    return {
        "message": "CTC snapshot generated successfully",
        "snapshot": service.format_ctc_snapshot_response(snapshot),
    }


# ===========================================
# WHAT-IF SIMULATION ENDPOINTS
# ===========================================

@router.get(
    "/simulations",
    response_model=dict,
    summary="List simulations",
    description="Get paginated list of What-If simulations.",
)
async def list_simulations(
    saved_only: bool = Query(False, description="Show only saved simulations"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """List simulations with pagination."""
    service = PayrollAdvancedService(db)
    
    simulations, total = await service.list_simulations(
        entity_id=entity_id,
        saved_only=saved_only,
        page=page,
        per_page=per_page,
    )
    
    return {
        "items": [service.format_simulation_response(s) for s in simulations],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page > 0 else 0,
    }


@router.get(
    "/simulations/{simulation_id}",
    response_model=dict,
    summary="Get simulation details",
    description="Get details of a specific simulation.",
)
async def get_simulation(
    simulation_id: uuid.UUID = Path(..., description="Simulation ID"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get simulation details."""
    service = PayrollAdvancedService(db)
    
    simulation = await service.get_simulation(simulation_id)
    
    if not simulation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Simulation {simulation_id} not found",
        )
    
    return service.format_simulation_response(simulation)


@router.post(
    "/simulations/salary-increase",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Run salary increase simulation",
    description="Run a What-If simulation for salary increases.",
)
async def run_salary_increase_simulation(
    data: WhatIfSimulationRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Run salary increase simulation."""
    service = PayrollAdvancedService(db)
    
    if not data.salary_increase:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="salary_increase parameters required",
        )
    
    simulation = await service.run_salary_increase_simulation(
        entity_id=entity_id,
        user_id=current_user.id,
        simulation_name=data.simulation_name,
        increase_type=data.salary_increase.increase_type,
        increase_value=data.salary_increase.increase_value,
        apply_to=data.salary_increase.apply_to,
        department=data.salary_increase.department,
        employee_ids=data.salary_increase.employee_ids,
        description=data.description,
        save_simulation=data.save_simulation,
    )
    
    return {
        "message": "Simulation completed successfully",
        "simulation": service.format_simulation_response(simulation),
    }


@router.delete(
    "/simulations/{simulation_id}",
    response_model=dict,
    summary="Delete simulation",
    description="Delete a simulation.",
)
async def delete_simulation(
    simulation_id: uuid.UUID = Path(..., description="Simulation ID"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Delete a simulation."""
    service = PayrollAdvancedService(db)
    
    deleted = await service.delete_simulation(simulation_id)
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Simulation {simulation_id} not found",
        )
    
    return {"message": "Simulation deleted successfully"}


# ===========================================
# GHOST WORKER DETECTION ENDPOINTS
# ===========================================

@router.get(
    "/ghost-worker/detections",
    response_model=dict,
    summary="List ghost worker detections",
    description="Get paginated list of ghost worker detections.",
)
async def list_ghost_detections(
    unresolved_only: bool = Query(False, description="Show only unresolved detections"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """List ghost worker detections."""
    service = PayrollAdvancedService(db)
    
    detections, total = await service.list_ghost_detections(
        entity_id=entity_id,
        unresolved_only=unresolved_only,
        page=page,
        per_page=per_page,
    )
    
    return {
        "items": [service.format_ghost_detection_response(d) for d in detections],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page > 0 else 0,
    }


@router.get(
    "/ghost-worker/detections/{detection_id}",
    response_model=dict,
    summary="Get detection details",
    description="Get details of a specific ghost worker detection.",
)
async def get_ghost_detection(
    detection_id: uuid.UUID = Path(..., description="Detection ID"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Get ghost worker detection details."""
    service = PayrollAdvancedService(db)
    
    detection = await service.get_ghost_detection(detection_id)
    
    if not detection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Detection {detection_id} not found",
        )
    
    return service.format_ghost_detection_response(detection)


@router.post(
    "/ghost-worker/scan",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Run ghost worker scan",
    description="Scan for duplicate employees (ghost workers).",
)
async def run_ghost_worker_scan(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """
    Run ghost worker detection scan.
    
    Scans for:
    - Duplicate BVNs
    - Duplicate bank accounts
    - Duplicate NINs
    """
    service = PayrollAdvancedService(db)
    return await service.run_ghost_worker_scan(entity_id)


@router.post(
    "/ghost-worker/detections/{detection_id}/resolve",
    response_model=dict,
    summary="Resolve detection",
    description="Mark a ghost worker detection as resolved.",
)
async def resolve_ghost_detection(
    detection_id: uuid.UUID = Path(..., description="Detection ID"),
    data: ResolveGhostWorkerRequest = Body(...),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_active_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
):
    """Resolve a ghost worker detection."""
    service = PayrollAdvancedService(db)
    
    detection = await service.resolve_ghost_detection(
        detection_id=detection_id,
        user_id=current_user.id,
        resolution_note=data.resolution_note,
    )
    
    if not detection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Detection {detection_id} not found",
        )
    
    # Audit logging for ghost worker resolution
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="ghost_worker_detection",
        entity_id=str(detection_id),
        action=AuditAction.UPDATE,
        user_id=current_user.id,
        new_values={
            "resolution_note": data.resolution_note,
            "resolved_by": str(current_user.id),
            "status": "resolved",
        }
    )
    
    return {
        "message": "Detection resolved successfully",
        "detection": service.format_ghost_detection_response(detection),
    }
