"""add_updated_at_to_exchange_rates

Finding 50 (docs/FINDING_50_SCOPE.md): exchange_rates is missing updated_at at the DB level
(created_at already exists, with timezone). Backfills from created_at before enforcing NOT NULL.

Revision ID: d0fd664030a3
Revises: f5829862f984
Create Date: 2026-09-20 12:11:03.030658

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd0fd664030a3'
down_revision: Union[str, None] = 'f5829862f984'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('exchange_rates', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')))
    op.execute("UPDATE exchange_rates SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column('exchange_rates', 'updated_at', nullable=False)


def downgrade() -> None:
    op.drop_column('exchange_rates', 'updated_at')
