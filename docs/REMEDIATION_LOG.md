# Remediation Log

Running, dated log of every section completed against `docs/IMPLEMENTATION_ROADMAP.md`, its commit
hash, and its deployment verification result. This is the implementation team's own audit trail —
separate from `docs/CHANGELOG.md` (user-facing) and `docs/AUDIT_CHECKLIST.md` (the original audit's
own section-tracking record). Update this file as the single detailed narrative account; keep
`docs/IMPLEMENTATION_ROADMAP.md`'s §20 traceability table as the fast-scan status view — the two must
agree.

See also: `docs/PRODUCTION_AUDIT_2026.md` (the original 48-finding audit) and
`docs/IMPLEMENTATION_ROADMAP.md` (the phased plan this log tracks execution against).

---

## Phase 0 — Baseline, Safety, and Implementation Control

**Started:** 2026-09-19

### 0.1 Repository baseline

- Branch: `main`. Working tree had uncommitted audit-phase documentation (root-to-`docs/` moves of
  `BUILD_PROGRESS.md`/`CHANGELOG.md`/`CONTRIBUTING.md`, plus new `docs/AUDIT_CHECKLIST.md`,
  `docs/PRODUCTION_AUDIT_2026.md`, `docs/IMPLEMENTATION_ROADMAP.md`) and 6 unpushed commits from prior
  session work (GCP migration, Railway removal, rebrand, TemplateResponse fix).
- Committed the documentation reorganization as `3f082bc` ("Add production audit report, checklist,
  and implementation roadmap; move root docs into docs/").
- Tagged `pre-remediation-baseline` at `3f082bc`.
- **Open decision, not yet resolved:** whether to push the now-7 unpushed commits (6 prior + this one)
  to `origin/main` as part of establishing the baseline, or hold them local until a later point. Not
  pushed yet as of this log entry — flagged to the user, awaiting confirmation, since this affects the
  shared remote.
- Local production Docker build (`docker build --target production .`): **succeeded**, no errors (4
  pre-existing lint-style Dockerfile warnings only, not new).

### 0.1 continued — Test suite baseline: DISCREPANCY FOUND, under investigation

Ran the full suite against a database built via the **real Alembic migration chain**
(`alembic upgrade head` against a fresh local Postgres database), matching the audit's own §13.1
methodology and this roadmap's Phase 1.3 plan — deliberately *not* using `tests/conftest.py`'s current
`Base.metadata.create_all()` path, specifically to get an accurate picture of what Phase 1.3 will
surface.

**Result: 726 passed, 20 failed, 1 skipped, 246 errored** — a large increase in errors from the
audit's own original baseline (773 passed / 19 failed / 42 errored, which was run against a
`create_all()`-built schema, not a migrated one).

**Root cause identified (in progress, being fully quantified):** `app/models/invoice.py`'s
`Invoice.credit_note_id` column does not declare `ForeignKey('credit_notes.id')` at the ORM level,
even though `alembic/versions/20260103_1430_2026_tax_reform_updates.py` creates a real
`fk_invoice_credit_note` foreign-key **constraint** on the live table
(`op.create_foreign_key('fk_invoice_credit_note', 'invoices', 'credit_notes', ['credit_note_id'],
['id'], ondelete='SET NULL')`). `Base.metadata` therefore has no knowledge `invoices` depends on
`credit_notes`. `tests/conftest.py`'s function-scoped fixture calls `Base.metadata.drop_all()` after
every single test; when run against a schema where the real constraint actually exists (i.e., a
migrated schema, not a `create_all()`-built one), SQLAlchemy's drop ordering — computed without
knowledge of this constraint — can attempt to drop `credit_notes` before `invoices`, and Postgres
correctly rejects it: `DependentObjectsStillExistError: cannot drop table credit_notes because other
objects depend on it`.

**Why the original audit never saw this:** the audit's full-suite run (Section 15 of
`docs/PRODUCTION_AUDIT_2026.md`) used `Base.metadata.create_all()` to build its test schema, exactly as
`conftest.py` currently does by default. `create_all()` only creates what the ORM models declare —
since the FK isn't declared on the model, `create_all()` never created the constraint at all, so the
ordering conflict was structurally impossible to hit in that environment. This is the same blind spot
Finding 41 exploited, now confirmed to hide at least one more real defect.

