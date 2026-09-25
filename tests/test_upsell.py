"""
Regression coverage for Finding 50's upsell.py column drift
(docs/FINDING_50_SCOPE.md, docs/REMEDIATION_LOG.md).

app/services/upsell_service.py -- the only real construction site for both models in this file --
already used each model's real field names (signal, current_product, target_product, signal_data,
confidence_score, auto_detected, next_action, next_action_date), none of which existed on the
model. The live tables already matched the service's usage exactly, so this was a pure model
rewrite (Direction B, zero migration). Two independent behavioral bugs were also found and fixed
along the way: `update_status()` wrote the same value into `won_amount` twice instead of setting
`actual_mrr_increase` and `actual_arr_increase` separately (and `won_amount` isn't a real column at
all), and `get_upsell_stats()`'s "won MRR this month" query summed the same phantom column.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.upsell import UpsellPriority, UpsellSignal, UpsellStatus, UpsellType
from app.models.user import User
from app.services.upsell_service import UpsellService


class TestUpsellOpportunityPersistence:
    async def test_create_and_fetch(
        self, db_session: AsyncSession, test_organization: Organization, test_user: User,
    ):
        service = UpsellService(db_session)
        opportunity = await service.create_opportunity(
            organization_id=test_organization.id,
            upsell_type=UpsellType.TIER_UPGRADE,
            signal=UpsellSignal.USAGE_NEAR_LIMIT,
            priority=UpsellPriority.HOT,
            title="Upgrade to Professional",
            description="Organization is hitting the Core tier's entity limit.",
            estimated_mrr_increase=Decimal("15000.00"),
            current_product="core",
            target_product="professional",
            signal_data={"entities_used": 3, "entity_limit": 3},
            confidence_score=82.5,
            auto_detected=True,
        )

        assert opportunity.id is not None
        assert opportunity.opportunity_code.startswith("UPS-")
        assert opportunity.signal == UpsellSignal.USAGE_NEAR_LIMIT
        assert opportunity.current_product == "core"
        assert opportunity.target_product == "professional"
        assert opportunity.estimated_arr_increase == Decimal("180000.00")
        assert opportunity.confidence_score == 82.5

    async def test_win_sets_actual_mrr_and_arr_separately(
        self, db_session: AsyncSession, test_organization: Organization,
    ):
        service = UpsellService(db_session)
        opportunity = await service.create_opportunity(
            organization_id=test_organization.id,
            upsell_type=UpsellType.SEAT_EXPANSION,
            signal=UpsellSignal.HIGH_ENGAGEMENT,
            priority=UpsellPriority.WARM,
            title="Add 5 more seats",
            description="Team has been inviting users past the seat limit repeatedly.",
            estimated_mrr_increase=Decimal("5000.00"),
        )

        won = await service.update_status(
            opportunity_id=opportunity.id,
            status=UpsellStatus.WON,
            actual_mrr_increase=Decimal("4500.00"),
        )

        assert won.status == UpsellStatus.WON
        assert won.actual_mrr_increase == Decimal("4500.00")
        assert won.actual_arr_increase == Decimal("54000.00")
        assert won.closed_at is not None

    async def test_lost_sets_reason(
        self, db_session: AsyncSession, test_organization: Organization,
    ):
        service = UpsellService(db_session)
        opportunity = await service.create_opportunity(
            organization_id=test_organization.id,
            upsell_type=UpsellType.API_UPGRADE,
            signal=UpsellSignal.SUPPORT_INQUIRY,
            priority=UpsellPriority.COOL,
            title="Higher API limits",
            description="Customer asked about API rate limits.",
            estimated_mrr_increase=Decimal("2000.00"),
        )

        lost = await service.update_status(
            opportunity_id=opportunity.id,
            status=UpsellStatus.LOST,
            lost_reason="Customer decided to stay on current plan.",
        )

        assert lost.status == UpsellStatus.LOST
        assert lost.lost_reason == "Customer decided to stay on current plan."
        assert lost.actual_mrr_increase is None

    async def test_get_upsell_stats_sums_actual_mrr_increase(
        self, db_session: AsyncSession, test_organization: Organization,
    ):
        service = UpsellService(db_session)
        opportunity = await service.create_opportunity(
            organization_id=test_organization.id,
            upsell_type=UpsellType.STORAGE_UPGRADE,
            signal=UpsellSignal.USAGE_NEAR_LIMIT,
            priority=UpsellPriority.HOT,
            title="More storage",
            description="Organization is near its storage cap.",
            estimated_mrr_increase=Decimal("3000.00"),
        )
        await service.update_status(
            opportunity_id=opportunity.id,
            status=UpsellStatus.WON,
            actual_mrr_increase=Decimal("3000.00"),
        )

        stats = await service.get_upsell_stats()

        assert stats["won_this_month"] == 1
        assert stats["won_mrr_this_month"] == 3000.0


class TestUpsellActivityPersistence:
    async def test_add_activity_updates_opportunity_next_action(
        self, db_session: AsyncSession, test_organization: Organization, test_user: User,
    ):
        service = UpsellService(db_session)
        opportunity = await service.create_opportunity(
            organization_id=test_organization.id,
            upsell_type=UpsellType.ENTITY_EXPANSION,
            signal=UpsellSignal.GROWING_BUSINESS,
            priority=UpsellPriority.WARM,
            title="Add another entity",
            description="Customer opened a new subsidiary.",
            estimated_mrr_increase=Decimal("8000.00"),
        )

        activity = await service.add_activity(
            opportunity_id=opportunity.id,
            activity_type="call",
            description="Discussed the new subsidiary's accounting needs.",
            staff_id=test_user.id,
            outcome="Interested, wants a proposal.",
            next_action="Send proposal",
            next_action_date=datetime(2026, 10, 1, tzinfo=timezone.utc),
        )

        assert activity.id is not None
        assert activity.upsell_opportunity_id == opportunity.id
        assert activity.outcome == "Interested, wants a proposal."

        refreshed = await service.get_opportunity(opportunity.id)
        assert refreshed.next_action == "Send proposal"
        assert refreshed.next_action_date == datetime(2026, 10, 1, tzinfo=timezone.utc)

        activities = await service.get_activities(opportunity.id)
        assert len(activities) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
