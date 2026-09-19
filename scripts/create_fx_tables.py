#!/usr/bin/env python3
"""
Create FX tables in the database.
"""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://efeobukohwo:12345@localhost:5432/tekvwa_pro_audit"


async def create_fx_tables():
    engine = create_async_engine(DATABASE_URL)
    
    async with engine.begin() as conn:
        # Create enums
        await conn.execute(text("""
            DO $$ BEGIN
                CREATE TYPE fxrevaluationtype AS ENUM ('realized', 'unrealized', 'settlement');
            EXCEPTION WHEN duplicate_object THEN null;
            END $$;
        """))
        print("✓ Created fxrevaluationtype enum")
        
        await conn.execute(text("""
            DO $$ BEGIN
                CREATE TYPE fxaccounttype AS ENUM ('bank', 'receivable', 'payable', 'loan', 'intercompany');
            EXCEPTION WHEN duplicate_object THEN null;
            END $$;
        """))
        print("✓ Created fxaccounttype enum")
        
        # Create fx_revaluations table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fx_revaluations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                entity_id UUID NOT NULL REFERENCES business_entities(id) ON DELETE CASCADE,
                revaluation_date DATE NOT NULL,
                revaluation_type fxrevaluationtype NOT NULL,
                account_id UUID NOT NULL REFERENCES chart_of_accounts(id) ON DELETE CASCADE,
                fx_account_type fxaccounttype NOT NULL,
                foreign_currency VARCHAR(3) NOT NULL,
                functional_currency VARCHAR(3) NOT NULL DEFAULT 'NGN',
                original_fc_amount NUMERIC(18,2) NOT NULL,
                original_exchange_rate NUMERIC(12,6) NOT NULL,
                original_ngn_amount NUMERIC(18,2) NOT NULL,
                revaluation_rate NUMERIC(12,6) NOT NULL,
                revalued_ngn_amount NUMERIC(18,2) NOT NULL,
                fx_gain_loss NUMERIC(18,2) NOT NULL,
                is_gain BOOLEAN NOT NULL,
                journal_entry_id UUID REFERENCES journal_entries(id) ON DELETE SET NULL,
                source_document_type VARCHAR(50),
                source_document_id UUID,
                fiscal_period_id UUID REFERENCES fiscal_periods(id) ON DELETE SET NULL,
                notes TEXT
            )
        """))
        print("✓ Created fx_revaluations table")
        
        # Create indexes
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_fx_reval_entity_date ON fx_revaluations(entity_id, revaluation_date)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_fx_reval_account ON fx_revaluations(account_id, revaluation_date)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_fx_reval_type ON fx_revaluations(revaluation_type, revaluation_date)"))
        print("✓ Created fx_revaluations indexes")
        
        # Create fx_exposure_summaries table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fx_exposure_summaries (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                entity_id UUID NOT NULL REFERENCES business_entities(id) ON DELETE CASCADE,
                as_of_date DATE NOT NULL,
                foreign_currency VARCHAR(3) NOT NULL,
                bank_fc_balance NUMERIC(18,2) NOT NULL DEFAULT 0,
                receivable_fc_balance NUMERIC(18,2) NOT NULL DEFAULT 0,
                payable_fc_balance NUMERIC(18,2) NOT NULL DEFAULT 0,
                loan_fc_balance NUMERIC(18,2) NOT NULL DEFAULT 0,
                net_fc_exposure NUMERIC(18,2) NOT NULL,
                current_rate NUMERIC(12,6) NOT NULL,
                net_ngn_exposure NUMERIC(18,2) NOT NULL,
                ytd_realized_gain_loss NUMERIC(18,2) NOT NULL DEFAULT 0,
                ytd_unrealized_gain_loss NUMERIC(18,2) NOT NULL DEFAULT 0,
                UNIQUE(entity_id, as_of_date, foreign_currency)
            )
        """))
        print("✓ Created fx_exposure_summaries table")
        
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_fx_exposure_entity ON fx_exposure_summaries(entity_id, as_of_date)"))
        print("✓ Created fx_exposure_summaries index")
        
        # Add currency column to chart_of_accounts if not exists
        await conn.execute(text("ALTER TABLE chart_of_accounts ADD COLUMN IF NOT EXISTS currency VARCHAR(3) DEFAULT 'NGN'"))
        print("✓ Added currency column to chart_of_accounts")
    
    await engine.dispose()
    print("\n✅ FX tables created successfully!")


if __name__ == "__main__":
    asyncio.run(create_fx_tables())
