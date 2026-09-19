"""
Tekvwa Pro Audit - Unified Audit System Models

This consolidated module provides ALL database models for the audit system:

1. AUDIT LOGGING (Basic):
   - AuditLog: Immutable audit log for tracking all data changes
   - AuditAction: Action type enumeration

2. AUDIT SYSTEM (Advanced):
   - AuditRun: Reproducible audit execution records
   - AuditFinding: Human-readable findings with risk levels
   - AuditEvidence: Immutable evidence storage with hash verification
   - AuditorSession: Auditor access sessions with complete logging
   - AuditorActionLog: Individual action log for auditor activities

NTAA 2025 COMPLIANCE:
- 5-year digital record keeping
- Immutable audit trail
- Device fingerprint for tax submission verification
- NRS response storage (IRN and cryptographic stamps)

CRITICAL COMPLIANCE:
- All models are APPEND-ONLY (no update/delete operations)
- Every record is hash-verified for integrity
- Auditor actions are comprehensively logged
"""

import uuid
import hashlib
import json
import enum
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    String, Text, DateTime, Date, Boolean, Integer, Float,
    Enum, ForeignKey, Index, CheckConstraint, func, JSON
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ===========================================
# ENUMS - BASIC AUDIT
# ===========================================

class AuditAction(str, enum.Enum):
    """Audit action types for basic logging."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    VIEW = "view"
    EXPORT = "export"
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    NRS_SUBMIT = "nrs_submit"
    NRS_CANCEL = "nrs_cancel"
    NRS_CREDIT_NOTE = "nrs_credit_note"
    UPLOAD = "upload"
    DOWNLOAD = "download"
    # WREN Maker-Checker actions
    WREN_VERIFY = "wren_verify"
    WREN_REJECT = "wren_reject"
    CATEGORY_CHANGE = "category_change"
    # Impersonation actions
    IMPERSONATION_START = "impersonation_start"
    IMPERSONATION_END = "impersonation_end"
    IMPERSONATION_GRANT = "impersonation_grant"
    IMPERSONATION_REVOKE = "impersonation_revoke"


# ===========================================
# ENUMS - ADVANCED AUDIT SYSTEM
# ===========================================

class AuditRunStatus(str, enum.Enum):
    """Status of an audit run."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AuditRunType(str, enum.Enum):
    """Type of audit being performed."""
    # Compliance Audits
    TAX_COMPLIANCE = "tax_compliance"
    FINANCIAL_STATEMENT = "financial_statement"
    VAT_AUDIT = "vat_audit"
    WHT_AUDIT = "wht_audit"
    PAYE_AUDIT = "paye_audit"
    
    # Forensic Analysis
    BENFORDS_LAW = "benfords_law"
    ZSCORE_ANOMALY = "zscore_anomaly"
    NRS_GAP_ANALYSIS = "nrs_gap_analysis"
    THREE_WAY_MATCHING = "three_way_matching"
    HASH_CHAIN_INTEGRITY = "hash_chain_integrity"
    FULL_FORENSIC = "full_forensic"
    COMPLIANCE_REPLAY = "compliance_replay"
    BEHAVIORAL_ANALYTICS = "behavioral_analytics"
    
    # Custom
    CUSTOM = "custom"


class FindingRiskLevel(str, enum.Enum):
    """Risk level classification for audit findings."""
    CRITICAL = "critical"     # Immediate action required
    HIGH = "high"             # Significant risk
    MEDIUM = "medium"         # Moderate risk
    LOW = "low"               # Minor risk
    INFORMATIONAL = "informational"  # FYI only


class FindingCategory(str, enum.Enum):
    """Category of audit finding."""
    FRAUD_INDICATOR = "fraud_indicator"
    COMPLIANCE_GAP = "compliance_gap"
    DATA_INTEGRITY = "data_integrity"
    POLICY_VIOLATION = "policy_violation"
    PROCESS_WEAKNESS = "process_weakness"
    CONTROL_DEFICIENCY = "control_deficiency"
    DOCUMENTATION_GAP = "documentation_gap"
    TAX_DISCREPANCY = "tax_discrepancy"
    FINANCIAL_MISSTATEMENT = "financial_misstatement"


