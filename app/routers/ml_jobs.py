"""
Tekvwa Pro Audit - ML Jobs Router

API endpoints for managing ML jobs and models.
Super Admin only feature for platform ML operations.
"""

import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import require_super_admin
from app.models.user import User
from app.models.ml_job import MLJobType, MLJobStatus, MLJobPriority
from app.services.ml_job_service import MLJobService


router = APIRouter(prefix="/ml-jobs", tags=["ML Jobs"])


# ===========================================
# REQUEST/RESPONSE SCHEMAS
# ===========================================

class CreateMLJobRequest(BaseModel):
    """Request schema for creating an ML job."""
    job_type: MLJobType
    job_name: Optional[str] = None  # Auto-generated if not provided
    priority: MLJobPriority = MLJobPriority.NORMAL
    model_id: Optional[uuid.UUID] = None
    organization_id: Optional[uuid.UUID] = None
    parameters: Optional[Dict[str, Any]] = None
    scheduled_for: Optional[datetime] = None


class MLJobResponse(BaseModel):
    """Response schema for ML job."""
    id: uuid.UUID
    job_id: str
    job_type: str
    status: str
    priority: str
    model_id: Optional[uuid.UUID]
    organization_id: Optional[uuid.UUID]
    progress_percent: Optional[int]
    current_step: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]
    execution_time_seconds: Optional[int]
    error_message: Optional[str]
    created_at: str
    
    class Config:
        from_attributes = True


class MLJobListResponse(BaseModel):
    """Response schema for ML job list."""
    jobs: List[MLJobResponse]
    total: int


class MLJobStatsResponse(BaseModel):
    """Response schema for ML job statistics."""
    running: int
    pending: int
    failed_24h: int
    completed_24h: int


class CreateMLModelRequest(BaseModel):
    """Request schema for creating an ML model."""
    model_name: str = Field(..., min_length=1, max_length=255)
    model_version: str = Field(..., min_length=1, max_length=50)
    model_type: MLJobType
    algorithm: str = Field(..., min_length=1, max_length=100)
    framework: str = Field(default="scikit-learn", max_length=100)
    description: Optional[str] = None
    accuracy: Optional[float] = Field(None, ge=0, le=1)
    hyperparameters: Optional[Dict[str, Any]] = None
    feature_names: Optional[List[str]] = None
    model_path: Optional[str] = None


class MLModelResponse(BaseModel):
    """Response schema for ML model."""
    id: uuid.UUID
    model_name: str
    model_version: str
    model_type: str
    algorithm: str
    framework: str
    description: Optional[str]
    accuracy: Optional[float]
    is_active: bool
    training_samples_count: Optional[int]
    last_used_at: Optional[str]
    created_at: str
    
    class Config:
        from_attributes = True


class MLModelListResponse(BaseModel):
    """Response schema for ML model list."""
    models: List[MLModelResponse]
    total: int


class MLModelStatsResponse(BaseModel):
    """Response schema for ML model statistics."""
    total: int
    active: int
    average_accuracy: Optional[float]
    by_type: Dict[str, int]


class UpdateProgressRequest(BaseModel):
    """Request schema for updating job progress."""
    progress_percent: int = Field(..., ge=0, le=100)
    current_step: Optional[str] = None


# ===========================================
# ML JOB ENDPOINTS
# ===========================================

