"""backfill_accounting_dimensions_and_transaction_dimensions

Finding 50 (docs/FINDING_50_SCOPE.md): `AccountingDimension` and `TransactionDimension` --
confirmed via a codebase-wide grep to have zero real construction sites, genuinely dead code --
had drift the model side, fixed here on the DB side plus one dormant enum gap.

`AccountingDimension` had `sort_order`/`extra_data` fields with no matching live columns (the live
table's real column is `metadata`, unmapped in the model, fixed there not here), and its
`SQLEnum(DimensionType)` declaration had no explicit `name=`, so SQLAlchemy would have generated
bind casts against a `dimensiontype` type (auto-derived from the class name) that does not exist --
the real live enum type is `dimension_type` (with an underscore, fixed in the model). The live
`dimension_type` Postgres enum type is also missing 3 of the Python `DimensionType` enum's 9
members (`location`, `sales_channel`, `product_line`) -- added here so the full enum is actually
usable once this table has a real caller, at zero risk since adding enum values is purely
additive.

`TransactionDimension` inherits `BaseModel`, which always adds a NOT NULL `updated_at` with a
server default -- the live table only had `created_at`. Same pattern as `loan_repayments`/
`payslip_items` earlier this session; added here too, before this table gets a real caller.

Revision ID: 5845b65e3876
Revises: 02c915f85794
Create Date: 2026-09-25 17:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5845b65e3876'
down_revision: Union[str, None] = '02c915f85794'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE dimension_type ADD VALUE IF NOT EXISTS 'location'")
    op.execute("ALTER TYPE dimension_type ADD VALUE IF NOT EXISTS 'sales_channel'")
    op.execute("ALTER TYPE dimension_type ADD VALUE IF NOT EXISTS 'product_line'")
    op.add_column('transaction_dimensions', sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False))


def downgrade() -> None:
    op.drop_column('transaction_dimensions', 'updated_at')
    # PostgreSQL does not support removing enum values; the added values remain but go unused.
