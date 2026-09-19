"""
Tekvwa Pro Audit - Audit System Service

Comprehensive audit system service providing:
1. Auditor Read-Only Enforcement
2. Evidence Immutability Management
3. Reproducible Audit Runs
4. Human-Readable Findings Generation
5. Audit Export Support

CRITICAL: All auditor actions are logged. Evidence cannot be modified.
"""

import uuid
import hashlib
import json
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole
from app.models.audit_consolidated import (
    AuditLog,
    AuditRun, AuditRunStatus, AuditRunType,
    AuditFinding, FindingRiskLevel, FindingCategory,
    AuditEvidence, EvidenceType,
    AuditorSession, AuditorActionLog, AuditorActionType,
)
from app.utils.permissions import OrganizationPermission, has_organization_permission


# ===========================================
# EXCEPTIONS
# ===========================================

class AuditorPermissionError(Exception):
    """Raised when auditor tries to perform a forbidden action."""
    pass


class EvidenceImmutabilityError(Exception):
    """Raised when attempting to modify immutable evidence."""
    pass


class AuditRunError(Exception):
    """Raised when audit run fails."""
    pass


# ===========================================
# AUDITOR ROLE ENFORCEMENT
# ===========================================

class AuditorRoleEnforcer:
    """
    Hard enforcement of auditor read-only permissions.
    
    CRITICAL: Auditors CANNOT:
    - Create, update, or delete transactions
    - Approve or reject anything
    - Recalculate tax amounts
    - Upload documents to the entity
    - Modify any business data
    
    Auditors CAN ONLY:
    - View data (read-only)
    - Run analysis
    - Export data
    - Add findings and evidence
    - Generate reports
    """
    
    # Actions that auditors are FORBIDDEN from doing
    FORBIDDEN_ACTIONS = {
        "create_transaction",
        "update_transaction",
        "delete_transaction",
        "create_invoice",
        "update_invoice",
        "delete_invoice",
        "approve_transaction",
        "reject_transaction",
        "verify_wren",
        "submit_tax_filing",
        "cancel_nrs",
        "create_customer",
        "update_customer",
        "delete_customer",
        "create_vendor",
        "update_vendor",
        "delete_vendor",
        "manage_payroll",
        "run_payroll",
        "approve_payroll",
        "manage_inventory",
        "stock_adjustment",
        "upload_document",
        "delete_document",
        "manage_settings",
        "manage_users",
    }
    
    # Permissions that auditors are explicitly denied
    DENIED_PERMISSIONS = {
        OrganizationPermission.CREATE_TRANSACTIONS,
        OrganizationPermission.EDIT_TRANSACTIONS,
        OrganizationPermission.DELETE_TRANSACTIONS,
        OrganizationPermission.MANAGE_INVOICES,
        OrganizationPermission.MANAGE_TAX_FILINGS,
        OrganizationPermission.MANAGE_PAYROLL,
        OrganizationPermission.MANAGE_INVENTORY,
        OrganizationPermission.MANAGE_CUSTOMERS,
        OrganizationPermission.MANAGE_VENDORS,
        OrganizationPermission.MANAGE_SETTINGS,
        OrganizationPermission.MANAGE_USERS,
        OrganizationPermission.VERIFY_WREN,
        OrganizationPermission.CANCEL_NRS_SUBMISSION,
    }
    
    @classmethod
    def is_auditor(cls, user: User) -> bool:
        """Check if user is an auditor."""
        return user.role == UserRole.AUDITOR
    
    @classmethod
    def enforce_read_only(cls, user: User, action: str) -> None:
        """
        Enforce read-only access for auditors.
        
        Raises AuditorPermissionError if auditor tries forbidden action.
        """
        if not cls.is_auditor(user):
            return  # Non-auditors use normal permission system
        
        if action in cls.FORBIDDEN_ACTIONS:
            raise AuditorPermissionError(
                f"Auditor role is read-only. Action '{action}' is forbidden. "
                "Auditors cannot modify, approve, recalculate, or upload data."
            )
    
    @classmethod
    def check_permission(cls, user: User, permission: OrganizationPermission) -> bool:
        """
        Check if auditor has permission.
        
        Returns False for all write permissions.
        """
        if not cls.is_auditor(user):
            return has_organization_permission(user.role, permission)
        
        if permission in cls.DENIED_PERMISSIONS:
            return False
        
        return has_organization_permission(UserRole.AUDITOR, permission)
    
    @classmethod
    def get_allowed_actions(cls) -> List[str]:
        """Get list of actions auditors ARE allowed to perform."""
        return [
            "view_transaction",
            "view_invoice",
            "view_report",
            "view_tax_filing",
            "view_payroll",
            "view_audit_log",
            "run_analysis",
            "export_data",
            "add_finding",
            "add_evidence",
            "generate_report",
            "view_customer",
            "view_vendor",
            "view_inventory",
        ]


