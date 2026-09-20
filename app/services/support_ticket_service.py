"""
Tekvwa Pro Audit - Support Ticket Service

Service layer for managing support tickets.
Available to customer service and super admin roles.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.support_ticket import (
    SupportTicket,
    TicketComment,
    TicketAttachment,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    TicketSource,
)
from app.models.organization import Organization
from app.models.user import User


class SupportTicketService:
    """Service for managing support tickets."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_ticket(
        self,
        organization_id: uuid.UUID,
        category: TicketCategory,
        priority: TicketPriority,
        subject: str,
        description: str,
        reporter_user_id: Optional[uuid.UUID] = None,
        reporter_email: Optional[str] = None,
        reporter_name: Optional[str] = None,
        source: TicketSource = TicketSource.WEB_PORTAL,
        assigned_to_id: Optional[uuid.UUID] = None,
    ) -> SupportTicket:
        """Create a new support ticket."""
        ticket_number = await self._generate_ticket_number()
        
        ticket = SupportTicket(
            ticket_number=ticket_number,
            organization_id=organization_id,
            category=category,
            priority=priority,
            status=TicketStatus.OPEN,
            source=source,
            subject=subject,
            description=description,
            reporter_user_id=reporter_user_id,
            reporter_email=reporter_email,
            reporter_name=reporter_name,
            assigned_to_id=assigned_to_id,
        )
        
        # Set SLA based on priority
        ticket.sla_due_at = self._calculate_sla_due_date(priority)
        
        self.db.add(ticket)
        await self.db.commit()
        await self.db.refresh(ticket)
        
        return ticket
    
    async def get_ticket(self, ticket_id: uuid.UUID) -> Optional[SupportTicket]:
        """Get a support ticket by ID."""
        result = await self.db.execute(
            select(SupportTicket).where(SupportTicket.id == ticket_id)
        )
        return result.scalar_one_or_none()
    
    async def get_ticket_by_number(self, ticket_number: str) -> Optional[SupportTicket]:
        """Get a support ticket by ticket number."""
        result = await self.db.execute(
            select(SupportTicket).where(SupportTicket.ticket_number == ticket_number)
        )
        return result.scalar_one_or_none()
    
    async def get_all_tickets(
        self,
        status: Optional[TicketStatus] = None,
        category: Optional[TicketCategory] = None,
        priority: Optional[TicketPriority] = None,
        organization_id: Optional[uuid.UUID] = None,
        assigned_to_id: Optional[uuid.UUID] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[SupportTicket]:
        """Get all support tickets with optional filters."""
        query = select(SupportTicket)
        
        conditions = []
        if status:
            conditions.append(SupportTicket.status == status)
        if category:
            conditions.append(SupportTicket.category == category)
        if priority:
            conditions.append(SupportTicket.priority == priority)
        if organization_id:
            conditions.append(SupportTicket.organization_id == organization_id)
        if assigned_to_id:
            conditions.append(SupportTicket.assigned_to_id == assigned_to_id)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        query = query.order_by(desc(SupportTicket.created_at))
        query = query.offset(offset).limit(limit)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_open_tickets_count(self) -> int:
        """Get count of open tickets."""
        result = await self.db.execute(
            select(func.count(SupportTicket.id)).where(
                SupportTicket.status.in_([
                    TicketStatus.OPEN,
                    TicketStatus.IN_PROGRESS,
                    TicketStatus.PENDING_CUSTOMER,
                    TicketStatus.ON_HOLD,
                ])
            )
        )
        return result.scalar() or 0
    
    async def get_tickets_stats(self) -> Dict[str, Any]:
        """Get statistics for support tickets."""
        # Open tickets
        open_count = await self.get_open_tickets_count()
        
        # Critical priority open
        critical = await self.db.execute(
            select(func.count(SupportTicket.id)).where(
                and_(
                    SupportTicket.priority == TicketPriority.CRITICAL,
                    SupportTicket.status.in_([
                        TicketStatus.OPEN,
                        TicketStatus.IN_PROGRESS,
                        TicketStatus.PENDING_CUSTOMER,
                        TicketStatus.ON_HOLD,
                    ])
                )
            )
        )
        critical_count = critical.scalar() or 0
        
        # SLA breached
        now = datetime.now(timezone.utc)
        sla_breached = await self.db.execute(
            select(func.count(SupportTicket.id)).where(
                and_(
                    SupportTicket.status.in_([
                        TicketStatus.OPEN,
                        TicketStatus.IN_PROGRESS,
                        TicketStatus.PENDING_CUSTOMER,
                        TicketStatus.ON_HOLD,
                    ]),
                    SupportTicket.sla_due_at < now,
                    SupportTicket.sla_breached == True
                )
            )
        )
        sla_breached_count = sla_breached.scalar() or 0
        
        # Resolved today
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        resolved = await self.db.execute(
            select(func.count(SupportTicket.id)).where(
                and_(
                    SupportTicket.status == TicketStatus.RESOLVED,
                    SupportTicket.resolved_at >= today
                )
            )
        )
        resolved_today = resolved.scalar() or 0
        
        # Note: avg response time and resolution time would require calculation
        # from datetime fields. Return None for now until we add computed columns
        # or calculate from first_response_at and resolved_at.
        
        return {
            "open": open_count,
            "critical": critical_count,
            "sla_breached": sla_breached_count,
            "resolved_today": resolved_today,
            "avg_response_time_minutes": None,
            "avg_resolution_time_minutes": None,
        }
    
    async def get_tickets_by_category(self) -> Dict[str, int]:
        """Get count of tickets by category."""
        result = await self.db.execute(
            select(SupportTicket.category, func.count(SupportTicket.id))
            .where(SupportTicket.status.in_([
                TicketStatus.OPEN,
                TicketStatus.IN_PROGRESS,
                TicketStatus.PENDING_CUSTOMER,
                TicketStatus.ON_HOLD,
            ]))
            .group_by(SupportTicket.category)
        )
        return {str(row[0].value): row[1] for row in result.all()}
    
    async def assign_ticket(
        self,
        ticket_id: uuid.UUID,
        assigned_to_id: uuid.UUID,
    ) -> SupportTicket:
        """Assign a ticket to a staff member."""
        ticket = await self.get_ticket(ticket_id)
        if not ticket:
            raise ValueError(f"Support ticket {ticket_id} not found")
        
        ticket.assigned_to_id = assigned_to_id
        if ticket.status == TicketStatus.OPEN:
            ticket.status = TicketStatus.IN_PROGRESS
        
        await self.db.commit()
        await self.db.refresh(ticket)
        
        return ticket
    
    async def update_status(
        self,
        ticket_id: uuid.UUID,
        status: TicketStatus,
        resolution_notes: Optional[str] = None,
        resolved_by_id: Optional[uuid.UUID] = None,
    ) -> SupportTicket:
        """Update the status of a support ticket."""
        ticket = await self.get_ticket(ticket_id)
        if not ticket:
            raise ValueError(f"Support ticket {ticket_id} not found")
        
        old_status = ticket.status
        ticket.status = status
        
        if status in [TicketStatus.RESOLVED, TicketStatus.CLOSED]:
            ticket.resolved_at = datetime.now(timezone.utc)
            ticket.resolved_by_id = resolved_by_id
            ticket.resolution_notes = resolution_notes
            
            # Calculate resolution time
            if ticket.created_at:
                delta = ticket.resolved_at - ticket.created_at
                ticket.resolution_time_minutes = int(delta.total_seconds() / 60)
        
        await self.db.commit()
        await self.db.refresh(ticket)
        
        return ticket
    
    async def escalate_ticket(
        self,
        ticket_id: uuid.UUID,
        escalation_reason: str,
        escalated_by_id: uuid.UUID,
    ) -> SupportTicket:
        """Escalate a support ticket."""
        ticket = await self.get_ticket(ticket_id)
        if not ticket:
            raise ValueError(f"Support ticket {ticket_id} not found")
        
        ticket.status = TicketStatus.ON_HOLD
        ticket.is_escalated = True
        ticket.escalation_reason = escalation_reason
        ticket.escalated_at = datetime.now(timezone.utc)
        ticket.escalation_level = (ticket.escalation_level or 0) + 1
        
        await self.db.commit()
        await self.db.refresh(ticket)
        
        return ticket
    
    async def add_comment(
        self,
        ticket_id: uuid.UUID,
        comment_text: str,
        staff_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
        is_internal: bool = False,
    ) -> TicketComment:
        """Add a comment to a support ticket."""
        ticket = await self.get_ticket(ticket_id)
        if not ticket:
            raise ValueError(f"Support ticket {ticket_id} not found")
        
        comment = TicketComment(
            support_ticket_id=ticket_id,
            staff_id=staff_id,
            user_id=user_id,
            comment=comment_text,
            is_internal=is_internal,
        )
        
        self.db.add(comment)
        
        # Update first response time if this is staff's first response
        if staff_id and ticket.first_response_at is None and not is_internal:
            ticket.first_response_at = datetime.now(timezone.utc)
        
        await self.db.commit()
        await self.db.refresh(comment)
        
        return comment
    
    async def add_attachment(
        self,
        ticket_id: uuid.UUID,
        filename: str,
        file_path: str,
        file_size: int,
        content_type: str,
        uploaded_by_staff_id: Optional[uuid.UUID] = None,
        uploaded_by_user_id: Optional[uuid.UUID] = None,
    ) -> TicketAttachment:
        """Add an attachment to a support ticket."""
        ticket = await self.get_ticket(ticket_id)
        if not ticket:
            raise ValueError(f"Support ticket {ticket_id} not found")
        
        attachment = TicketAttachment(
            support_ticket_id=ticket_id,
            filename=filename,
            file_path=file_path,
            file_size=file_size,
            content_type=content_type,
            uploaded_by_staff_id=uploaded_by_staff_id,
            uploaded_by_user_id=uploaded_by_user_id,
        )
        
        self.db.add(attachment)
        await self.db.commit()
        await self.db.refresh(attachment)
        
        return attachment
    
    async def get_comments(
        self,
        ticket_id: uuid.UUID,
        include_internal: bool = False,
        limit: int = 100,
    ) -> List[TicketComment]:
        """Get comments for a support ticket."""
        query = select(TicketComment).where(
            TicketComment.support_ticket_id == ticket_id
        )
        
        if not include_internal:
            query = query.where(TicketComment.is_internal == False)
        
        query = query.order_by(TicketComment.created_at)
        query = query.limit(limit)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_attachments(self, ticket_id: uuid.UUID) -> List[TicketAttachment]:
        """Get attachments for a support ticket."""
        result = await self.db.execute(
            select(TicketAttachment)
            .where(TicketAttachment.support_ticket_id == ticket_id)
            .order_by(TicketAttachment.created_at)
        )
        return list(result.scalars().all())
    
    async def mark_sla_breached(self, ticket_id: uuid.UUID) -> SupportTicket:
        """Mark a ticket as having breached SLA."""
        ticket = await self.get_ticket(ticket_id)
        if not ticket:
            raise ValueError(f"Support ticket {ticket_id} not found")
        
        ticket.sla_breached = True
        
        await self.db.commit()
        await self.db.refresh(ticket)
        
        return ticket
    
    async def check_and_update_sla_breaches(self) -> int:
        """Check and update SLA breaches for all open tickets."""
        now = datetime.now(timezone.utc)
        
        result = await self.db.execute(
            select(SupportTicket).where(
                and_(
                    SupportTicket.status.in_([
                        TicketStatus.OPEN,
                        TicketStatus.IN_PROGRESS,
                        TicketStatus.PENDING_CUSTOMER,
                        TicketStatus.ON_HOLD,
                    ]),
                    SupportTicket.sla_due_at < now,
                    SupportTicket.sla_breached == False
                )
            )
        )
        tickets = result.scalars().all()
        
        breached_count = 0
        for ticket in tickets:
            ticket.sla_breached = True
            breached_count += 1
        
        if breached_count > 0:
            await self.db.commit()
        
        return breached_count
    
    def _calculate_sla_due_date(self, priority: TicketPriority) -> datetime:
        """Calculate SLA due date based on priority."""
        now = datetime.now(timezone.utc)
        
        sla_hours = {
            TicketPriority.CRITICAL: 2,
            TicketPriority.HIGH: 8,
            TicketPriority.MEDIUM: 24,
            TicketPriority.LOW: 72,
        }
        
        hours = sla_hours.get(priority, 24)
        return now + timedelta(hours=hours)
    
    async def _generate_ticket_number(self) -> str:
        """Generate a unique ticket number."""
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        
        result = await self.db.execute(
            select(func.count(SupportTicket.id)).where(
                SupportTicket.ticket_number.like(f"TKT-{today}-%")
            )
        )
        count = (result.scalar() or 0) + 1
        
        return f"TKT-{today}-{count:04d}"
