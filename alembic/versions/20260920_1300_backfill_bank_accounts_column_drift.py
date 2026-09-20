"""backfill_bank_accounts_column_drift

Finding 50 (docs/FINDING_50_SCOPE.md): bank_accounts had the same class of problem as
bank_reconciliations. POST /accounts crashed on its first line (account_data.opening_balance_date/
.notes -- AttributeError, neither existed on BankAccountCreate) before ever reaching the service,
and the service's own create_bank_account() would then have hit a second crash passing sort_code=
to the BankAccount constructor -- a field app/schemas/bank_reconciliation.py's BankAccountBase
already declared (along with swift_code/iban/branch_name/branch_address), none of which existed on
the model or the live table. The comprehensive migration
(20260118_1200_bank_reconciliation_comprehensive.py) had DDL for exactly these columns, but it was
gated behind an "IF NOT EXISTS (table)" check that never fired, since bank_accounts already existed
from the earlier 20260108_2030 migration -- so this intended shape never actually reached
production. This migration adds them for real, plus the other model-only columns
(opening_balance/opening_balance_date/is_primary/notes/api_enabled/api_credentials/gl_account_name/
created_by_id/updated_by_id) that existed on the model but not the DB.

Like bank_reconciliations, this table is confirmed structurally unable to hold any row under the
pre-fix code (create_bank_account is the only construction path in the codebase, and it was
unreachable), so no backfill is needed for any column added here.

Revision ID: 92e487a0d264
Revises: 12da478532fe
Create Date: 2026-09-20 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '92e487a0d264'
down_revision: Union[str, None] = '12da478532fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('bank_accounts', sa.Column('sort_code', sa.String(length=20), nullable=True))
    op.add_column('bank_accounts', sa.Column('swift_code', sa.String(length=11), nullable=True))
    op.add_column('bank_accounts', sa.Column('iban', sa.String(length=34), nullable=True))
    op.add_column('bank_accounts', sa.Column('branch_name', sa.String(length=200), nullable=True))
    op.add_column('bank_accounts', sa.Column('branch_address', sa.Text(), nullable=True))
    op.add_column('bank_accounts', sa.Column('gl_account_name', sa.String(length=100), nullable=True))
    op.add_column('bank_accounts', sa.Column('opening_balance', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('bank_accounts', sa.Column('opening_balance_date', sa.Date(), nullable=True))
    op.add_column('bank_accounts', sa.Column('is_primary', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('bank_accounts', sa.Column('notes', sa.Text(), nullable=True))
    op.add_column('bank_accounts', sa.Column('api_enabled', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('bank_accounts', sa.Column('api_credentials', postgresql.JSON(), nullable=True))
    op.add_column('bank_accounts', sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('bank_accounts', sa.Column('updated_by_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('bank_accounts', sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('bank_accounts', 'last_sync_at')
    op.drop_column('bank_accounts', 'updated_by_id')
    op.drop_column('bank_accounts', 'created_by_id')
    op.drop_column('bank_accounts', 'api_credentials')
    op.drop_column('bank_accounts', 'api_enabled')
    op.drop_column('bank_accounts', 'notes')
    op.drop_column('bank_accounts', 'is_primary')
    op.drop_column('bank_accounts', 'opening_balance_date')
    op.drop_column('bank_accounts', 'opening_balance')
    op.drop_column('bank_accounts', 'gl_account_name')
    op.drop_column('bank_accounts', 'branch_address')
    op.drop_column('bank_accounts', 'branch_name')
    op.drop_column('bank_accounts', 'iban')
    op.drop_column('bank_accounts', 'swift_code')
    op.drop_column('bank_accounts', 'sort_code')
