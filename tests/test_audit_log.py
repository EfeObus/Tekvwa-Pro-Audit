"""
Regression coverage for Finding 50's audit_logs column drift
(docs/FINDING_50_SCOPE.md, docs/REMEDIATION_LOG.md).

Separate from, and additional to, the already-known Finding 41 (target_entity_type/
target_entity_id). The model's own entity_id/user_id fields are declared Optional with comments
explicitly documenting why: "nullable for unauthenticated actions like login failures" -- but the
live columns were NOT NULL. app/routers/auth.py's failed-login handler calls
audit_service.log_action(business_entity_id=None, ..., user_id=None) with no surrounding
try/except -- every failed login attempt has always raised an unhandled NotNullViolation instead
of returning the intended 401/429 response. This test reproduces that exact call shape directly
against AuditService, without going through the auth router/lockout machinery.
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_consolidated import AuditAction
from app.models.entity import BusinessEntity
from app.models.user import User
from app.services.audit_service import AuditService


class TestAuditLogPersistence:
    async def test_log_action_with_no_entity_or_user_matches_failed_login(
        self, db_session: AsyncSession,
    ):
        """Mirrors app/routers/auth.py's failed-login audit log call exactly."""
        service = AuditService(db_session)
        audit_log = await service.log_action(
            business_entity_id=None,
            entity_type="user",
            entity_id=None,
            action=AuditAction.LOGIN_FAILED,
            user_id=None,
            new_values={
                "email": "attacker@example.com",
                "ip_address": "203.0.113.5",
                "reason": "invalid_credentials",
            },
            ip_address="203.0.113.5",
            user_agent="Mozilla/5.0",
        )

        assert audit_log.id is not None
        assert audit_log.entity_id is None
        assert audit_log.user_id is None
        assert audit_log.action == "login_failed"

    async def test_log_action_sets_target_entity_and_changes(
        self, db_session: AsyncSession, test_entity: BusinessEntity, test_user: User,
    ):
        service = AuditService(db_session)
        transaction_id = str(test_entity.id)
        audit_log = await service.log_action(
            business_entity_id=test_entity.id,
            entity_type="transaction",
            entity_id=transaction_id,
            action=AuditAction.UPDATE,
            user_id=test_user.id,
            old_values={"amount": "100.00"},
            new_values={"amount": "150.00"},
        )

        assert audit_log.id is not None
        assert audit_log.target_entity_type == "transaction"
        assert audit_log.target_entity_id == transaction_id


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
