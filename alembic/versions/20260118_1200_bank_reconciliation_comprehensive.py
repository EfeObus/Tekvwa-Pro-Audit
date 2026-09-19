"""Bank reconciliation comprehensive models with Nigerian banking support

Revision ID: 20260118_1200
Revises: 20260110_1000_add_advanced_payroll_tables
Create Date: 2026-01-18 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260118_1200'
down_revision: Union[str, None] = '20260110_1000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # This migration supersedes the simpler bank_statements/bank_statement_transactions/
    # bank_reconciliations tables created in 20260108_2030_add_bank_reconciliation_expense_claims.py
    # with a comprehensive Nigerian-banking schema. Drop the earlier versions first so the
    # CREATE TABLE IF NOT EXISTS statements below actually create the new schema instead of
    # silently no-op'ing against the old, incompatible one.
    op.execute("DROP TABLE IF EXISTS bank_reconciliations CASCADE")
    op.execute("DROP TABLE IF EXISTS bank_statement_transactions CASCADE")
    op.execute("DROP TABLE IF EXISTS bank_statements CASCADE")

    # Create enum types
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE bankaccountcurrency AS ENUM ('NGN', 'USD', 'GBP', 'EUR');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE bankstatementsource AS ENUM (
                'mono_api', 'okra_api', 'stitch_api', 
                'csv_upload', 'excel_upload', 'mt940_upload', 
                'pdf_ocr', 'email_parse', 'manual_entry'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE reconciliationstatus AS ENUM (
                'draft', 'in_progress', 'pending_review', 
                'approved', 'rejected', 'completed'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE matchtype AS ENUM (
                'exact', 'fuzzy_amount', 'fuzzy_date', 
                'one_to_many', 'many_to_one', 'rule_based', 'manual'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE matchconfidencelevel AS ENUM ('high', 'medium', 'low', 'manual');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE adjustmenttype AS ENUM (
                'bank_charge', 'emtl', 'stamp_duty', 'sms_fee', 
                'maintenance_fee', 'vat_on_charges', 'wht_deduction', 
                'pos_settlement', 'nip_charge', 'ussd_charge', 
                'interest_earned', 'interest_paid', 'foreign_exchange', 
                'reversal', 'timing_difference', 'error_correction', 'other'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE unmatcheditemtype AS ENUM (
                'outstanding_cheque', 'deposit_in_transit', 
                'bank_error', 'book_error', 'timing_difference', 
                'unidentified_deposit', 'unidentified_withdrawal', 
                'reversal_pending', 'other'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE chargedetectionmethod AS ENUM (
                'narration_pattern', 'exact_amount', 'amount_range', 
                'keyword_match', 'combined'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Check if bank_accounts table exists, if not create it
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'bank_accounts') THEN
                CREATE TABLE bank_accounts (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    entity_id UUID NOT NULL REFERENCES business_entities(id) ON DELETE CASCADE,
                    bank_name VARCHAR(100) NOT NULL,
                    account_number VARCHAR(20) NOT NULL,
                    account_name VARCHAR(200) NOT NULL,
                    account_type VARCHAR(50) DEFAULT 'current',
                    currency VARCHAR(3) DEFAULT 'NGN',
                    bank_code VARCHAR(10),
                    sort_code VARCHAR(20),
                    swift_code VARCHAR(11),
                    iban VARCHAR(34),
                    branch_name VARCHAR(200),
                    branch_address TEXT,
                    gl_account_code VARCHAR(20),
                    gl_account_name VARCHAR(100),
                    is_active BOOLEAN DEFAULT TRUE,
                    is_primary BOOLEAN DEFAULT FALSE,
                    opening_balance NUMERIC(18,2) DEFAULT 0,
                    current_balance NUMERIC(18,2) DEFAULT 0,
                    last_reconciled_date DATE,
                    last_reconciled_balance NUMERIC(18,2),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    UNIQUE(entity_id, account_number)
                );
                CREATE INDEX idx_bank_accounts_entity ON bank_accounts(entity_id);
            END IF;
        END $$;
    """)
    
    # Add new columns to bank_accounts if they don't exist
    columns_to_add = [
        ("mono_account_id", "VARCHAR(100)"),
        ("mono_connected", "BOOLEAN DEFAULT FALSE"),
        ("mono_last_sync", "TIMESTAMP WITH TIME ZONE"),
        ("mono_auth_code", "VARCHAR(255)"),
        ("okra_account_id", "VARCHAR(100)"),
        ("okra_record_id", "VARCHAR(100)"),
        ("okra_connected", "BOOLEAN DEFAULT FALSE"),
        ("okra_last_sync", "TIMESTAMP WITH TIME ZONE"),
        ("stitch_account_id", "VARCHAR(100)"),
        ("stitch_connected", "BOOLEAN DEFAULT FALSE"),
        ("stitch_last_sync", "TIMESTAMP WITH TIME ZONE"),
        ("stitch_payment_consent_id", "VARCHAR(255)"),
        ("auto_sync_enabled", "BOOLEAN DEFAULT FALSE"),
        ("sync_frequency_hours", "INTEGER DEFAULT 24"),
        ("last_sync_status", "VARCHAR(50)"),
        ("last_sync_error", "TEXT"),
    ]
    
    for col_name, col_type in columns_to_add:
        op.execute(f"""
            DO $$ BEGIN
                ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS {col_name} {col_type};
            EXCEPTION
                WHEN duplicate_column THEN null;
            END $$;
        """)
    
    # Create bank_statements table
    op.execute("""
        CREATE TABLE IF NOT EXISTS bank_statements (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            bank_account_id UUID NOT NULL REFERENCES bank_accounts(id) ON DELETE CASCADE,
            statement_date DATE NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            opening_balance NUMERIC(18,2) NOT NULL,
            closing_balance NUMERIC(18,2) NOT NULL,
            source VARCHAR(50) DEFAULT 'manual_entry',
            file_name VARCHAR(255),
            imported_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            imported_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
            transaction_count INTEGER DEFAULT 0,
            total_credits NUMERIC(18,2) DEFAULT 0,
            total_debits NUMERIC(18,2) DEFAULT 0,
            is_reconciled BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_bank_statements_account ON bank_statements(bank_account_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_bank_statements_date ON bank_statements(statement_date)")
    
    # Create bank_statement_transactions table
    op.execute("""        CREATE TABLE IF NOT EXISTS bank_statement_transactions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            bank_account_id UUID NOT NULL REFERENCES bank_accounts(id) ON DELETE CASCADE,
            statement_id UUID REFERENCES bank_statements(id) ON DELETE SET NULL,
            transaction_date DATE NOT NULL,
            value_date DATE,
            posted_date DATE,
            raw_narration TEXT,
            clean_narration TEXT,
            narration TEXT,
            reference VARCHAR(100),
            bank_reference VARCHAR(100),
            debit_amount NUMERIC(18,2),
            credit_amount NUMERIC(18,2),
            balance NUMERIC(18,2),
            transaction_type VARCHAR(50),
            channel VARCHAR(50),
            category VARCHAR(100),
            subcategory VARCHAR(100),
            
            -- Reversal Tracking
            is_reversal BOOLEAN DEFAULT FALSE,
            reversed_transaction_id UUID,
            reversal_reason TEXT,
            
            -- Nigerian-specific charge detection
            is_emtl BOOLEAN DEFAULT FALSE,
            is_stamp_duty BOOLEAN DEFAULT FALSE,
            is_bank_charge BOOLEAN DEFAULT FALSE,
            is_vat_charge BOOLEAN DEFAULT FALSE,
            is_wht_deduction BOOLEAN DEFAULT FALSE,
            is_pos_settlement BOOLEAN DEFAULT FALSE,
            is_nip_transfer BOOLEAN DEFAULT FALSE,
            is_ussd_transaction BOOLEAN DEFAULT FALSE,
            detected_charge_type VARCHAR(50),
            
            -- Matching
            is_matched BOOLEAN DEFAULT FALSE,
            matched_transaction_id UUID REFERENCES transactions(id) ON DELETE SET NULL,
            match_type VARCHAR(50),
            match_group_id UUID,
            match_confidence NUMERIC(5,2),
            match_confidence_level VARCHAR(20),
            matched_at TIMESTAMP WITH TIME ZONE,
            matched_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
            matching_rule_id UUID,
            
            -- Duplicate detection
            duplicate_hash VARCHAR(64),
            is_duplicate BOOLEAN DEFAULT FALSE,
            
            -- Source data
            source VARCHAR(50),
            external_id VARCHAR(255),
            raw_data JSONB,
            
            -- Metadata
            notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
    """)
    op.execute("""        CREATE INDEX IF NOT EXISTS idx_bst_account ON bank_statement_transactions(bank_account_id);
    """)
    op.execute("""        CREATE INDEX IF NOT EXISTS idx_bst_date ON bank_statement_transactions(transaction_date);
    """)
    op.execute("""        CREATE INDEX IF NOT EXISTS idx_bst_matched ON bank_statement_transactions(is_matched);
    """)
    op.execute("""        CREATE INDEX IF NOT EXISTS idx_bst_match_group ON bank_statement_transactions(match_group_id);
    """)
    op.execute("""        CREATE INDEX IF NOT EXISTS idx_bst_duplicate_hash ON bank_statement_transactions(duplicate_hash);
    """)
    op.execute("""        CREATE INDEX IF NOT EXISTS idx_bst_emtl ON bank_statement_transactions(is_emtl) WHERE is_emtl = TRUE;
    """)
    
    # Create bank_reconciliations table
    op.execute("""        CREATE TABLE IF NOT EXISTS bank_reconciliations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            entity_id UUID NOT NULL REFERENCES business_entities(id) ON DELETE CASCADE,
            bank_account_id UUID NOT NULL REFERENCES bank_accounts(id) ON DELETE CASCADE,
            
            -- Period
            reconciliation_date DATE NOT NULL,
            period_start DATE NOT NULL,
            period_end DATE NOT NULL,
            
            -- Balances
            statement_ending_balance NUMERIC(18,2) NOT NULL,
            ledger_ending_balance NUMERIC(18,2) NOT NULL,
            adjusted_bank_balance NUMERIC(18,2),
            adjusted_book_balance NUMERIC(18,2),
            
            -- Reconciling Items
            deposits_in_transit NUMERIC(18,2) DEFAULT 0,
            outstanding_checks NUMERIC(18,2) DEFAULT 0,
            bank_charges NUMERIC(18,2) DEFAULT 0,
            interest_earned NUMERIC(18,2) DEFAULT 0,
            other_adjustments NUMERIC(18,2) DEFAULT 0,
            difference NUMERIC(18,2) DEFAULT 0,
            
            -- Nigerian-specific totals
            total_emtl NUMERIC(18,2) DEFAULT 0,
            total_stamp_duty NUMERIC(18,2) DEFAULT 0,
            total_vat_on_charges NUMERIC(18,2) DEFAULT 0,
            total_wht_deducted NUMERIC(18,2) DEFAULT 0,
            
            -- Statistics
            total_transactions INTEGER DEFAULT 0,
            matched_transactions INTEGER DEFAULT 0,
            unmatched_bank_transactions INTEGER DEFAULT 0,
            unmatched_book_transactions INTEGER DEFAULT 0,
            auto_matched_count INTEGER DEFAULT 0,
            manual_matched_count INTEGER DEFAULT 0,
            
            -- Status
            status VARCHAR(50) DEFAULT 'draft',
            
            -- Workflow
            prepared_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
            prepared_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            reviewed_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
            reviewed_at TIMESTAMP WITH TIME ZONE,
            approved_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
            approved_at TIMESTAMP WITH TIME ZONE,
            
            -- Notes
            notes TEXT,
            rejection_reason TEXT,
            
            -- Metadata
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
    """)
    op.execute("""        CREATE INDEX IF NOT EXISTS idx_bank_recon_entity ON bank_reconciliations(entity_id);
    """)
    op.execute("""        CREATE INDEX IF NOT EXISTS idx_bank_recon_account ON bank_reconciliations(bank_account_id);
    """)
    op.execute("""        CREATE INDEX IF NOT EXISTS idx_bank_recon_date ON bank_reconciliations(reconciliation_date);
    """)
    op.execute("""        CREATE INDEX IF NOT EXISTS idx_bank_recon_status ON bank_reconciliations(status);
    """)
    
    # Create reconciliation_adjustments table
    op.execute("""        CREATE TABLE IF NOT EXISTS reconciliation_adjustments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            reconciliation_id UUID NOT NULL REFERENCES bank_reconciliations(id) ON DELETE CASCADE,
            bank_transaction_id UUID REFERENCES bank_statement_transactions(id) ON DELETE SET NULL,
            
            -- Adjustment Type
            adjustment_type VARCHAR(50) NOT NULL,
            
            -- Journal Entry Details
            description VARCHAR(500) NOT NULL,
            debit_account_code VARCHAR(20) NOT NULL,
            debit_account_name VARCHAR(100),
            credit_account_code VARCHAR(20) NOT NULL,
            credit_account_name VARCHAR(100),
            amount NUMERIC(18,2) NOT NULL,
            
            -- Nigerian Tax Details
            vat_amount NUMERIC(18,2),
            wht_amount NUMERIC(18,2),
            
            -- Journal Reference
            journal_entry_id UUID REFERENCES transactions(id) ON DELETE SET NULL,
            journal_posted BOOLEAN DEFAULT FALSE,
            journal_posted_at TIMESTAMP WITH TIME ZONE,
            
            -- Auto-detection
            auto_detected BOOLEAN DEFAULT FALSE,
            detection_rule_id UUID,
            
            -- Approval
            approved BOOLEAN DEFAULT FALSE,
            approved_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
            approved_at TIMESTAMP WITH TIME ZONE,
            
            -- Notes
            notes TEXT,
            
            -- Metadata
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
    """)
    op.execute("""        CREATE INDEX IF NOT EXISTS idx_recon_adj_reconciliation ON reconciliation_adjustments(reconciliation_id);
    """)
    op.execute("""        CREATE INDEX IF NOT EXISTS idx_recon_adj_type ON reconciliation_adjustments(adjustment_type);
    """)
    
    # Create unmatched_items table
    op.execute("""        CREATE TABLE IF NOT EXISTS unmatched_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            reconciliation_id UUID NOT NULL REFERENCES bank_reconciliations(id) ON DELETE CASCADE,
            
            -- Source
            item_type VARCHAR(50) NOT NULL,
            source VARCHAR(20) NOT NULL,
            
            -- Transaction Reference
            bank_transaction_id UUID REFERENCES bank_statement_transactions(id) ON DELETE SET NULL,
            ledger_transaction_id UUID REFERENCES transactions(id) ON DELETE SET NULL,
            
            -- Details
            transaction_date DATE NOT NULL,
            amount NUMERIC(18,2) NOT NULL,
            description TEXT,
            reference VARCHAR(100),
            
            -- Resolution
            resolution VARCHAR(50),
            resolved_at TIMESTAMP WITH TIME ZONE,
            resolved_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
            resolution_notes TEXT,
            
            -- Carry Forward
            carried_to_reconciliation_id UUID,
            carried_from_reconciliation_id UUID,
            
            -- Journal Entry
            journal_entry_id UUID REFERENCES transactions(id) ON DELETE SET NULL,
            
            -- Metadata
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
    """)
    op.execute("""        CREATE INDEX IF NOT EXISTS idx_unmatched_reconciliation ON unmatched_items(reconciliation_id);
    """)
    op.execute("""        CREATE INDEX IF NOT EXISTS idx_unmatched_item_type ON unmatched_items(item_type);
    """)
    op.execute("""        CREATE INDEX IF NOT EXISTS idx_unmatched_resolution ON unmatched_items(resolution);
    """)
    
    # Create bank_charge_rules table
    op.execute("""        CREATE TABLE IF NOT EXISTS bank_charge_rules (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            entity_id UUID REFERENCES business_entities(id) ON DELETE CASCADE,
            bank_account_id UUID REFERENCES bank_accounts(id) ON DELETE CASCADE,
            
            -- Rule Details
            name VARCHAR(100) NOT NULL,
            description TEXT,
            charge_type VARCHAR(50) NOT NULL,
            
            -- Detection Method
            detection_method VARCHAR(50) NOT NULL,
            
            -- Narration Pattern
            narration_pattern VARCHAR(500),
            narration_keywords JSONB,
            
            -- Amount Criteria
            exact_amount NUMERIC(18,2),
            min_amount NUMERIC(18,2),
            max_amount NUMERIC(18,2),
            
            -- Account Mapping
            debit_account_code VARCHAR(20),
            credit_account_code VARCHAR(20),
            
            -- Nigerian Tax
            includes_vat BOOLEAN DEFAULT FALSE,
            vat_rate NUMERIC(5,2) DEFAULT 7.5,
            
            -- Status
            is_active BOOLEAN DEFAULT TRUE,
            is_system_rule BOOLEAN DEFAULT FALSE,
            priority INTEGER DEFAULT 100,
            
            -- Statistics
            times_applied INTEGER DEFAULT 0,
            last_applied_at TIMESTAMP WITH TIME ZONE,
            
            -- Metadata
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
    """)
    op.execute("""        CREATE INDEX IF NOT EXISTS idx_charge_rules_entity ON bank_charge_rules(entity_id);
    """)
    op.execute("""        CREATE INDEX IF NOT EXISTS idx_charge_rules_account ON bank_charge_rules(bank_account_id);
    """)
    op.execute("""        CREATE INDEX IF NOT EXISTS idx_charge_rules_active ON bank_charge_rules(is_active);
    """)
    
    # Create matching_rules table
    op.execute("""        CREATE TABLE IF NOT EXISTS matching_rules (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            entity_id UUID NOT NULL REFERENCES business_entities(id) ON DELETE CASCADE,
            bank_account_id UUID REFERENCES bank_accounts(id) ON DELETE CASCADE,
            
            -- Rule Details
            name VARCHAR(100) NOT NULL,
            description TEXT,
            
            -- Bank Side Criteria
            bank_narration_pattern VARCHAR(500),
            bank_narration_keywords JSONB,
            bank_reference_pattern VARCHAR(200),
            bank_amount_min NUMERIC(18,2),
            bank_amount_max NUMERIC(18,2),
            bank_is_debit BOOLEAN,
            
            -- Ledger Side Criteria
            ledger_description_pattern VARCHAR(500),
            ledger_account_code VARCHAR(20),
            ledger_vendor_id UUID,
            ledger_customer_id UUID,
            
            -- Match Settings
            date_tolerance_days INTEGER DEFAULT 3,
            amount_tolerance_percent NUMERIC(5,2) DEFAULT 0,
            auto_match BOOLEAN DEFAULT FALSE,
            
            -- Statistics
            times_used INTEGER DEFAULT 0,
            last_used_at TIMESTAMP WITH TIME ZONE,
            successful_matches INTEGER DEFAULT 0,
            
            -- Status
            is_active BOOLEAN DEFAULT TRUE,
            priority INTEGER DEFAULT 100,
            
            -- Metadata
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
    """)
    op.execute("""        CREATE INDEX IF NOT EXISTS idx_matching_rules_entity ON matching_rules(entity_id);
    """)
    op.execute("""        CREATE INDEX IF NOT EXISTS idx_matching_rules_account ON matching_rules(bank_account_id);
    """)
    op.execute("""        CREATE INDEX IF NOT EXISTS idx_matching_rules_active ON matching_rules(is_active);
    """)
    
    # Create bank_statement_imports table
    op.execute("""        CREATE TABLE IF NOT EXISTS bank_statement_imports (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            entity_id UUID NOT NULL REFERENCES business_entities(id) ON DELETE CASCADE,
            bank_account_id UUID NOT NULL REFERENCES bank_accounts(id) ON DELETE CASCADE,
            
            -- Import Details
            source VARCHAR(50) NOT NULL,
            filename VARCHAR(255),
            file_path VARCHAR(500),
            file_hash VARCHAR(64),
            
            -- Period
            statement_start_date DATE,
            statement_end_date DATE,
            
            -- Statistics
            total_rows INTEGER DEFAULT 0,
            imported_count INTEGER DEFAULT 0,
            duplicate_count INTEGER DEFAULT 0,
            error_count INTEGER DEFAULT 0,
            
            -- Auto-detected charges
            emtl_count INTEGER DEFAULT 0,
            stamp_duty_count INTEGER DEFAULT 0,
            bank_charge_count INTEGER DEFAULT 0,
            reversal_count INTEGER DEFAULT 0,
            
            -- Status
            status VARCHAR(20) DEFAULT 'pending',
            error_message TEXT,
            
            -- Import User
            imported_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
            imported_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            processing_time_ms INTEGER,
            
            -- Raw Data
            import_log JSONB,
            
            -- Metadata
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
    """)
    op.execute("""        CREATE INDEX IF NOT EXISTS idx_stmt_imports_entity ON bank_statement_imports(entity_id);
    """)
    op.execute("""        CREATE INDEX IF NOT EXISTS idx_stmt_imports_account ON bank_statement_imports(bank_account_id);
    """)
    op.execute("""        CREATE INDEX IF NOT EXISTS idx_stmt_imports_status ON bank_statement_imports(status);
    """)
    
    # Insert default Nigerian bank charge rules
    op.execute("""
        INSERT INTO bank_charge_rules (
            id, name, description, charge_type, detection_method,
            exact_amount, narration_keywords, debit_account_code, credit_account_code,
            includes_vat, is_active, is_system_rule, priority
        )
        VALUES 
        -- EMTL Rule (N50 on electronic transfers > N10,000)
        (
            gen_random_uuid(),
            'EMTL - Electronic Money Transfer Levy',
            'N50 levy on electronic inflows above N10,000',
            'emtl',
            'combined',
            50.00,
            '["EMTL", "E-LEVY", "TRANSFER LEVY", "NIP LEVY"]',
            '7140',
            '1110',
            false,
            true,
            true,
            10
        ),
        -- Stamp Duty Rule (N50)
        (
            gen_random_uuid(),
            'Stamp Duty - N50',
            'N50 stamp duty on qualifying transactions',
            'stamp_duty',
            'combined',
            50.00,
            '["STAMP DUTY", "STD", "STAMP"]',
            '7140',
            '1110',
            false,
            true,
            true,
            20
        ),
        -- SMS Alert Fee
        (
            gen_random_uuid(),
            'SMS Alert Fee',
            'SMS notification charges',
            'sms_fee',
            'keyword_match',
            NULL,
            '["SMS ALERT", "SMS CHG", "SMS FEE", "SMS CHARGE", "NOTIFICATION FEE"]',
            '7120',
            '1110',
            true,
            true,
            true,
            30
        ),
        -- Account Maintenance Fee
        (
            gen_random_uuid(),
            'Account Maintenance Fee',
            'Monthly account maintenance charges',
            'maintenance_fee',
            'keyword_match',
            NULL,
            '["MAINTENANCE", "COT", "ACCOUNT FEE", "CURRENT ACCOUNT MAINTENANCE"]',
            '7120',
            '1110',
            true,
            true,
            true,
            40
        ),
        -- VAT on Bank Charges (7.5%)
        (
            gen_random_uuid(),
            'VAT on Bank Charges',
            '7.5% VAT on bank charges',
            'vat_on_charges',
            'keyword_match',
            NULL,
            '["VAT", "V.A.T"]',
            '7140',
            '1110',
            false,
            true,
            true,
            50
        )
        ON CONFLICT DO NOTHING;
    """)


def downgrade() -> None:
    # Drop tables in reverse order
    op.execute("DROP TABLE IF EXISTS bank_statement_imports CASCADE;")
    op.execute("DROP TABLE IF EXISTS matching_rules CASCADE;")
    op.execute("DROP TABLE IF EXISTS bank_charge_rules CASCADE;")
    op.execute("DROP TABLE IF EXISTS unmatched_items CASCADE;")
    op.execute("DROP TABLE IF EXISTS reconciliation_adjustments CASCADE;")
    op.execute("DROP TABLE IF EXISTS bank_reconciliations CASCADE;")
    op.execute("DROP TABLE IF EXISTS bank_statement_transactions CASCADE;")
    op.execute("DROP TABLE IF EXISTS bank_statements CASCADE;")
    
    # Remove added columns from bank_accounts (don't drop the table)
    columns_to_remove = [
        "mono_account_id", "mono_connected", "mono_last_sync", "mono_auth_code",
        "okra_account_id", "okra_record_id", "okra_connected", "okra_last_sync",
        "stitch_account_id", "stitch_connected", "stitch_last_sync", "stitch_payment_consent_id",
        "auto_sync_enabled", "sync_frequency_hours", "last_sync_status", "last_sync_error"
    ]
    
    for col_name in columns_to_remove:
        op.execute(f"""
            DO $$ BEGIN
                ALTER TABLE bank_accounts DROP COLUMN IF EXISTS {col_name};
            EXCEPTION
                WHEN undefined_column THEN null;
            END $$;
        """)
    
    # Drop enum types
    op.execute("DROP TYPE IF EXISTS chargedetectionmethod CASCADE;")
    op.execute("DROP TYPE IF EXISTS unmatcheditemtype CASCADE;")
    op.execute("DROP TYPE IF EXISTS adjustmenttype CASCADE;")
    op.execute("DROP TYPE IF EXISTS matchconfidencelevel CASCADE;")
    op.execute("DROP TYPE IF EXISTS matchtype CASCADE;")
    op.execute("DROP TYPE IF EXISTS reconciliationstatus CASCADE;")
    op.execute("DROP TYPE IF EXISTS bankstatementsource CASCADE;")
    op.execute("DROP TYPE IF EXISTS bankaccountcurrency CASCADE;")
