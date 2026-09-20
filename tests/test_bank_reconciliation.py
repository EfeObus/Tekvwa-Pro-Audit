"""
Regression coverage for Finding 50's bank_reconciliations column drift
(docs/FINDING_50_SCOPE.md, docs/REMEDIATION_LOG.md).

Before this fix, POST /reconciliations crashed on its first line
(BankReconciliationCreate has no statement_opening_balance attribute), and even a direct
service-level call would have violated the live table's NOT NULL entity_id constraint, since
the model never declared entity_id at all. submit_for_review()/reject_reconciliation() also
referenced ReconciliationStatus.IN_REVIEW, a member that existed on neither of the file's two
(duplicate, shadowing) enum definitions.
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_reconciliation import BankAccount, BankAccountType, ReconciliationStatus
from app.models.entity import BusinessEntity
from app.models.user import User
from app.services.bank_reconciliation_service import get_bank_reconciliation_service


async def _make_bank_account(db_session: AsyncSession, entity: BusinessEntity) -> BankAccount:
    account = BankAccount(
        entity_id=entity.id,
        bank_name="GTBank",
        account_name="Operating Account",
        account_number="0123456789",
        account_type=BankAccountType.CURRENT,
        currency="NGN",
    )
    db_session.add(account)
    await db_session.commit()
    await db_session.refresh(account)
    return account


class TestBankReconciliationPersistence:
    """Regression coverage for Finding 50's BankReconciliation column drift."""

    async def test_create_reconciliation(
        self, db_session: AsyncSession, test_entity: BusinessEntity, test_user: User,
    ):
        account = await _make_bank_account(db_session, test_entity)
        service = get_bank_reconciliation_service(db_session)

        recon = await service.create_reconciliation(
            entity_id=test_entity.id,
            bank_account_id=account.id,
            reconciliation_date=date.today(),
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
            statement_ending_balance=Decimal("50000.00"),
            ledger_ending_balance=Decimal("49500.00"),
            reference="RECON-SEP-2026",
            created_by_id=test_user.id,
        )

        assert recon.id is not None
        assert recon.entity_id == test_entity.id
        assert recon.statement_ending_balance == Decimal("50000.00")
        assert recon.ledger_ending_balance == Decimal("49500.00")
        assert recon.difference == Decimal("500.00")
        assert recon.status == ReconciliationStatus.DRAFT
        assert recon.reference == "RECON-SEP-2026"

    async def test_submit_approve_and_reject_workflow(
        self, db_session: AsyncSession, test_entity: BusinessEntity, test_user: User,
    ):
        account = await _make_bank_account(db_session, test_entity)
        service = get_bank_reconciliation_service(db_session)

        recon = await service.create_reconciliation(
            entity_id=test_entity.id,
            bank_account_id=account.id,
            reconciliation_date=date.today(),
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
            statement_ending_balance=Decimal("50000.00"),
            ledger_ending_balance=Decimal("50000.00"),
        )
        assert recon.difference == Decimal("0.00")

        submitted = await service.submit_for_review(
            reconciliation_id=recon.id, submitted_by_id=test_user.id,
        )
        assert submitted.status == ReconciliationStatus.PENDING_REVIEW
        assert submitted.submitted_at is not None
        assert submitted.submitted_by_id == test_user.id

        rejected = await service.reject_reconciliation(
            reconciliation_id=recon.id, rejected_by_id=test_user.id, reason="Balances need review",
        )
        assert rejected.status == ReconciliationStatus.REJECTED
        assert rejected.rejected_at is not None
        assert rejected.rejected_by_id == test_user.id
        assert rejected.rejection_reason == "Balances need review"

        reopened = await service.reopen_reconciliation(
            reconciliation_id=recon.id, reopened_by_id=test_user.id,
        )
        assert reopened.status == ReconciliationStatus.DRAFT
        assert reopened.rejected_at is None
        assert reopened.rejection_reason is None

        submitted_again = await service.submit_for_review(
            reconciliation_id=recon.id, submitted_by_id=test_user.id,
        )
        assert submitted_again.status == ReconciliationStatus.PENDING_REVIEW

        approved = await service.approve_reconciliation(
            reconciliation_id=recon.id, approved_by_id=test_user.id,
        )
        assert approved.status == ReconciliationStatus.APPROVED
        assert approved.approved_at is not None
        assert approved.approved_by_id == test_user.id


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
