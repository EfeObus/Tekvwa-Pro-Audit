"""
Tekvwa Pro Audit - Financial Report Export Router

API endpoints for exporting financial reports in multiple formats:
- Balance Sheet (PDF, Excel, CSV)
- Income Statement (PDF, Excel, CSV)
- Trial Balance (PDF, Excel, CSV)
- General Ledger (PDF, Excel, CSV)
- Cash Flow Statement

Supports Nigerian IFRS compliant formatting with company branding.
"""

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import io

from app.database import get_db
from app.dependencies import get_current_user, get_current_entity_id
from app.models.user import User
from app.models.entity import BusinessEntity
from app.services.report_export_service import (
    FinancialReportExportService, ReportFormat, ReportType
)


router = APIRouter(prefix="/api/v1/reports/export", tags=["Report Export"])


# =============================================================================
# SCHEMAS
# =============================================================================

class ExportBalanceSheetRequest(BaseModel):
    """Request to export balance sheet"""
    as_of_date: date
    format: ReportFormat = ReportFormat.PDF
    comparative_date: Optional[date] = None


class ExportIncomeStatementRequest(BaseModel):
    """Request to export income statement"""
    start_date: date
    end_date: date
    format: ReportFormat = ReportFormat.PDF
    comparative_start: Optional[date] = None
    comparative_end: Optional[date] = None


class ExportTrialBalanceRequest(BaseModel):
    """Request to export trial balance"""
    as_of_date: date
    format: ReportFormat = ReportFormat.PDF
    include_zero_balances: bool = False


class ExportGeneralLedgerRequest(BaseModel):
    """Request to export general ledger"""
    start_date: date
    end_date: date
    format: ReportFormat = ReportFormat.PDF
    account_id: Optional[uuid.UUID] = None


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def resolve_entity_id(
    db: AsyncSession,
    entity_id: Optional[uuid.UUID],
    user: User
) -> uuid.UUID:
    """Resolve entity ID from parameter or user context."""
    if entity_id:
        return entity_id
    
    if user.organization_id:
        result = await db.execute(
            select(BusinessEntity).where(
                BusinessEntity.organization_id == user.organization_id
            ).limit(1)
        )
        entity = result.scalar_one_or_none()
        if entity:
            return entity.id
    
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Entity ID is required"
    )


def get_content_type(format: ReportFormat) -> str:
    """Get content type for export format."""
    content_types = {
        ReportFormat.PDF: "application/pdf",
        ReportFormat.EXCEL: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ReportFormat.CSV: "text/csv"
    }
    return content_types.get(format, "application/octet-stream")


# =============================================================================
# ENDPOINTS - BALANCE SHEET
# =============================================================================

