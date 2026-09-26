# Tekvwa Pro Audit — Production Remediation Implementation Roadmap

**Source of truth:** `docs/PRODUCTION_AUDIT_2026.md` (48 findings, Finding 1–48) and
`docs/AUDIT_CHECKLIST.md` (22-section coverage record). This document does not re-audit anything —
it converts what was already found into an ordered, gated, executable implementation plan.

**Status:** Not started. This is a planning document. No remediation work has begun as of the writing
of this roadmap. Update the status column in §9 (Traceability Table) as each section moves.

**How to read this document:** Work top to bottom. Each Phase has an Objective, a list of Findings it
closes, explicit Preconditions (what must already be true before starting), a set of Sections (the
actual units of work), and a Phase Completion Gate. Do not start a Phase whose Preconditions aren't
met. Do not skip a Section's gate because the code "looks right." Do not start the next Phase until
the current Phase's gate has actually passed.

---

## 0. Conventions Carried From the Audit

| Severity | Meaning | Implementation Priority |
|---|---|---|
| P0 Critical | Security vulnerability, data loss, production-breaking | Blocks launch — Phases 1-5 |
| P1 High | Major feature broken, serious authz/data issue | Blocks launch — Phases 1-6 |
| P2 Medium | Functional issue, tech debt, performance, inconsistency | Should fix before launch — Phases 7-13 |
| P3 Low | Minor cleanup, UX, non-critical optimization | Fix opportunistically — Phase 12-14 |

| Confidence (from audit) | What the roadmap does with it |
|---|---|
| Confirmed | Goes straight to an implementation section |
| Likely | Goes to an implementation section, but its first task is "reproduce/confirm," not "fix" |
| Potential Risk | Goes to a **verification-only** task first (§9.2). No code changes until confirmed. |
| Code Smell | Batched into a hygiene section (Phase 12), never sequenced ahead of a P0/P1 |
| Recommendation | Logged in the traceability table with no forced sequencing — do opportunistically |

**A "Potential Risk" is never silently promoted to "confirmed defect" in this roadmap.** Finding 15
(spoofable upload MIME check) is the one instance of this in the audit — see §9.2 for its
verification task. If verification confirms exploitability, only then does it get a normal
implementation section with its own gate.

**New implementation-status legend used throughout this document:**

| Status | Meaning |
|---|---|
| ⬜ Not Started | No work begun |
| 🟨 In Progress | Implementation underway, gate not yet attempted |
| 🟧 Blocked | Cannot proceed — precondition unmet or external dependency (see note) |
| 🟦 Testing | Implementation done, running through the Section Completion Gate |
| ✅ Complete | Gate passed in full, documented, deployed, verified |

---

## 1. Standard Section Completion Gate (SCG) — apply to every section below

Every section in every phase must pass this exact gate before being marked ✅. This is defined once
here and referenced by name ("Apply SCG") rather than repeated in full 60 times.

**1. Code**
- [ ] Implementation finished per the section's specific scope (no scope creep beyond what the section lists)
- [ ] No unintended changes outside the files listed in the section
- [ ] No new dead code introduced
- [ ] Linter/type-checker clean (`black`, `isort`, `flake8`, `mypy` — whatever the section touches)
- [ ] No unresolved runtime errors on a manual smoke pass

**2. Functional testing** (write or extend automated tests; do not rely on manual-only verification for anything that will run in production)
- [ ] Happy path
- [ ] Invalid input
- [ ] Missing/null input
- [ ] Error path (the thing that used to be broken, re-tested to confirm it's fixed)
- [ ] Boundary conditions relevant to this specific finding
- [ ] Permission/authorization behavior, if the section touches an authenticated or entity-scoped route
- [ ] Authentication behavior, if the section touches login/session/token logic

**3. Regression**
- [ ] Every other endpoint/service that shares the touched file, model, or table still passes its existing tests
- [ ] Shared components (middleware, dependencies, base classes) re-tested, not assumed safe
- [ ] Existing API response shape unchanged unless the section explicitly intends to change it (if it does, §8's frontend-contract check runs)

**4. Integration**
- [ ] Frontend → API → service → database → response traced end-to-end for at least one representative endpoint in this section, the same way the audit itself traced findings — not inferred from the diff
- [ ] Cross-service relationships this section touches (e.g., `AuditService`, `EntityService`, `BillingService`) re-verified, not assumed

**5. GitHub**
- [ ] Changes committed with a message that names the Finding number(s) closed
- [ ] Correct branch confirmed (never commit directly to `main` for anything beyond Phase 0 — see §2 branching strategy)
- [ ] Pushed
- [ ] Push confirmed (`git log origin/<branch>` or PR view matches local)

**6. Deployment**
- [ ] Deployed to the target environment for this stage (staging first — see §2)
- [ ] Application starts successfully (check Cloud Run revision logs)
- [ ] The specific endpoint/page this section fixed is manually exercised against the deployed instance
- [ ] No new errors in logs for at least one full request cycle of the affected path
- [ ] Smoke test suite (a small, fast subset covering login, dashboard load, one write op) passes

**7. Documentation**
- [ ] `docs/AUDIT_CHECKLIST.md` or this roadmap's traceability table (§9) updated to reflect the finding is closed, not just "worked on"
- [ ] Any of `docs/DATA_MODEL_ERD.md`, `docs/TECHNICAL_ARCHITECTURE.md`, `docs/GCP_DEPLOYMENT.md`, `docs/BILLING_RUNBOOK.md`, or a relevant `docs/*_DOCUMENTATION.md` updated if this section changed something they describe
- [ ] `docs/CHANGELOG.md` gets an entry

**Only after all seven groups are checked: Section Status = ✅ Complete.**

If any functional, regression, or integration test fails at any point: **STOP → INVESTIGATE →
FIX → RE-RUN THE FULL GATE FROM STEP 2.** Do not patch forward past a failing test into the next
section. Do not mark partial completion.

---

## 2. Standard Phase Completion Gate (PCG) — apply after every phase's sections are all ✅

Passing every section's SCG does **not** mean the phase is done. A phase is a claim about how a set
of sections behave *together*, which individual section testing cannot prove.

**1. Full phase regression pass** — run the entire automated test suite (not just this phase's new
tests), against a database built from the real Alembic migration chain (see Phase 1 — this is itself
a fix this roadmap makes, and every phase after Phase 1 depends on it being in place).

**2. Cross-section integration test** — for every pair of sections in the phase that touch a shared
service, table, or middleware, run at least one test that exercises both together, not each in
isolation.

**3. Cross-phase test** — for every dependency recorded in §3 (Cross-Phase Dependency Matrix) where
*this* phase is the dependent side, re-run the specific test named in that matrix row.

**4. Staging deployment verification** — deploy the full phase to staging (if not already there
section-by-section), run the smoke suite, and manually walk the highest-risk workflow this phase
touched end-to-end as a real user would.

**5. Production deployment** (only after staging verification passes) — deploy, verify via the same
smoke suite against the live Cloud Run revision, watch logs for 15-30 minutes of real or synthetic
traffic before considering the phase live.

**6. Documentation review** — re-read every doc touched by this phase's sections together, check for
contradictions between sections (e.g., one section's doc update assuming a default the next section
changed).

**7. Rollback rehearsal** — for any phase that touched the database schema (Phases 1, 2, 3), confirm
the down-migration actually runs cleanly against a copy of the pre-phase schema before calling the
phase done. Do not assume a rollback path exists just because Alembic generated one.

**Only after all seven pass: Phase Status = ✅ Complete.** Only then does the next phase's
Preconditions get checked.

### Branching strategy (referenced throughout)

- `main` — always deployable, always the last fully-gated phase.
- One feature branch per **phase**, e.g. `phase-1-entity-isolation`, `phase-2-audit-log-migration`.
- One commit per **section** on that branch (small, reviewable, each closing a specific finding).
- Phase branch merges to `main` only after the Phase Completion Gate passes on staging.
- Production deploy happens from `main` after merge, never from a feature branch directly.

---

## 3. Why This Roadmap Reorders the Audit's Suggested Remediation Sequence

The audit's own Deliverable K lists Finding 18 (cross-tenant IDOR) before Finding 41 (broken
audit-log write path). That ordering is correct for *risk severity* — Finding 18 is the single most
severe finding in the report. It is not correct for *implementation sequencing*, for one concrete
reason the audit itself documents:

> "Traced `app/routers/accounting.py::create_account`... A caller creating an account gets a 500 and
> the account does not exist — not 'the account exists but wasn't logged.'" (Finding 41's write-up,
> §6.3 of the audit)

Every write endpoint this roadmap needs to test as part of fixing Finding 18 (accounting.py,
budget.py, entities.py, year_end.py, report_export.py — all confirmed-vulnerable **write** operations)
calls `AuditService.log_action()` on the same shared session. Until Finding 41 is fixed, **every one
of those write endpoints 500s regardless of whether the entity-access fix is correct**, because the
audit-log call crashes first and takes the whole transaction down with it (Finding 44's commit-
coupling). Testing Finding 18's fix on write endpoints without fixing Finding 41 first would produce
false failures indistinguishable from a broken access-control fix — the Section Completion Gate's
"integration" step would be unable to tell the two apart.

**Therefore: Phase 1 of this roadmap is the audit's Finding 41 (+ Finding 44, its immediate structural
cause) and Finding 19 (the same class of model/migration drift, cheap to fix at the same time). Phase
2 is Finding 18.** Everything else follows the audit's severity ordering except where a similar
concrete testing dependency requires otherwise (documented inline where it happens).

---

## 4. Phase 0 — Baseline, Safety, and Implementation Control

**Objective:** Establish a known-good starting point and a safe way to make changes, before touching
any production functionality. No findings are "fixed" in this phase.

**Preconditions:** None — this is the starting point.

### 0.1 Repository baseline

- [ ] Confirm current branch is `main`, working tree is clean (`git status`)
- [ ] Record current commit hash in this document's changelog section
- [ ] Tag the current state: `git tag pre-remediation-baseline`
- [ ] Confirm the current build succeeds locally (`docker build --target production .`)
- [ ] Run the full existing test suite exactly as the audit did (clean venv from `requirements.txt`,
      real Alembic-migrated Postgres, not `Base.metadata.create_all()`) and record the exact number:
      834 collected / 773 passed / 19 failed / 42 errored / 1 skipped is the audit's baseline — confirm
      it still matches before starting, since drift between the audit and implementation start would
      itself need investigation.

### 0.2 Deployment baseline

- [ ] Confirm current Cloud Run revision (`gcloud run services describe proaudit-web --region
      africa-south1`) and record its revision ID
- [ ] Confirm current `alembic_version` head matches the migration files in the repo
- [ ] Confirm rollback method: which prior Cloud Run revision to route traffic back to, and that
      `gcloud run services update-traffic` access is available to whoever is deploying
- [ ] Snapshot the current Cloud SQL database (`gcloud sql backups create`) before Phase 1 touches
      anything — this is the actual safety net for the migration work in Phases 1-3

### 0.3 Testing foundation (groundwork only — the fix itself is sequenced later)

The audit's Finding 15.6 (`ci.yml`'s `pytest ... || true`) means CI cannot currently fail. Do **not**
remove `|| true` yet in Phase 0 — the audit is explicit that doing so before Findings 27–31 are fixed
"would immediately turn CI red on the very next push." Instead:

- [ ] Add a non-blocking CI annotation that reports the pass/fail counts visibly (e.g., a PR comment
      or job summary) without failing the build, so regressions are *visible* during Phases 1-8 even
      though the job can't yet gate on them
- [ ] Record this as a tracked, deliberate deferral — the actual `|| true` removal is Phase 9, Section
      9.4, after Findings 27-31 are closed

### 0.4 Documentation foundation

- [ ] Create `docs/REMEDIATION_LOG.md` — a running, dated log of every section completed, its commit
      hash, and its deployment verification result. This is separate from this roadmap (which is the
      plan) and from `docs/CHANGELOG.md` (which is user-facing) — it's the implementation team's own
      audit trail of *this remediation effort*, so a future audit can verify these fixes the same way
      this one verified the original bugs.
- [ ] Link `docs/REMEDIATION_LOG.md`, this roadmap, `docs/AUDIT_CHECKLIST.md`, and
      `docs/PRODUCTION_AUDIT_2026.md` from each other's headers so the chain of evidence stays
      navigable.

**Phase 0 has no PCG in the normal sense** (nothing was implemented to regress-test) — its exit
condition is simply that every checkbox above is checked and the baseline snapshot exists.

