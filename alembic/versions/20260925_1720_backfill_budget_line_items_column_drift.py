"""backfill_budget_line_items_column_drift

Finding 50 (docs/FINDING_50_SCOPE.md): app/services/budget_service.py's three real construction
sites for BudgetLineItem all set `total_budget` -- extensively read/written throughout
budget_service.py and app/routers/budget.py (dozens of references) -- but the live table has no
`total_budget` column at all. It instead has a NOT NULL, no-default `annual_amount` column the
model never references. Every BudgetLineItem creation has always failed with an
UndefinedColumnError (missing `total_budget`), and even with that fixed would have failed on the
`annual_amount` NOT NULL violation next. Also relaxes `account_code` to nullable to match the
model (one call site, `add_budget_line_item()`, allows it to be omitted).

This table is confirmed structurally unable to hold a row under the pre-fix code, so no backfill
is needed. `annual_amount` is left in place, unmapped, per this session's additive-only policy.

Revision ID: 98bdd0ac439d
Revises: 553f1e5fc3cc
Create Date: 2026-09-25 17:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '98bdd0ac439d'
down_revision: Union[str, None] = '553f1e5fc3cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('budget_line_items', sa.Column('total_budget', sa.Numeric(precision=18, scale=2), server_default='0', nullable=True))
    op.alter_column('budget_line_items', 'annual_amount', existing_type=sa.Numeric(precision=20, scale=2), nullable=True)
    op.alter_column('budget_line_items', 'account_code', existing_type=sa.String(length=20), nullable=True)


def downgrade() -> None:
    op.alter_column('budget_line_items', 'account_code', existing_type=sa.String(length=20), nullable=False)
    op.alter_column('budget_line_items', 'annual_amount', existing_type=sa.Numeric(precision=20, scale=2), nullable=False)
    op.drop_column('budget_line_items', 'total_budget')
