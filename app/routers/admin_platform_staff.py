"""
Tekvwa Pro Audit - Platform Staff Management API Router

Super Admin endpoints for managing platform staff accounts.

Endpoints:
- GET /api/v1/admin/staff/ - HTML page for staff management
- GET /api/v1/admin/staff/list - List all platform staff
- GET /api/v1/admin/staff/stats - Get staff statistics
- POST /api/v1/admin/staff/create - Create new staff account
- GET /api/v1/admin/staff/{staff_id} - Get staff details
- PUT /api/v1/admin/staff/{staff_id} - Update staff account
- POST /api/v1/admin/staff/{staff_id}/reset-password - Reset staff password
- POST /api/v1/admin/staff/{staff_id}/deactivate - Deactivate staff
- POST /api/v1/admin/staff/{staff_id}/reactivate - Reactivate staff
- GET /api/v1/admin/staff/{staff_id}/audit - Get staff audit history
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import require_super_admin
from app.models.user import User, PlatformRole
from app.services.platform_staff_service import PlatformStaffService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/staff",
    tags=["Platform Staff Management"],
    responses={404: {"description": "Not found"}},
)

templates = Jinja2Templates(directory="templates")


# ==================== Pydantic Schemas ====================

class CreateStaffRequest(BaseModel):
    """Request schema for creating platform staff."""
    email: EmailStr = Field(..., description="Staff email address")
    first_name: str = Field(..., min_length=1, max_length=100, description="First name")
    last_name: str = Field(..., min_length=1, max_length=100, description="Last name")
    platform_role: str = Field(..., description="Platform role (super_admin, admin, it_developer, customer_service, marketing)")
    phone_number: Optional[str] = Field(None, max_length=20, description="Phone number")
    staff_notes: Optional[str] = Field(None, description="Internal notes about staff member")
    custom_password: Optional[str] = Field(None, min_length=8, description="Custom password (optional)")


class UpdateStaffRequest(BaseModel):
    """Request schema for updating platform staff."""
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone_number: Optional[str] = Field(None, max_length=20)
    platform_role: Optional[str] = Field(None)
    is_active: Optional[bool] = Field(None)
    staff_notes: Optional[str] = Field(None)


class ResetPasswordRequest(BaseModel):
    """Request schema for password reset."""
    new_password: Optional[str] = Field(None, min_length=8, description="New password (optional, generates if not provided)")


class DeactivateRequest(BaseModel):
    """Request schema for deactivation."""
    reason: Optional[str] = Field(None, description="Reason for deactivation")


class ReactivateRequest(BaseModel):
    """Request schema for reactivation."""
    reason: Optional[str] = Field(None, description="Reason for reactivation")


# ==================== API Endpoints ====================

@router.get("/list")
async def list_platform_staff(
    role: Optional[str] = Query(None, description="Filter by platform role"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    query: Optional[str] = Query(None, description="Search by email or name"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order (asc/desc)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Results per page"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    List all platform staff accounts.
    
    Super Admin only endpoint for viewing platform staff.
    """
    try:
        # Parse role filter
        role_filter = None
        if role:
            try:
                role_filter = PlatformRole(role)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid platform role: {role}"
                )
        
        service = PlatformStaffService(db)
        result = await service.list_platform_staff(
            role_filter=role_filter,
            is_active=is_active,
            query=query,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            page_size=page_size,
        )
        
        logger.info(f"Super Admin {current_user.email} listed platform staff")
        
        return {
            "success": True,
            "data": result,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing platform staff: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing platform staff: {str(e)}"
        )


@router.get("/stats")
async def get_staff_stats(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Get platform staff statistics.
    
    Returns counts by role, active/inactive status, etc.
    """
    try:
        service = PlatformStaffService(db)
        stats = await service.get_staff_stats()
        
        return {
            "success": True,
            "data": stats,
        }
        
    except Exception as e:
        logger.error(f"Error getting staff stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting staff stats: {str(e)}"
        )


@router.post("/create")
async def create_platform_staff(
    request: CreateStaffRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Create a new platform staff account.
    
    Super Admin only. Returns temporary password if not provided.
    """
    try:
        # Parse platform role
        try:
            platform_role = PlatformRole(request.platform_role)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid platform role: {request.platform_role}"
            )
        
        service = PlatformStaffService(db)
        result = await service.create_platform_staff(
            email=request.email,
            first_name=request.first_name,
            last_name=request.last_name,
            platform_role=platform_role,
            created_by=current_user,
            phone_number=request.phone_number,
            staff_notes=request.staff_notes,
            custom_password=request.custom_password,
        )
        
        logger.info(f"Super Admin {current_user.email} created platform staff: {request.email}")
        
        return {
            "success": True,
            "data": result,
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating platform staff: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating platform staff: {str(e)}"
        )


