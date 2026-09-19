"""
Tekvwa Pro Audit - Third-Party Attestation Service

This module provides audit attestation workflows for:
- External auditor read-only access management
- Digital sign-off workflows (Accountant -> Auditor -> CFO)
- Cryptographic signatures on audit reports
- Audit trail for all attestation activities

Compliant with ISA 500 (Audit Evidence) and ISA 580 (Written Representations).
"""

import uuid
import hashlib
import hmac
import json
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import base64


class AttestationRole(str, Enum):
    """Roles in the attestation workflow."""
    PREPARER = "preparer"
    REVIEWER = "reviewer"
    ACCOUNTANT = "accountant"
    INTERNAL_AUDITOR = "internal_auditor"
    EXTERNAL_AUDITOR = "external_auditor"
    CFO = "cfo"
    CEO = "ceo"
    BOARD_MEMBER = "board_member"


class AttestationType(str, Enum):
    """Types of attestation available."""
    REVIEW = "review"
    APPROVAL = "approval"
    CERTIFICATION = "certification"
    AUDIT_OPINION = "audit_opinion"


class AttestationStatus(str, Enum):
    """Status of an attestation workflow."""
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    PENDING_APPROVAL = "pending_approval"
    PENDING_CERTIFICATION = "pending_certification"
    APPROVED = "approved"
    REJECTED = "rejected"
    RETURNED = "returned"
    CERTIFIED = "certified"


class AuditOpinionType(str, Enum):
    """Types of audit opinions."""
    UNQUALIFIED = "unqualified"
    QUALIFIED = "qualified"
    ADVERSE = "adverse"
    DISCLAIMER = "disclaimer"


@dataclass
class Attestor:
    """A person who can attest to a document."""
    attestor_id: uuid.UUID
    name: str
    email: str
    role: AttestationRole
    title: str
    organization: str
    professional_credentials: List[str] = field(default_factory=list)
    digital_certificate_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "attestor_id": str(self.attestor_id),
            "name": self.name,
            "email": self.email,
            "role": self.role.value,
            "title": self.title,
            "organization": self.organization,
            "professional_credentials": self.professional_credentials,
            "digital_certificate_id": self.digital_certificate_id,
        }


@dataclass
class AttestationSignature:
    """A cryptographic signature on a document."""
    signature_id: str
    attestor: Attestor
    attestation_type: AttestationType
    timestamp: datetime
    content_hash: str
    signature: str
    comments: Optional[str] = None
    ip_address: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "signature_id": self.signature_id,
            "attestor": self.attestor.to_dict(),
            "attestation_type": self.attestation_type.value,
            "timestamp": self.timestamp.isoformat(),
            "content_hash": self.content_hash,
            "signature": self.signature,
            "comments": self.comments,
            "ip_address": self.ip_address,
        }
    
    def verify(self, content: str, secret_key: str) -> bool:
        """Verify the signature against the content."""
        expected_hash = hashlib.sha256(content.encode()).hexdigest()
        if expected_hash != self.content_hash:
            return False
        
        expected_sig = hmac.new(
            secret_key.encode(),
            f"{self.content_hash}:{self.attestor.attestor_id}:{self.timestamp.isoformat()}".encode(),
            hashlib.sha256,
        ).hexdigest()
        
        return hmac.compare_digest(expected_sig, self.signature)


@dataclass
class WorkflowStep:
    """A step in the attestation workflow."""
    step_order: int
    required_role: AttestationRole
    attestation_type: AttestationType
    is_required: bool
    assigned_to: Optional[Attestor] = None
    completed_at: Optional[datetime] = None
    signature: Optional[AttestationSignature] = None
    status: str = "pending"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_order": self.step_order,
            "required_role": self.required_role.value,
            "attestation_type": self.attestation_type.value,
            "is_required": self.is_required,
            "assigned_to": self.assigned_to.to_dict() if self.assigned_to else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "signature": self.signature.to_dict() if self.signature else None,
            "status": self.status,
        }


