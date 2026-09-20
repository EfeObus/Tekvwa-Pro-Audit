"""add_timestamps_to_gl_integration_logs

Finding 50 (docs/FINDING_50_SCOPE.md): gl_integration_logs is missing both created_at and
updated_at at the DB level entirely. Backfills from posted_at (itself always populated) before
enforcing NOT NULL, so this works regardless of row count.

Revision ID: 104a08d0d777
Revises: 1f34cc20a492
Create Date: 2026-09-20 11:22:24.678819

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '104a08d0d777'
down_revision: Union[str, None] = '1f34cc20a492'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('gl_integration_logs', sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')))
    op.add_column('gl_integration_logs', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')))
    op.execute("UPDATE gl_integration_logs SET created_at = posted_at, updated_at = posted_at WHERE created_at IS NULL")
    op.alter_column('gl_integration_logs', 'created_at', nullable=False)
    op.alter_column('gl_integration_logs', 'updated_at', nullable=False)


def downgrade() -> None:
    op.drop_column('gl_integration_logs', 'updated_at')
    op.drop_column('gl_integration_logs', 'created_at')