**This is a new finding, not one of the audit's original 48.** Logged here per Phase 1.3's own
instruction ("triage each one as its own finding... route it to the correct phase") rather than folded
silently into an existing finding number or the raw pass/fail count reported without explanation.

**Finding number: Finding 49 — CONFIRMED, P1 High: 93 real foreign-key constraints exist in the live
migrated database with no matching declaration in the SQLAlchemy models, across 3 distinct root
causes.**

### Full investigation and resolution

Wrote a permanent diagnostic script
(`app/../scratchpad/fk_drift_check.py` during investigation; the reusable version should live at
`scripts/check_fk_drift.py` — see Recommended Fix below) that queries `information_schema` for every
real FK constraint in a migrated database and cross-references each one against
`Base.metadata`. Result against a fresh `alembic upgrade head` database: **297 real FK constraints,
93 with no matching model declaration**, in three categories:

| Category | Count | Root cause |
|---|---|---|
| Table not in ORM metadata at all | 42 | Finding 19 (already known) — `payroll_advanced.py`'s 11 tables never imported by `app/models/__init__.py`. All 42 constraints belong to these 11 tables. |
| Column not in ORM metadata at all | 36 | The model doesn't declare the column at all, even though the DB has it (with an FK). Spans 29 tables. |
| Column exists, but no `ForeignKey()` declared | 15 | The model has the column as a plain UUID; a migration added a real constraint the ORM never learned about. |

**Fixed in this session (57 of 93):**
- Applied Finding 19's own recommended fix (`app/models/__init__.py` now imports all 11
  `payroll_advanced.py` classes) — resolved all 42 "table not registered" mismatches.
- Added `ForeignKey(...)` to the 15 "column exists, no FK declared" columns:
  `audit_logs.impersonated_by_id`, `audit_logs.organization_id`, `organizations.emergency_suspended_by_id`,
  `invoices.credit_note_id`, `invoices.original_invoice_id`, `invoices.nrs_cancelled_by_id`,
  `transactions.original_category_id`, and (on the 7 specific model classes that actually have the
  constraint — `ChartOfAccounts`, `JournalEntry`, `RecurringJournalEntry`, `Employee`, `PayrollRun`,
  `StatutoryRemittance`, `EmployeeLoan`) `created_by_id`/`updated_by_id` overrides of the shared
  `AuditMixin`.

**Explicitly reverted and corrected mid-investigation — a genuine mistake caught before it shipped:**
first attempt added `ForeignKey('users.id')` directly to `AuditMixin.created_by_id`/`updated_by_id`
(the shared base class). This looked like the obvious fix since 16 different models use the mixin, but
**only 7 of those 16 tables actually have the matching constraint in the live database** — the other
9 (`bank_accounts`, `bank_reconciliations`, `expense_claims`, `stock_movements`, `stock_write_offs`,
`legal_holds`, `invoices`, `opening_balance_imports`, `report_templates`, `transactions`) were never
covered by a migration for this specific constraint. Applying the fix to the mixin caused *new* test
failures (confirmed via a full-suite re-run: 726→679 passed, 246→280 errors) because SQLAlchemy's
`create_all()`/`drop_all()` cycle now expected a constraint on all 16 tables that only 7 actually have.
**Reverted the mixin change; applied the fix individually to only the 7 correct model classes
instead**, each with a comment explaining why the other 9 are deliberately left alone. Recorded here
in full because this is exactly the kind of self-correction this roadmap's gates exist to catch, and
because a future contributor touching `AuditMixin` again needs to know *why* it doesn't have the FK
before "helpfully" re-adding it.

**Two further real bugs surfaced and fixed as a direct consequence of the above 15 fixes, not separate
pre-existing findings:**
- `organizations.emergency_suspended_by_id`'s real constraint was created via a bare inline
  `ForeignKey()` in its migration, which bypasses this codebase's configured SQLAlchemy
  `naming_convention` (`app/database.py`) and got a Postgres-default name
  (`organizations_emergency_suspended_by_id_fkey`) instead of the convention's
  `fk_organizations_emergency_suspended_by_id_users`. Declaring the FK without an explicit matching
  `name=` caused `DROP CONSTRAINT` to fail against the real name. Fixed by passing the exact name
  explicitly.
