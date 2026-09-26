"""
Regression coverage for Finding 50's ml_job.py column drift
(docs/FINDING_50_SCOPE.md, docs/REMEDIATION_LOG.md).

app/services/ml_job_service.py is the only real construction site for both MLJob and MLModel.
For MLJob, the service already used job_name/queued_at/organization_id, none of which existed on
the live table (which has target_organization_id instead of organization_id, with zero real
code ever referencing it) -- every create_ml_job() call has always failed with an
UndefinedColumnError. job_type/status/priority were also declared as native SQLAlchemy enums
while the live columns are plain VARCHAR -- fixed to plain String columns to match. worker_id/
results/metrics/output_files/error_details existed on the live table but were unmapped, so every
start_job()/complete_job()/fail_job() call silently discarded those writes even once a job could
be created. For MLModel, the live table already matched the service's real field names
(model_name/model_version/feature_names/model_path/precision_score/recall_score/
training_samples_count) -- the model class had the wrong names entirely (name/version/
feature_columns/artifact_path/precision/recall/training_data_size) -- a pure model rewrite,
zero migration needed for MLModel.
"""
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.services.ml_job_service import MLJobService
from app.models.ml_job import MLJobPriority, MLJobStatus, MLJobType


class TestMLJobPersistence:
    async def test_create_job_matches_real_construction(
        self, db_session: AsyncSession, test_organization: Organization,
    ):
        service = MLJobService(db_session)
        job = await service.create_ml_job(
            job_type=MLJobType.ANOMALY_DETECTION,
            organization_id=test_organization.id,
            priority=MLJobPriority.HIGH,
        )

        assert job.id is not None
        assert job.job_id.startswith("MLJ-")
        assert job.job_name
        assert job.status == MLJobStatus.QUEUED
        assert job.organization_id == test_organization.id
        assert job.queued_at is not None

    async def test_full_lifecycle_start_complete(
        self, db_session: AsyncSession, test_organization: Organization,
    ):
        service = MLJobService(db_session)
        job = await service.create_ml_job(
            job_type=MLJobType.RISK_SCORING,
            organization_id=test_organization.id,
        )

        started = await service.start_job(job.id, worker_id="worker-1")
        assert started.status == MLJobStatus.RUNNING
        assert started.worker_id == "worker-1"
        assert started.started_at is not None

        completed = await service.complete_job(
            job.id,
            results={"anomalies": 3},
            metrics={"auc": 0.91},
            output_files=["report.csv"],
        )
        assert completed.status == MLJobStatus.COMPLETED
        assert completed.results == {"anomalies": 3}
        assert completed.metrics == {"auc": 0.91}
        assert completed.output_files == ["report.csv"]
        assert completed.execution_time_seconds is not None

    async def test_fail_job_persists_error_details(
        self, db_session: AsyncSession, test_organization: Organization,
    ):
        service = MLJobService(db_session)
        job = await service.create_ml_job(
            job_type=MLJobType.MODEL_TRAINING,
            organization_id=test_organization.id,
        )

        failed = await service.fail_job(
            job.id,
            error_message="Out of memory",
            error_details={"code": "OOM"},
        )
        assert failed.status == MLJobStatus.FAILED
        assert failed.error_message == "Out of memory"
        assert failed.error_details == {"code": "OOM"}
        assert failed.retry_count == 1


class TestMLModelPersistence:
    async def test_create_model_matches_real_construction(
        self, db_session: AsyncSession,
    ):
        service = MLJobService(db_session)
        model = await service.create_model(
            model_name="Anomaly Detector",
            model_version="1.0.0",
            model_type=MLJobType.ANOMALY_DETECTION,
            algorithm="IsolationForest",
            accuracy=0.95,
            feature_names=["amount", "vendor_frequency"],
            model_path="/models/anomaly_v1.pkl",
        )

        assert model.id is not None
        assert model.model_name == "Anomaly Detector"
        assert model.model_version == "1.0.0"
        assert model.is_active is True
        assert model.feature_names == ["amount", "vendor_frequency"]

    async def test_activate_deactivate_and_stats(
        self, db_session: AsyncSession,
    ):
        service = MLJobService(db_session)
        model = await service.create_model(
            model_name="Risk Scorer",
            model_version="2.1.0",
            model_type=MLJobType.RISK_SCORING,
            algorithm="GradientBoostingClassifier",
            accuracy=0.88,
        )

        deactivated = await service.deactivate_model(model.id)
        assert deactivated.is_active is False

        reactivated = await service.activate_model(model.id)
        assert reactivated.is_active is True
        assert reactivated.last_used_at is not None

        stats = await service.get_models_stats()
        assert stats["total"] == 1
        assert stats["active"] == 1
        assert stats["by_type"] == {"risk_scoring": 1}


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
