"""add_updated_at_to_payslip_items

Finding 50 (docs/FINDING_50_SCOPE.md): `PayslipItem` inherits `BaseModel` (id + `TimestampMixin`),
which always adds a NOT NULL `updated_at` with a server default -- included in every INSERT
regardless of application code. The live table only had `created_at`, so every payslip item
creation has always failed with an UndefinedColumnError. Also narrows the model's `item_type`
from `String(50)` to the live column's real `String(30)` (real values top out at
"employer_contribution", 22 chars, so this was never a truncation risk in practice, just a
mismatch worth closing while already here).

Revision ID: 553f1e5fc3cc
Revises: 88bc48bd3bee
Create Date: 2026-09-25 17:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '553f1e5fc3cc'
down_revision: Union[str, None] = '88bc48bd3bee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('payslip_items', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))


def downgrade() -> None:
    op.drop_column('payslip_items', 'updated_at')
