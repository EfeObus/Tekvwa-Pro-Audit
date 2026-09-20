"""add_timestamps_to_goods_received_note_items

Finding 50 (docs/FINDING_50_SCOPE.md): goods_received_note_items was missing created_at/updated_at
at the DB level entirely (alembic/versions/20260106_1600_advanced_accounting.py:164-176 never
included them), despite GoodsReceivedNoteItem inheriting BaseModel/TimestampMixin, which assumes
both columns exist. Same gap as purchase_order_items, fixed the same way -- adds both, no backfill
possible or needed (server_default=now() only, no historical source).

Revision ID: 0fc583c63898
Revises: 2abef31e385f
Create Date: 2026-09-20 13:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0fc583c63898'
down_revision: Union[str, None] = '2abef31e385f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('goods_received_note_items', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('goods_received_note_items', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))


def downgrade() -> None:
    op.drop_column('goods_received_note_items', 'updated_at')
    op.drop_column('goods_received_note_items', 'created_at')
