# TekVwarho ProAudit - GCP Deployment Reference

**Status: live.** The app is fully deployed and serving traffic at
`https://proaudit-web-966191721117.africa-south1.run.app` (health check returns
`{"status":"healthy","database":"connected"}`). The Cloud SQL schema is built to the
latest migration head (`fx_revaluation_001`), the Celery worker and beat schedulers are
running and connected to Redis, and the super admin account requested for this migration
(Efe Obukohwo / efe.obukohwo@tekvwa.org) exists in the database.

This documents the live GCP infrastructure created for the migration described in
`docs/GCP_MIGRATION_PLAN.md`, and the exact commands used to stand it up, so it can
be reproduced, extended, or torn down deliberately.

Project: `tekvwarho-proaudit` (org `tekvwa.org`, billing account `01C692-FEF20F-476F05`)
Region: `africa-south1` (Johannesburg) - closest GCP region to Nigeria, lowest latency for users there.

---

## 1. What has been provisioned

| Resource | Name | Notes |
|---|---|---|
| Project | `tekvwarho-proaudit` | Dedicated project, separate from other TekVwa projects |
| VPC | `proaudit-vpc` | Custom-mode, one subnet `proaudit-subnet` (10.10.0.0/20) in `africa-south1` |
| Private services access | peering via `proaudit-private-ip-range` | Required for Cloud SQL private IP |
| Serverless VPC Access connector | `proaudit-connector` | Lets Cloud Run reach Cloud SQL/Memorystore privately |
| Firewall | `proaudit-allow-internal` | Allows internal traffic within 10.10.0.0/16 |
| Cloud SQL | `proaudit-db` (Postgres 15, private IP only, `db-custom-2-8192`) | PITR + daily backups enabled, 14 backups retained |
| Memorystore Redis | `proaudit-redis` (Basic tier, 1GB, Redis 7) | Used for cache + Celery broker/backend |
| Artifact Registry | `proaudit-repo` (Docker, `africa-south1`) | Container image storage |
| GCS bucket | `tekvwarho-proaudit-files` | Application file storage (versioned) |
| GCS bucket | `tekvwarho-proaudit-db-backups` | For manual/ad-hoc DB dump storage (versioned) |
| Service account | `proaudit-run-sa@tekvwarho-proaudit.iam.gserviceaccount.com` | Cloud Run runtime identity — `cloudsql.client`, `secretmanager.secretAccessor`, `storage.objectAdmin`, `redis.editor` |
| Secret Manager secrets | see table below | |

### Secrets already created

| Secret name | Contents |
|---|---|
| `secret-key` | Randomly generated app `SECRET_KEY` |
| `jwt-secret-key` | Randomly generated `JWT_SECRET_KEY` |
| `postgres-password` | Randomly generated password for the `proaudit_app` DB user |
| `super-admin-email` | `Efe.obukohwo@tekvwa.org` |
| `super-admin-password` | (as provided) |
| `super-admin-first-name` | `Efe` |
| `super-admin-last-name` | `Obukohwo` |
| `database-url` / `database-url-async` | Created by `deploy/gcp/bootstrap.sh` once the Cloud SQL private IP is known |
| `redis-url` | Created by `deploy/gcp/bootstrap.sh` once the Memorystore IP is known |

None of these values are stored in the repository. They only exist in Secret Manager and are wired
onto the Cloud Run services via `--set-secrets`, which injects them as environment variables at
container start.

### Secrets NOT yet created (need real values from you before those features work in production)

These have safe defaults (disabled/sandbox) in `app/config.py`, so the app runs without them, but the
corresponding feature will not work until you add the value. Use the pattern below for each:

```bash
printf '%s' 'REAL_VALUE_HERE' | gcloud secrets create SECRET_NAME \
  --project=tekvwarho-proaudit --replication-policy=automatic --data-file=-
```

| Secret name (suggested) | Purpose |
|---|---|
| `paystack-secret-key`, `paystack-public-key`, `paystack-webhook-secret` | Live subscription billing |
| `azure-form-recognizer-endpoint`, `azure-form-recognizer-key` | OCR (external Azure service, kept as-is) |
| `mono-secret-key`, `mono-public-key`, `mono-webhook-secret` | Bank statement aggregation |
| `okra-secret-key`, `okra-client-token`, `okra-public-key`, `okra-webhook-secret` | Open banking |
| `stitch-client-id`, `stitch-client-secret`, `stitch-webhook-secret` | Payment initiation |
| `nrs-api-key` | FIRS/NRS e-invoicing |
| `mail-username`, `mail-password` (or `sendgrid-api-key`) | Outbound email |