@router.post("", response_model=MLJobResponse, status_code=status.HTTP_201_CREATED)
async def create_ml_job(
    request: CreateMLJobRequest,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Create a new ML job (Super Admin only)."""
    service = MLJobService(db)
    
    try:
        job = await service.create_ml_job(
            job_type=request.job_type,
            job_name=request.job_name,
            priority=request.priority,
            model_id=request.model_id,
            organization_id=request.organization_id,
            parameters=request.parameters,
            scheduled_for=request.scheduled_for,
        )
        
        return _format_ml_job(job)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("", response_model=MLJobListResponse)
async def list_ml_jobs(
    status_filter: Optional[MLJobStatus] = Query(None, alias="status"),
    job_type: Optional[MLJobType] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """List all ML jobs (Super Admin only)."""
    service = MLJobService(db)
    
    jobs = await service.get_all_ml_jobs(
        status=status_filter,
        job_type=job_type,
        limit=limit,
        offset=offset,
    )
    
    return {
        "jobs": [_format_ml_job(j) for j in jobs],
        "total": len(jobs),
    }


@router.get("/stats", response_model=MLJobStatsResponse)
async def get_ml_jobs_stats(
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Get ML job statistics (Super Admin only)."""
    service = MLJobService(db)
    stats = await service.get_ml_jobs_stats()
    return stats


@router.get("/{job_id}", response_model=MLJobResponse)
async def get_ml_job(
    job_id: uuid.UUID,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Get a specific ML job (Super Admin only)."""
    service = MLJobService(db)
    job = await service.get_ml_job(job_id)
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ML job not found",
        )
    
    return _format_ml_job(job)


@router.post("/{job_id}/start", response_model=MLJobResponse)
async def start_ml_job(
    job_id: uuid.UUID,
    worker_id: Optional[str] = None,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Start an ML job (Super Admin only)."""
    service = MLJobService(db)
    
    try:
        job = await service.start_job(job_id, worker_id)
        return _format_ml_job(job)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{job_id}/progress", response_model=MLJobResponse)
async def update_job_progress(
    job_id: uuid.UUID,
    request: UpdateProgressRequest,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Update ML job progress (Super Admin only)."""
    service = MLJobService(db)
    
    try:
        job = await service.update_progress(
            job_id=job_id,
            progress_percent=request.progress_percent,
            current_step=request.current_step,
        )
        return _format_ml_job(job)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{job_id}/cancel", response_model=MLJobResponse)
async def cancel_ml_job(
    job_id: uuid.UUID,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Cancel an ML job (Super Admin only)."""
    service = MLJobService(db)
    
    try:
        job = await service.cancel_job(job_id)
        return _format_ml_job(job)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# ===========================================
# ML MODEL ENDPOINTS
# ===========================================

@router.post("/models", response_model=MLModelResponse, status_code=status.HTTP_201_CREATED)
async def create_ml_model(
    request: CreateMLModelRequest,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Create a new ML model (Super Admin only)."""
    service = MLJobService(db)
    
    try:
        model = await service.create_model(
            model_name=request.model_name,
            model_version=request.model_version,
            model_type=request.model_type,
            algorithm=request.algorithm,
            framework=request.framework,
            description=request.description,
            accuracy=request.accuracy,
            hyperparameters=request.hyperparameters,
            feature_names=request.feature_names,
            model_path=request.model_path,
        )
        
        return _format_ml_model(model)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/models", response_model=MLModelListResponse)
async def list_ml_models(
    model_type: Optional[MLJobType] = None,
    is_active: Optional[bool] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """List all ML models (Super Admin only)."""
    service = MLJobService(db)
    
    models = await service.get_all_models(
        model_type=model_type,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )
    
    return {
        "models": [_format_ml_model(m) for m in models],
        "total": len(models),
    }


@router.get("/models/stats", response_model=MLModelStatsResponse)
async def get_ml_models_stats(
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Get ML model statistics (Super Admin only)."""
    service = MLJobService(db)
    stats = await service.get_models_stats()
    return stats


@router.get("/models/{model_id}", response_model=MLModelResponse)
async def get_ml_model(
    model_id: uuid.UUID,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Get a specific ML model (Super Admin only)."""
    service = MLJobService(db)
    model = await service.get_model(model_id)
    
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ML model not found",
        )
    
    return _format_ml_model(model)


@router.post("/models/{model_id}/activate", response_model=MLModelResponse)
async def activate_ml_model(
    model_id: uuid.UUID,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Activate an ML model (Super Admin only)."""
    service = MLJobService(db)
    
    try:
        model = await service.activate_model(model_id)
        return _format_ml_model(model)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/models/{model_id}/deactivate", response_model=MLModelResponse)
async def deactivate_ml_model(
    model_id: uuid.UUID,
    current_user: User = Depends(require_super_admin()),
    db: AsyncSession = Depends(get_async_session),
):
    """Deactivate an ML model (Super Admin only)."""
    service = MLJobService(db)
    
    try:
        model = await service.deactivate_model(model_id)
        return _format_ml_model(model)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


def _format_ml_job(job) -> dict:
    """Format ML job for response."""
    return {
        "id": job.id,
        "job_id": job.job_id,
        "job_type": job.job_type.value if job.job_type else None,
        "status": job.status.value if job.status else None,
        "priority": job.priority.value if job.priority else None,
        "model_id": job.model_id,
        "organization_id": job.organization_id,
        "progress_percent": job.progress_percent,
        "current_step": job.current_step,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "execution_time_seconds": job.execution_time_seconds,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


def _format_ml_model(model) -> dict:
    """Format ML model for response."""
    return {
        "id": model.id,
        "model_name": model.model_name,
        "model_version": model.model_version,
        "model_type": model.model_type.value if model.model_type else None,
        "algorithm": model.algorithm,
        "framework": model.framework,
        "description": model.description,
        "accuracy": model.accuracy,
        "is_active": model.is_active,
        "training_samples_count": model.training_samples_count,
        "last_used_at": model.last_used_at.isoformat() if model.last_used_at else None,
        "created_at": model.created_at.isoformat() if model.created_at else None,
    }
