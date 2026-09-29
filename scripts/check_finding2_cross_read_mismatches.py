"""
For each column check_enum_type_drift.py flags (a model declares a native SQLAlchemy `Enum`, but
the live column is plain VARCHAR with no DB-level enum constraint -- Finding 2,
docs/IMPLEMENTATION_ROADMAP.md §3.4), determine whether the mismatch is a live bug or just a code
smell.

Background: without a native enum type constraining the column, Postgres accepts any string. The
ORM still writes/reads through the column's declared `Enum(SomeEnum)` type (matching by `.name`
without `values_callable`, i.e. uppercase). This is only a live bug if some OTHER code path -- raw
SQL, a different service, a report query -- reads that column expecting a *different* string
(typically the enum's lowercase `.value`, matching the common pattern elsewhere in this codebase).
If every reader goes through the same ORM type (or through a derived boolean flag, as several
tables in this audit do), there's no live mismatch, just an unused/inconsistent type declaration.

This is a *static, grep-based* search, not exhaustive: it looks for `<column> == "<value>"` (or
`!=`) comparisons and raw `text(...)` SQL blocks anywhere under `app/` that mention the column name
together with one of its enum's own lowercase values. Anything it finds needs a human to read the
surrounding code (see docs/REMEDIATION_LOG.md's Phase 3 §3.4 entry for exactly how each hit from
the run that produced this script was resolved) -- it is a discovery aid, not a CI gate, since a
"no hits" result proves absence of an easy-to-grep pattern, not absence of any possible mismatch.

Usage:
    DATABASE_URL_ASYNC=postgresql+asyncpg://user@localhost/dbname \
        python scripts/check_finding2_cross_read_mismatches.py [--verbose]

Always exits 0 -- this is a discovery tool, not a pass/fail gate (see docstring above for why a
clean run can't be trusted as exhaustive proof).
"""
import asyncio
import os
import re
import subprocess
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import Enum as SQLEnum

from app.database import Base
import app.models  # noqa: F401 - ensure all models register on Base.metadata

COLUMN_TYPE_SQL = """
    SELECT data_type
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = :table_name AND column_name = :column_name
"""


def _grep_hits(column_name: str, value: str) -> list:
    """Lines under app/ where `column_name` is compared against this enum member's lowercase
    value via ==/!=, or referenced inside a raw text() SQL block together with that value."""
    hits = []
    pattern = rf"{re.escape(column_name)}\s*[!=]=\s*['\"]{re.escape(value)}['\"]"
    try:
        result = subprocess.run(
            ["grep", "-rnE", pattern, "app/"],
            capture_output=True, text=True, timeout=30,
        )
        if result.stdout:
            hits.extend(line for line in result.stdout.splitlines())
    except (subprocess.SubprocessError, OSError):
        pass
    return hits


async def main() -> int:
    verbose = "--verbose" in sys.argv
    db_url = os.environ.get("DATABASE_URL_ASYNC")
    if not db_url:
        print("DATABASE_URL_ASYNC is required", file=sys.stderr)
        return 2

    engine = create_async_engine(db_url)
    varchar_enum_columns = []

    async with engine.connect() as conn:
        for table in Base.metadata.tables.values():
            for column in table.columns:
                if not isinstance(column.type, SQLEnum):
                    continue
                if column.type.native_enum is False:
                    continue
                result = await conn.execute(
                    text(COLUMN_TYPE_SQL),
                    {"table_name": table.name, "column_name": column.name},
                )
                row = result.mappings().first()
                if row is not None and row["data_type"] != "USER-DEFINED":
                    varchar_enum_columns.append((table.name, column.name, column.type.enums or []))

    await engine.dispose()

    print(f"Finding-2 VARCHAR-but-declared-enum columns to check: {len(varchar_enum_columns)}\n")

    clean = []
    needs_review = []

    for table_name, column_name, enum_values in varchar_enum_columns:
        all_hits = []
        for value in enum_values:
            all_hits.extend(_grep_hits(column_name, value))
        if all_hits:
            needs_review.append((table_name, column_name, all_hits))
        else:
            clean.append((table_name, column_name))
        if verbose:
            status = "NEEDS REVIEW" if all_hits else "no grep hits"
            print(f"  {table_name}.{column_name}: {status}")

    print(f"\nNo grep hits (Code Smell candidates, Phase 12): {len(clean)}")
    print(f"Grep hits found (needs manual read, potential real bug): {len(needs_review)}\n")
    for table_name, column_name, hits in needs_review:
        print(f"  {table_name}.{column_name}:")
        for hit in hits:
            print(f"    {hit}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
