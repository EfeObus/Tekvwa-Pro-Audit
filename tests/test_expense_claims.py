"""
Regression coverage for Finding 50's expense_claims/expense_claim_items column drift
(docs/FINDING_50_SCOPE.md, docs/REMEDIATION_LOG.md).

Before this fix, create_claim() and add_expense_item() -- the only real construction sites for
either model -- always failed with an UndefinedColumnError, since several fields they sent
(title/expense_date_from/expense_date_to/... on ExpenseClaim; vat_amount/approved_amount/
receipt_file_url/has_receipt on ExpenseClaimItem) never existed on the live tables. Separately,
submit_claim()'s FX-metadata handling silently shadowed SQLAlchemy's own reserved
`Base.metadata` attribute instead of persisting anything.
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import BusinessEntity
from app.models.expense_claims import ClaimStatus, ExpenseCategory
from app.models.user import User
from app.services.expense_claims_service import ExpenseClaimsService


async def _make_employee(db_session: AsyncSession, entity: BusinessEntity):
    from app.models.payroll import Employee

    employee = Employee(
        entity_id=entity.id,
        employee_id="EMP-001",
        first_name="Ada",
        last_name="Okafor",
        email="ada.okafor@example.com",
        hire_date=date(2024, 1, 1),
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee


class TestExpenseClaimPersistence:
    async def test_create_claim_and_add_item(
        self, db_session: AsyncSession, test_entity: BusinessEntity, test_user: User,
    ):
        employee = await _make_employee(db_session, test_entity)
        service = ExpenseClaimsService(db_session)

        claim = await service.create_claim(
            entity_id=test_entity.id,
            employee_id=employee.id,
            title="Lagos client visit",
            expense_date_from=date(2026, 9, 1),
            expense_date_to=date(2026, 9, 5),
            project_code="PRJ-01",
            cost_center="CC-SALES",
            department="Sales",
            created_by_id=test_user.id,
        )

        assert claim.id is not None
        assert claim.title == "Lagos client visit"
        assert claim.claim_date == date(2026, 9, 1)
        assert claim.project_code == "PRJ-01"
        assert claim.status == ClaimStatus.DRAFT

        item = await service.add_expense_item(
            claim_id=claim.id,
            expense_date=date(2026, 9, 2),
            category=ExpenseCategory.TRAVEL,
            description="Flight to Lagos",
            amount=Decimal("45000.00"),
            vat_amount=Decimal("3375.00"),
            receipt_file_url="https://example.com/receipts/1.pdf",
        )

        assert item.expense_claim_id == claim.id
        assert item.vat_amount == Decimal("3375.00")
        assert item.has_receipt is True
        assert item.approved_amount == Decimal("45000.00")

        await db_session.refresh(claim, attribute_names=["line_items"])
        assert claim.total_amount == Decimal("45000.00")

    async def test_submit_and_approve_fx_claim_persists_metadata(
        self, db_session: AsyncSession, test_entity: BusinessEntity, test_user: User,
    ):
        employee = await _make_employee(db_session, test_entity)
        service = ExpenseClaimsService(db_session)

        claim = await service.create_claim(
            entity_id=test_entity.id,
            employee_id=employee.id,
            title="Conference in Accra",
            expense_date_from=date(2026, 9, 10),
            expense_date_to=date(2026, 9, 12),
        )
        await service.add_expense_item(
            claim_id=claim.id,
            expense_date=date(2026, 9, 11),
            category=ExpenseCategory.TRAVEL,
            description="Hotel",
            amount=Decimal("100.00"),
        )

        submitted = await service.submit_claim(
            claim_id=claim.id, currency="USD", exchange_rate=Decimal("1"),
        )
        assert submitted.status == ClaimStatus.SUBMITTED
        assert submitted.claim_metadata is not None
        assert submitted.claim_metadata["currency"] == "USD"

        approved = await service.approve_claim(
            claim_id=claim.id, approved_by_id=test_user.id, approval_notes="Looks good",
        )
        assert approved.status == ClaimStatus.APPROVED
        assert approved.approved_by_id == test_user.id
        assert approved.approval_notes == "Looks good"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
