"""Add performance optimization indexes

Revision ID: 20260128_1000
Revises: 20260127_1200
Create Date: 2026-01-28 10:00:00.000000

This migration adds database indexes to optimize commonly executed queries:
- FX rate lookups by currency pair and date
- Journal entry date range queries
- Account balance lookups
- Transaction reporting queries
- Consolidation intercompany queries
- Invoice status queries
- Budget variance calculations
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260128_1000'
down_revision: Union[str, None] = '20260127_1200'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add performance optimization indexes."""
    
    # Exchange rates - frequently queried by currency pair and date
    # Speeds up FX rate lookups for multi-currency transactions
    op.create_index(
        'ix_exchange_rates_currency_date',
        'exchange_rates',
        ['from_currency', 'to_currency', 'rate_date'],
        unique=False,
        if_not_exists=True,
    )
    
    # Journal entries - date range queries
    # Optimizes period-end reports and date-filtered queries
    op.create_index(
        'ix_journal_entries_entity_date',
        'journal_entries',
        ['entity_id', 'entry_date'],
        unique=False,
        if_not_exists=True,
    )
    
    # Journal entries - status for pending/posted queries
    op.create_index(
        'ix_journal_entries_entity_status',
        'journal_entries',
        ['entity_id', 'status'],
        unique=False,
        if_not_exists=True,
    )
    
    # Note: account_balances has no entity_id or period_end_date column (only account_id
    # and fiscal_period_id, both already indexed at table creation), so the
    # ix_account_balances_entity_period / ix_account_balances_account_period indexes
    # originally planned here were dropped as not applicable to the actual schema.

    # Transactions - type and date queries for P&L reports
    op.create_index(
        'ix_transactions_entity_type_date',
        'transactions',
        ['entity_id', 'transaction_type', 'transaction_date'],
        unique=False,
        if_not_exists=True,
    )
    
    # Intercompany transactions - consolidation elimination queries
    op.create_index(
        'ix_intercompany_from_to_date',
        'intercompany_transactions',
        ['source_entity_id', 'target_entity_id', 'created_at'],
        unique=False,
        if_not_exists=True,
    )

    # Intercompany transactions - group-based queries
    op.create_index(
        'ix_intercompany_group_date',
        'intercompany_transactions',
        ['group_id', 'created_at'],
        unique=False,
        if_not_exists=True,
    )
    
    # Invoices - status and date queries for AR aging
    op.create_index(
        'ix_invoices_entity_status_date',
        'invoices',
        ['entity_id', 'status', 'invoice_date'],
        unique=False,
        if_not_exists=True,
    )
    
    # Invoices - due date for overdue tracking
    op.create_index(
        'ix_invoices_entity_due_date',
        'invoices',
        ['entity_id', 'due_date'],
        unique=False,
        if_not_exists=True,
    )
    
    # Chart of accounts - type lookups for report grouping
    op.create_index(
        'ix_coa_entity_type',
        'chart_of_accounts',
        ['entity_id', 'account_type'],
        unique=False,
        if_not_exists=True,
    )
    
    # Chart of accounts - code lookups
    op.create_index(
        'ix_coa_entity_code',
        'chart_of_accounts',
        ['entity_id', 'account_code'],
        unique=False,
        if_not_exists=True,
    )
    
    # Budget line items - budget and account lookups
    # (column is account_code, not account_id - budget_line_items has no account_id FK)
    op.create_index(
        'ix_budget_line_items_budget_account',
        'budget_line_items',
        ['budget_id', 'account_code'],
        unique=False,
        if_not_exists=True,
    )

    # Note: budget_line_items stores amounts as monthly columns (jan_amount..dec_amount),
    # not a period_start/period_end range, so ix_budget_line_items_period as originally
    # planned does not apply to the actual schema and was dropped.

    # Entity group members - consolidation queries
    op.create_index(
        'ix_entity_group_members_group',
        'entity_group_members',
        ['group_id', 'entity_id'],
        unique=False,
        if_not_exists=True,
    )
    
    # Note: fx_revaluations is created later in the chain by fx_revaluation_001.py
    # (its down_revision is this very migration), and that migration already creates
    # an equivalent 'ix_fx_reval_entity_date' index on the same columns, so no index is
    # created here for a table that doesn't exist yet at this point in the chain.
    
    # Audit logs - entity and date queries
    op.create_index(
        'ix_audit_logs_entity_date',
        'audit_logs',
        ['entity_id', 'created_at'],
        unique=False,
        if_not_exists=True,
    )
    
    # Journal entry lines - account lookups for account activity
    op.create_index(
        'ix_journal_entry_lines_account',
        'journal_entry_lines',
        ['account_id'],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    """Remove performance optimization indexes."""
    
    # Drop indexes in reverse order
    op.drop_index('ix_journal_entry_lines_account', table_name='journal_entry_lines', if_exists=True)
    op.drop_index('ix_audit_logs_entity_date', table_name='audit_logs', if_exists=True)
    op.drop_index('ix_fx_revaluations_entity_date', table_name='fx_revaluations', if_exists=True)
    op.drop_index('ix_entity_group_members_group', table_name='entity_group_members', if_exists=True)
    op.drop_index('ix_budget_line_items_period', table_name='budget_line_items', if_exists=True)
    op.drop_index('ix_budget_line_items_budget_account', table_name='budget_line_items', if_exists=True)
    op.drop_index('ix_coa_entity_code', table_name='chart_of_accounts', if_exists=True)
    op.drop_index('ix_coa_entity_type', table_name='chart_of_accounts', if_exists=True)
    op.drop_index('ix_invoices_entity_due_date', table_name='invoices', if_exists=True)
    op.drop_index('ix_invoices_entity_status_date', table_name='invoices', if_exists=True)
    op.drop_index('ix_intercompany_group_date', table_name='intercompany_transactions', if_exists=True)
    op.drop_index('ix_intercompany_from_to_date', table_name='intercompany_transactions', if_exists=True)
    op.drop_index('ix_transactions_entity_type_date', table_name='transactions', if_exists=True)
    op.drop_index('ix_account_balances_account_period', table_name='account_balances', if_exists=True)
    op.drop_index('ix_account_balances_entity_period', table_name='account_balances', if_exists=True)
    op.drop_index('ix_journal_entries_entity_status', table_name='journal_entries', if_exists=True)
    op.drop_index('ix_journal_entries_entity_date', table_name='journal_entries', if_exists=True)
    op.drop_index('ix_exchange_rates_currency_date', table_name='exchange_rates', if_exists=True)
