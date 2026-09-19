"""2026 Tax Reform Updates - Buyer Review, VAT Recovery, Development Levy, PIT Reliefs, Business Type

Revision ID: 2026_tax_reform
Revises: 864ffbd2f5c4
Create Date: 2026-01-03 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2026_tax_reform'
down_revision: Union[str, None] = '864ffbd2f5c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create ENUMs
    buyer_status_enum = postgresql.ENUM('pending', 'accepted', 'rejected', name='buyerstatus', create_type=False)
    buyer_status_enum.create(op.get_bind(), checkfirst=True)
    
    business_type_enum = postgresql.ENUM('business_name', 'limited_company', name='businesstype', create_type=False)
    business_type_enum.create(op.get_bind(), checkfirst=True)
    
    vat_recovery_type_enum = postgresql.ENUM('stock_in_trade', 'capital_expenditure', 'services', name='vatrecoverytype', create_type=False)
    vat_recovery_type_enum.create(op.get_bind(), checkfirst=True)
    
    relief_type_enum = postgresql.ENUM('rent', 'life_insurance', 'nhf', 'pension', 'nhis', 'gratuity', 'other', name='relieftype', create_type=False)
    relief_type_enum.create(op.get_bind(), checkfirst=True)
    
    # =====================================================
    # INVOICE TABLE - Add buyer review fields
    # =====================================================
    op.add_column('invoices', sa.Column('buyer_status', buyer_status_enum, nullable=True, server_default='pending'))
    op.add_column('invoices', sa.Column('buyer_response_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('invoices', sa.Column('credit_note_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('invoices', sa.Column('is_credit_note', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('invoices', sa.Column('original_invoice_id', postgresql.UUID(as_uuid=True), nullable=True))
    
    # =====================================================
    # BUSINESS ENTITY TABLE - Add business type and thresholds
    # =====================================================
    op.add_column('business_entities', sa.Column('business_type', business_type_enum, nullable=False, server_default='limited_company'))
    op.add_column('business_entities', sa.Column('annual_turnover', sa.Numeric(precision=15, scale=2), nullable=True))
    op.add_column('business_entities', sa.Column('fixed_assets_value', sa.Numeric(precision=15, scale=2), nullable=True))
    op.add_column('business_entities', sa.Column('is_development_levy_exempt', sa.Boolean(), nullable=False, server_default='false'))
    
    # =====================================================
    # CREATE VAT RECOVERY AUDIT TABLE
    # =====================================================
    op.create_table(
        'vat_recovery_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('transaction_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('transactions.id', ondelete='SET NULL'), nullable=True),
        
        # VAT Details
        sa.Column('vat_amount', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('recovery_type', vat_recovery_type_enum, nullable=False),
        sa.Column('is_recoverable', sa.Boolean(), nullable=False, default=True),
        sa.Column('non_recovery_reason', sa.String(500), nullable=True),
        
        # NRS Validation
        sa.Column('vendor_irn', sa.String(100), nullable=True, comment='Vendor NRS Invoice Reference Number'),
        sa.Column('has_valid_irn', sa.Boolean(), nullable=False, default=False),
        
        # Description
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('vendor_name', sa.String(255), nullable=True),
        sa.Column('vendor_tin', sa.String(20), nullable=True),
        
        # Period
        sa.Column('transaction_date', sa.Date(), nullable=False),
        sa.Column('recovery_period_year', sa.Integer(), nullable=False),
        sa.Column('recovery_period_month', sa.Integer(), nullable=False),
        
        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    
    # =====================================================
    # CREATE DEVELOPMENT LEVY RECORDS TABLE
    # =====================================================
    op.create_table(
        'development_levy_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='CASCADE'), nullable=False, index=True),
        
        # Period
        sa.Column('fiscal_year', sa.Integer(), nullable=False),
        
        # Calculation
        sa.Column('assessable_profit', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('levy_rate', sa.Numeric(precision=5, scale=4), nullable=False, server_default='0.04'),  # 4%
        sa.Column('levy_amount', sa.Numeric(precision=15, scale=2), nullable=False),
        
        # Eligibility
        sa.Column('turnover', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('fixed_assets', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('is_exempt', sa.Boolean(), nullable=False, default=False),
        sa.Column('exemption_reason', sa.String(500), nullable=True),
        
        # Filing
        sa.Column('is_filed', sa.Boolean(), nullable=False, default=False),
        sa.Column('filed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('payment_reference', sa.String(100), nullable=True),
        
        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        
        # Unique constraint
        sa.UniqueConstraint('entity_id', 'fiscal_year', name='uq_dev_levy_entity_year'),
    )
    
    # =====================================================
    # CREATE PIT RELIEF DOCUMENTS TABLE
    # =====================================================
    op.create_table(
        'pit_relief_documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        
        # Relief Details
        sa.Column('relief_type', relief_type_enum, nullable=False),
        sa.Column('fiscal_year', sa.Integer(), nullable=False),
        
        # Amounts
        sa.Column('claimed_amount', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('allowed_amount', sa.Numeric(precision=15, scale=2), nullable=True),  # After cap applied
        
        # For Rent Relief
        sa.Column('annual_rent', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('rent_relief_cap', sa.Numeric(precision=15, scale=2), nullable=True, server_default='500000'),  # ₦500,000 cap
        
        # Document
        sa.Column('document_url', sa.String(500), nullable=True),
        sa.Column('document_name', sa.String(255), nullable=True),
        sa.Column('document_type', sa.String(50), nullable=True),  # PDF, Image, etc.
        
        # Verification
        sa.Column('is_verified', sa.Boolean(), nullable=False, default=False),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('verified_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('verification_notes', sa.Text(), nullable=True),
        
        # Status
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),  # pending, approved, rejected
        
        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    
    # =====================================================
    # CREATE CREDIT NOTES TABLE
    # =====================================================
    op.create_table(
        'credit_notes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('original_invoice_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('invoices.id', ondelete='SET NULL'), nullable=True),
        
        # Credit Note Details
        sa.Column('credit_note_number', sa.String(50), nullable=False),
        sa.Column('issue_date', sa.Date(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        
        # Amounts (reversed from original)
        sa.Column('subtotal', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('vat_amount', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('total_amount', sa.Numeric(precision=15, scale=2), nullable=False),
        
        # NRS
        sa.Column('nrs_irn', sa.String(100), nullable=True, unique=True),
        sa.Column('nrs_submitted_at', sa.DateTime(timezone=True), nullable=True),
        
        # Status
        sa.Column('status', sa.String(20), nullable=False, server_default='draft'),  # draft, submitted, accepted
        
        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    
    # Add foreign key for credit_note_id in invoices
    op.create_foreign_key('fk_invoice_credit_note', 'invoices', 'credit_notes', ['credit_note_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_invoice_original', 'invoices', 'invoices', ['original_invoice_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    # Drop foreign keys
    op.drop_constraint('fk_invoice_credit_note', 'invoices', type_='foreignkey')
    op.drop_constraint('fk_invoice_original', 'invoices', type_='foreignkey')
    
    # Drop tables
    op.drop_table('credit_notes')
    op.drop_table('pit_relief_documents')
    op.drop_table('development_levy_records')
    op.drop_table('vat_recovery_records')
    
    # Drop columns from invoices
    op.drop_column('invoices', 'original_invoice_id')
    op.drop_column('invoices', 'is_credit_note')
    op.drop_column('invoices', 'credit_note_id')
    op.drop_column('invoices', 'buyer_response_at')
    op.drop_column('invoices', 'buyer_status')
    
    # Drop columns from business_entities
    op.drop_column('business_entities', 'is_development_levy_exempt')
    op.drop_column('business_entities', 'fixed_assets_value')
    op.drop_column('business_entities', 'annual_turnover')
    op.drop_column('business_entities', 'business_type')
    
    # Drop ENUMs
    sa.Enum(name='relieftype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='vatrecoverytype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='businesstype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='buyerstatus').drop(op.get_bind(), checkfirst=True)
