#!/usr/bin/env python3
"""
Fix tier and intelligence_addon ENUM columns in payment_transactions.

The database has PostgreSQL ENUMs with lowercase values (e.g., 'professional')
but SQLAlchemy is sending uppercase values ('PROFESSIONAL').

Solution: Convert these columns to VARCHAR like we did for transaction_type and status.
"""
import asyncio
import sys
sys.path.insert(0, '/Users/efeobukohwo/Desktop/Tekvwa Pro Audit')

from sqlalchemy import text
from app.database import async_session_maker


async def fix_tier_enum():
    async with async_session_maker() as session:
        print("=" * 60)
        print("Fixing tier and intelligence_addon ENUM columns")
        print("=" * 60)
        
        # Check current state
        print("\n1. Checking current column types...")
        result = await session.execute(text("""
            SELECT column_name, data_type, udt_name
            FROM information_schema.columns
            WHERE table_name = 'payment_transactions'
            AND column_name IN ('tier', 'intelligence_addon')
        """))
        for row in result.fetchall():
            print(f"   {row[0]}: {row[1]} (udt: {row[2]})")
        
        # Check if tier is an enum
        result = await session.execute(text("""
            SELECT column_name, data_type, udt_name
            FROM information_schema.columns
            WHERE table_name = 'payment_transactions'
            AND column_name = 'tier'
        """))
        tier_row = result.fetchone()
        
        if tier_row and tier_row[1] == 'USER-DEFINED':
            print("\n2. Converting 'tier' column from ENUM to VARCHAR...")
            
            # Convert tier column
            await session.execute(text("""
                ALTER TABLE payment_transactions 
                ALTER COLUMN tier TYPE VARCHAR(50) 
                USING tier::text
            """))
            print("   ✅ tier column converted to VARCHAR(50)")
        elif tier_row:
            print(f"\n2. tier column is already {tier_row[1]} - no change needed")
        
        # Check intelligence_addon
        result = await session.execute(text("""
            SELECT column_name, data_type, udt_name
            FROM information_schema.columns
            WHERE table_name = 'payment_transactions'
            AND column_name = 'intelligence_addon'
        """))
        intel_row = result.fetchone()
        
        if intel_row and intel_row[1] == 'USER-DEFINED':
            print("\n3. Converting 'intelligence_addon' column from ENUM to VARCHAR...")
            
            await session.execute(text("""
                ALTER TABLE payment_transactions 
                ALTER COLUMN intelligence_addon TYPE VARCHAR(50) 
                USING intelligence_addon::text
            """))
            print("   ✅ intelligence_addon column converted to VARCHAR(50)")
        elif intel_row:
            print(f"\n3. intelligence_addon column is already {intel_row[1]} - no change needed")
        
        await session.commit()
        print("\n4. Changes committed successfully!")
        
        # Verify
        print("\n5. Verifying changes...")
        result = await session.execute(text("""
            SELECT column_name, data_type, udt_name
            FROM information_schema.columns
            WHERE table_name = 'payment_transactions'
            AND column_name IN ('tier', 'intelligence_addon')
        """))
        for row in result.fetchall():
            print(f"   {row[0]}: {row[1]} (udt: {row[2]})")
        
        print("\n✅ Done!")


if __name__ == "__main__":
    asyncio.run(fix_tier_enum())
