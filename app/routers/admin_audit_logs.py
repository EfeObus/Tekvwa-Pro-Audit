"""
Tekvwa Pro Audit - Admin Global Audit Log API Router

Platform-wide audit log viewing, searching, and analytics for Super Admin users.
Provides cross-tenant visibility into all platform activity.

Endpoints:
- GET /api/v1/admin/audit-logs - Search audit logs across all tenants
- GET /api/v1/admin/audit-logs/stats - Get platform audit statistics
- GET /api/v1/admin/audit-logs/{log_id} - Get specific log entry details
- GET /api/v1/admin/audit-logs/user/{user_id}/activity - Get user activity summary
- GET /api/v1/admin/audit-logs/filters/actions - Get available action types
- GET /api/v1/admin/audit-logs/filters/entity-types - Get available entity types
"""

import logging
from datetime import date, datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import require_super_admin
from app.models.user import User
from app.services.admin_audit_log_service import AdminAuditLogService, AuditLogSeverity

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/audit-logs",
    tags=["Admin Audit Logs"],
    responses={404: {"description": "Not found"}},
)

templates = Jinja2Templates(directory="templates")


# ==================== Response Schemas ====================

class AuditLogEntry(BaseModel):
    """Schema for audit log entry in list response."""
    id: str
    organization_id: Optional[str]
    organization_name: str
    user_id: Optional[str]
    user_email: Optional[str]
    action: str
    severity: str
    target_entity_type: Optional[str]
    target_entity_id: Optional[str]
    ip_address: Optional[str]
    created_at: Optional[str]


class AuditLogListResponse(BaseModel):
    """Schema for paginated audit log list response."""
    success: bool = True
    items: List[dict]
    total: int
    page: int
    page_size: int
    total_pages: int


class AuditLogDetailResponse(BaseModel):
    """Schema for detailed audit log entry."""
    success: bool = True
    log: dict


class AuditStatisticsResponse(BaseModel):
    """Schema for audit statistics response."""
    success: bool = True
    statistics: dict


class UserActivityResponse(BaseModel):
    """Schema for user activity summary response."""
    success: bool = True
    activity: dict


class FilterOptionsResponse(BaseModel):
    """Schema for filter options response."""
    success: bool = True
    options: List[str]


# ==================== API Endpoints ====================

@router.get("")
async def search_audit_logs(
    organization_id: Optional[UUID] = Query(None, description="Filter by organization ID"),
    user_id: Optional[UUID] = Query(None, description="Filter by user ID"),
    user_email: Optional[str] = Query(None, description="Filter by user email (partial match)"),
    action: Optional[str] = Query(None, description="Filter by exact action"),
    action_contains: Optional[str] = Query(None, description="Filter by action containing string"),
    target_entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    severity: Optional[str] = Query(None, description="Filter by severity (critical, high, medium, low, info)"),
    start_date: Optional[date] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="Filter to date (YYYY-MM-DD)"),
    ip_address: Optional[str] = Query(None, description="Filter by IP address"),
    search: Optional[str] = Query(None, description="Full-text search query"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order (asc/desc)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Results per page"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
) -> AuditLogListResponse:
    """
    Search audit logs across all organizations.
    
    Super Admin only endpoint for platform-wide audit log viewing.
    
    Supports:
    - Multiple filters (organization, user, action, entity type, severity, date range)
    - Full-text search
    - Pagination and sorting
    
    Severity levels:
    - critical: Security breaches, unauthorized access
    - high: Data deletions, data exports, emergency actions
    - medium: Data modifications, configuration changes
    - low: Read operations, searches
    - info: Login/logout, general activity
    """
    try:
        # Parse severity if provided
        severity_enum = None
        if severity:
            try:
                severity_enum = AuditLogSeverity(severity.lower())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid severity. Must be one of: {[s.value for s in AuditLogSeverity]}"
                )
        
        service = AdminAuditLogService(db)
        logs, total = await service.get_global_audit_logs(
            organization_id=organization_id,
            user_id=user_id,
            user_email=user_email,
            action=action,
            action_contains=action_contains,
            target_entity_type=target_entity_type,
            severity=severity_enum,
            start_date=start_date,
            end_date=end_date,
            ip_address=ip_address,
            search_query=search,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            page_size=page_size,
        )
        
        total_pages = (total + page_size - 1) // page_size
        
        logger.info(
            f"Admin {current_user.email} searched audit logs: "
            f"{total} total results, page {page}/{total_pages}"
        )
        
        return AuditLogListResponse(
            success=True,
            items=logs,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching audit logs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search audit logs"
        )


