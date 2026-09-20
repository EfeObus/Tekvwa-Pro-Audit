"""backfill_account_balances_column_drift

Finding 50 (docs/FINDING_50_SCOPE.md): AccountBalance's model declares entity_id/ytd_debit/
ytd_credit/last_updated, and app/utils/query_optimization.py, app/services/accounting_service.py,
and app/services/year_end_closing_service.py all already query/update using exactly these names -
none of which exist on the live table (which has no entity_id at all, no ytd_debit/ytd_credit, and
last_calculated_at instead of last_updated). Migrating the database to match the model+code.
entity_id is NOT NULL on the model; backfilled here via a join through chart_of_accounts (which
already has a real, NOT NULL entity_id), not left to a data-driven guess.

Revision ID: 1f34cc20a492
Revises: a17c9e5f2b3d
Create Date: 2026-09-20 07:42:45.346002

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '1f34cc20a492'
down_revision: Union[str, None] = 'a17c9e5f2b3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('account_balances', sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('account_balances', sa.Column('ytd_debit', sa.Numeric(18, 2), nullable=True, server_default='0'))
    op.add_column('account_balances', sa.Column('ytd_credit', sa.Numeric(18, 2), nullable=True, server_default='0'))
    op.add_column('account_balances', sa.Column('last_updated', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')))
    # This table is also missing created_at/updated_at (BaseModel/TimestampMixin) at the DB level
    # entirely - same additive-plus-backfill treatment, unrelated to the entity_id/ytd drift above.
    op.add_column('account_balances', sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')))
    op.add_column('account_balances', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')))

    op.execute("""
        UPDATE account_balances ab SET
            entity_id = coa.entity_id,
            last_updated = COALESCE(ab.last_calculated_at, now()),
            created_at = COALESCE(ab.last_calculated_at, now()),
            updated_at = COALESCE(ab.last_calculated_at, now())
        FROM chart_of_accounts coa
        WHERE ab.account_id = coa.id
    """)

    op.create_foreign_key(
        'fk_account_balances_entity_id_business_entities',
        'account_balances', 'business_entities', ['entity_id'], ['id'], ondelete='CASCADE',
    )

    # Backfill above draws entity_id from chart_of_accounts.entity_id, itself NOT NULL, via account_id,
    # itself NOT NULL and FK-enforced - every row is guaranteed a match, safe to enforce NOT NULL.
    op.alter_column('account_balances', 'entity_id', nullable=False)
    op.alter_column('account_balances', 'ytd_debit', nullable=False)
    op.alter_column('account_balances', 'ytd_credit', nullable=False)
    op.alter_column('account_balances', 'last_updated', nullable=False)
    op.alter_column('account_balances', 'created_at', nullable=False)
    op.alter_column('account_balances', 'updated_at', nullable=False)

    # Indexes matching the model's own __table_args__ (ix_ab_entity_period, ix_ab_account) -
    # these reference the brand-new entity_id column, so they don't exist yet. The old
    # ix_account_balances_account_id/fiscal_period_id indexes and uq_account_balances_account_period
    # unique constraint stay in place - the model's own uq_account_balance is a different,
    # entity_id-inclusive constraint, added separately below.
    op.create_index('ix_ab_entity_period', 'account_balances', ['entity_id', 'fiscal_period_id'])
    op.create_index('ix_ab_account', 'account_balances', ['account_id'])
    op.create_unique_constraint('uq_account_balance', 'account_balances', ['entity_id', 'account_id', 'fiscal_period_id'])


def downgrade() -> None:
    op.drop_constraint('uq_account_balance', 'account_balances', type_='unique')
    op.drop_index('ix_ab_account', table_name='account_balances')
    op.drop_index('ix_ab_entity_period', table_name='account_balances')
    op.drop_constraint('fk_account_balances_entity_id_business_entities', 'account_balances', type_='foreignkey')
    op.drop_column('account_balances', 'updated_at')
    op.drop_column('account_balances', 'created_at')
    op.drop_column('account_balances', 'last_updated')
    op.drop_column('account_balances', 'ytd_credit')
    op.drop_column('account_balances', 'ytd_debit')
    op.drop_column('account_balances', 'entity_id')