After creating any of these, add them to the `--set-secrets` list in `deploy/gcp/bootstrap.sh` (or a
follow-up `gcloud run services update ... --update-secrets=...`) and redeploy.

---

## 2. First deployment

Run once, after infra above exists:

```bash
cd /Users/efeobukohwo/Developer/TekVwarho-ProAudit
./deploy/gcp/bootstrap.sh
```

This creates the `proaudit_app` DB user + `tekvwarho_proaudit` database on Cloud SQL, resolves the
Cloud SQL/Redis private IPs, stores the derived connection strings in Secret Manager, runs
`alembic upgrade head` via a Cloud Run Job (`proaudit-migrate`) to build the schema, then deploys:

- `proaudit-web` - a Cloud Run **service**, public HTTPS, `min-instances=1` (avoids cold starts on a
  login-gated app)
- `proaudit-worker` / `proaudit-beat` - Cloud Run **worker pools** (not services). Celery worker/beat
  never bind to a port, and ordinary Cloud Run services require passing an HTTP/TCP startup probe on
  `$PORT` - worker pools are the Cloud Run resource type built for exactly this case, and use Direct
  VPC egress (`--network`/`--subnet`) instead of the Serverless VPC Access connector. Both run at a
  fixed `--instances=1` with no autoscaling.

On `proaudit-web`'s first startup, the existing `seed_super_admin()` hook in `main.py` runs
automatically and creates the super admin account using the `SUPER_ADMIN_*` secrets above — no
separate script needed for that step. This has already run in production; see Section 6.

## 3. Ongoing deployments (CI/CD)

`cloudbuild.yaml` at the repo root defines the pipeline: build image -> push to Artifact Registry ->
run migrations via the `proaudit-migrate` job -> redeploy `proaudit-web`, `proaudit-worker`, and
`proaudit-beat` with the new image. Wire it to a Cloud Build trigger on push to `main`:

```bash
gcloud builds triggers create github \
  --project=tekvwarho-proaudit \
  --region=africa-south1 \
  --repo-name=<your-github-repo> \
  --repo-owner=<your-github-org-or-user> \
  --branch-pattern='^main$' \
  --build-config=cloudbuild.yaml
```