---

## 5. Phase 1 — Data-Layer Integrity Foundation

**Objective:** Fix the defects that would otherwise silently corrupt the test signal for every phase
that follows. Nothing here is user-facing; everything here is "make the ground stable enough to build
on."

**Findings closed:** 41 (P0), 44 (P2, bundled — see rationale below), 19 (P2).

**Preconditions:** Phase 0 complete. Database snapshot exists.

### 1.1 Section: Fix the `audit_logs` schema drift (Finding 41)

**Understand:** `AuditLog.target_entity_type`/`target_entity_id` (`app/models/audit_consolidated.py`,
lines 246-256) are declared on the model but no migration ever created them on the live table. Every
call to `AuditService.log_action()` fails with `UndefinedColumnError` at `db.flush()`.

**Plan:** One additive Alembic migration. No data transformation needed — these are new nullable
columns, not a change to existing data.

**Implement:**
- [ ] `alembic revision -m "add_target_entity_columns_to_audit_logs"`
- [ ] `op.add_column('audit_logs', sa.Column('target_entity_type', sa.String(100), nullable=True))`
- [ ] `op.add_column('audit_logs', sa.Column('target_entity_id', sa.String(100), nullable=True))`
- [ ] Add the matching `op.create_index` if `target_entity_type`/`target_entity_id` are expected to be
      queried by `get_audit_logs()` filters (the model declares `index=True` on both — match it)
- [ ] Write the `downgrade()` (`op.drop_column` x2, `op.drop_index` x2) and actually run it against a
      restored copy of the pre-migration schema to confirm it's not just Alembic-generated boilerplate

**Test (SCG §1.2):**
- [ ] Unit: construct an `AuditLog(...)` directly, `db.flush()`, assert no exception (this is the
      exact reproduction the audit used — re-run it as a permanent regression test, not a one-off)