class EvidenceType(str, enum.Enum):
    """Type of audit evidence."""
    DOCUMENT = "document"
    TRANSACTION = "transaction"
    CALCULATION = "calculation"
    SCREENSHOT = "screenshot"
    LOG_EXTRACT = "log_extract"
    DATABASE_SNAPSHOT = "database_snapshot"
    EXTERNAL_CONFIRMATION = "external_confirmation"
    SYSTEM_GENERATED = "system_generated"


class AuditorActionType(str, enum.Enum):
    """Actions that auditors can perform (all read-only)."""
    VIEW_TRANSACTION = "view_transaction"
    VIEW_INVOICE = "view_invoice"
    VIEW_REPORT = "view_report"
    VIEW_TAX_FILING = "view_tax_filing"
    VIEW_PAYROLL = "view_payroll"
    VIEW_AUDIT_LOG = "view_audit_log"
    RUN_ANALYSIS = "run_analysis"
    EXPORT_DATA = "export_data"
    ADD_FINDING = "add_finding"
    ADD_EVIDENCE = "add_evidence"
    GENERATE_REPORT = "generate_report"


# ===========================================
# BASIC AUDIT LOG MODEL
# ===========================================

class AuditLog(Base):
    """
    Immutable audit log for tracking all data changes.
    
    NTAA 2025 Compliant:
    - IP & Device Fingerprint for proving submission source
    - Before/After snapshots for category changes
    - NRS response storage for IRN and cryptographic stamps
    - 5-year retention per NTAA requirements
    
    This table should have no UPDATE or DELETE permissions.
    """
    
    __tablename__ = "audit_logs"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    # Entity Context (business entity)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="Business entity ID (nullable for system-level events like login failures)",
    )
    
    # Organization Context (for multi-tenant queries)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL", name="fk_audit_logs_organization"),
        nullable=True,
        index=True,
    )
    
    # User Context
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="User ID (nullable for unauthenticated actions like login failures)",
    )
    
    # User Email (required for audit trail - denormalized for efficiency)
    user_email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="info@tekvwa.org",
        comment="Email of user who performed the action",
    )
    
    # Impersonation Context (if CSR is impersonating)
    impersonated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_audit_logs_impersonated_by", use_alter=True),
        nullable=True,
        comment="If action was performed by CSR impersonating user",
    )
    
    # Action
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Action performed (CREATE, UPDATE, DELETE, etc.)",
    )
    
    # Legacy fields (table_name and record_id for database compatibility)
    table_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        default="",
        comment="Table name for the affected entity (legacy field)",
    )
    record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        default=uuid.uuid4,
        comment="Record ID in the table (legacy field)",
    )
    
    # Target Entity
    target_entity_type: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        default="",
        comment="Type of entity (transaction, invoice, etc.)",
    )
    target_entity_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="ID of the affected entity",
    )
    
    # ===========================================
    # BEFORE/AFTER SNAPSHOTS (NTAA 2025 Requirement)
    # ===========================================
    
    old_values: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Previous values (for UPDATE/DELETE) - MANDATORY for audit",
    )
    new_values: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="New values (for CREATE/UPDATE)",
    )
    changes: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Calculated changes for UPDATEs - shows exact field diffs",
    )
    
    # ===========================================
    # DEVICE FINGERPRINT (NTAA 2025 Requirement)
    # Mandatory for proving who submitted tax returns
    # ===========================================
    
    # Request Context
    ip_address: Mapped[Optional[str]] = mapped_column(INET, nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    device_fingerprint: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Browser/device fingerprint for submission verification",
    )
    session_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Session ID for tracking related actions",
    )
    
    # Geolocation (optional but helpful for fraud detection)
    geo_location: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Approximate location from IP (country, city)",
    )
    
    # ===========================================
    # NRS RESPONSE STORAGE (NTAA 2025 Requirement)
    # Store IRN and Cryptographic Stamp directly
    # ===========================================
    
    nrs_irn: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="NRS Invoice Reference Number (if NRS action)",
    )
    nrs_response: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Full NRS server response including cryptographic stamp",
    )
    
    # Timestamp (immutable)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    
    # Description for human-readable logging
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Human-readable description of the action",
    )
    
    def __repr__(self) -> str:
        action_str = self.action if isinstance(self.action, str) else self.action.value
        return f"<AuditLog(id={self.id}, action={action_str}, type={self.target_entity_type})>"


