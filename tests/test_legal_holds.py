"""
Regression coverage for Finding 50's legal_hold.py column drift
(docs/FINDING_50_SCOPE.md, docs/REMEDIATION_LOG.md).

`LegalHold` inherited `AuditMixin` for zero reason: `app/services/legal_hold_service.py`'s real
construction site never sets AuditMixin's plain `created_by_id`/`updated_by_id` (it uses its own,
differently-named `created_by_staff_id`/`released_by_staff_id`), and the live table has no
`created_by_id`/`updated_by_id` columns at all -- both were dead weight, so `AuditMixin` was
dropped entirely (zero migration, since there was nothing to remove from the DB). `hold_type`/
`status`/`data_scope` were native SQLAlchemy enums against plain VARCHAR live columns (same
pattern already fixed in `ml_jobs`/`risk_signals` earlier this session) -- fixed to plain
`String`. `LegalHoldNotification` had a completely non-overlapping field set from the live table
(`recipient_user_id` vs. the real `recipient_email`/`recipient_name`/`acknowledged`) and was
never constructed anywhere in the codebase (genuinely dead code) -- rewritten to match the live
table exactly.
"""
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.legal_hold import DataScope, LegalHoldNotification, LegalHoldStatus, LegalHoldType
from app.models.user import User
from app.services.legal_hold_service import LegalHoldService


class TestLegalHoldPersistence:
    async def test_create_legal_hold(
        self, db_session: AsyncSession, test_organization: Organization, test_user: User,
    ):
        service = LegalHoldService(db_session)
        hold = await service.create_legal_hold(
            organization_id=test_organization.id,
            matter_name="Tax Investigation 2026",
            hold_type=LegalHoldType.TAX_INVESTIGATION,
            data_scope=DataScope.ALL_DATA,
            preservation_start_date=date(2026, 1, 1),
            created_by_id=test_user.id,
        )

        assert hold.id is not None
        assert hold.hold_number.startswith("LH-")
        assert hold.status == LegalHoldStatus.ACTIVE
        assert hold.hold_type == LegalHoldType.TAX_INVESTIGATION
        assert hold.created_by_staff_id == test_user.id


class TestLegalHoldNotificationPersistence:
    async def test_create_matches_live_table(
        self, db_session: AsyncSession, test_organization: Organization, test_user: User,
    ):
        service = LegalHoldService(db_session)
        hold = await service.create_legal_hold(
            organization_id=test_organization.id,
            matter_name="Compliance Audit 2026",
            hold_type=LegalHoldType.REGULATORY_AUDIT,
            data_scope=DataScope.ALL_DATA,
            preservation_start_date=date(2026, 1, 1),
            created_by_id=test_user.id,
        )

        notification = LegalHoldNotification(
            legal_hold_id=hold.id,
            recipient_email="admin@example.com",
            recipient_name="Test Admin",
            notification_type="hold_initiated",
        )
        db_session.add(notification)
        await db_session.commit()
        await db_session.refresh(notification)

        assert notification.id is not None
        assert notification.recipient_email == "admin@example.com"
        assert notification.acknowledged is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