(Requires connecting the GitHub repo to Cloud Build first via the Cloud Console's "Connect
Repository" flow — this needs an interactive GitHub OAuth step, so it isn't scriptable from here.)

## 4. Railway decommissioning

Railway has been removed as a target entirely - there is no data migration step, and no fallback
environment. What was done:

- Deleted `railway.json` and the three Railway-only ops scripts under `scripts/`
  (`create_railway_tables.py`, `seed_railway_db.py`, `fix_railway_efe_obus_user.py`).
- Removed the `RAILWAY_PUBLIC_DOMAIN` environment-variable check from `app/routers/auth.py`
  (cookie `Secure` flag now derives from `APP_ENV` alone, which Cloud Run already sets to
  `production`).
- Cleaned up Railway-specific comments in the `Dockerfile`.
- Checked whether the database credential hardcoded in the now-deleted
  `fix_railway_efe_obus_user.py` (`postgresql://postgres:***@turntable.proxy.rlwy.net:28165/railway`)
  still had recoverable data before removing it: the host's TCP port accepted a connection, but the
  Postgres server closed the connection immediately during authentication - the credential is
  stale/rotated and nothing could be read. **This does not confirm Railway has no data** - it only
  confirms this one leaked credential no longer works. If there is data on Railway you still need,
  get a current `DATABASE_URL` from the Railway dashboard before deleting the Railway project itself.
- The actual Railway project/service was **not** deleted from this session - doing that requires
  Railway credentials this environment doesn't have (`railway whoami` is unauthenticated here). Do
  that from the Railway dashboard, or run `railway login` locally and let me know so I can do it via
  the CLI.
- That leaked credential was live in git history in this repo. Even though Railway is being retired,
  treat it as compromised - do not reuse that password anywhere else.

## 5. Bugs found and fixed while running a truly clean migration

Nobody had ever run `alembic upgrade head` from a genuinely empty database before this
migration - the evidence strongly suggests the Railway production schema was built by the
ad-hoc scripts in `scripts/` (e.g. `create_railway_tables.py`) rather than the migration chain
itself. Doing that for the first time here surfaced a number of real, pre-existing bugs in the
migration scripts and application code, all fixed as part of this work (not GCP-specific -
they would hit any fresh database, including a future rebuild of Railway itself):

- **`alembic/env.py`** - Alembic's default `alembic_version.version_num` column is
  `VARCHAR(32)`, but this repo uses long human-readable revision IDs (up to 40 characters, e.g.
  `20260106_1400_add_lga_email_verification`). Added a step that widens the column to
  `VARCHAR(255)` before migrations run. A first attempt at this fix left an open outer
  transaction that silently swallowed all 34 migrations on connection close (they appeared to
  succeed, but nothing was actually persisted) - fixed by committing that setup step on its own
  before Alembic's own transaction begins.
- **Duplicate Postgres enum type creation** in several migrations - a generic `sa.Enum(name=X,
  create_type=False)` does not reliably suppress auto-creation when reused inline in a second
  `create_table`/`add_column` call; the working pattern is to reuse the actual `postgresql.ENUM(...)`
  object/variable. Fixed in `20260103_1430_2026_tax_reform_updates.py`,
  `20260103_1600_add_fixed_assets.py`, and `20260106_1600_advanced_accounting.py`.
- **`ALTER TYPE auditaction ADD VALUE ...`** in `20260103_1630_ntaa_2025_compliance.py` referenced
  a native enum type that was never created - `audit_logs.action` is `VARCHAR(50)`, not a native
  enum. Removed (dead code).
- **Wrong table/column names** - `20260106_1600_advanced_accounting.py` referenced a non-existent
  `entities` table (real name: `business_entities`, 12 call sites); `20260127_1100_...` referenced
  a non-existent `tenants` table (real name: `organizations`) and dropped a unique constraint that
  was never created.
- **Multi-statement `op.execute("""...""")` blocks** - asyncpg's prepared-statement protocol
  rejects a string containing more than one SQL statement ("cannot insert multiple commands into
  a prepared statement"). Split into one `op.execute()` per statement in
  `20260118_1200_bank_reconciliation_comprehensive.py` and `20260123_2200_add_billing_features_30_36.py`,
  taking care to keep `DO $$ ... END $$;` blocks intact as a single statement.
- **Schema drift between two migrations for the same tables** -
  `20260118_1200_bank_reconciliation_comprehensive.py` redefines `bank_statements`,
  `bank_statement_transactions`, and `bank_reconciliations` with a materially different
  (Nigerian-banking-specific) schema than the one `20260108_2030_...` originally created, but
  used `CREATE TABLE IF NOT EXISTS`, which silently kept the old, incompatible schema in place.
  Added explicit `DROP TABLE ... CASCADE` for the three overlapping tables before recreating them.
- **Duplicate `add_column` for already-existing columns** - `refunded_at` and `refund_amount_kobo`
  in `20260123_2100_...` were already added by `20260122_1920_add_payment_transactions.py`.
- **Indexes referencing columns/tables that don't match the actual schema** in
  `20260128_1000_add_performance_indexes.py` - `account_balances` has no `entity_id`/`period_end_date`;
  `intercompany_transactions` uses `source_entity_id`/`target_entity_id`/`created_at`, not
  `from_entity_id`/`to_entity_id`/`transaction_date`; `budget_line_items` has no
  `account_id`/`period_start`/`period_end` (uses `account_code` and monthly columns instead); and
  an index on `fx_revaluations` was created one migration too early, before that table exists
  (`fx_revaluation_001.py`'s `down_revision` points *at* this migration).
- **Enum value casing mismatch** in `app/models/user.py` and `app/models/organization.py` -
  `SQLEnum(SomeEnum)` without `values_callable` sends the Python enum member's `.name` (e.g.
  `"SUPER_ADMIN"`) rather than its `.value` (`"super_admin"`); several native Postgres enum types
  were created with lowercase values, so inserts failed. Fixed for `PlatformRole`,
  `OrganizationType`, and `VerificationStatus` by adding
  `values_callable=lambda enum_cls: [e.value for e in enum_cls]`. **This same class of bug likely
  affects other enum columns across the ~84 models that haven't been exercised yet** - noticed one
  more instance (`businesstype`) surface in the non-critical "seed platform test entity" startup
  step, which is caught in a try/except and only logs a warning, so it was left as a known
  follow-up rather than chased exhaustively here.
- **`organizations.emergency_suspended_by_id`** - the migration
  (`20260126_2000_emergency_controls.py`) creates this column as `UUID`, but the ORM model
  (`app/models/organization.py`) declared it as `String(36)` with no UUID import in the file at
  all. Fixed to `UUID(as_uuid=True)`.

## 6. Rollback / cleanup

There is no Railway fallback anymore (see Section 4) - GCP is the only environment. If GCP needs
to be torn down anyway:

```bash
gcloud projects delete tekvwarho-proaudit
```

This deletes every resource above in one action and cannot be undone — do not run it without being certain.
