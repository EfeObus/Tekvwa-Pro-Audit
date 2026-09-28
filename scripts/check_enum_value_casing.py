"""
Detect drift between the exact string values a SQLAlchemy `Enum(SomeEnum)` column would send to
Postgres and the labels the live database's native enum type actually has.

Background (docs/IMPLEMENTATION_ROADMAP.md Phase 3, Finding 1 / docs/PRODUCTION_AUDIT_2026.md
§1.2): without `values_callable=...`, SQLAlchemy's default behavior for a native `Enum` column is
to persist the Python enum member's `.name` (e.g. "REALIZED"), not its `.value` (e.g. "realized").
Many of this codebase's native Postgres enum types were created by hand-written migrations using
lowercase values matching `.value`, not `.name` -- any ORM write to one of these columns sends a
value that does not exist in the live enum type, and Postgres rejects it with
`invalid input value for enum <type>`. This is invisible until application code actually tries to
write a non-default value through the ORM.

This script is the complement to check_enum_type_drift.py (which checks whether a column is a real
native enum type *at all* -- Finding 2). This one assumes the column genuinely is a native enum type
(skips anything check_enum_type_drift.py would already flag) and checks whether SQLAlchemy's
resolved values for that column actually exist as labels on the live type.

Usage:
    DATABASE_URL_ASYNC=postgresql+asyncpg://user@localhost/dbname \
        python scripts/check_enum_value_casing.py [--verbose]

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

ENUM_LABELS_SQL = """
    SELECT e.enumlabel
    FROM pg_enum e
    JOIN pg_type t ON e.enumtypid = t.oid
    WHERE t.typname = :type_name
    ORDER BY e.enumsortorder
"""

# Columns with a genuine value-set divergence (not just casing) between the model's Python enum
# and the live Postgres type -- Finding 1b/1c (docs/IMPLEMENTATION_ROADMAP.md §3.2/§3.3,
# docs/REMEDIATION_LOG.md's Phase 3 entry). These are blocked on a product/business decision, not
# a mechanical values_callable fix, so this script must not fail CI on them. Any NEW mismatch this
# script finds that isn't in this set still fails the build.
KNOWN_VALUE_SET_DIVERGENCES = {
    ("feature_access_logs", "feature"),
    ("invoices", "buyer_status"),
    ("wht_credit_notes", "status"),
    ("fiscal_periods", "status"),
    ("journal_entries", "entry_type"),
    ("journal_entries", "status"),
}


async def main() -> int:
    verbose = "--verbose" in sys.argv
    db_url = os.environ.get("DATABASE_URL_ASYNC")
    if not db_url:
        print("DATABASE_URL_ASYNC is required", file=sys.stderr)
        return 2

    engine = create_async_engine(db_url)
    mismatches = []
    known_divergences_seen = []
    checked = 0
    skipped_not_native = 0

    async with engine.connect() as conn:
        for table in Base.metadata.tables.values():
            # .values(), not .sorted_tables: this script only reads, no DDL ordering is needed, and
            # sorted_tables warns/fails on the credit_notes<->invoices mutual FK cycle.
            for column in table.columns:
                if not isinstance(column.type, SQLEnum):
                    continue
                if column.type.native_enum is False:
                    continue

                col_result = await conn.execute(
                    text(COLUMN_TYPE_SQL),
                    {"table_name": table.name, "column_name": column.name},
                )
                col_row = col_result.mappings().first()
                if col_row is None or col_row["data_type"] != "USER-DEFINED":
                    # Not a real native enum column on the live DB at all -- that's
                    # check_enum_type_drift.py's finding (Finding 2), not this script's.
                    skipped_not_native += 1
                    continue

                checked += 1
                live_type_name = col_row["udt_name"]

                label_result = await conn.execute(
                    text(ENUM_LABELS_SQL), {"type_name": live_type_name}
                )
                live_labels = {row[0] for row in label_result.all()}

                would_send = set(column.type.enums) if column.type.enums else set()
                # column.type.enums holds the exact strings SQLAlchemy will bind, honoring
                # values_callable if one is set, and falling back to member .name otherwise.

                missing = would_send - live_labels
                if missing:
                    entry = (
                        f"{table.name}.{column.name} (Postgres type {live_type_name}) -> "
                        f"would send {sorted(missing)}, not present in live labels "
                        f"{sorted(live_labels)}"
                    )
                    if (table.name, column.name) in KNOWN_VALUE_SET_DIVERGENCES:
                        known_divergences_seen.append(entry)
                    else:
                        mismatches.append(entry)
                elif verbose:
                    print(f"OK: {table.name}.{column.name} -> {live_type_name} ({sorted(would_send)})")

    await engine.dispose()

    print(f"\nNative-enum columns checked for value-casing drift: {checked}")
    print(f"(skipped {skipped_not_native} columns that aren't real native enum types on the live DB "
          f"-- see check_enum_type_drift.py for those)")
    print(f"Known, deliberately-unfixed value-set divergences (Finding 1b/1c, blocked on a product "
          f"decision - see docs/REMEDIATION_LOG.md): {len(known_divergences_seen)}")
    for m in known_divergences_seen:
        print(f"  (known, not failing CI) {m}")
    print(f"New/unexpected mismatches (fails CI): {len(mismatches)}\n")
    for m in mismatches:
        print(f"  {m}")

    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
