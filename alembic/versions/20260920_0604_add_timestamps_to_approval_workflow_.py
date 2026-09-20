"""add_timestamps_to_approval_workflow_approvers

Finding 50 (docs/FINDING_50_SCOPE.md): approval_workflow_approvers is one of 36 tables across the
schema missing at least one BaseModel/TimestampMixin column - this one is missing both created_at
and updated_at (its original migration, 20260106_1600_advanced_accounting.py, never included
either). Both get server_default=now() so existing rows and new inserts alike get a sensible value
without needing a data-driven backfill.

Revision ID: 68893a772b64
Revises: 5300207c437e
Create Date: 2026-09-20 06:04:23.880679

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '68893a772b64'
down_revision: Union[str, None] = '5300207c437e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('approval_workflow_approvers', sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')))
    op.add_column('approval_workflow_approvers', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')))
    op.execute("UPDATE approval_workflow_approvers SET created_at = now(), updated_at = now() WHERE created_at IS NULL")
    op.alter_column('approval_workflow_approvers', 'created_at', nullable=False)
    op.alter_column('approval_workflow_approvers', 'updated_at', nullable=False)


def downgrade() -> None:
    op.drop_column('approval_workflow_approvers', 'updated_at')
    op.drop_column('approval_workflow_approvers', 'created_at')
