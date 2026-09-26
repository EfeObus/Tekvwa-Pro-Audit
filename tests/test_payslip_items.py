"""
Regression coverage for Finding 50's payslip_items column drift
(docs/FINDING_50_SCOPE.md, docs/REMEDIATION_LOG.md).

`PayslipItem` inherits `BaseModel`, which always adds a NOT NULL `updated_at` with a server
default -- the live table only had `created_at`, so every payslip item creation has always failed
with an UndefinedColumnError. Migration 553f1e5fc3cc adds it.
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import BusinessEntity
from app.models.payroll import (
    Employee,
    PayItemCategory,
    PayItemType,
    PayrollFrequency,
    PayrollRun,
    PayrollStatus,
    Payslip,
    PayslipItem,
)


class TestPayslipItemPersistence:
    async def test_create_has_updated_at(
        self, db_session: AsyncSession, test_entity: BusinessEntity,
    ):
        employee = Employee(
            entity_id=test_entity.id,
            employee_id="EMP-PSI1",
            first_name="Bola",
            last_name="Adeyemi",
            email="bola.adeyemi@example.com",
            hire_date=date(2024, 1, 1),
        )
        db_session.add(employee)
        await db_session.commit()
        await db_session.refresh(employee)

        run = PayrollRun(
            entity_id=test_entity.id,
            payroll_code="PAY-2026-PSI1",
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

        payslip = Payslip(
            payroll_run_id=run.id,
            employee_id=employee.id,
            payslip_number="PS-2026-09-PSI1",
        )
        db_session.add(payslip)
        await db_session.commit()
        await db_session.refresh(payslip)

        item = PayslipItem(
            payslip_id=payslip.id,
            item_type=PayItemType.EARNING.value,
            category=PayItemCategory.HOUSING_ALLOWANCE.value,
            name="Housing Allowance",
            amount=Decimal("20000.00"),
            is_taxable=True,
            is_pensionable=True,
            sort_order=1,
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        assert item.id is not None
        assert item.updated_at is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
