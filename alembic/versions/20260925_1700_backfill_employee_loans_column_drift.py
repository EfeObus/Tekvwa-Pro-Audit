"""backfill_employee_loans_column_drift

Finding 50 (docs/FINDING_50_SCOPE.md): two small, independent gaps found while investigating the
Tier 3 "1 mismatched column" entries for employee_loans and loan_repayments.

`employee_loans.updated_by_id`: this table's model comment already documented that its migration
added a FK for `created_by_id` but not `updated_by_id`, and read that as "the plain (no-FK)
AuditMixin column is used instead" -- but the live table has no `updated_by_id` column at all,
not just a missing FK. `app/services/payroll_service.py`'s `update_loan()` always sets
`loan.updated_by_id = updated_by_id` unconditionally, so every loan update has always failed with
an UndefinedColumnError. Added the plain (no-FK) column the model already declares via AuditMixin.

`loan_repayments.updated_at`: this model inherits `BaseModel` (id + TimestampMixin), which always
adds a NOT NULL `updated_at` with a server default -- included in every INSERT regardless of
whether application code ever sets it. The live table only has `created_at`. Every loan repayment
creation has always failed with an UndefinedColumnError; confirmed zero rows exist for either
table, so this migration needs no backfill.

Revision ID: 88bc48bd3bee
Revises: 5a3098d47860
Create Date: 2026-09-25 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '88bc48bd3bee'
down_revision: Union[str, None] = '5a3098d47860'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('employee_loans', sa.Column('updated_by_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('loan_repayments', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))


def downgrade() -> None:
    op.drop_column('loan_repayments', 'updated_at')
    op.drop_column('employee_loans', 'updated_by_id')