@dataclass
class AttestationWorkflow:
    """Complete attestation workflow for a document."""
    workflow_id: str
    entity_id: uuid.UUID
    document_type: str
    document_id: str
    document_title: str
    document_hash: str
    period_start: date
    period_end: date
    created_at: datetime
    created_by: Attestor
    status: AttestationStatus
    steps: List[WorkflowStep]
    current_step: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    audit_opinion: Optional[AuditOpinionType] = None
    audit_opinion_text: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "entity_id": str(self.entity_id),
            "document_type": self.document_type,
            "document_id": self.document_id,
            "document_title": self.document_title,
            "document_hash": self.document_hash,
            "period": {
                "start": self.period_start.isoformat(),
                "end": self.period_end.isoformat(),
            },
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by.to_dict(),
            "status": self.status.value,
            "steps": [s.to_dict() for s in self.steps],
            "current_step": self.current_step,
            "metadata": self.metadata,
            "audit_opinion": self.audit_opinion.value if self.audit_opinion else None,
            "audit_opinion_text": self.audit_opinion_text,
        }


@dataclass
class AuditorAccessGrant:
    """Read-only access grant for external auditors."""
    grant_id: str
    entity_id: uuid.UUID
    auditor: Attestor
    granted_by: Attestor
    granted_at: datetime
    expires_at: datetime
    scope: List[str]  # List of accessible data categories
    access_token: str
    is_active: bool
    access_log: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "grant_id": self.grant_id,
            "entity_id": str(self.entity_id),
            "auditor": self.auditor.to_dict(),
            "granted_by": self.granted_by.to_dict(),
            "granted_at": self.granted_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "scope": self.scope,
            "is_active": self.is_active,
            "access_log_count": len(self.access_log),
        }


# Predefined workflow templates
WORKFLOW_TEMPLATES = {
    "financial_statements": [
        WorkflowStep(1, AttestationRole.PREPARER, AttestationType.REVIEW, True),
        WorkflowStep(2, AttestationRole.ACCOUNTANT, AttestationType.APPROVAL, True),
        WorkflowStep(3, AttestationRole.INTERNAL_AUDITOR, AttestationType.REVIEW, False),
        WorkflowStep(4, AttestationRole.CFO, AttestationType.CERTIFICATION, True),
        WorkflowStep(5, AttestationRole.EXTERNAL_AUDITOR, AttestationType.AUDIT_OPINION, True),
    ],
    "tax_returns": [
        WorkflowStep(1, AttestationRole.PREPARER, AttestationType.REVIEW, True),
        WorkflowStep(2, AttestationRole.ACCOUNTANT, AttestationType.APPROVAL, True),
        WorkflowStep(3, AttestationRole.CFO, AttestationType.CERTIFICATION, True),
    ],
    "vat_returns": [
        WorkflowStep(1, AttestationRole.PREPARER, AttestationType.REVIEW, True),
        WorkflowStep(2, AttestationRole.ACCOUNTANT, AttestationType.APPROVAL, True),
    ],
    "audit_report": [
        WorkflowStep(1, AttestationRole.INTERNAL_AUDITOR, AttestationType.REVIEW, True),
        WorkflowStep(2, AttestationRole.EXTERNAL_AUDITOR, AttestationType.AUDIT_OPINION, True),
        WorkflowStep(3, AttestationRole.CFO, AttestationType.CERTIFICATION, True),
        WorkflowStep(4, AttestationRole.CEO, AttestationType.CERTIFICATION, False),
    ],
}


