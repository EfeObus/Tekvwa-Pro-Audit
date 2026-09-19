#!/usr/bin/env python
"""
Migration script to add missing columns to tenant_skus table.
"""
import asyncio
from sqlalchemy import text

# Add project root to path
import sys
sys.path.insert(0, '/Users/efeobukohwo/Desktop/Tekvwa Pro Audit')

from app.database import get_async_session


async def migrate():
    """Add missing columns to tenant_skus table."""
    async for db in get_async_session():
        migrations = [
            # Issue #31: Billing Cycle Alignment
            'ALTER TABLE tenant_skus ADD COLUMN IF NOT EXISTS align_to_calendar_month BOOLEAN DEFAULT FALSE',
            'ALTER TABLE tenant_skus ADD COLUMN IF NOT EXISTS prorated_first_period BOOLEAN DEFAULT TRUE',
            # Issue #32: Subscription Pause/Resume
            'ALTER TABLE tenant_skus ADD COLUMN IF NOT EXISTS paused_at TIMESTAMP WITH TIME ZONE',
            'ALTER TABLE tenant_skus ADD COLUMN IF NOT EXISTS pause_reason VARCHAR(500)',
            'ALTER TABLE tenant_skus ADD COLUMN IF NOT EXISTS pause_until TIMESTAMP WITH TIME ZONE',
            'ALTER TABLE tenant_skus ADD COLUMN IF NOT EXISTS pause_credits_days INTEGER DEFAULT 0',
            'ALTER TABLE tenant_skus ADD COLUMN IF NOT EXISTS total_paused_days INTEGER DEFAULT 0',
            'ALTER TABLE tenant_skus ADD COLUMN IF NOT EXISTS pause_count_this_year INTEGER DEFAULT 0',
            'ALTER TABLE tenant_skus ADD COLUMN IF NOT EXISTS last_pause_year INTEGER',
            # Issue #36: Multi-Currency Support
            'ALTER TABLE tenant_skus ADD COLUMN IF NOT EXISTS preferred_currency VARCHAR(3) DEFAULT \'NGN\'',
            'ALTER TABLE tenant_skus ADD COLUMN IF NOT EXISTS locked_exchange_rate NUMERIC(12, 6)',
        ]
        
        print("Adding missing columns to tenant_skus...")
        for sql in migrations:
            try:
                await db.execute(text(sql))
                col_name = sql.split('ADD COLUMN IF NOT EXISTS ')[1].split()[0]
                print(f'  ✓ {col_name}')
            except Exception as e:
                print(f'  ✗ Error: {e}')
        
        await db.commit()
        print('\nMigration complete!')
        break


if __name__ == '__main__':
    asyncio.run(migrate())
