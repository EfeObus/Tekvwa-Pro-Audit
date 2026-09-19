"""Test that payment_transactions insert works correctly."""
import asyncio
import sys
sys.path.insert(0, '/Users/efeobukohwo/Desktop/Tekvwa Pro Audit')

from app.database import async_session_maker
from sqlalchemy import text

async def test_insert():
    async with async_session_maker() as session:
        try:
            # Test insert with minimal required fields
            result = await session.execute(text("""
                INSERT INTO payment_transactions (
                    id, created_at, organization_id, reference, transaction_type, 
                    status, amount_kobo, currency
                ) VALUES (
                    gen_random_uuid(), NOW(), 
                    (SELECT id FROM organizations LIMIT 1), 
                    'TEST-' || extract(epoch from now())::text,
                    'payment', 'pending', 10000, 'NGN'
                ) RETURNING id, reference
            """))
            row = result.fetchone()
            print(f'✅ Test insert succeeded: {row[0]} - {row[1]}')
            
            # Rollback test data
            await session.rollback()
            print('(Test data rolled back)')
        except Exception as e:
            print(f'❌ Insert failed: {e}')
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_insert())
