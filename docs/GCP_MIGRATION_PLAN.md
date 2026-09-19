# Tekvwa Pro Audit — Google Cloud Migration Plan

**Status:** Draft for review
**Scope:** Move the full stack (app, database, cache/queue, file storage, CI/CD) off Railway onto Google Cloud Platform.

---

## 1. Current State (as-built)

| Layer | Current implementation | Notes |
|---|---|---|
| App | FastAPI (`main.py`), Jinja2 server-rendered templates + static assets, single Docker image | Deployed on **Railway** via `railway.json` / `Dockerfile`, `uvicorn main:app` on `$PORT` |
| Database | PostgreSQL, SQLAlchemy 2.0 async (`asyncpg`), Alembic (35 migrations) | `app/database.py` — pool_size=5, max_overflow=10, `pool_pre_ping=True` |
| Cache / queue | Redis — used for caching AND as Celery broker + result backend | `app/celery_app.py`, `REDIS_URL` |
| Background jobs | Celery worker + Celery beat (scheduled tasks, e.g. daily data-retention cleanup at 3am) | Run as separate containers in `docker-compose.yml`, not yet defined for Railway prod |
| File storage | `FileStorageService` — Azure Blob Storage if `azure_storage_connection_string` is set, else local disk `./uploads` | `app/services/file_storage_service.py` |
| OCR | Azure Form Recognizer / Document Intelligence (external API) | Not infrastructure — stays as-is unless you want to swap to Document AI later |
| Payments / open banking | Paystack, Mono, Okra, Stitch, FIRS/NRS e-invoicing | External SaaS APIs — no infra migration needed, only need egress + webhook reachability |
| ML | scikit-learn model loaded from a checked-in pickle (`ml_models/transaction_classifier.pkl`) | In-process, no separate serving infra today |
| Secrets/config | `.env` file / Railway environment variables (`app/config.py`, pydantic-settings) | ~40+ settings incl. JWT secret, Paystack keys, SMTP creds |
| Compliance | 7-year retention on payment transactions, 5-year NTAA retention enforced *in the database* (`audit_vault_service.py`), legal holds, immutable ledger — all at the application/DB layer, not object-storage layer | Relevant to backup & retention design below |

This is a single-region, single-container monolith today — a good fit for **Cloud Run**, not a case that needs GKE.

---

## 2. Target GCP Architecture

| Current | GCP target | Why |
|---|---|---|
| Railway container (web) | **Cloud Run service** (`proaudit-web`) | Serverless, autoscales, HTTPS by default, pay-per-use, minimal ops |
| Celery worker (not yet in prod) | **Cloud Run service** with `min-instances=1`, no public ingress (`proaudit-worker`), driven by Pub/Sub or polling Redis | Cloud Run now supports always-on background services; simplest path without standing up GKE |
| Celery beat (scheduler) | **Cloud Scheduler → Cloud Run job / HTTP endpoint**, replacing celery-beat's cron loop | Removes a second always-on container; Scheduler is purpose-built and free at this volume |
| Railway Postgres | **Cloud SQL for PostgreSQL** (private IP), read replica optional later | Managed backups, PITR, HA option |
| Redis (Railway/self-hosted) | **Memorystore for Redis** (Basic tier to start) | Managed, VPC-internal, low-latency for cache + Celery broker |
| Azure Blob (prod file storage) | **Cloud Storage (GCS) bucket** per environment | New `gcs` provider added to `FileStorageService`; keeps local fallback for dev |
| `.env` / Railway vars | **Secret Manager** + Cloud Run env var references | Central secret rotation, IAM-scoped access, audit logging on secret reads |
| No CI/CD today (manual deploy?) | **Cloud Build** trigger on GitHub push → build image → push to **Artifact Registry** → deploy to Cloud Run | Reuses existing multi-stage `Dockerfile` almost unchanged |
| No WAF/edge | **Cloud Load Balancing + Cloud Armor** (optional, recommended given this is financial/audit data) | Rate limiting, geo restriction, OWASP rule sets in front of Cloud Run |
| Logs (Railway console) | **Cloud Logging + Cloud Monitoring** (uptime checks, alerting) | Structured logs already via `logging` module; minimal changes needed |
| Nigeria-Tax-Act PDF, ml_models pickle | Bundled in image (unchanged) or moved to GCS if it grows | Both are small (<2MB); no need to externalize yet |

---

