"""backfill_expense_claims_column_drift

Finding 50 (docs/FINDING_50_SCOPE.md): app/services/expense_claims_service.py's create_claim()
-- the only real construction site for ExpenseClaim -- always sent title/expense_date_from/
expense_date_to/project_code/cost_center/department, and approve_claim()/reject_claim() set
approved_by_id/rejected_by_id/approval_notes directly, none of which existed on the live table
(which instead has claim_date/approved_by/rejected_by/notes) -- every real call has always failed
with an UndefinedColumnError. Also adds claim_metadata (submit_claim() previously wrote FX
metadata to `claim.metadata`, which silently shadows SQLAlchemy's own reserved `Base.metadata`
class attribute at the instance level without ever persisting -- renamed to claim_metadata and
given a real column here). This table is confirmed structurally unable to hold a row under the
pre-fix code, so no backfill is needed for anything added here.

Revision ID: 3f637da4ead5
Revises: 3a1c0b05fc35
Create Date: 2026-09-20 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '3f637da4ead5'
down_revision: Union[str, None] = '3a1c0b05fc35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('expense_claims', sa.Column('title', sa.String(length=200), nullable=False))
    op.add_column('expense_claims', sa.Column('expense_date_from', sa.Date(), nullable=False))
    op.add_column('expense_claims', sa.Column('expense_date_to', sa.Date(), nullable=False))
    op.add_column('expense_claims', sa.Column('approved_amount', sa.Numeric(precision=15, scale=2), server_default='0', nullable=False))
    op.add_column('expense_claims', sa.Column('approval_notes', sa.Text(), nullable=True))
    op.add_column('expense_claims', sa.Column('payment_method', sa.String(length=50), nullable=True))
    op.add_column('expense_claims', sa.Column('project_code', sa.String(length=50), nullable=True))
    op.add_column('expense_claims', sa.Column('cost_center', sa.String(length=50), nullable=True))
    op.add_column('expense_claims', sa.Column('department', sa.String(length=100), nullable=True))
    op.add_column('expense_claims', sa.Column('approved_by_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('expense_claims', sa.Column('rejected_by_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('expense_claims', sa.Column('claim_metadata', postgresql.JSON(), nullable=True))
    op.add_column('expense_claims', sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('expense_claims', sa.Column('updated_by_id', postgresql.UUID(as_uuid=True), nullable=True))

    op.create_foreign_key('fk_expense_claims_approved_by_id_users', 'expense_claims', 'users', ['approved_by_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_expense_claims_rejected_by_id_users', 'expense_claims', 'users', ['rejected_by_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('fk_expense_claims_rejected_by_id_users', 'expense_claims', type_='foreignkey')
    op.drop_constraint('fk_expense_claims_approved_by_id_users', 'expense_claims', type_='foreignkey')

    op.drop_column('expense_claims', 'updated_by_id')
    op.drop_column('expense_claims', 'created_by_id')
    op.drop_column('expense_claims', 'claim_metadata')
    op.drop_column('expense_claims', 'rejected_by_id')
    op.drop_column('expense_claims', 'approved_by_id')
    op.drop_column('expense_claims', 'department')
    op.drop_column('expense_claims', 'cost_center')
    op.drop_column('expense_claims', 'project_code')
    op.drop_column('expense_claims', 'payment_method')
    op.drop_column('expense_claims', 'approval_notes')
    op.drop_column('expense_claims', 'approved_amount')
    op.drop_column('expense_claims', 'expense_date_to')
    op.drop_column('expense_claims', 'expense_date_from')
    op.drop_column('expense_claims', 'title')
