"""
Regression coverage for Finding 50's payroll_runs column drift
(docs/FINDING_50_SCOPE.md, docs/REMEDIATION_LOG.md).

Like `payslips`, this table wasn't crashing -- the live table has `is_locked`/`locked_at` that the
model never mapped, and nothing in payroll_service.py currently sets them. Added both for
completeness, matching the same "close the latent trap before someone hits it" reasoning used for
payslips. Zero migration needed.
"""
from datetime import date, datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import BusinessEntity
from app.models.payroll import PayrollFrequency, PayrollRun, PayrollStatus


class TestPayrollRunPersistence:
    async def test_lock_fields_round_trip(
        self, db_session: AsyncSession, test_entity: BusinessEntity,
    ):
        run = PayrollRun(
            entity_id=test_entity.id,
            payroll_code="PAY-2026-LOCK1",
            name="September 2026 Payroll",
            frequency=PayrollFrequency.MONTHLY.value,
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
            payment_date=date(2026, 9, 28),
            status=PayrollStatus.DRAFT.value,
        )
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)

        assert run.is_locked is False

        run.is_locked = True
        run.locked_at = datetime.now(timezone.utc)
        await db_session.commit()
        await db_session.refresh(run)

        assert run.is_locked is True
        assert run.locked_at is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