# ===========================================
# AUDIT RUN MODEL
# ===========================================

class AuditRun(Base):
    """
    Reproducible audit run record.
    
    Every audit execution is recorded with:
    - Rule version used
    - Data snapshot reference
    - Configuration parameters
    - Result summary
    
    This ensures audit results are reproducible at any future date.
    """
    
    __tablename__ = "audit_runs"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    # Human-readable Run ID (for display)
    run_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
        comment="Human-readable run identifier (e.g., RUN-2026-001)",
    )
    
    # Title and Description
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Human-readable title for this audit run",
    )
    
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Detailed description of the audit run purpose",
    )
    
    # Entity Context
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    
    # Audit Configuration
    run_type: Mapped[AuditRunType] = mapped_column(
        Enum(AuditRunType),
        nullable=False,
        index=True,
    )
    
    status: Mapped[AuditRunStatus] = mapped_column(
        Enum(AuditRunStatus),
        nullable=False,
        default=AuditRunStatus.PENDING,
        index=True,
    )
    
    # Period Under Audit
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Version Control (for reproducibility)
    rule_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Version of rules/algorithms used",
    )
    
    rule_config: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Configuration parameters for this run",
    )
    
    # Data Snapshot Reference
    data_snapshot_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Reference to point-in-time data snapshot",
    )
    
    data_snapshot_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA-256 hash of data snapshot",
    )
    
    # Execution Details
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    executed_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="User who initiated the audit run",
    )
    
    # Results Summary
    total_records_analyzed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    
    findings_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    
    critical_findings: Mapped[int] = mapped_column(Integer, default=0)
    high_findings: Mapped[int] = mapped_column(Integer, default=0)
    medium_findings: Mapped[int] = mapped_column(Integer, default=0)
    low_findings: Mapped[int] = mapped_column(Integer, default=0)
    
    # Result Details
    result_summary: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Summary of audit results",
    )
    
    # Integrity
    run_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 hash of run configuration and results",
    )
    
    # Timestamps (immutable)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    
    # Relationships
    findings: Mapped[List["AuditFinding"]] = relationship(
        "AuditFinding",
        back_populates="audit_run",
        lazy="dynamic",
    )
    
    def __repr__(self) -> str:
        return f"<AuditRun(id={self.id}, type={self.run_type}, status={self.status})>"
    
    def calculate_hash(self) -> str:
        """Calculate SHA-256 hash of this audit run for integrity verification."""
        data = {
            "entity_id": str(self.entity_id),
            "run_type": self.run_type.value,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "rule_version": self.rule_version,
            "rule_config": self.rule_config,
            "data_snapshot_id": self.data_snapshot_id,
            "result_summary": self.result_summary,
            "total_records_analyzed": self.total_records_analyzed,
            "findings_count": self.findings_count,
        }
        data_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(data_str.encode()).hexdigest()


# ===========================================
# AUDIT FINDING MODEL
# ===========================================

