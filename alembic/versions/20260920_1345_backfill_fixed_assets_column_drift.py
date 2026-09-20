"""backfill_fixed_assets_column_drift

Finding 50 (docs/FINDING_50_SCOPE.md): app/services/fixed_asset_service.py's create_asset() --
the only real construction site for FixedAsset -- always included vendor_invoice_number/
vat_recovered/disposal_amount/insured_value/insurance_expiry in its INSERT (the model already
declared all of them), but none of these columns ever existed on the live table
(alembic/versions/20260103_1600_add_fixed_assets.py:86-143 has invoice_number/insurance_value/
insurance_expiry_date/disposal_proceeds/vat_recovery_eligible/vat_recovery_claimed/
vat_recovery_date instead) -- every real call has always failed with an UndefinedColumnError.
department/assigned_to/warranty_expiry/notes/asset_metadata (also declared on the model) were
already added by a later migration
(alembic/versions/20260104_1500_sync_models_with_db.py:126-160), so they're not repeated here.
This table is confirmed structurally unable to hold a row under the pre-fix code, so no backfill
is needed for anything added here.

Revision ID: 4ada40aa5f48
Revises: 0fc583c63898
Create Date: 2026-09-20 13:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4ada40aa5f48'
down_revision: Union[str, None] = '0fc583c63898'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('fixed_assets', sa.Column('vendor_invoice_number', sa.String(length=100), nullable=True))
    op.add_column('fixed_assets', sa.Column('vat_recovered', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('fixed_assets', sa.Column('disposal_amount', sa.Numeric(precision=15, scale=2), nullable=True))
    op.add_column('fixed_assets', sa.Column('insured_value', sa.Numeric(precision=15, scale=2), nullable=True))
    op.add_column('fixed_assets', sa.Column('insurance_expiry', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('fixed_assets', 'insurance_expiry')
    op.drop_column('fixed_assets', 'insured_value')
    op.drop_column('fixed_assets', 'disposal_amount')
    op.drop_column('fixed_assets', 'vat_recovered')
    op.drop_column('fixed_assets', 'vendor_invoice_number')