@router.get("/stats")
async def get_audit_statistics(
    organization_id: Optional[UUID] = Query(None, description="Filter by organization ID"),
    start_date: Optional[date] = Query(None, description="Start date for statistics"),
    end_date: Optional[date] = Query(None, description="End date for statistics"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
) -> AuditStatisticsResponse:
    """
    Get audit log statistics for the platform or specific organization.
    
    Returns:
    - Total log count
    - Unique users and organizations
    - Actions breakdown
    - Entity types breakdown
    - Severity breakdown
    - Daily activity trend
    - Top organizations by activity
    """
    try:
        service = AdminAuditLogService(db)
        stats = await service.get_audit_statistics(
            organization_id=organization_id,
            start_date=start_date,
            end_date=end_date,
        )
        
        logger.info(f"Admin {current_user.email} retrieved audit statistics")
        
        return AuditStatisticsResponse(
            success=True,
            statistics=stats,
        )
        
    except Exception as e:
        logger.error(f"Error getting audit statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get audit statistics"
        )


@router.get("/filters/actions")
async def get_action_types(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
) -> FilterOptionsResponse:
    """Get all distinct action types available for filtering."""
    try:
        service = AdminAuditLogService(db)
        actions = await service.get_distinct_actions()
        
        return FilterOptionsResponse(
            success=True,
            options=actions,
        )
        
    except Exception as e:
        logger.error(f"Error getting action types: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get action types"
        )


@router.get("/filters/entity-types")
async def get_entity_types(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
) -> FilterOptionsResponse:
    """Get all distinct entity types available for filtering."""
    try:
        service = AdminAuditLogService(db)
        entity_types = await service.get_distinct_entity_types()
        
        return FilterOptionsResponse(
            success=True,
            options=entity_types,
        )
        
    except Exception as e:
        logger.error(f"Error getting entity types: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get entity types"
        )


@router.get("/user/{user_id}/activity")
async def get_user_activity(
    user_id: UUID,
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
) -> UserActivityResponse:
    """
    Get activity summary for a specific user.
    
    Returns:
    - User details
    - Total activities count
    - Actions breakdown
    - IP addresses used
    - Organizations accessed
    - Recent activities list
    """
    try:
        service = AdminAuditLogService(db)
        activity = await service.get_user_activity_summary(
            user_id=user_id,
            days=days,
        )
        
        if "error" in activity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=activity["error"]
            )
        
        logger.info(
            f"Admin {current_user.email} retrieved activity for user {user_id}"
        )
        
        return UserActivityResponse(
            success=True,
            activity=activity,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user activity: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user activity"
        )


@router.get("/{log_id}")
async def get_audit_log_detail(
    log_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
) -> AuditLogDetailResponse:
    """
    Get detailed information about a specific audit log entry.
    
    Returns full audit log details including:
    - User details (if available)
    - Organization name
    - Full old/new values
    - Calculated changes
    - IP address and user agent
    - Session and device information
    """
    try:
        service = AdminAuditLogService(db)
        log_detail = await service.get_audit_log_detail(log_id)
        
        if not log_detail:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Audit log entry not found"
            )
        
        logger.info(
            f"Admin {current_user.email} viewed audit log {log_id}"
        )
        
        return AuditLogDetailResponse(
            success=True,
            log=log_detail,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting audit log detail: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get audit log detail"
        )
