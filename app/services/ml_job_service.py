"""
Tekvwa Pro Audit - ML Job Service

Service layer for managing ML jobs and models.
Super Admin only feature for platform ML operations.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ml_job import (
    MLJob,
    MLModel,
    MLJobType,
    MLJobStatus,
    MLJobPriority,
)


class MLJobService:
    """Service for managing ML jobs."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_ml_job(
        self,
        job_type: MLJobType,
        job_name: Optional[str] = None,
        priority: MLJobPriority = MLJobPriority.NORMAL,
        model_id: Optional[uuid.UUID] = None,
        organization_id: Optional[uuid.UUID] = None,
        parameters: Optional[Dict[str, Any]] = None,
        scheduled_for: Optional[datetime] = None,
    ) -> MLJob:
        """Create a new ML job."""
        job_id = await self._generate_job_id()
        
        # Auto-generate job name if not provided
        if not job_name:
            job_name = f"{job_type.value.replace('_', ' ').title()} - {job_id}"
        
        ml_job = MLJob(
            job_id=job_id,
            job_name=job_name,
            job_type=job_type,
            status=MLJobStatus.QUEUED,
            priority=priority,
            model_id=model_id,
            organization_id=organization_id,
            parameters=parameters or {},
            scheduled_for=scheduled_for,
            queued_at=datetime.utcnow(),
        )
        
        self.db.add(ml_job)
        await self.db.commit()
        await self.db.refresh(ml_job)
        
        return ml_job
    
    async def get_ml_job(self, job_id: uuid.UUID) -> Optional[MLJob]:
        """Get an ML job by ID."""
        result = await self.db.execute(
            select(MLJob).where(MLJob.id == job_id)
        )
        return result.scalar_one_or_none()
    
    async def get_ml_job_by_job_id(self, job_id: str) -> Optional[MLJob]:
        """Get an ML job by job_id string."""
        result = await self.db.execute(
            select(MLJob).where(MLJob.job_id == job_id)
        )
        return result.scalar_one_or_none()
    
    async def get_all_ml_jobs(
        self,
        status: Optional[MLJobStatus] = None,
        job_type: Optional[MLJobType] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[MLJob]:
        """Get all ML jobs with optional filters."""
        query = select(MLJob)
        
        conditions = []
        if status:
            conditions.append(MLJob.status == status)
        if job_type:
            conditions.append(MLJob.job_type == job_type)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        query = query.order_by(desc(MLJob.created_at))
        query = query.offset(offset).limit(limit)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_ml_jobs_stats(self) -> Dict[str, Any]:
        """Get statistics for ML jobs."""
        # Running jobs
        running = await self.db.execute(
            select(func.count(MLJob.id)).where(
                MLJob.status == MLJobStatus.RUNNING
            )
        )
        running_count = running.scalar() or 0
        
        # Pending jobs
        pending = await self.db.execute(
            select(func.count(MLJob.id)).where(
                MLJob.status == MLJobStatus.QUEUED
            )
        )
        pending_count = pending.scalar() or 0
        
        # Failed (last 24h)
        yesterday = datetime.utcnow() - timedelta(hours=24)
        failed = await self.db.execute(
            select(func.count(MLJob.id)).where(
                and_(
                    MLJob.status == MLJobStatus.FAILED,
                    MLJob.completed_at >= yesterday
                )
            )
        )
        failed_count = failed.scalar() or 0
        
        # Completed (last 24h)
        completed = await self.db.execute(
            select(func.count(MLJob.id)).where(
                and_(
                    MLJob.status == MLJobStatus.COMPLETED,
                    MLJob.completed_at >= yesterday
                )
            )
        )
        completed_count = completed.scalar() or 0
        
        return {
            "running": running_count,
            "pending": pending_count,
            "failed_24h": failed_count,
            "completed_24h": completed_count,
        }
    
    async def start_job(self, job_id: uuid.UUID, worker_id: Optional[str] = None) -> MLJob:
        """Start an ML job."""
        job = await self.get_ml_job(job_id)
        if not job:
            raise ValueError(f"ML job {job_id} not found")
        
        if job.status not in [MLJobStatus.QUEUED, MLJobStatus.RETRYING]:
            raise ValueError(f"Job is not in a startable state: {job.status}")
        
        job.status = MLJobStatus.RUNNING
        job.started_at = datetime.utcnow()
        job.worker_id = worker_id
        
        await self.db.commit()
        await self.db.refresh(job)
        
        return job
    
    async def complete_job(
        self,
        job_id: uuid.UUID,
        results: Optional[Dict[str, Any]] = None,
        metrics: Optional[Dict[str, Any]] = None,
        output_files: Optional[List[str]] = None,
    ) -> MLJob:
        """Complete an ML job successfully."""
        job = await self.get_ml_job(job_id)
        if not job:
            raise ValueError(f"ML job {job_id} not found")
        
        job.status = MLJobStatus.COMPLETED
        job.completed_at = datetime.utcnow()
        job.progress_percent = 100
        
        if job.started_at:
            job.execution_time_seconds = int(
                (job.completed_at - job.started_at).total_seconds()
            )
        
        job.results = results or {}
        job.metrics = metrics or {}
        job.output_files = output_files
        
        await self.db.commit()
        await self.db.refresh(job)
        
        return job
    
    async def fail_job(
        self,
        job_id: uuid.UUID,
        error_message: str,
        error_details: Optional[Dict[str, Any]] = None,
    ) -> MLJob:
        """Mark an ML job as failed."""
        job = await self.get_ml_job(job_id)
        if not job:
            raise ValueError(f"ML job {job_id} not found")
        
        job.status = MLJobStatus.FAILED
        job.completed_at = datetime.utcnow()
        job.error_message = error_message
        job.error_details = error_details
        job.retry_count = (job.retry_count or 0) + 1
        
        await self.db.commit()
        await self.db.refresh(job)
        
        return job
    
    async def update_progress(
        self,
        job_id: uuid.UUID,
        progress_percent: int,
        current_step: Optional[str] = None,
    ) -> MLJob:
        """Update job progress."""
        job = await self.get_ml_job(job_id)
        if not job:
            raise ValueError(f"ML job {job_id} not found")
        
        job.progress_percent = min(progress_percent, 100)
        job.current_step = current_step
        
        await self.db.commit()
        await self.db.refresh(job)
        
        return job
    
    async def cancel_job(self, job_id: uuid.UUID) -> MLJob:
        """Cancel an ML job."""
        job = await self.get_ml_job(job_id)
        if not job:
            raise ValueError(f"ML job {job_id} not found")
        
        if job.status in [MLJobStatus.COMPLETED, MLJobStatus.CANCELLED]:
            raise ValueError(f"Job cannot be cancelled: {job.status}")
        
        job.status = MLJobStatus.CANCELLED
        job.completed_at = datetime.utcnow()
        
        await self.db.commit()
        await self.db.refresh(job)
        
        return job
    
    # ML Model methods
    
    async def create_model(
        self,
        model_name: str,
        model_version: str,
        model_type: MLJobType,
        algorithm: str,
        framework: str = "scikit-learn",
        description: Optional[str] = None,
        accuracy: Optional[float] = None,
        hyperparameters: Optional[Dict[str, Any]] = None,
        feature_names: Optional[List[str]] = None,
        model_path: Optional[str] = None,
    ) -> MLModel:
        """Create a new ML model."""
        model = MLModel(
            model_name=model_name,
            model_version=model_version,
            model_type=model_type,
            algorithm=algorithm,
            framework=framework,
            description=description,
            accuracy=accuracy,
            hyperparameters=hyperparameters or {},
            feature_names=feature_names,
            model_path=model_path,
            is_active=True,
        )
        
        self.db.add(model)
        await self.db.commit()
        await self.db.refresh(model)
        
        return model
    
    async def get_model(self, model_id: uuid.UUID) -> Optional[MLModel]:
        """Get an ML model by ID."""
        result = await self.db.execute(
            select(MLModel).where(MLModel.id == model_id)
        )
        return result.scalar_one_or_none()
    
    async def get_all_models(
        self,
        model_type: Optional[MLJobType] = None,
        is_active: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[MLModel]:
        """Get all ML models with optional filters."""
        query = select(MLModel)
        
        conditions = []
        if model_type:
            conditions.append(MLModel.model_type == model_type)
        if is_active is not None:
            conditions.append(MLModel.is_active == is_active)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        query = query.order_by(desc(MLModel.created_at))
        query = query.offset(offset).limit(limit)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_models_stats(self) -> Dict[str, Any]:
        """Get statistics for ML models."""
        # Total models
        total = await self.db.execute(
            select(func.count(MLModel.id))
        )
        total_count = total.scalar() or 0
        
        # Active models
        active = await self.db.execute(
            select(func.count(MLModel.id)).where(MLModel.is_active == True)
        )
        active_count = active.scalar() or 0
        
        # Average accuracy
        avg_accuracy = await self.db.execute(
            select(func.avg(MLModel.accuracy)).where(MLModel.accuracy.isnot(None))
        )
        average_accuracy = avg_accuracy.scalar()
        
        # Models by type
        by_type = await self.db.execute(
            select(MLModel.model_type, func.count(MLModel.id))
            .group_by(MLModel.model_type)
        )
        models_by_type = {str(row[0]): row[1] for row in by_type.all()}
        
        return {
            "total": total_count,
            "active": active_count,
            "average_accuracy": round(average_accuracy, 2) if average_accuracy else None,
            "by_type": models_by_type,
        }
    
    async def activate_model(self, model_id: uuid.UUID) -> MLModel:
        """Activate an ML model."""
        model = await self.get_model(model_id)
        if not model:
            raise ValueError(f"ML model {model_id} not found")
        
        model.is_active = True
        model.last_used_at = datetime.utcnow()
        
        await self.db.commit()
        await self.db.refresh(model)
        
        return model
    
    async def deactivate_model(self, model_id: uuid.UUID) -> MLModel:
        """Deactivate an ML model."""
        model = await self.get_model(model_id)
        if not model:
            raise ValueError(f"ML model {model_id} not found")
        
        model.is_active = False
        
        await self.db.commit()
        await self.db.refresh(model)
        
        return model
    
    async def _generate_job_id(self) -> str:
        """Generate a unique job ID."""
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        random_suffix = uuid.uuid4().hex[:6].upper()
        return f"MLJ-{timestamp}-{random_suffix}"
