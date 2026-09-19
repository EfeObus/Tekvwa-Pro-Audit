"""
Tekvwa Pro Audit - Admin Organization Verification Router

Super Admin endpoints for comprehensive organization verification workflow:
- GET /admin/verifications - List organizations with filtering
- GET /admin/verifications/stats - Get verification statistics
- GET /admin/verifications/{org_id} - Get organization details
- GET /admin/verifications/{org_id}/history - Get verification history
- POST /admin/verifications/{org_id}/start-review - Start reviewing (→ UNDER_REVIEW)
- POST /admin/verifications/{org_id}/approve - Approve organization (→ VERIFIED)
- POST /admin/verifications/{org_id}/reject - Reject organization (→ REJECTED)
- POST /admin/verifications/{org_id}/request-documents - Request additional documents
- POST /admin/verifications/{org_id}/reset - Reset status (Super Admin only)
"""

import uuid
from datetime import datetime
from typing import List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import get_current_platform_admin, require_super_admin
from app.models.user import User
from app.services.organization_verification_service import OrganizationVerificationService


router = APIRouter(prefix="/admin/verifications", tags=["Admin - Organization Verification"])


# ===========================================
# REQUEST/RESPONSE SCHEMAS
# ===========================================

class VerificationStatsResponse(BaseModel):
    """Statistics about organization verification."""
    pending: int
    submitted: int
    under_review: int
    verified: int
    rejected: int
    total: int


class DocumentInfo(BaseModel):
    """Document information."""
    cac_document_path: Optional[str] = None
    tin_document_path: Optional[str] = None
    additional_documents: List[str] = []


class AdminContact(BaseModel):
    """Organization admin contact info."""
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class OrganizationVerificationDetail(BaseModel):
    """Detailed organization information for verification."""
    id: str
    name: str
    slug: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    organization_type: Optional[str] = None
    subscription_tier: Optional[str] = None
    verification_status: str
    verification_notes: Optional[str] = None
    verified_by_id: Optional[str] = None
    is_emergency_suspended: bool = False
    emergency_suspension_reason: Optional[str] = None
    user_count: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    documents: DocumentInfo
    admin_contact: Optional[AdminContact] = None


class OrganizationListItem(BaseModel):
    """Organization item for list view."""
    id: str
    name: str
    email: Optional[str] = None
    organization_type: Optional[str] = None
    verification_status: str
    verification_notes: Optional[str] = None
    cac_document_path: Optional[str] = None
    tin_document_path: Optional[str] = None
    created_at: Optional[str] = None


class OrganizationListResponse(BaseModel):
    """Response for organization list."""
    organizations: List[OrganizationListItem]
    total: int
    page: int
    page_size: int


class VerificationHistoryEntry(BaseModel):
    """Single verification history entry."""
    id: str
    action: str
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    details: dict = {}
    created_at: Optional[str] = None


class VerificationHistoryResponse(BaseModel):
    """Verification history response."""
    organization_id: str
    organization_name: str
    history: List[VerificationHistoryEntry]


class NotesRequest(BaseModel):
    """Request with optional notes."""
    notes: Optional[str] = Field(None, max_length=2000)


class RejectRequest(BaseModel):
    """Request for rejection."""
    reason: str = Field(..., min_length=5, max_length=2000)


class RequestDocumentsRequest(BaseModel):
    """Request for additional documents."""
    requested_documents: List[str] = Field(..., min_items=1)
    notes: str = Field(..., min_length=10, max_length=2000)


class ResetRequest(BaseModel):
    """Request for status reset."""
    reason: str = Field(..., min_length=5, max_length=2000)


class SuccessResponse(BaseModel):
    """Generic success response."""
    success: bool = True
    message: str
    organization_id: str
    new_status: str


# ===========================================
# ENDPOINTS
# ===========================================

@router.get(
    "/stats",
    response_model=VerificationStatsResponse,
    summary="Get verification statistics",
    description="Get counts of organizations by verification status.",
)
async def get_verification_stats(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_platform_admin),
):
    """Get verification statistics."""
    service = OrganizationVerificationService(db)
    
    try:
        stats = await service.get_verification_stats(current_user)
        return VerificationStatsResponse(**stats)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )


@router.get(
    "",
    response_model=OrganizationListResponse,
    summary="List organizations for verification",
    description="List organizations with optional status filtering and search.",
)
async def list_organizations(
    status_filter: Optional[str] = Query(
        None, 
        description="Filter by status: pending, submitted, under_review, verified, rejected, pending_review"
    ),
    search: Optional[str] = Query(None, description="Search by name or email"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_platform_admin),
):
    """List organizations for verification review."""
    service = OrganizationVerificationService(db)
    
    skip = (page - 1) * page_size
    
    try:
        organizations, total = await service.list_organizations_for_verification(
            requesting_user=current_user,
            status_filter=status_filter,
            search_query=search,
            skip=skip,
            limit=page_size,
        )
        
        items = [
            OrganizationListItem(
                id=str(org.id),
                name=org.name,
                email=org.email,
                organization_type=org.organization_type.value if org.organization_type else None,
                verification_status=org.verification_status.value if org.verification_status else "pending",
                verification_notes=org.verification_notes,
                cac_document_path=org.cac_document_path,
                tin_document_path=org.tin_document_path,
                created_at=org.created_at.isoformat() if org.created_at else None,
            )
            for org in organizations
        ]
        
        return OrganizationListResponse(
            organizations=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )


