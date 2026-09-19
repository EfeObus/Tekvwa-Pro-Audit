"""
Tekvwa Pro Audit - Query Optimization Utilities

Performance optimization utilities for database queries including:
- Eager loading configurations
- Query hints
- Batch processing utilities
- Index recommendations

Author: Tekvwa Pro Audit Team
Date: January 2026
"""

import logging
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Type, TypeVar, Callable
from functools import wraps
import time

from sqlalchemy import select, func, and_, Index, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload, load_only
from sqlalchemy.sql import Select

logger = logging.getLogger(__name__)

T = TypeVar('T')


# =========================================================================
# QUERY TIMING DECORATOR
# =========================================================================

def log_query_time(func: Callable) -> Callable:
    """
    Decorator to log query execution time.
    Useful for identifying slow queries during development.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        result = await func(*args, **kwargs)
        elapsed_time = (time.time() - start_time) * 1000  # Convert to ms
        
        if elapsed_time > 100:  # Log queries taking more than 100ms
            logger.warning(
                f"Slow query detected: {func.__name__} took {elapsed_time:.2f}ms"
            )
        else:
            logger.debug(f"Query {func.__name__} completed in {elapsed_time:.2f}ms")
        
        return result
    return wrapper


# =========================================================================
# BATCH PROCESSING UTILITIES
# =========================================================================

async def batch_process(
    items: List[T],
    processor: Callable[[List[T]], Any],
    batch_size: int = 100,
) -> List[Any]:
    """
    Process items in batches to avoid memory issues with large datasets.
    
    Args:
        items: List of items to process
        processor: Async function to process each batch
        batch_size: Number of items per batch
        
    Returns:
        List of results from each batch
    """
    results = []
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        result = await processor(batch)
        results.append(result)
    return results


async def batch_insert(
    db: AsyncSession,
    objects: List[Any],
    batch_size: int = 100,
) -> int:
    """
    Insert objects in batches to avoid transaction timeout issues.
    
    Args:
        db: Database session
        objects: List of ORM objects to insert
        batch_size: Number of objects per batch
        
    Returns:
        Total number of objects inserted
    """
    total = 0
    for i in range(0, len(objects), batch_size):
        batch = objects[i:i + batch_size]
        db.add_all(batch)
        await db.flush()  # Flush each batch
        total += len(batch)
    await db.commit()
    return total


# =========================================================================
# OPTIMIZED SELECT BUILDERS
# =========================================================================

class OptimizedQueryBuilder:
    """Builder for creating optimized queries with common patterns."""
    
    @staticmethod
    def select_with_pagination(
        model: Type[T],
        page: int = 1,
        per_page: int = 50,
        max_per_page: int = 100,
    ) -> Select:
        """
        Create a paginated select query.
        
        Args:
            model: SQLAlchemy model class
            page: Page number (1-indexed)
            per_page: Items per page
            max_per_page: Maximum allowed items per page
        """
        per_page = min(per_page, max_per_page)
        offset = (page - 1) * per_page
        
        return select(model).offset(offset).limit(per_page)
    
    @staticmethod
    def select_with_date_range(
        model: Type[T],
        date_column: str,
        start_date: date,
        end_date: date,
    ) -> Select:
        """
        Create a query filtered by date range.
        Uses proper indexable date comparisons.
        """
        column = getattr(model, date_column)
        return select(model).where(
            and_(
                column >= start_date,
                column <= end_date
            )
        )
    
    @staticmethod
    def select_active_only(
        model: Type[T],
        active_column: str = "is_active",
    ) -> Select:
        """Create a query for active records only."""
        column = getattr(model, active_column)
        return select(model).where(column == True)


# =========================================================================
# EAGER LOADING CONFIGURATIONS
# =========================================================================

class EagerLoadingConfig:
    """
    Predefined eager loading configurations for common relationships.
    Use these to avoid N+1 query problems.
    """
    
    @staticmethod
    def journal_entry_with_lines():
        """Load journal entry with all lines in single query."""
        return [selectinload('lines')]
    
    @staticmethod
    def invoice_with_items_and_customer():
        """Load invoice with items and customer."""
        return [
            selectinload('items'),
            joinedload('customer'),
        ]
    
    @staticmethod
    def entity_with_group():
        """Load entity with its consolidation group."""
        return [joinedload('entity_group')]
    
    @staticmethod
    def chart_of_accounts_with_balances():
        """Load chart of accounts with latest balances."""
        return [selectinload('balances')]


# =========================================================================
# AGGREGATE QUERY UTILITIES
# =========================================================================

class AggregateQueries:
    """Pre-built aggregate queries for common reporting needs."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    @log_query_time
    async def get_account_balances_summary(
        self,
        entity_id: str,
        as_of_date: date,
    ) -> Dict[str, Decimal]:
        """
        Get summarized account balances by type.
        Optimized with direct aggregation instead of loading all records.
        """
        from app.models.accounting import ChartOfAccounts, AccountBalance
        
        result = await self.db.execute(
            select(
                ChartOfAccounts.account_type,
                func.sum(AccountBalance.debit_balance - AccountBalance.credit_balance).label('net_balance')
            )
            .join(AccountBalance, ChartOfAccounts.id == AccountBalance.account_id)
            .where(AccountBalance.entity_id == entity_id)
            .where(AccountBalance.period_end_date <= as_of_date)
            .group_by(ChartOfAccounts.account_type)
        )
        
        return {str(row.account_type): row.net_balance for row in result}
    
    @log_query_time
    async def get_trial_balance_totals(
        self,
        entity_id: str,
        as_of_date: date,
    ) -> Dict[str, Decimal]:
        """
        Get trial balance totals without loading all accounts.
        """
        from app.models.accounting import AccountBalance
        
        result = await self.db.execute(
            select(
                func.sum(AccountBalance.debit_balance).label('total_debits'),
                func.sum(AccountBalance.credit_balance).label('total_credits'),
            )
            .where(AccountBalance.entity_id == entity_id)
            .where(AccountBalance.period_end_date <= as_of_date)
        )
        
        row = result.first()
        return {
            'total_debits': row.total_debits or Decimal('0'),
            'total_credits': row.total_credits or Decimal('0'),
        }
    
    @log_query_time
    async def get_fx_rate_latest(
        self,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Optional[Decimal]:
        """
        Get latest FX rate using optimized index-friendly query.
        """
        from app.models.sku import ExchangeRate
        
        result = await self.db.execute(
            select(ExchangeRate.rate)
            .where(
                and_(
                    ExchangeRate.from_currency == from_currency,
                    ExchangeRate.to_currency == to_currency,
                    ExchangeRate.rate_date <= as_of_date,
                )
            )
            .order_by(ExchangeRate.rate_date.desc())
            .limit(1)
        )
        
        row = result.scalar_one_or_none()
        return row if row else None
    
    @log_query_time
    async def get_period_totals_by_account_type(
        self,
        entity_id: str,
        start_date: date,
        end_date: date,
    ) -> Dict[str, Dict[str, Decimal]]:
        """
        Get transaction totals by account type for a period.
        Optimized single query replacing multiple queries.
        """
        from app.models.accounting import JournalEntryLine, JournalEntry, ChartOfAccounts
        
        result = await self.db.execute(
            select(
                ChartOfAccounts.account_type,
                func.sum(JournalEntryLine.debit_amount).label('total_debit'),
                func.sum(JournalEntryLine.credit_amount).label('total_credit'),
                func.count(JournalEntryLine.id).label('line_count'),
            )
            .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
            .join(ChartOfAccounts, JournalEntryLine.account_id == ChartOfAccounts.id)
            .where(JournalEntry.entity_id == entity_id)
            .where(JournalEntry.entry_date >= start_date)
            .where(JournalEntry.entry_date <= end_date)
            .group_by(ChartOfAccounts.account_type)
        )
        
        return {
            str(row.account_type): {
                'total_debit': row.total_debit or Decimal('0'),
                'total_credit': row.total_credit or Decimal('0'),
                'line_count': row.line_count,
            }
            for row in result
        }


# =========================================================================
# INDEX RECOMMENDATIONS
# =========================================================================

# These are the recommended indexes for optimal query performance.
# Add to appropriate Alembic migrations.

RECOMMENDED_INDEXES = [
    # Exchange rates - frequently queried by currency pair and date
    {
        "name": "ix_exchange_rates_currency_date",
        "table": "exchange_rates",
        "columns": ["from_currency", "to_currency", "rate_date"],
        "description": "Speeds up FX rate lookups by currency pair and date",
    },
    
    # Journal entries - date range queries
    {
        "name": "ix_journal_entries_entity_date",
        "table": "journal_entries",
        "columns": ["entity_id", "entry_date"],
        "description": "Optimizes date-range queries for journal entries",
    },
    
    # Account balances - entity and period lookups
    {
        "name": "ix_account_balances_entity_period",
        "table": "account_balances",
        "columns": ["entity_id", "period_end_date"],
        "description": "Speeds up balance lookups by entity and period",
    },
    
    # Transactions - type and date queries
    {
        "name": "ix_transactions_entity_type_date",
        "table": "transactions",
        "columns": ["entity_id", "transaction_type", "transaction_date"],
        "description": "Optimizes report queries by transaction type and date",
    },
    
    # Intercompany transactions - consolidation queries
    {
        "name": "ix_intercompany_from_to_date",
        "table": "intercompany_transactions",
        "columns": ["from_entity_id", "to_entity_id", "transaction_date"],
        "description": "Speeds up intercompany elimination queries",
    },
    
    # Invoices - status and date queries
    {
        "name": "ix_invoices_entity_status_date",
        "table": "invoices",
        "columns": ["entity_id", "status", "invoice_date"],
        "description": "Optimizes AR aging and invoice list queries",
    },
    
    # Chart of accounts - type lookups
    {
        "name": "ix_coa_entity_type",
        "table": "chart_of_accounts",
        "columns": ["entity_id", "account_type"],
        "description": "Speeds up account type filtering",
    },
    
    # Budget line items - budget and account
    {
        "name": "ix_budget_line_items_budget_account",
        "table": "budget_line_items",
        "columns": ["budget_id", "account_id"],
        "description": "Optimizes budget variance calculations",
    },
]


def generate_index_migration_sql() -> str:
    """Generate Alembic migration SQL for recommended indexes."""
    lines = ["# Add these indexes to an Alembic migration\n"]
    
    for idx in RECOMMENDED_INDEXES:
        columns = ", ".join(idx["columns"])
        lines.append(f"# {idx['description']}")
        lines.append(
            f"op.create_index('{idx['name']}', '{idx['table']}', [{', '.join(repr(c) for c in idx['columns'])}])"
        )
        lines.append("")
    
    return "\n".join(lines)


# =========================================================================
# QUERY ANALYSIS UTILITIES
# =========================================================================

async def analyze_query_performance(
    db: AsyncSession,
    query_sql: str,
) -> Dict[str, Any]:
    """
    Analyze query performance using EXPLAIN ANALYZE.
    Only for PostgreSQL.
    """
    try:
        result = await db.execute(text(f"EXPLAIN ANALYZE {query_sql}"))
        plan_rows = [row[0] for row in result]
        
        return {
            "query": query_sql,
            "plan": plan_rows,
            "summary": plan_rows[-1] if plan_rows else "No plan available",
        }
    except Exception as e:
        logger.error(f"Failed to analyze query: {e}")
        return {"error": str(e)}


# =========================================================================
# LOAD TESTING UTILITIES
# =========================================================================

async def benchmark_query(
    db: AsyncSession,
    query_func: Callable,
    iterations: int = 10,
    **kwargs,
) -> Dict[str, float]:
    """
    Benchmark a query function over multiple iterations.
    
    Returns timing statistics.
    """
    times = []
    
    for _ in range(iterations):
        start = time.time()
        await query_func(db, **kwargs)
        elapsed = (time.time() - start) * 1000
        times.append(elapsed)
    
    return {
        "min_ms": min(times),
        "max_ms": max(times),
        "avg_ms": sum(times) / len(times),
        "iterations": iterations,
    }
