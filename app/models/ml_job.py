"""
Tekvwa Pro Audit - ML Job Model

Machine Learning job tracking for the platform.
Tracks ML pipeline jobs, model training, and inference operations.

ML Features in Tekvwa Pro Audit:
- Anomaly Detection (Isolation Forest + Autoencoder)
- Risk Scoring (Gradient Boosting)
- Benford's Law Analysis
- Growth Prediction
- AI Transaction Labeling
"""

import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Optional, List
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, Integer, Numeric, Float, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.user import User


class MLJobType(str, Enum):
    """Type of ML job."""
    ANOMALY_DETECTION = "anomaly_detection"
    RISK_SCORING = "risk_scoring"
    BENFORDS_LAW = "benfords_law"
    GROWTH_PREDICTION = "growth_prediction"
    TRANSACTION_LABELING = "transaction_labeling"
    MODEL_TRAINING = "model_training"
    MODEL_RETRAINING = "model_retraining"
    BATCH_INFERENCE = "batch_inference"
    DATA_PREPROCESSING = "data_preprocessing"
    FEATURE_ENGINEERING = "feature_engineering"


class MLJobStatus(str, Enum):
    """Status of an ML job."""
    QUEUED = "queued"           # Waiting to be processed
    RUNNING = "running"         # Currently executing
    COMPLETED = "completed"     # Successfully finished
    FAILED = "failed"           # Failed with error
    CANCELLED = "cancelled"     # Manually cancelled
    TIMEOUT = "timeout"         # Exceeded time limit
    RETRYING = "retrying"       # Retrying after failure


class MLJobPriority(str, Enum):
    """Priority level for job scheduling."""
    CRITICAL = "critical"    # Immediate execution
    HIGH = "high"            # Next available slot
    NORMAL = "normal"        # Standard queue
    LOW = "low"              # Background processing
    BATCH = "batch"          # Overnight batch jobs


class MLJob(BaseModel):
    """
    ML Job tracking for platform ML operations.
    
    Tracks training, inference, and analysis jobs
    for the Super Admin monitoring dashboard.
    """
    __tablename__ = "ml_jobs"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    # Job identification
    job_id: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Unique job reference (e.g., MLJ-2026-0001)"
    )
    
    job_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    
    # Job type and classification
    job_type: Mapped[MLJobType] = mapped_column(
        SQLEnum(MLJobType),
        nullable=False,
        index=True,
    )
    
    status: Mapped[MLJobStatus] = mapped_column(
        SQLEnum(MLJobStatus),
        nullable=False,
        default=MLJobStatus.QUEUED,
        index=True,
    )
    
    priority: Mapped[MLJobPriority] = mapped_column(
        SQLEnum(MLJobPriority),
        nullable=False,
        default=MLJobPriority.NORMAL,
    )
    
    # Organization context (optional - some jobs are platform-wide)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    
    # Model reference
    model_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ml_models.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Job parameters
    parameters: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Job configuration parameters"
    )
    
    # Input data
    input_data_source: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Source of input data"
    )
    
    input_record_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    
    # Execution timing
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Progress tracking
    progress_percent: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="0-100 progress percentage"
    )
    
    current_step: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Current processing step"
    )
    
    # Results
    output_record_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    
    results_summary: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Summary of job results"
    )
    
    # For inference jobs - number of predictions
    predictions_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    
    anomalies_detected: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    
    # Performance metrics
    execution_time_seconds: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    
    memory_usage_mb: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    
    cpu_usage_percent: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    
    # Error handling
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    
    error_traceback: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    
    retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    
    max_retries: Mapped[int] = mapped_column(
        Integer,
        default=3,
    )
    
    # Triggered by
    triggered_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    trigger_source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="manual",
        comment="manual, scheduled, api, webhook"
    )
    
    # Scheduling
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="For scheduled jobs"
    )
    
    is_recurring: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )
    
    recurrence_pattern: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Cron expression for recurring jobs"
    )
    
    # Relationships
    organization: Mapped[Optional["Organization"]] = relationship(
        lazy="selectin"
    )
    
    model: Mapped[Optional["MLModel"]] = relationship(
        back_populates="jobs",
        lazy="selectin"
    )
    
    triggered_by: Mapped[Optional["User"]] = relationship(
        lazy="selectin"
    )
    
    def __repr__(self) -> str:
        return f"<MLJob {self.job_id}: {self.job_type.value} ({self.status.value})>"
    
    @property
    def duration(self) -> Optional[timedelta]:
        """Get job duration."""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        elif self.started_at:
            return datetime.now(self.started_at.tzinfo) - self.started_at
        return None
    
    @property
    def is_running(self) -> bool:
        """Check if job is currently running."""
        return self.status in [MLJobStatus.RUNNING, MLJobStatus.RETRYING]


class MLModel(BaseModel):
    """
    ML Model registry for tracking deployed models.
    """
    __tablename__ = "ml_models"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    # Model identification
    model_code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Unique model code (e.g., MDL-ANOM-001)"
    )
    
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    
    # Model type
    model_type: Mapped[MLJobType] = mapped_column(
        SQLEnum(MLJobType),
        nullable=False,
    )
    
    # Algorithm details
    algorithm: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="e.g., IsolationForest, GradientBoostingClassifier"
    )
    
    framework: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="scikit-learn",
        comment="ML framework used"
    )
    
    # Versioning
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="1.0.0",
    )
    
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        index=True,
    )
    
    is_production: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Currently serving production traffic"
    )
    
    # Performance metrics
    accuracy: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 4),
        nullable=True,
        comment="Model accuracy 0.0000-1.0000"
    )
    
    precision: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 4),
        nullable=True,
    )
    
    recall: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 4),
        nullable=True,
    )
    
    f1_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 4),
        nullable=True,
    )
    
    # Training info
    trained_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    training_data_size: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    
    training_duration_seconds: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    
    # Model artifact
    artifact_path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Path to saved model file"
    )
    
    artifact_size_mb: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    
    # Hyperparameters
    hyperparameters: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )
    
    # Feature configuration
    feature_columns: Mapped[Optional[List[str]]] = mapped_column(
        JSONB,
        nullable=True,
    )
    
    # Inference stats
    total_predictions: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    
    avg_inference_time_ms: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Relationships
    jobs: Mapped[List["MLJob"]] = relationship(
        back_populates="model",
        lazy="selectin"
    )
    
    def __repr__(self) -> str:
        return f"<MLModel {self.model_code}: {self.name} v{self.version}>"
