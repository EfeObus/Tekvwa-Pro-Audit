"""backfill_budgets_column_drift

Finding 50 (docs/FINDING_50_SCOPE.md): budget_service.py and app/routers/budget.py consistently
construct/read Budget using description/total_revenue_budget/total_expense_budget/
total_capex_budget - none of which exist on the live table (which has notes/total_revenue/
total_expense instead, and no capex concept at all). Confirmed via grep that Budget.description is
the real usage (not Budget.notes, which nothing references - only the unrelated
BudgetLineItem.notes is used elsewhere) and total_revenue_budget/total_expense_budget/
total_capex_budget are used extensively (variance calculations, summary reporting, revision
copying). Migrating the database to match the model+code here (option (A)), not the reverse -
create_budget() and every revenue/expense/capex variance calculation already depend on this shape.

Revision ID: to be filled by alembic
Revises: 3022ef79bed9
Create Date: 2026-09-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a17c9e5f2b3d'
down_revision: Union[str, None] = '3022ef79bed9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('budgets', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('budgets', sa.Column('total_revenue_budget', sa.Numeric(18, 2), nullable=True, server_default='0'))
    op.add_column('budgets', sa.Column('total_expense_budget', sa.Numeric(18, 2), nullable=True, server_default='0'))
    op.add_column('budgets', sa.Column('total_capex_budget', sa.Numeric(18, 2), nullable=True, server_default='0'))

    # Backfill from the old columns for any existing rows. total_capex_budget has no prior source,
    # so it starts at 0 for existing rows (matching its own default). Safe no-op if empty.
    op.execute("""
        UPDATE budgets SET
            total_revenue_budget = total_revenue,
            total_expense_budget = total_expense
    """)

    # notes remains in place, unmapped by the model going forward - nothing in the codebase reads
    # or writes Budget.notes (only the unrelated BudgetLineItem.notes is used elsewhere).


def downgrade() -> None:
    op.drop_column('budgets', 'total_capex_budget')
    op.drop_column('budgets', 'total_expense_budget')
    op.drop_column('budgets', 'total_revenue_budget')
    op.drop_column('budgets', 'description')