class AuditFinding(Base):
    """
    Human-readable audit finding with clear explanations.
    
    Each finding includes:
    - What is wrong (description)
    - Why it matters (impact)
    - Evidence reference
    - Risk level
    - Recommended action
    
    This is what regulators and external auditors actually read.
    """
    
    __tablename__ = "audit_findings"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    # Link to Audit Run
    audit_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("audit_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Entity Context
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    
    # Finding Reference (human-readable ID)
    finding_ref: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        comment="Human-readable finding reference (e.g., FIND-2026-00001)",
    )
    
    # Classification
    category: Mapped[FindingCategory] = mapped_column(
        Enum(FindingCategory),
        nullable=False,
        index=True,
    )
    
    risk_level: Mapped[FindingRiskLevel] = mapped_column(
        Enum(FindingRiskLevel),
        nullable=False,
        index=True,
    )
    
    # WHAT IS WRONG - Clear Title
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Clear, concise title of the finding",
    )
    
    # WHAT IS WRONG - Detailed Description
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Detailed description of what was found",
    )
    
    # WHY IT MATTERS - Impact Analysis
    impact: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Business/compliance impact explanation",
    )
    
    # AFFECTED ITEMS
    affected_records: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Number of records affected by this finding",
    )
    
    affected_amount: Mapped[Optional[Decimal]] = mapped_column(
        Float,
        nullable=True,
        comment="Financial amount impacted (if applicable)",
    )
    
    affected_record_ids: Mapped[List[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="List of affected record IDs",
    )
    
    # EVIDENCE REFERENCE
    evidence_summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Summary of supporting evidence",
    )
    
    evidence_ids: Mapped[List[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="List of evidence record IDs",
    )
    
    # RECOMMENDED ACTION
    recommendation: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Recommended corrective action",
    )
    
    # LEGAL/REGULATORY REFERENCE
    regulatory_reference: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Relevant law/regulation reference (e.g., FITA 2023 s.45)",
    )
    
    # Technical Details
    detection_method: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Method used to detect this finding",
    )
    
    detection_details: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Technical details of detection",
    )
    
    # Confidence Score
    confidence_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
        comment="Confidence level 0.0-1.0",
    )
    
    # Finding Status
    is_false_positive: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Marked as false positive by reviewer",
    )
    
    false_positive_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Integrity
    finding_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 hash for immutability verification",
    )
    
    # Timestamps (immutable)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    
    # Relationship
    audit_run: Mapped["AuditRun"] = relationship(
        "AuditRun",
        back_populates="findings",
    )
    
    evidence_items: Mapped[List["AuditEvidence"]] = relationship(
        "AuditEvidence",
        back_populates="finding",
        lazy="dynamic",
    )
    
    def __repr__(self) -> str:
        return f"<AuditFinding(ref={self.finding_ref}, risk={self.risk_level}, title='{self.title[:30]}...')>"
    
    def calculate_hash(self) -> str:
        """Calculate SHA-256 hash for integrity verification."""
        data = {
            "audit_run_id": str(self.audit_run_id),
            "entity_id": str(self.entity_id),
            "category": self.category.value,
            "risk_level": self.risk_level.value,
            "title": self.title,
            "description": self.description,
            "impact": self.impact,
            "affected_records": self.affected_records,
            "evidence_summary": self.evidence_summary,
            "recommendation": self.recommendation,
        }
        data_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(data_str.encode()).hexdigest()
    
    def to_human_readable(self) -> Dict[str, Any]:
        """Convert finding to human-readable format for reports."""
        return {
            "reference": self.finding_ref,
            "risk_level": self.risk_level.value.upper(),
            "category": self.category.value.replace("_", " ").title(),
            "what_is_wrong": {
                "title": self.title,
                "description": self.description,
            },
            "why_it_matters": self.impact,
            "evidence": {
                "summary": self.evidence_summary,
                "record_count": len(self.evidence_ids),
            },
            "affected": {
                "records": self.affected_records,
                "amount": float(self.affected_amount) if self.affected_amount else None,
            },
            "recommendation": self.recommendation,
            "regulatory_reference": self.regulatory_reference,
            "confidence": f"{self.confidence_score * 100:.0f}%",
        }


# ===========================================
# AUDIT EVIDENCE MODEL
# ===========================================

