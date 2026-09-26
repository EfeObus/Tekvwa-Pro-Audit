# Finding 50 — Full Scope

**Status:** Scoped, not yet remediated. See `docs/REMEDIATION_LOG.md` (Phase 1, Section 1.5 entry) for
how this was discovered — while mechanically fixing Finding 49's last 51 "missing ForeignKey" columns,
the columns turned out not to be isolated oversights but symptoms of models whose column sets diverge
from their own migrations at a much larger scale.

**Severity: P0/P1, CONFIRMED.** Not a single defect — a systemic pattern across the "advanced feature"
half of the application (accounting extensions, payroll extensions, bank reconciliation, ML/risk
detection, support tickets, upsell tracking, budgets/approvals, intercompany consolidation). This
document exists so the pattern can be judged and remediated as one coherent piece of work rather than
discovered piecemeal, table by table, the way Finding 49 was.

## How this was measured

A diagnostic-only `alembic revision --autogenerate` was run against a database built via the real
migration chain (`alembic upgrade head`, clean scratch database, same method as every other verification
in this audit) with every current model (including all of Phase 0's Finding 49 fixes) loaded. The
generated migration was reviewed and then deleted — never committed, never applied to any real
database. Its every operation was parsed and bucketed by table and by category with a one-off script
(not committed; available in this session's scratch history if needed again).

**Total: 109 of 123 registered tables show at least one detected difference.** Categories:

| Category | Meaning | Count |
|---|---|---|
| `ADD_DROP` | Column the model has but the DB doesn't, paired with a column the DB has but the model doesn't — the strongest signal of real drift (usually a rename or a wholesale re-imagining of the table) | 755, across 66 tables |
| `NULLABLE` | Same column, same type, different nullability between model and DB | real but milder — often just means the model is stricter or looser than what the DB actually enforces |
| `TYPE` | Same column, different type/length | real, severity varies (e.g. `VARCHAR(100)` vs `String(50)` risks silent truncation; most others are benign) |
| `FK` | Foreign-key constraint added/changed | real, same class of issue as Finding 49, now folded into this table-level view |
| `ENUM` | Enum value-set or type-name mismatch | **this is already-known Finding 1** (the audit's own headline enum-casing bug), not new — appears here because it shows up on every enum column, in every table, not just the one place Finding 1 was originally illustrated |
| `TIMESTAMP` | `TIMESTAMP()` (raw introspection) vs `DateTime(timezone=True)` (model) with nothing else different | likely cosmetic — a known Alembic autogenerate comparator quirk — but **not yet confirmed cosmetic on every instance**, so not assumed safe to ignore everywhere |
| `INDEX_UQ` | Index/unique-constraint-only differences | likely cosmetic naming-convention differences, same reasoning as `TIMESTAMP` |

**The `ADD_DROP` count (755, across 66 tables) is this finding's real substance.** It is not evenly
spread — it concentrates almost exactly on the app's "advanced feature" surface, and confirmed, via
direct code reading (not just the automated diff), to represent genuinely different table shapes, not
autogenerate noise, in every case checked by hand so far (8 tables — see `docs/REMEDIATION_LOG.md`).

## Severity tiers (by `ADD_DROP` count on that table)

**Tier 1 — Severe (≥15 mismatched columns), 21 tables, 483 of the 755 `ADD_DROP` ops:**

| Table | ADD_DROP | Owning model | Confirmed live via |
|---|---|---|---|
| `payroll_impact_previews` | 40 | `PayrollImpactPreview` | checked by hand (see log) |
| `compliance_snapshots` | 35 | `ComplianceSnapshot` | grep: 1 service/router file |
| `ytd_payroll_ledgers` | 33 | `YTDPayrollLedger` | grep: 1 service/router file |
| `opening_balance_imports` | 29 | `OpeningBalanceImport` | grep: 1 service/router file |
| `what_if_simulations` | 28 | `WhatIfSimulation` | grep: 1 service/router file |
| `ctc_snapshots` | 27 | `CostToCompanySnapshot` | grep: 1 service/router file |
| `bank_reconciliations` | 27 | `BankReconciliation` | checked by hand (see log) |
| `support_tickets` | 26 | `SupportTicket` | grep: 1 service/router file |
| `upsell_opportunities` | 24 | `UpsellOpportunity` | grep: 1 service/router file |
| `payment_transactions` | 24 | `PaymentTransaction` | grep: 2 service/router files |
| `three_way_matches` | 22 | `ThreeWayMatch` | checked by hand (see log) |
| `ml_jobs` | 22 | `MLJob` | grep: 1 service/router file |
| `ml_models` | 21 | `MLModel` | grep: 1 service/router file |
| `ledger_entries` | 20 | `LedgerEntry` | checked by hand (see log) |
| `fixed_assets` | 20 | `FixedAsset` | grep: 5 service/router files |
| `risk_signals` | 19 | `RiskSignal` | grep: 1 service/router file |
| `expense_claims` | 17 | `ExpenseClaim` | grep: 3 service/router files |
| `ghost_worker_detections` | 16 | `GhostWorkerDetection` | grep: 1 service/router file |
| `payslip_explanations` | 15 | `PayslipExplanation` | grep: 1 service/router file |
| `intercompany_transactions` | 15 | `IntercompanyTransaction` | checked by hand — **confirmed crashing endpoint, see log** |
| `employee_variance_logs` | 15 | `EmployeeVarianceLog` | grep: 1 service/router file |

**Every single Tier 1 table is confirmed reachable from a real router or service — none are dead code.**
Only `IntercompanyTransaction` has been individually traced far enough to confirm an actual runtime
crash on every call (`POST /intercompany` — see `docs/REMEDIATION_LOG.md`); the other 20 are confirmed
*reachable* but not yet individually traced to confirm whether they crash on every use, only on some
code paths, or (less likely, given the pattern) happen to avoid the mismatched columns in their current
usage. **This is the first thing any remediation pass on Tier 1 should establish per table, before
choosing a fix direction** — per this roadmap's standing rule not to assume failure any more than
success.

**Tier 2 — Moderate (5–14 mismatched columns), 22 tables:** `wht_credit_notes`(14), `payslips`(14),
`recurring_journal_entries`(13), `depreciation_entries`(13), `purchase_order_items`(12),
`bank_accounts`(12), `bank_statements`(11), `bank_statement_transactions`(11), `approval_requests`(11),
`ticket_attachments`(10), `payroll_exceptions`(10), `approval_workflows`(10), `ticket_comments`(9),
`expense_claim_items`(9), `goods_received_note_items`(8), `approval_workflow_approvers`(8), `budgets`(7),
`account_balances`(7), `upsell_activities`(6), `sku_pricing`(6), `purchase_orders`(6),
`approval_decisions`(5).

**Tier 3 — Minor (1–4 mismatched columns), 23 tables:** likely single renamed/added/missing columns per
table, much closer in shape to what Finding 49 already fixes mechanically. Full list:
`legal_hold_notifications`(4), `fiscal_periods`(4), `budget_line_items`(4), `audit_logs`(4),
`risk_signal_comments`(3), `journal_entries`(3), `entity_group_members`(3), `accounting_dimensions`(3),
`payroll_runs`(2), `legal_holds`(2), `journal_entry_lines`(2), `gl_integration_logs`(2),
`entity_groups`(2), `usage_report_history`(1), `transaction_dimensions`(1), `payslip_items`(1),
`payroll_decision_logs`(1), `loan_repayments`(1), `goods_received_notes`(1), `exchange_rates`(1),
`employee_loans`(1), `discount_code_usages`(1), `chart_of_accounts`(1). Note `audit_logs` here is
**separate from, and additional to**, the already-known Finding 41 (`target_entity_type`/
`target_entity_id` never migrated) — this is 4 *different* mismatched columns, not yet individually
identified.

**43 tables show no `ADD_DROP` at all** — their differences are only `NULLABLE`/`TYPE`/`ENUM`/
`TIMESTAMP`/`INDEX_UQ`, i.e. milder drift or (for the `ENUM` cases) already-known Finding 1. These are
lower priority but not zero priority — `NULLABLE` and `TYPE` differences are still real, just less likely
to cause an outright crash on every use.

## Root cause (working hypothesis, not yet confirmed with the people who wrote this code)

Every Tier 1 and most Tier 2 tables belong to files that read like later, more ambitious rewrites of an
originally simpler migrated table: `payroll_advanced.py`, `advanced_accounting.py`,
`bank_reconciliation.py`, `risk_signal.py`, `support_ticket.py`, `upsell.py`, `ml_job.py`,
`fixed_asset.py`, `sku.py`. The most likely explanation, consistent with every case checked by hand, is
that these models were extended or rewritten to support a fuller feature set (opening/closing balances
instead of one ending balance, per-field change logs instead of simple before/after, tolerance and
override logic for 3-way matching, etc.) without ever running `alembic revision --autogenerate` to check
whether a real migration was needed — the same blind spot Finding 41 and Finding 49 both already
exploited, just recurring at a much larger scale. This is a process gap (no CI check ever compares
models to migrations), not a one-off mistake — see the Recommended Fix in
`docs/REMEDIATION_LOG.md`'s Phase 0 entry, which already proposed exactly this CI check before Finding
50 existed.

## What remediation requires (not yet decided — this is the decision point)

For each affected table, one of:

- **(A) Migrate the database to match the model.** Write a real Alembic migration adding/renaming/
  retyping columns so the live schema matches the model's fuller, apparently-intended shape. Preserves
  the feature richness already coded into routers/services (e.g. `IntercompanyTransaction`'s
  `transaction_date`/`currency`, `BankReconciliation`'s opening-balance tracking). Requires knowing
  whether these tables currently hold any real production rows under the *old* column names, since a
  rename needs a data-preserving migration, not just an additive one, wherever real data exists.
- **(B) Fix the model (and dependent router/service code) to match the database.** No production
  migration risk. Likely means removing fields the code currently references that don't actually exist
  anywhere in the database (e.g. `IntercompanyTransaction.currency`), which is a functional regression
  from what the code was clearly trying to do, not a neutral fix.
- **(C) Per-table judgment**, likely correlated with whether the table has any real rows in production
  today: empty/never-populated tables are low-risk either direction and (A) is usually preferable (it
  finishes what the code already intended); populated tables lean towards (B) unless a proper data
  migration is written for the rename.

**Decision made (2026-09-19): additive-only, no row-count dependency.** Row counts would only matter for
deciding whether it's *safe to drop or rename a column in place* — and this pass deliberately never does
that regardless of what the counts turn out to be, so the blocker is resolved by removing the need for
the number, not by obtaining it. Concretely, for every table in this document:

- Any column the **model** has that the **DB** lacks: add it via a normal additive Alembic migration
  (nullable, or nullable-with-backfill if the model requires `NOT NULL` — see below). Safe whether the
  table has 0 rows or a million; existing rows either get `NULL` (if nullable) or a computed backfill
  value (if not).
- Any column the **DB** has that the **model** lacks, where it's the same concept under an old name (the
  common case — e.g. `IntercompanyTransaction.from_entity_id` vs. DB's `source_entity_id`): add the new
  column, backfill it from the old column in the same migration (`UPDATE table SET new_col = old_col`),
  and **leave the old column in place** rather than dropping it in the same step. Dropping genuinely
  unused legacy columns is a separate, later cleanup pass (candidate for Phase 12), not this one — this
  keeps every step here reversible and safe under any row count.
- Any DB column with no plausible model equivalent at all: add it back onto the model as-is (catch the
  model up to reality) rather than removing it from the database.
- `NOT NULL` columns the model wants that don't exist in the DB yet get a computed backfill in the same
  migration (e.g. `IntercompanyTransaction.transaction_date` backfills from `created_at::date` for any
  existing rows) before the `NOT NULL` constraint is added, so the migration works unconditionally.

This is (A) from the options above, made safe by construction rather than by knowing the data in advance.
Executed per table, in the same individually-verified style as the rest of Finding 49/50 — see
`docs/REMEDIATION_LOG.md` for the running per-table log as this executes.

**Progress (updated as tables are fixed):** `intercompany_transactions`, `entity_groups`,
`approval_workflow_approvers`, `approval_workflows`, `ledger_entries`, `three_way_matches`,
`wht_credit_notes`, `approval_requests`, `approval_decisions`, `budgets`, `account_balances`,
`recurring_journal_entries`, `gl_integration_logs`, `journal_entries`, `journal_entry_lines`,
`chart_of_accounts`, `fiscal_periods`, `exchange_rates`, `bank_reconciliations`, `bank_accounts`,
`bank_statements`, `bank_statement_transactions`, `purchase_orders`, `purchase_order_items`,
`goods_received_notes`, `goods_received_note_items`, `fixed_assets`, `depreciation_entries`,
`expense_claims`, `expense_claim_items`, `support_tickets`, `ticket_comments`,
`ticket_attachments`, `compliance_snapshots`, `payroll_impact_previews`, `payroll_exceptions`,
`payroll_decision_logs`, `ytd_payroll_ledgers`, `opening_balance_imports`, `payslip_explanations`,
`employee_variance_logs`, `ctc_snapshots`, `what_if_simulations`, `ghost_worker_detections`,
`upsell_opportunities`, `upsell_activities`, `payment_transactions`, `ml_jobs`, `ml_models`,
`risk_signals`, `risk_signal_comments`, `payslips`, `sku_pricing`, `payroll_runs`,
`employee_loans`, `loan_repayments`, `payslip_items`, `legal_holds`, `legal_hold_notifications`,
`budget_line_items`, `audit_logs`, `accounting_dimensions`, `transaction_dimensions`,
`entity_group_members` — done, verified (check `docs/REMEDIATION_LOG.md` for current deploy status
of the most recent one). **All 66 tables in the original scope are now resolved.** (See "Status"
in `docs/REMEDIATION_LOG.md`'s latest entries for exactly what has and hasn't reached production
yet — a billing-account closure has blocked every deploy since `5cab0ec`.) `ledger_entries`,
`budgets`, and `account_balances` were fixed via
option (A) — migrating the database to match the model — rather than (B); see those log entries
for why. `recurring_journal_entries` is the first table found to be genuinely dead code (no real
call site anywhere), fixed via (B) for that reason.

## What this changes about the roadmap

Finding 49 and Finding 50 are not two separate defects — Finding 49's remaining 51-column, 29-table
scope (`docs/IMPLEMENTATION_ROADMAP.md` Phase 1 §1.5) turns out to be almost entirely a subset of Finding
50's Tier 1/Tier 2 tables, just discovered at a shallower depth of inspection first. **§1.5 as originally
written (mechanical FK-annotation fixes) should be considered superseded by this document for those
tables**, not run in parallel with it — running both would mean re-doing the same tables twice under two
different plans. `budget_periods.tenant_id` (Phase 0's one genuinely simple fix from this batch) is the
exception: already fixed and committed, unaffected by this.

This likely warrants its own dedicated roadmap phase — sized more like a full phase (66 tables) than a
single section — inserted based on the (A)/(B)/(C) decision above, once made.
