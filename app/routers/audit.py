"""
Tekvwa Pro Audit - Audit Trail Router

API endpoints for audit logs, compliance tracking, and Audit Vault.

NTAA 2025 Compliant:
- 5-year digital record keeping
- Immutable audit trail
- Export for regulatory audits
- Integrity verification
"""

import uuid
from datetime import date
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.services.audit_service import AuditService
from app.services.audit_vault_service import AuditVaultService
from app.models.user import User
from app.models.audit_consolidated import AuditAction

router = APIRouter(tags=["Audit Trail"])


@router.get("/{entity_id}/audit/logs")
async def get_audit_logs(
    entity_id: uuid.UUID,
    target_entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    target_entity_id: Optional[str] = Query(None, description="Filter by entity ID"),
    action: Optional[str] = Query(None, description="Filter by action type"),
    user_id: Optional[uuid.UUID] = Query(None, description="Filter by user"),
    start_date: Optional[date] = Query(None, description="Filter from date"),
    end_date: Optional[date] = Query(None, description="Filter to date"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get audit logs with optional filtering.
    
    Supports filtering by:
    - Entity type (transaction, invoice, etc.)
    - Specific entity ID
    - Action type (create, update, delete, etc.)
    - User who performed the action
    - Date range
    """
    action_enum = None
    if action:
        try:
            action_enum = AuditAction(action)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid action. Must be one of: {[a.value for a in AuditAction]}",
            )
    
    service = AuditService(db)
    logs, total = await service.get_audit_logs(
        entity_id=entity_id,
        target_entity_type=target_entity_type,
        target_entity_id=target_entity_id,
        action=action_enum,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=limit,
        return_total=True,
    )
    
    return {
        "items": [
            {
                "id": str(log.id),
                "timestamp": log.created_at.isoformat(),
                "target_entity_type": log.target_entity_type,
                "target_entity_id": str(log.target_entity_id) if log.target_entity_id else None,
                "action": log.action if isinstance(log.action, str) else log.action.value,
                "user_id": str(log.user_id) if log.user_id else None,
                "changes": log.changes,
                "ip_address": log.ip_address,
            }
            for log in logs
        ],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/{entity_id}/audit/history/{target_entity_type}/{target_entity_id}")
async def get_entity_history(
    entity_id: uuid.UUID,
    target_entity_type: str,
    target_entity_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get complete history of changes for a specific entity.
    
    Returns chronological list of all changes made to the entity,
    useful for compliance audits and debugging.
    """
    service = AuditService(db)
    history = await service.get_entity_history(
        entity_id=entity_id,
        target_entity_type=target_entity_type,
        target_entity_id=target_entity_id,
    )
    
    return {
        "entity_type": target_entity_type,
        "entity_id": target_entity_id,
        "history": history,
    }


@router.get("/{entity_id}/audit/user-activity/{user_id}")
async def get_user_activity(
    entity_id: uuid.UUID,
    user_id: uuid.UUID,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get activity summary for a specific user.
    
    Shows breakdown of actions performed by entity type.
    """
    service = AuditService(db)
    activity = await service.get_user_activity(
        entity_id=entity_id,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )
    
    return activity


@router.get("/{entity_id}/audit/summary")
async def get_audit_summary(
    entity_id: uuid.UUID,
    start_date: date = Query(..., description="Report period start"),
    end_date: date = Query(..., description="Report period end"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate audit summary report.
    
    Shows:
    - Total events
    - Breakdown by action type
    - Breakdown by entity type
    - Breakdown by user
    """
    service = AuditService(db)
    summary = await service.get_audit_summary(
        entity_id=entity_id,
        start_date=start_date,
        end_date=end_date,
    )
    
    return summary


@router.get("/{entity_id}/audit/actions")
async def list_audit_actions(entity_id: uuid.UUID):
    """List all available audit action types."""
    return {
        "actions": [
            {
                "value": action.value,
                "description": _get_action_description(action),
            }
            for action in AuditAction
        ]
    }


def _get_action_description(action: AuditAction) -> str:
    """Get human-readable description for audit action."""
    descriptions = {
        AuditAction.CREATE: "Record created",
        AuditAction.UPDATE: "Record updated",
        AuditAction.DELETE: "Record deleted",
        AuditAction.VIEW: "Record viewed",
        AuditAction.EXPORT: "Data exported",
        AuditAction.LOGIN: "User logged in",
        AuditAction.LOGOUT: "User logged out",
        AuditAction.LOGIN_FAILED: "Login attempt failed",
        AuditAction.NRS_SUBMIT: "E-invoice submitted to NRS",
        AuditAction.NRS_CANCEL: "E-invoice cancelled in NRS",
        AuditAction.UPLOAD: "Document uploaded",
        AuditAction.DOWNLOAD: "Document downloaded",
    }
    return descriptions.get(action, action.value)


# ===========================================
# AUDIT VAULT ENDPOINTS (NTAA 2025 Compliant)
# ===========================================

@router.get("/{entity_id}/audit/vault/info")
async def get_vault_info(entity_id: uuid.UUID):
    """
    Get Audit Vault information and capabilities.
    
    Returns information about NTAA 2025 compliant record keeping features.
    """
    return {
        "name": "Tekvwa Pro Audit Audit Vault",
        "version": "1.0.0",
        "compliance_standard": "NTAA 2025",
        "features": [
            "5-year minimum retention policy",
            "Immutable audit trail",
            "Cryptographic integrity verification",
            "Fiscal year organization",
            "NRS submission tracking",
            "Regulatory export generation",
            "Automatic archival policies",
        ],
        "retention_policy": {
            "retention_years": 5,
            "archive_after_years": 2,
            "legal_hold_support": True,
        },
        "document_types": [
            "invoice", "receipt", "transaction", "tax_filing",
            "nrs_submission", "credit_note", "fixed_asset",
            "payroll", "bank_statement", "supporting_doc",
        ],
    }


@router.get("/{entity_id}/audit/vault/statistics")
async def get_vault_statistics(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get comprehensive vault statistics.
    
    Returns:
    - Total record counts
    - Records by retention status (active, archived, pending purge)
    - Records by fiscal year
    - Records by document type
    - Storage estimates
    """
    service = AuditVaultService(db)
    stats = await service.get_vault_statistics(entity_id)
    
    return {
        "entity_id": str(entity_id),
        "total_records": stats.total_records,
        "active_records": stats.active_records,
        "archived_records": stats.archived_records,
        "pending_purge": stats.pending_purge,
        "legal_hold": stats.legal_hold,
        "oldest_record": stats.oldest_record.isoformat() if stats.oldest_record else None,
        "by_fiscal_year": stats.by_fiscal_year,
        "by_document_type": stats.by_document_type,
        "storage_size_mb": stats.storage_size_estimate_mb,
    }


@router.get("/{entity_id}/audit/vault/records")
async def get_vault_records(
    entity_id: uuid.UUID,
    fiscal_year: Optional[int] = Query(None, description="Filter by fiscal year"),
    document_type: Optional[str] = Query(None, description="Filter by document type"),
    retention_status: Optional[str] = Query(None, description="Filter by status: active, archived, pending_purge"),
    search: Optional[str] = Query(None, description="Search in description, document type, or reference ID"),
    start_date: Optional[date] = Query(None, description="Filter from date"),
    end_date: Optional[date] = Query(None, description="Filter to date"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Query vault records with filtering.
    
    Supports filtering by:
    - Fiscal year
    - Document type
    - Retention status
    - Date range
    - Search term (searches description, document type, reference ID)
    """
    service = AuditVaultService(db)
    records, total = await service.get_vault_records(
        entity_id=entity_id,
        fiscal_year=fiscal_year,
        document_type=document_type,
        retention_status=retention_status,
        search_term=search,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=limit,
    )
    
    return {
        "items": records,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/{entity_id}/audit/vault/records/{record_id}")
async def get_vault_record_detail(
    entity_id: uuid.UUID,
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get detailed view of a single vault record.
    
    Includes:
    - Full record data with old/new values
    - Integrity hash
    - NRS submission data
    - Device fingerprint (for compliance verification)
    """
    service = AuditVaultService(db)
    record = await service.get_record_detail(entity_id, record_id)
    
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Record not found in vault",
        )
    
    return record


@router.get("/{entity_id}/audit/vault/retention-policy")
async def get_retention_policy(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get current retention policy configuration.
    
    Returns NTAA 2025 compliance settings.
    """
    service = AuditVaultService(db)
    return await service.get_retention_policy()


@router.get("/{entity_id}/audit/vault/retention-timeline")
async def get_retention_timeline(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get retention timeline showing records approaching expiry.
    
    Shows record counts expiring in each of the next 5 years.
    """
    service = AuditVaultService(db)
    timeline = await service.get_retention_timeline(entity_id)
    
    return {
        "entity_id": str(entity_id),
        "retention_years": 5,
        "timeline": timeline,
    }


@router.get("/{entity_id}/audit/vault/export/{fiscal_year}")
async def export_vault_records(
    entity_id: uuid.UUID,
    fiscal_year: int,
    document_types: Optional[str] = Query(None, description="Comma-separated document types"),
    include_full_data: bool = Query(False, description="Include old/new values and device info"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate export package for regulatory audit.
    
    Creates structured data suitable for FIRS/NRS audit submissions.
    Includes:
    - Export metadata with integrity hash
    - NRS submissions list
    - Full record export
    """
    types_list = document_types.split(",") if document_types else None
    
    service = AuditVaultService(db)
    export_data = await service.generate_audit_export(
        entity_id=entity_id,
        fiscal_year=fiscal_year,
        document_types=types_list,
        include_full_data=include_full_data,
    )
    
    return export_data


@router.get("/{entity_id}/audit/vault/compliance-report/{fiscal_year}")
async def get_compliance_report(
    entity_id: uuid.UUID,
    fiscal_year: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate compliance report for a fiscal year.
    
    Shows:
    - Total records and NRS submissions
    - Activity by action type
    - Monthly activity breakdown
    - Compliance status indicators
    """
    service = AuditVaultService(db)
    report = await service.get_compliance_report(entity_id, fiscal_year)
    
    return report


@router.post("/{entity_id}/audit/vault/verify/{record_id}")
async def verify_record_integrity(
    entity_id: uuid.UUID,
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Verify the integrity of a single record.
    
    Computes cryptographic hash and confirms record integrity.
    """
    service = AuditVaultService(db)
    result = await service.verify_record_integrity(entity_id, record_id)
    
    if not result.get("verified") and result.get("error"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["error"],
        )
    
    return result


@router.post("/{entity_id}/audit/vault/verify-year/{fiscal_year}")
async def verify_fiscal_year_integrity(
    entity_id: uuid.UUID,
    fiscal_year: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Verify integrity of all records for a fiscal year.
    
    Computes chain hash of all records for the year to verify
    no records have been tampered with or removed.
    """
    service = AuditVaultService(db)
    result = await service.verify_fiscal_year_integrity(entity_id, fiscal_year)
    
    return result


@router.get("/{entity_id}/audit/vault/fiscal-years")
async def get_available_fiscal_years(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get list of fiscal years with records in the vault.
    
    Returns years with record counts for quick navigation.
    """
    service = AuditVaultService(db)
    stats = await service.get_vault_statistics(entity_id)
    
    # Sort by year descending
    years = sorted(stats.by_fiscal_year.items(), key=lambda x: x[0], reverse=True)
    
    return {
        "entity_id": str(entity_id),
        "fiscal_years": [
            {"year": year, "record_count": count}
            for year, count in years
        ],
    }


@router.post("/{entity_id}/audit/vault/legal-hold/{record_id}")
async def set_legal_hold(
    entity_id: uuid.UUID,
    record_id: uuid.UUID,
    enable: bool = Query(True, description="Enable or disable legal hold"),
    reason: Optional[str] = Query(None, description="Reason for legal hold"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Set or remove legal hold on a vault record.
    
    Records under legal hold:
    - Cannot be automatically purged
    - Have extended retention periods
    - Are flagged for regulatory review
    """
    service = AuditVaultService(db)
    result = await service.set_legal_hold(
        entity_id=entity_id,
        record_id=record_id,
        enable=enable,
        reason=reason,
    )
    
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result.get("error", "Failed to set legal hold"),
        )
    
    return result
