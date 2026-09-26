"""backfill_ml_jobs_column_drift

Finding 50 (docs/FINDING_50_SCOPE.md): app/services/ml_job_service.py's create_ml_job() (the only
real construction site) always passed job_name/queued_at/organization_id, none of which existed
on the live table (the live table has target_organization_id instead of organization_id, with zero
real code ever referencing it) -- every real call has always failed with an UndefinedColumnError.
Also confirmed independently broken: job_type/status/priority were declared as SQLAlchemy native
enums in the model while the live columns are plain VARCHAR (same "converted for flexibility"
pattern already documented in app/models/sku.py) -- fixed in the model, not here, since no DB
change was needed for that part. worker_id/results/metrics/output_files/error_details already
existed on the live table and were simply unmapped in the model (fixed there, not here).

This table is confirmed structurally unable to hold a row under the pre-fix code, so no backfill
is needed for the NOT NULL columns added here. `target_organization_id` is left in place,
unmapped, per this session's additive-only policy -- nothing in the codebase references it.

Revision ID: 5a3098d47860
Revises: b4aa55783317
Create Date: 2026-09-25 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '5a3098d47860'
down_revision: Union[str, None] = 'b4aa55783317'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('ml_jobs', sa.Column('job_name', sa.String(length=255), server_default='', nullable=False))
    op.add_column('ml_jobs', sa.Column('queued_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False))
    op.add_column('ml_jobs', sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_ml_jobs_organization_id_organizations',
        'ml_jobs', 'organizations',
        ['organization_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_index('ix_ml_jobs_organization_id', 'ml_jobs', ['organization_id'])
    op.alter_column('ml_jobs', 'priority', existing_type=sa.String(length=20), nullable=False,
                     server_default='normal')


def downgrade() -> None:
    op.alter_column('ml_jobs', 'priority', existing_type=sa.String(length=20), nullable=True,
                     server_default=None)
    op.drop_index('ix_ml_jobs_organization_id', table_name='ml_jobs')
    op.drop_constraint('fk_ml_jobs_organization_id_organizations', 'ml_jobs', type_='foreignkey')
    op.drop_column('ml_jobs', 'organization_id')
    op.drop_column('ml_jobs', 'queued_at')
    op.drop_column('ml_jobs', 'job_name')
