"""
Regression coverage for Finding 50's risk_signal.py column drift
(docs/FINDING_50_SCOPE.md, docs/REMEDIATION_LOG.md).

app/services/risk_signal_service.py's create_risk_signal() (the only real construction site)
already used auto_detected/detected_by_id/ml_model_id/evidence/recommended_actions and set
requires_immediate_action directly on the instance -- none of which existed on the old model
(which instead had a differently-named, non-overlapping field set: user_id/detection_source/
evidence_data/assigned_at/escalated*/parent_signal_id/auto_resolved/potential_impact_amount, all
with zero real usage and no matching live column). The live table already had every column the
service needed -- a pure model rewrite, zero migration. Also fixes a guaranteed AttributeError in
_calculate_risk_score(), which referenced RiskCategory.REPUTATIONAL and RiskCategory.PERFORMANCE,
neither of which existed on the enum -- every create_risk_signal() call omitting an explicit
risk_score (i.e. nearly every real call) has always crashed. RiskSignalComment's real construction
site used staff_id, not the model's author_id, and never set is_internal.
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.user import User
from app.models.risk_signal import RiskCategory, RiskSeverity, RiskSignalType, RiskStatus
from app.services.risk_signal_service import RiskSignalService


class TestRiskSignalPersistence:
    async def test_create_signal_without_explicit_risk_score(
        self, db_session: AsyncSession, test_organization: Organization,
    ):
        """This is the exact path that always crashed on RiskCategory.REPUTATIONAL."""
        service = RiskSignalService(db_session)
        signal = await service.create_risk_signal(
            organization_id=test_organization.id,
            signal_type=RiskSignalType.UNUSUAL_TRANSACTION_VOLUME,
            category=RiskCategory.FINANCIAL,
            severity=RiskSeverity.HIGH,
            title="Unusual transaction volume detected",
            description="Transaction count spiked 400% over the trailing 7-day average.",
            auto_detected=True,
            evidence={"baseline": 50, "observed": 210},
            recommended_actions=["Review recent transactions", "Contact organization admin"],
        )

        assert signal.id is not None
        assert signal.signal_code.startswith("RS-")
        assert signal.risk_score is not None
        assert signal.auto_detected is True
        assert signal.evidence == {"baseline": 50, "observed": 210}
        assert signal.requires_immediate_action is False

    async def test_reputational_and_performance_categories_score(
        self, db_session: AsyncSession, test_organization: Organization,
    ):
        service = RiskSignalService(db_session)
        signal = await service.create_risk_signal(
            organization_id=test_organization.id,
            signal_type=RiskSignalType.SYSTEM_ERROR_SPIKE,
            category=RiskCategory.PERFORMANCE,
            severity=RiskSeverity.CRITICAL,
            title="Platform latency spike",
            description="P95 API latency exceeded 5s for 10 consecutive minutes.",
        )

        assert signal.risk_score is not None
        assert signal.requires_immediate_action is True

    async def test_acknowledge_assign_and_resolve_lifecycle(
        self, db_session: AsyncSession, test_organization: Organization, test_user: User,
    ):
        service = RiskSignalService(db_session)
        signal = await service.create_risk_signal(
            organization_id=test_organization.id,
            signal_type=RiskSignalType.SUSPICIOUS_LOGIN,
            category=RiskCategory.SECURITY,
            severity=RiskSeverity.HIGH,
            title="Suspicious login pattern",
            description="Multiple failed logins from distinct geographies within 5 minutes.",
        )

        acknowledged = await service.acknowledge_signal(signal.id, acknowledged_by_id=test_user.id)
        assert acknowledged.acknowledged is True
        assert acknowledged.acknowledged_by_id == test_user.id

        assigned = await service.assign_signal(
            signal.id, assigned_to_id=test_user.id, assigned_by_id=test_user.id,
        )
        assert assigned.assigned_to_id == test_user.id
        assert assigned.status == RiskStatus.ACKNOWLEDGED

        resolved = await service.update_signal_status(
            signal.id,
            status=RiskStatus.RESOLVED,
            resolution_notes="Confirmed false alarm from a VPN exit node change.",
            resolved_by_id=test_user.id,
        )
        assert resolved.status == RiskStatus.RESOLVED
        assert resolved.resolved_at is not None
        assert resolved.resolution_notes == "Confirmed false alarm from a VPN exit node change."

    async def test_get_signals_by_category(
        self, db_session: AsyncSession, test_organization: Organization,
    ):
        service = RiskSignalService(db_session)
        await service.create_risk_signal(
            organization_id=test_organization.id,
            signal_type=RiskSignalType.REVENUE_DECLINE,
            category=RiskCategory.CHURN,
            severity=RiskSeverity.MEDIUM,
            title="Revenue decline",
            description="MRR dropped 12% month over month.",
        )

        by_category = await service.get_signals_by_category()
        assert by_category == {"churn": 1}


class TestRiskSignalCommentPersistence:
    async def test_add_comment_uses_staff_id(
        self, db_session: AsyncSession, test_organization: Organization, test_user: User,
    ):
        service = RiskSignalService(db_session)
        signal = await service.create_risk_signal(
            organization_id=test_organization.id,
            signal_type=RiskSignalType.DATA_SYNC_ERROR,
            category=RiskCategory.OPERATIONAL,
            severity=RiskSeverity.LOW,
            title="Data sync error",
            description="Nightly sync job failed for one tenant.",
        )

        comment = await service.add_comment(
            signal_id=signal.id,
            comment_text="Retried the sync job manually, succeeded.",
            staff_id=test_user.id,
        )

        assert comment.id is not None
        assert comment.staff_id == test_user.id
        assert comment.risk_signal_id == signal.id


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
