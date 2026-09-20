"""
Regression coverage for Finding 50's bank_accounts/bank_reconciliations column drift
(docs/FINDING_50_SCOPE.md, docs/REMEDIATION_LOG.md).

Before this fix, POST /reconciliations crashed on its first line
(BankReconciliationCreate has no statement_opening_balance attribute), and even a direct
service-level call would have violated the live table's NOT NULL entity_id constraint, since
the model never declared entity_id at all. submit_for_review()/reject_reconciliation() also
referenced ReconciliationStatus.IN_REVIEW, a member that existed on neither of the file's two
(duplicate, shadowing) enum definitions. POST /accounts had the same class of bug: crashing on
account_data.opening_balance_date/.notes before ever reaching the service.
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


class TestBankAccountPersistence:
    """
    Regression coverage for Finding 50's BankAccount column drift.

    Before this fix, POST /accounts crashed on its first line
    (account_data.opening_balance_date/.notes -- AttributeError, neither existed on
    BankAccountCreate), and create_bank_account() would then have hit a second crash passing
    sort_code= to the BankAccount constructor -- a field the request schema declared (along with
    swift_code/iban/branch_name/branch_address) that existed on neither the model nor the DB.
    """

    async def test_create_bank_account_with_full_schema_fields(
        self, db_session: AsyncSession, test_entity: BusinessEntity, test_user: User,
    ):
        service = get_bank_reconciliation_service(db_session)

        account = await service.create_bank_account(
            entity_id=test_entity.id,
            bank_name="GTBank",
            account_name="Operating Account",
            account_number="0123456789",
            opening_balance=Decimal("10000.00"),
            opening_balance_date=date(2026, 9, 1),
            sort_code="123456",
            swift_code="GTBINGLA",
            iban="NG21GTB0123456789012",
            branch_name="Victoria Island",
            branch_address="1 Ahmadu Bello Way, Lagos",
            is_primary=True,
            notes="Primary operating account",
            created_by_id=test_user.id,
        )

        assert account.id is not None
        assert account.entity_id == test_entity.id
        assert account.sort_code == "123456"
        assert account.swift_code == "GTBINGLA"
        assert account.iban == "NG21GTB0123456789012"
        assert account.branch_name == "Victoria Island"
        assert account.is_primary is True
        assert account.opening_balance == Decimal("10000.00")
        assert account.current_balance == Decimal("10000.00")
        assert account.notes == "Primary operating account"


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
