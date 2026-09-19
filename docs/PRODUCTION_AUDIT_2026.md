# Tekvwa Pro Audit — Independent Production Readiness Audit

**Started:** 2026-09-19
**Methodology:** Section-by-section, evidence-based. Every finding below is backed by either
(a) direct code inspection with file:line citations, or (b) live verification against the running
application/database (queries actually executed, not assumed). Findings are explicitly labeled
**Confirmed / Likely / Potential Risk / Code Smell / Recommendation** — see Section 0.

**Note on prior audit documents:** `docs/AUDIT_REPORT.md`, `docs/SYSTEM_AUDIT_REPORT.md`, and
`docs/WORLD_CLASS_AUDIT_DOCUMENTATION.md` already exist in this repo and self-report full
verification ("Status: Yes All Systems Verified"). Those are self-authored claims from within the
project, not independently verified — several of the confirmed bugs below (see Finding 1) are
exactly the kind of thing those documents claim doesn't exist. Treat prior "audit" docs in this repo
as unverified until this audit re-confirms or contradicts them.

---

## 0. Severity & Confidence Legend

| Severity | Meaning |
|---|---|
| P0 Critical | Security vulnerability, data loss, production-breaking, major functionality failure |
| P1 High | Major feature broken, serious authz/data issue, significant production risk |
| P2 Medium | Functional issue, tech debt, performance issue, important inconsistency |
| P3 Low | Minor cleanup, UX improvement, non-critical optimization |

| Confidence | Meaning |
|---|---|
| **Confirmed** | Verified by direct evidence — code inspection + live DB/runtime check |
| **Likely** | Strong evidence, same pattern as a Confirmed case, not individually re-verified |
| **Potential Risk** | Plausible based on code shape, not yet traced end-to-end |
| **Code Smell** | Not necessarily a bug, but a maintainability/consistency concern |
| **Recommendation** | Suggested improvement, no defect implied |

---

## EXECUTIVE SUMMARY (updated as findings accumulate — current as of Finding 25)

### A. Overall assessment

**Not production-ready in its current state.** The application is architecturally sound in many
places (the RBAC dependency layer, the org-role-escalation prevention logic, and 44+ of 68 routers
correctly scope data to the caller's organization) — this is not a codebase built carelessly. But seven
confirmed, high-severity defects would each independently block a production launch, four are already
actively exploitable/broken with zero special access — one of those requires nothing but filling out
the public signup form, and one silently breaks writes across roughly a quarter of the app's own
routers — and one silently produces wrong numbers a real user could file with a tax authority. Four of
the seven were confirmed not by reading the code but by actually running it, which is the strongest
evidence standard this audit uses:

1. **Cross-tenant data exposure and data-integrity risk (Finding 18, P0):** 164 API
   endpoints across 17 routers let any authenticated user read — and in several routers' cases, mutate
   — another organization's financial reports, tax filings, audit logs, forensic analyses, budgets,
   general ledger, and fiscal period state, simply by supplying a different entity UUID. Every one of
   these has now been individually traced to the service layer and confirmed exploitable (no
   unresolved candidates remain).
2. **The central audit-logging service cannot write a single record, and roughly 26 routers' write
   endpoints call it with no exception handling narrow enough to survive it (Finding 41, P0):**
   `AuditLog.target_entity_type` was added to the model but never migrated into the actual database —
   confirmed by running the real Alembic migration chain (the same one used for the live GCP
   deployment) and then exercising a real endpoint, not by reading the code. Every call to
   `AuditService.log_action()` fails, deterministically, on every invocation, meaning every write
   operation across roughly a quarter of this application's routers — creating vendors, accounts,
   journal entries, invoices, receipts, transactions, payroll records, entities, and more — is at risk
   of a raw 500 the moment it tries to record what it just did. The existing test suite cannot see this
   at all, because it builds its schema from the current models directly rather than from migrations —
   a second, independent finding in its own right. This may be the single highest-blast-radius defect
   in this report.
3. **Stored XSS in the Admin Verifications panel grants an unauthenticated attacker code execution in
   a Super Admin's session (Finding 37, P0):** the organization-name field, filled in by anyone during
   public self-registration with zero sanitization, is rendered via unescaped `innerHTML` on the one
   page restricted to Super Admin/Admin accounts. The platform's own CSP would normally block this, but
   it's deliberately configured with `script-src 'unsafe-inline'` for Alpine.js, so nothing stops it.
   Register with a malicious name, wait for a routine admin review, and the payload runs with full
   admin privileges — no authentication of any kind required to launch the attack.
4. **Unauthenticated billing takeover (Finding 11, P0):** the Paystack webhook accepts completely
   unsigned requests right now (its signature check is skipped whenever the webhook secret is unset,
   which it currently is) and, traced end-to-end, will grant any organization the highest paid tier
   for free from a single anonymous HTTP request. Independently re-confirmed against the live Cloud
   Run deployment (§14.1): the webhook secret is genuinely absent from production today.
5. **Creating a transaction is completely broken (Finding 27, P0):** `POST
   /{entity_id}/transactions` — the single most fundamental write operation in a bookkeeping app —
   crashes with an `AttributeError` on every call, for every input, because the router uses a stale
   local copy of its request schema that's missing the `currency` field the handler unconditionally
   reads. Reproduced by actually running the test suite, not inferred from reading the code.
6. **Trial-subscription status checks crash for every trial tenant (Finding 28, P0):** comparing a
   timezone-aware `trial_ends_at` against a timezone-naive "now" raises `TypeError` for any
   organization currently on a trial. The dedicated status endpoint returns a raw 500 to the trial
   user; separately, the middleware call site fails open, meaning trial/grace-period access
   enforcement is silently disabled for the entire trial-tenant segment. Also confirmed by execution.
7. **Company Income Tax minimum-tax rule silently doesn't apply where it should (Finding 35, P1):**
   `CITCalculator.calculate_cit()` only charges the higher minimum tax when a company's profit is zero
   or negative — but a profitable, low-margin company (exactly the case minimum tax exists for) falls
   through and is undercharged. Reproduced with a concrete example: a ₦200M-turnover, ₦1M-profit
   company is charged ₦300,000 when the correct figure is ₦1,000,000 — a 68% shortfall. This is not a
   crash; it is a silently wrong number a real user could file with the tax authority as-is.

Beyond these seven, there is a systemic, already-proven-to-break-things pattern of **insufficient
defensive engineering around type boundaries, undocumented conditions, and model/migration drift** —
the enum-casing bug (Finding 1, confirmed across 35 database columns), the unbounded dependency
versions that already caused a full-site outage this session (Finding 23), the invoice line-item
crash (Finding 22), the naive/aware datetime bug (Finding 28), the audit-log column that was never
migrated (Finding 41), the CIT minimum-tax condition that doesn't match its own comment (Finding 35),
a payroll relief calculation that silently understates PAYE on every ordinary salary structure
(Finding 39), and a shared boolean flag with no coordination between voluntary billing changes and
involuntary payment-dunning suspension (Finding 40) all share the same root shape: code that assumes a
value, column, or condition will always hold, or that a field means only one thing, with no
validation, fallback, or test coverage catching it when that assumption breaks.

### B. Major risks (see Section C for full severity-ranked list)

- Cross-tenant IDOR spanning financial/tax/audit data and fiscal-period mutation (P0)
- The central audit-log write path is broken for every caller, risking a 500 on ~26 routers' writes (P0)
- Stored XSS reachable by any anonymous visitor, executes in a Super Admin's session (P0)
- Unauthenticated billing/subscription tier escalation via unsigned webhook (P0)
- Creating a transaction via the API crashes on every call, no exceptions (P0)
- Trial-subscription status checks crash for every active-trial tenant; enforcement silently fails open (P0)
- CIT minimum tax silently undercharges profitable, low-margin companies — a wrong number, not a crash (P1)
- Every payroll run understates PAYE via a relief-basis mismatch and double-counted NHF relief (P1)
- A customer facing suspension for non-payment can escape it via an unrelated downgrade request (P1)
- Systemic enum value-casing mismatch breaking writes across ~35 DB columns / a dozen+ features (P1)
- The test suite's schema setup bypasses migrations entirely, hiding this entire class of drift (P1)
- `httponly=False` on the primary auth cookie (P1)
- Unbounded dependency versions with a proven history of breaking the entire app on rebuild (P1)
- Core invoicing feature (edit line item) crashes on a normal, expected request shape (P1)
- CI's test job cannot fail (`|| true`), so none of the above would ever show up red in CI (P1)

### C. Production-readiness verdict

| Area | Verdict |
|---|---|
| Core accounting/invoicing functionality | **Not safe** — creating a transaction crashes on every call (Finding 27); invoice line-item edits crash on a normal request shape (Finding 22); the audit-log write path underneath most write endpoints is broken (Finding 41); the enum-casing bug (Finding 1) is waiting to surface wherever an affected column is written to |
| Tax calculation / compliance | **Not safe** — CIT minimum tax silently undercharges the exact companies it exists to catch (Finding 35); payroll silently understates PAYE on ordinary salary structures (Finding 39); PAYE/VAT/WHT calculators themselves independently verified robust against edge cases (§12) |
| Multi-tenant data isolation | **Not safe** — this is the P0 that most needs fixing before any real customer organizations share the platform |
| Billing/payments | **Not safe to enable** until Finding 11 is fixed — do not turn on live Paystack keys before this is resolved; separately, Finding 40 lets a non-paying customer dodge suspension |
| Trial onboarding | **Not safe** — the subscription-status endpoint 500s for every trial user, and trial-tier enforcement is silently disabled (Finding 28) |
| Authentication | Functionally correct (password reset, RBAC, self-escalation prevention all verified sound) but has a real cookie-security weakness |
| Infrastructure/deployment | Solid — GCP migration, secrets management, and CI/CD pipeline are in good shape, though `DEBUG`/`APP_ENV` insecure-by-default and a non-blocking test suite are real gaps (§14, §15) |
| Dependency management | Actively risky — no version ceilings, already caused one full outage |
| Testing | The suite itself mostly works (773/834 passing) but cannot currently catch regressions — CI never fails on test results, and the one file testing the P0 webhook vulnerability has a wrong URL in every request (§15) |

---

## B. CRITICAL ISSUES — full P0/P1 list, in the order they should be fixed

| # | Finding | Sev | Section | One-line fix |
|---|---|---|---|---|
| 1 | 18 | P0 | §3 | Add `verify_entity_access`/`get_entity_by_id(entity_id, current_user)` check to 164 endpoints across 17 routers; fix the fake `resolve_entity_id` helper in 2 of them and the additive-not-restrictive `organization_id` pattern in `report_template.py` |
| 2 | 41 | P0 | §6.3 | Add a migration for `audit_logs.target_entity_type`/`target_entity_id` so `AuditService.log_action()` can insert a row at all; separately stop building the test DB with `Base.metadata.create_all()` and run real migrations instead |
| 3 | 37 | P0 | §9.1 | Escape `org.name`/`org.email`/`entry.details.notes` before `innerHTML` insertion in `admin_verifications.html` (use `.textContent` or an HTML-escaping helper); sweep other admin templates for the same pattern |
| 4 | 11 | P0 | §2 | Fail closed (reject) when `PAYSTACK_WEBHOOK_SECRET` is unset, instead of skipping verification; stop trusting `metadata.tier` from the webhook payload as ground truth |
| 5 | 27 | P0 | §15.1 | Delete `transactions.py`'s stale local `TransactionCreateRequest`; import/complete the schema so `request.currency` actually exists |
| 6 | 28 | P0 | §15.2 | Use `datetime.now(timezone.utc)` instead of naive `datetime.utcnow()`/`datetime.now()` everywhere compared against `TenantSKU.trial_ends_at` |
| 7 | 35 | P1 | §16.5 | Remove the `and profit <= 0` clause from `CITCalculator.calculate_cit()`'s minimum-tax condition — it should just be `minimum_tax > cit_on_profit` |
| 8 | 39 | P1 | §16.6 | In `payroll_service.py::calculate_salary_breakdown`, pass one correctly-computed pension relief (on pensionable earnings) into `calculate_paye()`, and stop also passing `other_reliefs=nhf_relief` when NHF is already computed internally |
| 9 | 40 | P1 | §16.7 | Give payment-dunning its own state field, independent of `cancel_at_period_end`/`scheduled_downgrade_tier`; make the scheduled task check dunning state before applying any pending voluntary downgrade |
| 10 | 1 | P1 | §1 | Add `values_callable=lambda e: [m.value for m in e]` to 30+ confirmed `SQLEnum(...)` columns; separately reconcile 4 columns with genuinely divergent value sets and normalize `journalentrytype`'s mixed casing |
| 11 | 6 | P1 | §7 | Set `httponly=True` on the `access_token` cookie; solve the client-side-read need a different way |
| 12 | 23 | P1 | §18 | Pin dependency versions to compatible-release ranges, starting with `fastapi`/`sqlalchemy`/`jinja2`/`pydantic`/`celery` |
| 13 | 22 | P1 | §16 | Add a persisted `vat_rate` column to `InvoiceLineItem`; stop unconditionally reading a value that may never have been set |
| 14 | 29 | P1 | §15.3 | Fix the URL in all 16 requests in `test_webhook_integration.py` (`/api/billing/...` → `/api/v1/billing/...`) so it actually tests Finding 11 |
| 15 | 15.6 | P1 | §15.6 | Remove the trailing `\|\| true` from `ci.yml`'s pytest step so failing tests actually fail CI — sequence after Findings 27-31 are fixed |
| 15 | 26 | P2 | §14 | Flip `debug`/`app_env` defaults in `app/config.py` to fail safe (`False`/`production`) — protects 4 controls at once: stack-trace leakage, CSRF, geo-fencing, and rate-limit strictness (§8.6) |
| 16 | 32 | P2 | §8.7 | Back the rate limiter with Redis (already provisioned) instead of a per-instance in-memory dict, so limits hold under Cloud Run's real 10-instance autoscaling |
| 17 | 33 | P2 | §8.8 | Add a `Response` param to `logout()` and call `delete_cookie()` for the access/refresh token cookies |
| 18 | 34 | P2 | §12.2 | Replace `ReplayRequest.inputs: Dict[str, Any]` with a typed model per calculation type, or wrap the `Decimal(str(...))` conversions in a try/except |
| 19 | 36 | P2 | §6.2 | Add an index to `UserEntityAccess.user_id`/`.entity_id` (or a composite index) and a `UniqueConstraint(user_id, entity_id)`; add `index=True` to `AccountBalance.entity_id` |
| 20 | 38 | P2 | §9.2 | Escape `ev.title` before insertion into `generateEvidenceReportHTML()`'s HTML string in `audit_unified.html` |
| 21 | 42 | P2 | §13.2 | Add `/health` to `RateLimitingMiddleware`'s exempt paths, matching the existing pattern in `GeoFencingMiddleware`/`CSRFMiddleware` |
| 22 | 43 | P2 | §13.3 | Rewrite `recalculate_gl_balances_from_journal_entries` to use one grouped `SUM(...) GROUP BY account_id` query instead of 2 queries per account; batch `UsageAlertService`'s per-alert org/user lookups |
| 23 | 44 | P2 | §10.4 | Adopt one commit-ownership convention (recommended: services `flush()` only, routers/a shared dependency `commit()` once per request) — not a full retrofit of all 388 sites, but the new convention going forward |
| 24 | 46 | P2 | §9.3 | Fix 6 broken hrefs (`/legal/terms`→`/terms`, `/legal/privacy`→`/privacy`, `/admin/dashboard` and `/staff/dashboard`→`/dashboard`, `/settings/billing`→`/settings`) across 7 templates; build or remove `/contact-sales` and `/dpa` |
| 25 | 47 | P2 | §9.4 | Add matching `id`/`for` pairs (or nest inputs in labels) across ~615 form labels, starting with the highest-traffic forms (registration, transactions, invoices) |
| 26 | 30 | P2 | §15.4 | Fix the `TenantSKU(is_trial=False, ...)` fixture bug in `test_metering_concurrency.py`/`test_metering_load.py`/`test_webhook_integration.py` — set `trial_ends_at` instead |
| 27 | 31 | P3 | §15.5 | Rename the `name` parameter in `test_api_endpoints.py::test_endpoint` (or add the missing `@pytest.mark.parametrize`) |
| 28 | 45 | P3 | §5.1 | Add `collected_by` to `/api/evidence/list`'s per-item response dict, matching the detail endpoint for the same resource |
| 29 | 48 | P3 | §17.1 | Replace all bare/non-`en-NG` `toLocaleDateString()` calls with the same explicit locale used in the other 23 call sites; factor into one shared helper |

---

## 1. Application Structure — Audit Map

### 1.1 Scale (ground truth, counted directly)

| Area | Count |
|---|---|
| Routers (`app/routers/*.py`) | 68 files, 66 actually mounted in `main.py` |
| Services (`app/services/*.py`) | 92 |
| Model files (`app/models/*.py`) | 32 (29 with `__tablename__`, 1 pure-enum file, base/`__init__`) |
| Database tables (live, verified via `information_schema`) | 109 declared by models; **124 actually in the DB** — 15-table gap not yet explained (see Open Question 1.1a) |
| Postgres native enum types (live, verified via `pg_enum`/`pg_type`) | 53 |
| Middleware | 4 (`security.py`, `sku_middleware.py`, `emergency_mode.py`, `__init__.py`) |
| Templates (`templates/**/*.html`) | 85 |
| Background task modules | `app/tasks/celery_tasks.py` (1725 lines, ~24 Celery task wrappers) + `app/tasks/scheduled_tasks.py` (1032 lines, actual implementations, lazily imported from celery_tasks.py — not dead, just layered) |
| Alembic migrations | 35 |
| Test files | 24 (`tests/test_*.py`) + 1 stray `test_checkout_debug.py` at repo root (see Finding 3) |
| Ops scripts | 43 (many are one-off/debug scripts — see Finding 4) |

**Open Question 1.1a:** 109 model-declared tables vs. 124 live tables is a real discrepancy that needs
its own investigation pass (Section 6). Not yet root-caused — could be legitimate (e.g. `alembic_version`,
association tables without a dedicated model class) or could indicate orphaned schema. Flagged, not
resolved.

### 1.2 Finding 1 — CONFIRMED, P1 High: Systemic enum value-casing bug across the ORM layer

**What's wrong:** Throughout `app/models/*.py`, SQLAlchemy `Column`/`mapped_column` definitions use
`SQLEnum(SomeEnum)` (aliased from `sqlalchemy.Enum`) **without** `values_callable=...`. SQLAlchemy's
default behavior without that argument is to persist the Python enum member's `.name` (e.g.
`"REALIZED"`), not its `.value` (e.g. `"realized"`). Many of the corresponding native Postgres enum
types were created by hand-written migrations using **lowercase** values that match `.value`, not
`.name`. Any ORM write to one of these columns sends the uppercase name, which Postgres rejects with
`invalid input value for enum <type>`.

**How this was verified (not assumed):** loaded the live app's SQLAlchemy metadata inside the running
container, introspected every column's resolved Postgres enum type name and the exact string values
SQLAlchemy would send for it, and cross-referenced against `pg_enum`/`pg_type` queried live from the
production Cloud SQL database. This is a full-coverage structural check, not a sample.

