"""
Regression coverage for Finding 50's employee_loans/loan_repayments column drift
(docs/FINDING_50_SCOPE.md, docs/REMEDIATION_LOG.md).

Two independent, small gaps: `payroll_service.py`'s `update_loan()` always sets
`loan.updated_by_id = updated_by_id` unconditionally, but the live `employee_loans` table never
had that column at all (an earlier comment on the model had read "no FK" as "no column" -- it was
missing entirely). `LoanRepayment` inherits `BaseModel`, which always adds a NOT NULL `updated_at`
with a server default -- the live `loan_repayments` table only had `created_at`, so every
repayment creation has always failed. Migration 88bc48bd3bee adds both columns.
"""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import BusinessEntity
from app.models.payroll import Employee, LoanRepayment
from app.models.user import User
from app.services.payroll_service import PayrollService


async def _make_employee(db_session: AsyncSession, entity: BusinessEntity, staff_no: str) -> Employee:
    employee = Employee(
        entity_id=entity.id,
        employee_id=staff_no,
        first_name="Chinedu",
        last_name="Okafor",
        email=f"{staff_no.lower()}@example.com",
        hire_date=date(2024, 1, 1),
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee


class TestEmployeeLoanPersistence:
    async def test_update_loan_persists_updated_by_id(
        self, db_session: AsyncSession, test_entity: BusinessEntity, test_user: User,
    ):
        employee = await _make_employee(db_session, test_entity, "EMP-LN1")
        service = PayrollService(db_session)

        create_data = SimpleNamespace(
            loan_type="loan",
            description="Emergency loan",
            principal_amount=Decimal("100000.00"),
            interest_rate=Decimal("5.00"),
            tenure_months=6,
            start_date=date(2026, 9, 1),
            notes=None,
        )
        loan = await service.create_loan(
            entity_id=test_entity.id,
            employee_id=employee.id,
            loan_data=create_data,
            created_by_id=test_user.id,
        )

        update_data = SimpleNamespace(description="Updated note", status=None, notes=None)
        updated = await service.update_loan(
            entity_id=test_entity.id,
            loan_id=loan.id,
            loan_data=update_data,
            updated_by_id=test_user.id,
        )

        assert updated.updated_by_id == test_user.id
        assert updated.description == "Updated note"


class TestLoanRepaymentPersistence:
    async def test_repayment_has_updated_at(
        self, db_session: AsyncSession, test_entity: BusinessEntity, test_user: User,
    ):
        employee = await _make_employee(db_session, test_entity, "EMP-LN2")
        service = PayrollService(db_session)

        create_data = SimpleNamespace(
            loan_type="salary_advance",
            description="Salary advance",
            principal_amount=Decimal("50000.00"),
            interest_rate=Decimal("0.00"),
            tenure_months=1,
            start_date=date(2026, 9, 1),
            notes=None,
        )
        loan = await service.create_loan(
            entity_id=test_entity.id,
            employee_id=employee.id,
            loan_data=create_data,
            created_by_id=test_user.id,
        )

        repayment = LoanRepayment(
            loan_id=loan.id,
            repayment_date=date(2026, 9, 30),
            amount=Decimal("50000.00"),
            principal_portion=Decimal("50000.00"),
            interest_portion=Decimal("0.00"),
            balance_after=Decimal("0.00"),
            is_manual=True,
        )
        db_session.add(repayment)
        await db_session.commit()
        await db_session.refresh(repayment)

        assert repayment.id is not None
        assert repayment.updated_at is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
