"""backfill_audit_logs_column_drift

Finding 50 (docs/FINDING_50_SCOPE.md): separate from, and additional to, the already-known
Finding 41 (target_entity_type/target_entity_id never migrated). Tracing the "4 mismatched
columns" flagged for this table found: the original `create_table` migration
(20260103_1251) created only 13 columns; a later NTAA migration (20260103_1630) added 8 more
(organization_id/impersonated_by_id/device_fingerprint/session_id/geo_location/nrs_irn/
nrs_response/description) but never added `target_entity_type`, `target_entity_id`, or `changes`
-- all three used unconditionally by `app/services/audit_service.py`'s `log_action()`, the single
shared entry point called from 82+ places across the codebase. Every audit log write has always
failed with an UndefinedColumnError.

Also fixes an independent, additional bug found while tracing this: the model's own
`entity_id`/`user_id` fields are declared `Optional`, with comments explicitly documenting why --
"nullable for system-level events / unauthenticated actions like login failures" -- but the live
columns (from the original 20260103_1251 migration) were `NOT NULL`. `app/routers/auth.py`'s
failed-login handler passes `business_entity_id=None`/`user_id=None` with no surrounding
try/except -- every failed login attempt has always raised an unhandled NotNullViolation instead
of returning the intended 401/429 response, a 500 error on a security-critical, high-traffic path.
Relaxed both to nullable to match the model's already-correct, documented design.

`request_id` already existed on the live table (from the original migration) but was unmapped in
the model until this fix -- no migration needed for it. `device_fingerprint` is widened here to
`String(512)` to match the NTAA migration's real column (the model had drifted back down to 255).

Revision ID: 02c915f85794
Revises: 98bdd0ac439d
Create Date: 2026-09-25 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '02c915f85794'
down_revision: Union[str, None] = '98bdd0ac439d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('audit_logs', sa.Column('target_entity_type', sa.String(length=100), server_default='', nullable=True))
    op.add_column('audit_logs', sa.Column('target_entity_id', sa.String(length=100), nullable=True))
    op.add_column('audit_logs', sa.Column('changes', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_index('ix_audit_logs_target_entity_type', 'audit_logs', ['target_entity_type'])
    op.create_index('ix_audit_logs_target_entity_id', 'audit_logs', ['target_entity_id'])

    op.alter_column('audit_logs', 'entity_id', existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.alter_column('audit_logs', 'user_id', existing_type=postgresql.UUID(as_uuid=True), nullable=True)


def downgrade() -> None:
    op.alter_column('audit_logs', 'user_id', existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    op.alter_column('audit_logs', 'entity_id', existing_type=postgresql.UUID(as_uuid=True), nullable=False)

    op.drop_index('ix_audit_logs_target_entity_id', table_name='audit_logs')
    op.drop_index('ix_audit_logs_target_entity_type', table_name='audit_logs')
    op.drop_column('audit_logs', 'changes')
    op.drop_column('audit_logs', 'target_entity_id')
    op.drop_column('audit_logs', 'target_entity_type')
