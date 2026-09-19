#!/bin/bash
#
# TekVwarho ProAudit - GCP first-time deployment bootstrap
#
# Runs once, after the base infrastructure (project, VPC, VPC connector,
# Cloud SQL, Memorystore, GCS buckets, Artifact Registry, Secret Manager
# secrets) already exists. It creates the application database/user on
# Cloud SQL, wires the remaining Secret Manager references, and deploys
# the three Cloud Run services (web, worker, beat) plus the migration job
# for the first time.
#
# Re-runs of ordinary deploys after this go through cloudbuild.yaml, not
# this script.
#
set -euo pipefail

PROJECT="tekvwarho-proaudit"
REGION="africa-south1"
SQL_INSTANCE="proaudit-db"
DB_NAME="tekvwarho_proaudit"
DB_USER="proaudit_app"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/proaudit-repo/proaudit:initial"
SA_EMAIL="proaudit-run-sa@${PROJECT}.iam.gserviceaccount.com"
CONNECTOR="proaudit-connector"

echo "== Reading DB password from Secret Manager =="
DB_PASSWORD=$(gcloud secrets versions access latest --secret=postgres-password --project="$PROJECT")

echo "== Creating application database and user on Cloud SQL =="
gcloud sql databases create "$DB_NAME" --instance="$SQL_INSTANCE" --project="$PROJECT" || echo "  (database may already exist, continuing)"
gcloud sql users create "$DB_USER" --instance="$SQL_INSTANCE" --password="$DB_PASSWORD" --project="$PROJECT" || echo "  (user may already exist, continuing)"

echo "== Resolving Cloud SQL private IP =="
DB_PRIVATE_IP=$(gcloud sql instances describe "$SQL_INSTANCE" --project="$PROJECT" \
  --format='value(ipAddresses[0].ipAddress)')
echo "  Cloud SQL private IP: $DB_PRIVATE_IP"

echo "== Resolving Memorystore Redis IP =="
REDIS_IP=$(gcloud redis instances describe proaudit-redis --region="$REGION" --project="$PROJECT" \
  --format='value(host)')
echo "  Redis private IP: $REDIS_IP"

DATABASE_URL="postgresql://${DB_USER}:${DB_PASSWORD}@${DB_PRIVATE_IP}:5432/${DB_NAME}"
DATABASE_URL_ASYNC="postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@${DB_PRIVATE_IP}:5432/${DB_NAME}"
REDIS_URL="redis://${REDIS_IP}:6379/0"

echo "== Storing derived connection strings in Secret Manager =="
printf '%s' "$DATABASE_URL" | gcloud secrets create database-url --project="$PROJECT" --replication-policy=automatic --data-file=- 2>/dev/null \
  || printf '%s' "$DATABASE_URL" | gcloud secrets versions add database-url --project="$PROJECT" --data-file=-
printf '%s' "$DATABASE_URL_ASYNC" | gcloud secrets create database-url-async --project="$PROJECT" --replication-policy=automatic --data-file=- 2>/dev/null \
  || printf '%s' "$DATABASE_URL_ASYNC" | gcloud secrets versions add database-url-async --project="$PROJECT" --data-file=-
printf '%s' "$REDIS_URL" | gcloud secrets create redis-url --project="$PROJECT" --replication-policy=automatic --data-file=- 2>/dev/null \
  || printf '%s' "$REDIS_URL" | gcloud secrets versions add redis-url --project="$PROJECT" --data-file=-

# Common --set-secrets mapping: ENV_VAR=secret-name:latest
SECRETS_MAP="SECRET_KEY=secret-key:latest,\
JWT_SECRET_KEY=jwt-secret-key:latest,\
DATABASE_URL=database-url:latest,\
DATABASE_URL_ASYNC=database-url-async:latest,\
REDIS_URL=redis-url:latest,\
SUPER_ADMIN_EMAIL=super-admin-email:latest,\
SUPER_ADMIN_PASSWORD=super-admin-password:latest,\
SUPER_ADMIN_FIRST_NAME=super-admin-first-name:latest,\
SUPER_ADMIN_LAST_NAME=super-admin-last-name:latest"

ENV_VARS="APP_ENV=production,DEBUG=False,GCS_BUCKET_NAME=tekvwarho-proaudit-files,GCS_PROJECT_ID=${PROJECT}"

echo "== Deploying migration Cloud Run Job =="
gcloud run jobs create proaudit-migrate \
  --project="$PROJECT" \
  --region="$REGION" \
  --image="$IMAGE" \
  --command=alembic \
  --args=upgrade,head \
  --vpc-connector="$CONNECTOR" \
  --vpc-egress=private-ranges-only \
  --service-account="$SA_EMAIL" \
  --set-env-vars="$ENV_VARS" \
  --set-secrets="$SECRETS_MAP" \
  --max-retries=1 \
  2>&1 || echo "  (job may already exist, use 'gcloud run jobs update' instead)"

echo "== Running migrations against the fresh Cloud SQL database =="
gcloud run jobs execute proaudit-migrate --project="$PROJECT" --region="$REGION" --wait

echo "== Deploying web service =="
gcloud run deploy proaudit-web \
  --project="$PROJECT" \
  --region="$REGION" \
  --image="$IMAGE" \
  --platform=managed \
  --vpc-connector="$CONNECTOR" \
  --vpc-egress=private-ranges-only \
  --service-account="$SA_EMAIL" \
  --min-instances=1 \
  --max-instances=10 \
  --concurrency=40 \
  --cpu=1 \
  --memory=1Gi \
  --port=8000 \
  --allow-unauthenticated \
  --set-env-vars="$ENV_VARS" \
  --set-secrets="$SECRETS_MAP"

# Celery worker/beat are background-only processes that never listen on a port, so they
# cannot run as ordinary Cloud Run services (which require binding to $PORT and passing an
# HTTP/TCP startup probe). They run as Cloud Run worker pools instead - a distinct resource
# type built for exactly this case, using Direct VPC egress (--network/--subnet) rather than
# the Serverless VPC Access connector.
echo "== Deploying Celery worker pool =="
gcloud run worker-pools deploy proaudit-worker \
  --project="$PROJECT" \
  --region="$REGION" \
  --image="$IMAGE" \
  --command=celery \
  --args=-A,app.celery_app,worker,--loglevel=info,--concurrency=4 \
  --network=proaudit-vpc \
  --subnet=proaudit-subnet \
  --vpc-egress=private-ranges-only \
  --service-account="$SA_EMAIL" \
  --instances=1 \
  --cpu=1 \
  --memory=1Gi \
  --set-env-vars="$ENV_VARS" \
  --set-secrets="$SECRETS_MAP"

echo "== Deploying Celery beat worker pool =="
gcloud run worker-pools deploy proaudit-beat \
  --project="$PROJECT" \
  --region="$REGION" \
  --image="$IMAGE" \
  --command=celery \
  --args=-A,app.celery_app,beat,--loglevel=info \
  --network=proaudit-vpc \
  --subnet=proaudit-subnet \
  --vpc-egress=private-ranges-only \
  --service-account="$SA_EMAIL" \
  --instances=1 \
  --cpu=1 \
  --memory=512Mi \
  --set-env-vars="$ENV_VARS" \
  --set-secrets="$SECRETS_MAP"

echo "== Done. Web service URL: =="
gcloud run services describe proaudit-web --project="$PROJECT" --region="$REGION" --format='value(status.url)'
