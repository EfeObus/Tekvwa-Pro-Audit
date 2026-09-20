"""backfill_bank_statement_transactions_column_drift

Finding 50 (docs/FINDING_50_SCOPE.md): all 4 real construction sites of BankStatementTransaction
(app/services/bank_integration_service.py's Mono/Okra/Stitch importers, and
app/services/bank_reconciliation_service.py's import_statement_transactions()) each passed at
least one keyword argument that existed on neither the model nor the live table -- every bank
statement import path has always crashed with TypeError before ever reaching the DB, so this
table is confirmed structurally unable to hold a row under the pre-fix code. Most of the drift
(bank_account_id/narration/transaction_type/channel/posted_date/reversal_reason/source/
external_id) was model-only-missing (the DB already had these; no migration needed for them).
This migration adds the columns that existed on neither side: description (a cleaned, user-facing
description distinct from raw_narration, needed by import_statement_transactions()),
reconciliation_id/import_id (needed by the same function to link imported transactions back to a
reconciliation/import batch), charge_detection_method (needed by the same function's manual
charge-detection branch), and match_status (the model's existing, far-more-used richer status
enum -- 10+ call sites in bank_reconciliation_service.py vs. 3 for the DB's plain is_matched
boolean, which stays in place unmapped per this session's additive-only policy).

No backfill needed for any column here -- the table cannot have any existing rows.

Revision ID: 367e1f63c047
Revises: 92e487a0d264
Create Date: 2026-09-20 13:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '367e1f63c047'
down_revision: Union[str, None] = '92e487a0d264'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('bank_statement_transactions', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('bank_statement_transactions', sa.Column('reconciliation_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('bank_statement_transactions', sa.Column('import_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('bank_statement_transactions', sa.Column('charge_detection_method', sa.String(length=50), nullable=True))
    op.add_column('bank_statement_transactions', sa.Column('match_status', sa.String(length=20), server_default='unmatched', nullable=False))

    op.create_foreign_key('bank_statement_transactions_reconciliation_id_fkey', 'bank_statement_transactions', 'bank_reconciliations', ['reconciliation_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('bank_statement_transactions_import_id_fkey', 'bank_statement_transactions', 'bank_statement_imports', ['import_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('bank_statement_transactions_import_id_fkey', 'bank_statement_transactions', type_='foreignkey')
    op.drop_constraint('bank_statement_transactions_reconciliation_id_fkey', 'bank_statement_transactions', type_='foreignkey')

    op.drop_column('bank_statement_transactions', 'match_status')
    op.drop_column('bank_statement_transactions', 'charge_detection_method')
    op.drop_column('bank_statement_transactions', 'import_id')
    op.drop_column('bank_statement_transactions', 'reconciliation_id')
    op.drop_column('bank_statement_transactions', 'description')
