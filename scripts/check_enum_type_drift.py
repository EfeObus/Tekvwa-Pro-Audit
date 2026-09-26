"""
Detect drift between columns the ORM declares as a native SQLAlchemy Enum (which generates a
real Postgres enum type and CASTs bind parameters to it) and what the live database actually
has for that column.

Background: several tables this session (ml_jobs, risk_signals, legal_holds,
compliance_snapshots, payroll_exceptions, ghost_worker_detections, upsell_opportunities, ...)
were found to declare `mapped_column(Enum(SomeEnum), ...)` while the live column is plain
VARCHAR -- a category of bug invisible to tests that build tables via
`Base.metadata.create_all()` (which always creates whatever the model says, enum type included),
since it only ever shows up against a database built by real Alembic migrations. See
docs/IMPLEMENTATION_ROADMAP.md Phase 3.4 (Finding 2) and docs/REMEDIATION_LOG.md.

Usage:
    DATABASE_URL_ASYNC=postgresql+asyncpg://user@localhost/dbname \
        python scripts/check_enum_type_drift.py [--verbose]

Exits non-zero if any mismatch is found.
"""
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import Enum as SQLEnum

from app.database import Base
import app.models  # noqa: F401 - ensure all models register on Base.metadata

COLUMN_TYPE_SQL = """
    SELECT data_type, udt_name
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = :table_name AND column_name = :column_name
"""


async def main() -> int:
    verbose = "--verbose" in sys.argv
    db_url = os.environ.get("DATABASE_URL_ASYNC")
    if not db_url:
        print("DATABASE_URL_ASYNC is required", file=sys.stderr)
        return 2

    engine = create_async_engine(db_url)
    mismatches = []
    checked = 0

    async with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            for column in table.columns:
                if not isinstance(column.type, SQLEnum):
                    continue
                if column.type.native_enum is False:
                    continue
                checked += 1
                result = await conn.execute(
                    text(COLUMN_TYPE_SQL),
                    {"table_name": table.name, "column_name": column.name},
                )
                row = result.mappings().first()
                if row is None:
                    mismatches.append(
                        f"{table.name}.{column.name} -> model declares native Enum, "
                        f"but this column does not exist on the live table at all"
                    )
                    continue
                if row["data_type"] != "USER-DEFINED":
                    mismatches.append(
                        f"{table.name}.{column.name} -> model declares native Enum "
                        f"(would bind as ::{column.type.name}), but the live column is "
                        f"{row['data_type']} ({row['udt_name']})"
                    )
                elif verbose:
                    print(f"OK: {table.name}.{column.name} -> {row['udt_name']}")

    await engine.dispose()

    print(f"\nTotal native-Enum columns checked: {checked}")
    print(f"Mismatches (model expects a real DB enum type that isn't there): {len(mismatches)}\n")
    for m in mismatches:
        print(f"  {m}")

    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
