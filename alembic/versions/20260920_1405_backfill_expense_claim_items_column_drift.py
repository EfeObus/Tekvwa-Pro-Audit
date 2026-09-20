"""backfill_expense_claim_items_column_drift

Finding 50 (docs/FINDING_50_SCOPE.md): app/services/expense_claims_service.py's
add_expense_item() -- the only real construction site -- always sent vat_amount/approved_amount/
receipt_file_url/has_receipt, none of which existed on the live table -- every real call has
always failed with an UndefinedColumnError. The model's FK column was also misnamed (claim_id
instead of the live table's real expense_claim_id, per its own FK constraint name) -- renamed in
the model instead of migrated here, since the DB already had the right name. Also missing
entirely: updated_at (only created_at existed, despite this model inheriting BaseModel/
TimestampMixin). This table is confirmed structurally unable to hold a row under the pre-fix
code, so no backfill is needed for anything added here.

Revision ID: 6415d481ab54
Revises: 3f637da4ead5
Create Date: 2026-09-20 14:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6415d481ab54'
down_revision: Union[str, None] = '3f637da4ead5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('expense_claim_items', sa.Column('vat_amount', sa.Numeric(precision=15, scale=2), server_default='0', nullable=False))
    op.add_column('expense_claim_items', sa.Column('approved_amount', sa.Numeric(precision=15, scale=2), server_default='0', nullable=False))
    op.add_column('expense_claim_items', sa.Column('receipt_file_url', sa.String(length=500), nullable=True))
    op.add_column('expense_claim_items', sa.Column('has_receipt', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('expense_claim_items', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))


def downgrade() -> None:
    op.drop_column('expense_claim_items', 'updated_at')
    op.drop_column('expense_claim_items', 'has_receipt')
    op.drop_column('expense_claim_items', 'receipt_file_url')
    op.drop_column('expense_claim_items', 'approved_amount')
    op.drop_column('expense_claim_items', 'vat_amount')