## 3. Code changes required (before infra cutover)

These are small, contained changes — doing them first de-risks the infra move:

1. **`app/services/file_storage_service.py`** — add a `StorageProvider.GCS` branch (`google-cloud-storage` SDK), selected when `GCS_BUCKET_NAME` is set, mirroring the existing Azure branch (`_upload_to_gcs`, `_download_from_gcs`, `_delete_from_gcs`, `_list_gcs_files`, signed URLs via `blob.generate_signed_url`). Keep Azure branch for a transition period so old file URLs stored in the DB (if any use Azure paths) still resolve.
2. **`app/config.py`** — add `gcs_bucket_name`, `gcs_project_id`, `database_url` sourced from Cloud SQL connector or private IP, keep `redis_url` pointed at Memorystore's internal IP.
3. **`app/database.py`** — no code change needed if connecting via private IP/VPC connector; if using the Cloud SQL Auth Proxy/connector library instead, swap the engine creation to use `google-cloud-sql-connector`'s `Connector` + `asyncpg` creator function.
4. **Celery beat → Cloud Scheduler**: extract the scheduled task list from `celery_app.py`'s beat schedule into individual HTTP-triggered endpoints (or Cloud Run Jobs) that Cloud Scheduler calls directly — avoids running a second long-lived container just for cron.
5. **Dockerfile**: unchanged in structure; just confirm `CMD` still reads `$PORT` (Cloud Run also injects `PORT=8080` — already compatible).
6. **Health check**: `/health` already exists (used by Railway) — reuse directly for Cloud Run startup/liveness probe and the load balancer health check.
7. Remove `SUPER_ADMIN_PASSWORD` and other bootstrap secrets from `.env`-style files entirely; source only from Secret Manager in every environment.

---

## 4. Migration Phases

### Phase 0 — Foundation (½–1 day)
- Create GCP project(s): recommend separate `proaudit-staging` and `proaudit-prod` projects (or folders) for hard isolation of prod data.
- Enable APIs: Cloud Run, Cloud SQL Admin, Memorystore, Secret Manager, Cloud Build, Artifact Registry, VPC Access, Cloud Scheduler, Cloud Storage, Cloud Logging/Monitoring.
- Set up a VPC + **Serverless VPC Access connector** (Cloud Run needs this to reach Cloud SQL private IP and Memorystore).
- Set up Artifact Registry repo for the Docker image.

### Phase 1 — Database (highest risk, plan carefully)
- Provision Cloud SQL for PostgreSQL (match current Postgres major version — repo assumes Postgres 15 per `docker-compose.yml`).
- **Migration method** — two options depending on acceptable downtime:
  - **A. Simple dump/restore (recommended for a first migration at this stage/size)**: `pg_dump` from Railway → `pg_restore`/`psql` into Cloud SQL during a scheduled maintenance window. Run `alembic upgrade head` against Cloud SQL first (empty schema) or restore schema+data directly, then verify `alembic current` matches.
  - **B. Near-zero-downtime via Database Migration Service (DMS)**: requires logical replication (`wal_level=logical`) enabled on the Railway source — check whether Railway's managed Postgres exposes this; if not, fall back to Option A.
- Validate row counts and spot-check critical tables (journal entries, GL accounts, payment_transactions) post-migration, per the existing checklist pattern in `docs/MIGRATION_GUIDE.md`.
- Configure automated backups + point-in-time recovery on Cloud SQL matching the retention requirements already enforced in `audit_vault_service.py` (5–7 year data retention).

### Phase 2 — Cache/Queue
- Provision Memorystore for Redis (Basic tier is fine pre-scale; Standard/HA tier once revenue justifies it).
- Point `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` at the Memorystore internal IP via the VPC connector.

### Phase 3 — File Storage
- Create GCS bucket(s), one per environment, with versioning enabled and a lifecycle rule mirroring current retention config (`USAGE_RECORDS_RETENTION_DAYS`, `PAYMENT_TRANSACTIONS_RETENTION_DAYS`, etc.).
- Ship the `GCS` provider code change (Section 3.1).
- **Correction from initial draft**: `azure_storage_connection_string` is read via `getattr()` in `file_storage_service.py` but was never declared as a field on the `Settings` model in `config.py`, so `getattr` always returns `None` and the Azure Blob branch has never actually been reachable at runtime. Production file storage on Railway has been local disk inside the container the whole time — which does not persist across restarts/redeploys. There is no Azure Blob content to bulk-migrate. Any files that matter should be recovered from the live Railway container's `./uploads` directory (if still running) before cutover, since nothing else has a durable copy.
- Cut `FileStorageService` over to GCS via config from day one; the Azure branch stays in the code only for future use if Azure is ever wired up correctly, not for a migration path.

