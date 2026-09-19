"""
Tekvwa Pro Audit - Support Tickets Router

API endpoints for managing support tickets.
Available to customer service and super admin roles.
"""

import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import require_super_admin, require_platform_staff
from app.models.user import User
from app.models.support_ticket import (
    TicketCategory,
    TicketPriority,
    TicketStatus,
    TicketSource,
)
from app.services.support_ticket_service import SupportTicketService


router = APIRouter(prefix="/support-tickets", tags=["Support Tickets"])


# ===========================================
# REQUEST/RESPONSE SCHEMAS
# ===========================================

class CreateTicketRequest(BaseModel):
    """Request schema for creating a support ticket."""
    organization_id: uuid.UUID
    category: TicketCategory
    priority: TicketPriority
    subject: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    reporter_email: Optional[str] = Field(None, max_length=255)
    reporter_name: Optional[str] = Field(None, max_length=255)
    source: TicketSource = TicketSource.WEB_PORTAL
    assigned_to_id: Optional[uuid.UUID] = None


class TicketResponse(BaseModel):
    """Response schema for support ticket."""
    id: uuid.UUID
    ticket_number: str
    organization_id: uuid.UUID
    category: str
    priority: str
    status: str
    source: str
    subject: str
    description: str
    reporter_email: Optional[str]
    reporter_name: Optional[str]
    assigned_to_id: Optional[uuid.UUID]
    sla_due_at: Optional[str]
    sla_breached: bool
    is_escalated: bool
    first_response_at: Optional[str]
    resolved_at: Optional[str]
    response_time_minutes: Optional[int]
    resolution_time_minutes: Optional[int]
    created_at: str
    
    class Config:
        from_attributes = True


class TicketListResponse(BaseModel):
    """Response schema for support ticket list."""
    tickets: List[TicketResponse]
    total: int


class TicketStatsResponse(BaseModel):
    """Response schema for support ticket statistics."""
    open: int
    critical: int
    sla_breached: int
    resolved_today: int
    avg_response_time_minutes: Optional[int]
    avg_resolution_time_minutes: Optional[int]


class UpdateStatusRequest(BaseModel):
    """Request schema for updating ticket status."""
    status: TicketStatus
    resolution_notes: Optional[str] = None


class AssignTicketRequest(BaseModel):
    """Request schema for assigning a ticket."""
    assigned_to_id: uuid.UUID


class EscalateTicketRequest(BaseModel):
    """Request schema for escalating a ticket."""
    escalation_reason: str = Field(..., min_length=1)


class AddCommentRequest(BaseModel):
    """Request schema for adding a comment."""
    comment: str = Field(..., min_length=1)
    is_internal: bool = False


# ===========================================
# API ENDPOINTS
# ===========================================

