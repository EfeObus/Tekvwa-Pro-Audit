"""2026 Tax Reform Advanced Features

Revision ID: 20260106_1600_advanced_accounting
Revises: 20260106_1400_add_lga_email_verification
Create Date: 2026-01-06 16:00:00.000000

Advanced Accounting Models:
- Accounting Dimensions (Department, Project, State, LGA)
- Purchase Orders & Goods Received Notes
- 3-Way Matching
- WHT Credit Note Vault
- Budget Management
- M-of-N Approval Workflows
- Immutable Ledger (Hash Chain)
- Entity Consolidation
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260106_1600_advanced_accounting'
down_revision = '20260106_1400_add_lga_email_verification'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create ENUM types
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE dimension_type AS ENUM ('department', 'project', 'cost_center', 'state', 'lga', 'custom');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE matching_status AS ENUM ('pending', 'matched', 'discrepancy', 'pending_review', 'rejected');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE wht_credit_status AS ENUM ('pending', 'received', 'matched', 'applied', 'expired', 'rejected');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE approval_status AS ENUM ('pending', 'approved', 'rejected', 'expired', 'cancelled');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE budget_period_type AS ENUM ('monthly', 'quarterly', 'annual');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Accounting Dimensions
    op.create_table(
        'accounting_dimensions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('dimension_type', postgresql.ENUM('department', 'project', 'cost_center', 'state', 'lga', 'custom', name='dimension_type', create_type=False), nullable=False),
        sa.Column('code', sa.String(50), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('parent_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('accounting_dimensions.id'), nullable=True),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        sa.Column('metadata', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, onupdate=sa.text('NOW()'), nullable=True),
    )
    op.create_index('ix_accounting_dimensions_entity_type', 'accounting_dimensions', ['entity_id', 'dimension_type'])
    op.create_unique_constraint('uq_dimension_entity_code', 'accounting_dimensions', ['entity_id', 'dimension_type', 'code'])
    
    # Transaction Dimensions (Many-to-Many with allocation)
    op.create_table(
        'transaction_dimensions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('transaction_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('transactions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('dimension_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('accounting_dimensions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('allocation_percentage', sa.Numeric(5, 2), default=100, nullable=False),
        sa.Column('allocated_amount', sa.Numeric(20, 2), nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_transaction_dimensions_transaction', 'transaction_dimensions', ['transaction_id'])
    op.create_index('ix_transaction_dimensions_dimension', 'transaction_dimensions', ['dimension_id'])
    
    # Purchase Orders
    op.create_table(
        'purchase_orders',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('vendor_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('vendors.id'), nullable=False),
        sa.Column('po_number', sa.String(50), nullable=False),
        sa.Column('po_date', sa.Date, nullable=False),
        sa.Column('expected_delivery_date', sa.Date, nullable=True),
        sa.Column('delivery_address', sa.Text, nullable=True),
        sa.Column('payment_terms', sa.String(200), nullable=True),
        sa.Column('subtotal', sa.Numeric(20, 2), nullable=False),
        sa.Column('vat_amount', sa.Numeric(20, 2), default=0, nullable=False),
        sa.Column('total_amount', sa.Numeric(20, 2), nullable=False),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('status', sa.String(50), default='draft', nullable=False),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('approved_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('approved_at', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, onupdate=sa.text('NOW()'), nullable=True),
    )
    op.create_index('ix_purchase_orders_entity', 'purchase_orders', ['entity_id'])
    op.create_index('ix_purchase_orders_vendor', 'purchase_orders', ['vendor_id'])
    op.create_unique_constraint('uq_po_entity_number', 'purchase_orders', ['entity_id', 'po_number'])
    
    # Purchase Order Items
    op.create_table(
        'purchase_order_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('purchase_order_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('purchase_orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('item_description', sa.String(500), nullable=False),
        sa.Column('quantity', sa.Numeric(15, 4), nullable=False),
        sa.Column('unit_of_measure', sa.String(50), nullable=True),
        sa.Column('unit_price', sa.Numeric(20, 4), nullable=False),
        sa.Column('vat_amount', sa.Numeric(20, 2), default=0, nullable=False),
        sa.Column('line_total', sa.Numeric(20, 2), nullable=False),
        sa.Column('inventory_item_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('inventory_items.id'), nullable=True),
        sa.Column('gl_account_code', sa.String(20), nullable=True),
    )
    op.create_index('ix_po_items_po', 'purchase_order_items', ['purchase_order_id'])
    
    # Goods Received Notes
    op.create_table(
        'goods_received_notes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('purchase_order_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('purchase_orders.id'), nullable=False),
        sa.Column('grn_number', sa.String(50), nullable=False),
        sa.Column('received_date', sa.Date, nullable=False),
        sa.Column('received_by', sa.String(200), nullable=True),
        sa.Column('delivery_note_number', sa.String(100), nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('status', sa.String(50), default='pending_inspection', nullable=False),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, onupdate=sa.text('NOW()'), nullable=True),
    )
    op.create_index('ix_grn_entity', 'goods_received_notes', ['entity_id'])
    op.create_index('ix_grn_po', 'goods_received_notes', ['purchase_order_id'])
    op.create_unique_constraint('uq_grn_entity_number', 'goods_received_notes', ['entity_id', 'grn_number'])
    
    # GRN Items
    op.create_table(
        'goods_received_note_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('grn_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('goods_received_notes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('po_item_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('purchase_order_items.id'), nullable=True),
        sa.Column('item_description', sa.String(500), nullable=False),
        sa.Column('quantity_received', sa.Numeric(15, 4), nullable=False),
        sa.Column('quantity_accepted', sa.Numeric(15, 4), nullable=False),
        sa.Column('quantity_rejected', sa.Numeric(15, 4), default=0, nullable=False),
        sa.Column('rejection_reason', sa.Text, nullable=True),
        sa.Column('inspection_notes', sa.Text, nullable=True),
        sa.Column('storage_location', sa.String(200), nullable=True),
    )
    op.create_index('ix_grn_items_grn', 'goods_received_note_items', ['grn_id'])
    
    # 3-Way Match Records
    op.create_table(
        'three_way_matches',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('purchase_order_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('purchase_orders.id'), nullable=False),
        sa.Column('grn_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('goods_received_notes.id'), nullable=True),
        sa.Column('invoice_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('invoices.id'), nullable=False),
        sa.Column('status', postgresql.ENUM('pending', 'matched', 'discrepancy', 'pending_review', 'rejected', name='matching_status', create_type=False), nullable=False),
        sa.Column('po_amount', sa.Numeric(20, 2), nullable=False),
        sa.Column('grn_quantity', sa.Numeric(15, 4), nullable=True),
        sa.Column('invoice_amount', sa.Numeric(20, 2), nullable=False),
        sa.Column('discrepancies', postgresql.JSONB, nullable=True),
        sa.Column('matched_at', sa.DateTime, nullable=True),
        sa.Column('resolved_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('resolution_notes', sa.Text, nullable=True),
        sa.Column('resolved_at', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_three_way_matches_entity', 'three_way_matches', ['entity_id'])
    op.create_index('ix_three_way_matches_status', 'three_way_matches', ['status'])
    
    # WHT Credit Notes
    op.create_table(
        'wht_credit_notes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('credit_note_number', sa.String(100), nullable=False),
        sa.Column('issue_date', sa.Date, nullable=False),
        sa.Column('issuer_name', sa.String(300), nullable=False),
        sa.Column('issuer_tin', sa.String(20), nullable=False),
        sa.Column('issuer_address', sa.Text, nullable=True),
        sa.Column('gross_amount', sa.Numeric(20, 2), nullable=False),
        sa.Column('wht_rate', sa.Numeric(5, 2), nullable=False),
        sa.Column('wht_amount', sa.Numeric(20, 2), nullable=False),
        sa.Column('wht_type', sa.String(50), nullable=False),
        sa.Column('tax_year', sa.Integer, nullable=False),
        sa.Column('status', postgresql.ENUM('pending', 'received', 'matched', 'applied', 'expired', 'rejected', name='wht_credit_status', create_type=False), nullable=False),
        sa.Column('matched_invoice_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('invoices.id'), nullable=True),
        sa.Column('matched_at', sa.DateTime, nullable=True),
        sa.Column('applied_tax_reference', sa.String(100), nullable=True),
        sa.Column('applied_at', sa.DateTime, nullable=True),
        sa.Column('applied_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('received_at', sa.DateTime, nullable=True),
        sa.Column('expires_at', sa.DateTime, nullable=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, onupdate=sa.text('NOW()'), nullable=True),
    )
    op.create_index('ix_wht_credit_notes_entity', 'wht_credit_notes', ['entity_id'])
    op.create_index('ix_wht_credit_notes_tax_year', 'wht_credit_notes', ['tax_year'])
    op.create_index('ix_wht_credit_notes_status', 'wht_credit_notes', ['status'])
    op.create_unique_constraint('uq_wht_credit_note', 'wht_credit_notes', ['entity_id', 'credit_note_number', 'issuer_tin'])
    
    # Budgets
    op.create_table(
        'budgets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('fiscal_year', sa.Integer, nullable=False),
        sa.Column('period_type', postgresql.ENUM('monthly', 'quarterly', 'annual', name='budget_period_type', create_type=False), nullable=False),
        sa.Column('start_date', sa.Date, nullable=False),
        sa.Column('end_date', sa.Date, nullable=False),
        sa.Column('total_revenue', sa.Numeric(20, 2), default=0, nullable=False),
        sa.Column('total_expense', sa.Numeric(20, 2), default=0, nullable=False),
        sa.Column('status', sa.String(50), default='draft', nullable=False),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('approved_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('approved_at', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, onupdate=sa.text('NOW()'), nullable=True),
    )
    op.create_index('ix_budgets_entity', 'budgets', ['entity_id'])
    op.create_index('ix_budgets_fiscal_year', 'budgets', ['fiscal_year'])
    
    # Budget Line Items
    op.create_table(
        'budget_line_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('budget_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('budgets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('account_code', sa.String(20), nullable=False),
        sa.Column('account_name', sa.String(200), nullable=False),
        sa.Column('line_type', sa.String(20), nullable=False),
        sa.Column('category_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('categories.id'), nullable=True),
        sa.Column('dimension_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('accounting_dimensions.id'), nullable=True),
        sa.Column('annual_amount', sa.Numeric(20, 2), nullable=False),
        sa.Column('jan_amount', sa.Numeric(20, 2), default=0),
        sa.Column('feb_amount', sa.Numeric(20, 2), default=0),
        sa.Column('mar_amount', sa.Numeric(20, 2), default=0),
        sa.Column('apr_amount', sa.Numeric(20, 2), default=0),
        sa.Column('may_amount', sa.Numeric(20, 2), default=0),
        sa.Column('jun_amount', sa.Numeric(20, 2), default=0),
        sa.Column('jul_amount', sa.Numeric(20, 2), default=0),
        sa.Column('aug_amount', sa.Numeric(20, 2), default=0),
        sa.Column('sep_amount', sa.Numeric(20, 2), default=0),
        sa.Column('oct_amount', sa.Numeric(20, 2), default=0),
        sa.Column('nov_amount', sa.Numeric(20, 2), default=0),
        sa.Column('dec_amount', sa.Numeric(20, 2), default=0),
        sa.Column('notes', sa.Text, nullable=True),
    )
    op.create_index('ix_budget_line_items_budget', 'budget_line_items', ['budget_id'])
    
    # Approval Workflows
    op.create_table(
        'approval_workflows',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('workflow_type', sa.String(50), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('required_approvers', sa.Integer, default=1, nullable=False),
        sa.Column('threshold_amount', sa.Numeric(20, 2), nullable=True),
        sa.Column('escalation_hours', sa.Integer, default=24, nullable=True),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, onupdate=sa.text('NOW()'), nullable=True),
    )
    op.create_index('ix_approval_workflows_entity', 'approval_workflows', ['entity_id'])
    op.create_index('ix_approval_workflows_type', 'approval_workflows', ['workflow_type'])
    
    # Approval Workflow Approvers
    op.create_table(
        'approval_workflow_approvers',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('workflow_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('approval_workflows.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('role', sa.String(50), nullable=True),
        sa.Column('approval_order', sa.Integer, default=1, nullable=False),
        sa.Column('can_delegate', sa.Boolean, default=False, nullable=False),
        sa.Column('is_required', sa.Boolean, default=False, nullable=False),
        sa.Column('delegated_from_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('delegation_expires', sa.DateTime, nullable=True),
    )
    op.create_index('ix_workflow_approvers_workflow', 'approval_workflow_approvers', ['workflow_id'])
    op.create_index('ix_workflow_approvers_user', 'approval_workflow_approvers', ['user_id'])
    
    # Approval Requests
    op.create_table(
        'approval_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('workflow_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('approval_workflows.id'), nullable=False),
        sa.Column('resource_type', sa.String(100), nullable=False),
        sa.Column('resource_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('amount', sa.Numeric(20, 2), nullable=True),
        sa.Column('status', postgresql.ENUM('pending', 'approved', 'rejected', 'expired', 'cancelled', name='approval_status', create_type=False), nullable=False),
        sa.Column('submitted_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('context', postgresql.JSONB, nullable=True),
        sa.Column('expires_at', sa.DateTime, nullable=True),
        sa.Column('completed_at', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_approval_requests_entity', 'approval_requests', ['entity_id'])
    op.create_index('ix_approval_requests_status', 'approval_requests', ['status'])
    op.create_index('ix_approval_requests_resource', 'approval_requests', ['resource_type', 'resource_id'])
    
    # Approval Decisions
    op.create_table(
        'approval_decisions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('request_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('approval_requests.id', ondelete='CASCADE'), nullable=False),
        sa.Column('approver_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('decision', sa.String(20), nullable=False),
        sa.Column('comments', sa.Text, nullable=True),
        sa.Column('decided_at', sa.DateTime, nullable=False),
    )
    op.create_index('ix_approval_decisions_request', 'approval_decisions', ['request_id'])
    op.create_index('ix_approval_decisions_approver', 'approval_decisions', ['approver_id'])
    
    # Immutable Ledger Entries
    op.create_table(
        'ledger_entries',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sequence_number', sa.BigInteger, nullable=False),
        sa.Column('entry_type', sa.String(50), nullable=False),
        sa.Column('resource_type', sa.String(100), nullable=False),
        sa.Column('resource_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('data_snapshot', postgresql.JSONB, nullable=False),
        sa.Column('previous_hash', sa.String(64), nullable=True),
        sa.Column('entry_hash', sa.String(64), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_ledger_entries_entity_seq', 'ledger_entries', ['entity_id', 'sequence_number'])
    op.create_index('ix_ledger_entries_resource', 'ledger_entries', ['resource_type', 'resource_id'])
    op.create_unique_constraint('uq_ledger_entity_sequence', 'ledger_entries', ['entity_id', 'sequence_number'])
    
    # Entity Groups (for consolidation)
    op.create_table(
        'entity_groups',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('consolidation_currency', sa.String(3), default='NGN', nullable=False),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime, onupdate=sa.text('NOW()'), nullable=True),
    )
    op.create_index('ix_entity_groups_org', 'entity_groups', ['organization_id'])
    
    # Entity Group Members
    op.create_table(
        'entity_group_members',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('group_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('entity_groups.id', ondelete='CASCADE'), nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ownership_percentage', sa.Numeric(5, 2), default=100, nullable=False),
        sa.Column('is_parent', sa.Boolean, default=False, nullable=False),
        sa.Column('consolidation_method', sa.String(50), default='full', nullable=False),
        sa.Column('joined_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_entity_group_members_group', 'entity_group_members', ['group_id'])
    op.create_unique_constraint('uq_entity_group_member', 'entity_group_members', ['group_id', 'entity_id'])
    
    # Intercompany Transactions
    op.create_table(
        'intercompany_transactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('group_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('entity_groups.id', ondelete='CASCADE'), nullable=False),
        sa.Column('source_entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id'), nullable=False),
        sa.Column('target_entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id'), nullable=False),
        sa.Column('source_transaction_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('transactions.id'), nullable=True),
        sa.Column('target_transaction_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('transactions.id'), nullable=True),
        sa.Column('amount', sa.Numeric(20, 2), nullable=False),
        sa.Column('transaction_type', sa.String(50), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('is_eliminated', sa.Boolean, default=False, nullable=False),
        sa.Column('eliminated_at', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_intercompany_txn_group', 'intercompany_transactions', ['group_id'])
    op.create_index('ix_intercompany_txn_source', 'intercompany_transactions', ['source_entity_id'])
    op.create_index('ix_intercompany_txn_target', 'intercompany_transactions', ['target_entity_id'])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('intercompany_transactions')
    op.drop_table('entity_group_members')
    op.drop_table('entity_groups')
    op.drop_table('ledger_entries')
    op.drop_table('approval_decisions')
    op.drop_table('approval_requests')
    op.drop_table('approval_workflow_approvers')
    op.drop_table('approval_workflows')
    op.drop_table('budget_line_items')
    op.drop_table('budgets')
    op.drop_table('wht_credit_notes')
    op.drop_table('three_way_matches')
    op.drop_table('goods_received_note_items')
    op.drop_table('goods_received_notes')
    op.drop_table('purchase_order_items')
    op.drop_table('purchase_orders')
    op.drop_table('transaction_dimensions')
    op.drop_table('accounting_dimensions')
    
    # Drop ENUM types
    op.execute('DROP TYPE IF EXISTS budget_period_type CASCADE')
    op.execute('DROP TYPE IF EXISTS approval_status CASCADE')
    op.execute('DROP TYPE IF EXISTS wht_credit_status CASCADE')
    op.execute('DROP TYPE IF EXISTS matching_status CASCADE')
    op.execute('DROP TYPE IF EXISTS dimension_type CASCADE')