- Adding `ForeignKey('categories.id')` to `transactions.original_category_id` gave `Transaction` two
  FK columns to `categories` (the pre-existing `category_id` and the newly-declared
  `original_category_id`), which made the existing `Category.transactions`/`Transaction.category`
  `relationship()` pair ambiguous (`AmbiguousForeignKeysError`). Fixed by adding explicit
  `foreign_keys="Transaction.category_id"` to both sides of that relationship.

**Verified via 3 independent methods before considering this closed:**
1. `alembic revision --autogenerate` against an already-migrated database produces **zero**
   `create_foreign_key`/`drop_foreign_key` operations for any of the 57 fixed columns — confirmed
   DDL-neutral for existing (production) databases; no migration is needed to ship this.
2. The full drift-check script, re-run against a fresh `alembic upgrade head` database, shows exactly
   0 remaining mismatches in the two fixed categories, and a stable 51 in the untouched third category
   (spanning 29 tables — see "Remaining work" below).
3. The specific test that first surfaced this (`test_api.py::TestVendorsAPI::test_create_vendor`) now
   fails for a *different*, already-documented, already-scoped reason (Finding 1's enum-casing bug —
   `invalid input value for enum businesstype: "LIMITED_COMPANY"`, Phase 3 work) instead of the
   FK-ordering `DependentObjectsStillExistError` it failed with before — confirming the fix resolves
   the actual problem rather than papering over the symptom.

**Remaining work (51 mismatches, 29 tables) — deliberately not rushed in this session:** the "column
not in ORM metadata at all" category requires adding a genuinely new column declaration to each
affected model (not just an annotation on an existing one), which means checking each column's exact
type/nullable/default against its migration individually — 29 tables' worth of careful, individually-
verified edits, the same standard already applied to the 57 fixed here. Full list by table:
`payroll_impact_previews` (4), `intercompany_transactions` (4), `ticket_comments` (3),
`ticket_attachments` (3), `fixed_assets` (3), `bank_reconciliations` (3), `ytd_payroll_ledgers` (2),
`wht_credit_notes` (2), `what_if_simulations` (2), `risk_signals` (2), `payroll_exceptions` (2),
`expense_claims` (2), `employee_variance_logs` (2), `depreciation_entries` (2), and 15 further tables
with 1 each (`upsell_activities`, `three_way_matches`, `support_tickets`, `risk_signal_comments`,
`payment_transactions`, `opening_balance_imports`, `ml_jobs`, `ledger_entries`,
`ghost_worker_detections`, `expense_claim_items`, `ctc_snapshots`, `budget_periods`,
`bank_statement_transactions`, `approval_workflow_approvers`, `approval_requests`).

**This is why the full test suite's pass/fail/error counts did not visibly improve in this session**
despite 57 real, confirmed, verified fixes: the remaining 51 mismatches are spread across enough
different tables that most test files still hit at least one of them during
`Base.metadata.create_all()`/`drop_all()`, plus the already-known Finding 1 enum-casing bug (Phase 3)
independently affects many of the same test paths. The 57 fixes are real and necessary, not sufficient
on their own to unblock Phase 1.3's planned switch to a migration-built test schema — **Phase 1.3 is
now understood to be gated on resolving all 51 remaining mismatches first**, not just "likely to
surface a few more" as originally anticipated when Phase 1.3 was drafted.

**Additional, separate discovery, not yet actioned:** `app/services/compliance_penalty_service.py`
defines a real model class (`PenaltyRecord`, `__tablename__ = "penalty_records"`) inside a *service*
file rather than `app/models/`. It registers correctly in the real running app (since `main.py`
imports `tax_2026.py`, which imports this service, at startup) but is invisible to any test harness or
script that imports `app.models` without also importing this specific service — the same "incidental,
import-order-dependent registration" fragility pattern as Finding 19, just not caught by the audit's
original sweep because it isn't in `app/models/` at all. Logged here as a code-smell/architecture
finding for Phase 12 (move the model to `app/models/`), not fixed in this session.

**Recommended fix, beyond what's already done:** promote `fk_drift_check.py` (currently a scratch
script) into a permanent `scripts/check_fk_drift.py`, and add it as a CI check alongside Finding 1's
own recommended enum-compatibility check (§1 of the roadmap) — both are the same class of "model and
migration silently disagree" problem, and both are cheap to check permanently once written.