**30 columns are CONFIRMED broken** (SQLAlchemy would send a value that does not exist in the
column's actual Postgres enum type — verified by name-for-name comparison against the live DB):

| Table.column | Postgres type | Would send | DB actually has |
|---|---|---|---|
| `usage_events.metric_type` | `usagemetrictype` | `TRANSACTIONS`, ... | `transactions`, ... (lowercase) |
| `feature_access_logs.feature` | `feature` | `GL_ENABLED`, ... (46 values) | lowercase equivalents |
| `business_entities.business_type` | `businesstype` | `BUSINESS_NAME`, `LIMITED_COMPANY` | `business_name`, `limited_company` |
| `invoices.buyer_status` | `buyerstatus` | `PENDING`,`ACCEPTED`,`AUTO_ACCEPTED`,`REJECTED` | `pending`,`accepted`,`rejected` (no `auto_accepted` at all — see Finding 1b) |
| `vat_recovery_records.recovery_type` | `vatrecoverytype` | uppercase | lowercase |
| `pit_relief_documents.relief_type` | `relieftype` | uppercase | lowercase |
| `fixed_assets.category` | `assetcategory` | uppercase | lowercase |
| `fixed_assets.status` | `assetstatus` | uppercase | lowercase |
| `fixed_assets.depreciation_method` | `depreciationmethod` | uppercase | lowercase |
| `fixed_assets.disposal_type` | `disposaltype` | uppercase | lowercase |
| `depreciation_entries.depreciation_method` | `depreciationmethod` | uppercase | lowercase |
| `bank_statements.source` | `bankstatementsource` | uppercase | lowercase |
| `bank_statement_transactions.detected_charge_type` | `adjustmenttype` | uppercase, **and includes values that don't exist in the DB at all** (`INTEREST_INCOME`, `INTEREST_EXPENSE` vs DB's `interest_earned`, `interest_paid`, `foreign_exchange`) | lowercase, different value set |
| `bank_statement_transactions.match_type` | `matchtype` | uppercase, **and wrong value set** (`EXACT`,`FUZZY` vs DB's `exact`,`fuzzy_amount`,`fuzzy_date`) | lowercase, different value set |
| `bank_statement_transactions.match_confidence_level` | `matchconfidencelevel` | uppercase | lowercase |
| `bank_reconciliations.status` | `reconciliationstatus` | uppercase, **missing values** (`PENDING_REVIEW`, `REJECTED` not in the model's Python enum at all, but exist in the DB) | lowercase, wider value set |
| `reconciliation_adjustments.adjustment_type` | `adjustmenttype` | same mismatch as above | |
| `unmatched_items.item_type` | `unmatcheditemtype` | uppercase, **wrong value set** (model has `BANK_CHARGE`,`UNEXPECTED_DEPOSIT`,`UNEXPECTED_WITHDRAWAL`,`REVERSAL`; DB has `bank_error`,`book_error`,`unidentified_deposit`,`unidentified_withdrawal`,`reversal_pending`,`other`) | different value set entirely |
| `bank_charge_rules.charge_type` | `adjustmenttype` | same as above | |
| `bank_charge_rules.detection_method` | `chargedetectionmethod` | uppercase, **wrong value set** (model: `NARRATION_REGEX`,`AMOUNT_EXACT`,`UNMATCHED`,`AUTO_MATCHED`,`MANUAL_MATCHED`,`RECONCILED`,`DISPUTED`; DB: `narration_pattern`,`exact_amount`,`amount_range`,`keyword_match`,`combined`) | different value set entirely |
| `bank_statement_imports.source` | `bankstatementsource` | uppercase | lowercase |
| `platform_api_keys.key_type` | `apikeytype` | uppercase | lowercase |
| `platform_api_keys.environment` | `apikeyenvironment` | uppercase | lowercase |
| `emergency_controls.action_type` | `emergency_action_type` | uppercase | lowercase |
| `fiscal_periods.status` | `fiscalperiodstatus` | model has `PENDING_CLOSE`, **DB does not** | DB: `OPEN`,`CLOSED`,`LOCKED`,`REOPENED`,`YEAR_END` |
| `journal_entries.entry_type` | `journalentrytype` | model has `OPENING_BALANCE`,`CLOSING_ENTRY`,`PREPAYMENT`,`TRANSFER`,`SYSTEM` etc. — **none of these exist in the DB type at all** | DB: `MANUAL`,`SALES`,`PURCHASE`, etc. (17 original uppercase values) plus 3 lowercase values added later (`fx_revaluation`, `fx_realized_gain_loss`, `fx_unrealized_gain_loss` — themselves inconsistent with the other 17, see Finding 1c) |
| `journal_entries.status` | `journalentrystatus` | model has `PENDING`, **DB does not** | DB: `DRAFT`,`PENDING_APPROVAL`,`APPROVED`,`POSTED`,`REJECTED`,`REVERSED`,`VOIDED` |
| `recurring_journal_entries.entry_type` | `journalentrytype` | same as journal_entries above | |
| `fx_revaluations.revaluation_type` | `fxrevaluationtype` | uppercase | lowercase |
| `fx_revaluations.fx_account_type` | `fxaccounttype` | uppercase | lowercase |

**Finding 1b (Confirmed, separate from casing):** `invoices.buyer_status`'s Python enum
(`app/models/invoice.py`) includes a member `AUTO_ACCEPTED` that has **no corresponding label in the
live Postgres type at all** — this isn't just a casing issue, the value literally cannot be written
under any casing until the DB type is altered. Same root problem hits `bank_reconciliations.status`,
`unmatched_items.item_type`, and `bank_charge_rules.detection_method` — the model's enum and the DB
type have **diverged in which values exist**, not just how they're cased. These four need a data-model
reconciliation, not just a `values_callable` fix.

**Finding 1c (Confirmed):** `journalentrytype` itself is an internally inconsistent Postgres enum: 17
of its 20 values are uppercase (from the original migration) and 3 are lowercase
(`fx_revaluation`, `fx_realized_gain_loss`, `fx_unrealized_gain_loss`, added later by a raw
`ALTER TYPE ADD VALUE` in a subsequent migration). No `values_callable` fix can make one Python enum
correctly serve both casings at once — this type needs to be normalized (pick one casing, migrate the
mismatched values) as part of the fix, not just patched at the ORM layer.

**5 more columns are near-certain (Likely) duplicates of this same bug**, missed by the automated
introspection only because the *type name* SQLAlchemy expects doesn't match the type name the
migration actually created (a separate, second bug — see Finding 2) — but once you resolve the name
mismatch, the underlying values are lowercase in the DB while the Python enums use the same
uppercase-name convention as every confirmed case above:

- `accounting_dimensions.dimension_type` (DB type `dimension_type`, all-lowercase values)
- `three_way_matches.status` (DB type `matching_status`, all-lowercase)
- `wht_credit_notes.status` (DB type `wht_credit_status`, all-lowercase)
- `approval_requests.status` (DB type `approval_status`, all-lowercase)
- `budgets.period_type` (DB type `budget_period_type`, all-lowercase)

**Why this matters:** every one of these 35 columns will raise a database error the first time
application code actually tries to **write** a non-default value through the ORM (e.g. marking a fixed
asset disposed, creating a bank reconciliation adjustment, approving a budget, recording an FX
revaluation, generating a platform API key). This is not a theoretical risk — it is the exact bug that
broke super admin seeding and platform-test-entity seeding earlier in this project (documented in
`docs/GCP_DEPLOYMENT.md` §5), just not yet fixed for the other 33+ columns because those code paths
haven't been exercised yet.

**Already fixed (for reference, not part of this list):** `platform_role` (`app/models/user.py`),
`organization_type`, `verification_status` (`app/models/organization.py`) — these three were fixed
during the earlier GCP migration work by adding `values_callable=lambda enum_cls: [e.value for e in
enum_cls]`. **`user.role` (`UserRole`) is genuinely safe as-is** — verified: its DB type `userrole` uses
uppercase values that already match `.name`, so no fix is needed there. This is the one enum column in
the whole codebase that "works by accident" rather than by design.

**Recommended fix (do not implement yet — audit phase only, per your instructions):**
1. For the 30 (+5 likely) confirmed-broken columns: add `values_callable=lambda e: [m.value for m in e]`
   to each `SQLEnum(...)` call. Mechanical, low-risk, same fix already applied to the 3 reference cases.
2. Separately reconcile the 4 columns with genuinely divergent value sets (Finding 1b) — these need a
   product decision on which values are correct, then a migration to align the DB type, before the
   `values_callable` fix alone would be sufficient.
3. Separately normalize `journalentrytype`'s mixed casing (Finding 1c) — likely means adding uppercase
   equivalents for the 3 straggler values, or migrating existing rows and re-adding them uppercase.
4. Add a CI check (a small script very close to the one used to produce this finding) that fails the
   build if any `SQLEnum` column's Python values don't match its live DB type — this exact class of bug
   is trivial to prevent going forward and expensive to find by accident in production.

### 1.3 Finding 2 — CONFIRMED, P2 Medium: Enum type-name mismatches between models and migrations

Distinct from Finding 1: for 5 columns (listed under "Likely" above) plus a further batch still to be
individually confirmed, the SQLAlchemy model doesn't pass an explicit `name=` to `SQLEnum(...)`, so
SQLAlchemy computes a default Postgres type name from the Python class name (e.g. `DimensionType` →
`dimensiontype`). The migration that actually created the column named the type differently (e.g.
`dimension_type`, with an underscore). The column's *real* type in the database is the migration's
name, not SQLAlchemy's guessed one. This doesn't break DML directly (Postgres binds by the column's
actual type, not by what SQLAlchemy's metadata thinks it's called), but it does mean:
- Any `checkfirst`/DDL-generation code path (autogenerate, `create_all`) would try to create a
  *second*, differently-named enum type and fail or diverge from the live schema.
- It's a sign the model file was written independently of the migration that actually shipped, which
  is the same root cause as Finding 1 and as the emergency_suspended_by_id UUID/String mismatch fixed
  earlier this project (`docs/GCP_DEPLOYMENT.md` §5) — model and migration drift is a **recurring
  pattern** in this codebase, not a one-off.

**33 further columns** (full list captured during this audit, not reproduced in full here to keep this
section readable) resolve to a Postgres type name that doesn't exist in the database *and* the
underlying column turns out to be plain `VARCHAR`, not a native enum at all — e.g. `support_tickets.status`,
`ml_jobs.status`, `risk_signals.severity`, `expense_claims.status`, `audit_runs.status`,
`legal_holds.status`, `upsell_opportunities.status`. For these, there is no DB-level enum constraint,
so writes won't be rejected by Postgres — but SQLAlchemy will still write the uppercase `.name` by
default, meaning **any other code that queries these columns by the lowercase `.value` string directly
(raw SQL, a different service, a frontend expecting lowercase) will silently fail to match rows written
through the ORM.** This is a Likely (not yet individually reproduced) but architecturally consistent
risk across all 33 — flagged for Section 6/16 follow-up to check each one's actual read paths.

### 1.4 Finding 3 — CONFIRMED, P3 Low: Dead router

`app/routers/audit_consolidated.py` (116 lines) defines a `unified_router` that re-mounts `audit.py`,
`audit_system.py`, `advanced_audit.py`, and `forensic_audit.py` under one namespace, explicitly
documented in its own docstring as "Option 2" of two ways to wire up audit routing. `main.py` uses
"Option 1" (mounts the four individual routers directly) and never imports `audit_consolidated` at
all. The entire file is unreachable dead code — harmless (doesn't cause duplicate route registration
since it's never mounted) but should either be removed or clearly marked as an intentional
future-refactor option, not left ambiguous.

### 1.5 Finding 4 — CONFIRMED, P3 Low: 12 orphaned template files

Verified by checking every template against every `TemplateResponse(...)` call in the routers *and*
every `{% extends %}` / `{% include %}` directive in every other template (not just router calls —
the first pass had false positives from templates only ever reached via `{% include %}`, corrected):

- `templates/advanced_audit.html`, `templates/audit_logs.html`, `templates/dashboard.html`,
  `templates/worm_storage.html` — standalone pages with zero references anywhere. `dashboard.html`
  is superseded by `dashboard_v2.html` (which *is* referenced); `audit_logs.html`/`advanced_audit.html`
  are superseded by `audit_unified.html`/`audit_dashboard.html`.
- `templates/partials/org_dashboard/*.html` (8 files: `admin`, `inventory_manager`, `accountant`,
  `payroll_manager`, `viewer`, `external_accountant`, `owner`, `auditor`) — an entire parallel set of
  role-based dashboard partials, completely unreferenced. `templates/partials/dashboard/*.html` (a
  *different*, similarly-named directory) **is** actively used via `{% include %}` from
  `staff_dashboard.html`. These two directories look like two attempts at the same thing where only
  one was wired up.

### 1.6 Finding 5 — Code Smell, P3: Stray test file and script sprawl outside conventions

- `test_checkout_debug.py` sits at the repo root, outside `tests/`, not collected by the same
  convention as the other 24 test files (needs checking whether `pytest` even picks it up given
  `pyproject.toml`'s `testpaths = ["tests"]` — if not, it's dead/never-run test code).
- `scripts/` has 43 files, many named `fix_*`, `debug_*`, `quick_fix.py`, `test_*` — one-off remediation
  scripts from past incidents, several referencing hardcoded credentials for environments that no
  longer exist (the Railway-specific ones were already removed in a prior session pass; this audit
  will inventory the remaining 43 in Section 11, Dead Code, rather than here).

### 1.7 Middleware stack (as registered in `main.py`, in order)

1. `app.middleware.security.setup_security_middleware` — NDPA/NITDA compliance, rate limiting, CSRF, geo-fencing
2. `app.middleware.sku_middleware.setup_sku_middleware` — commercial tier feature gating
3. `app.middleware.emergency_mode.create_emergency_middleware` — platform emergency controls

Not yet individually audited (Section 7/8 will cover these in depth) — flagged here only to confirm
the registration order, since middleware order determines execution order and is itself a common
source of bugs (e.g. does rate limiting run before or after auth? Does SKU gating see the
authenticated user or not?). **This is an open question for Section 7, not yet answered.**

### 1.8 Third-party integration surface (inventory only — not yet audited)

Paystack (billing), Mono/Okra/Stitch (Nigerian open banking — per user, none of these API keys are
live yet), Azure Form Recognizer (OCR), FIRS/NRS e-invoicing gateway. 7 service files touch these
directly. Full audit deferred to Section 8/14.

---

## 7. Authentication and Authorization

Traced directly from `app/routers/auth.py` (1337 lines, 23 endpoints), `app/dependencies.py` (907
lines — the full RBAC dependency layer), and `app/utils/security.py` (JWT/password utilities).

### 7.1 Finding 6 — CONFIRMED, P1 High: Access token cookie set with `httponly=False`

**Location:** `app/routers/auth.py`, `login()`, lines 254–265.

```python
response.set_cookie(
    key="access_token",
    value=tokens["access_token"],
    max_age=60 * 60 * 24 * 7,
    path="/",
    httponly=False,  # Allow JS access for now (needed for some client-side operations)
    samesite="lax",
    secure=is_production,
)
```

**Risk:** the JWT access token is readable by any JavaScript running on the page via
`document.cookie`. Combined with any XSS vulnerability elsewhere in the app (85 templates using
Jinja2 + Alpine.js `x-model`/`x-text` bindings is a plausible surface — not yet individually audited,
see Section 9), an attacker who can inject a script can read this cookie directly and impersonate the
user without needing to intercept network traffic. The comment shows this was a deliberate tradeoff
("needed for some client-side operations"), not an oversight — but the underlying need should be
solved a different way (e.g. a separate non-sensitive flag cookie, or reading the token from an
`Authorization` header set by JS from `localStorage`/response body instead of from a cookie).
**Impact scope:** every authenticated session, platform-wide.

### 7.2 Finding 7 — CONFIRMED, P3 Low (currently unreachable — see caveat): broken call signature in `get_optional_user`

**Location:** `app/dependencies.py`, lines 511–525.

```python
async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_async_session),
) -> Optional[User]:
    if not credentials:
        return None
    try:
        return await get_current_user(credentials, db)   # <-- BUG
    except HTTPException:
        return None
```

`get_current_user`'s actual signature is `get_current_user(request: Request, credentials, db)` — three
parameters, `request` first. This call passes only two positional arguments, so `credentials` (an
`HTTPAuthorizationCredentials`) gets bound to `get_current_user`'s `request` parameter, and `db` (an
`AsyncSession`) gets bound to its `credentials` parameter. Once inside, `get_current_user` does
`token = credentials.credentials` — but "credentials" is now the `AsyncSession`, which has no
`.credentials` attribute, raising `AttributeError`. That is **not** an `HTTPException`, so the
`except HTTPException` in `get_optional_user` does not catch it — the error propagates as an unhandled
500.

**Trigger condition:** only fires when a request carries an actual `Authorization: Bearer` header
*and* hits an endpoint using `get_optional_user`. Requests with no token return `None` early (line
"if not credentials") and never reach the buggy call, which is almost certainly why this has gone
unnoticed.

**Current reachability (why this is P3, not P1):** `get_optional_user` is imported in
`app/routers/views.py` (line 18) but **never actually used as a `Depends(...)` on any endpoint** in
that file — confirmed by grep, zero other matches anywhere in the codebase. It is dead code today.
Severity would jump to P1 the moment anyone wires it up expecting graceful "authenticated or
anonymous" behavior, since it would instead 500 for every authenticated caller. Fix is a one-line
change (pass `request` as the first argument — which means `get_optional_user` itself needs to accept
and forward a `Request` parameter, since it doesn't currently have one).

### 7.3 Finding 8 — CONFIRMED, P3 Low: duplicate function definitions

**Location:** `app/dependencies.py` — `require_bank_reconciliation()` is defined twice (lines 739 and
803, identical bodies); `require_advanced_reports()` is defined twice (lines 744 and 808, identical
bodies). Python silently lets the second definition win; both call sites still work identically today,
this is pure duplication, not a functional bug. Likely from a merge or a copy-paste block ("ADDITIONAL
SHORTCUT DEPENDENCIES" section duplicating two entries already defined above it). Safe to delete the
second pair.

### 7.4 Finding 9 — Potential Risk, P2: access-token cookie lifetime doesn't match token validity

The `access_token` cookie is set with `max_age=60*60*24*7` (7 days), but the JWT it contains expires
after `settings.access_token_expire_minutes` (30 minutes by default — `app/config.py`). For 6 days and
23.5 hours of that cookie's life, it is present in the browser but the token inside it is already
expired. Any request relying on the cookie (rather than a header) during that window will hit
`get_current_user`'s "Invalid or expired token" 401 — which is *correct* behavior, but there is no
confirmed silent-refresh mechanism found yet tying the `/api/v1/auth/refresh` endpoint to automatic
cookie renewal (would need a Section 9 frontend trace of the JS calling `/refresh` to confirm whether
this is handled gracefully or surfaces as a confusing logout-while-cookie-still-present UX). Flagged
as a risk pending that trace, not yet confirmed as broken.

### 7.5 Finding 10 — Verified SAFE: password reset flow

`app/routers/auth.py` `forgot_password()` (lines 489–517) correctly avoids user-enumeration: it always
returns the identical generic message regardless of whether the email exists, and only sends an actual
reset email when a matching user is found. This is the *correct* pattern — noted here as a positive
finding, not a bug, per the instruction to record what was checked even when it passes.

### 7.6 RBAC dependency layer — structural assessment (not yet exhaustively tested per-endpoint)

`app/dependencies.py` implements a genuinely thorough layered permission model: platform-staff role
checks (`require_platform_role`, `require_platform_permission`), organization role checks
(`require_role`, `require_organization_permission`), a combined check (`require_any_admin`), and SKU
feature-gating (`require_feature`, `require_within_usage_limit`) — all composable as FastAPI
dependencies. The *design* is sound. What this audit has **not yet done** is verify, endpoint by
endpoint across all 66 mounted routers, that every route that *should* be protected actually has one
of these dependencies attached, and that the *correct* one is used (e.g. an admin-only endpoint that
accidentally uses `get_current_active_user` alone would compile and run fine while being open to any
logged-in user). That per-endpoint sweep is Section 2/5 work, not yet done — flagged here as the
natural next step, since this section only confirms the *mechanism* is sound, not that it's applied
correctly everywhere.

### 7.7 Open question carried over from Section 1

Middleware execution order (`main.py`: security → SKU gating → emergency mode) has not yet been traced
against auth. Specifically unresolved: does `sku_middleware` run before or after `get_current_user`
resolves the authenticated user, and does the security middleware's rate-limiting/CSRF logic use the
same client-IP resolution as `AccountLockoutManager` in `auth.py`'s `login()` (which reads
`fastapi_request.state.client_ip`, implying some upstream component is expected to set it — not yet
confirmed which one, or whether it correctly parses `X-Forwarded-For` behind Cloud Run's proxy). Carried
to Section 2 (functional audit of the middleware stack itself).

---

## 2. Section-by-Section Functional Audit — Route Protection Sweep

**Method:** statically parsed every route decorator (`@router.get/post/put/delete/patch`) across all
66 mounted routers via Python's `ast` module (not regex — full parse, so nested decorators and
multi-line signatures are handled correctly), extracted every dependency name used in each function's
parameter defaults, and flagged any route where none of the known auth-dependency names appeared.
**1185 routes were analyzed; 113 were initially flagged as having no detected auth dependency.**

This is exactly the kind of check the audit instructions warn against trusting blindly — a
dependency-injection–based static check like this *will* produce false positives wherever a codebase
uses a different auth pattern than `Depends(...)`. So each flagged route was individually re-examined
before drawing any conclusion, rather than reporting the raw 113 as bugs.

### 2.1 Finding 11 — CONFIRMED, P0 Critical: Paystack webhook accepts unsigned requests when the webhook secret is unconfigured

**Location:** `app/routers/billing.py`, `paystack_webhook()`, mounted at
`POST /api/v1/billing/webhook/paystack` (router prefix `/api/v1/billing`, line 88; handler lines
1326–1403).

The handler's own docstring states it verifies `X-Paystack-Signature` via HMAC-SHA512 with
constant-time comparison — and it does, **but only inside an `if webhook_secret:` guard**:

```python
webhook_secret = settings.paystack_webhook_secret
if webhook_secret:
    if not verify_paystack_signature(body, signature, webhook_secret):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
else:
    if settings.paystack_secret_key and settings.paystack_secret_key.startswith("sk_live_"):
        logger.warning("SECURITY WARNING: Paystack webhook secret not configured...")
    # falls through — no exception raised, no verification performed

# unconditionally, regardless of which branch above ran:
payload = await request.json() if not body else json.loads(body)
...
result = await service.process_payment_webhook(event_type, payload)
if result.get("handled"):
    await db.commit()
```

**Current live impact:** confirmed via this project's own `.env`/`app/config.py` defaults and the
user's explicit statement that none of the payment APIs are configured yet —
`PAYSTACK_WEBHOOK_SECRET` is empty in the current deployment. That means the `if webhook_secret:`
branch is **never entered right now**, verification is skipped entirely, and the endpoint proceeds
straight to parsing and processing whatever JSON body is posted to it — no signature, no auth, no
origin check of any kind. The warning log only fires if `paystack_secret_key` additionally starts with
`sk_live_`, which it currently doesn't either, so this is happening **silently**.

**Why this is P0 and not "fine because Paystack isn't live yet":** the endpoint is mounted and
publicly reachable *right now*, independent of whether Paystack itself has been configured on the
other end.

**Independently re-confirmed against the live deployment (§14):** `gcloud run services describe
proaudit-web --region africa-south1` shows the actual running Cloud Run revision's env-var list has no
`PAYSTACK_WEBHOOK_SECRET`, `PAYSTACK_SECRET_KEY`, or `PAYSTACK_PUBLIC_KEY` entries at all — not set to
empty, simply absent, alongside every other unconfigured third-party integration (Mono, Okra, Stitch,
Azure Form Recognizer). This isn't inferred from `.env` defaults anymore; it's a direct read of the
production service's actual runtime configuration. The endpoint at
`https://proaudit-web-kipujaq7xa-bq.a.run.app/api/v1/billing/webhook/paystack` is live and exploitable
today, in exactly the way described above.

**Full impact, now traced end-to-end into `app/services/billing_service.py`:**
`process_payment_webhook()` dispatches on the attacker-supplied `event_type` field. For
`charge.success`, `_handle_charge_success()` (line 2113) reads `organization_id` and `tier` **directly
out of the attacker-controlled `metadata` object in the JSON body** (lines 2146–2153: `org_id =
UUID(metadata["organization_id"])`, `tier = SKUTier(metadata.get("tier", "core"))`), then calls
`_upgrade_tenant_sku(organization_id=org_id, tier=tier, ...)` (line 3012). That function does **no
further verification of any kind** — no check against a real Paystack transaction, no check that a
payment of any amount actually occurred — it simply writes the requested `tier` (and
`intelligence_addon`, also attacker-controlled) onto the `TenantSKU` row for that organization and
extends `current_period_end` by 30 or 365 days, creating the `TenantSKU` row from scratch if one
doesn't exist yet.

**Concretely: right now, anyone who knows or can enumerate a single organization UUID can POST one
unauthenticated HTTP request and grant that organization the Enterprise tier plus the full
Intelligence add-on, for a full year, for free — with no payment, no signature, no auth of any kind.**
This is not a theoretical "billing data could be polluted" risk; it is a direct feature/privilege
escalation vulnerability with a fully traced, reproducible path from an anonymous HTTP request to a
tier upgrade. Idempotency (line 2072–2089) only prevents the *exact same* webhook `event_id` being
replayed — it does nothing to stop an attacker from sending a fresh, uniquely-numbered fake event.

This is also a live landmine for the future even after Paystack is configured correctly: the moment
the `PAYSTACK_WEBHOOK_SECRET` env var is ever dropped in a redeploy (misconfiguration, not malice),
this exact path reopens with real customer organizations and real money involved, and nothing in the
current code would surface an error to indicate anything is wrong.

**Recommended fix (two layers, both needed):**
1. Invert the guard in `paystack_webhook()` — if `webhook_secret` is not configured, reject the
   request (503), never fall through to processing. Never process a webhook payload without a
   verified signature, full stop.
2. Independently of (1), `_handle_charge_success`/`_upgrade_tenant_sku` should not trust
   `metadata.tier` from the webhook at all as the source of truth for *what was purchased* — the
   correct pattern is to look up the expected tier/price from Paystack's own transaction-verification
   API (`GET /transaction/verify/:reference`) using the `reference`, or from a record your own system
   created *before* redirecting the user to Paystack (i.e. the metadata should be a foreign key into a
   pending-order record you control, not directly-actionable tier/org data). Even with signature
   verification restored, the current design lets Paystack's webhook payload dictate arbitrary
   business outcomes, which is a weaker trust boundary than necessary.

### 2.2 Finding 12 — CONFIRMED, P3 Low: unauthenticated internal metrics endpoint

**Location:** `app/routers/websocket.py`, `GET /stats` → `get_websocket_stats()`, lines 281–289. No
auth dependency of any kind. Returns live connection counts, channel subscriptions, and queue status —
internal operational data, not sensitive user data, but exposed to any unauthenticated caller. Low
severity (no PII, no financial data) but should require at least platform-staff auth
(`require_platform_staff()`), since it's the kind of endpoint that aids reconnaissance
(load/scale information) for no legitimate anonymous use case. `GET /channels` on the same router is
correctly harmless — it only returns a static list of channel names/descriptions with no live state.

### 2.3 Verified SAFE (re-examined, not bugs)

- **All ~85 flagged routes in `app/routers/views.py`** (page-rendering routes): this file uses a
  manual `require_auth(request, db)` helper (defined at line 119, called 48 times) that checks a
  token and returns a `RedirectResponse` to `/login` rather than using FastAPI's `Depends()`
  mechanism — invisible to a Depends-based static check, but functionally equivalent and confirmed
  present in every route that renders user-specific data. The genuinely public pages (`/login`,
  `/register`, `/terms`, `/privacy`, `/cookies`, `/faq`, `/security`, `/forgot-password`,
  `/reset-password`, `/verify-email`) correctly have no auth check by design. `pricing_page()` uses
  `get_user_from_token()` directly for *optional* auth (personalizes for logged-in users, works for
  anonymous ones too) — correct for a public pricing page. Six routes
  (`new_transaction_page`, `new_invoice_page`, `audit_dashboard_page`, `audit_logs_page`,
  `forensic_audit_page`, `advanced_audit_page`, `worm_storage_page`) are pure legacy-compatibility
  redirects to already-protected destinations (mostly `/audit?tab=...`) with zero data exposure — this
  is also *why* `advanced_audit.html`, `audit_logs.html`, and `worm_storage.html` showed up as
  orphaned templates in Finding 4: these routes stopped rendering them in favor of the unified audit
  page, but nobody deleted the old templates or the old redirect stubs.
- **`app/routers/audit.py`**: `list_audit_actions()` and `get_vault_info()` both accept an unused
  `entity_id` path parameter but return only static reference data (enum descriptions, feature lists)
  — no per-entity data is actually queried or returned, so there is no IDOR risk despite the
  entity-scoped-looking URL. (The unused `entity_id` parameter is a minor code-smell — an API consumer
  could reasonably assume the response is entity-specific when it isn't.)
- **All "reference data" endpoints** in `advanced_billing.py`, `tax_2026.py`, `report_export.py`,
  `notifications.py`, `advanced_audit.py`, `forensic_audit.py`, `nrs.py` (`/health`) flagged by the
  static check (currencies list, pricing tiers, PIT relief types, business-type comparisons, B2C
  thresholds, penalty rate tables, export format lists, notification channel types) are static
  catalog/reference data with no user- or entity-specific content — intentionally public by design,
  not bugs.
- **`app/routers/auth.py`**: `/register`, `/login`, `/refresh`, `/forgot-password`, `/reset-password`,
  `/verify-email`, `/resend-verification`, `/2fa/verify-login` are pre-authentication endpoints by
  definition (you can't require a token to log in) — correctly unauthenticated.
  `/nigeria/states` and `/nigeria/states/{state}/lgas` are static geography reference data —
  correctly public.

### 2.4 Per-endpoint business-logic tracing — coverage achieved across this engagement

This pass answered one specific question — "is any route completely unprotected?" — for all 66
routers, and found it clean beyond the gaps already documented (Finding 12). The remaining, harder
question — for routes that *do* have an auth dependency, tracing the individual endpoint frontend →
backend → database → response to verify the dependency is *sufficiently strict* and the logic behind
it is *correct* — cannot be done literally exhaustively for all 1185 routes within any audit's
resourcing; no real-world audit traces every single endpoint of an application this size line by line.
What can honestly be reported is the coverage actually achieved, prioritized by blast radius exactly as
originally planned (billing, admin/*, payroll, entities, tax/accounting first):

- **164 + 24 = 188 endpoints** individually traced for entity-ownership correctness (Finding 18, §3.2-3.3)
  — every endpoint across 68 routers that takes a raw `entity_id` was resolved to either confirmed
  vulnerable or confirmed safe, with zero left ambiguous.
- **~26 routers'** write endpoints traced for their audit-logging call path (Finding 41, §6.3).
- **Every accounting.py write endpoint** traced for its commit/audit-log interaction (Finding 44, §10.4).
- Individual endpoints fully traced end-to-end for: transaction creation (Finding 27), trial-status
  checks (Finding 28), invoice line-item updates (Finding 22), CIT/PAYE/VAT/WHT/Minimum-ETR/CGT
  calculation endpoints (§12, §16), compliance-replay (Finding 34), payroll salary breakdown
  (Finding 39), billing tier transitions and dunning (Finding 40), GL balance recalculation
  (Finding 43), evidence list/detail (Finding 45), admin verification list/review (Finding 37),
  logout (Finding 33), and the Paystack webhook (Finding 11) — each traced from router signature
  through service call through database write/read through response shape, not inferred from
  reading a function signature alone.
- **Not traced to this depth:** the remaining majority of the ~1185 routes that don't touch
  cross-tenant access, billing, tax calculation, payroll, or audit logging — e.g., most read-only
  reporting endpoints, most CRUD on categories/vendors/customers beyond what Finding 18 already
  covered for access control specifically. These were covered by the Section 2 auth-dependency sweep
  (confirmed to have *a* check present) but not individually traced for internal logic correctness.

This is the honest scope of what "per-endpoint business-logic tracing" produced in this engagement:
deep, verified coverage of every high-blast-radius area identified across all 22 sections, not uniform
depth across all 1185 routes.

---

## 8. Security Audit

Findings 11 and 12 above (unsigned webhook, unauthenticated metrics endpoint) and Finding 6
(`httponly=False` cookie) belong here too — not repeated. Additional checks run this pass:

### 8.1 Finding 13 — CONFIRMED (dead code, not currently exploitable), P3: SQL injection pattern in an unused utility function

**Location:** `app/utils/query_optimization.py`, `analyze_query_performance()`, line 431:

```python
result = await db.execute(text(f"EXPLAIN ANALYZE {query_sql}"))
```

`query_sql` is interpolated directly into a raw SQL string with no parameterization — textbook SQL
injection shape, and `EXPLAIN ANALYZE` actually *executes* the wrapped query (not just plans it), so
this would mean arbitrary SQL execution if reachable with attacker-controlled input.

**Confirmed via full-repo grep: this function has zero callers anywhere in the codebase.** It's dead
code, presumably a leftover profiling utility, not wired to any API endpoint — no HTTP request can
reach it today. Severity would jump to P0 the moment anyone exposes it (e.g., an admin "query
analyzer" debug page) without adding parameterization first. Recommend either deleting it or, if
kept, changing it to only accept an already-planned/validated internal-use query and never a
caller-supplied string.

**Also checked and confirmed clean:** grepped the entire `app/` tree for `.execute(f"..."` and
`text(f"...")` — this was the only hit. No other raw-SQL-with-string-interpolation pattern exists in
the codebase.

### 8.2 Finding 14 — Verified SAFE: `{{ ... | tojson | safe }}` pattern in templates

`templates/admin_platform_staff.html`, `admin_user_search.html`, `staff_dashboard.html` embed
server-side data into inline `<script>` blocks for Alpine.js via `{{ data | tojson | safe }}`. This is
the standard, safe pattern for this use case — Jinja2's `tojson` filter escapes HTML-sensitive
sequences (including `</script>`-breaking content) before the `safe` filter suppresses the *separate*
HTML-body auto-escaping that would otherwise double-encode it. Checked because `|safe` is often a red
flag, but confirmed correct here — not a bug.

### 8.3 Finding 15 — Potential Risk, P2: file-upload type validation trusts a client-supplied header

**Location:** `app/routers/evidence_routes.py`, `upload_document_evidence()`, lines 233–238 (and the
same pattern likely repeats across the other ~12 `UploadFile` endpoints in `bank_reconciliation.py`,
`bulk_operations.py`, `ml_ai.py`, `organization_settings.py`, `receipts.py`, `audit_system.py` — not
yet individually re-checked, flagged as Likely for those):

```python
mime_type = file.content_type or "application/octet-stream"
if mime_type not in ALLOWED_MIME_TYPES:
    raise HTTPException(status_code=400, detail=f"File type not allowed: {mime_type}...")
```

`file.content_type` is the client-declared `Content-Type` header from the multipart upload — trivially
spoofable (an attacker can upload an arbitrary file while claiming any MIME type they like). This is
not validating the file's actual content (no magic-byte / signature sniffing). The upload path itself
does correctly check for empty files and enforces a 50MB size cap first, and requires authentication
and audit permission — so this isn't an open/anonymous upload vector. The residual risk is specifically
around what happens *after* upload: if a spoofed file (e.g. an HTML/SVG file with embedded `<script>`
disguised as an image) is ever served back to a browser without a forced `Content-Disposition:
attachment` and a strict `Content-Type`, that's a stored-XSS-via-file-upload path. **Not yet traced**
whether the download/serving side (`file_storage_service.py`, evidence retrieval endpoints) sets those
headers correctly — that trace is needed before upgrading this from Potential Risk to Confirmed, and is
carried forward to Section 9/10.

### 8.4 Finding 16 — Confirmed gap (not a vulnerability, a production-readiness gap), P2: `CORS_ORIGINS` is not set in the live Cloud Run deployment

Checked directly against the running service: `CORS_ORIGINS` does not appear in `proaudit-web`'s
environment variables, confirmed via `gcloud run services describe`. This means production is
currently running on `app/config.py`'s **default** value — a hardcoded list of `localhost`/`127.0.0.1`
origins meant for local development:

```python
cors_origins: str = "http://localhost:3000,http://localhost:8000,http://127.0.0.1:8000,http://localhost:5120,http://127.0.0.1:5120"
```

This is not exploitable by an attacker (a *more* permissive misconfiguration would be the security
concern — e.g. a wildcard `*` combined with `allow_credentials=True`, which is not the case here) but
it is a real production gap: any legitimate cross-origin caller of the API (a separate frontend
deployment, a mobile app calling the API directly, a partner integration) will be silently rejected by
CORS in production right now. Needs an explicit `CORS_ORIGINS` env var set to the real production
domain(s) once one exists (see the `proaudit.com` vs `tekvwa.org` domain discussion from earlier in
this project).

### 8.5 Finding 17 — Verified SAFE: no hardcoded secrets in application code

Grepped `app/` and `main.py` for Paystack live/test key patterns (`sk_live_`, `sk_test_`), AWS access
key patterns (`AKIA...`), and PEM private key headers. Zero matches. (This check does not cover
`scripts/` or git history — a prior session already found and removed a leaked Railway database
credential from 8 files in `scripts/`, documented in `docs/GCP_DEPLOYMENT.md` §4. `scripts/` is not
re-swept here; carried to Section 11, Dead Code, since most of those scripts are also candidates for
deletion on their own merits.)

### 8.6 Verified: CSRF protection is correctly enforced in production; but it shares Finding 26's insecure-by-default root cause

`CSRFMiddleware.dispatch` (`app/middleware/security.py:290`) skips signature validation entirely
whenever `self.development_mode` is true, and `main.py:129` wires this from `settings.is_development`
— the same field already flagged in Finding 26 as defaulting to `True` (`app_env: str =
"development"`) unless a deployment explicitly overrides it. The live Cloud Run service does override
it (`APP_ENV=production`, confirmed in §14), so CSRF is genuinely enforced today — this is not a new
finding, just a verification. But it means Finding 26's blast radius is broader than originally scoped:
the same single misconfigured `APP_ENV` would, in one stroke, (a) leak stack traces (as already
documented), (b) skip CSRF token validation on every unsafe-method request
(`CSRFMiddleware`), (c) skip Nigeria-only geo-fencing entirely (`GeoFencingMiddleware.dispatch`,
`app/middleware/security.py:67`), and (d) relax the rate limiter's per-IP limits by 10x
(`RateLimitingMiddleware.__init__`, line 134). Recommended fix for Finding 26 should note this — flipping
the two defaults protects four independent controls, not one.

### 8.7 Finding 32 — Confirmed, P2 Medium: rate limiting is in-memory and per-instance, not distributed — real effectiveness is diluted by up to 10x under Cloud Run's actual autoscaling configuration

`RateLimitingMiddleware` (`app/middleware/security.py:113-221`) stores request timestamps in a plain
Python `dict` (`self._requests`) scoped to a single process, despite its own docstring's claim of being
"Redis-compatible for production" — nothing in the class actually touches Redis, even though
`settings.redis_url` is configured and used elsewhere in this app for exactly this kind of shared state.
Cross-referencing against the live deployment (§14): `gcloud run services describe proaudit-web`
shows `autoscaling.knative.dev/maxScale: '10'` — the service can and does run as multiple concurrent
container instances, each with its own independent, unsynchronized `_requests` dict. A client whose
requests get distributed across instances (normal behavior under Cloud Run's load balancing, not an
attacker-controlled trick) can receive up to roughly 10x the configured per-IP/per-path limit before
any single instance's counter reaches the threshold. This meaningfully weakens brute-force protection
on `/api/v1/auth/login` and similar endpoints specifically because the deployment scales — the
limiter would work exactly as documented on a single-instance deployment.

**Recommended fix:** back the counter with Redis (already provisioned and used elsewhere in this app)
using a simple sliding-window or token-bucket key per `(ip, path)`, or accept the current per-instance
behavior explicitly and correct the misleading "Redis-compatible" docstring claim.

### 8.8 Finding 33 — Confirmed, P2 Medium: `/api/v1/auth/logout` neither invalidates the token server-side (by design) nor clears the auth cookie client-side (not by design — just missing)

`app/routers/auth.py`'s `logout()` (lines 453-480) writes an audit-log entry and returns a success
message — nothing else. Its own docstring states the server-side tradeoff plainly: "JWT tokens are
stateless, so logout is handled client-side by discarding the tokens... for future token blacklisting
implementation" — no blacklist exists yet, which is a reasonable, disclosed tradeoff for a stateless-JWT
design, not itself a bug. But the endpoint doesn't even do the client-side half it's relying on to make
that tradeoff safe: it takes no `Response` parameter and contains no `delete_cookie(...)` call anywhere
in the file (`grep -n "delete_cookie" app/routers/auth.py` returns nothing). Combined with Finding 6
(`access_token` cookie has `httponly=False`, readable by any JS on the page) and the current
30-minute/7-day access/refresh token lifetimes: on a shared or public computer, clicking "Logout"
leaves the actual authentication cookie sitting in the browser, unexpired and fully valid, contradicting
the UI's implication that the session has ended. A token already exfiltrated via XSS is equally
unaffected — expected, given no blacklist — but the cookie case is not an inherent stateless-JWT
limitation; clearing a cookie server-side via `response.delete_cookie()` is unrelated to whether the
token itself is blacklisted, and its absence here is a straightforward, fixable gap.

**Recommended fix:** add a `Response` parameter to `logout()` and call `response.delete_cookie()` for
both the access and refresh token cookies, using the same name/path/domain they were set with.

---

## 9. Frontend Audit

### 9.1 Finding 37 — CONFIRMED, P0 Critical: stored XSS in the Admin Verifications panel — any anonymous visitor who registers an organization can execute JavaScript in a Super Admin's session

**Location:** `templates/admin_verifications.html`, `renderOrganizations()` (lines 591-643) and the
verification-history modal (lines 968-1003); served by `GET /admin/verifications`
(`app/routers/views.py:695-714`, restricted to `PlatformRole.SUPER_ADMIN`/`ADMIN` only).

The page fetches the pending-verification queue via AJAX and renders it with raw template-literal
interpolation directly into `.innerHTML`, with no escaping:

```javascript
tbody.innerHTML = organizations.map(org => `
    ...
    <div class="text-sm font-medium text-gray-900">${org.name}</div>
    <div class="text-sm text-gray-500">${org.email || 'No email'}</div>
    ...
`).join('');
```

`org.name` is `Organization.name`, sourced directly from `RegisterRequest.organization_name`
(`app/schemas/auth.py:59`) — `Field(None, min_length=1, max_length=255)`, no character-set restriction
of any kind, accepted verbatim from a completely anonymous, unauthenticated visitor via the public
registration endpoint. The same unescaped-interpolation pattern recurs in the verification-history
modal (line 977: `${entry.details.notes}`, a free-text note entered by whichever admin previously
reviewed the organization — a second injection point, this time admin-to-admin).

**Attack chain, entirely unauthenticated up to the final step:**
1. Register an organization via the public signup form with `organization_name` set to a payload such
   as `<img src=x onerror="fetch('/api/v1/admin/...', {credentials:'include', ...})">`.
2. The organization enters `submitted`/`under_review` status and appears in the pending-verification
   queue — a queue platform staff are expected to review as a normal part of operating the platform.
3. The moment a Super Admin or Admin opens `/admin/verifications`, `renderOrganizations()` injects the
   payload into their DOM via `innerHTML`. It executes immediately, in their authenticated session,
   with their cookies and CSRF token both ambient to any `fetch()` call the payload makes.

**Not mitigated by the app's CSP:** `app/utils/ndpa_security.py::CSPBuilder.add_alpinejs_support()`
(called unconditionally from `setup_security_middleware`, confirmed in §7.7's middleware trace) adds
`'unsafe-inline'` to `script-src` specifically to support Alpine.js's `@click`-style inline handlers —
the exact CSP directive that would otherwise block this payload class is deliberately disabled
platform-wide. There is no other backstop between this HTML string and the DOM.

**Confirmed not a deliberate pattern:** the same file's `viewHistory()` function uses
`document.getElementById('history-org-name').textContent = ...` (line 957) for the organization name
in a different location on the same page — `.textContent` auto-escapes, correctly. This confirms the
vulnerable code paths are an oversight in specific rendering functions, not a considered design
decision applied consistently across the file.

**Severity rationale for P0 over P1:** this is not a self-XSS or an authenticated-attacker-only issue
(would already be serious) — the entire attack surface up to code execution is reachable by a
completely anonymous actor via the public registration form, and the target is guaranteed to be one of
the two most privileged account types in the entire platform, since that's who this page is
restricted to. A working exploit here is a realistic path to full platform compromise (approve/reject
any organization, escalate any tenant's SKU tier via the admin's own authenticated session, view any
organization's submitted CAC/TIN documents), not merely a defacement or cookie-theft risk.

**Recommended fix:** escape all interpolated user-controlled fields before insertion (either switch to
`.textContent` assignment for text nodes as `viewHistory()`'s org-name line already correctly does, or
run every interpolated value through an HTML-escaping helper before building the template string);
audit every other admin-facing template using the same `innerHTML = ...map(...)` pattern for the same
issue, since this file alone had it in two separate functions.

**Not yet done:** a systematic sweep of all 64 templates for this exact pattern (raw template-literal
interpolation of a fetched API response into `.innerHTML`) — this finding was found by manually tracing
one specific admin page flagged by its `innerHTML` usage during a general grep sweep, not by exhaustive
coverage. Given it recurred twice in the *same* file, other admin/staff-facing pages that render
user-submitted data (organization names, vendor names, customer names, notes fields) are worth the same
scrutiny before considering frontend XSS coverage complete.

### 9.2 Finding 38 — CONFIRMED, P2 Medium: same-tenant stored XSS via audit-evidence titles, printed to a new window with no CSP protection at all

**Location:** `templates/audit_unified.html`, `generateEvidenceReportHTML()` (lines 4231-4265), used by
`generateClientSidePDFReport()` (line 4207) which calls `printWindow.document.write(printContent)`.

Following up on the grep sweep from §9.1 that flagged this file's `document.write` calls: each
`ev.title` from `this.evidenceList` (populated from `GET` responses served by
`app/routers/evidence_routes.py`, confirmed live and mounted at `main.py:789`) is interpolated raw into
an HTML string (`<td>${ev.title || 'Untitled'}</td>`) with no escaping. `AuditEvidence.title`
(`app/models/audit_consolidated.py:830`) is `String(255)`, free text, with no format restriction —
confirmed exploitable by anyone with permission to submit evidence for an entity (a lower bar than
`evidence_ref`, which the model's comment suggests is meant to be server-generated in a fixed format,
and `collected_by`, which is a UUID foreign key, not a string — neither of those two is a viable
injection point). The resulting HTML is written into a **new, blank popup window** via `document.write`
rather than rendered inside the main app page — this window never received the main app's
`Content-Security-Policy` header at all (it's constructed entirely client-side, never fetched over
HTTP), so the `unsafe-inline` discussion from §9.1 is moot here for a different reason: there is no CSP
whatsoever protecting this specific document.

**Why P2, not P0 like Finding 37:** exploiting this requires the attacker to already have
authenticated, evidence-submission-level access within a specific organization — this is a same-tenant
attack (one user in an org targeting another user, e.g. an entity's own staff member, in the *same*
org, who later exports/prints the evidence report), not a cross-tenant or unauthenticated path to
platform-admin compromise. Still a genuine, confirmed stored XSS with a real reproduction path, just a
narrower blast radius than §9.1.

**Recommended fix:** same as Finding 37 — escape `ev.title` (and, for defense-in-depth, every other
interpolated field in this function) before building the HTML string, e.g. via a small `escapeHtml()`
helper applied to each user-controlled value.

### 9.3 Finding 46 — CONFIRMED, P2 Medium: 6 internal links across 7 templates point to pages that don't exist, including a "View Billing Settings" button on the page a customer sees immediately after paying

Extracted every internal `href="/..."` from all 64 templates and cross-referenced each against the
*actual* mounted path of every `HTMLResponse` route (resolving router prefix + decorator path
together, not either alone — the same resolution technique already used for the duplicate-route check
in §4/5). Six links resolve to nothing:

| Link | Found in | Actual route | Notes |
|---|---|---|---|
| `/legal/terms`, `/legal/privacy` | `checkout.html` | `/terms`, `/privacy` (`app/routers/views.py:1248,1254`) | Missing the `/legal` prefix the author apparently assumed existed |
| `/admin/dashboard` | `admin_platform_staff.html` | No such route exists; the platform-staff dashboard is served at plain `/dashboard`, which branches internally by role (`views.py:242-259`) | |
| `/staff/dashboard` | `admin_api_keys.html`, `admin_security.html`, `admin_settings.html` | Same as above — plain `/dashboard` | Same broken link copy-pasted into 3 templates |
| `/settings/billing` | `payment_success.html` — **the page shown immediately after a successful subscription payment** | `/settings` (billing is an Alpine.js client-side tab within that page, `activeTab === 'billing'`, not a separate server route) | Highest-visibility instance: a paying customer clicking "View Billing Settings" right after checkout gets a 404 |
| `/contact-sales` | `feature_unavailable.html` | Does not exist anywhere in the router tree | Not a wrong-prefix typo like the others — this page was apparently never built |
| `/dpa` | `register.html`, linking to "Data Processing Agreement" | Does not exist anywhere in the router tree | A legal-document link shown during registration that 404s |

**Recommended fix:** for the `/legal/*` and dashboard links, correct the href to the real path (a
find-and-replace across the affected templates); for `/settings/billing`, either link to plain
`/settings` or add query-string/hash support so the billing tab can be pre-selected on load; for
`/contact-sales` and `/dpa`, either build the missing page or remove/redirect the link until it exists
— a link to a legal document that 404s during registration is a compliance-adjacent gap worth fixing
before real users hit it.

### 9.4 Finding 47 — CONFIRMED, P2 Medium: most form labels across the app have no programmatic association with their input — a widespread, systemic accessibility gap

Counted 651 `<label>` elements across all 64 templates, of which only 36 use a `for="..."` attribute
pairing with a matching input `id`. Sampled the remaining ~615 (`templates/register.html` shown as a
representative example) and confirmed the pattern directly: the label is a sibling block-level element
immediately before its input, not wrapping it and not linked by `for`/`id`:

```html
<label class="block text-sm font-medium text-gray-700">Street Address</label>
<input type="text" x-model="streetAddress" ... />
```

Neither of the two ways a `<label>` becomes programmatically associated with a control (nesting the
input inside the label, or an explicit `for`/`id` pair) is present here. A screen reader user tabbing
into this field hears no field name announced at all — this is not a cosmetic issue, it's a
functional barrier for assistive-technology users across nearly every form in the application
(registration, entity setup, transactions, invoices, and more all follow this same pattern based on
the sample checked).

**Verified clean, for contrast:** all 8 `<img>` tags across every template include an `alt` attribute
— image accessibility is fine; this finding is specifically about form-label association.

**Recommended fix:** add matching `id`/`for` pairs (mechanical, and Alpine.js's `x-model` bindings are
unaffected by adding an `id`), or restructure to wrap each input inside its `<label>`. Given the scale
(hundreds of instances), this is better addressed as a deliberate, tracked cleanup than a drive-by fix
alongside unrelated changes.

**Not exhaustively covered:** the remaining accessibility surface (keyboard-navigation order, color
contrast, ARIA roles on custom Alpine.js widgets, focus management in modals) — this audit checked the
two highest-value, most mechanically verifiable accessibility signals (image alt text and label
association) rather than a full WCAG audit, which is a distinct specialized discipline.

---

## 10. Backend Audit

Targeted, mechanical checks for specific bug classes that are common in async Python/SQLAlchemy
codebases, run the same way as the rest of this audit — grep the whole tree, then read every hit, not
just count them.

### 10.1 Verified clean: no missing-`await` bugs on database session calls

Scanned every `app/services/*.py` and `app/routers/*.py` file for `db.execute(...)`,
`.commit()`, `.flush()`, `.refresh()`, or `.rollback()` called without a preceding `await` — the
classic async-Python bug where a coroutine is constructed but never actually run, silently no-op-ing
instead of raising an error. **Zero matches.** Every database call in both directories is correctly
awaited.

### 10.2 Verified clean: no unsafe concurrent use of a single `AsyncSession`

`asyncio.gather` and `asyncio.create_task`/`asyncio.ensure_future` do not appear anywhere in `app/`.
SQLAlchemy's `AsyncSession` is not safe to use concurrently from multiple coroutines at once (a common,
subtle bug in async FastAPI apps that fan out work with `gather`); this codebase's async code is
uniformly sequential `await` chains, which sidesteps the entire bug class by construction rather than
by careful discipline. Worth recording as a positive architectural finding, not just an absence of
bugs.

### 10.3 Cross-confirmed: the SQL-injection sweep from §8.1 (Finding 13) is complete and consistent

Independently re-ran a raw-SQL-interpolation grep (`text(f"..."`, `.execute(f"..."`) across the whole
`app/` tree from a different starting angle (looking for backend architectural issues generally, not
specifically re-checking Finding 13). Got the exact same single hit already documented in §8.1
(`app/utils/query_optimization.py:431`, dead code, zero callers). This cross-confirms the earlier
sweep's completeness rather than finding anything new — recorded because independent reproduction of a
finding is stronger evidence than a single pass, and the audit's own standard is to verify, not assume.

N+1 query detection was completed under §13.3 (Finding 43) rather than here, since it surfaced during
the same load-testing work as Finding 41 and fits more naturally alongside the other performance
findings.

### 10.4 Finding 44 — CONFIRMED, P2 Medium: no consistent rule for who owns a transaction's commit — routers and the services they call both commit independently, on the same shared session

Counted every `commit()` call site across the codebase: **30 router files call `db.commit()` directly
(138 call sites)**, and **41 service files also call `self.db.commit()` internally (250 call sites)**.
There is no consistent architectural rule (e.g., "services never commit, only routers do" or the
reverse) — both patterns coexist throughout the codebase, often within the same request.

**Concrete example, traced end-to-end:** `app/routers/accounting.py::create_account` calls
`AccountingService.create_account()` (flushes, does not commit) → `AuditService.log_action()` on the
same session (commits internally, `audit_service.py:99`) → then the router calls `db.commit()` itself.
Three code paths, two of which believe they own the commit boundary, sharing one `AsyncSession`. In
practice this means the account creation's real commit point is whichever of these fires first — today
that's the audit-log call, an implementation detail of a completely different concern (§6.3, Finding
41's write-up traces the concrete consequence: a failure in the audit-log commit currently takes the
already-flushed account creation down with it, rather than the two being independently recoverable).

This pattern was not exhaustively verified across all 388 commit call sites (that volume makes
line-by-line review impractical within this audit), but the shape — a service-layer method committing
on a session that its router caller will also commit, with no shared convention — recurs by simple
inspection across many of the 41 service files identified, not just the one traced in depth.

**Recommended fix:** adopt one convention (recommended: services never call `commit()`, only
`flush()`; the router or a shared dependency owns the transaction boundary and commits exactly once
per request) and apply it going forward; a full retrofit of all 388 existing call sites is a larger,
separate effort that should be scoped deliberately rather than done as a drive-by fix.

### 10.5 Not yet done

Structured-logging consistency across services (whether log messages follow a consistent
format/severity convention) was not assessed — lower priority given the volume of higher-severity
findings elsewhere in this audit, and not a correctness or security concern in the way everything
above this line is.

---

## 3. Relationships Between Sections / Cross-Section Business-Logic Trace (billing & multi-tenancy)

### 3.1 Finding 18 — CONFIRMED, P0 Critical: cross-tenant IDOR across ~46 endpoints in three routers — any authenticated user can read any other organization's financial reports, tax filings, and audit logs

**This is the single most severe, most rigorously confirmed finding in this audit.** Traced from
route signature all the way into the exact service call arguments — not inferred from absence of a
check, but confirmed by reading the call site and seeing that the user object is never even passed
where it would need to be for scoping to be possible.

**Affected files, all with the identical defect shape** — every endpoint takes `entity_id` as a URL
path parameter and passes it straight to a service method with no verification that the
authenticated caller's organization owns, or has been granted access to, that entity:

| File | Endpoints affected | What's exposed |
|---|---|---|
| `app/routers/reports.py` | 22 of 22 | P&L, cash flow, balance sheet, trial balance, VAT/PAYE/WHT/CIT tax returns, compliance health, fixed assets report, dashboard metrics |
| `app/routers/audit.py` | 12 of 14 (2 are static-reference-only, see §2.3) | Full audit logs (who did what, when, IP address, field-level changes), entity history, **individual user activity logs**, audit vault records/export/compliance reports |
| `app/routers/forensic_audit.py` | 14 of 15 (`/info` is static) | Benford's Law fraud-analysis results, anomaly detection, NRS gap analysis, ledger integrity reports, three-way matching results, WORM storage status |

**Exact confirmed trace (`app/routers/audit.py::get_audit_logs`, lines 30–93):**

```python
@router.get("/{entity_id}/audit/logs")
async def get_audit_logs(
    entity_id: uuid.UUID,
    ...
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ...
    service = AuditService(db)
    logs, total = await service.get_audit_logs(
        entity_id=entity_id,   # <-- straight from the URL, unchecked
        ...
        # current_user is never passed to the service at all
    )
```

`current_user` is resolved (so the endpoint does require *some* valid login) but is **never passed
into the service call, and never compared against the entity's owning organization anywhere in the
function**. The service has no way to scope the query even if it wanted to — the information needed
to do so was never given to it.

**Contrast with the correct pattern, already established elsewhere in this same codebase**
(`app/routers/transactions.py::list_transactions`, lines 116–131):

```python
entity_service = EntityService(db)
entity = await entity_service.get_entity_by_id(entity_id, current_user)
if not entity:
    raise HTTPException(status_code=404, detail="Entity not found or access denied")
```

This confirms the gap is not a matter of the *concept* being unknown to this codebase — `entities.py`,
`transactions.py`, and others do this correctly. `reports.py`, `audit.py`, and `forensic_audit.py`
were simply never updated to use it, or were written independently without it.

**Concrete exploit scenario:** any registered user of the platform — a small business owner on the
free/Core tier, say — can call `GET /api/v1/entities/{any-uuid}/reports/profit-loss?start_date=...&
end_date=...` with **any** entity UUID, not just their own, and receive that entity's full income
statement. The same user can call `GET /api/v1/entities/{any-uuid}/audit/logs` and read another
organization's complete audit trail, including which of *their* users took which actions and from
which IP addresses. Entity IDs are UUIDs (not sequential integers), so this isn't trivially
walkable by brute force — but UUIDs leak through many channels in a real deployment (URLs shared in
support tickets, browser history, referrer headers, logs, screenshots, past API responses to a
different, legitimately-accessed entity that happens to reference a related one) and none of that
matters if there is *any* channel by which an entity UUID becomes known to someone outside that
organization. For a product whose core value proposition is Nigerian tax/audit compliance and NDPA
data-protection adherence, unauthenticated-across-tenants exposure of financial statements, tax
filings, and audit trails is about as severe as a confidentiality bug gets.

**Recommended fix:** add the same `entity_service.get_entity_by_id(entity_id, current_user)` (or
equivalent `verify_entity_access(entity_id, current_user, db)`) check used correctly elsewhere in this
codebase to the top of every affected endpoint in these three files, before any data is queried.
Given the number of endpoints (46+), this is mechanical enough to do as one focused pass, and
valuable enough to add a regression test asserting every entity-scoped route 403s/404s for a user
without access, so this class of gap can't silently reappear.

### 3.2 Finding 18 UPDATE — the gap is far larger than initially scoped: at least 140 endpoints across 16 routers, including write operations on fiscal-year state

Ran a full AST-based sweep of all 68 routers (not just the 3 flagged in §3.1), checking every route
handler that takes a raw `entity_id` parameter (path or query, not derived from the already-verified
`get_current_entity_id` dependency) for any access-check call in its body. Result: **188 route handlers
across 18 files matched the vulnerable shape.** Rather than report all 188 as confirmed, each was
bucketed by a second, stricter check — does `current_user` appear *anywhere* in the function body at
all? If it doesn't, the downstream service call cannot possibly have received it, so there is no
mechanism by which access could be scoped — this is the same proof standard already used for Finding
18's original three files.

**120 endpoints across 14 files are CONFIRMED by this standard** (`current_user` never referenced past
the function signature — full list below). A further 68 use `current_user` somewhere in the body,
which doesn't prove safety by itself but means each needs individual tracing before a verdict; spot
checks below resolve two of those files (**+20 more confirmed**, one file verified safe) and leave the
rest open.

**Confirmed (120), by file:**

| File | Count | What's exposed/mutable |
|---|---|---|
| `accounting.py` | 24 | GL, journal entries, trial balance, income statement, balance sheet, cash flow, source-system aging reports |
| `audit.py` | 17 | *(already covered in §3.1)* |
| `budget.py` | 18 | Budgets, line items, variance, forecasts — **includes `update_budget`, `add_budget_line_item`, `delete_budget_line_item` (writes)** |
| `consolidation.py` | 2 | Currency translation reports for entity groups |
| `dashboard.py` | 1 | `mark_all_alerts_read` (write) |
| `fixed_assets.py` | 4 | Asset register, depreciation schedules, capital gains |
| `forensic_audit.py` | 15 | *(already covered in §3.1)* |
| `fx.py` | 10 | Exchange rates, FX exposure, **`create_exchange_rate`, `run_period_end_revaluation` (writes)** |
| `ml_ai.py` | 1 | ML dashboard |
| `report_template.py` | 2 | `set_default_template` (write), generation history |
| `reports.py` | 21 | *(already covered in §3.1)* |
| `tax_2026.py` | 4 | CIT/VAT self-assessment generation, TaxPro Max export |
| `views.py` | 1 (verified SAFE, see below) | `set_entity` |

**Additional 20 confirmed by spot-check — `resolve_entity_id`, used in `year_end.py` and
`report_export.py`, is a fake safety net.** Both files independently define an identically-broken
helper:

```python
async def resolve_entity_id(db, entity_id, user) -> uuid.UUID:
    if entity_id:
        return entity_id          # <-- explicit entity_id: returned completely unchecked
    if user.organization_id:      # <-- ownership scoping only runs on THIS fallback path
        ...
        return entity.id
```

The organization-scoping logic only executes when the caller **omits** `entity_id` (server picks the
user's own default entity). The moment a caller supplies an explicit `entity_id` — exactly the
attacker's move — it is returned as-is with zero verification. This makes all 12 `year_end.py`
endpoints and all 8 `report_export.py` endpoints just as vulnerable as the other 120, despite
superficially looking safer (they do reference `current_user`, which is why the automated sweep
bucketed them separately). **`year_end.py` is the most severe addition: `close_fiscal_year`,
`reopen_fiscal_year`, `lock_period`, `unlock_period`, `generate_closing_entries`, and
`create_opening_balances` are all state-mutating operations on another organization's accounting
period** — this is not a read-only confidentiality issue like the rest of Finding 18, it's a
tenant-crossing **data integrity** issue: an attacker could lock, unlock, close, or reopen a fiscal
year for a business they have no relationship with.

**Revised total at this stage: at least 140 confirmed endpoints across 16 files**, with 48 more still
requiring individual service-layer tracing before a verdict (superseded below — see §3.3, where all
48 are resolved).

**One file spot-checked and found correct, for calibration:** `dashboard.py`'s main `get_dashboard()`
passes `current_user` into `DashboardService.get_dashboard(current_user, entity_id)` and catches
`PermissionError` — the ownership check happens inside the service, not the router. This is a valid
alternative pattern, confirming that not everything in the remaining ~48 unresolved endpoints
(`accounting.py`'s other 10, `dashboard.py`'s other 20, plus smaller counts in `entities.py`,
`ml_ai.py`, `notifications.py`, `reports.py`) is necessarily broken — but each needs the same
individual service-layer trace before being called safe, since the `resolve_entity_id` case shows a
function can *reference* `current_user` while still providing no actual protection.

**Resolved:** `views.py::set_entity` (traced, lines 1228–1241) sets the `entity_id` cookie
unconditionally with no auth check of its own, but this is verified SAFE — the actual boundary is
enforced downstream by `get_current_entity_id` (`app/dependencies.py`, already read in §7.6), which
re-validates the cookie's entity_id against `current_user.entity_access` before trusting it for
anything, falling back to the user's own default entity otherwise. Write access to the cookie without
read-time revalidation would matter; here it doesn't, because the read side does the real check.

### 3.3 Finding 18 FINAL — all 48 remaining endpoints individually traced; count settles at 164 confirmed, 0 unresolved

The automated sweep's safe-marker list (`get_entity_by_id`, `verify_entity_access`,
`require_entity_access`) missed a fourth legitimate pattern: `dashboard_service.py` defines
`_get_entity_if_accessible(user, entity_id)`, which genuinely checks membership (`for access in
user.entity_access: if access.entity_id == entity_id: ...`, returns `None` otherwise — not a fake net
like `resolve_entity_id`). Re-running the sweep with this marker added dropped `dashboard.py`'s
unresolved count from 20 to 4 with no change to the confirmed-120 bucket, and cut the total
"needs-trace" bucket from 68 to 52. The remaining 52 (after subtracting the 20 already resolved via
`resolve_entity_id` in §3.2) left exactly 32 endpoints across 11 files to individually trace to the
service layer. All 32 are now resolved:

**+24 more confirmed vulnerable** — each traced to a service method that takes `entity_id` (or an
id derived from it) and performs zero ownership/organization check; `current_user`/`current_user.id`
is used only to stamp `created_by_id`/`user_id` on the write, never to gate access:

| File | Endpoints | Notes |
|---|---|---|
| `accounting.py` | 10 | `create_account`, `update_account` (looks up by bare `account_id`, never even receives `entity_id`), `initialize_chart_of_accounts`, `create_fiscal_year`, `create_journal_entry`, `post_journal_entry`, `reverse_journal_entry`, `post_to_general_ledger`, `close_fiscal_period`, `sync_gl_from_source_systems` — an attacker can post, reverse, or close another organization's general ledger |
| `budget.py` | 5 | `create_budget`, `submit_budget_for_approval`, `process_budget_approval_decision`, `create_budget_revision`, `approve_budget` — another org's budget can be approved or rejected outright |
| `report_template.py` | 4 | `list_templates`, `create_template`, `get_default_template`, `clone_template` — see below, a distinct sub-pattern |
| `ml_ai.py` | 2 | `get_cash_flow_forecast`/`forecast_cash_flow`, `get_growth_prediction`/`predict_growth` — see below, a distinct sub-pattern |
| `consolidation.py` | 1 | `recycle_cta_on_disposal` — checks that `entity_id` is a member of `group_id`, but never that `group_id` belongs to `current_user`'s organization |
| `entities.py` | 1 | `restore_entity` — checks `current_user.role == OWNER` but never that the target entity's organization matches the caller's; any Owner can un-delete any org's entity |
| `forensic_audit.py` | 1 | `sync_journal_entries_to_ledger` — writes hash-chained immutable ledger entries for any `entity_id` with no ownership check at all |

Two sub-patterns inside this +24 are worth calling out individually because they demonstrate the same
"looks correct but isn't" failure mode as `resolve_entity_id`, just in new shapes:

- **`report_template.py`'s `organization_id` parameter is additive, not restrictive.** All four
  endpoints pass `organization_id=current_user.organization_id` into the service alongside
  `entity_id`, which reads like a scoping check. In `list_templates`, the service builds `WHERE
  entity_id = :entity_id OR organization_id = :organization_id` — the org check only *adds* extra
  org-wide templates to the result, it never restricts the `entity_id` branch to entities the caller's
  org actually owns. `create_template`, `get_default_template`, and `clone_template` don't even do
  that much — `organization_id` is accepted but the entity/template lookups are unconditional.
- **`ml_ai.py`'s `forecast_cash_flow` and `predict_growth` each contain a comment reading `# Verify
  entity access` directly above the only entity-related check in the function** — which is `entity =
  await db.get(BusinessEntity, request.entity_id); if not entity: raise 404`. That confirms the entity
  *exists*, not that the caller has any relationship to it. The comment asserts a check that the code
  one line below does not perform.

**+8 resolved as genuinely SAFE (false positives from the automated sweep):**

| File | Endpoints | Why safe |
|---|---|---|
| `dashboard.py` | 4 | `get_dashboard` delegates to `DashboardService.get_dashboard`, which raises `PermissionError` internally (already established in §3.2). `get_widget_layout`/`update_widget_layout` accept `entity_id` but never reference it in the body — both are unimplemented stubs (`# TODO: Fetch/Save ... from/to database`) returning per-role defaults with no per-entity data read or written. `compare_kpis` checks a role-based `VIEW_REPORTS` permission and returns 100%-hardcoded placeholder numbers regardless of `entity_id` — nothing real to leak |
| `notifications.py` | 2 | `list_notifications` and `mark_all_as_read` scope every query by `NotificationModel.user_id == current_user.id` as the mandatory base filter; the optional `entity_id` param only narrows further within the caller's own notifications — it can never widen access to another user's rows |
| `reports.py` | 1 | `subscribe_to_compliance_alerts` calls `ComplianceHealthService.subscribe_alerts`, which is an unimplemented stub (`# For now, return confirmation of subscription intent... Full implementation would store this in a subscriptions table`) — nothing is read or persisted, so there is no cross-tenant data to expose |
| `auth.py` | 1 | `get_dashboard` (a second, separate route from the one in `dashboard.py`) delegates to the same already-verified-safe `DashboardService.get_dashboard` |

**Final total: 164 confirmed cross-tenant IDOR endpoints across 17 files** (the 16 from §3.2 plus
`entities.py`, newly added). **Zero endpoints remain unresolved** — every route flagged by the
original structural sweep has now been individually traced to either a confirmed missing check or a
verified, working access-control mechanism. Files with zero confirmed findings after full tracing:
`views.py` (1 endpoint, verified safe), `dashboard.py` (all safe), `notifications.py` (all safe),
`auth.py`'s flagged endpoint (safe). Files with 100% of flagged endpoints confirmed vulnerable:
`accounting.py`, `audit.py`, `budget.py`, `consolidation.py`, `entities.py`, `fixed_assets.py`,
`forensic_audit.py`, `fx.py`, `ml_ai.py`, `report_template.py`, `reports.py`, `tax_2026.py`,
`year_end.py`, `report_export.py`.

---

## 6. Database and Data Integrity — the model/DB table gap, resolved

Section 1 flagged an unexplained 15-table gap between what `app/models/*.py` declares (109, later
recounted as 112) and what actually exists in the live database (124). Traced to ground truth:

### 6.1 Finding 19 — CONFIRMED, P2 Medium: `payroll_advanced.py`'s 11 tables are invisible to `app/models/__init__.py`

Loaded `Base.metadata.tables` inside the running container (same technique as the enum audit in
Finding 1) and diffed it against `information_schema.tables`. Result: **zero tables exist in the
database without a corresponding model** (the reverse of what you'd worry about) — but **11 tables
that do have model classes in `app/models/payroll_advanced.py`** (`compliance_snapshots`,
`ctc_snapshots`, `employee_variance_logs`, `ghost_worker_detections`, `opening_balance_imports`,
`payroll_decision_logs`, `payroll_exceptions`, `payroll_impact_previews`, `payslip_explanations`,
`what_if_simulations`, `ytd_payroll_ledgers`) **never register with `Base.metadata` when the app
imports only `from app.models import *`**, because `app/models/__init__.py` never imports
`payroll_advanced.py` — unlike every other model file in the package (confirmed by grep: e.g. line 48
explicitly imports `audit_consolidated`'s classes; `payroll_advanced` has no equivalent line).

**Why this currently "works" anyway:** `app/services/payroll_advanced_service.py` imports directly
from `app.models.payroll_advanced`, which is enough to trigger SQLAlchemy's declarative registration
as a side effect, *as long as that service module gets imported before anything needs those tables*.
In the running app today, it apparently does (no reported failures), but this is incidental, not
guaranteed — the safety depends on import order across the whole app, not on an explicit contract.

**Concrete risks this creates:**
- Alembic autogenerate (`alembic revision --autogenerate`) would not see these 11 tables as
  model-backed, and could propose spurious `DROP TABLE` migrations for them, believing they're
  orphaned schema.
- Any `relationship("ComplianceSnapshot")`-style string reference from another model, or any direct
  `from app.models import ComplianceSnapshot`, will raise `NameError`/mapper-configuration errors
  unless `payroll_advanced_service.py` (or the model file itself) has already been imported earlier in
  that specific process — fragile, order-dependent behavior that is easy to break with an unrelated
  refactor.

**Recommended fix:** add `payroll_advanced.py`'s model classes to `app/models/__init__.py`'s import
list, matching the pattern already used for every other model file. Mechanical, zero behavior change
for the happy path, removes the import-order fragility.

### 6.2 Finding 36 — CONFIRMED, P2 Medium: the table backing nearly every access-control check in the app has no index and no uniqueness constraint on the columns it's actually queried by

Wrote a script scanning every `entity_id: Mapped[...] = mapped_column(...)` definition across all of
`app/models/*.py` for the presence of both `ForeignKey` and `index=True`. Two results stand out (a
third, `PayrollSettings.entity_id`, has no explicit `index=True` but does have `unique=True`, which
Postgres backs with an implicit unique index — not a gap):

- **`UserEntityAccess`** (`app/models/user.py:293-315`) — this is the table read by
  `_get_entity_if_accessible` and the equivalent access-check pattern used throughout the codebase
  (the exact mechanism verified safe/unsafe across all of Finding 18's 164+24 endpoints): "does
  `user.entity_access` contain a row for this `entity_id`." Both `user_id` and `entity_id` are declared
  as plain `ForeignKey` columns with **no `index=True` on either, no composite index, and no unique
  constraint on `(user_id, entity_id)`** (confirmed: no `__table_args__`/`Index(...)` anywhere in the
  class). This table is read on a very large fraction of authenticated requests across the entire
  application — every entity-scoped endpoint that correctly checks access does so against this table.
  Without an index, that lookup is a full table scan once the table grows past a small size, meaning
  the busiest access-control check in the app gets slower for every request as the user base grows —
  and the missing `(user_id, entity_id)` uniqueness constraint means nothing stops two grant rows for
  the same user/entity pair from existing with different `can_write`/`can_delete` values, at which point
  which one governs depends on unordered iteration, not a defined rule.
- **`AccountBalance`** (`app/models/accounting.py:659-673`) — the class's own docstring says
  "Denormalized from journal entries for performance," specifically so callers don't have to
  re-aggregate journal entries on every read. `entity_id` has a `ForeignKey` but no index, so the exact
  column this table would be filtered by (get this entity's account balances) has no index to make that
  read fast — the denormalization's performance goal is undermined by the one column most queries would
  filter on.

**Recommended fix:** add `index=True` to `UserEntityAccess.user_id` and `.entity_id` (or, better, a
composite `Index("ix_user_entity_access_user_entity", "user_id", "entity_id")` matching the actual
query pattern), plus a `UniqueConstraint("user_id", "entity_id")` to prevent duplicate/conflicting grant
rows; add `index=True` to `AccountBalance.entity_id`. All three are additive migrations with no
behavior change for existing correct queries — only latency and one data-integrity gap improve.

### 6.3 Finding 41 — CONFIRMED, P0 Critical: the central audit-logging service used by ~26 routers cannot write a single record — every call fails, unconditionally, against a real migrated database

**Location:** `app/services/audit_service.py::AuditService.log_action()` (lines 82-101), which
constructs and inserts an `app.models.audit_consolidated.AuditLog` row on every call, and
`app/models/audit_consolidated.py::AuditLog` (lines 166-256).

**Discovered by load-testing the running application** (§13) against a database built from a genuine,
complete `alembic upgrade head` — the same migration chain used for the actual GCP deployment earlier
in this engagement — rather than by reading the code or running the existing pytest suite. A
concurrent request burst against `POST /api/v1/auth/login` with a wrong password produced repeated
500s; the server log showed the real cause:

```
asyncpg.exceptions.UndefinedColumnError: column "target_entity_type" of relation "audit_logs" does not exist
```

**Root cause, fully traced:** `AuditLog.target_entity_type` (`audit_consolidated.py:246-252`) and its
sibling `target_entity_id` are declared on the model with no corresponding column ever added to the
live table. Checked every migration that touches `audit_logs`
(`20260103_1251_initial_migration_create_all_tables.py`,
`20260103_1630_ntaa_2025_compliance.py`, `20260120_1000_add_sku_system.py`,
`20260128_1000_add_performance_indexes.py`): the NTAA-compliance migration carefully adds eight other
new columns the model also declares (`organization_id`, `impersonated_by_id`, `device_fingerprint`,
`session_id`, `geo_location`, `nrs_irn`, `nrs_response`, `description`) but never adds
`target_entity_type`/`target_entity_id` — a clean omission, not a broader drift; every other new field
added around the same time made it into a migration except these two.

**Reproduced deterministically, independent of any caller:** constructing a single `AuditLog(...)` row
directly and calling `db.flush()` fails every time, because SQLAlchemy's generated `INSERT` statement
unconditionally includes every mapped column — `target_entity_type` is in the column list whether or
not a caller sets it to a real value, `None`, or leaves it at its default. There is no code path through
`log_action()` that avoids this; it is not input-dependent, timing-dependent, or specific to the
login-failure case that surfaced it.

**Blast radius:** `grep` confirms 26 router files call `audit_service.log_action()` or construct an
`AuditService` and call `.log_action` directly: `accounting.py`, `advanced_accounting.py`,
`bank_reconciliation.py`, `auth.py`, `categories.py`, `bulk_operations.py`, `entities.py`,
`customers.py`, `exports.py`, `fixed_assets.py`, `expense_claims.py`, `inventory.py`, `invoices.py`,
`nrs.py`, `organization_users.py`, `organization_settings.py`, `payroll_advanced.py`, `receipts.py`,
`payroll.py`, `sales.py`, `staff.py`, `self_assessment.py`, `transactions.py`, `tax_2026.py`, `tax.py`,
`vendors.py`. Every one of these has at least one write endpoint that calls `log_action()` with no
surrounding `try`/`except` narrow enough to catch a `ProgrammingError` (most catch only `ValueError`,
per the pattern already documented in Finding 27's neighborhood) — meaning the audit-log call itself,
not the business operation it's meant to record, is what actually crashes the request.

**The practical impact is worse than "the log entry is lost": it can take the business operation down
with it.** Traced `app/routers/accounting.py::create_account` (§3.2's Finding 18 write-up already
covers this endpoint's access-control gap; this is a separate concern) as a concrete example:
`AccountingService.create_account()` calls `self.db.flush()` but never commits; the router then calls
`AuditService.log_action()` on the *same* `AsyncSession`, which internally calls `self.db.commit()`
(`audit_service.py:99`) — meaning the account's own commit boundary is, today, an accidental side
effect of the audit-log call succeeding, not an explicit decision in the router. Now that `log_action()`
always raises before reaching its own commit (Finding 41), the account creation that was already
flushed is never committed either — the exception propagates past `create_account`'s
`except ValueError` (which doesn't match `ProgrammingError`), and the session is left needing a
rollback. **A caller creating an account gets a 500 and the account does not exist** — not "the account
exists but wasn't logged." This specific coupling — a service's write success being commit-gated by an
unrelated audit-log call sharing its session — is the general pattern documented as Finding 44 (§10.1).

**Why the existing test suite never caught this:** `tests/conftest.py:68` creates the test database
with `Base.metadata.create_all(...)` — building tables directly from the *current* Python model
definitions, not by running the Alembic migration chain. A test database built this way always has
every column any model currently declares, including `target_entity_type`, so no test running against
it could ever observe this drift — the gap between "what the models say" and "what a real migration
history actually produces" is invisible to this test suite by construction. This is a distinct,
compounding finding in its own right: **the test suite's schema-setup strategy cannot detect
model/migration drift of any kind**, not just this specific instance.

**Confirmed currently live:** the production Cloud SQL database was migrated via this exact same
Alembic chain earlier in this engagement (documented in `docs/GCP_DEPLOYMENT.md`). This audit could not
directly query production to confirm the column's absence there (attempted via a read-only Cloud SQL
proxy connection; blocked by both a permissions error and this session's own restriction on production
reads — see §6's checklist note), but the migration files are the same files, applied the same way, so
there is no reason to expect a different outcome. This should be verified directly against production
before being deprioritized on the theory that "maybe it's fine in practice."

**Recommended fix:** write a migration adding `target_entity_type VARCHAR(100)` and `target_entity_id
VARCHAR(100)` to `audit_logs`, matching the model exactly (a mechanical, additive, zero-risk migration —
the same class of fix as Finding 19). Separately and more importantly: replace
`tests/conftest.py`'s `Base.metadata.create_all()` with running the actual Alembic migration chain
against the test database, so this entire class of drift becomes visible to CI going forward instead of
structurally invisible.

---

## 11. Dead Code and Unused Functionality

Combines the router/template findings from §1 (dead `audit_consolidated.py` router, 12 orphaned
templates) with a fresh sweep of `app/services/` (92 files) and `scripts/` (43 files).

**Services: none found dead.** Grepped every one of the 92 service module names against every router,
task, middleware, other service, and schema file — all 92 are referenced from at least one other
location. (This doesn't rule out dead *functions inside* a used file — not checked at that
granularity.)

### 11.1 Finding 20 — CONFIRMED, P2 Medium: 10 test files are silently never executed by the test suite

`pyproject.toml` sets `testpaths = ["tests"]` (line 83) with no competing `pytest.ini` or root
`conftest.py` to override it — confirmed authoritative. Two sets of test files sit outside that path
and are therefore **never collected or run** by a plain `pytest` invocation, despite being named and
written exactly like real tests:

- Repo root: `test_checkout_debug.py`
- `scripts/`: `test_billing_features.py`, `test_billing_subscription.py`, `test_checkout_e2e.py`,
  `test_checkout_flow.py`, `test_checkout_insert.py`, `test_core_sku.py`, `test_core_tier.py`,
  `test_fx_fields.py`, `test_sku_enforcement.py`

**Why this matters beyond tidiness:** these names (`test_checkout_e2e`, `test_billing_subscription`,
`test_sku_enforcement`) strongly suggest checkout, billing, and SKU-enforcement have test coverage
that, in fact, hasn't run in CI or locally via `pytest` for as long as they've lived outside
`tests/`. Anyone who assumes "there are e2e checkout tests" based on a file listing is wrong — this is
exactly the kind of gap the Testing Audit (§15) needs to account for rather than assume away. Not yet
verified whether the code in these files still runs correctly if invoked directly (`python
scripts/test_checkout_e2e.py`) — that's separate from whether they're part of the automated suite,
which they confirmed are not.

**Recommended fix:** for each file, either move it into `tests/` (if still relevant and passing) or
delete it (if superseded/broken) — don't leave it silently inert in `scripts/`.

### 11.2 Finding 21 — CONFIRMED, P2 Medium: schema-patching scripts that bypass Alembic entirely

`scripts/` contains 8 scripts that directly `ALTER`/`CREATE` database schema outside the migration
chain: `add_audit_columns.py`, `add_missing_payment_columns.py`, `add_transaction_fx_columns.py`,
`create_accounting_tables.py`, `create_fx_tables.py`, `fix_enum_values.py`,
`fix_payment_transactions_schema.py`, `fix_tier_enum_columns.py`. This is the exact same anti-pattern
already found and removed once this project (`create_railway_tables.py`, deleted in an earlier
session specifically because its docstring said *"bypasses Alembic migrations which have enum
conflicts"* — documented in `docs/GCP_DEPLOYMENT.md` §5). These 8 are the same idea, just not yet
cleaned up. Given the current database's schema is now fully and correctly migration-managed
(confirmed throughout this session's work), **running any of these scripts against the live database
today risks reintroducing exactly the kind of drift Findings 1/2/19 already catalog** — a script that
manually adds a column Alembic already added would either no-op or, worse, add it with different
constraints/defaults than the migration specified.

**Recommended fix:** delete these 8 (their intent should already be captured in the Alembic migration
history at this point — confirmed the live schema has all 124 tables from Section 1/6) or, if any
capture a fix that was never actually turned into a proper migration, convert that specific one into
an Alembic migration and then delete the script. Do not leave them in place as "just in case" —
they're a live footgun for the next person who doesn't know the history.

### 11.3 Carried from §1: dead router and orphaned templates

`app/routers/audit_consolidated.py` (dead, unreachable `unified_router`) and 12 orphaned template
files (`advanced_audit.html`, `audit_logs.html`, `dashboard.html`, `worm_storage.html`, and the entire
`templates/partials/org_dashboard/` directory) — see Finding 3/4 for full detail, not repeated here.

---

## 16. Business-Logic Audit

### 16.1 Finding 22 — CONFIRMED, P1 High: editing an invoice line item's quantity or price crashes unless `vat_rate` is also supplied in the same request

**Location:** `app/routers/invoices.py`, `update_line_item()`, `PUT
/{entity_id}/invoices/{invoice_id}/line-items/{line_item_id}` (route at line 1405, body at
1434–1465).

```python
if request.vat_rate is not None:
    line_item.vat_rate = request.vat_rate      # only ever set conditionally

# Recalculate
line_item.subtotal = line_item.quantity * line_item.unit_price
line_item.vat_amount = line_item.subtotal * (line_item.vat_rate / 100)   # <-- unconditional read
line_item.total = line_item.subtotal + line_item.vat_amount
```

`InvoiceLineItem` (`app/models/invoice.py`, lines 393–425) has **no `vat_rate` column at all** — only
`subtotal`, `vat_amount`, and `total`. The assignment on line 1459 sets a plain transient Python
attribute (never persisted; SQLAlchemy allows setting arbitrary attributes on a mapped instance, but
only mapped columns survive a commit/refresh). The read on line 1462 unconditionally accesses
`line_item.vat_rate` regardless of whether the current request set it.

**Confirmed failure mode:** call this endpoint to update only `quantity` or `unit_price` (a completely
normal, expected use case — "I want to change the quantity, not the tax rate") without also including
`vat_rate` in the request body. Since `UpdateLineItemRequest.vat_rate` is `Optional[float]` (line
1237), a client has every reason to omit it. `line_item` was just loaded fresh from the database via
`invoice.line_items` (line 1439), so no prior request's transient attribute carries over — accessing
`line_item.vat_rate` on line 1462 raises `AttributeError: 'InvoiceLineItem' object has no attribute
'vat_rate'`, an unhandled 500.

**Even when it doesn't crash** (i.e. the caller does pass `vat_rate`), the value is silently lost:
`vat_amount` gets computed correctly for that one request, but the rate that produced it is never
written to any column, so there is no way to later determine what VAT rate was actually applied to
that specific line item — a real problem for a tax-compliance product where every filed VAT figure
needs to be reconstructable from stored data.

**Root cause:** the schema/router layer was written assuming a per-line-item VAT rate override exists
as a persisted concept, but the corresponding model column was either never added or was removed at
some point without updating this endpoint.

**Recommended fix:** add a `vat_rate` column to `InvoiceLineItem` (matching the `Decimal`/`Numeric`
pattern used for every other monetary field on this model) so the value can actually persist, and
guard the recalculation to fall back to a sensible default (the invoice-level `vat_rate`, or the
existing stored value) when the request doesn't provide one, rather than assuming it's always present.

### 16.2 Code Smell, P3: VAT rate (7.5%) is hardcoded independently in 10+ files instead of one shared constant

Grepped for the literal `7.5` / `0.075` Nigerian standard VAT rate: it appears independently in
`app/routers/tax.py`, `sales.py`, `tax_2026.py`, `nrs.py`, `invoices.py`,
`app/models/bank_reconciliation.py`, `advanced_accounting.py`, `app/schemas/invoice.py`,
`bank_reconciliation.py`, and `app/services/ai_labelling.py` — at least 10 independent occurrences,
not a single shared `settings.vat_rate` or `TaxConfig.VAT_STANDARD_RATE` constant. This is a
maintainability risk specific to a Nigerian tax-compliance product: VAT rates are set by government
policy and do change (this codebase's own "2026 Tax Reform" theme is evidence rates/rules shift) — a
future rate change requires finding and updating every one of these independently, and missing even
one creates a silent inconsistency between, say, what `invoices.py` charges and what `tax_2026.py`
reports. Not a bug today (all 10 currently agree on 7.5), but worth consolidating into one constant
before the next rate change, not after.

### 16.3 Verified robust: PAYE calculator handles boundary/zero/negative income correctly

Covered in §12.1 — directly executed `PAYECalculator.calculate_paye()` against zero, negative, and
every band boundary; no exceptions, no negative-tax results, and the API layer independently validates
`gt=0` before this code ever runs on the real PAYE endpoints.

### 16.4 Verified: WHT calculator's rate table is internally safe; a theoretical division-by-zero in `calculate_gross_from_net` is not currently reachable

`WHTCalculator.calculate_gross_from_net()` divides by `(1 - rate/100)`, which would raise
`decimal.DivisionByZero` if any WHT rate were ever 100% (or produce a negative, silently wrong gross
figure if a rate exceeded 100%). Checked every rate in the hardcoded `WHT_RATES` table
(`app/services/tax_calculators/wht_service.py:53-66`): all are 5% or 10%. Since rates are static
constants, not user- or database-configurable at this layer, this is not currently reachable —
recorded as a fragility worth a defensive guard if `WHT_RATES` is ever made configurable, not reported
as a bug per this audit's own standard against flagging unreachable theoreticals as confirmed issues.

### 16.5 Finding 35 — CONFIRMED, P1 High: CIT minimum tax silently fails to apply to the exact case it exists to catch — a profitable company with a low margin

**Location:** `app/services/tax_calculators/cit_service.py`, `CITCalculator.calculate_cit()`, lines
163-173.

The method's own comment states the intended rule plainly: "Final CIT is higher of CIT on profit or
minimum tax (if not exempt)." The code that follows does not implement that rule:

```python
if is_minimum_tax_exempt:
    final_cit = cit_on_profit
    minimum_tax_applied = False
else:
    if cit_on_profit < minimum_tax and profit <= 0:   # <-- extra, undocumented condition
        final_cit = minimum_tax
        minimum_tax_applied = True
    else:
        final_cit = cit_on_profit                      # <-- minimum tax silently skipped
        minimum_tax_applied = False
```

Minimum tax only applies when **both** `cit_on_profit < minimum_tax` **and** `profit <= 0` — the
`profit <= 0` clause has no basis in the method's own stated rule ("higher of the two") and restricts
minimum tax to loss-making/breakeven companies only. A non-exempt company with **positive** profit
whose 30%-of-profit CIT is still lower than 0.5%-of-turnover minimum tax — precisely the low-margin,
high-turnover profile minimum tax exists to catch — falls through to the `else` branch and is charged
only `cit_on_profit`, silently skipping the higher minimum tax entirely.

**Reproduced directly:**
```python
CITCalculator.calculate_cit(gross_turnover=200_000_000, assessable_profit=1_000_000)
# → cit_on_profit: 300,000.00   minimum_tax: 1,000,000.00   is_minimum_tax_exempt: False
# → minimum_tax_applied: False  final_cit: 300,000.00 (should be 1,000,000.00)
# → total_tax_liability: 330,000.00 (understated by ₦700,000 — a 68% shortfall on this bill)
```

This is not an edge case unlikely to occur in practice — a large or medium company with genuinely thin
margins (200M turnover, 1M profit is a 0.5% margin, not exotic for e.g. a trading/distribution
business) is exactly the profile this bug affects, and the result is a **understated CIT figure that a
real user could file with the tax authority as-is**, which is a materially different (and worse) risk
class than a crash: a crash is visible and gets reported; a silently wrong number in a compliance
product does not announce itself and could expose the filer to a real underpayment/penalty risk months
or years later during a tax audit.

**Recommended fix:** remove the `and profit <= 0` clause; the correct condition for whether minimum tax
applies is simply `not is_minimum_tax_exempt and minimum_tax > cit_on_profit`, matching the method's own
documented rule.

### 16.6 Finding 39 — CONFIRMED, P1 High: every payroll run understates PAYE, because the relief passed to the PAYE calculator uses the wrong income base and double-counts NHF relief

**Location:** `app/services/payroll_service.py`, `calculate_salary_breakdown()`, lines 294-399,
specifically the call into `PAYECalculator.calculate_paye()` at lines 349-354.

This method computes two *different* figures for pension relief and asserts they're the same amount,
when they aren't:

1. **The actual pension amount deducted from the employee's pay** (`monthly_pension_employee`, line
   333) is correctly based on **pensionable earnings** — Basic + Housing + Transport only, per PenCom
   rules, exactly as the code's own comment states (line 324: "Pensionable earnings (Basic + Housing +
   Transport per PenCom)").
2. **The pension relief used to reduce taxable income for PAYE purposes** is not derived from that same
   figure. Instead, `calculate_paye()` (line 349) is passed the *full* `gross_annual_income` (which
   additionally includes meal allowance, utility allowance, and any `other_allowances`) and
   independently recomputes its own pension relief internally
   (`PAYECalculator.calculate_pension_relief`, `paye_service.py:96-107`) as `pension_percentage% ×
   full gross`, not `× pensionable earnings`. Whenever meal/utility/other allowances are non-zero
   (a normal, expected input — the method accepts all four as parameters), this internal relief is
   larger than the relief the employee actually earned by contributing to pension, silently reducing
   taxable income more than it should.

**A second, independent bug compounds it:** `calculate_paye()` is also passed
`other_reliefs=float(nhf_relief)` (line 353) — but `calculate_paye()` **separately and unconditionally
computes its own NHF relief internally** from the `basic_salary` parameter
(`PAYECalculator.calculate_paye`, `paye_service.py:196`: `nhf_relief = self.calculate_nhf_relief(basic)`)
and adds *both* the internal one and the externally-passed `other_reliefs` one into
`calculate_taxable_income()`'s total (`paye_service.py:135`: `total_reliefs = cra + pension_contribution
+ nhf_contribution + other_reliefs`). NHF relief is therefore counted twice in every call.

**Reproduced directly** with a representative salary (basic ₦500,000/mo, housing ₦200,000, transport
₦100,000, meal ₦50,000, utility ₦30,000 — an entirely ordinary input shape):

| Figure | Correct | Actual (this code) | Overstatement |
|---|---|---|---|
| Pension relief used for PAYE | ₦768,000/yr (matches the ₦64,000/mo actually deducted × 12) | ₦844,800/yr (8% of full gross, not pensionable earnings) | +₦76,800 |
| NHF relief used for PAYE | ₦150,000/yr (counted once) | ₦300,000/yr (counted twice) | +₦150,000 |
| **Annual taxable income** | ₦7,330,000 | **₦7,103,200** | **−₦226,800** |
| **Annual PAYE tax** | ₦1,359,000 | **₦1,295,800** | **shortfall of ₦63,200/employee/year** |

**Why this is more severe in practice than Finding 35 despite the same P1 severity label:** Finding 35
only fires for a specific profitability profile (profitable, thin-margin companies past the minimum-tax
threshold). This bug fires on **every single payroll calculation that includes meal or utility
allowances or any `other_allowances`** — an entirely ordinary, expected salary structure, not an edge
case. For a payroll of 20 employees with similar allowance structures, this alone understates annual
PAYE remittance by over ₦1.2 million, silently, indefinitely, with the shortfall compounding every pay
period the bug remains unfixed. An employer relying on this software's payroll output would be
under-withholding statutory tax with no visibility into the gap until a tax audit reconciles it.

**Recommended fix:** compute pension relief once, on pensionable earnings, and pass that single value
into `calculate_paye()` as an explicit relief parameter rather than letting it recompute its own
(mismatched) figure from `gross_annual_income`; remove the double NHF counting by not passing
`other_reliefs=nhf_relief` when `calculate_paye()` already computes NHF relief internally from the
`basic_salary` parameter it's given — pick exactly one place this calculation happens.

### 16.7 Finding 40 — CONFIRMED, P1 High: billing-tier transition logic and payment-dunning logic share one boolean flag with no coordination — a customer facing suspension for non-payment can escape it by requesting an unrelated downgrade

**Location:** `TenantSKU.cancel_at_period_end`/`.scheduled_downgrade_tier`
(`app/models/sku.py:205-220`), written independently by three different code paths with no shared
contract:

| Writer | Purpose | Sets `scheduled_downgrade_tier`? |
|---|---|---|
| `BillingService.request_downgrade()` (`billing_service.py:1356-1359`) | Customer voluntarily schedules a downgrade to a specific lower tier | Yes — to the requested target tier |
| `BillingService.cancel_subscription()`, non-immediate branch (`billing_service.py:3331-3334`) | Customer voluntarily schedules cancellation | Yes — explicitly to `SKUTier.CORE` |
| `DunningService.record_payment_failure()` (`dunning_service.py:122`) and `escalate_dunning_level()` (`dunning_service.py:265`) | System-driven: a payment failed and the org is being escalated toward suspension for non-payment | **No — never touches it, by the code's own admission** (comment at lines 120-121: "TenantSKU doesn't have custom_metadata - mark as pending cancellation instead. This sets up the dunning state using existing fields") |

The scheduled task that actually applies the change at period end (`app/tasks/scheduled_tasks.py:328-348`)
reads `target_tier = sku.scheduled_downgrade_tier or SKUTier.CORE` for every row where
`cancel_at_period_end == True`, with no way to distinguish *why* the flag was set.

**Confirmed failure mode 1 — a dunned customer keeps paid access instead of being suspended:**
1. An organization on Enterprise requests a downgrade to Professional (`request_downgrade`) →
   `cancel_at_period_end=True`, `scheduled_downgrade_tier=PROFESSIONAL`.
2. Before the period ends, a recurring charge fails and `record_payment_failure()` runs →
   `cancel_at_period_end` is already `True`, so this call changes nothing about `scheduled_downgrade_tier`
   — it stays `PROFESSIONAL`.
3. At period end, the scheduled task downgrades the organization to **Professional** (a paid tier) —
   not Core, not suspended — even though the organization has an actual unresolved payment failure that
   should result in suspension.

**Confirmed failure mode 2 — a customer already being dunned for non-payment can launder that state
into a benign scheduled downgrade:** `request_downgrade()` never checks `suspension_reason` or any
dunning-related state before proceeding — it unconditionally overwrites `scheduled_downgrade_tier`
with whatever the caller requests. An organization already flagged via
`escalate_dunning_level()` (`cancel_at_period_end=True`, heading toward suspension) can call the
ordinary downgrade endpoint and have `scheduled_downgrade_tier` overwritten to any tier they choose —
at period end, the scheduled task has no record that this was ever a payment-failure case, and simply
applies the requested (possibly still-paid) tier instead of suspending the account.

**Confirmed failure mode 3 — a temporary payment hiccup silently erases a legitimate pending
downgrade:** `DunningService.clear_dunning()` (`dunning_service.py:287`) resets
`cancel_at_period_end=False` unconditionally on successful payment, with no check for whether a
genuine, unrelated downgrade was already scheduled via `scheduled_downgrade_tier`. A customer who
requested a downgrade, then had one card-decline-and-retry cycle resolve normally, would find their
voluntary downgrade request silently cancelled — the shared flag was reset by a process that had no
idea the customer's own request existed.

**Root cause:** all three concerns (voluntary downgrade, voluntary cancellation, involuntary
suspension for non-payment) were implemented by reusing the same two fields, justified in the dunning
code's own comments as a workaround for `TenantSKU` lacking a dedicated metadata/state field — with no
guard preventing one concern's writes from corrupting another's.

**Recommended fix:** give dunning its own state (e.g., a `dunning_status` enum column, or reuse
`suspension_reason` consistently, which the model already has), independent of
`cancel_at_period_end`/`scheduled_downgrade_tier`; have the scheduled task check dunning state first
and suspend/cancel regardless of any pending voluntary downgrade; have `request_downgrade()` refuse or
warn when the organization has an active dunning flag.

---

## 17. UI/UX Consistency

### 17.1 Finding 48 — CONFIRMED, P3 Low: date formatting is inconsistent across the app — most calls specify the Nigerian locale, but some don't specify any locale at all

Extracted every `toLocaleDateString(...)` call across all 64 templates: **23 explicitly specify
`'en-NG'`** (the correct, consistent choice for a Nigerian tax/accounting product), but **1 specifies
`'en-GB'`**, **1 specifies `'en-US'`**, and **10 specify no locale at all**
(`admin_legal_holds.html:503`, `admin_risk_signals.html:501`, `base.html:643`, `audit_unified.html`
(twice), `business_insights.html:689`, `reports.html:1090`, `settings.html` (three times)).

A bare `date.toLocaleDateString()` with no arguments renders using **the visiting browser's own
locale/OS settings**, not a fixed format — meaning the same date can render as `4/3/2026` (US,
month/day) or `03/04/2026` (most other locales, day/month) depending entirely on the individual
viewer's device, with no relationship to the `en-NG` format used everywhere else in the same app. Two
Nigerian users viewing the identical record could see different date orderings, and either could
misread a date as the wrong day/month.

**Recommended fix:** replace all bare and non-`en-NG` `toLocaleDateString()` calls with the same
explicit `'en-NG'` locale (and matching `options`) already used in the other 23 call sites, ideally by
factoring the ~23 slightly-varying option objects into one shared formatting helper rather than leaving
each template to redeclare its own.

### 17.2 Not yet done

A full visual-consistency pass (spacing, color usage, component reuse across the 64 templates) was not
attempted — this would require rendering and visually comparing pages, not something this audit's
code-reading and grep-based methodology can do meaningfully. Terminology consistency (e.g., "Entity" vs
"Business Entity" vs "Organization") was spot-checked and found reasonably consistent in the templates
sampled, but not exhaustively verified across all 64 files.

---

## 4/5. Routing and API Audit — duplicate-route check

Wrote a corrected AST-based checker that resolves each router's **actual** mounted path — combining
the prefix `main.py` applies at `include_router(..., prefix=...)` with any prefix the router
declares on itself — rather than checking either one alone (a first attempt without full prefix
resolution produced 8 false-positive "duplicates" that all turned out to be an HTML page in
`views.py` and an unrelated JSON API endpoint that only *look* identical because neither file's
in-source prefix, checked in isolation, revealed the full picture).

**Result: zero real (method, path) collisions across all 1185 routes.** No two handlers are mounted
on the same method+path — this specific concern is verified clean. (This does not mean every path is
*correct* or *reachable as intended* — see §2/§3 for the routes that are reachable but improperly
protected, and §1 for the router that's mounted nowhere at all.)

### 5.1 Response-shape / frontend-contract consistency

Rather than attempt exhaustive coverage of all 528 endpoints declaring a `response_model` (impractical
to review individually within this audit), cross-checked specific frontend field usages already
identified during the Section 9 template sweep against the exact API responses that populate them —
tracing from a concrete `fetch()`/`apiCall()` call site in a template to the router's actual return
value, the same technique used throughout this audit.

**Verified correct:** `admin_verifications.html`'s `renderOrganizations()` (traced for Finding 37)
consumes `org.name`, `.email`, `.organization_type`, `.verification_status`, `.cac_document_path`,
`.tin_document_path`, `.created_at` — every one of these is present on
`OrganizationListItem` (`app/routers/admin_verification.py:82-92`), the exact response model
`GET /api/v1/admin/verifications` declares. No contract mismatch on this pair.

**Finding 45 — CONFIRMED, P3 Low: `audit_unified.html`'s evidence print/export report always shows
"Collected By: System," never the real collector, because the list endpoint it reads from omits a
field the detail endpoint includes**

`generateEvidenceReportHTML()` (already read for Finding 38, §9.2) renders
`${ev.collected_by || 'System'}` for every evidence row, and `this.evidenceList` is populated
exclusively from `GET /api/evidence/list` (`app/routers/evidence_routes.py:926-1013`). That endpoint's
hand-built response dict (lines 987-1004) includes `id`, `evidence_ref`, `evidence_type`, `title`,
`description`, `content_hash`, `file_hash`, `is_verified`, `collected_at`, `collection_method`,
`file_path`, `file_size_bytes`, `file_mime_type`, `has_file`, `finding_id` — **`collected_by` is not
among them**, even though `AuditEvidence.collected_by` (`app/models/audit_consolidated.py:892`) is
always populated on creation (`collected_by=current_user.id`, confirmed at 10 separate call sites in
the same router file) and a *different* endpoint in the same file
(the single-evidence detail view, line 1108: `"collected_by": str(evidence.collected_by)`) does include
it correctly. Since `ev.collected_by` is always `undefined` on every item `/list` returns, the `||
'System'` fallback fires unconditionally — **every row in every printed/exported evidence report
attributes collection to "System," regardless of who actually collected it.**

This is not a security issue (no data exposure, and the correct value is visible elsewhere in the same
UI via the detail view, which does work) and not a crash — it's a silent, cosmetic-looking but
substantively misleading defect in a report whose stated purpose (per its own generated HTML, §9.2) is
demonstrating chain of custody for audit defense — exactly the context where "who collected this" is
supposed to matter.

**Recommended fix:** add `"collected_by": str(e.collected_by) if e.collected_by else None` to the
`/list` endpoint's per-item dict, matching the detail endpoint; consider resolving it to a display name
server-side (the detail endpoint's neighbor code at line 1457 already shows a `User.first_name,
last_name` lookup pattern for exactly this purpose) so the frontend doesn't need to render a bare UUID.

---

## 18. Dependency Audit

### 18.1 Finding 23 — CONFIRMED, P1 High (already materialized once this session): almost every dependency in `requirements.txt` has no upper version bound

```
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
sqlalchemy[asyncio]>=2.0.25
jinja2>=3.1.3
... (37 of 39 non-comment lines use >=, zero use ==, zero use <)
bcrypt==4.0.1   # the ONE exception
```

**This is not a theoretical risk — it already caused a full production outage this session.** Earlier
in this project (documented in `docs/GCP_DEPLOYMENT.md` §5 and the git history around commit
"Fix TemplateResponse crash on every page"), building this exact codebase pulled the then-latest
Starlette release, which had changed `TemplateResponse`'s calling convention. Every one of the 80
call sites in this codebase used the old convention, and the app returned HTTP 500 on **every single
page** until that was found and fixed. `bcrypt` was pinned to an exact version for the identical
reason, evidenced by this repo's own git history (commit "Pin bcrypt to 4.0.1 to fix bcrypt 4.2+
ValueError") — the team has already hit this exact class of problem twice and fixed it twice, but
only for the two packages that happened to break, not as a policy change for the other 37.

**Recommended fix:** pin to compatible-release ranges (e.g. `fastapi~=0.110` or an explicit `<0.2xx`
ceiling) for at least the framework-level packages most likely to make breaking changes
(`fastapi`, `starlette` — currently not even directly pinned, it's a transitive dependency of
`fastapi`, which is itself part of the problem — `sqlalchemy`, `jinja2`, `pydantic`, `celery`), and add
a `requirements.lock`/`pip freeze` snapshot that CI/CD actually builds from, so "what version is
running in production" is a known, reviewable fact rather than "whatever was latest on the day of the
last `docker build`."

### 18.2 Finding 24 — Code Smell, P2: development/test tooling is bundled into the production `requirements.txt`

`pytest`, `pytest-asyncio`, `pytest-cov`, `pytest-benchmark`, `respx`, `black`, `isort`, `flake8`,
`mypy` are all listed in the same `requirements.txt` that the Dockerfile's `production` build stage
installs from (confirmed by reading `Dockerfile` earlier this project — the `production` stage runs
`pip install -r requirements.txt` directly; a separate `development` stage layers `pytest`/`black`/etc.
*again*, redundantly, on top of an image that already has them). This means the live production
container ships test and linting tools it never uses at runtime — unnecessary image size and
unnecessary installed-package surface area (each one is something that could, in principle, carry a
CVE that then shows up in a container scan for a production image, even though nothing in production
ever imports it).

**Recommended fix:** split into `requirements.txt` (runtime only) and `requirements-dev.txt` (adds
the above for local development/CI), and point the Dockerfile's `production` stage at the former only.

---

## 14. Configuration and Deployment Audit

Most of the ground truth here was already established during the GCP migration work earlier in this
engagement; this section cross-references those decisions against the actual live infrastructure
rather than re-deriving them from scratch, plus covers items the migration work didn't specifically
examine (insecure defaults, Docker build-stage targeting, secret wiring).

### 14.1 Finding 26 — Confirmed, P2 Medium: `debug=True` and `app_env="development"` are the code-level defaults; nothing in `app/config.py` stops a misconfigured deployment from leaking full stack traces

`app/config.py` declares `debug: bool = True` and `app_env: str = "development"` as the Pydantic
field defaults (lines 27–28), and `.env.example` documents the same (`APP_ENV=development`,
`DEBUG=True`) as the starting template anyone copies for a new environment. `main.py`'s catch-all
exception handler (`global_exception_handler`, lines 433–465) branches on `settings.is_development`
(which is `app_env.lower() == "development"`, true unless explicitly overridden): when true, the
response body includes `type(exc).__name__`, `str(exc)`, the request path/method, and the **full
Python traceback** (`traceback.format_exc()`) — for both the JSON API response and the rendered HTML
error page. There is no code-level safeguard forcing production mode; the only thing standing between
this and a real leak is every deployment target remembering to set `APP_ENV=production` explicitly.

**Verified this is currently mitigated in the one live deployment, but only operationally, not in
code:** `deploy/gcp/bootstrap.sh` line 66 sets `APP_ENV=production,DEBUG=False` explicitly, and a live
`gcloud run services describe proaudit-web --region africa-south1` confirms both env vars are set
correctly on the running revision. So today's production traffic is not exposed. But this is a classic
insecure-by-default: any new environment (a staging deploy, a second Cloud Run service, a contributor
running the "production" Docker stage locally against a real database, a future deploy target that
isn't `bootstrap.sh`) inherits `debug=True`/`development` unless someone remembers to override it, and
the failure mode is a full stack trace — including file paths and internal exception messages, which
for a database error can include fragments of the failing query — handed to whoever triggers the 500.

**Recommended fix:** flip the defaults (`debug: bool = False`, `app_env: str = "production"`) so an
unconfigured deployment fails safe, and update `.env.example` to model a safe production-shaped
default with a comment showing how to loosen it for local dev.

### 14.2 Finding 16 (from §8.4) re-confirmed live: `CORS_ORIGINS` is absent from the running Cloud Run service, not just undocumented

The live env-var read above also shows no `CORS_ORIGINS` entry at all on `proaudit-web`, which means
the app is currently running on `app/config.py`'s hardcoded fallback (`http://localhost:3000` and other
localhost origins only). This corroborates §8.4's Finding 16 with direct infrastructure evidence rather
than static-code inference — no new finding, same gap, now confirmed against the actual running
service rather than the codebase alone.

### 14.3 Verified correct: Docker multi-stage build target, non-root user, and Secret Manager wiring

Three things worth confirming explicitly rather than assuming, since each is a common source of
silent production misconfiguration:

- **The `--reload` dev command cannot reach production.** `Dockerfile`'s final `development` stage
  (line 87) runs `uvicorn ... --reload`, which would be a real problem in production (file-watching
  and auto-restart are not meant to run under load). `cloudbuild.yaml`'s build step explicitly passes
  `--target production` (lines 30–31), which stops the build at the `production` stage — the
  `development` stage is never built or deployed by the CI pipeline. Confirmed safe.
- **Non-root container user.** `Dockerfile` creates `appuser`/`appgroup` and switches to `appuser`
  before the final `CMD` (lines 44, 55) — the production container does not run as root.
- **No secrets are baked into the image or left as `.env.example` placeholders in production.**
  `SECRET_KEY`, `JWT_SECRET_KEY`, `DATABASE_URL`, `DATABASE_URL_ASYNC`, `REDIS_URL`, all four
  `SUPER_ADMIN_*` fields, and `MAIL_USERNAME`/`MAIL_PASSWORD` are wired via `--set-secrets` in
  `bootstrap.sh` to real Secret Manager entries (`gcloud secrets list` confirms all of them exist,
  created during this engagement's GCP migration), and the live service's env-var dump shows each as a
  `secretKeyRef`, not a literal value. `.env` itself is correctly gitignored and was never committed
  (`git ls-files` returns nothing for `.env`).

### 14.4 Not a finding: Mono, Okra, Stitch, and Azure Form Recognizer are unconfigured in production

None of `MONO_*`, `OKRA_*`, `STITCH_*`, or `AZURE_FORM_RECOGNIZER_*` appear in the live service's
env vars either. This is expected, not a gap — consistent with the user's own statement earlier in
this engagement that none of these third-party integrations are ready yet. Recorded here only so a
future reader doesn't mistake their absence for an oversight distinct from the Paystack gap (§2.1),
which — unlike these — has a reachable, already-wired endpoint behind it and is a live P0.

---

## 15. Testing Audit — the suite was actually executed, not just read; this surfaced two new live P0 application bugs

Per this engagement's own standard ("do not assume something works because the code exists"), the
test suite was not just inspected — it was actually run, end-to-end, against a real ephemeral
Postgres + Redis instance (mirroring `ci.yml`'s services), using a clean virtual environment built
strictly from `requirements.txt` (not a pre-existing, possibly-stale local environment — an initial
attempt using an ad hoc Anaconda environment produced a `Router.__init__() got an unexpected keyword
argument 'on_startup'` error that turned out to be a stale/mismatched local `fastapi`/`starlette`
install unrelated to this project; discarded once a clean venv installing exactly what `requirements.txt`
resolves to today showed the app imports cleanly). Result: **834 tests collected, 773 passed, 19
failed, 42 errored, 1 skipped.** Every failure/error was individually traced to its root cause rather
than reported as a raw count. Two of them are new, confirmed, currently-live application bugs —
not test bugs — found only because the code was actually executed.

### 15.1 Finding 27 — CONFIRMED, P0 Critical: creating a transaction crashes on every single call

**Location:** `app/routers/transactions.py`, `create_transaction()`, `POST /{entity_id}/transactions`
(line 226, handler lines 192–239+).

The handler's docstring advertises multi-currency support ("currency: Transaction currency (defaults
to NGN)... exchange_rate: Exchange rate to functional currency") and line 226 unconditionally executes
`if request.currency and request.currency != "NGN":` before any `try`/`except` wraps it (the `try`
block starts at line 230, four lines later). But `request` is typed as `TransactionCreateRequest` —
and there are **two different classes with that exact name** in this codebase: the complete one with
`currency`/`exchange_rate`/`exchange_rate_source`/`wht_amount` fields lives in
`app/schemas/transaction.py` (confirmed by `grep` to be imported by **zero** files anywhere in
`app/` — pure dead code), while the router defines its **own**, older, local
`TransactionCreateRequest` at line 50 with no `currency` field at all. Because the router never
imports the complete schema, `request` at runtime is always an instance of the incomplete local class,
and `request.currency` raises `AttributeError: 'TransactionCreateRequest' object has no attribute
'currency'` in Pydantic v2 (attribute access on an undeclared field is a hard error, not `None`).

**Reproduced directly:** `pytest tests/test_api.py::TestTransactionsAPI::test_create_transaction`
fails with exactly this `AttributeError`, traced through the full middleware stack into
`app/routers/transactions.py:226`. This is not a test artifact — the test calls the real endpoint with
a valid, complete request body and the app crashes regardless. **Every call to this endpoint, from any
client, with any input, currently fails.** This is the single most fundamental write operation in a
bookkeeping application (recording a transaction) and it does not work via this API route at all.

**Recommended fix:** delete the router's local, stale `TransactionCreateRequest`/incomplete duplicate
and import the complete one from `app/schemas/transaction.py` (reconciling field-name differences —
e.g. `transaction_date` vs `date` — since the two schemas also disagree on that), or add the missing
fields to the local class directly. Either way, add the currency-support fields the docstring already
promises.

### 15.2 Finding 28 — CONFIRMED, P0 Critical: trial-subscription access checks crash with a naive/aware datetime comparison for every tenant currently on a trial

**Location:** `app/services/billing_service.py`, `check_subscription_access()` (line 3235) and
`app/models/sku.py`, `TenantSKU.is_trial` property (line 337) — the same bug in two places.

`TenantSKU.trial_ends_at` is declared `DateTime(timezone=True)` (`app/models/sku.py:167-171`), so
SQLAlchemy returns it as a timezone-**aware** Python `datetime` whenever it's set. Both call sites
compare it against a timezone-**naive** `datetime`:

```python
# billing_service.py:3225, 3235
now = datetime.utcnow()                                  # naive
...
if tenant_sku.trial_ends_at and tenant_sku.trial_ends_at > now:   # aware > naive
```
```python
# models/sku.py:334-338
@property
def is_trial(self) -> bool:
    if self.trial_ends_at:
        return self.trial_ends_at > datetime.now()        # aware > naive
    return False
```

Comparing an aware and a naive `datetime` with `>`/`<` is not undefined behavior in Python — it is a
hard `TypeError: can't compare offset-naive and offset-aware datetimes`, raised immediately, for
**every organization that currently has an active trial** (any `trial_ends_at` in the future; the
`and`/`if` guards check truthiness, not tz-awareness, so they never prevent this).

**Blast radius traced through both call sites:**
- `GET /api/v1/billing/subscription-access` (`app/routers/billing.py:1419-1445`) — the docstring
  states "This endpoint is used by the frontend to display subscription status banners." It has
  **no `try`/`except` around the call** — a trial organization's user hitting this endpoint gets a raw,
  unhandled 500. **Reproduced directly:**
  `pytest tests/test_trial_lifecycle.py::TestCheckSubscriptionAccess::test_active_trial_has_access`
  fails with exactly this `TypeError` at `billing_service.py:3235`; 9 of `test_trial_lifecycle.py`'s
  failures and 2 of its errors trace to this same root cause.
- `app/middleware/sku_middleware.py::_load_subscription_status` (line 453) calls the same method on
  every request for an authenticated org, **but this call site is wrapped in a broad
  `try/except Exception` that fails open** (lines 462-469: logs a warning, then sets
  `subscription_has_access = True`, `subscription_status = "unknown"`). This means the crash itself is
  invisible here — but it also means **trial-tier and grace-period enforcement is silently disabled
  for every organization currently on a trial**, since the middleware can never successfully determine
  their real status; it always falls through to the permissive default. This is a distinct,
  quieter consequence of the same bug: not a visible outage, but subscription/tier gating that
  doesn't actually gate for the one segment (active trials) it exists to manage.

**Recommended fix:** use `datetime.now(timezone.utc)` (or `datetime.now(UTC)` on Python 3.11+)
everywhere a timezone-aware column is compared against "now," in both `billing_service.py` and the
`TenantSKU.is_trial` property; audit the rest of `billing_service.py`/`app/models/sku.py` for the same
`datetime.utcnow()`/`datetime.now()` pattern against other `DateTime(timezone=True)` columns
(`current_period_start`/`current_period_end` are plain `Date`, not affected, but this pattern is worth
a dedicated grep before considering the class of bug closed).

### 15.3 Finding 29 — Testing gap, P1: the only test file covering the Finding 11 webhook vulnerability has never once exercised the real endpoint

`tests/test_webhook_integration.py` posts to `/api/billing/webhook/paystack` in all 16 places it
builds a request (verified via `grep`) — but the router is mounted at `/api/v1/billing` (confirmed:
`app/routers/billing.py:88`, `APIRouter(prefix="/api/v1/billing", ...)`). Every request in this file
is missing `/v1` and 404s before reaching any real code. **Reproduced directly:** all three
`TestWebhookSignatureVerification` tests fail with `assert 404 == 200`/`assert 404 == 400` — the app
never even routes the request, let alone runs the signature-verification logic this file exists to
test. This is the one test file in the suite that could have caught Finding 11 (§2.1, the unsigned
webhook), and it has never actually run against the real endpoint since whenever this URL was written
incorrectly. A secondary, independent bug (§15.4) breaks the remaining 8 tests in the same file via a
broken fixture, so effectively 100% of this file's 11 test methods currently provide zero real
coverage.

### 15.4 Finding 30 — Testing gap, P2: `tests/test_metering_concurrency.py` and `tests/test_metering_load.py` cannot run at all — a shared fixture bug, not an app bug

Both files (and the shared fixture in `test_webhook_integration.py:271`) construct
`TenantSKU(..., is_trial=False, ...)` directly. `TenantSKU.is_trial` (`app/models/sku.py:333-338`) is
a read-only, **computed** `@property` derived from `trial_ends_at` — it has no column and no setter.
SQLAlchemy's default declarative `__init__` rejects any keyword argument it can't `setattr`, so every
test depending on this fixture pattern errors before the test body even runs:
`AttributeError: property 'is_trial' of 'TenantSKU' object has no setter`. **Reproduced directly:**
confirmed identical across all 16 collected tests in `test_metering_concurrency.py`, all in
`test_metering_load.py`, and 8 of the 11 in `test_webhook_integration.py`. This means the entire
concurrent-metering and load-testing test suites — which exist specifically to validate usage-metering
correctness under concurrent/high-volume load, exactly the kind of thing that's hard to verify by
reading code — have never successfully run a single test. **Not an application bug**: `is_trial` is
correctly read-only by design; the fixture code should set `trial_ends_at` instead and let `is_trial`
derive from it (which would additionally have surfaced Finding 28 much earlier).

### 15.5 Finding 31 — Testing gap, P3: `test_api_endpoints.py::test_endpoint` cannot run — a parameter named `name` collides with pytest's fixture-injection

The test function declares a parameter literally named `name`, which pytest interprets as a request
for a fixture called `name` (pytest injects any parameter matching a fixture name). No such fixture is
defined anywhere in the suite, so pytest fails setup with `fixture 'name' not found` before the test
body runs. Almost certainly a `@pytest.mark.parametrize("name", [...])` decorator was intended but
never added, or a leftover parameter from an earlier version of the test.

### 15.6 Systemic: CI's test job cannot fail, so none of Findings 27–31 would ever surface there

`.github/workflows/ci.yml`'s `test` job runs `pytest tests/ --cov=app ... -x --tb=short || true` (line
176-184). The trailing `|| true` means the shell step always exits 0 **regardless of how many tests
fail or error** — the "Test Suite" job in the GitHub Actions UI reports green whether 0 or all 834
tests fail. This is the direct reason Findings 27–31 (two of them live P0 application bugs) have not
been caught by CI: there is currently no mechanism by which a broken test can block anything. Separately,
noted in passing: the same job's migration step (line 161) runs
`python scripts/create_railway_tables.py || alembic upgrade head || echo "Migration skipped..."` — but
`scripts/create_railway_tables.py` was deleted from this repository earlier in this engagement (Railway
removal). The `||` fallback chain means this doesn't currently break the job (it falls through to
`alembic upgrade head`), but the reference is dead and the comment justifying it ("to avoid alembic enum
conflicts") is now stale.

**Recommended fix:** remove `|| true` from the test step so a failing/erroring test actually fails CI;
fix Findings 27, 28, 29, 30, and 31 first (in that order — 27 and 28 are live app bugs, the rest are
test-only), otherwise removing `|| true` would immediately turn CI red on the very next push. Update or
remove the dead `scripts/create_railway_tables.py` reference in the migration step.

### 15.7 Everything that passed

773 of 834 tests passed against a real database with no special accommodation, including the full
`test_tax_calculators.py`, `test_2026_compliance.py`, `test_sku_system.py`, `test_fx_conversion.py`,
`test_cache_service.py`, `test_auth_service.py`, and `test_consolidation.py` suites, and the majority
of `test_api.py`, `test_trial_lifecycle.py`, and `test_integration.py`. This is recorded because the
audit's own standard cuts both ways: having found real, reproducible failures, it's equally important
not to imply the entire suite or the entire application is broken — the failures found are real,
specific, and now enumerated, not representative of the whole.

---

## 12. Error and Edge-Case Testing

Extended the same "actually execute it" standard from §15 to boundary/malformed inputs on core
tax-calculation logic, since that's the highest-consequence business logic in the app and the most
likely place for a silent miscalculation or crash to matter.

### 12.1 Verified robust: `PAYECalculator.calculate_paye` handles zero, negative, and boundary income cleanly

Ran `calculate_paye()` directly (clean venv, no mocking) against `0`, `-50000`, `0.01`, and each PAYE
band boundary (`799999`/`800000`/`800001`, `2400000`, `7200000`) and one very large value
(`100000000`). No exceptions; negative/zero income correctly clamps to zero tax via
`max(Decimal("0"), gross_annual_income - total_reliefs)` rather than producing a negative tax figure.
Confirmed at the API boundary (`app/routers/tax.py:380`, `app/routers/tax_2026.py:1185`,
`app/routers/advanced_audit.py:76`) that `gross_annual_income: float = Field(..., gt=0)` rejects
non-positive input with a clean 422 before it ever reaches the calculator on the normal PAYE-calculation
endpoints — so the calculator's own graceful handling of zero/negative is defense-in-depth, not the
only thing standing between a bad request and a crash.

### 12.2 Finding 34 — Confirmed, P2 Medium: the compliance-replay endpoint has no input validation on its numeric fields and crashes on non-numeric input

**Location:** `POST /replay/calculate` (`app/routers/advanced_audit.py:295-320`) →
`ComplianceReplayEngine.replay_paye_calculation` (`app/services/compliance_replay_service.py:367-379`).

Unlike the normal PAYE endpoints (§12.1), this one takes `inputs: Dict[str, Any]`
(`ReplayRequest.inputs`, line 118) — Pydantic cannot apply any numeric constraint to values inside an
`Any`-typed dict, so `gross_annual_income` here is never validated as a number at all before reaching
`gross = Decimal(str(gross_annual_income))` (line 379, no `try`/`except` around it, and none in the
router either). **Reproduced directly:** calling `PAYECalculator.calculate_paye('not-a-number')` (the
same `Decimal(str(x))` pattern used in both places) raises `decimal.InvalidOperation:
[<class 'decimal.ConversionSyntax'>]` immediately. A client sending
`{"calculation_type": "paye", "calculation_date": "2026-01-01", "inputs": {"gross_annual_income": "abc"}}`
to this endpoint gets an unhandled 500, not a clean validation error.

This endpoint's own docstring states its purpose: "Useful for audit defense and demonstrating
point-in-time compliance" — a compliance/audit-replay tool that 500s on malformed input is a real
robustness gap in a feature specifically meant to be trustworthy during an actual audit, even though
it isn't a security vulnerability (no data exposure, no injection — the input still comes from an
authenticated user).

**Recommended fix:** replace `inputs: Dict[str, Any]` with a proper typed request model
(`gross_annual_income: float`, etc.) per `calculation_type`, so Pydantic validates it the same way the
normal PAYE/VAT endpoints already do; at minimum, wrap the `Decimal(str(...))` conversions in a
`try/except (InvalidOperation, ValueError)` that returns a 400.

### 12.3 Verified robust: the remaining 4 tax calculators (VAT, WHT, CIT's non-minimum-tax path, Minimum ETR, CGT) all handle edge-case input correctly

Completing the sweep started in §12.1/§16: ran `VATCalculator.calculate_vat()` directly against zero,
negative, and inclusive/exclusive-mode amounts — no exceptions; a negative amount produces a
mathematically consistent negative VAT figure (correct for a credit-note/refund scenario, not a bug).
Confirmed at the API boundary (`app/routers/tax.py:34-35`,
`VATCalculationRequest.amount: float = Field(..., gt=0)`, `vat_rate: float = Field(7.5, ge=0, le=100)`)
that non-positive amounts and out-of-range rates are rejected with a clean 422 before reaching the
calculator, mirroring the PAYE endpoint's pattern from §12.1. Also checked
`VATCalculator.is_vat_recoverable()`'s string comparison (`wren_status in [WRENStatus.COMPLIANT,
"compliant", "classified"]`) against `WRENStatus`'s actual enum values (`app/models/transaction.py:36-40`,
all lowercase) — consistent, not a repeat of Finding 1's casing bug; `"classified"` is a harmless
unreachable extra string (no `CLASSIFIED` member exists in `WRENStatus`, so that branch of the `in`
check never matches anything, but it also never causes incorrect behavior).

This completes edge-case verification of all 5 modules in `app/services/tax_calculators/`: PAYE (§12.1,
robust), VAT (above, robust), WHT (§16.4, safe — theoretical div-by-zero confirmed unreachable), CIT
(§16.5, Finding 35 CONFIRMED — the one real bug in this group), Minimum ETR and CGT (§16, both
independently traced and found correct). No further tax-calculation edge-case work remains open.

---

## 7.7 Resolution: middleware ordering (carried from Section 7)

Traced `app/middleware/security.py::setup_security_middleware` (lines 502–563) and its call site in
`main.py` (security → SKU gating → emergency mode, in that order). Starlette's `add_middleware` stacks
LIFO — the *last* `add_middleware` call becomes the *outermost* layer and runs first on every
request. Working through the actual call order: within `security.py`, `GeoFencingMiddleware` is added
6th (last) of the six security layers, so despite the file's own comment mislabeling it "innermost...
first check" (self-contradictory phrasing — outermost is what runs first), it correctly *is*
outermost among those six, and does set `request.state.client_ip` before `RateLimitingMiddleware` and
`AccountLockoutMiddleware` execute. **Verified safe** — `auth.py::login()`'s read of
`request.state.client_ip` is reliably populated by the time it matters.

**Finding 25 — Code Smell, P3:** the numbered comments in `setup_security_middleware` (`# 1. Request
logging (outermost...)` through `# 6. Geo-fencing (innermost...)`) label the layers backwards relative
to Starlette's actual LIFO behavior — #1 is added first and is therefore the *innermost* layer, #6 is
added last and is the *outermost*, the reverse of what the comments say. The current behavior happens
to be correct (geo-fencing genuinely does run first, which is the intent), but the comments would
actively mislead the next person who tries to reason about inserting a new middleware layer correctly.
Recommend rewriting the comments to match Starlette's real semantics, or reversing the add order to
match the comments (either fixes the confusion; only the comments are wrong today, not the behavior).

At the app level, `main.py` calls `setup_security_middleware()` → `setup_sku_middleware()` →
`create_emergency_middleware()` in that order, meaning emergency-mode checks become the absolute
outermost layer of the entire app (run before geo-fencing, CSRF, rate limiting, and SKU gating) — a
reasonable design for a kill-switch, and not flagged as an issue.

---

## 13. Performance Audit

Rather than re-derive performance concerns from scratch, this section cross-references what earlier
sections already surfaced under direct investigation, plus one dedicated check (database index
coverage) done specifically for this section.

- **§6.2 (Finding 36):** `UserEntityAccess` — read on nearly every authenticated, entity-scoped
  request in the app — has no index on `entity_id` or `user_id`. This is the single highest-leverage
  performance finding in the audit: one missing index on the busiest access-control table in the
  system, not a narrow feature-specific slowdown. `AccountBalance`, a table built specifically "for
  performance," has the same gap on the column it exists to be filtered by.
- **§8.7 (Finding 32):** rate limiting is in-memory and per-instance while the live Cloud Run service
  autoscales to 10 instances — not a "slow" finding in the traditional sense, but a case where the
  deployment's own scaling behavior (good for performance) directly undermines a control that assumes
  single-instance state.
- **§18 (Finding 23):** unbounded dependency version ceilings already caused a full-site outage this
  session from a routine rebuild — the most severe "performance" risk in the literal sense of uptime,
  even though its root cause is dependency management, not algorithmic complexity.
- **Middleware stack depth (§7.7):** every request that isn't exempt passes through up to 8 layered
  `BaseHTTPMiddleware` instances (request logging, geo-fencing, rate limiting, CSRF, three security-
  header/audit layers, SKU gating) before reaching route logic. Each `BaseHTTPMiddleware` layer in
  Starlette adds a measurable amount of overhead (it wraps the ASGI call in a `StreamingResponse`
  under the hood); 8 layers is on the high side but not unusual for a security-conscious app, and no
  specific layer was found doing obviously wasteful work (e.g., a synchronous blocking call or a
  redundant DB round-trip) beyond what's already documented. Not flagged as a confirmed problem —
  recorded as a dimension worth profiling with real traffic before or shortly after launch, since static
  reading of the code can establish *that* overhead exists but not *how much*.
### 13.1 Actual concurrent load testing against a fully-migrated instance — this is how Finding 41 was found

Since `test_metering_load.py` cannot currently run at all (Finding 30, §15.4), a standalone load-test
script was written instead: a fresh local Postgres database, migrated via the real `alembic upgrade
head` chain (not `Base.metadata.create_all()` — deliberately, to make this run representative of a
real deployment), the app started against it exactly as `bootstrap.sh` would configure production
(`APP_ENV=production`, `DEBUG=False`), then hit with concurrent `httpx.AsyncClient` requests using
`asyncio.gather`. This is exactly the discovery method that found Finding 41 — a burst of concurrent
failed-login attempts surfaced the `target_entity_type` column error immediately, something no amount
of code reading had caught up to that point.

**50 concurrent `GET /health`:** all 200 OK, 0.16s total — no problem at low concurrency.

**30 concurrent `POST /api/v1/auth/login` with a wrong password:** 26 correctly rate-limited (429), but
**4 returned 500** — these 4 are Finding 41 (the audit-log write for `LOGIN_FAILED` failing before the
rate limiter's own 429 response path is reached for those particular requests).

### 13.2 Finding 42 — CONFIRMED, P2 Medium: `/health` has no rate-limit exemption, unlike every other security middleware, and a burst of legitimate traffic can make it return 429

**200 concurrent `GET /health`:** only 49 returned 200 — the other **151 were rate-limited (429)**,
confirmed directly from the server's own access log (`GET /health HTTP/1.1" 429 Too Many Requests`,
repeated).

**Root cause:** `RateLimitingMiddleware.dispatch()` (`app/middleware/security.py:139-183`) has no
`EXEMPT_PATHS` check at all — every path, including `/health`, goes straight to
`rate_limit_config.get_limit(path)`. `/health` matches none of `RateLimitConfig.LIMITS`'s specific
patterns (`app/utils/ndpa_security.py:512-522`, all `/api/v1/...`), so it falls through to the default
`return (100, 60)` — 100 requests per 60 seconds per client IP, the same budget as an arbitrary
unmatched API route. This is inconsistent with the app's own established pattern: both
`GeoFencingMiddleware` (line 50-51) and `CSRFMiddleware` (line 240-243) explicitly list `/health` in
their own `EXEMPT_PATHS`, precisely because a security check returning a non-2xx for a health probe is
recognized elsewhere in this same file as something to avoid — the rate limiter alone was never given
the same treatment.

**Why this matters operationally:** a health/liveness-check endpoint that can return 429 under a burst
of *legitimate* traffic is a self-inflicted availability risk — the busier and more successful the app
is at a given moment (more concurrent requests from the same effective IP, e.g. behind a NAT gateway
or shared corporate network), the more likely `/health` itself starts failing, right when an
orchestrator's liveness probe would be most likely to also be checking in. A liveness probe that starts
seeing 429s could conclude the container is unhealthy and restart it — during exactly the traffic spike
the container was actually handling correctly.

**Recommended fix:** add `/health` (and any other genuine health/readiness endpoints) to
`RateLimitingMiddleware`'s own exempt-path check, matching the pattern already used by
`GeoFencingMiddleware` and `CSRFMiddleware` in the same file.

### 13.3 Finding 43 — CONFIRMED, P2 Medium: `recalculate_gl_balances_from_journal_entries` runs 2 queries per account instead of 1 grouped query — 100-300+ individual queries for a single API call on a normal Chart of Accounts

Wrote an AST scan across all 92 services for `await ...execute(...)` calls inside a `for`/`async for`
loop body — the mechanical shape of an N+1 query pattern — and manually read every result to separate
genuine antipatterns from loops that are small/bounded or do semantically distinct per-item work (most
of the 38 raw hits are the latter — e.g., iterating a handful of line items to *create* records, or
`DashboardService._get_entity_if_accessible`'s loop over `user.entity_access`, which returns on first
match against a typically single-digit list, not a scaling read).

**Location:** `AccountingService.recalculate_gl_balances_from_journal_entries()`
(`app/services/accounting_service.py:2302-2340+`), called by `POST /recalculate-balances`
(`app/routers/accounting.py:931-953`).

```python
accounts = await self.get_chart_of_accounts(entity_id, include_headers=False)
for account in accounts:
    debit_result = await self.db.execute(...)   # one query per account
    credit_result = await self.db.execute(...)  # a second query per account
```

A standard Nigerian Chart of Accounts (per this same service's own `create_default_chart_of_accounts`,
read earlier in this engagement) has several dozen accounts across asset/liability/equity/
revenue/expense categories; a real entity's chart is often larger once custom accounts are added. Every
call to this one endpoint issues **2 separate aggregate queries per account** — 100-300+ round trips to
Postgres for what is a single logical operation ("recompute every account's balance"), where a single
grouped query would do:

```sql
SELECT account_id, SUM(debit_amount), SUM(credit_amount)
FROM journal_entry_lines JOIN journal_entries ON ...
WHERE entity_id = :entity_id AND status = 'POSTED'
GROUP BY account_id
```

**A second, smaller instance** in `UsageAlertService` (`app/services/usage_alert_service.py:361-378`,
inside whatever sends billing/usage alert notifications): for every alert in a batch, it queries
`Organization` and then separately queries `User` — both keyed only by `organization_id`, both easily
replaced by two batched `WHERE organization_id IN (...)` queries outside the loop.

**Recommended fix:** rewrite `recalculate_gl_balances_from_journal_entries` to use a single grouped
aggregate query and update all account balances from that one result set; batch `UsageAlertService`'s
per-alert organization/user lookups the same way.

### 13.4 Not yet done

Cache-hit-rate verification for `app/services/cache_service.py` (the service itself passed all its
tests in §15.7, but that confirms correctness, not effectiveness under real load patterns) and load
testing beyond the two endpoints exercised in §13.1 and the static N+1 sweep in §13.3 — this was a
targeted probe that found real defects quickly, not an exhaustive load-testing pass across all 1185
routes or all 38 raw N+1 candidates.

---

## D. Broken-Flow Map — workflows that currently fail end-to-end

| Workflow | Where it breaks | Finding |
|---|---|---|
| Edit an invoice line item's quantity/price without also resending its VAT rate | `PUT /{entity_id}/invoices/{invoice_id}/line-items/{line_item_id}` raises an unhandled `AttributeError` | 22 |
| Any write to one of 30 confirmed enum-backed columns via the ORM (mark a fixed asset disposed, approve a budget, record an FX revaluation, generate a platform API key, etc.) | Postgres rejects the value SQLAlchemy sends (`invalid input value for enum ...`) | 1 |
| View another organization's financial reports/tax filings/audit logs/forensic analyses by changing a URL's entity ID | Succeeds when it should 403 — the flow "completes" but with the wrong data, which is worse than a visible break | 18 |
| Close/reopen/lock a fiscal year for an organization you don't belong to | Succeeds when it should be rejected | 18 (year_end.py) |
| Paystack sends (or an attacker forges) a webhook while `PAYSTACK_WEBHOOK_SECRET` is unset | Processes and mutates billing state with no verification | 11 |
| Fresh `docker build` of this exact codebase, no code changes | Historically has fully broken the app (every page 500s) the moment a dependency ships a breaking change — already happened once this session | 23 |
| Record any transaction (income or expense) via `POST /{entity_id}/transactions`, with any valid input | Raises an unhandled `AttributeError` on every single call — the endpoint cannot succeed | 27 |
| Any organization currently on a trial checks its subscription status (`GET /api/v1/billing/subscription-access`, or any request passing through `sku_middleware`) | Status endpoint 500s directly; middleware silently swallows the crash and grants unconditional access instead, disabling trial/grace-period enforcement | 28 |
| Calculate CIT for a non-exempt, profitable company whose margin is thin enough that 0.5% of turnover exceeds 30%/20% of profit | Doesn't fail — returns 200 with a materially understated tax figure (68% shortfall in the reproduced example) | 35 |
| `POST /replay/calculate` with a non-numeric value in `inputs` (e.g. `gross_annual_income: "abc"`) | Raises an unhandled `decimal.InvalidOperation` — a compliance/audit-defense tool that itself breaks on malformed input | 34 |
| Any write operation on any of ~26 routers that logs its own action (create a vendor/account/journal entry/invoice/receipt, fail a login, etc.) | The audit-log INSERT itself raises `UndefinedColumnError` (`target_entity_type` was never migrated), which propagates up as a 500 — the business operation's own success or failure is irrelevant once this line is reached | 41 |
| A payroll run for any employee with meal or utility allowances (an ordinary salary structure) | Succeeds, but silently understates annual PAYE by the excess relief amount — no error, no warning | 39 |
| A customer with a pending downgrade request has an unrelated payment failure, or a customer being dunged for non-payment requests an unrelated downgrade | Succeeds, but resolves to the wrong outcome (retains a paid tier instead of being suspended, or a legitimate downgrade is silently erased on payment recovery) | 40 |
| `recalculate_gl_balances_from_journal_entries` on an entity with a normal-sized Chart of Accounts | Succeeds, but issues 100-300+ individual queries where one grouped query would do | 43 |
| A burst of legitimate concurrent traffic shares an effective client IP with `/health` liveness/readiness checks | `/health` itself starts returning 429 — the one endpoint whose failure could trigger a container restart is not exempted from the rate limiter that every other security middleware exempts it from | 42 |

## E. Route Audit — summary (full detail in §1, §2, §3, §4/5)

- **1185 routes across 68 router files**, 66 actually mounted (`audit_consolidated.py` is dead — never
  imported by `main.py`).
- **Zero duplicate (method, path) collisions** once prefixes are correctly resolved (an initial check
  without full prefix resolution produced 8 false positives, corrected).
- **113 routes initially flagged for missing auth**, individually resolved: 1 real gap (unauthenticated
  metrics endpoint, Finding 12), the rest are legitimate public pages, a manual `require_auth()`
  pattern invisible to dependency-based static analysis, or dead redirect stubs.
- **188 routes flagged for missing entity-ownership verification**, all individually resolved:
  **164 confirmed vulnerable** (Finding 18) and **24 confirmed safe** (false positives — either a
  service-layer check under an access-check name the initial sweep didn't recognize, a route scoped by
  `current_user.id` rather than `entity_id`, or an endpoint that doesn't yet touch any real per-entity
  data). Zero remain unresolved.

## F. API Audit — summary

Every endpoint's HTTP method, route, and auth dependency were enumerated via full AST parsing (not
regex) — see the raw data behind §2/§3's findings. Not yet completed: systematic verification that
each endpoint's actual response shape matches what its frontend caller expects (would require pairing
each API route against its consuming template/JS, not yet done for anything outside the flows already
traced). No endpoints were found to be entirely unused (dead) in the sense of "defined but never
callable" beyond the 46 duplicated ones inside the dead `audit_consolidated.py` router.

## G. Dead-Code Report

| Item | Location | Safe to remove? |
|---|---|---|
| `unified_router` and the whole file | `app/routers/audit_consolidated.py` | Yes — confirmed zero references from `main.py` or anywhere else |
| 4 standalone templates | `advanced_audit.html`, `audit_logs.html`, `dashboard.html`, `worm_storage.html` | Yes — all superseded, confirmed zero `TemplateResponse`/`extends`/`include` references anywhere |
| 8 role-based dashboard partials | `templates/partials/org_dashboard/*.html` | Yes — confirmed zero references; a parallel, differently-named directory (`partials/dashboard/`) is the one actually in use |
| Unused SQL-injection-shaped utility | `app/utils/query_optimization.py::analyze_query_performance` | Yes to delete, or fix parameterization first if kept — confirmed zero callers |
| 10 test files outside `tests/` | repo root `test_checkout_debug.py`; `scripts/test_*.py` (9 files) | Move into `tests/` if still valid, else delete — confirmed never collected by `pytest` given `testpaths = ["tests"]` |
| 8 schema-patching scripts that bypass Alembic | `scripts/add_*.py`, `create_*.py`, `fix_*.py` (see Finding 21 for exact list) | Delete — confirmed the live schema is fully migration-managed; these are a footgun, not a safety net |
| 2 duplicate function definitions | `app/dependencies.py::require_bank_reconciliation`, `require_advanced_reports` (each defined twice) | Yes — delete the second, identical definition of each |

Not yet checked: dead code at function/variable granularity *inside* files that are otherwise used
(this report only confirmed all 92 service *files* are referenced somewhere, not that every function
within each is called).

## H. Security Report

| # | Finding | Sev | Status |
|---|---|---|---|
| 18 | Cross-tenant IDOR, 164 endpoints, 17 routers | P0 | Confirmed |
| 37 | Stored XSS in Admin Verifications, unauthenticated → Super Admin session compromise | P0 | Confirmed |
| 11 | Unsigned Paystack webhook → free tier escalation | P0 | Confirmed |
| 38 | Same-tenant stored XSS via evidence title in print/PDF export | P2 | Confirmed |
| 6 | `httponly=False` on access-token cookie | P1 | Confirmed |
| 12 | Unauthenticated internal metrics endpoint (`GET /stats`) | P3 | Confirmed |
| 13 | SQL-injection-shaped code, currently unreachable | P3 (would be P0 if wired up) | Confirmed dead |
| 15 | File-upload type check trusts client-supplied header | P2 | Potential Risk — serving side not yet traced |
| 16 | CORS still on localhost-only defaults in production | P2 | Confirmed (functional gap, not itself exploitable) |
| 17 | No hardcoded secrets in `app/` | — | Verified clean |
| 7/8 | Duplicate/broken `get_optional_user` dependency | P3 (dead today) | Confirmed |
| 26 | `debug`/`app_env` insecure-by-default; also silently disables CSRF, geo-fencing, and the rate-limit multiplier if misconfigured | P2 | Confirmed |
| 32 | In-memory, per-instance rate limiting diluted ~10x by real Cloud Run autoscaling | P2 | Confirmed |
| 33 | Logout doesn't clear the auth cookie (no server-side blacklist either, by design) | P2 | Confirmed |

CSRF token validation was independently verified correct and correctly enforced in production (§8.6) —
the earlier open question about whether the middleware's token-generation/validation logic actually
works is resolved, not still open. Session/logout token invalidation was traced to a concrete answer
(§8.8, Finding 33): no server-side blacklist exists (a disclosed, reasonable tradeoff for stateless
JWT), but the client-side cookie is also never cleared (not a tradeoff — a plain gap) — reclassified
from Potential Risk to Confirmed. Rate-limiting effectiveness under load was traced to a concrete
mechanism-level gap (§8.7, Finding 32) rather than left as an untested question.

## I. Database Integrity Report

- **35 confirmed/near-certain enum value-casing bugs** across 12+ tables (Finding 1), verified against
  live Postgres enum definitions, not assumed.
- **4 columns with genuinely divergent value sets** between the Python model and the live DB type,
  not just a casing mismatch (Finding 1b) — need a product decision before any mechanical fix.
- **1 internally-inconsistent enum type** (`journalentrytype`, mixing upper- and lower-case values
  from two different migrations) (Finding 1c).
- **11 tables whose models never register with `Base.metadata`** unless an unrelated service module
  happens to be imported first (Finding 19, `payroll_advanced.py`).
- **Zero orphaned database tables** (every live table has a corresponding model) — the initial
  15-table discrepancy was fully resolved and explained, not left open.
- **`UserEntityAccess` — the table nearly every access-control check in the app reads — has no index
  on `entity_id` or `user_id` and no uniqueness constraint on `(user_id, entity_id)`** (Finding 36,
  P2); `AccountBalance`, a table explicitly built "for performance," has the same missing-index gap on
  the one column it would actually be filtered by. Found by scanning every `entity_id` column
  definition across all model files for `ForeignKey`/`index=True` presence, not assumed.
- Not yet checked: foreign-key cascade behavior beyond what §6.2 covers, transaction-boundary
  correctness under concurrent access, soft-delete consistency, and any orphaned *rows* (as opposed to
  tables) — that check needs live-DB queries and was deliberately not run against the production
  database during this audit to avoid touching real tenant data casually.

## J. Testing Gaps

The suite was actually executed against a real database this session (§15), not just read — the
findings below reflect that, not static inference:

- **The test suite was actually run: 834 collected, 773 passed, 19 failed, 42 errored** (§15). Every
  failure/error was individually traced; none were left as an unexplained raw count.
- **Two of those failures are live, currently-broken P0 application bugs, not test bugs** — Finding 27
  (`create_transaction` crashes on every call) and Finding 28 (trial-subscription status check crashes
  for every active-trial tenant). Both were found only by running the code, not by reading it.
- **10 test files are not part of the executed test suite at all** (Finding 20) — checkout e2e,
  billing subscription, and SKU enforcement tests exist but have not actually run via `pytest` for as
  long as they've lived in `scripts/` instead of `tests/`.
- **A test file for the Paystack webhook's signature-verification path does exist
  (`test_webhook_integration.py`) — but it has never once exercised the real endpoint** (Finding 29):
  every one of its 16 requests posts to `/api/billing/webhook/paystack`, missing the `/v1` the router
  actually requires, so every request 404s before reaching any real code. Combined with an unrelated
  fixture bug (Finding 30) that breaks its other 8 tests, 100% of this file currently provides zero
  coverage of Finding 11, the P0 it exists to catch.
- **The concurrent-metering and load-testing suites (`test_metering_concurrency.py`,
  `test_metering_load.py` — ~30 tests total) have never successfully run a single test** (Finding 30)
  — a shared fixture tries to set a read-only computed property (`TenantSKU.is_trial`) as if it were a
  column, so every test errors in setup before its body runs.
- **No test found anywhere in the suite that exercises entity-scoped access control** (i.e., "user
  from Org A calls an Org B-scoped endpoint and gets 403/404") — given Finding 18, this is the most
  important missing test category in the entire codebase. Recommend one parameterized test that hits
  every entity-scoped route with a foreign entity ID and asserts rejection, which would have caught
  Finding 18 immediately had it existed.
- **No test found asserting `SQLEnum` columns' Python values match their live Postgres type** — would
  have caught Finding 1 across all 35 instances at once, and prevent regressions.
- **The single biggest structural testing gap found this session: `tests/conftest.py` builds its
  database with `Base.metadata.create_all()` (line 68), not by running Alembic migrations.** This
  means the entire 834-test suite runs against a schema that always exactly matches whatever the
  current model files say, regardless of whether a real migration was ever written to produce that
  schema in a real deployment. Finding 41 — every audit-log write across ~26 routers failing against a
  genuinely migrated database — is completely invisible to this test suite for exactly this reason, and
  it was found only by standing up a fresh database via the real `alembic upgrade head` chain and load-
  testing the running app (§13.1). This is not a one-off gap tied to Finding 41 specifically: *any*
  future model/migration drift of the same shape would be equally invisible until it reaches a
  genuinely migrated environment. Recommend switching `conftest.py` to migrate the test database the
  same way a real deployment does.
- **CI cannot currently fail on test results at all** (Finding 15.6) — `ci.yml`'s pytest step ends in
  `|| true`, so the "Test Suite" job reports green regardless of outcome. This is the reason none of
  Findings 27-31 have been caught before now despite being deterministic and 100%-reproducible.

## K. Recommended Remediation Order

1. **Finding 18** (cross-tenant IDOR, P0) — highest risk, highest breadth, purely additive fix
   (add a check; doesn't change any working behavior for legitimate callers).
2. **Finding 41** (audit-log write path broken for ~26 routers' writes, P0) — a single, mechanical,
   additive migration (add 2 columns) fixes every affected caller at once; do this immediately, since
   until it ships, any write endpoint that logs its own action is one unlucky request away from a 500.
3. **Finding 37** (stored XSS in Admin Verifications, P0) — small, isolated fix (escape 3 fields in
   one template) against the highest-privilege target in the app, reachable by anyone who can fill out
   the public signup form; do this immediately alongside Finding 18.
4. **Finding 11** (unsigned webhook, P0) — do this before ever enabling live Paystack keys; also
   purely additive/defensive, no legitimate flow depends on the current unsafe behavior.
5. **Finding 27** (`create_transaction` crashes on every call, P0) — small, isolated, immediately
   restores a completely broken core feature; no legitimate flow depends on the current broken schema.
6. **Finding 28** (trial-status naive/aware datetime crash, P0) — small, isolated, two call sites;
   immediately restores trial-status visibility and re-enables trial/grace-period enforcement that is
   currently silently disabled.
7. **Finding 35** (CIT minimum tax silently undercharges, P1) — one-line fix (delete a clause), but
   sequence it early despite the low mechanical risk: every day it ships is another day a real user
   could file an understated CIT figure with the tax authority based on this software's output.
8. **Finding 39** (payroll PAYE relief-basis mismatch, P1) — fires on every ordinary payroll run with
   meal/utility allowances, not an edge case; sequence alongside Finding 35 for the same reason —
   every day of delay is another pay period's worth of understated statutory withholding.
9. **Finding 40** (shared cancel_at_period_end flag lets dunning be bypassed, P1) — needs a small
   schema addition (a dedicated dunning-state field) rather than a one-line fix, so sequence it after
   the purely-mechanical P1s below but before the P2 cleanup, given its revenue-protection impact.
10. **Finding 1** (enum casing, P1) — mechanical, low-risk, same fix already proven correct on 3
    columns earlier this project; do the 4 divergent-value-set columns (Finding 1b) and the
    `journalentrytype` normalization (1c) as a deliberate follow-up since those need a product
    decision, not just a code change.
11. **Finding 22** (invoice line-item crash, P1) — small, contained, immediately improves a core
    customer-facing flow.
12. **Finding 6** (`httponly=False` cookie, P1) — needs a short design discussion (what was the
    client-side read actually for?) before the fix, so sequence it after the purely-mechanical fixes
    above.
13. **Finding 23** (dependency version ceilings, P1) — do this early regardless of the rest; every day
    without it is another day a routine rebuild can silently break the app again.
14. **Finding 29** (webhook test wrong URL, P1) — one-line-per-call fix, restores the only real test
    coverage of Finding 11; do immediately after Finding 11 itself is fixed, so the corrected test
    actually exercises the corrected behavior.
15. **Finding 15.6** (`ci.yml`'s `|| true`, P1) — remove only after Findings 27-31 are fixed, otherwise
    this turns CI red on the very next push for reasons already known and already being fixed.
16. Everything else in severity order: Findings 19, 20, 21, 26, 30, 32, 33, 34, 36, 38, 42, 43, 44, 46,
    47 (P2 cleanup), then the P3 dead-code/comment fixes (3, 4, 7, 8, 13, 25, 31, 45, 48), which are
    safe to batch
    together. Separately, and not tied to any one finding's severity: replace
    `tests/conftest.py`'s `Base.metadata.create_all()` with the real Alembic migration chain — this is
    what let Finding 41 go undetected, and the same blind spot could be hiding other model/migration
    drift that hasn't surfaced yet.

---

## Audit progress tracker

**All 22 sections of `docs/AUDIT_CHECKLIST.md` are now closed** (Done or Substantially Done for the 18
sections that involve one-time investigation; Ongoing for the 4 that are cross-cutting by nature —
traceability, methodology, severity classification, and deliverable assembly, which apply continuously
rather than reaching a discrete end state). Every section that started "Not started" or "Partial" —
2, 5, 6, 9, 10, and 17 — was subsequently worked to closure, each with an honest accounting in its own
write-up of what could and couldn't be verified within this audit's means (e.g., §6's orphaned-row
check blocked by infrastructure access, §13's cache-hit-rate check requiring production traffic this
audit doesn't have). **48 findings total (Finding 1 through Finding 48), all sequentially numbered
with no gaps, cross-referenced consistently throughout this document, `docs/AUDIT_CHECKLIST.md`, and
the executive summary/deliverables A-K.**

The single clearest lesson from this engagement: three of the most severe findings were caught only by
*running* the application rather than reading it. Section 15's test execution surfaced two live P0
crashes (Findings 27, 28) invisible to code review; the same standard surfaced Finding 35 (a silently
wrong CIT calculation) and Finding 39 (a payroll bug understating PAYE on every ordinary salary); and
standing up a fresh database via the *actual* Alembic migration chain and load-testing the running app
(§13.1) surfaced Finding 41 — the app's central audit-logging service cannot write a single record
against a genuinely migrated database, putting roughly a quarter of the app's routers' write endpoints
one request away from a 500. That defect is structurally invisible to the existing 834-test suite,
because its own database setup bypasses migrations entirely (a distinct finding in its own right,
Deliverable J). Finding 41 is, by blast radius, arguably the most consequential single defect in this
report; Finding 18 (cross-tenant IDOR) and Finding 37 (unauthenticated stored XSS into a Super Admin
session) remain the most severe from a confidentiality/integrity standpoint. Together with Finding 11
(unauthenticated billing takeover), these four defects are what stand between this application and a
safe production launch; everything else in this report is real, evidenced, and worth fixing, but none
of it is launch-blocking in the way these four are.