@router.get("/{staff_id}")
async def get_staff_details(
    staff_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Get detailed information about a platform staff member.
    """
    try:
        service = PlatformStaffService(db)
        staff = await service.get_staff_details(staff_id)
        
        if not staff:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Platform staff member not found"
            )
        
        logger.info(f"Super Admin {current_user.email} viewed staff details: {staff_id}")
        
        return {
            "success": True,
            "data": staff,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting staff details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting staff details: {str(e)}"
        )


@router.put("/{staff_id}")
async def update_staff(
    staff_id: UUID,
    request: UpdateStaffRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Update a platform staff account.
    """
    try:
        # Parse platform role if provided
        platform_role = None
        if request.platform_role:
            try:
                platform_role = PlatformRole(request.platform_role)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid platform role: {request.platform_role}"
                )
        
        service = PlatformStaffService(db)
        result = await service.update_staff(
            staff_id=staff_id,
            updated_by=current_user,
            first_name=request.first_name,
            last_name=request.last_name,
            phone_number=request.phone_number,
            platform_role=platform_role,
            is_active=request.is_active,
            staff_notes=request.staff_notes,
        )
        
        logger.info(f"Super Admin {current_user.email} updated platform staff: {staff_id}")
        
        return {
            "success": True,
            "data": result,
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating platform staff: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating platform staff: {str(e)}"
        )


@router.post("/{staff_id}/reset-password")
async def reset_staff_password(
    staff_id: UUID,
    request: ResetPasswordRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Reset a platform staff member's password.
    
    Returns temporary password if not provided in request.
    """
    try:
        service = PlatformStaffService(db)
        result = await service.reset_staff_password(
            staff_id=staff_id,
            reset_by=current_user,
            new_password=request.new_password,
        )
        
        logger.info(f"Super Admin {current_user.email} reset password for: {staff_id}")
        
        return {
            "success": True,
            "data": result,
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error resetting staff password: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error resetting staff password: {str(e)}"
        )


@router.post("/{staff_id}/deactivate")
async def deactivate_staff(
    staff_id: UUID,
    request: DeactivateRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Deactivate a platform staff account.
    """
    try:
        service = PlatformStaffService(db)
        result = await service.deactivate_staff(
            staff_id=staff_id,
            deactivated_by=current_user,
            reason=request.reason,
        )
        
        logger.info(f"Super Admin {current_user.email} deactivated staff: {staff_id}")
        
        return {
            "success": True,
            "data": result,
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error deactivating staff: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deactivating staff: {str(e)}"
        )


@router.post("/{staff_id}/reactivate")
async def reactivate_staff(
    staff_id: UUID,
    request: ReactivateRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Reactivate a deactivated platform staff account.
    """
    try:
        service = PlatformStaffService(db)
        result = await service.reactivate_staff(
            staff_id=staff_id,
            reactivated_by=current_user,
            reason=request.reason,
        )
        
        logger.info(f"Super Admin {current_user.email} reactivated staff: {staff_id}")
        
        return {
            "success": True,
            "data": result,
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error reactivating staff: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error reactivating staff: {str(e)}"
        )


@router.get("/{staff_id}/audit")
async def get_staff_audit_history(
    staff_id: UUID,
    limit: int = Query(50, ge=1, le=200, description="Maximum records to return"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Get audit history for a platform staff member.
    
    Includes actions by and actions on the staff member.
    """
    try:
        service = PlatformStaffService(db)
        
        # Verify staff exists
        staff = await service.get_staff_details(staff_id)
        if not staff:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Platform staff member not found"
            )
        
        audit_logs = await service.get_audit_history(staff_id, limit)
        
        logger.info(f"Super Admin {current_user.email} viewed audit history for: {staff_id}")
        
        return {
            "success": True,
            "data": {
                "staff_id": str(staff_id),
                "staff_email": staff["email"],
                "audit_logs": audit_logs,
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting staff audit history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting staff audit history: {str(e)}"
        )


# ==================== HTML Page ====================

@router.get("/", response_class=HTMLResponse)
async def platform_staff_page(
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Render the platform staff management page.
    """
    try:
        service = PlatformStaffService(db)
        
        # Get stats for the page
        stats = await service.get_staff_stats()
        
        # Get staff list for initial display
        staff_result = await service.list_platform_staff(page=1, page_size=20)
        
        return templates.TemplateResponse(
            request, "admin_platform_staff.html",
            {
                "request": request,
                "user": current_user,
                "stats": stats,
                "staff": staff_result["staff"],
                "pagination": staff_result["pagination"],
                "platform_roles": [role.value for role in PlatformRole],
            }
        )
        
    except Exception as e:
        logger.error(f"Error rendering platform staff page: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error loading platform staff page: {str(e)}"
        )
