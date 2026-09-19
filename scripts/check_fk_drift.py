"""
Detect drift between real foreign-key constraints in a migrated database and what
app/models/*.py's SQLAlchemy metadata actually declares.

Background: a column can have a real FK constraint created by an Alembic migration
while the SQLAlchemy model either omits the column entirely, or declares it without
a ForeignKey(). Base.metadata.create_all()/drop_all() (used by the default test
fixtures) never surfaces this, because create_all() only ever builds what the models
declare -- it silently can't create a constraint the model doesn't know about. Against
a real `alembic upgrade head` database, this becomes a real ordering/cleanup hazard.

See docs/REMEDIATION_LOG.md (Finding 49) for the full investigation this script
grew out of, and docs/IMPLEMENTATION_ROADMAP.md Phase 1 Section 1.5 for the plan
to close the remaining mismatches.

Usage:
    DATABASE_URL_ASYNC=postgresql+asyncpg://user@localhost/dbname \
        python scripts/check_fk_drift.py [--verbose]

Exits non-zero if any mismatch is found, so this can be wired into CI once the
mismatch count reaches zero (see the Recommended Fix note in REMEDIATION_LOG.md).
"""
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.database import Base
import app.models  # noqa: F401 - ensure all models register on Base.metadata


COLUMN_DETAIL_SQL = """
    SELECT data_type, udt_name, is_nullable, column_default, character_maximum_length,
           numeric_precision, numeric_scale
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = :table_name AND column_name = :column_name
"""

FK_SQL = """
    SELECT
        tc.table_name,
        kcu.column_name,
        ccu.table_name AS referenced_table,
        tc.constraint_name,
        rc.delete_rule
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
        ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
    JOIN information_schema.constraint_column_usage ccu
        ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema
    JOIN information_schema.referential_constraints rc
        ON tc.constraint_name = rc.constraint_name AND tc.table_schema = rc.constraint_schema
    WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
    ORDER BY tc.table_name, kcu.column_name
"""


async def main() -> int:
    verbose = "--verbose" in sys.argv
    db_url = os.environ.get("DATABASE_URL_ASYNC")
    if not db_url:
        print("DATABASE_URL_ASYNC must be set to a migrated database.", file=sys.stderr)
        return 2

    engine = create_async_engine(db_url)
    async with engine.connect() as conn:
        db_fks = (await conn.execute(text(FK_SQL))).fetchall()

        mismatches = []
        for table_name, column_name, referenced_table, constraint_name, delete_rule in db_fks:
            table = Base.metadata.tables.get(table_name)
            if table is None:
                reason = "TABLE NOT IN ORM METADATA AT ALL"
            else:
                col = table.columns.get(column_name)
                if col is None:
                    reason = "COLUMN NOT IN ORM METADATA AT ALL"
                elif not col.foreign_keys:
                    reason = "NO ForeignKey() DECLARED ON MODEL"
                else:
                    continue

            detail = None
            if verbose:
                detail_row = (await conn.execute(
                    text(COLUMN_DETAIL_SQL),
                    {"table_name": table_name, "column_name": column_name},
                )).fetchone()
                detail = detail_row
            mismatches.append(
                (table_name, column_name, referenced_table, constraint_name, delete_rule, reason, detail)
            )

    await engine.dispose()

    print(f"Total live FK constraints checked: {len(db_fks)}")
    print(f"Mismatches (model doesn't know about a real constraint): {len(mismatches)}\n")
    for table_name, column_name, referenced_table, constraint_name, delete_rule, reason, detail in mismatches:
        line = f"  {table_name}.{column_name} -> {referenced_table}  [{constraint_name}, ON DELETE {delete_rule}]  ({reason})"
        print(line)
        if detail:
            print(f"      db type: {detail}")

    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
