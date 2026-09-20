"""backfill_intercompany_transactions_column_drift

Finding 50 (docs/FINDING_50_SCOPE.md): IntercompanyTransaction's model has always declared
from_entity_id/to_entity_id/transaction_date/currency/from_transaction_id/to_transaction_id/
elimination_date/notes, but the original migration (20260106_1600_advanced_accounting.py) actually
created source_entity_id/target_entity_id/source_transaction_id/target_transaction_id/eliminated_at/
description instead, and never created transaction_date/currency at all. This is a confirmed, live
bug: POST /intercompany (app/routers/advanced_accounting.py) constructs an IntercompanyTransaction
using the model's (until-now-nonexistent) column names on every call and crashes at db.flush().

Additive-only per docs/FINDING_50_SCOPE.md's resolved strategy: add every column the model expects,
backfill from the old column where one exists, then apply NOT NULL only after backfill guarantees no
NULLs. The old columns (source_entity_id, target_entity_id, source_transaction_id,
target_transaction_id, eliminated_at, description) are deliberately left in place, unused by the
model going forward - dropping them is out of scope for this pass (candidate for a later Phase 12
cleanup once nothing depends on them).

Revision ID: fa30aeb4bae6
Revises: fx_revaluation_001
Create Date: 2026-09-19 21:20:24.973505

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'fa30aeb4bae6'
down_revision: Union[str, None] = 'fx_revaluation_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0. updated_at: every BaseModel/TimestampMixin subclass declares this NOT NULL with
    #    server_default=now(), but this table's original migration only created created_at. Same
    #    additive-plus-backfill treatment; backfill from created_at guarantees no NULLs before the
    #    NOT NULL constraint is applied, regardless of row count.
    op.add_column('intercompany_transactions', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')))
    op.execute("UPDATE intercompany_transactions SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column('intercompany_transactions', 'updated_at', nullable=False)

    # 1. Add every column the model expects, nullable for now (backfill happens before any NOT NULL).
    op.add_column('intercompany_transactions', sa.Column('from_entity_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('intercompany_transactions', sa.Column('to_entity_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('intercompany_transactions', sa.Column('transaction_date', sa.Date(), nullable=True))
    op.add_column('intercompany_transactions', sa.Column('currency', sa.String(3), nullable=True, server_default='NGN'))
    op.add_column('intercompany_transactions', sa.Column('from_transaction_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('intercompany_transactions', sa.Column('to_transaction_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('intercompany_transactions', sa.Column('elimination_date', sa.Date(), nullable=True))
    op.add_column('intercompany_transactions', sa.Column('notes', sa.Text(), nullable=True))

    # 2. Backfill from the old columns for any existing rows. Safe (no-op) if the table is empty.
    op.execute("""
        UPDATE intercompany_transactions SET
            from_entity_id = source_entity_id,
            to_entity_id = target_entity_id,
            transaction_date = created_at::date,
            from_transaction_id = source_transaction_id,
            to_transaction_id = target_transaction_id,
            elimination_date = eliminated_at::date,
            notes = description
    """)

    # 3. Foreign keys on the new columns, matching the model's ForeignKey() declarations and this
    #    codebase's naming_convention (app/database.py).
    op.create_foreign_key(
        'fk_intercompany_transactions_from_entity_id_business_entities',
        'intercompany_transactions', 'business_entities', ['from_entity_id'], ['id'],
    )
    op.create_foreign_key(
        'fk_intercompany_transactions_to_entity_id_business_entities',
        'intercompany_transactions', 'business_entities', ['to_entity_id'], ['id'],
    )
    op.create_foreign_key(
        'fk_intercompany_transactions_from_transaction_id_transactions',
        'intercompany_transactions', 'transactions', ['from_transaction_id'], ['id'],
    )
    op.create_foreign_key(
        'fk_intercompany_transactions_to_transaction_id_transactions',
        'intercompany_transactions', 'transactions', ['to_transaction_id'], ['id'],
    )

    # 4. Indexes matching the model's own __table_args__ declarations exactly (ix_interco_group,
    #    ix_interco_entities) - not the original migration's per-column ix_intercompany_txn_source/
    #    target, which indexed the old column names and are being superseded.
    op.create_index('ix_interco_group', 'intercompany_transactions', ['group_id'])
    op.create_index('ix_interco_entities', 'intercompany_transactions', ['from_entity_id', 'to_entity_id'])

    # 5. Backfill guarantees every existing row now has a value for the columns the model declares
    #    NOT NULL (from_entity_id/to_entity_id were NOT NULL on the old columns already; transaction_date
    #    backfills from created_at, itself NOT NULL) - safe to enforce now regardless of row count.
    op.alter_column('intercompany_transactions', 'from_entity_id', nullable=False)
    op.alter_column('intercompany_transactions', 'to_entity_id', nullable=False)
    op.alter_column('intercompany_transactions', 'transaction_date', nullable=False)

    # 6. The old columns are no longer written by the model going forward (the ORM INSERT only sets
    #    the new column names), so their own NOT NULL constraints must be relaxed or every future
    #    insert violates them. source_entity_id/target_entity_id were the only NOT NULL columns among
    #    the six being superseded; the rest were already nullable.
    op.alter_column('intercompany_transactions', 'source_entity_id', nullable=True)
    op.alter_column('intercompany_transactions', 'target_entity_id', nullable=True)


def downgrade() -> None:
    op.alter_column('intercompany_transactions', 'target_entity_id', nullable=False)
    op.alter_column('intercompany_transactions', 'source_entity_id', nullable=False)
    op.drop_index('ix_interco_entities', table_name='intercompany_transactions')
    op.drop_index('ix_interco_group', table_name='intercompany_transactions')
    op.drop_constraint('fk_intercompany_transactions_to_transaction_id_transactions', 'intercompany_transactions', type_='foreignkey')
    op.drop_constraint('fk_intercompany_transactions_from_transaction_id_transactions', 'intercompany_transactions', type_='foreignkey')
    op.drop_constraint('fk_intercompany_transactions_to_entity_id_business_entities', 'intercompany_transactions', type_='foreignkey')
    op.drop_constraint('fk_intercompany_transactions_from_entity_id_business_entities', 'intercompany_transactions', type_='foreignkey')
    op.drop_column('intercompany_transactions', 'notes')
    op.drop_column('intercompany_transactions', 'elimination_date')
    op.drop_column('intercompany_transactions', 'to_transaction_id')
    op.drop_column('intercompany_transactions', 'from_transaction_id')
    op.drop_column('intercompany_transactions', 'currency')
    op.drop_column('intercompany_transactions', 'transaction_date')
    op.drop_column('intercompany_transactions', 'to_entity_id')
    op.drop_column('intercompany_transactions', 'from_entity_id')
    op.drop_column('intercompany_transactions', 'updated_at')
