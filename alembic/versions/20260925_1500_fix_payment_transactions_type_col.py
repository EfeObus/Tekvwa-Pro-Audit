"""fix_payment_transactions_transaction_type_column

Finding 50 (docs/FINDING_50_SCOPE.md): app/services/billing_service.py's two real construction
sites for PaymentTransaction (create_payment_intent, and the invoice-payment webhook handler)
always passed transaction_type="payment" or "subscription" -- but the live column's type is the
Postgres enum `transactiontype`, shared with the unrelated accounting Transaction model, whose
only members are INCOME/EXPENSE. Every real insert has always failed with
`invalid input value for enum transactiontype`. Also confirmed structurally unable to hold a row
independently: the old model had a NOT-NULL `initiated_at` column with a Python-side default that
doesn't exist on the live table at all, so every insert attempt already failed before reaching the
transaction_type value. Fixes the column's type to VARCHAR(50), matching this same table's
sibling columns (tier, billing_cycle, intelligence_addon), which this file's own inline comment
says were deliberately converted from enum to VARCHAR "for flexibility" -- transaction_type was
evidently meant to get the same treatment and didn't. The shared `transactiontype` enum type
itself is left untouched (still used by the unrelated `transactions.transaction_type` column).

No other DB changes needed for this table: `fee_kobo`, `card_bank`, `tenant_sku_id`, `channel`,
`card_exp_month`, `card_exp_year`, `card_brand`, `customer_email`, `customer_code`,
`callback_url`, `paid_at`, `verified_at`, `failed_at`, `error_code`, `error_message`,
`retry_count`, and `notes` already existed on the live table and were simply unmapped in the
model (fixed there, not here); `initiated_at`, `completed_at`, `expires_at`, and `user_agent` were
phantom model-only fields with no live column at all (removed from the model, not added here).

Revision ID: b4aa55783317
Revises: 01cf410e050d
Create Date: 2026-09-25 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4aa55783317'
down_revision: Union[str, None] = '01cf410e050d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE payment_transactions "
        "ALTER COLUMN transaction_type TYPE VARCHAR(50) USING transaction_type::text"
    )
    op.execute(
        "ALTER TABLE payment_transactions "
        "ALTER COLUMN transaction_type SET DEFAULT 'subscription'"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE payment_transactions "
        "ALTER COLUMN transaction_type DROP DEFAULT"
    )
    op.execute(
        "ALTER TABLE payment_transactions "
        "ALTER COLUMN transaction_type TYPE transactiontype USING transaction_type::transactiontype"
    )