@router.get(
    "/{org_id}",
    response_model=OrganizationVerificationDetail,
    summary="Get organization details",
    description="Get detailed organization information for verification review.",
)
async def get_organization_details(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_platform_admin),
):
    """Get organization details for review."""
    service = OrganizationVerificationService(db)
    
    try:
        details = await service.get_organization_details(current_user, org_id)
        
        # Convert to response model
        return OrganizationVerificationDetail(
            id=details["id"],
            name=details["name"],
            slug=details.get("slug"),
            email=details.get("email"),
            phone=details.get("phone"),
            organization_type=details.get("organization_type"),
            subscription_tier=details.get("subscription_tier"),
            verification_status=details["verification_status"],
            verification_notes=details.get("verification_notes"),
            verified_by_id=details.get("verified_by_id"),
            is_emergency_suspended=details.get("is_emergency_suspended", False),
            emergency_suspension_reason=details.get("emergency_suspension_reason"),
            user_count=details["user_count"],
            created_at=details.get("created_at"),
            updated_at=details.get("updated_at"),
            documents=DocumentInfo(
                cac_document_path=details["documents"]["cac_document_path"],
                tin_document_path=details["documents"]["tin_document_path"],
                additional_documents=details["documents"]["additional_documents"],
            ),
            admin_contact=AdminContact(**details["admin_contact"]) if details.get("admin_contact") else None,
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get(
    "/{org_id}/history",
    response_model=VerificationHistoryResponse,
    summary="Get verification history",
    description="Get the verification action history for an organization.",
)
async def get_verification_history(
    org_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_platform_admin),
):
    """Get verification history for an organization."""
    service = OrganizationVerificationService(db)
    
    try:
        # Get org name
        org_details = await service.get_organization_details(current_user, org_id)
        
        # Get history
        history = await service.get_verification_history(current_user, org_id, limit)
        
        return VerificationHistoryResponse(
            organization_id=str(org_id),
            organization_name=org_details["name"],
            history=[VerificationHistoryEntry(**entry) for entry in history],
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post(
    "/{org_id}/start-review",
    response_model=SuccessResponse,
    summary="Start verification review",
    description="Move organization from SUBMITTED to UNDER_REVIEW status.",
)
async def start_review(
    org_id: uuid.UUID,
    request: NotesRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_platform_admin),
):
    """Start reviewing an organization."""
    service = OrganizationVerificationService(db)
    
    try:
        org = await service.start_review(
            requesting_user=current_user,
            organization_id=org_id,
            notes=request.notes,
        )
        
        return SuccessResponse(
            message=f"Started review for '{org.name}'",
            organization_id=str(org.id),
            new_status=org.verification_status.value,
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/{org_id}/approve",
    response_model=SuccessResponse,
    summary="Approve organization",
    description="Approve an organization's verification (move to VERIFIED status).",
)
async def approve_organization(
    org_id: uuid.UUID,
    request: NotesRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_platform_admin),
):
    """Approve an organization's verification."""
    service = OrganizationVerificationService(db)
    
    try:
        org = await service.approve_organization(
            requesting_user=current_user,
            organization_id=org_id,
            notes=request.notes,
        )
        
        return SuccessResponse(
            message=f"Organization '{org.name}' has been verified",
            organization_id=str(org.id),
            new_status=org.verification_status.value,
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/{org_id}/reject",
    response_model=SuccessResponse,
    summary="Reject organization",
    description="Reject an organization's verification (move to REJECTED status).",
)
async def reject_organization(
    org_id: uuid.UUID,
    request: RejectRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_platform_admin),
):
    """Reject an organization's verification."""
    service = OrganizationVerificationService(db)
    
    try:
        org = await service.reject_organization(
            requesting_user=current_user,
            organization_id=org_id,
            reason=request.reason,
        )
        
        return SuccessResponse(
            message=f"Organization '{org.name}' verification has been rejected",
            organization_id=str(org.id),
            new_status=org.verification_status.value,
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/{org_id}/request-documents",
    response_model=SuccessResponse,
    summary="Request additional documents",
    description="Request additional documents from an organization.",
)
async def request_documents(
    org_id: uuid.UUID,
    request: RequestDocumentsRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_platform_admin),
):
    """Request additional documents from an organization."""
    service = OrganizationVerificationService(db)
    
    try:
        org = await service.request_additional_documents(
            requesting_user=current_user,
            organization_id=org_id,
            requested_documents=request.requested_documents,
            notes=request.notes,
        )
        
        return SuccessResponse(
            message=f"Document request sent to '{org.name}'",
            organization_id=str(org.id),
            new_status=org.verification_status.value,
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/{org_id}/reset",
    response_model=SuccessResponse,
    summary="Reset verification status",
    description="Reset organization verification status back to SUBMITTED. Super Admin only.",
)
async def reset_verification_status(
    org_id: uuid.UUID,
    request: ResetRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """Reset verification status (Super Admin only)."""
    service = OrganizationVerificationService(db)
    
    try:
        org = await service.reset_to_submitted(
            requesting_user=current_user,
            organization_id=org_id,
            reason=request.reason,
        )
        
        return SuccessResponse(
            message=f"Verification status for '{org.name}' has been reset to SUBMITTED",
            organization_id=str(org.id),
            new_status=org.verification_status.value,
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