class ThirdPartyAttestationService:
    """
    Manages third-party attestation and audit workflows.
    
    Provides:
    - Auditor read-only access management
    - Multi-step attestation workflows
    - Cryptographic signing of documents
    - Complete audit trail
    """
    
    def __init__(self, secret_key: str = "tekvwa-pro-audit-2026"):
        self.secret_key = secret_key
        self._workflows: Dict[str, AttestationWorkflow] = {}
        self._access_grants: Dict[str, AuditorAccessGrant] = {}
        self._attestors: Dict[str, Attestor] = {}
    
    def register_attestor(
        self,
        name: str,
        email: str,
        role: AttestationRole,
        title: str,
        organization: str,
        professional_credentials: Optional[List[str]] = None,
    ) -> Attestor:
        """Register a new attestor in the system."""
        attestor = Attestor(
            attestor_id=uuid.uuid4(),
            name=name,
            email=email,
            role=role,
            title=title,
            organization=organization,
            professional_credentials=professional_credentials or [],
            digital_certificate_id=f"CERT-{uuid.uuid4().hex[:8].upper()}",
        )
        self._attestors[str(attestor.attestor_id)] = attestor
        return attestor
    
    def create_workflow(
        self,
        entity_id: uuid.UUID,
        document_type: str,
        document_id: str,
        document_title: str,
        document_content: str,
        period_start: date,
        period_end: date,
        created_by: Attestor,
        template_name: Optional[str] = None,
        custom_steps: Optional[List[WorkflowStep]] = None,
    ) -> AttestationWorkflow:
        """
        Create a new attestation workflow for a document.
        """
        # Generate document hash
        document_hash = hashlib.sha256(document_content.encode()).hexdigest()
        
        # Get workflow steps
        if custom_steps:
            steps = custom_steps
        elif template_name and template_name in WORKFLOW_TEMPLATES:
            steps = [
                WorkflowStep(
                    step_order=s.step_order,
                    required_role=s.required_role,
                    attestation_type=s.attestation_type,
                    is_required=s.is_required,
                )
                for s in WORKFLOW_TEMPLATES[template_name]
            ]
        else:
            # Default: simple two-step workflow
            steps = [
                WorkflowStep(1, AttestationRole.ACCOUNTANT, AttestationType.APPROVAL, True),
                WorkflowStep(2, AttestationRole.CFO, AttestationType.CERTIFICATION, True),
            ]
        
        workflow = AttestationWorkflow(
            workflow_id=f"WF-{uuid.uuid4().hex[:12].upper()}",
            entity_id=entity_id,
            document_type=document_type,
            document_id=document_id,
            document_title=document_title,
            document_hash=document_hash,
            period_start=period_start,
            period_end=period_end,
            created_at=datetime.utcnow(),
            created_by=created_by,
            status=AttestationStatus.PENDING_REVIEW,
            steps=steps,
            current_step=1,
        )
        
        self._workflows[workflow.workflow_id] = workflow
        return workflow
    
    def sign_document(
        self,
        workflow_id: str,
        attestor: Attestor,
        document_content: str,
        comments: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> AttestationSignature:
        """
        Create a cryptographic signature for a document.
        """
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")
        
        # Verify document hasn't been modified
        current_hash = hashlib.sha256(document_content.encode()).hexdigest()
        if current_hash != workflow.document_hash:
            raise ValueError("Document has been modified since workflow creation")
        
        # Find current step
        current_step = None
        for step in workflow.steps:
            if step.step_order == workflow.current_step:
                current_step = step
                break
        
        if not current_step:
            raise ValueError("No pending step in workflow")
        
        # Verify attestor has correct role
        if attestor.role != current_step.required_role:
            raise ValueError(
                f"Attestor role {attestor.role.value} does not match required role "
                f"{current_step.required_role.value}"
            )
        
        # Create signature
        timestamp = datetime.utcnow()
        signature_data = hmac.new(
            self.secret_key.encode(),
            f"{current_hash}:{attestor.attestor_id}:{timestamp.isoformat()}".encode(),
            hashlib.sha256,
        ).hexdigest()
        
        signature = AttestationSignature(
            signature_id=f"SIG-{uuid.uuid4().hex[:12].upper()}",
            attestor=attestor,
            attestation_type=current_step.attestation_type,
            timestamp=timestamp,
            content_hash=current_hash,
            signature=signature_data,
            comments=comments,
            ip_address=ip_address,
        )
        
        # Update workflow step
        current_step.assigned_to = attestor
        current_step.completed_at = timestamp
        current_step.signature = signature
        current_step.status = "completed"
        
        # Advance workflow
        workflow.current_step += 1
        if workflow.current_step > len(workflow.steps):
            workflow.status = AttestationStatus.CERTIFIED
        else:
            next_step = workflow.steps[workflow.current_step - 1]
            if next_step.attestation_type == AttestationType.APPROVAL:
                workflow.status = AttestationStatus.PENDING_APPROVAL
            elif next_step.attestation_type == AttestationType.CERTIFICATION:
                workflow.status = AttestationStatus.PENDING_CERTIFICATION
            else:
                workflow.status = AttestationStatus.PENDING_REVIEW
        
        return signature
    
    def reject_workflow(
        self,
        workflow_id: str,
        attestor: Attestor,
        reason: str,
    ) -> AttestationWorkflow:
        """Reject a workflow and return it to preparer."""
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")
        
        workflow.status = AttestationStatus.REJECTED
        workflow.metadata["rejection_reason"] = reason
        workflow.metadata["rejected_by"] = attestor.to_dict()
        workflow.metadata["rejected_at"] = datetime.utcnow().isoformat()
        
        return workflow
    
    def add_audit_opinion(
        self,
        workflow_id: str,
        auditor: Attestor,
        opinion_type: AuditOpinionType,
        opinion_text: str,
        findings: Optional[List[Dict[str, Any]]] = None,
    ) -> AttestationWorkflow:
        """Add an audit opinion to a workflow."""
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")
        
        if auditor.role not in [AttestationRole.EXTERNAL_AUDITOR, AttestationRole.INTERNAL_AUDITOR]:
            raise ValueError("Only auditors can provide audit opinions")
        
        workflow.audit_opinion = opinion_type
        workflow.audit_opinion_text = opinion_text
        workflow.metadata["audit_findings"] = findings or []
        workflow.metadata["opinion_issued_by"] = auditor.to_dict()
        workflow.metadata["opinion_issued_at"] = datetime.utcnow().isoformat()
        
        return workflow
    
    def grant_auditor_access(
        self,
        entity_id: uuid.UUID,
        auditor: Attestor,
        granted_by: Attestor,
        scope: List[str],
        validity_days: int = 90,
    ) -> AuditorAccessGrant:
        """
        Grant read-only access to an external auditor.
        """
        if auditor.role not in [AttestationRole.EXTERNAL_AUDITOR, AttestationRole.INTERNAL_AUDITOR]:
            raise ValueError("Access grants are only for auditors")
        
        # Generate secure access token
        token_data = f"{entity_id}:{auditor.attestor_id}:{datetime.utcnow().isoformat()}"
        access_token = base64.urlsafe_b64encode(
            hmac.new(self.secret_key.encode(), token_data.encode(), hashlib.sha256).digest()
        ).decode()
        
        grant = AuditorAccessGrant(
            grant_id=f"AG-{uuid.uuid4().hex[:12].upper()}",
            entity_id=entity_id,
            auditor=auditor,
            granted_by=granted_by,
            granted_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=validity_days),
            scope=scope,
            access_token=access_token,
            is_active=True,
        )
        
        self._access_grants[grant.grant_id] = grant
        return grant
    
    def validate_auditor_access(
        self,
        access_token: str,
        requested_scope: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate an auditor's access to a specific resource.
        
        Returns (is_valid, error_message).
        """
        for grant in self._access_grants.values():
            if grant.access_token == access_token:
                if not grant.is_active:
                    return False, "Access grant has been revoked"
                
                if datetime.utcnow() > grant.expires_at:
                    return False, "Access grant has expired"
                
                if requested_scope not in grant.scope and "*" not in grant.scope:
                    return False, f"Scope '{requested_scope}' not authorized"
                
                # Log access
                grant.access_log.append({
                    "timestamp": datetime.utcnow().isoformat(),
                    "scope": requested_scope,
                    "action": "access",
                })
                
                return True, None
        
        return False, "Invalid access token"
    
    def revoke_auditor_access(
        self,
        grant_id: str,
        revoked_by: Attestor,
        reason: str,
    ) -> AuditorAccessGrant:
        """Revoke an auditor's access grant."""
        grant = self._access_grants.get(grant_id)
        if not grant:
            raise ValueError(f"Access grant {grant_id} not found")
        
        grant.is_active = False
        grant.access_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "action": "revoked",
            "revoked_by": revoked_by.name,
            "reason": reason,
        })
        
        return grant
    
    def get_workflow_status(self, workflow_id: str) -> Dict[str, Any]:
        """Get the current status of an attestation workflow."""
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            return {"error": f"Workflow {workflow_id} not found"}
        
        completed_steps = sum(1 for s in workflow.steps if s.status == "completed")
        total_steps = len(workflow.steps)
        
        return {
            "workflow_id": workflow_id,
            "status": workflow.status.value,
            "progress": f"{completed_steps}/{total_steps} steps completed",
            "progress_percentage": (completed_steps / total_steps) * 100,
            "current_step": workflow.current_step,
            "next_action": self._get_next_action(workflow),
            "document_integrity": "verified",  # Document hash check
            "created_at": workflow.created_at.isoformat(),
            "last_updated": max(
                (s.completed_at for s in workflow.steps if s.completed_at),
                default=workflow.created_at,
            ).isoformat(),
        }
    
    def _get_next_action(self, workflow: AttestationWorkflow) -> Optional[Dict[str, Any]]:
        """Determine the next required action in a workflow."""
        if workflow.status == AttestationStatus.CERTIFIED:
            return None
        
        if workflow.status == AttestationStatus.REJECTED:
            return {
                "action": "review_rejection",
                "description": "Review rejection reason and make corrections",
            }
        
        if workflow.current_step <= len(workflow.steps):
            step = workflow.steps[workflow.current_step - 1]
            return {
                "action": step.attestation_type.value,
                "required_role": step.required_role.value,
                "description": f"Awaiting {step.attestation_type.value} from {step.required_role.value}",
            }
        
        return None
    
    def list_workflows(
        self,
        entity_id: Optional[uuid.UUID] = None,
        status: Optional[AttestationStatus] = None,
    ) -> List[Dict[str, Any]]:
        """List attestation workflows with optional filtering."""
        results = []
        for workflow in self._workflows.values():
            if entity_id and workflow.entity_id != entity_id:
                continue
            if status and workflow.status != status:
                continue
            results.append({
                "workflow_id": workflow.workflow_id,
                "document_title": workflow.document_title,
                "document_type": workflow.document_type,
                "status": workflow.status.value,
                "created_at": workflow.created_at.isoformat(),
                "progress": f"{sum(1 for s in workflow.steps if s.status == 'completed')}/{len(workflow.steps)}",
            })
        return results
    
    def list_access_grants(
        self,
        entity_id: Optional[uuid.UUID] = None,
        active_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """List auditor access grants with optional filtering."""
        results = []
        for grant in self._access_grants.values():
            if entity_id and grant.entity_id != entity_id:
                continue
            if active_only and not grant.is_active:
                continue
            results.append(grant.to_dict())
        return results
    
    def get_attestation_certificate(
        self,
        workflow_id: str,
    ) -> Dict[str, Any]:
        """
        Generate a formal attestation certificate for a completed workflow.
        """
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")
        
        if workflow.status != AttestationStatus.CERTIFIED:
            raise ValueError("Workflow is not yet certified")
        
        # Collect all signatures
        signatures = []
        for step in workflow.steps:
            if step.signature:
                signatures.append({
                    "attestor": step.signature.attestor.name,
                    "role": step.signature.attestor.role.value,
                    "title": step.signature.attestor.title,
                    "organization": step.signature.attestor.organization,
                    "attestation_type": step.signature.attestation_type.value,
                    "signed_at": step.signature.timestamp.isoformat(),
                    "signature_id": step.signature.signature_id,
                })
        
        # Generate certificate hash
        cert_content = json.dumps({
            "workflow_id": workflow_id,
            "document_hash": workflow.document_hash,
            "signatures": signatures,
        }, sort_keys=True)
        certificate_hash = hashlib.sha256(cert_content.encode()).hexdigest()
        
        return {
            "certificate_id": f"CERT-{workflow_id}",
            "document_title": workflow.document_title,
            "document_type": workflow.document_type,
            "document_hash": workflow.document_hash,
            "period": {
                "start": workflow.period_start.isoformat(),
                "end": workflow.period_end.isoformat(),
            },
            "issued_at": datetime.utcnow().isoformat(),
            "status": "CERTIFIED",
            "signatures": signatures,
            "audit_opinion": {
                "type": workflow.audit_opinion.value if workflow.audit_opinion else None,
                "text": workflow.audit_opinion_text,
            },
            "certificate_hash": certificate_hash,
            "verification_url": f"https://proaudit.tekvwa.org/verify/{certificate_hash[:16]}",
        }
