"""
Regression coverage for Finding 50's support_tickets/ticket_comments/ticket_attachments column
drift (docs/FINDING_50_SCOPE.md, docs/REMEDIATION_LOG.md).

Before this fix, create_ticket()/add_comment()/add_attachment() -- the only real construction
sites for these three models -- always failed with an UndefinedColumnError, and even a
successfully-created ticket would have failed Pydantic response validation on every read
(app/routers/support_tickets.py's own TicketResponse schema already used the live table's real
field names, not the model's fictional ones).
"""
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.support_ticket import TicketCategory, TicketPriority, TicketStatus
from app.models.user import User
from app.services.support_ticket_service import SupportTicketService


class TestSupportTicketPersistence:
    async def test_create_ticket_and_full_lifecycle(
        self, db_session: AsyncSession, test_organization: Organization, test_user: User,
    ):
        service = SupportTicketService(db_session)

        ticket = await service.create_ticket(
            organization_id=test_organization.id,
            category=TicketCategory.TECHNICAL,
            priority=TicketPriority.HIGH,
            subject="Cannot generate VAT report",
            description="The VAT report export button does nothing.",
            reporter_email="finance@acme.ng",
            reporter_name="Acme Finance",
        )

        assert ticket.id is not None
        assert ticket.organization_id == test_organization.id
        assert ticket.reporter_email == "finance@acme.ng"
        assert ticket.status == TicketStatus.OPEN
        assert ticket.sla_due_at is not None

        comment = await service.add_comment(
            ticket_id=ticket.id,
            comment_text="Looking into this now.",
            staff_id=test_user.id,
        )
        assert comment.support_ticket_id == ticket.id
        assert comment.staff_id == test_user.id
        assert comment.comment == "Looking into this now."

        attachment = await service.add_attachment(
            ticket_id=ticket.id,
            filename="screenshot.png",
            file_path="/uploads/screenshot.png",
            file_size=204800,
            content_type="image/png",
            uploaded_by_staff_id=test_user.id,
        )
        assert attachment.support_ticket_id == ticket.id
        assert attachment.file_size == 204800
        assert attachment.uploaded_by_staff_id == test_user.id

        await service.assign_ticket(ticket_id=ticket.id, assigned_to_id=test_user.id)
        escalated = await service.escalate_ticket(
            ticket_id=ticket.id,
            escalation_reason="Customer is a top-tier account",
            escalated_by_id=test_user.id,
        )
        assert escalated.is_escalated is True
        assert escalated.escalation_level == 1
        assert escalated.status == TicketStatus.ON_HOLD

        resolved = await service.update_status(
            ticket_id=ticket.id,
            status=TicketStatus.RESOLVED,
            resolution_notes="Fixed the export button.",
            resolved_by_id=test_user.id,
        )
        assert resolved.resolved_by_id == test_user.id
        assert resolved.resolution_notes == "Fixed the export button."
        assert resolved.resolution_time_minutes is not None

        comments = await service.get_comments(ticket.id, include_internal=True)
        assert len(comments) == 1
        attachments = await service.get_attachments(ticket.id)
        assert len(attachments) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