class AuditEvidence(Base):
    """
    Immutable audit evidence storage.
    
    Evidence cannot be altered after creation:
    - Hash computed at creation time
    - No update operations allowed
    - Delete requires special privilege and is logged
    """
    
    __tablename__ = "audit_evidence"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    # Link to Finding (optional - evidence can be standalone)
    finding_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("audit_findings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    
    # Entity Context
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    
    # Evidence Reference
    evidence_ref: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        comment="Human-readable reference (e.g., EVID-2026-00001)",
    )
    
    # Evidence Type
    evidence_type: Mapped[EvidenceType] = mapped_column(
        Enum(EvidenceType),
        nullable=False,
        index=True,
    )
    
    # Evidence Details
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    
    # Source Information
    source_table: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Source table if from database",
    )
    
    source_record_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Source record ID if from database",
    )
    
    # Evidence Content
    content: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Evidence content (JSON for structured data)",
    )
    
    # File Attachment (for documents)
    file_path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Path to attached file (WORM storage)",
    )
    
    file_mime_type: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    
    file_size_bytes: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    
    # IMMUTABILITY - Hash at creation
    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 hash of content at creation time",
    )
    
    file_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA-256 hash of attached file",
    )
    
    # Chain of Custody
    collected_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="User who collected/created this evidence",
    )
    
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    
    collection_method: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="How evidence was collected (automated/manual)",
    )
    
    # Verification
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    
    verified_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Timestamps (immutable)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    
    # Relationship
    finding: Mapped[Optional["AuditFinding"]] = relationship(
        "AuditFinding",
        back_populates="evidence_items",
    )
    
    def __repr__(self) -> str:
        return f"<AuditEvidence(ref={self.evidence_ref}, type={self.evidence_type})>"
    
    def calculate_content_hash(self) -> str:
        """Calculate SHA-256 hash of evidence content."""
        data_str = json.dumps(self.content, sort_keys=True, default=str)
        return hashlib.sha256(data_str.encode()).hexdigest()
    
    def verify_integrity(self) -> bool:
        """Verify that evidence has not been tampered with."""
        return self.content_hash == self.calculate_content_hash()


# ===========================================
# AUDITOR SESSION MODEL
# ===========================================

class AuditorSession(Base):
    """
    Complete logging of auditor access sessions.
    
    Every action by an auditor is logged for compliance.
    """
    
    __tablename__ = "auditor_sessions"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    # Auditor Information
    auditor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    
    auditor_email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    
    auditor_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    
    # Entity Being Audited
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    
    # Session Details
    session_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    
    session_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    
    # Access Context
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
    )
    
    user_agent: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    
    # Access Scope
    access_scope: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="What the auditor is allowed to access",
    )
    
    # Activity Summary
    actions_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    
    records_viewed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    
    exports_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    
    # Relationship to actions
    actions: Mapped[List["AuditorActionLog"]] = relationship(
        "AuditorActionLog",
        back_populates="session",
        lazy="dynamic",
    )
    
    def __repr__(self) -> str:
        return f"<AuditorSession(auditor={self.auditor_email}, entity={self.entity_id})>"


class AuditorActionLog(Base):
    """
    Individual action log for auditor activities.
    """
    
    __tablename__ = "auditor_action_logs"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    # Session Link
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("auditor_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Action Details
    action: Mapped[AuditorActionType] = mapped_column(
        Enum(AuditorActionType),
        nullable=False,
        index=True,
    )
    
    # Target Resource
    resource_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Type of resource accessed (transaction, invoice, etc.)",
    )
    
    resource_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="ID of specific resource accessed",
    )
    
    # Action Details
    details: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    
    # Timestamp
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    
    # Relationship
    session: Mapped["AuditorSession"] = relationship(
        "AuditorSession",
        back_populates="actions",
    )
    
    def __repr__(self) -> str:
        return f"<AuditorActionLog(action={self.action}, resource={self.resource_type})>"


# ===========================================
# INDEXES
# ===========================================

# Composite indexes for common queries
Index("ix_audit_runs_entity_period", AuditRun.entity_id, AuditRun.period_start, AuditRun.period_end)
Index("ix_audit_findings_entity_risk", AuditFinding.entity_id, AuditFinding.risk_level)
Index("ix_audit_evidence_entity_type", AuditEvidence.entity_id, AuditEvidence.evidence_type)
Index("ix_auditor_sessions_entity_active", AuditorSession.entity_id, AuditorSession.is_active)
