"""
TekVwarho ProAudit - Admin User Search API Router

Cross-tenant user search endpoints for Super Admin functionality.
All endpoints require Super Admin authentication.

Endpoints:
- GET /api/v1/admin/users/search - Search users across all tenants
- GET /api/v1/admin/users/{user_id} - Get detailed user info
- GET /api/v1/admin/users/{user_id}/activity - Get user activity summary
- GET /api/v1/admin/users/organizations - Get organizations for filter
- GET /api/v1/admin/users/stats - Get platform user statistics
"""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import require_super_admin
from app.models.user import User, UserRole, PlatformRole
from app.services.admin_user_search_service import AdminUserSearchService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/users",
    tags=["Admin User Management"],
    responses={404: {"description": "Not found"}},
)

templates = Jinja2Templates(directory="templates")


# ==================== API Endpoints ====================

@router.get("/search")
async def search_users(
    query: Optional[str] = Query(None, description="Search term for email, name, or phone"),
    organization_id: Optional[UUID] = Query(None, description="Filter by organization ID"),
    platform_role: Optional[str] = Query(None, description="Filter by platform role"),
    org_role: Optional[str] = Query(None, description="Filter by organization role"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    is_verified: Optional[bool] = Query(None, description="Filter by verification status"),
    is_platform_staff: Optional[bool] = Query(None, description="Filter platform staff vs org users"),
    created_after: Optional[datetime] = Query(None, description="Filter users created after date"),
    created_before: Optional[datetime] = Query(None, description="Filter users created before date"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order (asc/desc)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Results per page"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Search users across all organizations.
    
    Super Admin only endpoint for cross-tenant user discovery.
    
    Supports:
    - Text search across email, name, phone
    - Multiple filters (organization, role, status)
    - Pagination and sorting
    """
    try:
        # Parse platform role if provided
        parsed_platform_role = None
        if platform_role:
            try:
                parsed_platform_role = PlatformRole(platform_role)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid platform role: {platform_role}"
                )
        
        # Parse org role if provided
        parsed_org_role = None
        if org_role:
            try:
                parsed_org_role = UserRole(org_role)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid organization role: {org_role}"
                )
        
        service = AdminUserSearchService(db)
        result = await service.search_users(
            query=query,
            organization_id=organization_id,
            platform_role=parsed_platform_role,
            org_role=parsed_org_role,
            is_active=is_active,
            is_verified=is_verified,
            is_platform_staff=is_platform_staff,
            created_after=created_after,
            created_before=created_before,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            page_size=page_size,
        )
        
        logger.info(f"Super Admin {current_user.email} searched users with query: {query}")
        
        return {
            "success": True,
            "data": result,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching users: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error searching users: {str(e)}"
        )


@router.get("/organizations")
async def get_organizations_for_filter(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Get list of all organizations for filter dropdown.
    
    Returns organization ID, name, and user count.
    """
    try:
        service = AdminUserSearchService(db)
        organizations = await service.get_organizations_for_filter()
        
        return {
            "success": True,
            "data": organizations,
        }
        
    except Exception as e:
        logger.error(f"Error getting organizations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting organizations: {str(e)}"
        )


@router.get("/stats")
async def get_user_stats(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Get platform-wide user statistics.
    
    Returns various user counts and breakdowns.
    """
    try:
        service = AdminUserSearchService(db)
        stats = await service.get_user_stats()
        
        return {
            "success": True,
            "data": stats,
        }
        
    except Exception as e:
        logger.error(f"Error getting user stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting user stats: {str(e)}"
        )


@router.get("/{user_id}")
async def get_user_details(
    user_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Get detailed information about a specific user.
    
    Includes organization info, roles, and account status.
    """
    try:
        service = AdminUserSearchService(db)
        user = await service.get_user_details(user_id)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        logger.info(f"Super Admin {current_user.email} viewed user details for {user_id}")
        
        return {
            "success": True,
            "data": user,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting user details: {str(e)}"
        )


@router.get("/{user_id}/activity")
async def get_user_activity(
    user_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Get activity summary for a specific user.
    """
    try:
        service = AdminUserSearchService(db)
        activity = await service.get_user_activity_summary(user_id)
        
        if "error" in activity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=activity["error"]
            )
        
        return {
            "success": True,
            "data": activity,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user activity: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting user activity: {str(e)}"
        )


# ==================== HTML Template Endpoint ====================

@router.get("/", response_class=HTMLResponse)
async def admin_user_search_page(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Render the Admin User Search page.
    """
    try:
        service = AdminUserSearchService(db)
        
        # Get initial data for the page
        stats = await service.get_user_stats()
        organizations = await service.get_organizations_for_filter()
        
        # Get platform roles and org roles for dropdowns
        platform_roles = [role.value for role in PlatformRole]
        org_roles = [role.value for role in UserRole]
        
        return templates.TemplateResponse(
            request, "admin_user_search.html",
            {
                "request": request,
                "current_user": current_user,
                "stats": stats,
                "organizations": organizations,
                "platform_roles": platform_roles,
                "org_roles": org_roles,
            }
        )
        
    except Exception as e:
        logger.error(f"Error loading admin user search page: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error loading page: {str(e)}"
        )