- [ ] Integration: call `AuditService.log_action()` directly with representative arguments from 3
      different call sites (`accounting.py::create_account`, `auth.py::login`'s failed-login path,
      `vendors.py`'s vendor-creation path) — assert each succeeds and the row is queryable afterward
- [ ] Regression: run the 3 previously-passing-by-luck tests that exercise `log_action` indirectly
      (they passed before only because `tests/conftest.py` bypasses migrations — see §1.3 below — so
      re-running them against the *migrated* schema is itself a new check, not a formality)

**Deploy:** Apply this migration to staging Cloud SQL first, verify, then production. This is a
**schema-only, additive** deploy — no application code changes yet, so it can go out independently and
safely ahead of the rest of Phase 1.

**Document:** Update `docs/DATA_MODEL_ERD.md`'s `audit_logs` table definition. Note in
`docs/REMEDIATION_LOG.md` that this was verified against production directly (the audit could not do
this — see the audit's own note in §6 of `docs/AUDIT_CHECKLIST.md` about the blocked Cloud SQL proxy
check). **This section's deployment IS that verification** — confirm and record the column's absence
before the migration runs, and its presence after, as the actual proof the audit couldn't obtain.

### 1.2 Section: Fix the commit-ownership coupling (Finding 44) — bundled with 1.1, not deferred to Phase 12

**Understand:** The audit traced why Finding 41's failure destroyed the whole `create_account`
operation, not just the log entry: `AuditService.log_action()` calls `self.db.commit()` internally
(`audit_service.py:99`), on the same session as the caller's own uncommitted work. Fixing the missing
columns alone leaves this coupling in place — a future failure in `log_action()` (network blip,
constraint violation, anything) would still take down whatever the caller had already `flush()`-ed.

**Plan:** Adopt one convention: **services never call `commit()`, only `flush()`. The router (or a
shared FastAPI dependency that wraps the request in a transaction) commits exactly once per request.**
Apply it first to `AuditService.log_action()` specifically (highest blast radius, ~26 routers), not
the full 388-call-site retrofit — that full retrofit is explicitly out of scope for this phase (tracked
as its own item in Phase 12).

**Implement:**
- [ ] Remove `await self.db.commit()` from `AuditService.log_action()`; replace with `await
      self.db.flush()` only
- [ ] Audit the ~26 router call sites (`accounting.py`, `advanced_accounting.py`,
      `bank_reconciliation.py`, `auth.py`, `categories.py`, `bulk_operations.py`, `entities.py`,
      `customers.py`, `exports.py`, `fixed_assets.py`, `expense_claims.py`, `inventory.py`,
      `invoices.py`, `nrs.py`, `organization_users.py`, `organization_settings.py`,
      `payroll_advanced.py`, `receipts.py`, `payroll.py`, `sales.py`, `staff.py`,
      `self_assessment.py`, `transactions.py`, `tax_2026.py`, `tax.py`, `vendors.py`) — confirm each
      one already calls `db.commit()` itself after the audit-log call, or add it if missing
- [ ] Do not touch the other ~360 non-audit-log commit sites in this section — explicitly deferred

**Test (SCG):**
- [ ] Unit: mock a downstream failure after `log_action()`'s flush but before the router's commit;
      assert a rollback correctly undoes both the audit log row and the business write (proves they're
      now one atomic unit, which was the actual bug)
- [ ] Regression: re-run every test touched in 1.1

**Document:** Add a short "Transaction Ownership Convention" note to `docs/TECHNICAL_ARCHITECTURE.md`
stating the rule adopted here, so it's discoverable for whoever eventually does the full Phase 12
retrofit.

### 1.3 Section: Migrate the test database via Alembic instead of `Base.metadata.create_all()`

**Understand:** This is the audit's own explicit recommendation and the reason Finding 41 was
invisible to 834 existing tests. Fixing it here, in Phase 1, means every subsequent phase's testing is
against a schema that actually matches what a real deployment would have — closing the exact blind
spot that let Finding 41 exist undetected.

**Implement:**
- [ ] `tests/conftest.py` line 68: replace `await conn.run_sync(Base.metadata.create_all)` with a
      programmatic Alembic upgrade (`alembic.command.upgrade(alembic_cfg, "head")`) against the test
      database
- [ ] Keep `Base.metadata.drop_all` (line 75) for teardown, or switch to `alembic downgrade base` for
      full parity — confirm both approaches leave no orphaned objects between test runs
- [ ] This will likely surface *other* previously-invisible drift beyond Finding 41 — do not treat new
      failures here as this section's bug; triage each one as its own finding, log it in
      `docs/REMEDIATION_LOG.md`, and route it to the correct phase (a new enum drift goes to Phase 3, a
      new missing-column issue gets its own Phase 1 sub-section, etc.)

**Test:** The full 834-test suite, run against the now-migration-built schema, is itself the test.
Record the new baseline numbers (expect them to differ from the audit's original 773/19/42 — some of
those 19/42 were Findings 27/28/30/31, fixed in later phases, and some new ones may appear from
schema drift the audit didn't individually reproduce).

**Deploy:** This section is test-infrastructure only — no application or database changes ship to any
environment. "Deploy" for this section means merging to the phase branch and confirming CI (once
unblocked in Phase 9) runs against it correctly.

### 1.4 Section: Register `payroll_advanced.py` models (Finding 19)

**Understand:** 11 model classes in `app/models/payroll_advanced.py` never get imported by
`app/models/__init__.py`, so they only register with `Base.metadata` incidentally, when
`payroll_advanced_service.py` happens to be imported first. This is now more consequential than when
the audit found it, because §1.3 just switched the test database to building from `Base.metadata` via
Alembic — Alembic's migration files are independent of Python import order, so this specific fragility
doesn't affect §1.3 directly, but it remains a live footgun for `alembic revision --autogenerate` and
for any future test that imports models in a different order than production happens to.

**Implement:**
- [ ] Add the 11 classes (`ComplianceSnapshot`, `CTCSnapshot`, `EmployeeVarianceLog`,
      `GhostWorkerDetection`, `OpeningBalanceImport`, `PayrollDecisionLog`, `PayrollException`,
      `PayrollImpactPreview`, `PayslipExplanation`, `WhatIfSimulation`, `YTDPayrollLedger`) to
      `app/models/__init__.py`'s import list, matching the pattern every other model file already
      uses
- [ ] Confirm `alembic revision --autogenerate` on a scratch branch now produces an **empty** diff
      against the current schema (proving the models and the live tables were already in sync — this
      was a registration bug, not a schema bug, exactly as the audit concluded)

**Test:** Import `app.models` in a fresh Python process with a deliberately different import order than
production's; confirm all 11 classes are present on `Base.metadata.tables` regardless of order.

**Document:** Update `docs/DATA_MODEL_ERD.md` if `payroll_advanced.py`'s tables weren't already
represented there.

### 1.5 Section: Finding 49 (new — discovered during Phase 0's baseline run, not one of the audit's original 48) — reconcile every real DB foreign-key constraint the ORM doesn't know about

**⚠️ SUPERSEDED for most of this section's scope — see Finding 50, `docs/FINDING_50_SCOPE.md`, before
doing any further work here.** While starting the mechanical per-table fix this section describes, the
"missing column" mismatches turned out for most tables not to be isolated oversights but symptoms of
models whose entire column set diverges from their migration (renamed columns, extra model-only fields,
extra DB-only fields, sometimes a fundamentally different concept under the same table name — e.g.
`IntercompanyTransaction`, confirmed to crash `POST /intercompany` on every call). This is now its own
finding (50), schema-wide (66 tables, not 29), requiring a product decision (migrate the DB to match the
models vs. fix the models/code to match the DB, per table) before any fix is written — see that
document's "What remediation requires" section. **Only `budget_periods.tenant_id` from this section's
original 29-table list was confirmed genuinely simple and is done** (commit `7a4740a`). Do not run this
section's original per-table plan below on the other 28 tables until Finding 50's decision is made —
28 of them are Finding-50-shaped, not simple FK-annotation gaps.

**Original **Understand** (kept for history, superseded above):** Phase 0's baseline test run surfaced a
new, systemic defect: a permanent `information_schema`-vs-`Base.metadata` diagnostic script found **93
real FK constraints in a fully migrated database with no matching declaration on any SQLAlchemy
model**, across three root causes (table never registered — Finding 19, already covered by §1.4; column
entirely missing from the model; column present but its `ForeignKey()` never declared). Full
investigation, the exact list of affected columns, a documented false-start (a naive fix to the shared
`AuditMixin` that made things worse before being caught and reverted), and the fix for 57 of the 93 are
recorded in full in `docs/REMEDIATION_LOG.md`'s Phase 0 entry — this section was meant to be the
remaining 51, until 28 of the 29 tables involved turned out to need Finding 50's decision first.

**This section is now a precondition for §1.3** (switching `tests/conftest.py` to build its schema
via Alembic): with 51 mismatches still spread across 29 tables, `Base.metadata.create_all()`/
`drop_all()` will continue to fail unpredictably depending on which tables a given test touches. §1.3
should not be considered safe to ship until this section is ✅.

**Implement, per table — this is 29 individually-verified edits, not a bulk find-and-replace:**
- [ ] For each of the 29 tables listed in `docs/REMEDIATION_LOG.md`'s Finding 49 entry: read the exact
      migration that added the column (type, nullable, default, `ondelete` behavior), add the matching
      `Mapped[...] = mapped_column(...)` declaration to the corresponding model with an explicit
      `ForeignKey(...)` — do not guess the type from the column name; confirm it from the migration
      every time, the same standard already applied to the 57 fixed in Phase 0
- [ ] For any column referencing a table that is itself not yet in `Base.metadata` (double-check none
      remain after §1.4 — the drift script will confirm this directly), fix the registration gap first
- [ ] Watch specifically for the two secondary-bug patterns Phase 0 already found once each: a
      migration-created constraint with a Postgres-default name that doesn't match this codebase's
      configured `naming_convention` (needs an explicit `name=`), and a table gaining a second FK to
      the same target table (needs `foreign_keys=` added to any existing `relationship()` between them)
- [ ] Promote the scratch diagnostic script into `scripts/check_fk_drift.py` as part of this section,
      not as an afterthought — it's what makes every one of these 29 edits verifiable rather than
      hopeful

**Test, per table:**
- [ ] Round-trip: create a row with the new column set to a real referenced ID, commit, re-fetch,
      assert it persists
- [ ] Constraint enforcement: attempt to set the column to a non-existent referenced ID, assert the
      database (not just application-level validation) rejects it
- [ ] Re-run `scripts/check_fk_drift.py` after each batch of tables — confirm the remaining-mismatch
      count only ever decreases, never regresses (this would have caught the `AuditMixin` false-start
      immediately, before it reached a full test-suite run)

**Test, for the whole section:** re-run the full test suite against a real `alembic upgrade head`
database (not yet via `conftest.py` — §1.3 hasn't shipped until this section is done) and confirm the
`DependentObjectsStillExistError`/`UndefinedObjectError`/`AmbiguousForeignKeysError` failure family is
completely gone, leaving only already-catalogued failures (Finding 1's enum casing, Findings 27/28/30/31,
etc.) — each routed to its own phase, not re-investigated here.

**Deploy:** Same as §1.1 — purely additive at the ORM layer for the 51 columns whose constraints
already exist in production (confirmed via the same `alembic revision --autogenerate` no-op check
used for the first 57); no migration required for those. Any table where the *column itself* turns
out to be missing in production (not just unmodeled) is a different, more serious situation — confirm
this isn't the case for any of the 29 before treating this section as ORM-only.

### Phase 1 Completion Gate specifics

Beyond the standard PCG: explicitly confirm that the "15-table gap" the audit opened as Open Question
1.1a in its own §1 is fully closed — the audit's own §6 already resolved this (11 of the gap explained
by Finding 19's registration issue; the audit states "zero orphaned database tables... the initial
15-table discrepancy was fully resolved and explained, not left open"). This phase's job is only to
apply the mechanical fix (§1.4) to the *cause* the audit already diagnosed — do not reopen the
investigation, and do not accept a different table count without first checking whether Finding 19's
fix plus the other resolved sub-gaps still add up. If they don't, that is itself a new finding, not a
sign this phase's work is wrong.

---

## 6. Phase 2 — Multi-Tenant Security & Entity-Access Isolation

**Objective:** Close every confirmed cross-tenant IDOR path. This is the single highest-severity
phase in the roadmap.

**Findings closed:** 18 (P0 — 164 confirmed endpoints across 17 files), 36 (P2, bundled in — see
rationale).

**Preconditions:** Phase 1 complete (write endpoints must be testable without a confounding audit-log
crash before this phase's integration tests can distinguish "access check works" from "everything
500s regardless").

### 2.1 Section: Build one centralized entity-access-check mechanism

**Understand:** The audit found the *correct* pattern already exists and works correctly in this same
codebase (`transactions.py::list_transactions` calling `EntityService.get_entity_by_id(entity_id,
current_user)`), alongside three broken variants: no check at all (120 endpoints), a fake safety net
that only checks on the fallback path (`resolve_entity_id`, 20 endpoints in `year_end.py` +
`report_export.py`), and a check that's additive instead of restrictive
(`report_template.py`'s `organization_id` OR-condition, 4 endpoints).

**Plan:** Rather than patch 164 call sites independently with slightly different hand-rolled checks
(which is how the codebase got into this state in the first place — see Finding 18's "additive, not
restrictive" and "# Verify entity access... doesn't" sub-patterns as evidence that ad hoc checks drift
from correct over time), build **one** dependency:

```python
async def require_entity_access(
    entity_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> BusinessEntity:
    entity = await EntityService(db).get_entity_by_id(entity_id, current_user)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found or access denied")
    return entity
```

...and migrate every one of the 164 confirmed-vulnerable endpoints to use `Depends(require_entity_access)`
instead of a raw `entity_id: uuid.UUID` path parameter. This makes the fix *mechanically checkable*
(a route with a raw `entity_id` param and no `require_entity_access` dependency is, by definition,
unfixed) rather than relying on each of 164 hand-edits being individually correct.

**Implement — organized by the audit's own file groupings, each its own commit within this section:**
- [x] `accounting.py` — 24 read endpoints (already correctly-shaped in the audit's original sweep) + 10
      write endpoints (`create_account`, `update_account`, `initialize_chart_of_accounts`,
      `create_fiscal_year`, `create_journal_entry`, `post_journal_entry`, `reverse_journal_entry`,
      `post_to_general_ledger`, `close_fiscal_period`, `sync_gl_from_source_systems`) — 34 total.
      **Done 2026-09-26** (commit pending): all 34 endpoints given `Depends(require_entity_access)`
      via the new centralized dependency in `app/dependencies.py`; verified by
      `tests/test_entity_access_isolation.py` — 3 unit tests on `require_entity_access` itself, an
      AST-based structural sweep (`TestEntityAccessDependencyWiring`) confirming zero unmigrated
      `entity_id` params remain in the file, and 4 real HTTP-level tests
      (`TestAccountingRouterEndToEnd`) proving a foreign-org `entity_id` is rejected with 404 on both
      a read and a write endpoint, before any write occurs.
- [x] `audit.py` — 17 endpoints. **Done 2026-09-26.** Notable variant: this file declares
      `entity_id: uuid.UUID` as a bare path parameter (no explicit `Path(...)`) since its prefix is
      set externally via `main.py`'s `include_router(..., prefix="/api/v1/entities")` rather than on
      the router itself — confirmed via a one-off smoke test that FastAPI's dependency resolution
      still threads the same `entity_id` into `require_entity_access` correctly regardless of which
      style declares it. The AST structural check in `tests/test_entity_access_isolation.py` was
      generalized to detect both styles (any function with an `entity_id` parameter, not just ones
      defaulted via `Path(...)`), verified against `budget.py` (still correctly flags 22 unmigrated
      functions) before and after the change.
- [x] `budget.py` — 18 read + 5 write (`create_budget`, `submit_budget_for_approval`,
      `process_budget_approval_decision`, `create_budget_revision`, `approve_budget`) — 23 total.
      **Done 2026-09-26.** All 23 `entity_id: UUID = Path(...)` params given
      `Depends(require_entity_access)`. Note (out of Phase 2 scope, not fixed): spotted a pre-existing
      bug in `get_budget_variance_ytd` — it calls `service.get_budget(entity_id, budget_id)` but
      every other call site in this file uses `service.get_budget(budget_id, include_line_items)`,
      i.e. `entity_id` is passed where `budget_id` is expected. Not an access-control issue and not
      touched here; flag for Phase 3 or a dedicated bugfix.
- [x] `consolidation.py` — 2 + 1 write (`recycle_cta_on_disposal`, which additionally needs its
      `group_id`-to-organization check added, not just `entity_id`) — 3 total. **Done 2026-09-26, with
      a scope expansion found and fixed in the same pass:** while adding the `group_id`-to-organization
      check the roadmap calls out for `recycle_cta_on_disposal`, discovered `ConsolidationService.
      get_entity_group(group_id)` has **no organization_id filter at all** — every one of this file's
      17 `group_id`-keyed endpoints (not just the 3 counted here) let any authenticated user from any
      organization view or mutate any other organization's consolidated financial statements just by
      knowing/guessing a `group_id` UUID. This is the same root-cause bug as Finding 18, keyed on
      `group_id` instead of `entity_id`, and wasn't in the original audit's per-file tally for this
      file. Built a new `require_group_access` dependency (`app/dependencies.py`, mirroring
      `require_entity_access`) and applied it to all 17 endpoints, not just the 3 originally scoped;
      also added `require_entity_access` (or an inline equivalent, for `get_translation_history`'s
      *optional* `entity_id` filter, which can't take a hard `Depends()`) to the 3 `entity_id`-based
      endpoints this section originally called out. See docs/REMEDIATION_LOG.md's Phase 2 entry for
      `consolidation.py` for the full writeup. Verified via new `TestRequireGroupAccess` unit tests, the
      AST structural sweep (generalized to also check `group_id` params and to recognize
      `get_current_entity_id` as a second valid `entity_id`-guarding dependency), and the existing
      43-test `test_consolidation.py` regression suite passing unchanged.
- [x] `dashboard.py` — 1 write (`mark_all_alerts_read`) — the other 20 flagged in the audit's sweep are
      confirmed safe, do not touch them, re-verify they still pass their existing safety pattern after
      this phase's changes land nearby. **Done 2026-09-26.** `entity_id` here is an *optional* filter
      (like consolidation.py's `get_translation_history`), so used an inline
      `await require_entity_access(...)` call rather than a hard `Depends()`. Confirmed the other 20
      endpoints' existing pattern (`DashboardService._get_entity_if_accessible`, which checks
      `user.entity_access` directly) is genuinely organization-scoped and untouched. New
      `tests/test_dashboard_entity_access.py` (3 tests) covers the fixed endpoint; not added to the
      AST sweep's `MIGRATED_ROUTER_FILES` since that list's contract is "whole file clean" and this
      file's other 20 endpoints intentionally use a different pattern the sweep doesn't recognize.
- [ ] `fixed_assets.py` — 4
- [ ] `forensic_audit.py` — 15 + 1 write (`sync_journal_entries_to_ledger`) — 16 total
- [ ] `fx.py` — 10, including the 2 confirmed writes
- [ ] `ml_ai.py` — 1 (dashboard) + 2 confirmed vulnerable (`forecast_cash_flow`, `predict_growth` —
      remove their misleading `# Verify entity access` comments along with the fix, since the comment
      itself was evidence of the bug) — 3 total
- [ ] `report_template.py` — 2 + 4 confirmed (`list_templates`, `create_template`,
      `get_default_template`, `clone_template`) — **for this file specifically, do not just add
      `require_entity_access`; also fix the underlying service method's `OR organization_id =
      :organization_id` pattern in `ReportTemplateService` to `AND`, since the additive-not-restrictive
      bug lives in the service, not just the router** — 6 total
- [ ] `reports.py` — 21
- [ ] `tax_2026.py` — 4
- [ ] `year_end.py` — 12 (**delete `resolve_entity_id` entirely** — it is a confirmed fake safety net,
      not a helper worth keeping in any form)
- [ ] `report_export.py` — 8 (same `resolve_entity_id` deletion)
- [ ] `entities.py` — 1 (`restore_entity` — add an organization-match check, not just a role check)

That is 34+17+23+3+1+4+16+10+3+6+21+4+12+8+1 = **164**, matching the audit's final confirmed count
exactly. Track each file as its own commit so a review can verify the count lines up file-by-file
against the audit's own table in §3.3.

**Test (SCG, applied per file, then as one parameterized suite across all 164):**
- [ ] Build a single parameterized pytest fixture: two fully-seeded organizations (Org A, Org B), each
      with their own entity, user, and representative data (an account, a journal entry, a budget, an
      invoice, a fiscal year). For every one of the 164 endpoints: call it as an Org A user with Org
      B's `entity_id` and assert 403/404; call it as an Org A user with Org A's own `entity_id` and
      assert success. This single suite is the regression test that prevents this exact class of bug
      from reappearing — the audit explicitly recommended building it ("Recommend one parameterized
      test that hits every entity-scoped route with a foreign entity ID and asserts rejection").
- [ ] Additionally and specifically for the 4 report_template.py endpoints: assert that an Org A user
      requesting Org B's `entity_id` gets rejected **even when** `organization_id` happens to also
      match something valid — proving the OR-to-AND service fix, not just the router-level dependency,
      actually closed the gap.
- [ ] For `year_end.py`/`report_export.py`: assert `resolve_entity_id` no longer exists in the codebase
      at all (a grep-based test, not just a behavioral one) so it can't be silently reintroduced by a
      future merge.

**Regression:** Every endpoint in the "24 confirmed safe" bucket from the audit's §3.3 (`dashboard.py`'s
4, `notifications.py`'s 2, `reports.py`'s 1, `auth.py`'s 1, plus `views.py::set_entity`'s already-safe
pattern) must be re-run and must still pass — this phase must not accidentally break the patterns that
were already correct.

**Deploy:** This phase is large enough to warrant a staged rollout even within "staging" — deploy
file-group by file-group (matching the commit structure above) to staging, running the parameterized
suite after each group, before moving to the next. Do not batch all 17 files into one staging deploy
where a single failure is hard to isolate.

**Document:** Update `docs/DATA_MODEL_ERD.md`/`docs/TECHNICAL_ARCHITECTURE.md` with the new
`require_entity_access` dependency as the documented standard pattern for any future entity-scoped
route. Add a section to `CONTRIBUTING.md` (or wherever developer-facing conventions live) stating this
is now mandatory, not optional, for any endpoint taking an `entity_id`.

### 2.2 Section: Add the missing index on `UserEntityAccess` (Finding 36) — bundled here, not deferred to Phase 11

**Understand:** `require_entity_access` (§2.1) is about to become the single most frequently-executed
query path in the entire application — every one of the 164 migrated endpoints, plus every endpoint
already using the correct pattern, hits `UserEntityAccess` on every call. The audit found this table
has no index on `user_id` or `entity_id` and no uniqueness constraint on the pair. Shipping the
centralized dependency in §2.1 without this index means Phase 2 makes the exact performance problem
the audit warned about *worse*, not just unaddressed — a pattern going from "used inconsistently" to
"used on every single entity-scoped request" is precisely when a missing index starts to matter.

**Implement:**
- [ ] Migration: `op.create_index('ix_user_entity_access_user_entity', 'user_entity_access', ['user_id', 'entity_id'])`
- [ ] Migration: `op.create_unique_constraint('uq_user_entity_access_user_entity', 'user_entity_access', ['user_id', 'entity_id'])`
      — **before adding this, run a one-time data-integrity query for existing duplicate
      `(user_id, entity_id)` rows in production; if any exist, resolve them (keep the most permissive
      `can_write`/`can_delete` combination, per a product decision, not a unilateral engineering
      choice) before the constraint migration can succeed** — this is a real pre-migration data-cleanup
      step, not optional boilerplate
- [ ] Same index treatment for `AccountBalance.entity_id`

**Test:** `EXPLAIN ANALYZE` the exact query `require_entity_access` issues, before and after the index,
against a seeded table of a realistic size (10,000+ rows) — confirm the plan switches from a sequential
scan to an index scan.

### Phase 2 Completion Gate specifics

Beyond the standard PCG: re-run the audit's own AST-based sweep script (or an equivalent) that
originally found the 188 candidate endpoints, against the post-fix codebase, and confirm it now
returns zero unresolved candidates — the same proof standard the audit itself used to declare Finding
18 "final."

---

## 7. Phase 3 — Enum and Data-Model Normalization

**Objective:** Close Finding 1 (and its sub-findings 1b, 1c) and Finding 2, without introducing a new
data-integrity incident in the process — this phase touches live production data values, not just
schema.

**Findings closed:** 1 (P1 — 30 confirmed + 5 likely columns), 1b (divergent value sets), 1c
(`journalentrytype` mixed casing), 2 (P2 — type-name mismatches, 33 further columns at "Likely"
confidence).

**Preconditions:** Phase 1 and 2 complete. This phase is sequenced after multi-tenant security
specifically because several of the confirmed-broken enum columns live on tables Phase 2 just added
access checks to (`fixed_assets.status`, `bank_reconciliations.status`, `budgets.period_type`) — fixing
enum serialization on those tables before their access control was correct would have made testing
Phase 2 harder to reason about (a 403 and an enum-serialization 500 look different, but compounding
unrelated bug classes in the same test run is exactly the kind of confound Phase 1's reasoning already
warned against).

### 3.1 Section: Mechanical `values_callable` fix (30 confirmed columns)

**Understand:** These 30 columns' Python enums and live Postgres types have the *same* value sets, just
different casing. This is the safe, purely mechanical part of Finding 1 — the fix already proven
correct on 3 reference columns earlier in this project (`platform_role`, `organization_type`,
`verification_status`).

**Implement, one commit per table to keep blast radius reviewable:**
- [ ] For each of the 30 columns listed in the audit's §1.2 table, add
      `values_callable=lambda enum_cls: [e.value for e in enum_cls]` to the `SQLEnum(...)` declaration
- [ ] Do **not** touch the 5 "Likely" columns in this section — they have a second bug (type-name
      mismatch, Finding 2) that must be resolved first, see §3.4

**Test:**
- [ ] For each of the 30 columns: write (or extend an existing) round-trip test — create a row setting
      that column to each of its enum's members, commit, re-fetch, assert the value matches. This is
      the exact failure mode the audit found (`invalid input value for enum`), so the test must
      actually hit the database, not mock it.
- [ ] Add a permanent CI check (this is the audit's own Recommendation 4 for Finding 1): a script that
      loads `Base.metadata`, resolves every `SQLEnum` column's Postgres type name and the values
      SQLAlchemy would send, and diffs that against a live `pg_enum`/`pg_type` query — fail CI if any
      column is out of sync. This check is what makes Finding 1's *class* of bug structurally
      impossible to reintroduce, not just this instance of it.

**Deploy:** Purely additive at the ORM layer (`values_callable` doesn't change the database, only how
SQLAlchemy talks to it) — safe to deploy without a preceding data migration.

### 3.2 Section: Reconcile divergent value sets (Finding 1b — 4 columns, needs a product decision)

**Understand:** `invoices.buyer_status` (missing `AUTO_ACCEPTED` in the DB entirely),
`bank_reconciliations.status` (DB has `PENDING_REVIEW`/`REJECTED` the model doesn't), `unmatched_items.item_type`,
and `bank_charge_rules.detection_method` have **different value sets**, not just different casing. This
is not a mechanical fix — it requires deciding which value set is correct.

**Plan — this section starts with a decision meeting, not code:**
- [ ] For each of the 4 columns, present the product/business owner with: what the model currently
      allows, what the database currently allows, and which existing rows (if any) use a value that
      would become invalid under either resolution
- [ ] Get an explicit decision recorded in `docs/REMEDIATION_LOG.md` for each of the 4 (e.g.,
      "`AUTO_ACCEPTED` is a real, needed status — add it to the DB type" vs. "the model's
      `AUTO_ACCEPTED` was speculative and never actually used — remove it from the model")

**Implement (only after the decision is recorded):**
- [ ] For "add to DB": `ALTER TYPE buyerstatus ADD VALUE 'auto_accepted'` in a migration, then apply
      §3.1's `values_callable` fix to the column
- [ ] For "remove from model": delete the enum member, confirm no existing code path can ever attempt
      to set it (grep for the member name across `app/`), then apply §3.1

**Test:** Same round-trip test pattern as §3.1, plus an explicit test asserting the *removed or added*
value behaves as decided (e.g., if `AUTO_ACCEPTED` was kept, a test that actually exercises whatever
business logic sets that status).

### 3.3 Section: Normalize `journalentrytype`'s mixed casing (Finding 1c)

**Understand:** 17 of 20 Postgres enum values are uppercase, 3 are lowercase (added by a later
migration for FX revaluation entries). No `values_callable` fix can serve both casings from one Python
enum.

**Plan:** Standardize on uppercase (matching the majority and the original migration), migrate the 3
lowercase values and any existing rows using them.

**Implement:**
- [ ] Migration: `ALTER TYPE journalentrytype ADD VALUE 'FX_REVALUATION'`,
      `'FX_REALIZED_GAIN_LOSS'`, `'FX_UNREALIZED_GAIN_LOSS'` (uppercase additions)
- [ ] Data migration: `UPDATE journal_entries SET entry_type = 'FX_REVALUATION' WHERE entry_type =
      'fx_revaluation'` (and the other two) — **run this against a production data snapshot first and
      count affected rows before running it live**, since this touches existing financial records
- [ ] Migration: drop the 3 lowercase values from the type once no rows reference them (Postgres
      requires no rows use a value before it can be removed, or requires a full type rebuild — plan for
      whichever your Postgres version needs)
- [ ] Update the Python enum to only declare uppercase members
- [ ] Apply §3.1's `values_callable` fix

**Test:** Assert `SELECT DISTINCT entry_type FROM journal_entries` returns only uppercase values after
migration; assert creating a new FX-revaluation journal entry through the application writes the
uppercase value.

### 3.4 Section: Resolve Finding 2's type-name mismatches (5 "Likely" columns from §3.1, plus 33 further candidates)

**Understand:** These columns' SQLAlchemy-computed type name doesn't match the migration's actual type
name. The audit flagged this as **Likely**, not individually confirmed for all 33 — this section's
first task for each column is confirmation, per this roadmap's own rule about not promoting
Likely/Potential findings without verification.

**Implement, per column:**
- [ ] For the 5 already-identified (`accounting_dimensions.dimension_type`, `three_way_matches.status`,
      `wht_credit_notes.status`, `approval_requests.status`, `budgets.period_type`): confirm the real
      DB type name via `information_schema`, add an explicit `name=` argument to `SQLEnum(...)` matching
      it, then apply §3.1
- [ ] For the further 33 candidates (VARCHAR columns with no real DB enum constraint at all —
      `support_tickets.status`, `ml_jobs.status`, `risk_signals.severity`, `expense_claims.status`,
      `audit_runs.status`, `legal_holds.status`, `upsell_opportunities.status`, and the remainder not
      individually named in the audit): **write a verification script first** — for each column, check
      whether any other code path reads it via raw SQL or a different service expecting lowercase
      values. Only columns where a real read-path mismatch is confirmed get a code fix in this section;
      columns where nothing currently reads the mismatched value get logged as a Code Smell in Phase 12
      instead of an active bug fix here, per this roadmap's rule against promoting unconfirmed findings.

**Test:** For each confirmed-mismatched column, the specific cross-read failure the verification script
found, turned into a regression test (e.g., "a raw-SQL report query filtering on lowercase 'active'
now correctly matches rows written by the ORM with `values_callable` applied").

### Phase 3 Completion Gate specifics

Beyond the standard PCG: re-run the CI enum-compatibility check built in §3.1 against the fully
migrated schema and confirm zero mismatches remain across **all** `SQLEnum` columns in the codebase,
not just the ones explicitly named in the audit — this check's value is in catching anything the
audit's manual/scripted sweep might have missed.

---

## 8. Phase 4 — Core Application-Breaking Defects

**Objective:** Restore the basic write operations that currently cannot succeed at all. These are
independent of each other and of the security/data work in Phases 1-3, but are sequenced after them
because their own tests (especially Finding 27's, which creates a transaction and therefore triggers
audit logging and entity-access checks) depend on Phases 1-2 being correct to get a clean signal.

**Findings closed:** 27 (P0), 22 (P1), 28 (P0).

### 4.1 Section: Fix transaction creation (Finding 27)

**Understand:** `app/routers/transactions.py` defines its own stale local `TransactionCreateRequest`
(no `currency` field) that shadows the complete schema in `app/schemas/transaction.py`, which is
imported by zero files. `create_transaction()` unconditionally reads `request.currency`, crashing
every call.

**Plan:** Delete the router's local class; import and use the complete schema; reconcile the one known
field-name difference (`transaction_date` vs `date`).

**Implement:**
- [ ] Remove `class TransactionCreateRequest` from `app/routers/transactions.py` (lines 50-60)
- [ ] `from app.schemas.transaction import TransactionCreateRequest`
- [ ] Audit every field the router's handler reads (`transaction_type`, `transaction_date`, `amount`,
      `vat_amount`, `description`, `reference`, `category_id`, `vendor_id`, `receipt_url`, `currency`,
      `exchange_rate`, `exchange_rate_source`) against the imported schema's actual field names; fix
      the `transaction_date`/`date` mismatch by whichever direction is correct for the rest of the
      codebase's convention (check `Transaction` the model, not just the schema, to decide)
- [ ] Confirm `app/schemas/transaction.py` is now imported by at least one file (this one) — it's no
      longer dead code, which the audit will have flagged; that's expected and correct here

**Test (SCG):**
- [ ] The exact reproduction: `POST /{entity_id}/transactions` with a complete, valid body — assert
      201, not 500
- [ ] With `currency` omitted (should default to NGN per the schema) — assert success
- [ ] With `currency="USD"` and a valid `exchange_rate` — assert the FX service path is invoked (per
      the router's own `if request.currency and request.currency != "NGN":` branch) and the created
      transaction's stored amounts reflect the conversion
- [ ] Regression: `tests/test_api.py::TestTransactionsAPI::test_create_transaction` (the test that
      originally caught this) must now pass; re-run the full `test_api.py` file

### 4.2 Section: Fix invoice line-item update (Finding 22)

**Understand:** `InvoiceLineItem` has no `vat_rate` column. The router sets it as a transient
(non-persisted) attribute only when the request provides it, then unconditionally reads it back to
recompute `vat_amount` — crashing whenever a caller updates quantity/price without also resending
`vat_rate`.

**Plan:** Add the missing column (this is a real, missing piece of the data model, not just a router
bug — the audit is explicit that VAT-rate reconstructability is a compliance requirement for this
product).

**Implement:**
- [ ] Migration: `op.add_column('invoice_line_items', sa.Column('vat_rate', sa.Numeric(5,2),
      nullable=True))` — nullable initially, so existing rows aren't broken
- [ ] Backfill: for existing line items, derive `vat_rate` from `vat_amount / subtotal * 100` where
      both are non-zero, else leave null and fall back to the invoice-level default at read time
- [ ] Add `vat_rate` to the `InvoiceLineItem` model
- [ ] Fix `update_line_item()`: when `request.vat_rate is not None`, set and persist it normally; when
      it's `None`, fall back to `line_item.vat_rate` (the persisted value from last time) or the
      invoice-level `vat_rate` if this is the line item's first-ever rate — never read an attribute
      that was never set

**Test:**
- [ ] Update only `quantity` (omit `vat_rate`) on a line item that already has a persisted rate —
      assert success and that the rate used matches the previously-persisted one
- [ ] Update only `quantity` on a line item that has **never** had a rate set — assert it falls back to
      the invoice-level rate rather than crashing
- [ ] Update `vat_rate` explicitly — assert it persists and survives a re-fetch (closing the original
      "value silently lost" half of the finding, not just the crash)

### 4.3 Section: Fix the naive/aware datetime comparison (Finding 28)

**Understand:** `TenantSKU.trial_ends_at` is timezone-aware; `billing_service.py` and
`TenantSKU.is_trial` compare it against naive `datetime.utcnow()`/`datetime.now()`, raising `TypeError`
for every organization currently on a trial.

**Implement:**
- [ ] `app/services/billing_service.py`: replace every `datetime.utcnow()` compared against
      `trial_ends_at` with `datetime.now(timezone.utc)`
- [ ] `app/models/sku.py::TenantSKU.is_trial`: same fix
- [ ] Grep the rest of `billing_service.py` and `app/models/sku.py` for any other
      `datetime.utcnow()`/`datetime.now()` compared against a `DateTime(timezone=True)` column — the
      audit flagged this as worth a dedicated sweep before considering the bug class closed, not just
      the two known call sites

**Test:**
- [ ] `check_subscription_access()` called for an organization with `trial_ends_at` in the future —
      assert no exception, correct `has_access`/`days_remaining`
- [ ] `TenantSKU.is_trial` property accessed the same way — assert no exception
- [ ] Regression: `test_trial_lifecycle.py`'s full suite (9 failures + 2 errors in the audit's baseline
      traced to this exact bug) — all must pass now
- [ ] The middleware fail-open path (`sku_middleware.py::_load_subscription_status`) — assert it no
      longer needs its fail-open branch to be exercised for a valid trial org (i.e., confirm
      `subscription_status` is now something other than `"unknown"` for a trial org, proving
      enforcement is actually active again, not just that the crash is gone)

### Phase 4 Completion Gate specifics

Run the audit's own `test_trial_lifecycle.py` and `test_api.py::TestTransactionsAPI` results
side-by-side against the pre-fix baseline recorded in Phase 0 — confirm the specific failures the audit
named are gone and no new failures appeared in the same files.

---

## 9. Phase 5 — Billing, Tax & Payroll Business-Logic Correctness

**Objective:** Close every confirmed defect where the application computes or enforces the wrong
number or the wrong billing outcome. Grouped together because all four share a theme (money
calculations and money-adjacent state machines) and because Finding 40's fix touches the same
`TenantSKU` model Finding 28 just changed in Phase 4.

**Findings closed:** 11 (P0), 35 (P1), 39 (P1), 40 (P1).

**Preconditions:** Phase 4 complete (Finding 28's datetime fix must land before Finding 40's dunning
work, since both touch `TenantSKU`/billing_service.py state transitions and testing them independently
first avoids compounding two billing-state bugs in one PR).

### 5.1 Section: Fail closed on the Paystack webhook (Finding 11)

**Understand:** `paystack_webhook()` skips signature verification entirely whenever
`PAYSTACK_WEBHOOK_SECRET` is unset (currently true in production), and separately trusts
attacker-controlled `metadata.tier` from the webhook body as ground truth for what tier to grant.

**This is the one finding in this roadmap requiring an explicit business/security decision before
implementation, not just a code fix:** flipping to fail-closed means the webhook endpoint will reject
*all* traffic (including legitimate Paystack traffic, once it exists) until
`PAYSTACK_WEBHOOK_SECRET` is actually configured. Confirm with whoever owns the Paystack integration
that this is acceptable — the answer should obviously be yes given the alternative is the confirmed P0,
but get it recorded, since this is also the section that determines whether billing can go live at all.

**Implement:**
- [ ] Invert the guard: `if not webhook_secret: raise HTTPException(503, "Webhook not configured")` —
      remove the fallthrough path entirely
- [ ] `_handle_charge_success()`/`_upgrade_tenant_sku()`: stop trusting `metadata.tier` directly. Look
      up the expected tier from a pending-order/checkout-session record your own system created before
      redirecting to Paystack (this requires a small new table + write path at checkout time — treat
      this as its own sub-section since it's the part of the fix that's genuinely new functionality,
      not just a guard flip)
- [ ] Verify the transaction server-to-server against Paystack's `GET /transaction/verify/:reference`
      before crediting any tier change, rather than trusting the webhook payload alone

**Test:**
- [ ] Unsigned webhook request — assert 503, assert no `TenantSKU` mutation occurs
- [ ] Correctly-signed webhook with a `metadata.tier` that doesn't match the pending-order record it
      references — assert rejection, not silent trust
- [ ] Correctly-signed, correctly-referenced webhook — assert the tier upgrade applies, matching what
      the checkout session actually recorded, not what the webhook claims
- [ ] Configure a real (sandbox) `PAYSTACK_WEBHOOK_SECRET` in staging and send an actual test webhook
      from Paystack's dashboard — this finding is severe enough to warrant one genuine
      third-party-integration test, not just mocked signature verification

**Deploy:** Set `PAYSTACK_WEBHOOK_SECRET` in Secret Manager and wire it into the Cloud Run service
(`bootstrap.sh`'s `SECRETS_MAP`) as part of this section's deployment step — the fix is meaningless if
the secret still isn't configured after shipping the code.

### 5.2 Section: Fix CIT minimum-tax logic (Finding 35)

**Implement:**
- [ ] `app/services/tax_calculators/cit_service.py::calculate_cit()`: remove the `and profit <= 0`
      clause; the condition becomes `not is_minimum_tax_exempt and minimum_tax > cit_on_profit`

**Test:**
- [ ] The audit's exact reproduction case (₦200M turnover, ₦1M profit) — assert `final_cit` is now
      ₦1,000,000, not ₦300,000
- [ ] A loss-making non-exempt company (the case the old code accidentally handled correctly) — assert
      still correct, proving the fix didn't regress the one case that used to work
- [ ] A profitable company where `cit_on_profit` genuinely exceeds `minimum_tax` — assert
      `cit_on_profit` is charged, not `minimum_tax` (proving "higher of the two," not "always minimum
      tax now")
- [ ] Small-company exemption still correctly bypasses minimum tax entirely

### 5.3 Section: Fix payroll PAYE relief calculation (Finding 39)

**Implement:**
- [ ] `app/services/payroll_service.py::calculate_salary_breakdown()`: compute pension relief once,
      on pensionable earnings (Basic + Housing + Transport), and pass that single value into
      `calculate_paye()` as an explicit override rather than letting it recompute from full gross
      internally — this likely requires adding an optional `pension_relief_override` parameter to
      `PAYECalculator.calculate_paye()`/`calculate_taxable_income()` rather than only fixing the caller,
      since the double-computation is architectural (the calculator wants to own this computation, the
      caller now needs to override it)
- [ ] Remove the `other_reliefs=float(nhf_relief)` pass-through — `calculate_paye()` already computes
      NHF relief internally from `basic_salary`; passing it again is what causes the double-count

**Test:**
- [ ] The audit's exact reproduction case (₦500k basic, ₦200k housing, ₦100k transport, ₦50k meal, ₦30k
      utility) — assert annual PAYE is now ₦1,359,000, not ₦1,295,800
- [ ] A salary with **zero** meal/utility/other allowances (pensionable earnings == full gross) — assert
      unchanged output, proving the fix doesn't regress the case where the old bug happened to be
      harmless
- [ ] Pension-exempt and NHF-exempt flags — assert relief correctly zeroes out in both cases, not just
      the normal path
- [ ] Cross-check the fixed calculation against a manually-computed reference payroll (an actual
      accountant-verified example, not just re-deriving the audit's own arithmetic) before considering
      this section done — this is real people's tax withholding, worth a second independent check

### 5.4 Section: Give payment-dunning its own state, decoupled from voluntary billing changes (Finding 40)

**Implement:**
- [ ] Migration: add `TenantSKU.dunning_status` (enum: `none`, `active`, `escalated`, `suspended`)
- [ ] `DunningService.record_payment_failure()`/`escalate_dunning_level()`: set `dunning_status`
      instead of overloading `cancel_at_period_end`
- [ ] `DunningService.clear_dunning()`: reset `dunning_status` to `none`, leave
      `cancel_at_period_end`/`scheduled_downgrade_tier` untouched (fixing failure mode 3 from the audit)
- [ ] `app/tasks/scheduled_tasks.py`'s period-end task: check `dunning_status` **first** — if
      `escalated`/`suspended`, suspend/cancel regardless of any pending `scheduled_downgrade_tier`
      (fixing failure mode 1)
- [ ] `BillingService.request_downgrade()`: check `dunning_status != 'none'` before proceeding; reject
      or warn if the organization is currently being dunned (fixing failure mode 2)

**Test — one test per failure mode the audit identified, not a generic "dunning works" test:**
- [ ] Failure mode 1: org has a pending downgrade to Professional, then a payment fails — assert the
      org is suspended at period end, not downgraded to Professional
- [ ] Failure mode 2: org is actively being dunned, calls `request_downgrade()` — assert rejection
- [ ] Failure mode 3: org has a pending downgrade, an unrelated payment retry succeeds — assert the
      pending downgrade is still scheduled, not erased
- [ ] Normal path: no dunning involved, a voluntary downgrade proceeds exactly as before — regression
      check that this section didn't break the working case

### Phase 5 Completion Gate specifics

This phase touches money in four independent ways — before marking it complete, run a combined
scenario test: an organization on a trial (Phase 4's fix), with a scheduled downgrade, that then fails
payment, whose tier is CIT-relevant, computed through a payroll cycle — not because any single finding
requires this, but because Phase 5's own PCG requirement (cross-section integration) demands proving
these four fixes don't interact badly with each other on a shared `TenantSKU`/`Organization` record.

---

## 10. Phase 6 — Authentication & Session Security

**Objective:** Close the confirmed authentication-layer weaknesses.

**Findings closed:** 6 (P1), 33 (P2), 7 (P3), 8 (P3).

**Preconditions:** None from earlier phases — this phase is independent and could technically run in
parallel with Phases 4-5 if resourcing allows, but is sequenced here to keep the roadmap's own
reviewable sequence linear.

### 6.1 Section: Fix `httponly=False` on the access-token cookie (Finding 6)

**Understand — this is the one fix in this roadmap with a confirmed, real dependency the audit itself
found:** `templates/admin_verifications.html::getAccessToken()` (and likely other admin templates using
the same pattern) reads the `access_token` cookie directly via `document.cookie`, which **only works
because** `httponly=False`. Flipping this to `True` without a replacement mechanism breaks those pages.

**Plan:** Move the client-side auth mechanism from "read the cookie via JS" to "receive the token in
the login response body and store it in memory/`sessionStorage` for the JS-driven `Authorization:
Bearer` calls, while the cookie itself becomes `httponly=True` for the browser-driven page navigations
that don't need JS to read it."

**Implement:**
- [ ] `app/routers/auth.py::login()`: set `httponly=True` on the `access_token` cookie
- [ ] Confirm the login response body already returns the access token (check
      `TokenResponse`/whatever `login()` currently returns) — if not, add it
- [ ] Grep all templates for `document.cookie` reads of `access_token` (start with
      `admin_verifications.html`, but the audit didn't exhaustively check every template for this
      specific pattern — do that check now, as part of this section, not as a follow-up) — for each
      one found, change it to use the token from the login response stored in `sessionStorage`
      instead

**Test:**
- [ ] Confirm `document.cookie` no longer contains `access_token` after login (proving the flag
      actually took effect, not just that the code compiles)
- [ ] Every admin page identified in the grep sweep still successfully makes its authenticated API
      calls after the change
- [ ] A simulated XSS payload (in a test environment only) attempting `document.cookie` no longer
      yields a usable token

### 6.2 Section: Fix logout to clear the cookie (Finding 33)

**Implement:**
- [ ] `app/routers/auth.py::logout()`: add a `Response` parameter, call
      `response.delete_cookie("access_token", ...)` and the same for the refresh token, matching the
      exact `path`/`domain` they were set with

**Test:** After calling `/logout`, confirm the browser's cookie jar no longer contains either token
(an integration test using a real cookie-jar-aware test client, not just checking the response
headers superficially).

### 6.3 Section: Fix the broken `get_optional_user` call signature (Finding 7) and delete duplicate dependencies (Finding 8)

**Implement:**
- [ ] `app/dependencies.py::get_optional_user()`: add a `request: Request` parameter, fix the call to
      `get_current_user(request, credentials, db)`
- [ ] Delete the second, duplicate definitions of `require_bank_reconciliation()` and
      `require_advanced_reports()`

**Test:** Since both are currently dead/unreachable, this section's test is specifically about making
them *safely reachable* before anyone wires them up: a direct unit test calling `get_optional_user()`
with valid credentials, confirming no `AttributeError`.

### Phase 6 Completion Gate specifics

Full manual walkthrough of every admin-facing page as a real Super Admin user, post-deploy, since
Finding 6's fix is the one most likely to have an unaudited blast radius (templates the audit didn't
individually check for the same cookie-reading pattern).

---

## 11. Phase 7 — Frontend Security & XSS Remediation

**Objective:** Close the two confirmed stored-XSS findings and hardening the pattern that caused them.

**Findings closed:** 37 (P0), 38 (P2).

**Preconditions:** None structurally, but sequenced after Phase 6 since both phases touch
`admin_verifications.html`'s JS (Phase 6 changes `getAccessToken()`, this phase changes
`renderOrganizations()` in the same file) — doing them in the same phase-adjacent window keeps the
file's changes reviewable as one coherent diff rather than two overlapping ones.

### 7.1 Section: Fix the stored XSS in Admin Verifications (Finding 37)

**Implement:**
- [ ] `templates/admin_verifications.html::renderOrganizations()`: replace raw `${org.name}`/`${org.email}`
      template-literal interpolation with `.textContent` assignment (matching the already-correct
      pattern the same file uses in `viewHistory()`), or route every interpolated value through a
      small `escapeHtml()` helper before building the template string
- [ ] Same fix for the verification-history modal's `${entry.details.notes}` interpolation
- [ ] Sweep every other admin/staff-facing template for the same `innerHTML = ...map(...)` pattern with
      unescaped interpolation — the audit already did this sweep exhaustively (§9.1-9.2 of the audit)
      and found exactly two vulnerable files; re-run that same grep-then-trace methodology here as a
      final confirmation before closing this section, not a new investigation

**Test:**
- [ ] Register an organization with `organization_name` set to `<img src=x
      onerror="window.__xss_fired=true">`; render the admin verifications page as a Super Admin; assert
      `window.__xss_fired` is never set
- [ ] Same test for the history-notes injection point
- [ ] Confirm legitimate organization names with special characters (`O'Brien & Sons`, `<Company>
      Ltd` as a literal string a real business might type) still render correctly and readably, not
      double-escaped into visible entity codes

### 7.2 Section: Fix the same-tenant XSS in the evidence report (Finding 38)

**Implement:**
- [ ] `templates/audit_unified.html::generateEvidenceReportHTML()`: escape `ev.title` (and every other
      interpolated field in the function) before building the print-window HTML string

**Test:** Same pattern as 7.1 — an evidence record with a malicious title, generate the print report,
assert no script execution in the popup window.

### Phase 7 Completion Gate specifics

Since Finding 37's severity comes from its unauthenticated attack surface, the phase gate includes one
end-to-end test performed as an actual anonymous actor would: register through the real public
signup flow (not a direct service call) with a malicious org name, and confirm the admin page renders
it safely — proving the fix at the actual entry point, not just at the rendering function in
isolation.

---

## 12. Phase 8 — API/Frontend Contract & Navigation Fixes

**Objective:** Close the confirmed but lower-severity frontend-contract and navigation defects.

**Findings closed:** 45 (P3), 46 (P2), 47 (P2), 48 (P3).

**Preconditions:** None from earlier phases. This phase can run in parallel with Phase 6/7 if
resourcing allows — flagged here as an explicit parallelization opportunity since none of its four
findings touch security-sensitive code.

### 8.1 Section: Fix the missing `collected_by` field (Finding 45)

**Implement:**
- [ ] `app/routers/evidence_routes.py`'s `/list` endpoint: add `"collected_by": str(e.collected_by) if
      e.collected_by else None` to the per-item response dict, matching the detail endpoint
- [ ] Consider resolving to a display name server-side (the detail endpoint's neighbor code already
      has a `User.first_name, last_name` lookup pattern to reuse) rather than shipping a bare UUID to
      the frontend

**Test:** `/list` and the detail endpoint, called for the same evidence record, now return the same
`collected_by` value (a direct consistency assertion between the two endpoints, not just checking one
in isolation).

### 8.2 Section: Fix the 6 broken internal links (Finding 46)

**Implement, one per link:**
- [ ] `checkout.html`: `/legal/terms` → `/terms`, `/legal/privacy` → `/privacy`
- [ ] `admin_platform_staff.html`: `/admin/dashboard` → `/dashboard`
- [ ] `admin_api_keys.html`, `admin_security.html`, `admin_settings.html`: `/staff/dashboard` →
      `/dashboard`
- [ ] `payment_success.html`: `/settings/billing` → `/settings` (accept the loss of tab pre-selection
      for now, or add hash-based tab selection as a small enhancement if time allows — not required to
      close this finding)
- [ ] `feature_unavailable.html`'s `/contact-sales` and `register.html`'s `/dpa`: these two don't have
      a wrong-prefix fix available — either build the missing page (a product decision: is a
      contact-sales page and a published DPA actually needed before launch?) or remove/hide the link
      until they exist. **Flag this decision to the product owner explicitly** — this section cannot
      close itself without that answer.

**Test:** An automated link-checker test (extract every internal `href`, request each one, assert
non-404) as a permanent regression test — this is exactly the check this roadmap ran manually to find
the 6 broken links in the first place; automating it prevents recurrence.

### 8.3 Section: Fix form-label accessibility (Finding 47)

**Implement:**
- [ ] Across the ~615 affected labels: add matching `id`/`for` pairs (mechanical — generate `id`s
      programmatically where a template doesn't already have a natural unique identifier for the
      field, e.g. `id="street-address"` matching `for="street-address"`)
- [ ] Prioritize by traffic: registration, transaction entry, and invoice forms first (per the audit's
      own prioritization suggestion), then the rest
- [ ] Do this as a series of small, template-by-template commits, not one enormous diff — accessibility
      fixes are easy to get subtly wrong (a duplicate `id` on a page breaks more than it fixes) and
      need reviewable chunks

**Test:**
- [ ] An automated check: for every `<label>` in every template, assert it either has a `for` matching
      an existing `id` on the page, or wraps an `<input>`/`<select>`/`<textarea>` directly
- [ ] No duplicate `id` values within any single rendered page (a real, if less obvious, way this class
      of fix can go wrong)
- [ ] Manual screen-reader spot-check (VoiceOver or NVDA) on the 3 highest-priority forms, since the
      automated check proves structural correctness but not that it *sounds* right

### 8.4 Section: Fix date-locale inconsistency (Finding 48)

**Implement:**
- [ ] Create one shared JS date-formatting helper (`formatDate(date, options)`) that always applies
      `'en-NG'`
- [ ] Replace all 25 non-conforming `toLocaleDateString(...)` call sites (1 `en-GB`, 1 `en-US`, 10 bare)
      to use the shared helper

**Test:** A single test asserting the shared helper always produces `en-NG`-formatted output regardless
of the test runner's own locale/timezone settings (this is the actual bug class — don't just test that
the helper exists, test that it's locale-independent by construction).

### Phase 8 Completion Gate specifics

Standard PCG — this phase has no unusual cross-cutting risk, being entirely frontend/presentation
layer with no shared backend state across its four findings.

---

## 13. Phase 9 — Testing Infrastructure & CI Reliability

**Objective:** Fix the test suite itself and make CI capable of catching regressions, closing the exact
gap that let this roadmap's Phase 4/5 bugs (and Finding 41) ship unnoticed in the first place.

**Findings closed:** 29 (P1), 30 (P2), 31 (P3), 20 (P2), 21 (P2), 15.6 (P1, the `ci.yml` gate).

**Preconditions:** Phases 4 and 5 complete — Finding 15.6's `|| true` removal is explicitly gated on
Findings 27-31 being fixed first (per the audit's own recommendation), and Findings 27/28 are Phase 4,
so this phase cannot start its final section until that's true.

### 9.1 Section: Fix the webhook test's wrong URL (Finding 29)

**Implement:**
- [ ] `tests/test_webhook_integration.py`: fix all 16 occurrences of `/api/billing/webhook/paystack` →
      `/api/v1/billing/webhook/paystack`

**Test:** Re-run the file after Phase 5's Finding 11 fix has also landed — this test file should now
actually exercise the corrected signature-verification logic, not just stop 404ing. Confirm the
`TestWebhookSignatureVerification` tests now test something real (assert they fail correctly against
an unsigned request in a way that proves the *application's* fail-closed behavior, not just that the
URL resolves).

### 9.2 Section: Fix the `TenantSKU(is_trial=False, ...)` fixture bug (Finding 30)

**Implement:**
- [ ] `test_metering_concurrency.py`, `test_metering_load.py`, `test_webhook_integration.py`'s shared
      fixture: replace `is_trial=False` with setting `trial_ends_at=None` (or an appropriate past date,
      per whatever the test scenario needs `is_trial` to evaluate to) — let the computed property
      derive correctly rather than trying to set it directly

**Test:** All previously-erroring tests in these three files now run — record the new pass/fail count
for the concurrency and load suites specifically, since these were never verified to actually pass
their own assertions before (only that they didn't error in setup). Treat any newly-surfaced failures
in the actual test bodies (not just the fixture) as new findings to triage, not as this section's bug.

### 9.3 Section: Fix the pytest fixture-name collision (Finding 31)

**Implement:**
- [ ] `test_api_endpoints.py::test_endpoint`: rename the `name` parameter, or add the
      `@pytest.mark.parametrize("name", [...])` decorator that was evidently intended

### 9.4 Section: Bring the 10 orphaned test files into the real suite, or delete them (Finding 20)

**Implement, per file:**
- [ ] For each of `test_checkout_debug.py` (repo root) and the 9 in `scripts/`: run it directly, assess
      whether it still passes against the current (now-fixed) codebase
- [ ] Passing and relevant → move into `tests/`, confirm it's now collected by `pytest`
- [ ] Failing or superseded → delete, with a note in `docs/REMEDIATION_LOG.md` of what it used to cover
      and where equivalent coverage now lives (if it does)

### 9.5 Section: Remove the 8 Alembic-bypassing scripts (Finding 21)

**Implement:**
- [ ] Confirm each of the 8 scripts' intent is already captured by the current migration history
      (should be true, given Phases 1-3 just brought the schema fully in line)
- [ ] Delete all 8: `add_audit_columns.py`, `add_missing_payment_columns.py`,
      `add_transaction_fx_columns.py`, `create_accounting_tables.py`, `create_fx_tables.py`,
      `fix_enum_values.py`, `fix_payment_transactions_schema.py`, `fix_tier_enum_columns.py`
- [ ] Also remove the dead `scripts/create_railway_tables.py` reference in `ci.yml`'s migration step
      (the audit noted this reference is already stale/dead — clean it up in the same section since
      it's the same theme)

### 9.6 Section: Remove `ci.yml`'s `|| true` (Finding 15.6) — last section in this phase, by design

**Precondition specific to this section:** Findings 27, 28, 29, 30, 31 (all of Phase 4 plus 9.1-9.3
above) must be ✅ before this section starts. Verify by running the full suite locally one more time
immediately before touching `ci.yml` and confirming zero unexpected failures remain.

**Implement:**
- [ ] `.github/workflows/ci.yml`: remove `|| true` from the pytest step
- [ ] Push to a throwaway branch first and confirm the Actions run actually goes red on an intentionally
      broken test, then goes green on the real code — proving the gate works before trusting it on `main`

**Test:** This section's test *is* CI itself — there's no separate local test for "does CI correctly
fail." Use the throwaway-branch method above as the verification.

### Phase 9 Completion Gate specifics

This phase's PCG includes something the others don't: confirm the full suite's pass count is stable
across three consecutive runs (test flakiness would otherwise undermine the entire point of un-gating
CI in 9.6). If any test is flaky, fix or quarantine it before closing this phase — a flaky gate is
barely better than no gate.

---

## 14. Phase 10 — Dependency Management & Build Stability

**Objective:** Prevent the exact class of incident that already broke production once this project
(the Starlette `TemplateResponse` outage).

**Findings closed:** 23 (P1), 24 (P2).

### 10.1 Section: Pin dependency version ranges (Finding 23)

**Implement:**
- [ ] `requirements.txt`: convert every `>=` to a compatible-release range (`~=`) or explicit ceiling,
      starting with `fastapi`, `sqlalchemy`, `jinja2`, `pydantic`, `celery` per the audit's specific
      recommendation, then the remainder
- [ ] Add a `requirements.lock` (via `pip freeze` from a known-good build) that CI/CD actually installs
      from, so "what's running in production" becomes a reviewable, versioned fact

**Test:**
- [ ] `pip install -r requirements.txt` into a clean venv, confirm the resolved versions match what's
      expected (no silent latest-version pulls)
- [ ] Full test suite against this pinned set — this is also, incidentally, the final regression check
      for every fix in Phases 1-9, since it's the first time the *complete* fixed codebase runs against
      a version set deliberately controlled rather than "whatever `pip` resolved on the day"

### 10.2 Section: Split dev/test tooling out of production `requirements.txt` (Finding 24)

**Implement:**
- [ ] Move `pytest`, `pytest-asyncio`, `pytest-cov`, `pytest-benchmark`, `respx`, `black`, `isort`,
      `flake8`, `mypy` into a new `requirements-dev.txt`
- [ ] `Dockerfile`'s `production` stage installs only from `requirements.txt`; the `development` stage
      additionally installs `requirements-dev.txt` (removing its current redundant re-install)

**Test:** Build the `production` target, confirm none of the moved packages are present in the final
image (`docker run <image> pip list | grep pytest` should return nothing).

### Phase 10 Completion Gate specifics

Rebuild the full production Docker image from a clean Docker cache (`docker build --no-cache`) and
confirm it still builds and starts successfully — this is the actual scenario (a routine rebuild
pulling fresh versions) that caused the original outage, so the gate needs to prove that scenario is
now safe, not just that the pinned file looks right.

---

## 15. Phase 11 — Performance & Scalability Hardening

**Objective:** Close the confirmed performance findings that don't block launch but would degrade
badly under real growth.

**Findings closed:** 32 (P2), 42 (P2), 43 (P2).

*(Finding 36's index was already handled in Phase 2, bundled with the security fix it directly
supports — not repeated here.)*

### 11.1 Section: Back the rate limiter with Redis (Finding 32)

**Implement:**
- [ ] `RateLimitingMiddleware`: replace the in-process `dict` with a Redis-backed sliding-window or
      token-bucket implementation, keyed per `(ip, path)`, using the already-provisioned
      `settings.redis_url`
- [ ] Correct the misleading "Redis-compatible for production" docstring once it's actually true

**Test:**
- [ ] Simulate two "instances" (two separate process-local rate limiters, or two actual local uvicorn
      workers) sharing the same Redis — confirm the combined request count across both correctly hits
      the shared limit, where before each would have had its own independent budget
- [ ] Load-test against the real staging Cloud Run service (10-instance autoscale config) and confirm
      the per-IP limit now holds within a small margin of the configured value, not ~10x over

### 11.2 Section: Exempt `/health` from rate limiting (Finding 42)

**Implement:**
- [ ] `RateLimitingMiddleware`: add an `EXEMPT_PATHS` check including `/health`, matching the pattern
      already used in `GeoFencingMiddleware`/`CSRFMiddleware` in the same file

**Test:** Re-run this roadmap's own load-test methodology (200 concurrent `GET /health`) — assert 200/200
now, not 49/200.

### 11.3 Section: Fix the N+1 GL-balance recalculation (Finding 43)

**Implement:**
- [ ] `AccountingService.recalculate_gl_balances_from_journal_entries()`: replace the per-account
      double-query loop with one grouped aggregate query (`SELECT account_id, SUM(debit_amount),
      SUM(credit_amount) ... GROUP BY account_id`), then update each account's balance from that single
      result set
- [ ] `UsageAlertService`'s per-alert org/user lookups: batch into two `WHERE organization_id IN
      (...)` queries outside the loop

**Test:**
- [ ] Functional: recalculated balances match the old (correct, if slow) per-account results exactly,
      for a Chart of Accounts with at least 50 accounts and a realistic transaction volume
- [ ] Performance: assert query count for the recalculation endpoint drops from ~2N to a small constant
      (2-3 queries total), using SQLAlchemy's query-count instrumentation as a permanent regression
      assertion, not just a one-time manual check

### Phase 11 Completion Gate specifics

Run the full load-test script this roadmap's audit-phase predecessor wrote (or an updated version of
it) against staging, covering all three fixes together, and confirm no new N+1 or rate-limit
regressions were introduced by anything else that shipped in Phases 1-10 since the audit's original
pass.

---

## 16. Phase 12 — Dead Code Removal & Codebase Hygiene

**Objective:** Remove confirmed-dead code and code-smell-level issues. Nothing here is
launch-blocking; this phase exists so hygiene work happens deliberately, in one place, rather than as
scattered drive-by changes riding on unrelated PRs (which the audit itself warns against).

**Findings closed:** 3 (P3), 4 (P3), 5 (P3), 13 (P3), 7/8's duplicate-dependency cleanup (already done
in Phase 6, cross-referenced here), the deferred full 388-site commit-ownership retrofit (Finding 44's
remainder beyond the `AuditService`-specific fix in Phase 1), and the 33 Finding-2 candidates that
§3.4's verification found to be genuinely unreachable (logged as Code Smell, not fixed as bugs).

### 12.1 Section: Delete the dead `audit_consolidated.py` router (Finding 3)

**Implement:** Delete `app/routers/audit_consolidated.py` in full — confirmed zero references from
`main.py` or anywhere else.

**Test:** Confirm the application still starts and every route the *actual* four audit routers (`audit.py`,
`audit_system.py`, `advanced_audit.py`, `forensic_audit.py`) expose still resolves correctly (a
regression check that deleting the unused "Option 2" didn't accidentally remove something "Option 1"
depended on).

### 12.2 Section: Delete the 12 orphaned templates (Finding 4)

**Implement:** Delete `advanced_audit.html`, `audit_logs.html`, `dashboard.html`, `worm_storage.html`,
and all 8 files under `templates/partials/org_dashboard/`.

**Test:** Full template-rendering smoke test across every route that renders HTML, confirming none of
them ever referenced the deleted files even indirectly (an `{% include %}` the original audit sweep
might have missed would show up here as a template error).

### 12.3 Section: Clean up stray test files and script sprawl (Finding 5) — remainder not already covered by Phase 9

Phase 9 already handled the 10 test files and 8 schema-bypassing scripts. This section covers whatever
remains of the 43 `scripts/` files that aren't test files or schema-bypass scripts — audit each
remaining one for whether it's still needed, and delete or document the ones that aren't.

### 12.4 Section: Remove or properly gate the dead SQL-injection-shaped utility (Finding 13)

**Implement:** Delete `app/utils/query_optimization.py::analyze_query_performance()` (confirmed zero
callers), or, if the team wants to keep a query-analysis debug tool, rewrite it to never accept a
caller-supplied string and add an explicit `require_platform_role([SUPER_ADMIN])` guard before it's
ever wired to an endpoint.

### 12.5 Section: Full commit-ownership retrofit (remainder of Finding 44)

**Understand:** Phase 1 fixed the `AuditService` half of this (the highest blast-radius, most urgent
part). The remaining ~360 commit call sites across the other 40 services still don't follow the
"services flush, routers commit" convention documented in Phase 1.

**Implement:** Work through the remaining services in priority order (highest write-volume first),
converting each `self.db.commit()` to `self.db.flush()` and confirming the calling router already
commits. This is genuinely 40 small, mechanical, individually-low-risk changes — track each service as
its own commit, apply the SCG to each, and don't rush it into one giant diff just because the
individual changes are simple.

**Test, per service:** The same "simulate a downstream failure, assert atomic rollback" pattern used
in Phase 1.1, applied to at least one write path per converted service.

### Phase 12 Completion Gate specifics

Standard PCG, plus: confirm the codebase's total dead-code footprint (by whatever static-analysis tool
the team prefers — `vulture`, or a repeat of the audit's own manual grep methodology) has measurably
decreased, as the actual proof this phase did what it set out to do.

---

## 17. Phase 13 — Configuration & Deployment Hardening

**Objective:** Close the confirmed insecure-by-default configuration gaps.

**Findings closed:** 26 (P2), 16 (P2, re-confirmed live by the audit — the fix is operational, not
code, but recorded here for completeness).

### 13.1 Section: Flip `debug`/`app_env` defaults to fail safe (Finding 26)

**Implement:**
- [ ] `app/config.py`: `debug: bool = False`, `app_env: str = "production"`
- [ ] `.env.example`: update to model the safe default, with a comment showing how to loosen it for
      local dev (`APP_ENV=development` explicitly, not implicitly)

**Test:**
- [ ] Start the app with **no** environment variables set beyond the required secrets — confirm it
      behaves as production (no stack traces on a triggered error, CSRF/geo-fencing/rate-limiting all
      active) by default
- [ ] Confirm local development still works by explicitly setting `APP_ENV=development` — this flip
      shouldn't make local dev harder, just make the *unconfigured* case safe

### 13.2 Section: Set `CORS_ORIGINS` in production (Finding 16)

**Implement:** Once a real production domain exists (per the `proaudit.com` domain discussion from
earlier in this project), set `CORS_ORIGINS` via `bootstrap.sh`'s `SECRETS_MAP`/env-vars to that
domain. Until then, this section stays flagged 🟧 Blocked — external dependency (domain purchase), not
implementation work.

### Phase 13 Completion Gate specifics

Redeploy to a **fresh** Cloud Run service (not an update to the existing one) using `bootstrap.sh` from
a clean checkout, with no manual environment-variable intervention beyond what `bootstrap.sh` itself
sets — confirm it comes up safe by default. This is the actual scenario Finding 26 warns about (a new
deploy target inheriting insecure defaults), so the gate needs to prove that exact scenario is now
safe.

---

## 18. Phase 14 — Documentation, Release & Final Production-Readiness Sign-off

**Objective:** Close the loop. Confirm every finding is genuinely resolved, not just "worked on," and
produce the final artifact a stakeholder can read to decide whether to launch.

**Preconditions:** Phases 1-13 complete (Phase 13.2 may remain 🟧 Blocked on the domain purchase without
blocking sign-off overall — call this out explicitly in the final report rather than pretending it's
done).

### 14.1 Section: Full-suite final regression

- [ ] Run the entire automated test suite one final time, against production-equivalent staging,
      built via `bootstrap.sh` from a clean checkout
- [ ] Confirm the pass count and confirm zero of the original 48 findings' reproduction tests still
      fail

### 14.2 Section: Re-run the audit's own verification methodology

For each of the findings this roadmap closed, re-run the *exact* verification technique the audit used
to find it in the first place (the AST-based sweeps, the live load-test script, the enum
cross-reference query, the broken-link extractor) — not just this roadmap's own new tests — as an
independent second check that the fix generalizes and wasn't narrowly tailored to the audit's specific
reproduction case.

### 14.3 Section: Handle the audit's remaining open/blocked items explicitly

- [ ] Finding 15 (spoofable upload MIME check) — complete the verification task deferred in §9.2 of
      this roadmap (trace the file-serving path); only then decide whether it needs a fix
- [ ] The orphaned-*row* check (as opposed to orphaned tables, already resolved) — this needs live-DB
      access the audit and this roadmap's authors didn't have; assign it explicitly to whoever does
      have production DB access, with the exact read-only query the audit would have run
- [ ] Cache-hit-rate verification under real load — same treatment, needs production traffic
- [ ] Finding 46's `/contact-sales` and `/dpa` pages — confirm the product decision from Phase 8.2 was
      actually acted on (page built, or link removed) — don't let this quietly stay in limbo

### 14.4 Section: Update all documentation

- [ ] `docs/CHANGELOG.md` — full entry for this remediation effort
- [ ] `docs/AUDIT_CHECKLIST.md` — every section's notes updated to reference the fix commit/PR, not
      just the original finding
- [ ] `docs/REMEDIATION_LOG.md` — final summary
- [ ] Any `docs/*_DOCUMENTATION.md` file whose described behavior changed anywhere in Phases 1-13
- [ ] `docs/GCP_DEPLOYMENT.md` — reflect the final production configuration (secrets added in Phase 5,
      CORS in Phase 13, etc.)

### 14.5 Section: Produce the final Production-Readiness Sign-off report

A short document (or a final section appended to this roadmap) stating, for each of the original
audit's Production-Readiness Verdict rows (Core accounting, Tax/compliance, Multi-tenant isolation,
Billing/payments, Trial onboarding, Authentication, Infrastructure, Dependency management, Testing) —
**Safe** or **Not Safe**, with the specific fix/commit that changed it from the audit's original
verdict. This is the document a non-technical stakeholder reads to decide whether to launch — it must
be honest about anything still 🟧 Blocked (the domain-dependent CORS fix, any unresolved verification
task) rather than presenting a uniformly green report that isn't fully earned.

### Phase 14 Completion Gate

There is no further phase after this one. Its gate is: every finding in §9 traceability table below
shows ✅, 🟧 (blocked on a named, external, non-implementation dependency), or an explicit decision
that it's a Recommendation being deliberately deferred post-launch — nothing shows ⬜ or 🟨.

---

## 19. Cross-Phase Dependency Matrix

| Shared component | Phases involved | Dependency | Required cross-phase test |
|---|---|---|---|
| `AsyncSession` commit boundary | 1 (Finding 44, AuditService only), 12 (Finding 44, full retrofit) | Phase 12 extends a convention Phase 1 established; must not contradict it | Re-run Phase 1's atomic-rollback test against every service Phase 12 touches |
| `tests/conftest.py` schema build | 1 (switches to Alembic), every phase after | All later phases' test signal depends on Phase 1.3 | None needed beyond Phase 1's own gate — this is a one-way dependency |
| `TenantSKU` model | 4 (Finding 28, datetime fix), 5 (Finding 40, dunning state) | Phase 5 adds a column to a model Phase 4 just changed behavior on | Phase 5's combined-scenario test (§9, Phase 5 gate) |
| `admin_verifications.html` | 6 (Finding 6, token storage), 7 (Finding 37, XSS escaping) | Same file, two unrelated fixes in adjacent phases | Full manual walkthrough at the end of Phase 7, not just Phase 6's own gate |
| `UserEntityAccess` table | 2 (Finding 18 centralized check + Finding 36 index) | The index must ship with, not after, the new heavy-query pattern | Phase 2's own `EXPLAIN ANALYZE` test, run before Phase 2 is called complete |
| `SQLEnum` columns on tables Phase 2 touches | 2 (access control), 3 (enum fixes) | Sequenced to avoid compounding two bug classes in one test run | Phase 3's round-trip tests re-run against the Phase-2-hardened endpoints specifically |
| `ci.yml` | 0 (defers the fix), 9 (implements it) | Phase 0 explicitly does NOT fix this; Phase 9 does, gated on Phase 4 | Phase 9.6's throwaway-branch verification |
| `requirements.txt` | 10 (pins versions), every phase before it (all ran against whatever was installed at the time) | Phase 10 is the first time the *fixed* codebase runs against a deliberately controlled dependency set | Phase 10.1's full-suite run is also the de facto final regression for Phases 1-9 |
| Paystack integration | 5 (Finding 11, fail-closed + verification), 13 (secrets/config) | Finding 11's fix requires a real secret to be configured to fully test, which is a Phase 13-adjacent concern | Phase 5's sandbox webhook test must be repeated once Phase 13's secret management is finalized |

---

## 20. Master Finding Traceability Table

| Finding | Sev | Phase | Section | Status |
|---|---|---|---|---|
| 1 (+1b, 1c) | P1 | 3 | 3.1-3.3 | ⬜ |
| 2 | P2 | 3 | 3.4 | ⬜ Now precisely quantified: `scripts/check_enum_type_drift.py` (added 2026-09-25) found 28 remaining "native Enum declared, live column is VARCHAR" mismatches — `audit_runs`, `credit_notes`, `audit_findings`, `auditor_action_logs`, `audit_evidence`, `bank_accounts`, `pit_relief_documents`, `support_tickets` (4 columns), and the bank-reconciliation/expense-claims families. Run the script for the exact current list before starting this section. |
| 3 | P3 | 12 | 12.1 | ⬜ |
| 4 | P3 | 12 | 12.2 | ⬜ |
| 5 | P3 | 12 | 12.3 | ⬜ |
| 6 | P1 | 6 | 6.1 | ⬜ |
| 7 | P3 | 6 | 6.3 | ⬜ |
| 8 | P3 | 6 | 6.3 | ⬜ |
| 11 | P0 | 5 | 5.1 | ⬜ |
| 12 | P3 | *(not yet sequenced — see note below)* | — | ⬜ |
| 13 | P3 | 12 | 12.4 | ⬜ |
| 15 | Potential Risk | 14 | 14.3 (verification only) | ⬜ |
| 16 | P2 | 13 | 13.2 | 🟧 Blocked (domain) |
| 18 | P0 | 2 | 2.1 | 🟨 In progress — `require_entity_access` built, `accounting.py` + `audit.py` + `budget.py` + `consolidation.py` + `dashboard.py` migrated (78/164 endpoints per the original tally, 2026-09-26). 12 files / 86 endpoints remain. `consolidation.py` also got a same-root-cause `group_id` fix (17 endpoints via new `require_group_access`) beyond the original 3-endpoint count — see its roadmap entry and REMEDIATION_LOG.md. |
| 19 | P2 | 1 | 1.4 | ✅ Closed — payroll_advanced.py's 11 models registered in `Base.metadata` |
| 20 | P2 | 9 | 9.4 | ⬜ |
| 21 | P2 | 9 | 9.5 | ⬜ |
| 22 | P1 | 4 | 4.2 | ⬜ |
| 23 | P1 | 10 | 10.1 | ⬜ |
| 24 | P2 | 10 | 10.2 | ⬜ |
| 25 | P3 | *(comment-only fix — see note below)* | — | ⬜ |
| 26 | P2 | 13 | 13.1 | ⬜ |
| 27 | P0 | 4 | 4.1 | 🟨 Functionally fixed 2026-09-25 (added the missing multi-currency fields to the router's local `TransactionCreateRequest`/`TransactionResponse` instead of the roadmap's prescribed method — deleting the duplicate and importing `app/schemas/transaction.py`'s canonical one). Crash is closed; the architectural cleanup this section actually calls for is still open. |
| 28 | P0 | 4 | 4.3 | ⬜ |
| 29 | P1 | 9 | 9.1 | ⬜ |
| 30 | P2 | 9 | 9.2 | ⬜ |
| 31 | P3 | 9 | 9.3 | ⬜ |
| 32 | P2 | 11 | 11.1 | ⬜ |
| 33 | P2 | 6 | 6.2 | ⬜ |
| 34 | P2 | *(not yet sequenced — see note below)* | — | ⬜ |
| 35 | P1 | 5 | 5.2 | ⬜ |
| 36 | P2 | 2 | 2.2 | ⬜ |
| 37 | P0 | 7 | 7.1 | ⬜ |
| 38 | P2 | 7 | 7.2 | ⬜ |
| 39 | P1 | 5 | 5.3 | ⬜ |
| 40 | P1 | 5 | 5.4 | ⬜ |
| 41 | P0 | 1 | 1.1 | ✅ Closed 2026-09-25 — turned out to be 3 missing columns (`target_entity_type`/`target_entity_id`/`changes`), not 2, plus a NOT NULL `entity_id`/`user_id` mismatch that made every failed-login attempt 500 instead of 401/429. See `docs/REMEDIATION_LOG.md`. |
| 42 | P2 | 11 | 11.2 | ⬜ |
| 43 | P2 | 11 | 11.3 | ⬜ |
| 44 | P2 | 1 (partial), 12 (full) | 1.2, 12.5 | ⬜ |
| 45 | P3 | 8 | 8.1 | ⬜ |
| 46 | P2 | 8 | 8.2 | ⬜ |
| 47 | P2 | 8 | 8.3 | ⬜ |
| 48 | P3 | 8 | 8.4 | ⬜ |
| 49 (new, not in original 48) | P1 | 1 | 1.5 | ✅ Closed 2026-09-25 — every remaining mismatch confirmed a documented, intentional exception (superseded legacy columns from earlier design changes), not an oversight. `scripts/check_fk_drift.py` is now a permanent tool. See `docs/REMEDIATION_LOG.md`. |
| 50 (new, not in original 48) | P0/P1 (varies by table — see `docs/FINDING_50_SCOPE.md`) | 1 | 1.5 | ✅ Closed 2026-09-25 — all 66 of the original 66 tracked tables resolved in code. Deploy still blocked by the closed org billing account; nothing past commit `5cab0ec` has shipped. See `docs/FINDING_50_SCOPE.md`/`docs/REMEDIATION_LOG.md`. |
| 51 (new, not in original 48) | P1 (leaning) — CONFIRMED, reproduced live 3+ times total (twice more on 2026-09-25 during Finding 49/50 work), a real `db_session` connection leak; recovers with a plain `kill` of the stuck process but root cause (why the leak happens) still not fixed | 9 (tentative) | Not yet assigned | 🟨 |
| 52 (new, not in original 48) | P0, CONFIRMED — deploy pipeline's migration step silently never ran migrations | 0 (deployment baseline) | Fixed directly, not deferred — `cloudbuild.yaml` now pins the job's command every deploy plus a new verification step; see `docs/REMEDIATION_LOG.md` | ✅ |
| 53 (new, not in original 48) | P3, CONFIRMED — `verify-migration-applied`'s `gcloud logging read` can false-fail a good deploy due to Cloud Logging propagation delay | 0 (deployment baseline) | Fixed directly — `cloudbuild.yaml`'s check now retries up to 6 times over ~30s before concluding the head marker genuinely isn't there; see `docs/REMEDIATION_LOG.md` | ✅ |

**Note on Findings 12, 25, and 34 — not yet assigned a dedicated section above, added here for
completeness rather than left off the table entirely:**
- **Finding 12** (unauthenticated internal metrics endpoint, P3) — add `require_platform_staff()` to
  `websocket.py::get_websocket_stats()`. One-line fix; fold into Phase 6 (Section 6.3) as an additional
  item, since it's the same "add a missing dependency" shape as that section's other two items.
- **Finding 25** (misleading middleware-order comments, P3, Code Smell) — fold into Phase 12 as an
  additional item in Section 12.3; purely a comment rewrite, no behavior change.
- **Finding 34** (compliance-replay endpoint crashes on non-numeric input, P2) — fold into Phase 8 as
  an additional Section 8.5: replace `ReplayRequest.inputs: Dict[str, Any]` with a typed model per
  `calculation_type`, matching the validation pattern the normal PAYE/VAT endpoints already have. Test:
  the audit's exact reproduction (`{"gross_annual_income": "abc"}`) now returns a clean 422, not a 500.

Update this table's Status column as the single source of truth for "where are we" — do not let it
drift from `docs/REMEDIATION_LOG.md`'s narrative account; the table is the fast-scan view, the log is
the detailed one, and they must agree.

---

## 21. Changelog for This Roadmap

| Date | Change |
|---|---|
| 2026-09-19 | Initial roadmap created from `docs/PRODUCTION_AUDIT_2026.md` (48 findings) and `docs/AUDIT_CHECKLIST.md`. |
| 2026-09-19 | Phase 0 executed. Baseline commit `3f082bc`, tag `pre-remediation-baseline`. Local production Docker build: clean. Cloud Run baseline revision recorded: `proaudit-web-00012-6sb`. Baseline test run against a real `alembic upgrade head` schema surfaced a new, previously-undiscovered systemic finding (Finding 49 — 93 real DB foreign-key constraints with no matching ORM declaration); 57 of 93 fixed and verified in this session (see `docs/REMEDIATION_LOG.md` for the full investigation, including a caught-and-reverted false start on `AuditMixin`); the remaining 51 formally scoped as new Phase 1 §1.5, gated ahead of §1.3. Added Phase 1 §1.5 to this roadmap and Finding 49 to §20's traceability table. |
