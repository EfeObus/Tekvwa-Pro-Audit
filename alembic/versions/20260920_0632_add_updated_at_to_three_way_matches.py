"""add_updated_at_to_three_way_matches

Finding 50 (docs/FINDING_50_SCOPE.md): three_way_matches is missing updated_at at the DB level
(its original migration, 20260106_1600_advanced_accounting.py, only included created_at). Backfills
from created_at before enforcing NOT NULL, so this works regardless of row count.

Revision ID: 4dbd6a167d9c
Revises: e46be79bee0f
Create Date: 2026-09-20 06:32:39.995011

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4dbd6a167d9c'
down_revision: Union[str, None] = 'e46be79bee0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('three_way_matches', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')))
    op.execute("UPDATE three_way_matches SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column('three_way_matches', 'updated_at', nullable=False)


def downgrade() -> None:
    op.drop_column('three_way_matches', 'updated_at')
