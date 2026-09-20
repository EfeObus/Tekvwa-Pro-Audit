"""add_updated_at_to_journal_entry_lines

Finding 50 (docs/FINDING_50_SCOPE.md): journal_entry_lines is missing updated_at at the DB level
(created_at already exists). Backfills from created_at before enforcing NOT NULL.

Revision ID: f5829862f984
Revises: 104a08d0d777
Create Date: 2026-09-20 11:42:59.286487

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f5829862f984'
down_revision: Union[str, None] = '104a08d0d777'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('journal_entry_lines', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')))
    op.execute("UPDATE journal_entry_lines SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column('journal_entry_lines', 'updated_at', nullable=False)


def downgrade() -> None:
    op.drop_column('journal_entry_lines', 'updated_at')