@router.post("", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
async def create_support_ticket(
    request: CreateTicketRequest,
    current_user: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """Create a new support ticket (Platform Staff)."""
    service = SupportTicketService(db)
    
    try:
        ticket = await service.create_ticket(
            organization_id=request.organization_id,
            category=request.category,
            priority=request.priority,
            subject=request.subject,
            description=request.description,
            reporter_email=request.reporter_email,
            reporter_name=request.reporter_name,
            source=request.source,
            assigned_to_id=request.assigned_to_id,
        )
        
        return _format_ticket(ticket)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("", response_model=TicketListResponse)
async def list_support_tickets(
    status_filter: Optional[TicketStatus] = Query(None, alias="status"),
    category: Optional[TicketCategory] = None,
    priority: Optional[TicketPriority] = None,
    organization_id: Optional[uuid.UUID] = None,
    assigned_to_id: Optional[uuid.UUID] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """List all support tickets (Platform Staff)."""
    service = SupportTicketService(db)
    
    tickets = await service.get_all_tickets(
        status=status_filter,
        category=category,
        priority=priority,
        organization_id=organization_id,
        assigned_to_id=assigned_to_id,
        limit=limit,
        offset=offset,
    )
    
    return {
        "tickets": [_format_ticket(t) for t in tickets],
        "total": len(tickets),
    }


@router.get("/stats", response_model=TicketStatsResponse)
async def get_ticket_stats(
    current_user: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """Get support ticket statistics (Platform Staff)."""
    service = SupportTicketService(db)
    stats = await service.get_tickets_stats()
    return stats


@router.get("/by-category")
async def get_tickets_by_category(
    current_user: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """Get tickets grouped by category (Platform Staff)."""
    service = SupportTicketService(db)
    by_category = await service.get_tickets_by_category()
    return {"by_category": by_category}


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_support_ticket(
    ticket_id: uuid.UUID,
    current_user: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """Get a specific support ticket (Platform Staff)."""
    service = SupportTicketService(db)
    ticket = await service.get_ticket(ticket_id)
    
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Support ticket not found",
        )
    
    return _format_ticket(ticket)


@router.put("/{ticket_id}/status", response_model=TicketResponse)
async def update_ticket_status(
    ticket_id: uuid.UUID,
    request: UpdateStatusRequest,
    current_user: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """Update support ticket status (Platform Staff)."""
    service = SupportTicketService(db)
    
    try:
        ticket = await service.update_status(
            ticket_id=ticket_id,
            status=request.status,
            resolution_notes=request.resolution_notes,
            resolved_by_id=current_user.id,
        )
        return _format_ticket(ticket)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{ticket_id}/assign", response_model=TicketResponse)
async def assign_ticket(
    ticket_id: uuid.UUID,
    request: AssignTicketRequest,
    current_user: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """Assign a support ticket (Platform Staff)."""
    service = SupportTicketService(db)
    
    try:
        ticket = await service.assign_ticket(
            ticket_id=ticket_id,
            assigned_to_id=request.assigned_to_id,
        )
        return _format_ticket(ticket)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{ticket_id}/escalate", response_model=TicketResponse)
async def escalate_ticket(
    ticket_id: uuid.UUID,
    request: EscalateTicketRequest,
    current_user: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """Escalate a support ticket (Platform Staff)."""
    service = SupportTicketService(db)
    
    try:
        ticket = await service.escalate_ticket(
            ticket_id=ticket_id,
            escalation_reason=request.escalation_reason,
            escalated_by_id=current_user.id,
        )
        return _format_ticket(ticket)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{ticket_id}/comments")
async def add_comment(
    ticket_id: uuid.UUID,
    request: AddCommentRequest,
    current_user: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """Add a comment to a support ticket (Platform Staff)."""
    service = SupportTicketService(db)
    
    try:
        comment = await service.add_comment(
            ticket_id=ticket_id,
            comment_text=request.comment,
            staff_id=current_user.id,
            is_internal=request.is_internal,
        )
        return {
            "id": str(comment.id),
            "comment": comment.comment,
            "is_internal": comment.is_internal,
            "created_at": comment.created_at.isoformat() if comment.created_at else None,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/{ticket_id}/comments")
async def get_comments(
    ticket_id: uuid.UUID,
    include_internal: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """Get comments for a support ticket (Platform Staff)."""
    service = SupportTicketService(db)
    
    # Verify ticket exists
    ticket = await service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Support ticket not found",
        )
    
    comments = await service.get_comments(
        ticket_id=ticket_id,
        include_internal=include_internal,
        limit=limit,
    )
    
    return {
        "comments": [
            {
                "id": str(c.id),
                "comment": c.comment,
                "is_internal": c.is_internal,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in comments
        ],
        "total": len(comments),
    }


@router.get("/{ticket_id}/attachments")
async def get_attachments(
    ticket_id: uuid.UUID,
    current_user: User = Depends(require_platform_staff),
    db: AsyncSession = Depends(get_async_session),
):
    """Get attachments for a support ticket (Platform Staff)."""
    service = SupportTicketService(db)
    
    # Verify ticket exists
    ticket = await service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Support ticket not found",
        )
    
    attachments = await service.get_attachments(ticket_id)
    
    return {
        "attachments": [
            {
                "id": str(a.id),
                "filename": a.filename,
                "file_size": a.file_size,
                "content_type": a.content_type,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in attachments
        ],
        "total": len(attachments),
    }


@router.post("/check-sla-breaches")
async def check_sla_breaches(
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Check and update SLA breaches for all open tickets (Super Admin only)."""
    service = SupportTicketService(db)
    breached_count = await service.check_and_update_sla_breaches()
    
    return {
        "breached_count": breached_count,
        "message": f"Updated {breached_count} tickets as SLA breached",
    }


def _format_ticket(ticket) -> dict:
    """Format support ticket for response."""
    return {
        "id": ticket.id,
        "ticket_number": ticket.ticket_number,
        "organization_id": ticket.organization_id,
        "category": ticket.category.value if ticket.category else None,
        "priority": ticket.priority.value if ticket.priority else None,
        "status": ticket.status.value if ticket.status else None,
        "source": ticket.source.value if ticket.source else None,
        "subject": ticket.subject,
        "description": ticket.description,
        "reporter_email": ticket.reporter_email,
        "reporter_name": ticket.reporter_name,
        "assigned_to_id": ticket.assigned_to_id,
        "sla_due_at": ticket.sla_due_at.isoformat() if ticket.sla_due_at else None,
        "sla_breached": ticket.sla_breached,
        "is_escalated": ticket.is_escalated,
        "first_response_at": ticket.first_response_at.isoformat() if ticket.first_response_at else None,
        "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
        "response_time_minutes": ticket.response_time_minutes,
        "resolution_time_minutes": ticket.resolution_time_minutes,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
    }
