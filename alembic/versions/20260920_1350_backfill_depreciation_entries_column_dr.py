"""backfill_depreciation_entries_column_drift

Finding 50 (docs/FINDING_50_SCOPE.md): app/services/fixed_asset_service.py's only real
construction site for DepreciationEntry used period_year/period_month/depreciation_method/
depreciation_rate/posted_by_id directly -- none of which existed on the live table
(alembic/versions/20260103_1600_add_fixed_assets.py:160-181 has fiscal_year_end/period_start/
period_end/depreciation_rate_used instead, and no depreciation_method/posted_by_id at all) --
every real call has always failed with an UndefinedColumnError. Also missing entirely:
updated_at (only created_at existed, despite this model inheriting BaseModel/TimestampMixin).
entity_id/is_posted/created_by_id already existed on the live table with no model equivalent --
added to the model only (direction (B), no migration needed for those three). This table is
confirmed structurally unable to hold a row under the pre-fix code, so no backfill is needed for
anything added here.

Revision ID: 3a1c0b05fc35
Revises: 4ada40aa5f48
Create Date: 2026-09-20 13:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '3a1c0b05fc35'
down_revision: Union[str, None] = '4ada40aa5f48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('depreciation_entries', sa.Column('period_year', sa.Integer(), nullable=False))
    op.add_column('depreciation_entries', sa.Column('period_month', sa.Integer(), nullable=True))
    op.add_column('depreciation_entries', sa.Column(
        'depreciation_method',
        postgresql.ENUM(name='depreciationmethod', create_type=False),
        nullable=False,
    ))
    op.add_column('depreciation_entries', sa.Column('depreciation_rate', sa.Numeric(precision=5, scale=2), nullable=False))
    op.add_column('depreciation_entries', sa.Column('posted_by_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('depreciation_entries', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))

    op.create_foreign_key('fk_depreciation_entries_posted_by_id_users', 'depreciation_entries', 'users', ['posted_by_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('fk_depreciation_entries_posted_by_id_users', 'depreciation_entries', type_='foreignkey')

    op.drop_column('depreciation_entries', 'updated_at')
    op.drop_column('depreciation_entries', 'posted_by_id')
    op.drop_column('depreciation_entries', 'depreciation_rate')
    op.drop_column('depreciation_entries', 'depreciation_method')
    op.drop_column('depreciation_entries', 'period_month')
    op.drop_column('depreciation_entries', 'period_year')
