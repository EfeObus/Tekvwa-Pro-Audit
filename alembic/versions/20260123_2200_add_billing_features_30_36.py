"""Add billing features for issues #30-36

Revision ID: 20260123_2200
Revises: 20260123_2100
Create Date: 2026-01-23 22:00:00.000000

Features:
- #30: Usage report generation (scheduled reports table)
- #31: Billing cycle alignment (anchor date, proration)
- #32: Subscription pause/resume (paused_at, pause_until)
- #33: Service credits for outages (service_credits table)
- #34: Discount/referral codes (discount_codes table)
- #35: Volume discount logic (volume_discount_rules table)
- #36: Multi-currency support (currency fields, exchange rates)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260123_2200'
down_revision = '20260123_2100'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================================================
    # ISSUE #31 & #32 & #36: Add new fields to tenant_skus table
    # ==========================================================================
    
    # #31: Billing cycle alignment
    op.add_column('tenant_skus', sa.Column(
        'billing_anchor_day',
        sa.Integer(),
        nullable=True,
        comment='Day of month for billing (1-28). Null = subscription start date'
    ))
    op.add_column('tenant_skus', sa.Column(
        'align_to_calendar_month',
        sa.Boolean(),
        server_default='false',
        nullable=False,
        comment='If true, align billing to 1st of month'
    ))
    op.add_column('tenant_skus', sa.Column(
        'prorated_first_period',
        sa.Boolean(),
        server_default='true',
        nullable=False,
        comment='If true, prorate first billing period'
    ))
    
    # #32: Subscription pause/resume
    op.add_column('tenant_skus', sa.Column(
        'paused_at',
        sa.DateTime(timezone=True),
        nullable=True,
        comment='When subscription was paused (null if not paused)'
    ))
    op.add_column('tenant_skus', sa.Column(
        'pause_reason',
        sa.String(500),
        nullable=True,
        comment='Reason for pausing subscription'
    ))
    op.add_column('tenant_skus', sa.Column(
        'pause_until',
        sa.DateTime(timezone=True),
        nullable=True,
        comment='When to automatically resume (max 90 days from pause)'
    ))
    op.add_column('tenant_skus', sa.Column(
        'pause_credits_days',
        sa.Integer(),
        server_default='0',
        nullable=False,
        comment='Days credited when paused (extends subscription)'
    ))
    op.add_column('tenant_skus', sa.Column(
        'total_paused_days',
        sa.Integer(),
        server_default='0',
        nullable=False,
        comment='Total cumulative days subscription has been paused'
    ))
    op.add_column('tenant_skus', sa.Column(
        'pause_count_this_year',
        sa.Integer(),
        server_default='0',
        nullable=False,
        comment='Number of times paused this calendar year (max 2 allowed)'
    ))
    op.add_column('tenant_skus', sa.Column(
        'last_pause_year',
        sa.Integer(),
        nullable=True,
        comment='Calendar year of pause count tracking (resets annually)'
    ))
    
    # #36: Multi-currency support
    op.add_column('tenant_skus', sa.Column(
        'preferred_currency',
        sa.String(3),
        server_default='NGN',
        nullable=False,
        comment='Preferred billing currency (NGN, USD, EUR, GBP)'
    ))
    op.add_column('tenant_skus', sa.Column(
        'locked_exchange_rate',
        sa.Numeric(12, 6),
        nullable=True,
        comment='Locked exchange rate for this subscription (null = use current)'
    ))
    
    # ==========================================================================
    # ISSUE #33: Service Credits Table
    # ==========================================================================
    op.create_table(
        'service_credits',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        
        # Credit details
        sa.Column('credit_type', sa.String(50), nullable=False, comment='sla_breach, goodwill, promotion, referral_reward'),
        sa.Column('amount_ngn', sa.Integer(), nullable=False, comment='Credit amount in Naira'),
        sa.Column('amount_usd', sa.Numeric(10, 2), nullable=True, comment='Credit amount in USD (for multi-currency)'),
        sa.Column('currency', sa.String(3), server_default='NGN', nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        
        # SLA breach details (if applicable)
        sa.Column('incident_id', sa.String(100), nullable=True, comment='Reference to incident/outage'),
        sa.Column('incident_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('downtime_minutes', sa.Integer(), nullable=True),
        sa.Column('availability_percentage', sa.Numeric(5, 2), nullable=True),
        
        # Status
        sa.Column('status', sa.String(20), server_default='pending', nullable=False, comment='pending, approved, applied, expired, rejected'),
        sa.Column('approved_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        
        # Application
        sa.Column('applied_to_invoice_id', sa.String(100), nullable=True, comment='Invoice where credit was applied'),
        sa.Column('applied_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('amount_applied_ngn', sa.Integer(), nullable=True, comment='Actual amount applied'),
        
        # Expiry
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True, comment='Credit expires after 12 months'),
        
        # Notes
        sa.Column('admin_notes', sa.Text(), nullable=True),
        
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_service_credits_organization', 'service_credits', ['organization_id'])
    op.create_index('ix_service_credits_status', 'service_credits', ['status'])
    op.create_index('ix_service_credits_type', 'service_credits', ['credit_type'])
    op.create_index('ix_service_credits_expires', 'service_credits', ['expires_at'])
    
    # ==========================================================================
    # ISSUE #34: Discount Codes Table
    # ==========================================================================
    op.create_table(
        'discount_codes',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        
        # Code details
        sa.Column('code', sa.String(50), nullable=False, unique=True, comment='Unique discount code (e.g., WELCOME20)'),
        sa.Column('name', sa.String(100), nullable=False, comment='Display name for the discount'),
        sa.Column('description', sa.Text(), nullable=True),
        
        # Discount type and value
        sa.Column('discount_type', sa.String(20), nullable=False, comment='percentage, fixed_amount, free_months'),
        sa.Column('discount_value', sa.Numeric(10, 2), nullable=False, comment='Percentage (0-100), amount in Naira, or months'),
        sa.Column('max_discount_ngn', sa.Integer(), nullable=True, comment='Cap on discount amount (for percentage discounts)'),
        
        # Applicability
        sa.Column('applies_to_tiers', postgresql.ARRAY(sa.String()), nullable=True, comment='Null = all tiers, or ["core", "professional"]'),
        sa.Column('applies_to_billing_cycles', postgresql.ARRAY(sa.String()), nullable=True, comment='Null = all, or ["monthly", "annual"]'),
        sa.Column('min_subscription_months', sa.Integer(), nullable=True, comment='Minimum commitment for discount'),
        sa.Column('first_payment_only', sa.Boolean(), server_default='true', nullable=False),
        
        # Usage limits
        sa.Column('max_uses_total', sa.Integer(), nullable=True, comment='Null = unlimited'),
        sa.Column('max_uses_per_org', sa.Integer(), server_default='1', nullable=False),
        sa.Column('current_uses', sa.Integer(), server_default='0', nullable=False),
        
        # Validity period
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True, comment='Null = never expires'),
        
        # Referral link (if this is a referral code)
        sa.Column('is_referral_code', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('referrer_organization_id', postgresql.UUID(as_uuid=True), nullable=True, comment='Org that owns this referral code'),
        sa.Column('referrer_reward_type', sa.String(20), nullable=True, comment='credit, percentage, free_months'),
        sa.Column('referrer_reward_value', sa.Numeric(10, 2), nullable=True),
        
        # Status
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_discount_codes_code', 'discount_codes', ['code'], unique=True)
    op.create_index('ix_discount_codes_active', 'discount_codes', ['is_active'])
    op.create_index('ix_discount_codes_referrer', 'discount_codes', ['referrer_organization_id'])
    
    # Discount code usage tracking
    op.create_table(
        'discount_code_usages',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        
        sa.Column('discount_code_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('discount_codes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        
        # Usage details
        sa.Column('payment_reference', sa.String(100), nullable=True),
        sa.Column('original_amount_ngn', sa.Integer(), nullable=False),
        sa.Column('discount_amount_ngn', sa.Integer(), nullable=False),
        sa.Column('final_amount_ngn', sa.Integer(), nullable=False),
        
        # Referrer reward (if applicable)
        sa.Column('referrer_reward_issued', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('referrer_credit_id', postgresql.UUID(as_uuid=True), nullable=True),
        
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_discount_usage_code', 'discount_code_usages', ['discount_code_id'])
    op.create_index('ix_discount_usage_org', 'discount_code_usages', ['organization_id'])
    
    # ==========================================================================
    # ISSUE #35: Volume Discount Rules Table
    # ==========================================================================
    op.create_table(
        'volume_discount_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        
        # Rule identification
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        
        # Rule type
        sa.Column('rule_type', sa.String(30), nullable=False, 
                  comment='user_count, entity_count, commitment_months, combined'),
        
        # Thresholds
        sa.Column('min_users', sa.Integer(), nullable=True, comment='Minimum users for this discount'),
        sa.Column('max_users', sa.Integer(), nullable=True, comment='Maximum users (null = unlimited)'),
        sa.Column('min_entities', sa.Integer(), nullable=True),
        sa.Column('max_entities', sa.Integer(), nullable=True),
        sa.Column('min_commitment_months', sa.Integer(), nullable=True, comment='12, 24, 36 month commitments'),
        
        # Discount
        sa.Column('discount_percentage', sa.Numeric(5, 2), nullable=False, comment='Percentage off base price'),
        
        # Applicability
        sa.Column('applies_to_tier', sa.String(20), nullable=True, comment='Null = all tiers'),
        sa.Column('applies_to_currency', sa.String(3), nullable=True, comment='Null = all currencies'),
        
        # Priority (higher = applied first)
        sa.Column('priority', sa.Integer(), server_default='0', nullable=False),
        sa.Column('stackable', sa.Boolean(), server_default='false', nullable=False, 
                  comment='Can combine with other volume discounts'),
        
        # Status
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('effective_until', sa.Date(), nullable=True),
        
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_volume_rules_active', 'volume_discount_rules', ['is_active'])
    op.create_index('ix_volume_rules_type', 'volume_discount_rules', ['rule_type'])
    
    # ==========================================================================
    # ISSUE #36: Exchange Rates Table
    # ==========================================================================
    op.create_table(
        'exchange_rates',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        
        # Currency pair
        sa.Column('from_currency', sa.String(3), nullable=False, comment='Source currency (e.g., USD)'),
        sa.Column('to_currency', sa.String(3), nullable=False, comment='Target currency (e.g., NGN)'),
        
        # Rate
        sa.Column('rate', sa.Numeric(18, 6), nullable=False, comment='1 from_currency = rate to_currency'),
        sa.Column('rate_date', sa.Date(), nullable=False),
        
        # Source
        sa.Column('source', sa.String(50), nullable=True, comment='CBN, manual, api'),
        
        # For billing (we use a fixed rate for billing to avoid fluctuations)
        sa.Column('is_billing_rate', sa.Boolean(), server_default='false', nullable=False),
        
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_exchange_rates_pair', 'exchange_rates', ['from_currency', 'to_currency'])
    op.create_index('ix_exchange_rates_date', 'exchange_rates', ['rate_date'])
    op.create_index('ix_exchange_rates_billing', 'exchange_rates', ['is_billing_rate'])
    
    # Add unique constraint for billing rates per currency pair
    op.create_unique_constraint(
        'uq_exchange_rates_billing_pair',
        'exchange_rates',
        ['from_currency', 'to_currency', 'is_billing_rate'],
    )
    
    # ==========================================================================
    # ISSUE #30: Scheduled Usage Reports Table
    # ==========================================================================
    op.create_table(
        'scheduled_usage_reports',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        
        # Schedule
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('frequency', sa.String(20), nullable=False, comment='daily, weekly, monthly, quarterly'),
        sa.Column('day_of_week', sa.Integer(), nullable=True, comment='0-6 for weekly reports'),
        sa.Column('day_of_month', sa.Integer(), nullable=True, comment='1-28 for monthly reports'),
        
        # Report configuration
        sa.Column('report_type', sa.String(30), nullable=False, comment='usage_summary, detailed_usage, billing_history'),
        sa.Column('format', sa.String(10), nullable=False, comment='csv, pdf, excel'),
        sa.Column('include_charts', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('date_range_months', sa.Integer(), server_default='1', nullable=False),
        
        # Delivery
        sa.Column('delivery_method', sa.String(20), nullable=False, comment='email, download, both'),
        sa.Column('email_recipients', postgresql.ARRAY(sa.String()), nullable=True),
        
        # Status
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_scheduled_reports_org', 'scheduled_usage_reports', ['organization_id'])
    op.create_index('ix_scheduled_reports_next', 'scheduled_usage_reports', ['next_run_at'])
    
    # Generated reports history
    op.create_table(
        'usage_report_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('scheduled_report_id', postgresql.UUID(as_uuid=True), nullable=True, comment='Null if ad-hoc report'),
        sa.Column('generated_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        
        # Report details
        sa.Column('report_type', sa.String(30), nullable=False),
        sa.Column('format', sa.String(10), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        
        # File
        sa.Column('file_path', sa.String(500), nullable=True),
        sa.Column('file_size_bytes', sa.Integer(), nullable=True),
        sa.Column('download_count', sa.Integer(), server_default='0', nullable=False),
        
        # Delivery status
        sa.Column('email_sent', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('email_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('email_recipients', postgresql.ARRAY(sa.String()), nullable=True),
        
        # Expiry (auto-delete after 90 days)
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_report_history_org', 'usage_report_history', ['organization_id'])
    op.create_index('ix_report_history_expires', 'usage_report_history', ['expires_at'])
    
    # ==========================================================================
    # ISSUE #36: Add multi-currency pricing to sku_pricing table
    # ==========================================================================
    op.add_column('sku_pricing', sa.Column(
        'base_price_monthly_usd',
        sa.Numeric(10, 2),
        nullable=True,
        comment='Monthly price in USD for international customers'
    ))
    op.add_column('sku_pricing', sa.Column(
        'base_price_annual_usd',
        sa.Numeric(10, 2),
        nullable=True,
        comment='Annual price in USD'
    ))
    op.add_column('sku_pricing', sa.Column(
        'base_price_monthly_eur',
        sa.Numeric(10, 2),
        nullable=True,
        comment='Monthly price in EUR'
    ))
    op.add_column('sku_pricing', sa.Column(
        'base_price_annual_eur',
        sa.Numeric(10, 2),
        nullable=True,
        comment='Annual price in EUR'
    ))
    op.add_column('sku_pricing', sa.Column(
        'base_price_monthly_gbp',
        sa.Numeric(10, 2),
        nullable=True,
        comment='Monthly price in GBP'
    ))
    op.add_column('sku_pricing', sa.Column(
        'base_price_annual_gbp',
        sa.Numeric(10, 2),
        nullable=True,
        comment='Annual price in GBP'
    ))
    
    # ==========================================================================
    # Insert default data
    # ==========================================================================
    
    # Insert default volume discount rules
    op.execute("""
        INSERT INTO volume_discount_rules 
        (name, description, rule_type, min_users, discount_percentage, applies_to_tier, priority, is_active, effective_from)
        VALUES 
        ('10+ Users', '5% discount for 10+ users', 'user_count', 10, 5.00, NULL, 10, true, '2026-01-01'),
        ('25+ Users', '10% discount for 25+ users', 'user_count', 25, 10.00, NULL, 20, true, '2026-01-01'),
        ('50+ Users', '15% discount for 50+ users', 'user_count', 50, 15.00, NULL, 30, true, '2026-01-01'),
        ('100+ Users', '20% discount for 100+ users', 'user_count', 100, 20.00, NULL, 40, true, '2026-01-01'),
        ('5+ Entities', '5% discount for 5+ entities', 'entity_count', NULL, 5.00, 'enterprise', 15, true, '2026-01-01'),
        ('10+ Entities', '10% discount for 10+ entities', 'entity_count', NULL, 10.00, 'enterprise', 25, true, '2026-01-01'),
        ('2-Year Commitment', '10% discount for 24-month commitment', 'commitment_months', NULL, 10.00, NULL, 50, true, '2026-01-01'),
        ('3-Year Commitment', '20% discount for 36-month commitment', 'commitment_months', NULL, 20.00, NULL, 60, true, '2026-01-01');
    """)
    
    # Update volume discount rules with entity thresholds
    op.execute("""        UPDATE volume_discount_rules SET min_entities = 5 WHERE name = '5+ Entities';
    """)
    op.execute("""        UPDATE volume_discount_rules SET min_entities = 10 WHERE name = '10+ Entities';
    """)
    op.execute("""        UPDATE volume_discount_rules SET min_commitment_months = 24 WHERE name = '2-Year Commitment';
    """)
    op.execute("""        UPDATE volume_discount_rules SET min_commitment_months = 36 WHERE name = '3-Year Commitment';
    """)
    
    # Insert default exchange rates (for billing)
    op.execute("""
        INSERT INTO exchange_rates 
        (from_currency, to_currency, rate, rate_date, source, is_billing_rate)
        VALUES 
        ('USD', 'NGN', 1550.00, '2026-01-01', 'manual', true),
        ('EUR', 'NGN', 1700.00, '2026-01-01', 'manual', true),
        ('GBP', 'NGN', 1950.00, '2026-01-01', 'manual', true),
        ('NGN', 'USD', 0.000645, '2026-01-01', 'manual', true),
        ('NGN', 'EUR', 0.000588, '2026-01-01', 'manual', true),
        ('NGN', 'GBP', 0.000513, '2026-01-01', 'manual', true);
    """)
    
    # Insert default promo codes
    op.execute("""
        INSERT INTO discount_codes 
        (code, name, description, discount_type, discount_value, max_discount_ngn, 
         first_payment_only, max_uses_total, valid_from, valid_until, is_active)
        VALUES 
        ('WELCOME20', 'Welcome Discount', '20% off your first month', 'percentage', 20.00, 100000,
         true, NULL, '2026-01-01', '2026-12-31', true),
        ('ANNUAL15', 'Annual Commitment', '15% off when paying annually (in addition to annual discount)', 'percentage', 15.00, 500000,
         true, NULL, '2026-01-01', NULL, true),
        ('STARTUP50', 'Startup Special', '50% off first 3 months for startups', 'percentage', 50.00, 200000,
         true, 100, '2026-01-01', '2026-06-30', true);
    """)
    
    # Update annual discount code to apply only to annual billing
    op.execute("""
        UPDATE discount_codes 
        SET applies_to_billing_cycles = ARRAY['annual']
        WHERE code = 'ANNUAL15';
    """)
    
    # Update USD/EUR/GBP pricing in sku_pricing (approximate conversions)
    op.execute("""        UPDATE sku_pricing SET 
            base_price_monthly_usd = 16.00,
            base_price_annual_usd = 163.00,
            base_price_monthly_eur = 15.00,
            base_price_annual_eur = 153.00,
            base_price_monthly_gbp = 13.00,
            base_price_annual_gbp = 132.00
        WHERE sku_tier = 'core';
    """)
    op.execute("""        UPDATE sku_pricing SET 
            base_price_monthly_usd = 97.00,
            base_price_annual_usd = 988.00,
            base_price_monthly_eur = 88.00,
            base_price_annual_eur = 898.00,
            base_price_monthly_gbp = 77.00,
            base_price_annual_gbp = 785.00
        WHERE sku_tier = 'professional';
    """)
    op.execute("""        UPDATE sku_pricing SET 
            base_price_monthly_usd = 645.00,
            base_price_annual_usd = 6579.00,
            base_price_monthly_eur = 588.00,
            base_price_annual_eur = 5998.00,
            base_price_monthly_gbp = 513.00,
            base_price_annual_gbp = 5233.00
        WHERE sku_tier = 'enterprise';
    """)


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('usage_report_history')
    op.drop_table('scheduled_usage_reports')
    op.drop_table('exchange_rates')
    op.drop_table('volume_discount_rules')
    op.drop_table('discount_code_usages')
    op.drop_table('discount_codes')
    op.drop_table('service_credits')
    
    # Remove columns from sku_pricing
    op.drop_column('sku_pricing', 'base_price_annual_gbp')
    op.drop_column('sku_pricing', 'base_price_monthly_gbp')
    op.drop_column('sku_pricing', 'base_price_annual_eur')
    op.drop_column('sku_pricing', 'base_price_monthly_eur')
    op.drop_column('sku_pricing', 'base_price_annual_usd')
    op.drop_column('sku_pricing', 'base_price_monthly_usd')
    
    # Remove columns from tenant_skus
    op.drop_column('tenant_skus', 'locked_exchange_rate')
    op.drop_column('tenant_skus', 'preferred_currency')
    op.drop_column('tenant_skus', 'last_pause_year')
    op.drop_column('tenant_skus', 'pause_count_this_year')
    op.drop_column('tenant_skus', 'total_paused_days')
    op.drop_column('tenant_skus', 'pause_credits_days')
    op.drop_column('tenant_skus', 'pause_until')
    op.drop_column('tenant_skus', 'pause_reason')
    op.drop_column('tenant_skus', 'paused_at')
    op.drop_column('tenant_skus', 'prorated_first_period')
    op.drop_column('tenant_skus', 'align_to_calendar_month')
    op.drop_column('tenant_skus', 'billing_anchor_day')
