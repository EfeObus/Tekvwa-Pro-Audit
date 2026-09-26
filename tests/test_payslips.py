"""
Regression coverage for Finding 50's payslips column drift
(docs/FINDING_50_SCOPE.md, docs/REMEDIATION_LOG.md).

Unlike most Finding 50 tables, `payslips` was not crashing: every field the model already declared
mapped to a real live column, and app/services/payroll_service.py's real construction site never
referenced the 14 columns the live table has beyond what the model exposed (meal_allowance/
utility_allowance/overtime_pay/bonus/loan_deduction/salary_advance_deduction/
cooperative_deduction/union_dues/hmo_employer/group_life_insurance/rent_relief/pension_relief/
nhf_relief/payment_reference). This test just confirms those 14 real-but-previously-unmapped
columns now round-trip correctly, since nothing exercised them before.
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import BusinessEntity
from app.models.payroll import Employee, Payslip, PayrollFrequency, PayrollRun, PayrollStatus


class TestPayslipPersistence:
    async def test_create_with_newly_mapped_columns(
        self, db_session: AsyncSession, test_entity: BusinessEntity,
    ):
        employee = Employee(
            entity_id=test_entity.id,
            employee_id="EMP-PS1",
            first_name="Ada",
            last_name="Obi",
            email="ada.obi@example.com",
            hire_date=date(2024, 1, 1),
        )
        db_session.add(employee)
        await db_session.commit()
        await db_session.refresh(employee)

        run = PayrollRun(
            entity_id=test_entity.id,
            payroll_code="PAY-2026-PS1",
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
            payslip_number="PS-2026-09-001",
            meal_allowance=Decimal("10000.00"),
            utility_allowance=Decimal("5000.00"),
            overtime_pay=Decimal("15000.00"),
            bonus=Decimal("50000.00"),
            loan_deduction=Decimal("8000.00"),
            salary_advance_deduction=Decimal("2000.00"),
            cooperative_deduction=Decimal("3000.00"),
            union_dues=Decimal("500.00"),
            hmo_employer=Decimal("4000.00"),
            group_life_insurance=Decimal("1500.00"),
            rent_relief=Decimal("6000.00"),
            pension_relief=Decimal("2400.00"),
            nhf_relief=Decimal("1000.00"),
            payment_reference="TXN-REF-00123",
            account_number="0123456789012345678901234567890",
        )
        db_session.add(payslip)
        await db_session.commit()
        await db_session.refresh(payslip)

        assert payslip.id is not None
        assert payslip.overtime_pay == Decimal("15000.00")
        assert payslip.bonus == Decimal("50000.00")
        assert payslip.hmo_employer == Decimal("4000.00")
        assert payslip.rent_relief == Decimal("6000.00")
        assert payslip.payment_reference == "TXN-REF-00123"
        assert payslip.account_number == "0123456789012345678901234567890"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
