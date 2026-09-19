"""NTAA 2025 Compliance Updates

Add fields for:
- 72-Hour Legal Lock for NRS invoices
- Maker-Checker Segregation of Duties for WREN expenses
- External Accountant role support
- Enhanced audit logging per NTAA 2025
- Time-limited CSR impersonation (24hr tokens)

Revision ID: ntaa_2025_compliance
Revises: 20260103_1600_add_fixed_assets
Create Date: 2026-01-03 16:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '20260103_1630_ntaa_2025_compliance'
down_revision = '20260103_1600_add_fixed_assets'
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def index_exists(table_name: str, index_name: str) -> bool:
    """Check if an index exists on a table."""
    conn = op.get_bind()
    inspector = inspect(conn)
    indexes = [idx['name'] for idx in inspector.get_indexes(table_name)]
    return index_name in indexes


def upgrade() -> None:
    # ===========================================
    # USERS TABLE - External Accountant & Impersonation
    # ===========================================
    
    # Update UserRole enum to include EXTERNAL_ACCOUNTANT
    # PostgreSQL requires special handling for enum updates
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'EXTERNAL_ACCOUNTANT'")
    
    # Add impersonation time-limit fields
    if not column_exists('users', 'impersonation_expires_at'):
        op.add_column('users', sa.Column('impersonation_expires_at', sa.DateTime(timezone=True), nullable=True))
    if not column_exists('users', 'impersonation_granted_at'):
        op.add_column('users', sa.Column('impersonation_granted_at', sa.DateTime(timezone=True), nullable=True))
    
    # ===========================================
    # INVOICES TABLE - 72-Hour NRS Lock
    # ===========================================
    
    # Change nrs_response from TEXT to JSONB for structured storage (skip if already JSONB)
    try:
        op.alter_column('invoices', 'nrs_response',
                        type_=postgresql.JSONB,
                        postgresql_using='nrs_response::jsonb',
                        nullable=True)
    except Exception:
        pass  # Column may already be JSONB
    
    # Add NRS lock fields
    if not column_exists('invoices', 'nrs_cryptographic_stamp'):
        op.add_column('invoices', sa.Column('nrs_cryptographic_stamp', sa.Text(), nullable=True))
    if not column_exists('invoices', 'is_nrs_locked'):
        op.add_column('invoices', sa.Column('is_nrs_locked', sa.Boolean(), server_default='false', nullable=False))
    if not column_exists('invoices', 'nrs_lock_expires_at'):
        op.add_column('invoices', sa.Column('nrs_lock_expires_at', sa.DateTime(timezone=True), nullable=True))
    if not column_exists('invoices', 'nrs_cancelled_by_id'):
        op.add_column('invoices', sa.Column('nrs_cancelled_by_id', postgresql.UUID(as_uuid=True), nullable=True))
    if not column_exists('invoices', 'nrs_cancellation_reason'):
        op.add_column('invoices', sa.Column('nrs_cancellation_reason', sa.Text(), nullable=True))
    
    # Create foreign key for nrs_cancelled_by_id -> users (if column was added)
    if column_exists('invoices', 'nrs_cancelled_by_id'):
        try:
            op.create_foreign_key(
                'fk_invoices_nrs_cancelled_by',
                'invoices', 'users',
                ['nrs_cancelled_by_id'], ['id'],
                ondelete='SET NULL'
            )
        except Exception:
            pass  # FK may already exist
    
    # Create index for locked invoices
    if not index_exists('invoices', 'ix_invoices_is_nrs_locked'):
        op.create_index('ix_invoices_is_nrs_locked', 'invoices', ['is_nrs_locked'], postgresql_where=sa.text('is_nrs_locked = true'))
    
    # ===========================================
    # TRANSACTIONS TABLE - Maker-Checker SoD for WREN
    # ===========================================
    
    if not column_exists('transactions', 'created_by_id'):
        op.add_column('transactions', sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=True))
    if not column_exists('transactions', 'wren_verified_by_id'):
        op.add_column('transactions', sa.Column('wren_verified_by_id', postgresql.UUID(as_uuid=True), nullable=True))
    if not column_exists('transactions', 'wren_verified_at'):
        op.add_column('transactions', sa.Column('wren_verified_at', sa.DateTime(timezone=True), nullable=True))
    if not column_exists('transactions', 'original_category_id'):
        op.add_column('transactions', sa.Column('original_category_id', postgresql.UUID(as_uuid=True), nullable=True))
    if not column_exists('transactions', 'category_change_history'):
        op.add_column('transactions', sa.Column('category_change_history', postgresql.JSONB, nullable=True))
    
    # Create foreign keys (if columns exist)
    try:
        op.create_foreign_key(
            'fk_transactions_created_by',
            'transactions', 'users',
            ['created_by_id'], ['id'],
            ondelete='SET NULL'
        )
    except Exception:
        pass
    
    try:
        op.create_foreign_key(
            'fk_transactions_wren_verified_by',
            'transactions', 'users',
            ['wren_verified_by_id'], ['id'],
            ondelete='SET NULL'
        )
    except Exception:
        pass
    
    try:
        op.create_foreign_key(
            'fk_transactions_original_category',
            'transactions', 'categories',
            ['original_category_id'], ['id'],
            ondelete='SET NULL'
        )
    except Exception:
        pass
    
    # Index for WREN verification queries
    if not index_exists('transactions', 'ix_transactions_wren_verified'):
        op.create_index('ix_transactions_wren_verified', 'transactions', ['wren_verified_by_id', 'wren_verified_at'])
    
    # ===========================================
    # AUDIT_LOGS TABLE - NTAA 2025 Enhanced Logging
    # ===========================================
    
    # NOTE: audit_logs.action is sa.String(50), not a native Postgres enum -
    # there is no 'auditaction' DB type to alter. New AuditAction values (NRS_CREDIT_NOTE,
    # WREN_VERIFY, etc.) are enforced at the application layer only
    # (app/models/audit_consolidated.py) and need no schema change here.

    # Add NTAA 2025 compliance fields
    if not column_exists('audit_logs', 'organization_id'):
        op.add_column('audit_logs', sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True))
    if not column_exists('audit_logs', 'impersonated_by_id'):
        op.add_column('audit_logs', sa.Column('impersonated_by_id', postgresql.UUID(as_uuid=True), nullable=True))
    if not column_exists('audit_logs', 'device_fingerprint'):
        op.add_column('audit_logs', sa.Column('device_fingerprint', sa.String(512), nullable=True))
    if not column_exists('audit_logs', 'session_id'):
        op.add_column('audit_logs', sa.Column('session_id', sa.String(255), nullable=True))
    if not column_exists('audit_logs', 'geo_location'):
        op.add_column('audit_logs', sa.Column('geo_location', postgresql.JSONB, nullable=True))
    if not column_exists('audit_logs', 'nrs_irn'):
        op.add_column('audit_logs', sa.Column('nrs_irn', sa.String(100), nullable=True))
    if not column_exists('audit_logs', 'nrs_response'):
        op.add_column('audit_logs', sa.Column('nrs_response', postgresql.JSONB, nullable=True))
    if not column_exists('audit_logs', 'description'):
        op.add_column('audit_logs', sa.Column('description', sa.Text(), nullable=True))
    
    # Create foreign keys
    try:
        op.create_foreign_key(
            'fk_audit_logs_organization',
            'audit_logs', 'organizations',
            ['organization_id'], ['id'],
            ondelete='SET NULL'
        )
    except Exception:
        pass
    
    try:
        op.create_foreign_key(
            'fk_audit_logs_impersonated_by',
            'audit_logs', 'users',
            ['impersonated_by_id'], ['id'],
            ondelete='SET NULL'
        )
    except Exception:
        pass
    
    # Indexes for NTAA 2025 audit queries
    if not index_exists('audit_logs', 'ix_audit_logs_organization'):
        op.create_index('ix_audit_logs_organization', 'audit_logs', ['organization_id'])
    if not index_exists('audit_logs', 'ix_audit_logs_impersonated_by'):
        op.create_index('ix_audit_logs_impersonated_by', 'audit_logs', ['impersonated_by_id'])
    if not index_exists('audit_logs', 'ix_audit_logs_device_fingerprint'):
        op.create_index('ix_audit_logs_device_fingerprint', 'audit_logs', ['device_fingerprint'])
    if not index_exists('audit_logs', 'ix_audit_logs_session_id'):
        op.create_index('ix_audit_logs_session_id', 'audit_logs', ['session_id'])
    if not index_exists('audit_logs', 'ix_audit_logs_nrs_irn'):
        op.create_index('ix_audit_logs_nrs_irn', 'audit_logs', ['nrs_irn'])


def downgrade() -> None:
    # ===========================================
    # AUDIT_LOGS TABLE - Rollback
    # ===========================================
    op.drop_index('ix_audit_logs_nrs_irn')
    op.drop_index('ix_audit_logs_session_id')
    op.drop_index('ix_audit_logs_device_fingerprint')
    op.drop_index('ix_audit_logs_impersonated_by')
    op.drop_index('ix_audit_logs_organization')
    
    op.drop_constraint('fk_audit_logs_impersonated_by', 'audit_logs', type_='foreignkey')
    op.drop_constraint('fk_audit_logs_organization', 'audit_logs', type_='foreignkey')
    
    op.drop_column('audit_logs', 'description')
    op.drop_column('audit_logs', 'nrs_response')
    op.drop_column('audit_logs', 'nrs_irn')
    op.drop_column('audit_logs', 'geo_location')
    op.drop_column('audit_logs', 'session_id')
    op.drop_column('audit_logs', 'device_fingerprint')
    op.drop_column('audit_logs', 'impersonated_by_id')
    op.drop_column('audit_logs', 'organization_id')
    
    # Note: PostgreSQL does not support removing enum values easily
    # The enum values will remain but won't be used
    
    # ===========================================
    # TRANSACTIONS TABLE - Rollback
    # ===========================================
    op.drop_index('ix_transactions_wren_verified')
    
    op.drop_constraint('fk_transactions_original_category', 'transactions', type_='foreignkey')
    op.drop_constraint('fk_transactions_wren_verified_by', 'transactions', type_='foreignkey')
    op.drop_constraint('fk_transactions_created_by', 'transactions', type_='foreignkey')
    
    op.drop_column('transactions', 'category_change_history')
    op.drop_column('transactions', 'original_category_id')
    op.drop_column('transactions', 'wren_verified_at')
    op.drop_column('transactions', 'wren_verified_by_id')
    op.drop_column('transactions', 'created_by_id')
    
    # ===========================================
    # INVOICES TABLE - Rollback
    # ===========================================
    op.drop_index('ix_invoices_is_nrs_locked')
    
    op.drop_constraint('fk_invoices_nrs_cancelled_by', 'invoices', type_='foreignkey')
    
    op.drop_column('invoices', 'nrs_cancellation_reason')
    op.drop_column('invoices', 'nrs_cancelled_by_id')
    op.drop_column('invoices', 'nrs_lock_expires_at')
    op.drop_column('invoices', 'is_nrs_locked')
    op.drop_column('invoices', 'nrs_cryptographic_stamp')
    
    # Revert nrs_response to TEXT
    op.alter_column('invoices', 'nrs_response',
                    type_=sa.Text(),
                    postgresql_using='nrs_response::text',
                    nullable=True)
    
    # ===========================================
    # USERS TABLE - Rollback
    # ===========================================
    op.drop_column('users', 'impersonation_granted_at')
    op.drop_column('users', 'impersonation_expires_at')
    
    # Note: Cannot easily remove EXTERNAL_ACCOUNTANT from UserRole enum
