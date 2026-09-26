"""
Regression coverage for Finding 50's PaymentTransaction column drift
(docs/FINDING_50_SCOPE.md, docs/REMEDIATION_LOG.md).

app/services/billing_service.py's two real construction sites for PaymentTransaction
(create_payment_intent, and the invoice-payment webhook handler) always passed
transaction_type="payment"/"subscription" into a column whose live Postgres type was the
`transactiontype` enum (INCOME/EXPENSE only, shared with the unrelated accounting Transaction
model) -- every real insert has always failed with `invalid input value for enum`. The model also
had a phantom NOT-NULL `initiated_at` column with no matching live column at all, which alone
would have failed every insert before transaction_type was ever reached. These tests build the
exact object create_payment_intent() constructs (minus the real Paystack HTTP call, which isn't
mocked here) and exercise the update paths billing_service.py's webhook/verify handlers use
(paid_at/verified_at/failed_at/card_bank/fee_kobo/error_code), none of which existed on the old
model under their real names.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.sku import PaymentTransaction


class TestPaymentTransactionPersistence:
    async def test_create_matches_create_payment_intent_construction(
        self, db_session: AsyncSession, test_organization: Organization,
    ):
        """Mirrors billing_service.py's create_payment_intent() construction exactly."""
        payment_transaction = PaymentTransaction(
            organization_id=test_organization.id,
            reference="TVP-TEST0001-20260925120000",
            paystack_reference="paystack-ref-1",
            paystack_access_code="access-code-1",
            authorization_url="https://checkout.paystack.com/abc123",
            transaction_type="payment",
            status="pending",
            amount_kobo=1_500_000,
            currency="NGN",
            tier="professional",
            billing_cycle="monthly",
            intelligence_addon=None,
            additional_users=0,
            custom_metadata={"email": "admin@example.com"},
        )
        db_session.add(payment_transaction)
        await db_session.commit()
        await db_session.refresh(payment_transaction)

        assert payment_transaction.id is not None
        assert payment_transaction.transaction_type == "payment"
        assert payment_transaction.status == "pending"
        assert payment_transaction.amount_naira == 15000

    async def test_subscription_invoice_transaction_type(
        self, db_session: AsyncSession, test_organization: Organization,
    ):
        """Mirrors the invoice-payment webhook handler's construction exactly."""
        payment_tx = PaymentTransaction(
            organization_id=test_organization.id,
            reference="INV-inv_12345",
            paystack_reference="inv_12345",
            transaction_type="subscription",
            status="pending",
            amount_kobo=2_000_000,
            currency="NGN",
            paystack_invoice_id="inv_12345",
            paystack_invoice_status="pending",
            webhook_received_at=datetime.now(timezone.utc),
        )
        db_session.add(payment_tx)
        await db_session.commit()
        await db_session.refresh(payment_tx)

        assert payment_tx.transaction_type == "subscription"

    async def test_success_update_sets_paid_verified_and_card_details(
        self, db_session: AsyncSession, test_organization: Organization,
    ):
        payment_tx = PaymentTransaction(
            organization_id=test_organization.id,
            reference="TVP-TEST0002-20260925120000",
            transaction_type="payment",
            status="pending",
            amount_kobo=500_000,
            currency="NGN",
        )
        db_session.add(payment_tx)
        await db_session.commit()
        await db_session.refresh(payment_tx)

        # Mirrors _handle_charge_success()'s update path.
        payment_tx.status = "success"
        payment_tx.paid_at = datetime.now(timezone.utc)
        payment_tx.verified_at = datetime.now(timezone.utc)
        payment_tx.payment_method = "card"
        payment_tx.card_type = "visa"
        payment_tx.card_last4 = "4242"
        payment_tx.card_bank = "GTBank"
        payment_tx.fee_kobo = 5_000

        await db_session.commit()
        await db_session.refresh(payment_tx)

        assert payment_tx.status == "success"
        assert payment_tx.paid_at is not None
        assert payment_tx.verified_at is not None
        assert payment_tx.card_bank == "GTBank"
        assert payment_tx.fee_naira == 50

    async def test_failure_update_sets_failed_at_and_error_code(
        self, db_session: AsyncSession, test_organization: Organization,
    ):
        payment_tx = PaymentTransaction(
            organization_id=test_organization.id,
            reference="TVP-TEST0003-20260925120000",
            transaction_type="payment",
            status="pending",
            amount_kobo=500_000,
            currency="NGN",
        )
        db_session.add(payment_tx)
        await db_session.commit()
        await db_session.refresh(payment_tx)

        # Mirrors verify_payment()'s failure branch.
        payment_tx.status = "failed"
        payment_tx.failed_at = datetime.now(timezone.utc)
        payment_tx.error_message = "Insufficient funds"
        payment_tx.error_code = "PAYMENT_FAILED"

        await db_session.commit()
        await db_session.refresh(payment_tx)

        assert payment_tx.status == "failed"
        assert payment_tx.failed_at is not None
        assert payment_tx.error_code == "PAYMENT_FAILED"
        assert payment_tx.error_message == "Insufficient funds"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
