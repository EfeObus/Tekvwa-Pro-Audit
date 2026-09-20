"""add_timestamps_to_purchase_order_items

Finding 50 (docs/FINDING_50_SCOPE.md): purchase_order_items was missing created_at/updated_at at
the DB level entirely (alembic/versions/20260106_1600_advanced_accounting.py:128-139 never
included them), despite PurchaseOrderItem inheriting BaseModel/TimestampMixin, which assumes both
columns exist. Adds and backfills both from now() since there is no historical source to backfill
from.

Revision ID: 2abef31e385f
Revises: 367e1f63c047
Create Date: 2026-09-20 13:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2abef31e385f'
down_revision: Union[str, None] = '367e1f63c047'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('purchase_order_items', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('purchase_order_items', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))


def downgrade() -> None:
    op.drop_column('purchase_order_items', 'updated_at')
    op.drop_column('purchase_order_items', 'created_at')
