"""backfill_ledger_entries_column_drift

Finding 50 (docs/FINDING_50_SCOPE.md), the opposite direction from most fixes in this finding:
LedgerEntry's model and its only real caller (ImmutableLedgerService.create_entry,
app/services/immutable_ledger.py) already agree with each other on a coherent double-entry,
hash-chained ledger design (debit_amount/credit_amount/balance/account_code/currency/entry_date/
description/reference/created_by_id, with the hash chain computed over exactly these fields) - but
the live table implements a completely different, generic audit-log shape instead
(resource_type/resource_id/action/data_snapshot/user_id/ip_address), confirmed via
alembic/versions/20260106_1600_advanced_accounting.py. Confirmed via full-codebase grep that none
of the DB-only columns are referenced anywhere in application code - they are pure dead weight
from whatever this table's design was before the actual feature was built against the model
instead. Migrating the database to match the model+service here, not the other way around, per
docs/FINDING_50_SCOPE.md's "(A) migrate DB to match model" option - fixing the model to match the
DB in this case would mean gutting the hash-chain integrity feature that's clearly the intended,
already-implemented behavior.

Revision ID: e46be79bee0f
Revises: 68893a772b64
Create Date: 2026-09-20 06:17:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e46be79bee0f'
down_revision: Union[str, None] = '68893a772b64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add every column the model expects, nullable for now.
    op.add_column('ledger_entries', sa.Column('source_type', sa.String(50), nullable=True))
    op.add_column('ledger_entries', sa.Column('source_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('ledger_entries', sa.Column('account_code', sa.String(50), nullable=True))
    op.add_column('ledger_entries', sa.Column('debit_amount', sa.Numeric(18, 2), nullable=True, server_default='0'))
    op.add_column('ledger_entries', sa.Column('credit_amount', sa.Numeric(18, 2), nullable=True, server_default='0'))
    op.add_column('ledger_entries', sa.Column('balance', sa.Numeric(18, 2), nullable=True))
    op.add_column('ledger_entries', sa.Column('currency', sa.String(3), nullable=True, server_default='NGN'))
    op.add_column('ledger_entries', sa.Column('entry_date', sa.Date(), nullable=True))
    op.add_column('ledger_entries', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('ledger_entries', sa.Column('reference', sa.String(100), nullable=True))
    op.add_column('ledger_entries', sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('ledger_entries', sa.Column('is_verified', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('ledger_entries', sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('ledger_entries', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')))

    # 2. Backfill from the old columns for any existing rows. Safe (no-op) if the table is empty.
    op.execute("""
        UPDATE ledger_entries SET
            source_type = resource_type,
            source_id = resource_id,
            entry_date = created_at::date,
            created_by_id = user_id,
            updated_at = created_at
    """)

    # 3. entry_date/source_type/source_id are NOT NULL on the model; the backfill above draws from
    #    columns that were already NOT NULL on the live table (created_at, resource_type,
    #    resource_id), guaranteeing no NULLs regardless of row count.
    op.alter_column('ledger_entries', 'entry_date', nullable=False)
    op.alter_column('ledger_entries', 'source_type', nullable=False)
    op.alter_column('ledger_entries', 'source_id', nullable=False)

    # 4. FK for created_by_id, matching the model's ForeignKey() declaration. Deliberately left
    #    nullable (not NOT NULL like the model originally implied) because user_id - what it's
    #    backfilled from - is itself nullable on the live table, so a row with no user_id can't be
    #    given one; tightening this is an explicit follow-up once production data is confirmed clean,
    #    not an assumption made either way (same reasoning as entity_groups.parent_entity_id).
    op.create_foreign_key(
        'fk_ledger_entries_created_by_id_users',
        'ledger_entries', 'users', ['created_by_id'], ['id'],
    )

    # 5. The old columns are no longer written by the model going forward, so their own NOT NULL
    #    constraints must be relaxed or every future insert violates them.
    op.alter_column('ledger_entries', 'resource_type', nullable=True)
    op.alter_column('ledger_entries', 'resource_id', nullable=True)
    op.alter_column('ledger_entries', 'action', nullable=True)
    op.alter_column('ledger_entries', 'data_snapshot', nullable=True)

    # 7. Indexes matching the model's own __table_args__ exactly (ix_ledger_entry_date,
    #    ix_ledger_source) - these reference brand-new columns, so they don't exist yet. The old
    #    ix_ledger_entries_entity_seq/ix_ledger_entries_resource indexes are dropped since the model
    #    no longer declares matching Index objects for them (uq_ledger_entity_sequence, the real
    #    uniqueness guarantee on entity_id+sequence_number, already exists and is untouched).
    op.drop_index('ix_ledger_entries_entity_seq', table_name='ledger_entries')
    op.drop_index('ix_ledger_entries_resource', table_name='ledger_entries')
    op.create_index('ix_ledger_entry_date', 'ledger_entries', ['entry_date'])
    op.create_index('ix_ledger_source', 'ledger_entries', ['source_type', 'source_id'])

    # 6. sequence_number is bigint on the live table; the model previously declared plain Integer -
    #    fixed on the model side (no DDL change needed here, already correct).


def downgrade() -> None:
    op.drop_index('ix_ledger_source', table_name='ledger_entries')
    op.drop_index('ix_ledger_entry_date', table_name='ledger_entries')
    op.create_index('ix_ledger_entries_resource', 'ledger_entries', ['resource_type', 'resource_id'])
    op.create_index('ix_ledger_entries_entity_seq', 'ledger_entries', ['entity_id', 'sequence_number'])
    op.alter_column('ledger_entries', 'data_snapshot', nullable=False)
    op.alter_column('ledger_entries', 'action', nullable=False)
    op.alter_column('ledger_entries', 'resource_id', nullable=False)
    op.alter_column('ledger_entries', 'resource_type', nullable=False)
    op.drop_constraint('fk_ledger_entries_created_by_id_users', 'ledger_entries', type_='foreignkey')
    op.alter_column('ledger_entries', 'entry_date', nullable=True)
    op.drop_column('ledger_entries', 'updated_at')
    op.drop_column('ledger_entries', 'verified_at')
    op.drop_column('ledger_entries', 'is_verified')
    op.drop_column('ledger_entries', 'created_by_id')
    op.drop_column('ledger_entries', 'reference')
    op.drop_column('ledger_entries', 'description')
    op.drop_column('ledger_entries', 'entry_date')
    op.drop_column('ledger_entries', 'currency')
    op.drop_column('ledger_entries', 'balance')
    op.drop_column('ledger_entries', 'credit_amount')
    op.drop_column('ledger_entries', 'debit_amount')
    op.drop_column('ledger_entries', 'account_code')
    op.drop_column('ledger_entries', 'source_id')
    op.drop_column('ledger_entries', 'source_type')
