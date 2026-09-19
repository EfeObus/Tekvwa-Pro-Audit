"""Add budget period, revision, and approval workflow fields

Revision ID: 20260127_1100
Revises: 20260127_1000
Create Date: 2026-01-27 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260127_1100'
down_revision = '20260127_1000'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ===========================================================================
    # BUDGET TABLE - ADD NEW COLUMNS
    # ===========================================================================
    
    # Revision tracking
    op.add_column('budgets', sa.Column('version', sa.Integer(), nullable=False, server_default='1',
        comment='Budget revision version'))
    op.add_column('budgets', sa.Column('parent_budget_id', postgresql.UUID(as_uuid=True), nullable=True,
        comment='Previous version of this budget (for revision chain)'))
    op.add_column('budgets', sa.Column('revision_reason', sa.Text(), nullable=True,
        comment='Reason for revision'))
    op.add_column('budgets', sa.Column('revision_date', sa.DateTime(), nullable=True,
        comment='When revision was created'))
    op.add_column('budgets', sa.Column('is_current_version', sa.Boolean(), nullable=False, server_default='true',
        comment='Is this the active version'))
    
    # Approval workflow integration
    op.add_column('budgets', sa.Column('approval_workflow_id', postgresql.UUID(as_uuid=True), nullable=True,
        comment='Linked approval workflow for this budget'))
    op.add_column('budgets', sa.Column('approval_request_id', postgresql.UUID(as_uuid=True), nullable=True,
        comment='Current approval request if pending'))
    op.add_column('budgets', sa.Column('required_approvers', sa.Integer(), nullable=False, server_default='1',
        comment='Number of approvals required'))
    op.add_column('budgets', sa.Column('current_approvals', sa.Integer(), nullable=False, server_default='0',
        comment='Current approval count'))
    op.add_column('budgets', sa.Column('approval_notes', postgresql.JSON(), nullable=True,
        comment='History of approval comments'))
    
    # Forecasting support
    op.add_column('budgets', sa.Column('is_forecast', sa.Boolean(), nullable=False, server_default='false',
        comment='Is this a forecast vs original budget'))
    op.add_column('budgets', sa.Column('base_budget_id', postgresql.UUID(as_uuid=True), nullable=True,
        comment='Original budget this forecast is based on'))
    op.add_column('budgets', sa.Column('forecast_method', sa.String(50), nullable=True,
        comment='Method: rolling, year-to-go, full-year'))
    op.add_column('budgets', sa.Column('last_forecast_date', sa.Date(), nullable=True,
        comment='Date of last forecast update'))
    op.add_column('budgets', sa.Column('actuals_through_date', sa.Date(), nullable=True,
        comment='Date through which actuals are included in forecast'))
    
    # Variance thresholds
    op.add_column('budgets', sa.Column('variance_threshold_pct', sa.Numeric(5, 2), nullable=False, server_default='10.00',
        comment='Alert if variance exceeds this % of budget'))
    op.add_column('budgets', sa.Column('variance_threshold_amt', sa.Numeric(18, 2), nullable=True,
        comment='Alert if variance exceeds this absolute amount'))
    
    # Currency
    op.add_column('budgets', sa.Column('currency', sa.String(3), nullable=False, server_default='NGN',
        comment='Budget currency'))
    op.add_column('budgets', sa.Column('exchange_rate_date', sa.Date(), nullable=True,
        comment='Rate date for multi-currency conversion'))
    
    # Foreign keys
    op.create_foreign_key('fk_budget_parent', 'budgets', 'budgets', ['parent_budget_id'], ['id'])
    op.create_foreign_key('fk_budget_base', 'budgets', 'budgets', ['base_budget_id'], ['id'])
    op.create_foreign_key('fk_budget_workflow', 'budgets', 'approval_workflows', ['approval_workflow_id'], ['id'])
    op.create_foreign_key('fk_budget_approval_request', 'budgets', 'approval_requests', ['approval_request_id'], ['id'])
    
    # Note: no prior unique constraint named 'uq_budget_entity_year_name' actually exists on
    # budgets (the original table in 20260106_1600_advanced_accounting.py only has plain
    # indexes), so there is nothing to drop here - just add the versioned constraint.
    op.create_unique_constraint('uq_budget_entity_year_name_ver', 'budgets', ['entity_id', 'fiscal_year', 'name', 'version'])
    
    # Indexes
    op.create_index('ix_budget_entity_year', 'budgets', ['entity_id', 'fiscal_year'])
    op.create_index('ix_budget_status', 'budgets', ['status'])
    op.create_index('ix_budget_current_version', 'budgets', ['entity_id', 'is_current_version'])
    
    # ===========================================================================
    # BUDGET PERIODS TABLE - NEW
    # ===========================================================================
    op.create_table(
        'budget_periods',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id'), nullable=True),
        sa.Column('budget_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('budgets.id', ondelete='CASCADE'), nullable=False),
        
        sa.Column('period_number', sa.Integer(), nullable=False,
            comment='Period sequence (1-12 for monthly, 1-4 for quarterly)'),
        sa.Column('period_name', sa.String(50), nullable=False,
            comment="E.g., 'January 2026', 'Q1 2026'"),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        
        # Budgeted amounts
        sa.Column('budgeted_revenue', sa.Numeric(18, 2), nullable=False, server_default='0'),
        sa.Column('budgeted_expense', sa.Numeric(18, 2), nullable=False, server_default='0'),
        sa.Column('budgeted_capex', sa.Numeric(18, 2), nullable=False, server_default='0'),
        sa.Column('budgeted_net_income', sa.Numeric(18, 2), nullable=False, server_default='0'),
        
        # Actual amounts
        sa.Column('actual_revenue', sa.Numeric(18, 2), nullable=False, server_default='0'),
        sa.Column('actual_expense', sa.Numeric(18, 2), nullable=False, server_default='0'),
        sa.Column('actual_capex', sa.Numeric(18, 2), nullable=False, server_default='0'),
        sa.Column('actual_net_income', sa.Numeric(18, 2), nullable=False, server_default='0'),
        
        # Forecast amounts
        sa.Column('forecast_revenue', sa.Numeric(18, 2), nullable=True),
        sa.Column('forecast_expense', sa.Numeric(18, 2), nullable=True),
        sa.Column('forecast_capex', sa.Numeric(18, 2), nullable=True),
        sa.Column('forecast_net_income', sa.Numeric(18, 2), nullable=True),
        
        # Variance
        sa.Column('revenue_variance', sa.Numeric(18, 2), nullable=False, server_default='0',
            comment='Actual - Budget'),
        sa.Column('expense_variance', sa.Numeric(18, 2), nullable=False, server_default='0'),
        sa.Column('revenue_variance_pct', sa.Numeric(8, 4), nullable=False, server_default='0',
            comment='Variance as % of budget'),
        sa.Column('expense_variance_pct', sa.Numeric(8, 4), nullable=False, server_default='0'),
        
        # Status
        sa.Column('is_locked', sa.Boolean(), nullable=False, server_default='false',
            comment='Prevent further changes to this period'),
        sa.Column('is_closed', sa.Boolean(), nullable=False, server_default='false',
            comment='Period has been closed for reporting'),
        sa.Column('last_actuals_sync', sa.DateTime(), nullable=True,
            comment='When actuals were last synced'),
        
        # Standard audit columns
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        
        sa.UniqueConstraint('budget_id', 'period_number', name='uq_budget_period'),
    )
    
    op.create_index('ix_budget_period_dates', 'budget_periods', ['start_date', 'end_date'])
    op.create_index('ix_budget_period_budget_id', 'budget_periods', ['budget_id'])
    
    # ===========================================================================
    # BUDGET LINE ITEMS TABLE - ADD NEW COLUMNS
    # ===========================================================================
    
    # GL Account linkage
    op.add_column('budget_line_items', sa.Column('gl_account_id', postgresql.UUID(as_uuid=True), nullable=True,
        comment='Link to GL account for automatic variance calculation'))
    
    # Flexible period allocations
    op.add_column('budget_line_items', sa.Column('period_allocations', postgresql.JSON(), nullable=True,
        comment='Flexible allocations: {"Q1": 100000, "Q2": 150000, ...}'))
    
    # Monthly actuals
    op.add_column('budget_line_items', sa.Column('jan_actual', sa.Numeric(18, 2), nullable=False, server_default='0'))
    op.add_column('budget_line_items', sa.Column('feb_actual', sa.Numeric(18, 2), nullable=False, server_default='0'))
    op.add_column('budget_line_items', sa.Column('mar_actual', sa.Numeric(18, 2), nullable=False, server_default='0'))
    op.add_column('budget_line_items', sa.Column('apr_actual', sa.Numeric(18, 2), nullable=False, server_default='0'))
    op.add_column('budget_line_items', sa.Column('may_actual', sa.Numeric(18, 2), nullable=False, server_default='0'))
    op.add_column('budget_line_items', sa.Column('jun_actual', sa.Numeric(18, 2), nullable=False, server_default='0'))
    op.add_column('budget_line_items', sa.Column('jul_actual', sa.Numeric(18, 2), nullable=False, server_default='0'))
    op.add_column('budget_line_items', sa.Column('aug_actual', sa.Numeric(18, 2), nullable=False, server_default='0'))
    op.add_column('budget_line_items', sa.Column('sep_actual', sa.Numeric(18, 2), nullable=False, server_default='0'))
    op.add_column('budget_line_items', sa.Column('oct_actual', sa.Numeric(18, 2), nullable=False, server_default='0'))
    op.add_column('budget_line_items', sa.Column('nov_actual', sa.Numeric(18, 2), nullable=False, server_default='0'))
    op.add_column('budget_line_items', sa.Column('dec_actual', sa.Numeric(18, 2), nullable=False, server_default='0'))
    
    op.add_column('budget_line_items', sa.Column('total_actual', sa.Numeric(18, 2), nullable=False, server_default='0'))
    
    # Variance fields
    op.add_column('budget_line_items', sa.Column('total_variance', sa.Numeric(18, 2), nullable=False, server_default='0',
        comment='Actual - Budget'))
    op.add_column('budget_line_items', sa.Column('variance_pct', sa.Numeric(8, 4), nullable=False, server_default='0',
        comment='Variance as % of budget'))
    op.add_column('budget_line_items', sa.Column('is_favorable', sa.Boolean(), nullable=True,
        comment='True if variance is favorable'))
    
    # Forecasting
    op.add_column('budget_line_items', sa.Column('forecast_amount', sa.Numeric(18, 2), nullable=True,
        comment='Year-end forecast'))
    op.add_column('budget_line_items', sa.Column('forecast_variance', sa.Numeric(18, 2), nullable=True,
        comment='Forecast vs Budget variance'))
    
    # Foreign key and indexes
    op.create_foreign_key('fk_budget_item_gl', 'budget_line_items', 'chart_of_accounts', ['gl_account_id'], ['id'])
    op.create_index('ix_budget_item_account', 'budget_line_items', ['account_code'])
    op.create_index('ix_budget_item_gl', 'budget_line_items', ['gl_account_id'])


def downgrade() -> None:
    # ===========================================================================
    # BUDGET LINE ITEMS - REMOVE NEW COLUMNS
    # ===========================================================================
    op.drop_index('ix_budget_item_gl', table_name='budget_line_items')
    op.drop_index('ix_budget_item_account', table_name='budget_line_items')
    op.drop_constraint('fk_budget_item_gl', 'budget_line_items', type_='foreignkey')
    
    op.drop_column('budget_line_items', 'forecast_variance')
    op.drop_column('budget_line_items', 'forecast_amount')
    op.drop_column('budget_line_items', 'is_favorable')
    op.drop_column('budget_line_items', 'variance_pct')
    op.drop_column('budget_line_items', 'total_variance')
    op.drop_column('budget_line_items', 'total_actual')
    op.drop_column('budget_line_items', 'dec_actual')
    op.drop_column('budget_line_items', 'nov_actual')
    op.drop_column('budget_line_items', 'oct_actual')
    op.drop_column('budget_line_items', 'sep_actual')
    op.drop_column('budget_line_items', 'aug_actual')
    op.drop_column('budget_line_items', 'jul_actual')
    op.drop_column('budget_line_items', 'jun_actual')
    op.drop_column('budget_line_items', 'may_actual')
    op.drop_column('budget_line_items', 'apr_actual')
    op.drop_column('budget_line_items', 'mar_actual')
    op.drop_column('budget_line_items', 'feb_actual')
    op.drop_column('budget_line_items', 'jan_actual')
    op.drop_column('budget_line_items', 'period_allocations')
    op.drop_column('budget_line_items', 'gl_account_id')
    
    # ===========================================================================
    # BUDGET PERIODS TABLE - DROP
    # ===========================================================================
    op.drop_index('ix_budget_period_budget_id', table_name='budget_periods')
    op.drop_index('ix_budget_period_dates', table_name='budget_periods')
    op.drop_table('budget_periods')
    
    # ===========================================================================
    # BUDGET TABLE - REMOVE NEW COLUMNS
    # ===========================================================================
    op.drop_index('ix_budget_current_version', table_name='budgets')
    op.drop_index('ix_budget_status', table_name='budgets')
    op.drop_index('ix_budget_entity_year', table_name='budgets')
    
    op.drop_constraint('uq_budget_entity_year_name_ver', 'budgets', type_='unique')
    op.create_unique_constraint('uq_budget_entity_year_name', 'budgets', ['entity_id', 'fiscal_year', 'name'])
    
    op.drop_constraint('fk_budget_approval_request', 'budgets', type_='foreignkey')
    op.drop_constraint('fk_budget_workflow', 'budgets', type_='foreignkey')
    op.drop_constraint('fk_budget_base', 'budgets', type_='foreignkey')
    op.drop_constraint('fk_budget_parent', 'budgets', type_='foreignkey')
    
    op.drop_column('budgets', 'exchange_rate_date')
    op.drop_column('budgets', 'currency')
    op.drop_column('budgets', 'variance_threshold_amt')
    op.drop_column('budgets', 'variance_threshold_pct')
    op.drop_column('budgets', 'actuals_through_date')
    op.drop_column('budgets', 'last_forecast_date')
    op.drop_column('budgets', 'forecast_method')
    op.drop_column('budgets', 'base_budget_id')
    op.drop_column('budgets', 'is_forecast')
    op.drop_column('budgets', 'approval_notes')
    op.drop_column('budgets', 'current_approvals')
    op.drop_column('budgets', 'required_approvers')
    op.drop_column('budgets', 'approval_request_id')
    op.drop_column('budgets', 'approval_workflow_id')
    op.drop_column('budgets', 'is_current_version')
    op.drop_column('budgets', 'revision_date')
    op.drop_column('budgets', 'revision_reason')
    op.drop_column('budgets', 'parent_budget_id')
    op.drop_column('budgets', 'version')