**Status:** ✅ Investigated and partially fixed (57/93). Remaining 51 formally scoped and routed to
Phase 1 proper (added as Phase 1, Section 1.5 in `docs/IMPLEMENTATION_ROADMAP.md`) rather than
completed under time pressure in this session.

### 0.2 Deployment baseline

- Current Cloud Run revision: `proaudit-web-00012-6sb`, 100% traffic. Recorded as the rollback target
  for the duration of this remediation effort.
- Recent Cloud SQL backup confirmed present (`gcloud sql backups list`): backup ID `1789783200000`,
  window start `2026-09-19T02:00:00Z`, status `SUCCESSFUL` — recent enough that no additional on-demand
  backup was taken during Phase 0 itself (Phase 0 makes no production changes). A **fresh** on-demand
  backup will be taken immediately before Phase 1's first migration runs against production, per the
  roadmap's plan.
- `alembic_version` head vs. repo migration files: not yet cross-checked against the *live production*
  database (would require the same production-DB access that was blocked during the original audit —
  see `docs/AUDIT_CHECKLIST.md` §6's note). Deferred to immediately before Phase 1's production
  migration step, where it becomes load-bearing rather than just informational.

### 0.3 / 0.4

- CI non-blocking annotation (visibility without gating) — not yet implemented.
- This file created as the documentation foundation.

---

## Phase 1, Section 1.5 — Finding 49 remainder: STOPPED, new Finding 50 discovered

**Started:** 2026-09-19

Began the planned mechanical fix of the 51 remaining Finding-49 mismatches (29 tables — see Phase 0's
full list above). Re-ran the newly-promoted `scripts/check_fk_drift.py --verbose` against a freshly
migrated scratch database (`fk_drift_verify`, `alembic upgrade head`, same clean venv used throughout
this audit) to get exact DB-side type/nullable/on-delete detail for each column before writing any
model changes — confirmed the same 51 mismatches, same 29 tables, exact match with Phase 0's list.

**While pulling per-column detail for the first few tables, found something the mechanical fix cannot
safely paper over.** Checked the full `CREATE TABLE`/`ALTER TABLE` history (not just the FK constraint)
for every table in the three highest-count files before writing a single line of model code, per this
roadmap's own instruction not to rush per-column edits. Result:

**Finding 50 (NEW, not in the original 48, not the same shape as Finding 49) — CONFIRMED, severity
provisionally P1 pending full scope (see "Not yet fully scoped" below): for a significant number of
tables scoped under Finding 49's "column not in ORM metadata at all" category, the missing column is
not an isolated oversight — the model's column set for that table diverges substantially from what its
own migration(s) actually created:** different column names for the same concept, different
nullability, extra model-only columns with no DB equivalent, missing DB-only columns with no model
equivalent, and in at least one case a different enum's *value set* entirely. Confirmed present, with
full detail, in:

- **`IntercompanyTransaction` (`app/models/advanced_accounting.py`, table `intercompany_transactions`)**
  — model declares `from_entity_id`/`to_entity_id`/`from_transaction_id`/`to_transaction_id`/
  `transaction_date`/`currency`/`notes`/`elimination_date`; the live table (per
  `alembic/versions/20260106_1600_advanced_accounting.py:401-419`, confirmed unchanged by any later
  migration) actually has `source_entity_id`/`target_entity_id`/`source_transaction_id`/
  `target_transaction_id`/`description`/`eliminated_at`, and has **no** `transaction_date` or `currency`
  column at all. **This is live, reachable code, not dead code**: `POST /intercompany`
  (`app/routers/advanced_accounting.py:981-1047`) constructs an `IntercompanyTransaction(...)` using the
  model's (wrong) attribute names on every single call, so every call to this endpoint fails
  deterministically with `UndefinedColumnError` the moment it reaches `db.flush()`. Also used by
  `GET /intercompany` (same router, ~line 1078) and `ConsolidationService.get_unrealized_intercompany_profit`
  (`app/services/consolidation_service.py:721-725`) — both query using the same wrong attribute names and
  would fail identically the moment a real row existed to query, and cannot currently create one to test
  against.
- **`ApprovalRequest`/`ApprovalWorkflowApprover`/`LedgerEntry`/`ThreeWayMatch`/`WHTCreditNote`
  (`app/models/advanced_accounting.py`)** — each checked individually against
  `alembic/versions/20260106_1600_advanced_accounting.py`'s actual `CREATE TABLE` statements (lines
  180–221, 301–371). All five show the same pattern: model-only columns with no DB equivalent (e.g.
  `ApprovalRequest.required_approvals`/`current_approvals`/`current_rejections`/`resource_data`/
  `requested_by_id`/`requested_at`, none of which exist on the real table, which instead has `amount`/
  `submitted_by_id`/`context`), DB-only columns with no model equivalent, and for `ApprovalRequest` and
  `ThreeWayMatch` specifically, the model's own Python `Enum` (`ApprovalStatus`, `MatchingStatus`) has a
  **different value set** than the Postgres `ENUM` type actually installed (e.g. model's
  `ApprovalStatus.PARTIALLY_APPROVED` has no matching DB enum label; DB's `'cancelled'` label has no
  matching Python member) — confirmed live via `LedgerEntry`
  (`app/services/immutable_ledger.py`, `app/services/accounting_service.py`,
  `app/services/forensic_audit_service.py`, `app/routers/forensic_audit.py`), `ThreeWayMatch`
  (`app/services/three_way_matching.py`, `app/routers/forensic_audit.py`), `WHTCreditNote`
  (`app/services/wht_credit_vault.py`, `app/services/audit_reporting.py`,
  `app/routers/advanced_accounting.py`), `ApprovalWorkflowApprover`/`ApprovalRequest`
  (`app/services/approval_workflow.py`, `app/services/budget_service.py`,
  `app/routers/expense_claims.py`) — **all confirmed live and reachable, none dead code.**