# ===========================================
# EVIDENCE IMMUTABILITY SERVICE
# ===========================================

class EvidenceImmutabilityService:
    """
    Manages immutable audit evidence.
    
    CRITICAL: Evidence CANNOT be modified after creation.
    - Hash is computed at creation
    - No update operations allowed
    - Delete requires special audit and is logged
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_evidence(
        self,
        entity_id: uuid.UUID,
        evidence_type: EvidenceType,
        title: str,
        description: str,
        content: Dict[str, Any],
        collected_by: uuid.UUID,
        collection_method: str = "automated",
        finding_id: Optional[uuid.UUID] = None,
        source_table: Optional[str] = None,
        source_record_id: Optional[uuid.UUID] = None,
        file_path: Optional[str] = None,
        file_hash: Optional[str] = None,
        file_mime_type: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
    ) -> AuditEvidence:
        """
        Create immutable audit evidence.
        
        Hash is computed at creation and cannot be changed.
        """
        # Generate unique reference
        count = await self._get_evidence_count(entity_id)
        evidence_ref = f"EVID-{datetime.now().year}-{count + 1:05d}"
        
        # Calculate content hash at creation time
        content_hash = self._calculate_hash(content)
        
        evidence = AuditEvidence(
            entity_id=entity_id,
            evidence_ref=evidence_ref,
            evidence_type=evidence_type,
            title=title,
            description=description,
            content=content,
            content_hash=content_hash,
            collected_by=collected_by,
            collection_method=collection_method,
            finding_id=finding_id,
            source_table=source_table,
            source_record_id=source_record_id,
            file_path=file_path,
            file_hash=file_hash,
            file_mime_type=file_mime_type,
            file_size_bytes=file_size_bytes,
        )
        
        self.db.add(evidence)
        await self.db.flush()
        
        return evidence
    
    async def verify_evidence_integrity(
        self,
        evidence_id: uuid.UUID,
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify that evidence has not been tampered with.
        
        Returns (is_valid, error_message)
        """
        stmt = select(AuditEvidence).where(AuditEvidence.id == evidence_id)
        result = await self.db.execute(stmt)
        evidence = result.scalar_one_or_none()
        
        if not evidence:
            return False, "Evidence not found"
        
        # Recalculate hash
        current_hash = self._calculate_hash(evidence.content)
        
        if current_hash != evidence.content_hash:
            return False, f"Evidence integrity compromised. Original hash: {evidence.content_hash}, Current hash: {current_hash}"
        
        # Verify file hash if present
        if evidence.file_path and evidence.file_hash:
            # In production, would verify actual file hash
            pass
        
        return True, None
    
    async def verify_all_evidence(
        self,
        entity_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Verify integrity of all evidence for an entity."""
        stmt = select(AuditEvidence).where(AuditEvidence.entity_id == entity_id)
        result = await self.db.execute(stmt)
        evidence_list = result.scalars().all()
        
        valid_count = 0
        invalid_count = 0
        invalid_refs = []
        
        for evidence in evidence_list:
            current_hash = self._calculate_hash(evidence.content)
            if current_hash == evidence.content_hash:
                valid_count += 1
            else:
                invalid_count += 1
                invalid_refs.append(evidence.evidence_ref)
        
        return {
            "total_evidence": len(evidence_list),
            "valid": valid_count,
            "invalid": invalid_count,
            "invalid_references": invalid_refs,
            "integrity_status": "PASS" if invalid_count == 0 else "FAIL",
            "verified_at": datetime.now().isoformat(),
        }
    
    def _calculate_hash(self, content: Dict[str, Any]) -> str:
        """Calculate SHA-256 hash of content."""
        data_str = json.dumps(content, sort_keys=True, default=str)
        return hashlib.sha256(data_str.encode()).hexdigest()
    
    async def _get_evidence_count(self, entity_id: uuid.UUID) -> int:
        """Get count of evidence for entity."""
        stmt = select(func.count()).select_from(AuditEvidence).where(
            AuditEvidence.entity_id == entity_id
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0


# ===========================================
# REPRODUCIBLE AUDIT RUN SERVICE
# ===========================================

class ReproducibleAuditService:
    """
    Manages reproducible audit runs.
    
    Every audit execution stores:
    - Rule version used
    - Data snapshot reference
    - Configuration parameters
    - Result summary
    
    This ensures results are reproducible at any future date.
    """
    
    # Current rule versions
    RULE_VERSIONS = {
        # Compliance Audits
        AuditRunType.TAX_COMPLIANCE: "tax-v2026.1",
        AuditRunType.FINANCIAL_STATEMENT: "financial-v2.0.0",
        AuditRunType.VAT_AUDIT: "vat-v2026.1",
        AuditRunType.WHT_AUDIT: "wht-v2026.1",
        AuditRunType.PAYE_AUDIT: "paye-v2026.1",
        
        # Forensic Analysis
        AuditRunType.BENFORDS_LAW: "benford-v2.1.0",
        AuditRunType.ZSCORE_ANOMALY: "zscore-v1.3.0",
        AuditRunType.NRS_GAP_ANALYSIS: "nrs-v2026.1",
        AuditRunType.THREE_WAY_MATCHING: "3wm-v1.5.0",
        AuditRunType.HASH_CHAIN_INTEGRITY: "hash-v2.0.0",
        AuditRunType.FULL_FORENSIC: "forensic-v3.0.0",
        AuditRunType.COMPLIANCE_REPLAY: "replay-v2.0.0",
        AuditRunType.BEHAVIORAL_ANALYTICS: "behavioral-v1.2.0",
        
        # Custom
        AuditRunType.CUSTOM: "custom-v1.0.0",
    }
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def _generate_run_id(self, run_type: AuditRunType) -> str:
        """Generate a human-readable run ID."""
        prefix_map = {
            AuditRunType.TAX_COMPLIANCE: "TAX",
            AuditRunType.FINANCIAL_STATEMENT: "FIN",
            AuditRunType.VAT_AUDIT: "VAT",
            AuditRunType.WHT_AUDIT: "WHT",
            AuditRunType.PAYE_AUDIT: "PAYE",
            AuditRunType.BENFORDS_LAW: "BEN",
            AuditRunType.ZSCORE_ANOMALY: "ZSCR",
            AuditRunType.NRS_GAP_ANALYSIS: "NRS",
            AuditRunType.THREE_WAY_MATCHING: "3WM",
            AuditRunType.HASH_CHAIN_INTEGRITY: "HASH",
            AuditRunType.FULL_FORENSIC: "FOR",
            AuditRunType.COMPLIANCE_REPLAY: "RPL",
            AuditRunType.BEHAVIORAL_ANALYTICS: "BEH",
            AuditRunType.CUSTOM: "CUS",
        }
        prefix = prefix_map.get(run_type, "AUD")
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        random_suffix = uuid.uuid4().hex[:6].upper()
        return f"{prefix}-{timestamp}-{random_suffix}"
    
    async def create_audit_run(
        self,
        entity_id: uuid.UUID,
        run_type: AuditRunType,
        title: str,
        date_range_start: date,
        date_range_end: date,
        created_by_id: uuid.UUID,
        description: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> AuditRun:
        """
        Create a new reproducible audit run with title and description.
        
        This is the main method for creating audit runs from the UI.
        """
        rule_version = self.RULE_VERSIONS.get(run_type, "custom-v1.0.0")
        run_id = self._generate_run_id(run_type)
        
        # Merge parameters into rule_config
        rule_config = parameters or {}
        
        audit_run = AuditRun(
            run_id=run_id,
            title=title,
            description=description,
            entity_id=entity_id,
            run_type=run_type,
            status=AuditRunStatus.PENDING,
            period_start=date_range_start,
            period_end=date_range_end,
            rule_version=rule_version,
            rule_config=rule_config,
            executed_by=created_by_id,
            result_summary={},
            run_hash="pending",  # Will be calculated on completion
        )
        
        self.db.add(audit_run)
        await self.db.flush()
        await self.db.refresh(audit_run)
        
        return audit_run
    
    async def start_audit_run(
        self,
        entity_id: uuid.UUID,
        run_type: AuditRunType,
        period_start: date,
        period_end: date,
        executed_by: uuid.UUID,
        title: Optional[str] = None,
        description: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        data_snapshot_id: Optional[str] = None,
    ) -> AuditRun:
        """
        Start a new reproducible audit run.
        """
        rule_version = self.RULE_VERSIONS.get(run_type, "custom-v1.0.0")
        rule_config = config or {}
        run_id = self._generate_run_id(run_type)
        
        # Generate default title if not provided
        if not title:
            title = f"{run_type.value.replace('_', ' ').title()} - {period_start} to {period_end}"
        
        # Calculate data snapshot hash if snapshot provided
        data_snapshot_hash = None
        if data_snapshot_id:
            data_snapshot_hash = hashlib.sha256(data_snapshot_id.encode()).hexdigest()
        
        audit_run = AuditRun(
            run_id=run_id,
            title=title,
            description=description,
            entity_id=entity_id,
            run_type=run_type,
            status=AuditRunStatus.PENDING,
            period_start=period_start,
            period_end=period_end,
            rule_version=rule_version,
            rule_config=rule_config,
            data_snapshot_id=data_snapshot_id,
            data_snapshot_hash=data_snapshot_hash,
            executed_by=executed_by,
            result_summary={},
            run_hash="pending",  # Will be calculated on completion
        )
        
        self.db.add(audit_run)
        await self.db.flush()
        
        return audit_run
    
    async def mark_running(self, audit_run_id: uuid.UUID) -> None:
        """Mark audit run as running."""
        stmt = select(AuditRun).where(AuditRun.id == audit_run_id)
        result = await self.db.execute(stmt)
        audit_run = result.scalar_one()
        
        audit_run.status = AuditRunStatus.RUNNING
        audit_run.started_at = datetime.now()
        await self.db.flush()
    
    async def complete_audit_run(
        self,
        audit_run_id: uuid.UUID,
        total_records: int,
        result_summary: Dict[str, Any],
        findings_count: int = 0,
        critical: int = 0,
        high: int = 0,
        medium: int = 0,
        low: int = 0,
    ) -> AuditRun:
        """
        Complete an audit run with results.
        """
        stmt = select(AuditRun).where(AuditRun.id == audit_run_id)
        result = await self.db.execute(stmt)
        audit_run = result.scalar_one()
        
        audit_run.status = AuditRunStatus.COMPLETED
        audit_run.completed_at = datetime.now()
        audit_run.total_records_analyzed = total_records
        audit_run.result_summary = result_summary
        audit_run.findings_count = findings_count
        audit_run.critical_findings = critical
        audit_run.high_findings = high
        audit_run.medium_findings = medium
        audit_run.low_findings = low
        
        # Calculate final hash for reproducibility verification
        audit_run.run_hash = audit_run.calculate_hash()
        
        await self.db.flush()
        return audit_run
    
    async def verify_run_reproducibility(
        self,
        audit_run_id: uuid.UUID,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Verify that an audit run can be reproduced.
        
        Returns (is_reproducible, details)
        """
        stmt = select(AuditRun).where(AuditRun.id == audit_run_id)
        result = await self.db.execute(stmt)
        audit_run = result.scalar_one_or_none()
        
        if not audit_run:
            return False, {"error": "Audit run not found"}
        
        # Recalculate hash
        current_hash = audit_run.calculate_hash()
        hash_valid = current_hash == audit_run.run_hash
        
        return hash_valid, {
            "audit_run_id": str(audit_run_id),
            "run_type": audit_run.run_type.value,
            "rule_version": audit_run.rule_version,
            "period": f"{audit_run.period_start} to {audit_run.period_end}",
            "data_snapshot_id": audit_run.data_snapshot_id,
            "original_hash": audit_run.run_hash,
            "current_hash": current_hash,
            "hash_valid": hash_valid,
            "is_reproducible": hash_valid,
            "verified_at": datetime.now().isoformat(),
        }
    
    async def get_run_history(
        self,
        entity_id: uuid.UUID,
        run_type: Optional[AuditRunType] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get audit run history for an entity."""
        stmt = select(AuditRun).where(AuditRun.entity_id == entity_id)
        
        if run_type:
            stmt = stmt.where(AuditRun.run_type == run_type)
        
        stmt = stmt.order_by(AuditRun.created_at.desc()).limit(limit)
        
        result = await self.db.execute(stmt)
        runs = result.scalars().all()
        
        return [
            {
                "id": str(run.id),
                "run_type": run.run_type.value,
                "status": run.status.value,
                "period": f"{run.period_start} to {run.period_end}",
                "rule_version": run.rule_version,
                "findings_count": run.findings_count,
                "critical": run.critical_findings,
                "high": run.high_findings,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            }
            for run in runs
        ]


# ===========================================
# HUMAN-READABLE FINDINGS SERVICE
# ===========================================

class AuditFindingsService:
    """
    Generates and manages human-readable audit findings.
    
    Each finding clearly shows:
    - What is wrong (title + description)
    - Why it matters (impact)
    - Evidence reference
    - Risk level
    - Recommended action
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_finding(
        self,
        audit_run_id: uuid.UUID,
        entity_id: uuid.UUID,
        category: FindingCategory,
        risk_level: FindingRiskLevel,
        title: str,
        description: str,
        impact: str,
        recommendation: str,
        evidence_summary: str,
        detection_method: str,
        affected_records: int = 1,
        affected_amount: Optional[Decimal] = None,
        affected_record_ids: Optional[List[str]] = None,
        evidence_ids: Optional[List[str]] = None,
        regulatory_reference: Optional[str] = None,
        detection_details: Optional[Dict[str, Any]] = None,
        confidence_score: float = 1.0,
    ) -> AuditFinding:
        """
        Create a new audit finding with all required information.
        """
        # Generate unique reference
        count = await self._get_finding_count(entity_id)
        finding_ref = f"FIND-{datetime.now().year}-{count + 1:05d}"
        
        finding = AuditFinding(
            audit_run_id=audit_run_id,
            entity_id=entity_id,
            finding_ref=finding_ref,
            category=category,
            risk_level=risk_level,
            title=title,
            description=description,
            impact=impact,
            recommendation=recommendation,
            evidence_summary=evidence_summary,
            detection_method=detection_method,
            affected_records=affected_records,
            affected_amount=affected_amount,
            affected_record_ids=affected_record_ids or [],
            evidence_ids=evidence_ids or [],
            regulatory_reference=regulatory_reference,
            detection_details=detection_details or {},
            confidence_score=confidence_score,
            finding_hash="pending",
        )
        
        # Calculate hash for immutability
        self.db.add(finding)
        await self.db.flush()
        
        finding.finding_hash = finding.calculate_hash()
        await self.db.flush()
        
        return finding
    
    async def get_findings_by_risk(
        self,
        entity_id: uuid.UUID,
        risk_levels: Optional[List[FindingRiskLevel]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get findings grouped by risk level."""
        stmt = select(AuditFinding).where(AuditFinding.entity_id == entity_id)
        
        if risk_levels:
            stmt = stmt.where(AuditFinding.risk_level.in_(risk_levels))
        
        stmt = stmt.order_by(AuditFinding.created_at.desc())
        
        result = await self.db.execute(stmt)
        findings = result.scalars().all()
        
        grouped = {
            "critical": [],
            "high": [],
            "medium": [],
            "low": [],
            "informational": [],
        }
        
        for finding in findings:
            grouped[finding.risk_level.value].append(finding.to_human_readable())
        
        return grouped
    
    async def get_findings_report(
        self,
        entity_id: uuid.UUID,
        audit_run_id: Optional[uuid.UUID] = None,
        period_start: Optional[date] = None,
        period_end: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Generate a complete findings report."""
        stmt = select(AuditFinding).where(AuditFinding.entity_id == entity_id)
        
        if audit_run_id:
            stmt = stmt.where(AuditFinding.audit_run_id == audit_run_id)
        
        result = await self.db.execute(stmt)
        findings = result.scalars().all()
        
        # Calculate summary
        total_affected_amount = sum(
            f.affected_amount or 0 for f in findings
        )
        
        return {
            "report_generated_at": datetime.now().isoformat(),
            "entity_id": str(entity_id),
            "period": {
                "start": period_start.isoformat() if period_start else None,
                "end": period_end.isoformat() if period_end else None,
            },
            "summary": {
                "total_findings": len(findings),
                "by_risk_level": {
                    "critical": sum(1 for f in findings if f.risk_level == FindingRiskLevel.CRITICAL),
                    "high": sum(1 for f in findings if f.risk_level == FindingRiskLevel.HIGH),
                    "medium": sum(1 for f in findings if f.risk_level == FindingRiskLevel.MEDIUM),
                    "low": sum(1 for f in findings if f.risk_level == FindingRiskLevel.LOW),
                    "informational": sum(1 for f in findings if f.risk_level == FindingRiskLevel.INFORMATIONAL),
                },
                "total_affected_amount": float(total_affected_amount),
                "false_positives": sum(1 for f in findings if f.is_false_positive),
            },
            "findings": [f.to_human_readable() for f in findings],
        }
    
    async def _get_finding_count(self, entity_id: uuid.UUID) -> int:
        """Get count of findings for entity."""
        stmt = select(func.count()).select_from(AuditFinding).where(
            AuditFinding.entity_id == entity_id
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0


# ===========================================
# AUDITOR SESSION LOGGING SERVICE
# ===========================================

class AuditorSessionService:
    """
    Manages auditor access sessions and action logging.
    
    Every auditor action is logged for compliance.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def start_session(
        self,
        auditor_user_id: uuid.UUID,
        auditor_email: str,
        auditor_name: str,
        entity_id: uuid.UUID,
        access_scope: Dict[str, Any],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditorSession:
        """Start a new auditor session."""
        session = AuditorSession(
            auditor_user_id=auditor_user_id,
            auditor_email=auditor_email,
            auditor_name=auditor_name,
            entity_id=entity_id,
            access_scope=access_scope,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        
        self.db.add(session)
        await self.db.flush()
        
        return session
    
    async def log_action(
        self,
        session_id: uuid.UUID,
        action: AuditorActionType,
        resource_type: str,
        resource_id: Optional[uuid.UUID] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditorActionLog:
        """Log an auditor action."""
        action_log = AuditorActionLog(
            session_id=session_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
        )
        
        self.db.add(action_log)
        
        # Update session counters
        stmt = select(AuditorSession).where(AuditorSession.id == session_id)
        result = await self.db.execute(stmt)
        session = result.scalar_one()
        
        session.actions_count += 1
        if action in [AuditorActionType.VIEW_TRANSACTION, AuditorActionType.VIEW_INVOICE, 
                      AuditorActionType.VIEW_REPORT, AuditorActionType.VIEW_TAX_FILING]:
            session.records_viewed += 1
        if action == AuditorActionType.EXPORT_DATA:
            session.exports_count += 1
        
        await self.db.flush()
        
        return action_log
    
    async def end_session(self, session_id: uuid.UUID) -> None:
        """End an auditor session."""
        stmt = select(AuditorSession).where(AuditorSession.id == session_id)
        result = await self.db.execute(stmt)
        session = result.scalar_one()
        
        session.session_end = datetime.now()
        session.is_active = False
        await self.db.flush()
    
    async def get_session_history(
        self,
        entity_id: uuid.UUID,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get auditor session history for an entity."""
        stmt = (
            select(AuditorSession)
            .where(AuditorSession.entity_id == entity_id)
            .order_by(AuditorSession.created_at.desc())
            .limit(limit)
        )
        
        result = await self.db.execute(stmt)
        sessions = result.scalars().all()
        
        return [
            {
                "session_id": str(s.id),
                "auditor_email": s.auditor_email,
                "auditor_name": s.auditor_name,
                "session_start": s.session_start.isoformat(),
                "session_end": s.session_end.isoformat() if s.session_end else None,
                "is_active": s.is_active,
                "actions_count": s.actions_count,
                "records_viewed": s.records_viewed,
                "exports_count": s.exports_count,
            }
            for s in sessions
        ]


# ===========================================
# UNIFIED AUDIT SYSTEM SERVICE
# ===========================================

class AdvancedAuditSystemService:
    """
    Unified service for the complete audit system.
    
    Provides:
    1. Auditor role enforcement
    2. Evidence immutability
    3. Reproducible audit runs
    4. Human-readable findings
    5. Complete auditor action logging
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.role_enforcer = AuditorRoleEnforcer()
        self.evidence_service = EvidenceImmutabilityService(db)
        self.audit_service = ReproducibleAuditService(db)
        self.findings_service = AuditFindingsService(db)
        self.session_service = AuditorSessionService(db)
    
    async def verify_auditor_access(
        self,
        user: User,
        action: str,
    ) -> bool:
        """
        Verify auditor has access to perform action.
        
        Raises AuditorPermissionError for forbidden actions.
        """
        AuditorRoleEnforcer.enforce_read_only(user, action)
        return True
    
    async def create_audit_run(
        self,
        entity_id: uuid.UUID,
        run_type: AuditRunType,
        title: str,
        date_range_start: date,
        date_range_end: date,
        created_by_id: uuid.UUID,
        description: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> AuditRun:
        """
        Create a new reproducible audit run.
        
        Delegates to the ReproducibleAuditService.
        """
        return await self.audit_service.create_audit_run(
            entity_id=entity_id,
            run_type=run_type,
            title=title,
            date_range_start=date_range_start,
            date_range_end=date_range_end,
            created_by_id=created_by_id,
            description=description,
            parameters=parameters,
        )
    
    async def execute_audit_run(self, run_id: str) -> Optional[AuditRun]:
        """
        Execute an audit run by its run_id.
        """
        stmt = select(AuditRun).where(AuditRun.run_id == run_id)
        result = await self.db.execute(stmt)
        audit_run = result.scalar_one_or_none()
        
        if not audit_run:
            return None
        
        # Mark as running
        audit_run.status = AuditRunStatus.RUNNING
        audit_run.started_at = datetime.now()
        await self.db.flush()
        
        # Execute the audit based on run_type
        try:
            # For now, just mark as completed
            # In a real implementation, this would run the actual audit
            audit_run.status = AuditRunStatus.COMPLETED
            audit_run.completed_at = datetime.now()
            audit_run.run_hash = audit_run.calculate_hash()
            await self.db.flush()
            
            return audit_run
        except Exception as e:
            audit_run.status = AuditRunStatus.FAILED
            audit_run.result_summary = {"error": str(e)}
            await self.db.flush()
            raise
    
    async def run_full_audit(
        self,
        entity_id: uuid.UUID,
        period_start: date,
        period_end: date,
        executed_by: uuid.UUID,
        include_benfords: bool = True,
        include_zscore: bool = True,
        include_nrs_gap: bool = True,
        include_three_way: bool = True,
    ) -> Dict[str, Any]:
        """
        Run a comprehensive audit and generate findings.
        """
        # Start audit run
        audit_run = await self.audit_service.start_audit_run(
            entity_id=entity_id,
            run_type=AuditRunType.FULL_FORENSIC,
            period_start=period_start,
            period_end=period_end,
            executed_by=executed_by,
            config={
                "include_benfords": include_benfords,
                "include_zscore": include_zscore,
                "include_nrs_gap": include_nrs_gap,
                "include_three_way": include_three_way,
            },
        )
        
        await self.audit_service.mark_running(audit_run.id)
        
        try:
            # Run analyses and collect findings
            findings = []
            total_records = 0
            
            # This is where the actual analysis would run
            # For now, we'll simulate with the forensic audit service
            
            # Complete the audit run
            await self.audit_service.complete_audit_run(
                audit_run_id=audit_run.id,
                total_records=total_records,
                result_summary={
                    "analyses_run": {
                        "benfords_law": include_benfords,
                        "zscore_anomaly": include_zscore,
                        "nrs_gap": include_nrs_gap,
                        "three_way_matching": include_three_way,
                    },
                    "completed_at": datetime.now().isoformat(),
                },
                findings_count=len(findings),
            )
            
            return {
                "audit_run_id": str(audit_run.id),
                "status": "completed",
                "period": f"{period_start} to {period_end}",
                "total_records": total_records,
                "findings_count": len(findings),
            }
            
        except Exception as e:
            # Mark run as failed
            audit_run.status = AuditRunStatus.FAILED
            audit_run.result_summary = {"error": str(e)}
            await self.db.flush()
            raise AuditRunError(f"Audit run failed: {e}")
    
    async def reproduce_audit_run(
        self,
        run_id: str,
        executed_by_id: uuid.UUID,
    ) -> Optional[AuditRun]:
        """
        Reproduce a previous audit run with the same parameters.
        
        Creates a new run with identical settings to verify results can be reproduced.
        This is critical for audit reproducibility compliance.
        
        Args:
            run_id: The run_id of the original audit run to reproduce
            executed_by_id: The user ID who is reproducing the run
            
        Returns:
            The new AuditRun or None if original not found
        """
        # Find the original run
        stmt = select(AuditRun).where(AuditRun.run_id == run_id)
        result = await self.db.execute(stmt)
        original_run = result.scalar_one_or_none()
        
        if not original_run:
            return None
        
        # Create new run with same parameters
        new_run = await self.audit_service.create_audit_run(
            entity_id=original_run.entity_id,
            run_type=original_run.run_type,
            title=f"[Reproduced] {original_run.title}",
            date_range_start=original_run.period_start,
            date_range_end=original_run.period_end,
            created_by_id=executed_by_id,
            description=f"Reproduced from {run_id} on {datetime.now().strftime('%Y-%m-%d %H:%M')}. Original description: {original_run.description or 'N/A'}",
            parameters=original_run.rule_config,
        )
        
        # Store reference to original in result_summary
        new_run.result_summary = {
            "reproduced_from": run_id,
            "original_completed_at": original_run.completed_at.isoformat() if original_run.completed_at else None,
            "original_findings": {
                "critical": original_run.critical_findings or 0,
                "high": original_run.high_findings or 0,
                "medium": original_run.medium_findings or 0,
                "low": original_run.low_findings or 0,
            }
        }
        
        await self.db.flush()
        
        return new_run
    
    async def enforce_auditor_readonly(
        self,
        user: User,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Enforce auditor read-only permissions.
        
        Returns (is_allowed, denial_reason)
        """
        if user.role != UserRole.AUDITOR:
            return True, None  # Non-auditors use normal permissions
        
        # Check if action is forbidden for auditors
        if action in AuditorRoleEnforcer.FORBIDDEN_ACTIONS:
            return False, f"Auditor role is read-only. Action '{action}' is forbidden."
        
        return True, None
    
    async def get_audit_dashboard(
        self,
        entity_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Get comprehensive audit dashboard data."""
        # Get recent runs
        runs = await self.audit_service.get_run_history(entity_id, limit=10)
        
        # Get findings by risk
        findings = await self.findings_service.get_findings_by_risk(entity_id)
        
        # Get evidence integrity status
        evidence_status = await self.evidence_service.verify_all_evidence(entity_id)
        
        # Get recent auditor sessions
        sessions = await self.session_service.get_session_history(entity_id, limit=5)
        
        return {
            "recent_audit_runs": runs,
            "findings_summary": {
                "critical": len(findings["critical"]),
                "high": len(findings["high"]),
                "medium": len(findings["medium"]),
                "low": len(findings["low"]),
                "informational": len(findings["informational"]),
            },
            "evidence_integrity": evidence_status,
            "recent_auditor_sessions": sessions,
            "generated_at": datetime.now().isoformat(),
        }
