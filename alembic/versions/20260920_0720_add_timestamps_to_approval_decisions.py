"""add_timestamps_to_approval_decisions

Finding 50 (docs/FINDING_50_SCOPE.md): approval_decisions is missing both created_at and
updated_at at the DB level (its original migration only declared decided_at). Backfills from
decided_at before enforcing NOT NULL, so this works regardless of row count.

Revision ID: 3022ef79bed9
Revises: 5f429b0ba4cf
Create Date: 2026-09-20 07:20:26.758257

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3022ef79bed9'
down_revision: Union[str, None] = '5f429b0ba4cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('approval_decisions', sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')))
    op.add_column('approval_decisions', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')))
    op.execute("UPDATE approval_decisions SET created_at = decided_at, updated_at = decided_at WHERE created_at IS NULL")
    op.alter_column('approval_decisions', 'created_at', nullable=False)
    op.alter_column('approval_decisions', 'updated_at', nullable=False)


def downgrade() -> None:
    op.drop_column('approval_decisions', 'updated_at')
    op.drop_column('approval_decisions', 'created_at')