- **`BankReconciliation` (`app/models/bank_reconciliation.py`, table `bank_reconciliations`)** — same
  pattern, confirmed against the table's actual, current DDL (this table was fully dropped and
  recreated by a later migration, `alembic/versions/20260118_1200_bank_reconciliation_comprehensive.py:285-338`,
  so this is checked against its *final* real shape, not a stale intermediate one). Model declares
  `statement_opening_balance`/`statement_closing_balance`/`book_opening_balance`/`book_closing_balance`
  (all `NOT NULL`); the real table has `statement_ending_balance`/`ledger_ending_balance` instead (no
  "opening" variants of either exist in the DB at all) — meaning any INSERT via this model omits two
  real `NOT NULL` DB columns entirely (`statement_ending_balance`, `ledger_ending_balance`) while trying
  to write four columns that don't exist. Also missing from the model entirely: `prepared_at`,
  `reviewed_at`, `rejection_reason`, the Nigerian-specific charge/statistics columns
  (`total_emtl`/`total_stamp_duty`/`total_vat_on_charges`/`total_wht_deducted`/`total_transactions`/
  `matched_transactions`/`unmatched_bank_transactions`/`unmatched_book_transactions`/
  `auto_matched_count`/`manual_matched_count`). Model-only, no DB equivalent: `completed_at`/
  `completed_by_id`.
- **`PayrollImpactPreview` (`app/models/payroll_advanced.py`, table `payroll_impact_previews`)** — model
  imagines a "current period totals vs. previous period totals" comparison record
  (`current_gross`/`previous_payroll_id`/etc.); the real table
  (`alembic/versions/20260110_1000_add_advanced_payroll_tables.py:70-90`) implements a completely
  different concept — a field-level change-log row (`change_type`/`field_changed`/`old_value`/
  `new_value`/`impact_on_gross`/`impact_on_tax`/`impact_on_pension`/`impact_on_net`/`impact_details`).
  Also: the model declares `payroll_run_id` as `NOT NULL, unique=True`; the real column is nullable with
  no uniqueness constraint.

**Confirmed NOT part of this problem (verified individually, genuinely simple missing-FK cases):**
`transactions.original_category_id`, `organizations.emergency_suspended_by_id`, `invoices.*`,
`audit_logs.*`, `accounting.py`/`payroll.py`'s `created_by_id`/`updated_by_id` overrides — i.e.
everything already fixed in Phase 0. Within the *remaining* 51, `budget_periods.tenant_id` is
individually confirmed genuinely simple (the table's current DDL,
`alembic/versions/20260127_1100_add_budget_period_revision_fields.py:91-134`, matches the model's other
declared columns field-for-field; `tenant_id` really is just a bare additional nullable FK the model
never picked up) — this one alone would be safe to fix mechanically.

