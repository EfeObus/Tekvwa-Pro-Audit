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

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, Integer, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.organization import Organization


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
        String(100),
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
    # Note: plain String, not a native Postgres enum -- job_type/status/priority were
    # deliberately kept as VARCHAR on the live table (same "converted for flexibility"
    # pattern documented in app/models/sku.py for tier/billing_cycle/intelligence_addon).
    # MLJobType/MLJobStatus/MLJobPriority are all (str, Enum), so plain string columns work.
    job_type: Mapped[MLJobType] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    status: Mapped[MLJobStatus] = mapped_column(
        String(20),
        nullable=False,
        default=MLJobStatus.QUEUED,
        index=True,
    )

    priority: Mapped[MLJobPriority] = mapped_column(
        String(20),
        nullable=False,
        default=MLJobPriority.NORMAL,
    )

    # Organization context (optional - some jobs are platform-wide)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
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

    # Execution timing
    queued_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )

    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
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

    worker_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    # Results
    results: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )

    metrics: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )

    output_files: Mapped[Optional[List[str]]] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Performance metrics
    execution_time_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    # Error handling
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    error_details: Mapped[Optional[dict]] = mapped_column(
        JSONB,
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

    # Scheduling
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="For scheduled jobs"
    )

    # Relationships
    organization: Mapped[Optional["Organization"]] = relationship(
        lazy="selectin"
    )
    
    model: Mapped[Optional["MLModel"]] = relationship(
        back_populates="jobs",
        lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<MLJob {self.job_id}: {self.job_type} ({self.status})>"
    
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
    model_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    model_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Model type -- plain String, see the note on MLJob.job_type above.
    model_type: Mapped[MLJobType] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    # Algorithm details
    algorithm: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="e.g., IsolationForest, GradientBoostingClassifier"
    )

    framework: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        default="scikit-learn",
        comment="ML framework used"
    )

    is_active: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        default=True,
        index=True,
    )

    # Performance metrics
    accuracy: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Model accuracy 0.0-1.0"
    )

    precision_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )

    recall_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )

    f1_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )

    training_samples_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    # Model artifact
    model_path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Path to saved model file"
    )

    # Hyperparameters
    hyperparameters: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Feature configuration
    feature_names: Mapped[Optional[List[str]]] = mapped_column(
        JSONB,
        nullable=True,
    )

    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )
    
    # Relationships
    jobs: Mapped[List["MLJob"]] = relationship(
        back_populates="model",
        lazy="selectin"
    )
    
    def __repr__(self) -> str:
        return f"<MLModel {self.model_name} v{self.model_version}>"