@router.post(
    "/balance-sheet",
    summary="Export Balance Sheet",
    description="Export Balance Sheet report in PDF, Excel, or CSV format"
)
async def export_balance_sheet(
    request: ExportBalanceSheetRequest,
    entity_id: Optional[uuid.UUID] = Query(None, description="Entity ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export Balance Sheet report."""
    try:
        resolved_entity_id = await resolve_entity_id(db, entity_id, current_user)
        service = FinancialReportExportService(db)
        
        content, filename = await service.export_balance_sheet(
            entity_id=resolved_entity_id,
            as_of_date=request.as_of_date,
            format=request.format,
            comparative_date=request.comparative_date
        )
        
        return StreamingResponse(
            io.BytesIO(content),
            media_type=get_content_type(request.format),
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/balance-sheet",
    summary="Export Balance Sheet (GET)",
    description="Export Balance Sheet report via GET request"
)
async def export_balance_sheet_get(
    as_of_date: date = Query(..., description="Report date"),
    format: ReportFormat = Query(ReportFormat.PDF, description="Export format"),
    comparative_date: Optional[date] = Query(None, description="Comparative date"),
    entity_id: Optional[uuid.UUID] = Query(None, description="Entity ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export Balance Sheet report via GET."""
    try:
        resolved_entity_id = await resolve_entity_id(db, entity_id, current_user)
        service = FinancialReportExportService(db)
        
        content, filename = await service.export_balance_sheet(
            entity_id=resolved_entity_id,
            as_of_date=as_of_date,
            format=format,
            comparative_date=comparative_date
        )
        
        return StreamingResponse(
            io.BytesIO(content),
            media_type=get_content_type(format),
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# =============================================================================
# ENDPOINTS - INCOME STATEMENT
# =============================================================================

@router.post(
    "/income-statement",
    summary="Export Income Statement",
    description="Export Income Statement (P&L) report in PDF, Excel, or CSV format"
)
async def export_income_statement(
    request: ExportIncomeStatementRequest,
    entity_id: Optional[uuid.UUID] = Query(None, description="Entity ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export Income Statement report."""
    try:
        resolved_entity_id = await resolve_entity_id(db, entity_id, current_user)
        service = FinancialReportExportService(db)
        
        content, filename = await service.export_income_statement(
            entity_id=resolved_entity_id,
            start_date=request.start_date,
            end_date=request.end_date,
            format=request.format,
            comparative_start=request.comparative_start,
            comparative_end=request.comparative_end
        )
        
        return StreamingResponse(
            io.BytesIO(content),
            media_type=get_content_type(request.format),
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/income-statement",
    summary="Export Income Statement (GET)",
    description="Export Income Statement report via GET request"
)
async def export_income_statement_get(
    start_date: date = Query(..., description="Period start date"),
    end_date: date = Query(..., description="Period end date"),
    format: ReportFormat = Query(ReportFormat.PDF, description="Export format"),
    comparative_start: Optional[date] = Query(None, description="Comparative period start"),
    comparative_end: Optional[date] = Query(None, description="Comparative period end"),
    entity_id: Optional[uuid.UUID] = Query(None, description="Entity ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export Income Statement report via GET."""
    try:
        resolved_entity_id = await resolve_entity_id(db, entity_id, current_user)
        service = FinancialReportExportService(db)
        
        content, filename = await service.export_income_statement(
            entity_id=resolved_entity_id,
            start_date=start_date,
            end_date=end_date,
            format=format,
            comparative_start=comparative_start,
            comparative_end=comparative_end
        )
        
        return StreamingResponse(
            io.BytesIO(content),
            media_type=get_content_type(format),
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# =============================================================================
# ENDPOINTS - TRIAL BALANCE
# =============================================================================

@router.post(
    "/trial-balance",
    summary="Export Trial Balance",
    description="Export Trial Balance report in PDF, Excel, or CSV format"
)
async def export_trial_balance(
    request: ExportTrialBalanceRequest,
    entity_id: Optional[uuid.UUID] = Query(None, description="Entity ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export Trial Balance report."""
    try:
        resolved_entity_id = await resolve_entity_id(db, entity_id, current_user)
        service = FinancialReportExportService(db)
        
        content, filename = await service.export_trial_balance(
            entity_id=resolved_entity_id,
            as_of_date=request.as_of_date,
            format=request.format,
            include_zero_balances=request.include_zero_balances
        )
        
        return StreamingResponse(
            io.BytesIO(content),
            media_type=get_content_type(request.format),
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/trial-balance",
    summary="Export Trial Balance (GET)",
    description="Export Trial Balance report via GET request"
)
async def export_trial_balance_get(
    as_of_date: date = Query(..., description="Report date"),
    format: ReportFormat = Query(ReportFormat.PDF, description="Export format"),
    include_zero_balances: bool = Query(False, description="Include zero balance accounts"),
    entity_id: Optional[uuid.UUID] = Query(None, description="Entity ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export Trial Balance report via GET."""
    try:
        resolved_entity_id = await resolve_entity_id(db, entity_id, current_user)
        service = FinancialReportExportService(db)
        
        content, filename = await service.export_trial_balance(
            entity_id=resolved_entity_id,
            as_of_date=as_of_date,
            format=format,
            include_zero_balances=include_zero_balances
        )
        
        return StreamingResponse(
            io.BytesIO(content),
            media_type=get_content_type(format),
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# =============================================================================
# ENDPOINTS - GENERAL LEDGER
# =============================================================================

@router.post(
    "/general-ledger",
    summary="Export General Ledger",
    description="Export General Ledger report in PDF, Excel, or CSV format"
)
async def export_general_ledger(
    request: ExportGeneralLedgerRequest,
    entity_id: Optional[uuid.UUID] = Query(None, description="Entity ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export General Ledger report."""
    try:
        resolved_entity_id = await resolve_entity_id(db, entity_id, current_user)
        service = FinancialReportExportService(db)
        
        content, filename = await service.export_general_ledger(
            entity_id=resolved_entity_id,
            start_date=request.start_date,
            end_date=request.end_date,
            account_id=request.account_id,
            format=request.format
        )
        
        return StreamingResponse(
            io.BytesIO(content),
            media_type=get_content_type(request.format),
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/general-ledger",
    summary="Export General Ledger (GET)",
    description="Export General Ledger report via GET request"
)
async def export_general_ledger_get(
    start_date: date = Query(..., description="Period start date"),
    end_date: date = Query(..., description="Period end date"),
    format: ReportFormat = Query(ReportFormat.PDF, description="Export format"),
    account_id: Optional[uuid.UUID] = Query(None, description="Filter by account"),
    entity_id: Optional[uuid.UUID] = Query(None, description="Entity ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export General Ledger report via GET."""
    try:
        resolved_entity_id = await resolve_entity_id(db, entity_id, current_user)
        service = FinancialReportExportService(db)
        
        content, filename = await service.export_general_ledger(
            entity_id=resolved_entity_id,
            start_date=start_date,
            end_date=end_date,
            account_id=account_id,
            format=format
        )
        
        return StreamingResponse(
            io.BytesIO(content),
            media_type=get_content_type(format),
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# =============================================================================
# ENDPOINTS - REPORT INFO
# =============================================================================

@router.get(
    "/formats",
    summary="Get Available Export Formats",
    description="Get list of available export formats"
)
async def get_export_formats():
    """Get available export formats."""
    return {
        "formats": [
            {
                "code": ReportFormat.PDF.value,
                "name": "PDF Document",
                "description": "Portable Document Format - best for printing and sharing",
                "content_type": "application/pdf",
                "extension": ".pdf"
            },
            {
                "code": ReportFormat.EXCEL.value,
                "name": "Microsoft Excel",
                "description": "Excel Workbook - best for further analysis and editing",
                "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "extension": ".xlsx"
            },
            {
                "code": ReportFormat.CSV.value,
                "name": "CSV (Comma Separated)",
                "description": "Plain text format - compatible with any spreadsheet application",
                "content_type": "text/csv",
                "extension": ".csv"
            }
        ]
    }


@router.get(
    "/report-types",
    summary="Get Available Report Types",
    description="Get list of available financial report types"
)
async def get_report_types():
    """Get available report types."""
    return {
        "report_types": [
            {
                "code": ReportType.BALANCE_SHEET.value,
                "name": "Balance Sheet",
                "description": "Statement of Financial Position - shows assets, liabilities, and equity",
                "endpoints": ["/balance-sheet"],
                "parameters": {
                    "required": ["as_of_date"],
                    "optional": ["comparative_date", "format"]
                }
            },
            {
                "code": ReportType.INCOME_STATEMENT.value,
                "name": "Income Statement",
                "description": "Statement of Profit or Loss - shows revenue, expenses, and net income",
                "endpoints": ["/income-statement"],
                "parameters": {
                    "required": ["start_date", "end_date"],
                    "optional": ["comparative_start", "comparative_end", "format"]
                }
            },
            {
                "code": ReportType.TRIAL_BALANCE.value,
                "name": "Trial Balance",
                "description": "List of all account balances to verify debits equal credits",
                "endpoints": ["/trial-balance"],
                "parameters": {
                    "required": ["as_of_date"],
                    "optional": ["include_zero_balances", "format"]
                }
            },
            {
                "code": ReportType.GENERAL_LEDGER.value,
                "name": "General Ledger",
                "description": "Detailed transaction history for each account",
                "endpoints": ["/general-ledger"],
                "parameters": {
                    "required": ["start_date", "end_date"],
                    "optional": ["account_id", "format"]
                }
            }
        ]
    }
