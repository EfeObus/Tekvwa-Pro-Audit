"""Add fixed assets tables for 2026 compliance

Revision ID: 20260103_1600_add_fixed_assets
Revises: 20260103_1530_rbac_implementation
Create Date: 2026-01-03 16:00:00.000000

This migration adds tables for Fixed Asset Register tracking:
- fixed_assets: Main asset register with depreciation and disposal fields
- depreciation_entries: Period-by-period depreciation tracking

2026 Compliance:
- Capital gains on disposal taxed at CIT rate (not separate CGT)
- VAT recovery on qualifying capital assets via vendor IRN
- Integration with Development Levy threshold calculation
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '20260103_1600_add_fixed_assets'
down_revision = '20260103_1530_rbac_implementation'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create fixed assets tables."""
    
    # Check if fixed_assets table exists
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    existing_tables = inspector.get_table_names()
    
    # Create asset category enum if not exists
    asset_category = postgresql.ENUM(
        'land', 'buildings', 'plant_machinery', 'furniture_fittings',
        'motor_vehicles', 'computer_equipment', 'office_equipment',
        'leasehold_improvements', 'intangible_assets', 'other',
        name='assetcategory',
        create_type=False
    )
    
    asset_status = postgresql.ENUM(
        'active', 'disposed', 'written_off', 'under_repair', 'idle',
        name='assetstatus',
        create_type=False
    )
    
    depreciation_method = postgresql.ENUM(
        'straight_line', 'reducing_balance', 'units_of_production',
        name='depreciationmethod',
        create_type=False
    )
    
    disposal_type = postgresql.ENUM(
        'sale', 'trade_in', 'scrapped', 'donated', 'theft', 'insurance_claim',
        name='disposaltype',
        create_type=False
    )
    
    # Create enums
    try:
        asset_category.create(connection, checkfirst=True)
    except Exception:
        pass
    
    try:
        asset_status.create(connection, checkfirst=True)
    except Exception:
        pass
    
    try:
        depreciation_method.create(connection, checkfirst=True)
    except Exception:
        pass
    
    try:
        disposal_type.create(connection, checkfirst=True)
    except Exception:
        pass
    
    # Create fixed_assets table
    if 'fixed_assets' not in existing_tables:
        op.create_table(
            'fixed_assets',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
            sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='CASCADE'), nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('description', sa.Text, nullable=True),
            sa.Column('asset_code', sa.String(50), unique=True, nullable=False),
            sa.Column('category', asset_category, nullable=False),
            sa.Column('status', asset_status, server_default='active', nullable=False),
            
            # Acquisition details
            sa.Column('acquisition_date', sa.Date, nullable=False),
            sa.Column('acquisition_cost', sa.Numeric(15, 2), nullable=False),
            sa.Column('vendor_name', sa.String(255), nullable=True),
            sa.Column('vendor_irn', sa.String(50), nullable=True, comment='Invoice Reference Number for VAT recovery'),
            sa.Column('invoice_number', sa.String(100), nullable=True),
            
            # Depreciation settings
            sa.Column('depreciation_method', depreciation_method, server_default='straight_line', nullable=False),
            sa.Column('useful_life_years', sa.Integer, nullable=True),
            sa.Column('depreciation_rate', sa.Numeric(5, 2), nullable=False),
            sa.Column('residual_value', sa.Numeric(15, 2), server_default='0', nullable=False),
            sa.Column('accumulated_depreciation', sa.Numeric(15, 2), server_default='0', nullable=False),
            sa.Column('depreciation_start_date', sa.Date, nullable=True),
            sa.Column('last_depreciation_date', sa.Date, nullable=True),
            
            # Disposal details
            sa.Column('disposal_date', sa.Date, nullable=True),
            sa.Column('disposal_type', disposal_type, nullable=True),
            sa.Column('disposal_proceeds', sa.Numeric(15, 2), nullable=True),
            sa.Column('disposal_buyer_name', sa.String(255), nullable=True),
            sa.Column('disposal_buyer_tin', sa.String(20), nullable=True),
            sa.Column('disposal_notes', sa.Text, nullable=True),
            
            # Physical details
            sa.Column('serial_number', sa.String(100), nullable=True),
            sa.Column('location', sa.String(255), nullable=True),
            sa.Column('condition', sa.String(100), nullable=True),
            
            # Insurance
            sa.Column('is_insured', sa.Boolean, server_default='false', nullable=False),
            sa.Column('insurance_policy_number', sa.String(100), nullable=True),
            sa.Column('insurance_value', sa.Numeric(15, 2), nullable=True),
            sa.Column('insurance_expiry_date', sa.Date, nullable=True),
            
            # VAT Recovery tracking
            sa.Column('vat_recovery_eligible', sa.Boolean, server_default='false', nullable=False),
            sa.Column('vat_amount', sa.Numeric(15, 2), nullable=True),
            sa.Column('vat_recovery_claimed', sa.Boolean, server_default='false', nullable=False),
            sa.Column('vat_recovery_date', sa.Date, nullable=True),
            
            # Audit fields
            sa.Column('created_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('updated_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('disposed_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now(), nullable=True),
        )
        
        # Create indexes
        op.create_index('ix_fixed_assets_entity_id', 'fixed_assets', ['entity_id'])
        op.create_index('ix_fixed_assets_asset_code', 'fixed_assets', ['asset_code'])
        op.create_index('ix_fixed_assets_category', 'fixed_assets', ['category'])
        op.create_index('ix_fixed_assets_status', 'fixed_assets', ['status'])
        op.create_index('ix_fixed_assets_vendor_irn', 'fixed_assets', ['vendor_irn'])
        
        print("Created fixed_assets table")
    else:
        print("fixed_assets table already exists, skipping...")
    
    # Create depreciation_entries table
    if 'depreciation_entries' not in existing_tables:
        op.create_table(
            'depreciation_entries',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
            sa.Column('asset_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('fixed_assets.id', ondelete='CASCADE'), nullable=False),
            sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_entities.id', ondelete='CASCADE'), nullable=False),
            
            # Period details
            sa.Column('fiscal_year_end', sa.Date, nullable=False),
            sa.Column('period_start', sa.Date, nullable=False),
            sa.Column('period_end', sa.Date, nullable=False),
            
            # Values
            sa.Column('opening_book_value', sa.Numeric(15, 2), nullable=False),
            sa.Column('depreciation_amount', sa.Numeric(15, 2), nullable=False),
            sa.Column('closing_book_value', sa.Numeric(15, 2), nullable=False),
            sa.Column('depreciation_rate_used', sa.Numeric(5, 2), nullable=False),
            
            # Posting info
            sa.Column('is_posted', sa.Boolean, server_default='false', nullable=False),
            sa.Column('posted_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('notes', sa.Text, nullable=True),
            
            # Audit
            sa.Column('created_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        
        # Create indexes
        op.create_index('ix_depreciation_entries_asset_id', 'depreciation_entries', ['asset_id'])
        op.create_index('ix_depreciation_entries_entity_id', 'depreciation_entries', ['entity_id'])
        op.create_index('ix_depreciation_entries_fiscal_year', 'depreciation_entries', ['fiscal_year_end'])
        op.create_index(
            'ix_depreciation_unique_period', 
            'depreciation_entries', 
            ['asset_id', 'fiscal_year_end', 'period_start', 'period_end'],
            unique=True
        )
        
        print("Created depreciation_entries table")
    else:
        print("depreciation_entries table already exists, skipping...")


def downgrade() -> None:
    """Drop fixed assets tables."""
    op.drop_table('depreciation_entries')
    op.drop_table('fixed_assets')
    
    # Drop enums
    sa.Enum(name='disposaltype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='depreciationmethod').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='assetstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='assetcategory').drop(op.get_bind(), checkfirst=True)
