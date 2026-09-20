"""add_updated_at_to_approval_requests

Finding 50 (docs/FINDING_50_SCOPE.md): approval_requests is missing updated_at at the DB level
(its original migration only included created_at). Backfills from created_at before enforcing
NOT NULL, so this works regardless of row count.

Revision ID: 5f429b0ba4cf
Revises: 4dbd6a167d9c
Create Date: 2026-09-20 07:06:59.135360

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5f429b0ba4cf'
down_revision: Union[str, None] = '4dbd6a167d9c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('approval_requests', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')))
    op.execute("UPDATE approval_requests SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column('approval_requests', 'updated_at', nullable=False)


def downgrade() -> None:
    op.drop_column('approval_requests', 'updated_at')
