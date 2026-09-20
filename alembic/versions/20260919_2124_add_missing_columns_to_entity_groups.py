"""add_missing_columns_to_entity_groups

Finding 50 (docs/FINDING_50_SCOPE.md): EntityGroup.parent_entity_id (NOT NULL on the model) and
fiscal_year_end_month have always been on the model but were never created by any migration -
confirmed by direct inspection of the live entity_groups table, and confirmed to break basic
EntityGroup creation (no code path can construct one without parent_entity_id). No old column to
backfill from (these are genuinely new, not renames) - existing rows get a data-driven backfill
(first member entity per group, by join date, if any).

Deliberately does NOT add a DB-level NOT NULL constraint on parent_entity_id even though the model
declares one: a group with zero members (if any exist in production - unverified, and this
environment cannot check) would have nothing to backfill from and be left NULL, which would make
`ALTER COLUMN ... SET NOT NULL` fail outright against real data. Enforcing it at the DB level is an
explicit follow-up verification task (confirm no zero-member groups exist, or backfill them some
other way) rather than an assumption made either way here - see docs/REMEDIATION_LOG.md.

Revision ID: 5300207c437e
Revises: fa30aeb4bae6
Create Date: 2026-09-19 21:24:01.486538

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '5300207c437e'
down_revision: Union[str, None] = 'fa30aeb4bae6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('entity_groups', sa.Column('parent_entity_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('entity_groups', sa.Column('fiscal_year_end_month', sa.Integer(), nullable=True, server_default='12'))

    # Backfill: use the group's first member (by join date) as the parent, for any existing rows.
    # No-op if the table is empty.
    op.execute("""
        UPDATE entity_groups eg
        SET parent_entity_id = (
            SELECT egm.entity_id FROM entity_group_members egm
            WHERE egm.group_id = eg.id
            ORDER BY egm.joined_at ASC
            LIMIT 1
        )
        WHERE eg.parent_entity_id IS NULL
    """)

    op.create_foreign_key(
        'fk_entity_groups_parent_entity_id_business_entities',
        'entity_groups', 'business_entities', ['parent_entity_id'], ['id'],
    )

    # Deliberately not adding SET NOT NULL here - see module docstring.


def downgrade() -> None:
    op.drop_constraint('fk_entity_groups_parent_entity_id_business_entities', 'entity_groups', type_='foreignkey')
    op.drop_column('entity_groups', 'fiscal_year_end_month')
    op.drop_column('entity_groups', 'parent_entity_id')
