"""backfill_bank_reconciliations_column_drift

Finding 50 (docs/FINDING_50_SCOPE.md): bank_reconciliations was the deepest single-table drift
case found in this remediation pass. The comprehensive migration
(20260118_1200_bank_reconciliation_comprehensive.py) already gave the live table the correct
entity_id/statement_ending_balance/ledger_ending_balance/Nigerian-totals/statistics/prepared-review
shape -- the model was the thing out of sync (it declared a nonexistent
statement_opening_balance/statement_closing_balance/book_opening_balance/book_closing_balance
quartet instead, and had no entity_id at all). That side of the fix is model-only, no migration
needed. This migration adds the columns that existed on NEITHER side but that
app/services/bank_reconciliation_service.py already reads/writes (silently lost on every commit
until now): reference, submitted_at/submitted_by_id, rejected_at/rejected_by_id/rejection_reason
(rejection_reason already existed in the DB, only reference/submitted_*/rejected_*/reopened_*/
approval_notes/completed_*/outstanding_items/created_by_id/updated_by_id are new here).

The table is confirmed structurally unable to hold any row under the code as it existed before
this fix (entity_id was NOT NULL with no default and never set by the only INSERT path in the
codebase, app/services/bank_reconciliation_service.py's create_reconciliation) -- so there is no
backfill concern for any column added here.

Revision ID: 12da478532fe
Revises: d0fd664030a3
Create Date: 2026-09-20 12:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '12da478532fe'
down_revision: Union[str, None] = 'd0fd664030a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('bank_reconciliations', sa.Column('reference', sa.String(length=100), nullable=True))
    op.add_column('bank_reconciliations', sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('bank_reconciliations', sa.Column('submitted_by_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('bank_reconciliations', sa.Column('rejected_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('bank_reconciliations', sa.Column('rejected_by_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('bank_reconciliations', sa.Column('reopened_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('bank_reconciliations', sa.Column('reopened_by_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('bank_reconciliations', sa.Column('approval_notes', sa.Text(), nullable=True))
    op.add_column('bank_reconciliations', sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('bank_reconciliations', sa.Column('completed_by_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('bank_reconciliations', sa.Column('outstanding_items', postgresql.JSON(), nullable=True))
    op.add_column('bank_reconciliations', sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('bank_reconciliations', sa.Column('updated_by_id', postgresql.UUID(as_uuid=True), nullable=True))

    op.create_foreign_key('bank_reconciliations_submitted_by_id_fkey', 'bank_reconciliations', 'users', ['submitted_by_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('bank_reconciliations_rejected_by_id_fkey', 'bank_reconciliations', 'users', ['rejected_by_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('bank_reconciliations_reopened_by_id_fkey', 'bank_reconciliations', 'users', ['reopened_by_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('bank_reconciliations_completed_by_id_fkey', 'bank_reconciliations', 'users', ['completed_by_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('bank_reconciliations_completed_by_id_fkey', 'bank_reconciliations', type_='foreignkey')
    op.drop_constraint('bank_reconciliations_reopened_by_id_fkey', 'bank_reconciliations', type_='foreignkey')
    op.drop_constraint('bank_reconciliations_rejected_by_id_fkey', 'bank_reconciliations', type_='foreignkey')
    op.drop_constraint('bank_reconciliations_submitted_by_id_fkey', 'bank_reconciliations', type_='foreignkey')

    op.drop_column('bank_reconciliations', 'updated_by_id')
    op.drop_column('bank_reconciliations', 'created_by_id')
    op.drop_column('bank_reconciliations', 'outstanding_items')
    op.drop_column('bank_reconciliations', 'completed_by_id')
    op.drop_column('bank_reconciliations', 'completed_at')
    op.drop_column('bank_reconciliations', 'approval_notes')
    op.drop_column('bank_reconciliations', 'reopened_by_id')
    op.drop_column('bank_reconciliations', 'reopened_at')
    op.drop_column('bank_reconciliations', 'rejected_by_id')
    op.drop_column('bank_reconciliations', 'rejected_at')
    op.drop_column('bank_reconciliations', 'submitted_by_id')
    op.drop_column('bank_reconciliations', 'submitted_at')
    op.drop_column('bank_reconciliations', 'reference')