### Phase 4 — Compute
- Build and push the existing Docker image to Artifact Registry.
- Deploy `proaudit-web` to Cloud Run: attach VPC connector, set min-instances ≥1 (avoid cold-start on a login-gated finance app), configure concurrency, mount secrets from Secret Manager as env vars.
- Deploy `proaudit-worker` (Celery worker) as a second Cloud Run service or Cloud Run **worker pool** (no HTTP ingress needed) — same image, different `CMD`.
- Replace celery-beat with Cloud Scheduler jobs hitting authenticated internal endpoints (or `gcloud scheduler jobs create http` invoking a Cloud Run Job for one-off batch tasks like the daily retention cleanup).

### Phase 5 — Networking, Secrets, Domain
- Move every secret in `.env.example` into Secret Manager; grant the Cloud Run service account `roles/secretmanager.secretAccessor` scoped per-secret, not project-wide.
- Map custom domain to Cloud Run directly, or front with an external HTTPS Load Balancer + Cloud Armor if you want WAF/rate-limiting (recommended given Paystack/webhook and open-banking integrations are attack surface).
- Update CORS_ORIGINS, webhook URLs registered with Paystack/Mono/Okra/Stitch/FIRS to the new domain before DNS cutover.

### Phase 6 — CI/CD
- Add `cloudbuild.yaml`: build image → push to Artifact Registry → `gcloud run deploy`.
- Cloud Build trigger on push to `main` (prod) and a separate trigger for a `staging` branch/tag.
- Run `alembic upgrade head` as a Cloud Build step (or a Cloud Run Job) before traffic is shifted to the new revision.

### Phase 7 — Cutover
- Stand up staging fully on GCP first; run the existing test suite (`tests/`) against it.
- Do a dry-run data migration into a scratch Cloud SQL instance to time it and rehearse the checklist.
- Final cutover: short maintenance window → final incremental `pg_dump`/WAL catch-up → DNS switch → smoke test critical flows (login, invoice creation, Paystack checkout, file upload/download, a Celery-driven task).
- **Update, post-migration:** Railway was decommissioned immediately rather than kept as a rollback window — see `docs/GCP_DEPLOYMENT.md` Section 4 for what was removed and what's still outstanding (the actual Railway project/service itself needs deleting from the Railway dashboard, or via CLI once authenticated).

---

## 5. Rough Monthly Cost Shape (order-of-magnitude, low traffic)

| Service | Est. |
|---|---|
| Cloud Run (web + worker, low traffic, min-instances=1 each) | $30–80 |
| Cloud SQL (db-f1-micro/small, HA off initially) | $30–90 |
| Memorystore Basic (1GB) | $35 |
| Cloud Storage + egress | $5–20 |
| VPC connector, Scheduler, Logging | $10–20 |
| **Total** | **~$110–250/mo** at low scale, before Cloud Armor/HA |

(This is directional only — real numbers depend on traffic, instance sizing, and whether you enable Cloud SQL HA / Redis Standard tier.)

---

## 6. Open Decisions (need your input)

1. **Downtime tolerance for the DB cutover** — is a short maintenance window (dump/restore) acceptable, or does this need near-zero-downtime (DMS), which depends on whether Railway Postgres allows logical replication?
2. **Celery worker hosting** — Cloud Run worker pool (simplest, newer GA feature) vs. GKE Autopilot (more control, more ops) — do you have a preference or constraint pushing toward GKE?
3. **Single GCP project vs. staging/prod project split** — recommended for this kind of compliance-sensitive app, but changes IAM setup scope.
4. **Cloud Armor / Load Balancer now or later** — adds cost and setup time; could be deferred to a fast-follow if you want the fastest possible first migration.
5. **Timeline/deadline** — is there a target date (e.g., a Railway billing or reliability issue forcing this) that should set the pace of phases above?

---

## 7. Suggested Next Step

Once the open decisions above are answered, the first concrete implementation task is **Phase 0 + the `FileStorageService` GCS provider code change (Section 3.1)** — both are low-risk, reversible, and unblock everything else.
