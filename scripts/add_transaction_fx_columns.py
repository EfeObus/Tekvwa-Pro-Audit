"""
Add FX (Foreign Exchange) columns to transactions table.

This script adds the following columns:
- currency
- exchange_rate
- exchange_rate_source
- functional_amount
- functional_vat_amount
- functional_total_amount
- realized_fx_gain_loss
- settlement_exchange_rate
- settlement_date
"""

import asyncio
from contextlib import asynccontextmanager
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL_ASYNC", "postgresql+asyncpg://efeobukohwo@localhost:5432/tekvwa_pro_audit")
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def get_async_session_context():
    async with async_session() as session:
        yield session


async def add_fx_columns():
    """Add FX columns to transactions table."""
    print("Adding FX columns to transactions table...")
    
    async with get_async_session_context() as db:
        # List of columns to add with their types and defaults
        columns = [
            ("currency", "VARCHAR(3)", "'NGN'"),
            ("exchange_rate", "NUMERIC(18, 8)", "1.0"),
            ("exchange_rate_source", "VARCHAR(50)", "NULL"),
            ("functional_amount", "NUMERIC(18, 2)", "0"),
            ("functional_vat_amount", "NUMERIC(18, 2)", "0"),
            ("functional_total_amount", "NUMERIC(18, 2)", "0"),
            ("realized_fx_gain_loss", "NUMERIC(18, 2)", "0"),
            ("settlement_exchange_rate", "NUMERIC(18, 8)", "NULL"),
            ("settlement_date", "DATE", "NULL"),
        ]
        
        for col_name, col_type, col_default in columns:
            # Check if column exists
            check_sql = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'transactions' 
                AND column_name = :col_name
            """)
            result = await db.execute(check_sql, {"col_name": col_name})
            exists = result.scalar_one_or_none()
            
            if exists:
                print(f"  ✓ Column '{col_name}' already exists")
            else:
                # Add column
                default_clause = f" DEFAULT {col_default}" if col_default != "NULL" else ""
                not_null_clause = " NOT NULL" if col_default != "NULL" else ""
                add_sql = text(f"""
                    ALTER TABLE transactions 
                    ADD COLUMN IF NOT EXISTS {col_name} {col_type}{default_clause}{not_null_clause}
                """)
                await db.execute(add_sql)
                print(f"  ✓ Added column '{col_name}' ({col_type})")
        
        # Update functional amounts to match the transaction amounts (for existing NGN transactions)
        update_sql = text("""
            UPDATE transactions 
            SET functional_amount = amount,
                functional_vat_amount = vat_amount,
                functional_total_amount = total_amount
            WHERE currency = 'NGN' AND functional_amount = 0
        """)
        result = await db.execute(update_sql)
        print(f"  ✓ Updated {result.rowcount} existing transactions with functional amounts")
        
        await db.commit()
        print("\n✅ FX columns added successfully!")


if __name__ == "__main__":
    asyncio.run(add_fx_columns())