**Not yet fully scoped:** the remaining 21 of 51 mismatches (in `fixed_asset.py`, `expense_claims.py`,
`ml_job.py`, `sku.py`, `risk_signal.py`, `support_ticket.py`, `upsell.py`) have **not** been individually
checked against their migrations yet. Given the pattern is now confirmed in 3 of the largest-count files
(30 of 51 mismatches, all in live/reachable code, not isolated to one model author or one work session),
**do not assume these 21 are simple** — per this roadmap's own instruction against assuming success
where verification is incomplete. Each needs the same individual DDL-vs-model check before any fix.

**Why this stopped rather than continuing to "fix":** the mechanical fix this section was scoped to
do — add a `ForeignKey()` to an existing or new column — would be actively misleading here. Declaring
`IntercompanyTransaction.source_entity_id` with a correct `ForeignKey()` while the model still also
declares a non-existent `from_entity_id` fixes zero real bugs; the endpoint still crashes on every call.
Marking Finding 49 §1.5 "done" after only patching FK annotations on these tables would create false
confidence that these features work, when they are currently, and were probably always, completely
non-functional against the real database.

**Decision needed before this section can continue (not made unilaterally — see conversation):**
whether to (a) write new migrations bringing the live schema up to match each model's fuller, apparently
-intended shape, (b) cut each model back down to match what the database actually has and adjust the
dependent router/service code to match, table by table, or (c) some mix decided per-table depending on
which shape reflects the actually-intended, currently-marketed feature behavior — a product decision,
not a schema decision, since (a) and (b) produce different real user-facing behavior for features like
intercompany elimination, bank reconciliation statistics, and payroll impact previews.

**Status:** ⚠️ Stopped mid-section, not fixed. Finding 50 opened and documented above. Original Finding
49 §1.5 scope (mechanical FK-annotation fixes) is now understood to be blocked on resolving Finding 50
first for at least 3 of 29 tables, and possibly more pending the remaining 21 tables' individual checks.
`budget_periods.tenant_id` is the one column in this section confirmed safe to fix mechanically without
waiting on that decision — fixed, verified DDL-neutral, and committed separately from this finding.

**Scale check — how far Finding 50 actually extends beyond the 3 files above:** fixed
`budget_periods.tenant_id`, then ran `alembic revision --autogenerate` once against the full current
model set (all Phase 0 fixes + this one column) as a diagnostic-only, never-committed check of *total*
model/DB drift across the whole schema, not just the 51 columns Finding 49 originally scoped. Result:
**755 columns the autogenerate tool wants to add, 755 it wants to drop, 1274 `alter_column` operations,
171 foreign-key changes, across 66 distinct tables** (out of 123 registered). Some fraction of the
`alter_column` count is very likely cosmetic autogenerate noise (e.g. `server_default` timestamp
comparison quirks that are a known Alembic false-positive pattern, not real drift) — **not yet separated
from real drift, and deliberately not assumed to be all-cosmetic either**, per this roadmap's own rule
against assuming success where verification is incomplete. The exactly-matched 755/755 add/drop count is
the strongest concrete signal: at minimum, it means renamed-or-retyped columns exist at roughly that
scale across roughly half the schema's tables. The generated migration file was diagnostic only,
reviewed, and deleted — not committed.

**This means Finding 50 is not a bounded extension of Finding 49 (a few extra tables needing careful
column-adds) — it is a separate, schema-wide finding of unknown but apparently large scope**, discovered
as a side effect of trying to close Finding 49's remainder, not something either finding's original
scoping anticipated. Continuing to treat it as "part of §1.5" would misrepresent both its size and its
risk. Flagged to the user rather than either continuing to fix piecemeal or minimizing it — see
conversation for the decision requested.

---

*(Continue this log per-section as Phases 1–14 proceed. Do not skip an entry because a section seemed
straightforward — the original audit's own instruction against skipping "simple" work applies equally
here.)*
