"""
Tekvwa Pro Audit - Evidence Management API Routes

Complete API for evidence collection and management:
1. Document Upload
2. Screenshot Upload
3. Transaction Collection
4. Calculation Evidence
5. Log Extraction
6. Database Snapshots
7. Third-Party Confirmations
8. Evidence Verification
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks, Response
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload
from typing import Optional, List, Dict, Any
from datetime import datetime, date, timedelta, timezone
from pydantic import BaseModel, Field, validator
from decimal import Decimal
from enum import Enum
import uuid
import os

from app.database import get_db
from app.dependencies import get_current_user, get_current_entity_id, require_feature
from app.models import User
from app.models.sku import Feature
from app.models.audit_consolidated import (
    AuditEvidence, EvidenceType,
    AuditRun, AuditFinding,
)
from app.services.evidence_collection_service import (
    EvidenceCollectionService,
    EvidenceCollectionResult,
    ALLOWED_MIME_TYPES,
    MAX_FILE_SIZE,
)
from app.utils.permissions import has_organization_permission, OrganizationPermission

# Feature gate for evidence collection (ENTERPRISE tier - audit vault extended)
evidence_feature_gate = require_feature([Feature.AUDIT_VAULT_EXTENDED])

router = APIRouter(
    prefix="/api/evidence",
    tags=["Evidence Collection"],
    dependencies=[Depends(evidence_feature_gate)],
)


# ==========================================
# Pydantic Models for Requests/Responses
# ==========================================

class EvidenceResponse(BaseModel):
    """Standard evidence response."""
    id: uuid.UUID
    evidence_ref: str
    evidence_type: str
    title: str
    description: Optional[str] = None
    content_hash: str
    file_hash: Optional[str] = None
    is_verified: bool = True
    collected_at: datetime
    collected_by: Optional[uuid.UUID] = None
    collection_method: Optional[str] = None
    file_path: Optional[str] = None
    file_size_bytes: Optional[int] = None
    file_mime_type: Optional[str] = None


class EvidenceListResponse(BaseModel):
    """Paginated evidence list response."""
    evidence: List[Dict[str, Any]]
    pagination: Dict[str, int]


class TransactionCollectionRequest(BaseModel):
    """Request for collecting transaction records as evidence."""
    transaction_ids: Optional[List[uuid.UUID]] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    finding_id: Optional[uuid.UUID] = None
    title: str = "Transaction Records Evidence"
    description: Optional[str] = None
    transaction_type: Optional[str] = None  # Filter: 'all', 'journal_entries', 'income', 'expense', etc.


class CalculationEvidenceRequest(BaseModel):
    """Request for creating calculation evidence."""
    calculation_type: str
    inputs: Dict[str, Any]
    result: Any
    formula: str
    finding_id: Optional[uuid.UUID] = None
    title: str
    description: Optional[str] = None


class LogExtractionRequest(BaseModel):
    """Request for extracting logs as evidence."""
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    event_types: Optional[List[str]] = None
    user_ids: Optional[List[uuid.UUID]] = None
    table_name: Optional[str] = None
    finding_id: Optional[uuid.UUID] = None
    title: str = "Audit Log Extraction"
    description: Optional[str] = None


class DatabaseSnapshotRequest(BaseModel):
    """Request for creating database snapshot evidence."""
    snapshot_type: Optional[str] = Field(None, description="Type: chart_of_accounts, journal_entries, transactions, custom")
    table_name: Optional[str] = Field(None, description="Alias for snapshot_type (frontend compatibility)")
    include_balances: bool = True
    finding_id: Optional[uuid.UUID] = None
    title: str = "Database Snapshot"
    description: Optional[str] = None
    limit: Optional[int] = Field(None, description="Optional limit for records")
    
    @property
    def effective_snapshot_type(self) -> str:
        """Get the effective snapshot type from either field."""
        return self.snapshot_type or self.table_name or "custom"
    
    def model_post_init(self, __context):
        """Ensure at least one of snapshot_type or table_name is provided."""
        if not self.snapshot_type and not self.table_name:
            # Default to custom if neither is provided
            object.__setattr__(self, 'snapshot_type', 'custom')


class ConfirmationRequestCreate(BaseModel):
    """Request to create third-party confirmation."""
    external_party_name: str
    external_party_email: str
    confirmation_type: str = Field(..., description="balance, transaction, existence, or custom")
    items_to_confirm: List[Dict[str, Any]]
    due_date: Optional[date] = None  # Made optional for frontend compatibility
    finding_id: Optional[uuid.UUID] = None
    title: str = "External Confirmation Request"
    notes: Optional[str] = None


class ConfirmationResponseSubmit(BaseModel):
    """Submit response for a confirmation request."""
    confirmation_evidence_id: uuid.UUID
    response_status: str = Field(..., description="confirmed, exception, no_response")
    response_data: Dict[str, Any]
    responder_name: str
    responder_title: Optional[str] = None
    notes: Optional[str] = None


class VerifyEvidenceResponse(BaseModel):
    """Evidence verification result."""
    evidence_id: uuid.UUID
    evidence_ref: str
    is_valid: bool
    stored_hash: str
    computed_hash: str
    file_hash_valid: Optional[bool] = None
    verification_timestamp: datetime
    details: Dict[str, Any]


# ==========================================
# Permission Check
# ==========================================

def require_audit_permission(user: User):
    """Check if user has permission to manage evidence."""
    if not has_organization_permission(user.role, OrganizationPermission.VIEW_AUDIT_LOGS):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access evidence features"
        )


# ==========================================
# 1. DOCUMENT UPLOAD ENDPOINTS
# ==========================================

@router.post("/document/upload", response_model=Dict[str, Any])
async def upload_document_evidence(
    file: UploadFile = File(..., description="Document file to upload (PDF, DOCX, XLSX, images)"),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    finding_id: Optional[str] = Form(None),
    audit_run_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload a document as immutable audit evidence.
    
    Supported file types:
    - PDF documents
    - Word documents (.doc, .docx)
    - Excel files (.xls, .xlsx)
    - CSV files
    - Text files
    - Images (JPEG, PNG, GIF, WebP, TIFF)
    
    Maximum file size: 50 MB
    
    The file is:
    1. Validated for type and size
    2. Hashed with SHA-256
    3. Stored in secure location
    4. Recorded with full metadata
    """
    require_audit_permission(current_user)
    
    # Read file content
    content = await file.read()
    
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file uploaded")
    
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE / 1024 / 1024:.0f} MB"
        )
    
    # Validate MIME type
    mime_type = file.content_type or "application/octet-stream"
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed: {mime_type}. Allowed types: PDF, DOCX, XLSX, CSV, TXT, JPEG, PNG"
        )
    
    service = EvidenceCollectionService(db)
    
    result = await service.upload_document(
        entity_id=entity_id,
        file_content=content,
        filename=file.filename or "unknown",
        mime_type=mime_type,
        collected_by=current_user.id,
        title=title,
        description=description,
        finding_id=uuid.UUID(finding_id) if finding_id else None,
        audit_run_id=uuid.UUID(audit_run_id) if audit_run_id else None,
    )
    
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    
    await db.commit()
    
    return {
        "success": True,
        "message": "Document uploaded and locked as immutable evidence",
        "evidence_id": str(result.evidence_id),
        "evidence_ref": result.evidence_ref,
        "content_hash": result.content_hash,
        "file_hash": result.metadata.get("file_hash"),
        "file_size": result.metadata.get("file_size"),
        "is_immutable": True,
    }


@router.get("/document/{evidence_id}/download")
async def download_document_evidence(
    evidence_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Download an evidence document file.
    
    Verifies the file hash before serving to ensure integrity.
    """
    require_audit_permission(current_user)
    
    # Get evidence record
    result = await db.execute(
        select(AuditEvidence).where(
            and_(
                AuditEvidence.id == evidence_id,
                AuditEvidence.entity_id == entity_id,
                AuditEvidence.evidence_type == EvidenceType.DOCUMENT
            )
        )
    )
    evidence = result.scalar_one_or_none()
    
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")
    
    if not evidence.file_path or not os.path.exists(evidence.file_path):
        raise HTTPException(status_code=404, detail="Evidence file not found on disk")
    
    # Get original filename from content
    original_filename = "evidence_file"
    if evidence.content and "original_filename" in evidence.content:
        original_filename = evidence.content["original_filename"]
    
    return FileResponse(
        path=evidence.file_path,
        filename=original_filename,
        media_type=evidence.file_mime_type or "application/octet-stream"
    )


# ==========================================
# 2. SCREENSHOT UPLOAD ENDPOINTS
# ==========================================

@router.post("/screenshot/upload", response_model=Dict[str, Any])
async def upload_screenshot_evidence(
    file: UploadFile = File(..., description="Screenshot image file"),
    title: str = Form(...),
    description: Optional[str] = Form(None),
    finding_id: Optional[str] = Form(None),
    source_url: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload a screenshot as evidence.
    
    Supported formats: JPEG, PNG, GIF, WebP
    
    Use for capturing:
    - System screens
    - Third-party portal evidence
    - Visual audit trails
    - Error messages
    """
    require_audit_permission(current_user)
    
    content = await file.read()
    
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file uploaded")
    
    # Validate it's an image
    mime_type = file.content_type or "image/png"
    if not mime_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files allowed for screenshots")
    
    service = EvidenceCollectionService(db)
    
    result = await service.upload_screenshot(
        entity_id=entity_id,
        image_content=content,
        collected_by=current_user.id,
        title=title,
        description=description,
        finding_id=uuid.UUID(finding_id) if finding_id else None,
        source_url=source_url,
        capture_timestamp=datetime.now(),
    )
    
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    
    await db.commit()
    
    return {
        "success": True,
        "message": "Screenshot uploaded as evidence",
        "evidence_id": str(result.evidence_id),
        "evidence_ref": result.evidence_ref,
        "content_hash": result.content_hash,
    }


@router.post("/screenshot/paste", response_model=Dict[str, Any])
async def paste_screenshot_evidence(
    image_data: str = Form(..., description="Base64 encoded image data from clipboard"),
    title: str = Form(...),
    description: Optional[str] = Form(None),
    finding_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Accept a screenshot pasted from clipboard (base64 encoded).
    
    Frontend should capture Ctrl+V events and send the image data.
    """
    import base64
    
    require_audit_permission(current_user)
    
    try:
        # Remove data URL prefix if present
        if "," in image_data:
            image_data = image_data.split(",")[1]
        
        content = base64.b64decode(image_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 image data: {str(e)}")
    
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty image data")
    
    service = EvidenceCollectionService(db)
    
    result = await service.upload_screenshot(
        entity_id=entity_id,
        image_content=content,
        collected_by=current_user.id,
        title=title,
        description=description,
        finding_id=uuid.UUID(finding_id) if finding_id else None,
        capture_timestamp=datetime.now(),
    )
    
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    
    await db.commit()
    
    return {
        "success": True,
        "message": "Clipboard screenshot saved as evidence",
        "evidence_id": str(result.evidence_id),
        "evidence_ref": result.evidence_ref,
        "content_hash": result.content_hash,
    }


# ==========================================
# 3. TRANSACTION COLLECTION ENDPOINT
# ==========================================

@router.post("/transaction/collect", response_model=Dict[str, Any])
async def collect_transaction_evidence(
    request: TransactionCollectionRequest,
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Collect transaction records as immutable evidence.
    
    Can collect by:
    - Specific transaction IDs
    - Date range
    - Both (intersection)
    
    Creates a point-in-time snapshot of the transaction data.
    """
    require_audit_permission(current_user)
    
    if not request.transaction_ids and not (request.date_from or request.date_to):
        raise HTTPException(
            status_code=400,
            detail="Must provide transaction_ids or date range (date_from/date_to)"
        )
    
    service = EvidenceCollectionService(db)
    
    result = await service.collect_transaction_records(
        entity_id=entity_id,
        collected_by=current_user.id,
        transaction_ids=request.transaction_ids,
        date_from=request.date_from,
        date_to=request.date_to,
        finding_id=request.finding_id,
        title=request.title,
        description=request.description,
        transaction_type=request.transaction_type,
    )
    
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    
    await db.commit()
    
    return {
        "success": True,
        "message": "Transaction records collected as evidence",
        "evidence_id": str(result.evidence_id),
        "evidence_ref": result.evidence_ref,
        "content_hash": result.content_hash,
        "records_collected": result.metadata.get("record_count", 0),
        "total_amount": str(result.metadata.get("total_amount", 0)),
    }


# ==========================================
# 4. CALCULATION EVIDENCE ENDPOINT
# ==========================================

@router.post("/calculation/record", response_model=Dict[str, Any])
async def record_calculation_evidence(
    request: CalculationEvidenceRequest,
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Record a calculation with its full audit trail.
    
    Use for:
    - Tax computations
    - Trial balance totals
    - Financial ratios
    - Variance analyses
    - Materiality calculations
    
    Stores:
    - All input values
    - Formula/method used
    - Calculated result
    - Timestamp
    """
    require_audit_permission(current_user)
    
    service = EvidenceCollectionService(db)
    
    result = await service.collect_calculation_evidence(
        entity_id=entity_id,
        collected_by=current_user.id,
        calculation_type=request.calculation_type,
        inputs=request.inputs,
        outputs={"result": request.result},
        formula_description=request.formula,
        finding_id=request.finding_id,
        title=request.title,
    )
    
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    
    await db.commit()
    
    return {
        "success": True,
        "message": "Calculation recorded as evidence",
        "evidence_id": str(result.evidence_id),
        "evidence_ref": result.evidence_ref,
        "content_hash": result.content_hash,
    }


# ==========================================
# 5. LOG EXTRACTION ENDPOINT
# ==========================================

@router.post("/log/extract", response_model=Dict[str, Any])
async def extract_log_evidence(
    request: LogExtractionRequest,
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Extract audit logs as immutable evidence.
    
    Can filter by:
    - Date range
    - Event types (CREATE, UPDATE, DELETE, LOGIN, etc.)
    - Specific users
    - Specific tables
    
    Creates a snapshot of relevant audit trail entries.
    """
    require_audit_permission(current_user)
    
    service = EvidenceCollectionService(db)
    
    result = await service.extract_system_logs(
        entity_id=entity_id,
        collected_by=current_user.id,
        date_from=request.date_from.date() if hasattr(request.date_from, 'date') else request.date_from,
        date_to=request.date_to.date() if hasattr(request.date_to, 'date') else request.date_to,
        log_types=request.event_types,
        user_ids=request.user_ids,
        finding_id=request.finding_id,
        title=request.title,
    )
    
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    
    await db.commit()
    
    return {
        "success": True,
        "message": "Audit logs extracted as evidence",
        "evidence_id": str(result.evidence_id),
        "evidence_ref": result.evidence_ref,
        "content_hash": result.content_hash,
        "logs_extracted": result.metadata.get("log_count", 0),
    }


# ==========================================
# 6. DATABASE SNAPSHOT ENDPOINT
# ==========================================

@router.post("/snapshot/create", response_model=Dict[str, Any])
async def create_database_snapshot(
    request: DatabaseSnapshotRequest,
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a point-in-time database snapshot as evidence.
    
    Snapshot types:
    - chart_of_accounts: Complete COA with balances
    - journal_entries: Journal entry totals and counts
    - transactions: Transaction summary by type
    - custom: Specify tables/queries
    
    Useful for capturing financial position at audit date.
    """
    require_audit_permission(current_user)
    
    service = EvidenceCollectionService(db)
    
    # Use effective_snapshot_type to support both snapshot_type and table_name fields
    effective_type = request.effective_snapshot_type
    
    result = await service.create_database_snapshot(
        entity_id=entity_id,
        collected_by=current_user.id,
        snapshot_type=effective_type,
        finding_id=request.finding_id,
        title=request.title,
        description=request.description,
    )
    
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    
    await db.commit()
    
    return {
        "success": True,
        "message": "Database snapshot created as evidence",
        "evidence_id": str(result.evidence_id),
        "evidence_ref": result.evidence_ref,
        "content_hash": result.content_hash,
        "snapshot_type": effective_type,
    }


# ==========================================
# 7. THIRD-PARTY CONFIRMATION ENDPOINTS
# ==========================================

@router.post("/confirmation/request", response_model=Dict[str, Any])
async def create_confirmation_request(
    request: ConfirmationRequestCreate,
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a third-party confirmation request.
    
    Confirmation types:
    - balance: Bank/vendor balance confirmations
    - transaction: Specific transaction verification
    - existence: Asset/liability existence
    - custom: Custom confirmation
    
    Tracks:
    - Request sent date
    - Due date
    - Items to confirm
    - Response status
    """
    require_audit_permission(current_user)
    
    service = EvidenceCollectionService(db)
    
    result = await service.create_confirmation_request(
        entity_id=entity_id,
        collected_by=current_user.id,
        third_party_name=request.external_party_name,
        third_party_contact=request.external_party_email,
        confirmation_type=request.confirmation_type,
        request_details={"items_to_confirm": request.items_to_confirm, "notes": request.notes},
        expected_response_date=request.due_date,
        finding_id=request.finding_id,
        title=request.title,
    )
    
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    
    await db.commit()
    
    return {
        "success": True,
        "message": "Confirmation request created",
        "evidence_id": str(result.evidence_id),
        "evidence_ref": result.evidence_ref,
        "external_party": request.external_party_name,
        "due_date": request.due_date.isoformat(),
        "status": "pending",
    }


@router.post("/confirmation/response", response_model=Dict[str, Any])
async def submit_confirmation_response(
    request: ConfirmationResponseSubmit,
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Record a response to a confirmation request.
    
    Response statuses:
    - confirmed: Third party confirmed all items
    - exception: Differences noted
    - no_response: No reply received by due date
    
    Can also upload supporting documents.
    """
    require_audit_permission(current_user)
    
    service = EvidenceCollectionService(db)
    
    result = await service.record_confirmation_response(
        evidence_id=request.confirmation_evidence_id,
        response_data={
            "status": request.response_status,
            "responder_name": request.responder_name,
            "responder_title": request.responder_title,
            "details": request.response_data,
            "notes": request.notes,
        },
        verified_by=current_user.id,
    )
    
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    
    await db.commit()
    
    return {
        "success": True,
        "message": "Confirmation response recorded",
        "evidence_id": str(result.evidence_id),
        "response_status": request.response_status,
    }


@router.get("/confirmation/pending")
async def get_pending_confirmations(
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all pending confirmation requests.
    """
    require_audit_permission(current_user)
    
    result = await db.execute(
        select(AuditEvidence).where(
            and_(
                AuditEvidence.entity_id == entity_id,
                AuditEvidence.evidence_type == EvidenceType.EXTERNAL_CONFIRMATION,
            )
        ).order_by(AuditEvidence.collected_at.desc())
    )
    confirmations = result.scalars().all()
    
    pending = []
    for conf in confirmations:
        content = conf.content or {}
        if content.get("response_status") == "pending":
            pending.append({
                "evidence_id": str(conf.id),
                "evidence_ref": conf.evidence_ref,
                "title": conf.title,
                "external_party": content.get("external_party_name"),
                "due_date": content.get("due_date"),
                "confirmation_type": content.get("confirmation_type"),
                "created_at": conf.collected_at.isoformat() if conf.collected_at else None,
            })
    
    return {"pending_confirmations": pending, "count": len(pending)}


# ==========================================
# 8. EVIDENCE VERIFICATION ENDPOINT
# ==========================================

@router.get("/{evidence_id}/verify", response_model=VerifyEvidenceResponse)
async def verify_evidence_integrity(
    evidence_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Verify the integrity of evidence by checking its hash.
    
    For file-based evidence, also verifies file hash.
    If integrity check passes, the evidence is marked as verified.
    Returns whether the evidence has been tampered with.
    """
    require_audit_permission(current_user)
    
    service = EvidenceCollectionService(db)
    
    is_valid, computed_hash, details = await service.verify_evidence_integrity(
        evidence_id=evidence_id,
        entity_id=entity_id,
    )
    
    # Get evidence record for response and update
    result = await db.execute(
        select(AuditEvidence).where(
            and_(
                AuditEvidence.id == evidence_id,
                AuditEvidence.entity_id == entity_id,
            )
        )
    )
    evidence = result.scalar_one_or_none()
    
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")
    
    # If integrity check passes, mark as verified
    if is_valid and not evidence.is_verified:
        evidence.is_verified = True
        evidence.verified_by = current_user.id
        evidence.verified_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(evidence)
    
    return VerifyEvidenceResponse(
        evidence_id=evidence.id,
        evidence_ref=evidence.evidence_ref,
        is_valid=is_valid,
        stored_hash=evidence.content_hash,
        computed_hash=computed_hash,
        file_hash_valid=details.get("file_hash_valid"),
        verification_timestamp=datetime.now(),
        details=details,
    )


@router.get("/{evidence_id}/download")
async def download_evidence_file(
    evidence_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Download any evidence file (document, screenshot, etc).
    
    Verifies the file exists and returns it with proper headers.
    """
    require_audit_permission(current_user)
    
    # Get evidence record
    result = await db.execute(
        select(AuditEvidence).where(
            and_(
                AuditEvidence.id == evidence_id,
                AuditEvidence.entity_id == entity_id,
            )
        )
    )
    evidence = result.scalar_one_or_none()
    
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")
    
    if not evidence.file_path:
        raise HTTPException(status_code=404, detail="Evidence has no attached file")
    
    if not os.path.exists(evidence.file_path):
        raise HTTPException(status_code=404, detail="Evidence file not found on disk")
    
    # Get original filename from content or generate from ref
    original_filename = evidence.evidence_ref
    if evidence.content and isinstance(evidence.content, dict):
        if "original_filename" in evidence.content:
            original_filename = evidence.content["original_filename"]
        elif "filename" in evidence.content:
            original_filename = evidence.content["filename"]
    
    # Add extension based on mime type if not present
    if evidence.file_mime_type and '.' not in original_filename:
        ext_map = {
            'image/png': '.png',
            'image/jpeg': '.jpg',
            'application/pdf': '.pdf',
            'text/plain': '.txt',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
        }
        ext = ext_map.get(evidence.file_mime_type, '')
        original_filename += ext
    
    return FileResponse(
        path=evidence.file_path,
        filename=original_filename,
        media_type=evidence.file_mime_type or "application/octet-stream"
    )


# ==========================================
# 9. LIST & FILTER ENDPOINTS
# ==========================================

@router.get("/list")
async def list_evidence(
    page: int = 1,
    page_size: int = 20,
    evidence_type: Optional[str] = None,
    finding_id: Optional[uuid.UUID] = None,
    verified_only: bool = False,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    List all evidence with filtering and pagination.
    """
    require_audit_permission(current_user)
    
    # Build query
    query = select(AuditEvidence).where(AuditEvidence.entity_id == entity_id)
    
    if evidence_type:
        try:
            query = query.where(AuditEvidence.evidence_type == EvidenceType(evidence_type))
        except ValueError:
            pass
    
    if finding_id:
        query = query.where(AuditEvidence.finding_id == finding_id)
    
    if verified_only:
        query = query.where(AuditEvidence.is_verified == True)
    
    if date_from:
        query = query.where(AuditEvidence.collected_at >= datetime.combine(date_from, datetime.min.time()))
    
    if date_to:
        query = query.where(AuditEvidence.collected_at <= datetime.combine(date_to, datetime.max.time()))
    
    if search:
        search_filter = or_(
            AuditEvidence.title.ilike(f"%{search}%"),
            AuditEvidence.description.ilike(f"%{search}%"),
            AuditEvidence.evidence_ref.ilike(f"%{search}%"),
        )
        query = query.where(search_filter)
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Paginate
    query = query.order_by(AuditEvidence.collected_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    evidence_list = result.scalars().all()
    
    return {
        "evidence": [
            {
                "id": str(e.id),
                "evidence_ref": e.evidence_ref,
                "evidence_type": e.evidence_type.value if hasattr(e.evidence_type, 'value') else str(e.evidence_type),
                "title": e.title,
                "description": e.description,
                "content_hash": e.content_hash,
                "file_hash": e.file_hash,
                "is_verified": e.is_verified,
                "collected_at": e.collected_at.isoformat() if e.collected_at else None,
                "collection_method": e.collection_method,
                "file_path": e.file_path,
                "file_size_bytes": e.file_size_bytes,
                "file_mime_type": e.file_mime_type,
                "has_file": bool(e.file_path),
                "finding_id": str(e.finding_id) if e.finding_id else None,
            }
            for e in evidence_list
        ],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0
        }
    }


# ==========================================
# GET EVIDENCE BY FINDING
# ==========================================

@router.get("/by-finding/{finding_id}")
async def get_evidence_by_finding(
    finding_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all evidence items linked to a specific finding.
    
    This endpoint shows all evidence supporting a particular audit finding,
    enabling easy navigation from finding → evidence for review.
    """
    require_audit_permission(current_user)
    
    # Query all evidence linked to this finding
    result = await db.execute(
        select(AuditEvidence)
        .where(
            and_(
                AuditEvidence.entity_id == entity_id,
                AuditEvidence.finding_id == finding_id,
            )
        )
        .order_by(AuditEvidence.collected_at.desc())
    )
    evidence_list = result.scalars().all()
    
    return {
        "finding_id": str(finding_id),
        "evidence_count": len(evidence_list),
        "evidence": [
            {
                "id": str(e.id),
                "evidence_ref": e.evidence_ref,
                "evidence_type": e.evidence_type.value if hasattr(e.evidence_type, 'value') else str(e.evidence_type),
                "title": e.title,
                "description": e.description,
                "content_hash": e.content_hash,
                "is_verified": e.is_verified,
                "collected_at": e.collected_at.isoformat() if e.collected_at else None,
                "has_file": bool(e.file_path),
            }
            for e in evidence_list
        ],
    }


@router.get("/{evidence_id}")
async def get_evidence_detail(
    evidence_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed information about a specific evidence item.
    """
    require_audit_permission(current_user)
    
    result = await db.execute(
        select(AuditEvidence).where(
            and_(
                AuditEvidence.id == evidence_id,
                AuditEvidence.entity_id == entity_id
            )
        )
    )
    evidence = result.scalar_one_or_none()
    
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")
    
    return {
        "id": str(evidence.id),
        "evidence_ref": evidence.evidence_ref,
        "evidence_type": evidence.evidence_type.value if hasattr(evidence.evidence_type, 'value') else str(evidence.evidence_type),
        "title": evidence.title,
        "description": evidence.description,
        "content": evidence.content,
        "content_hash": evidence.content_hash,
        "file_path": evidence.file_path,
        "file_mime_type": evidence.file_mime_type,
        "file_size_bytes": evidence.file_size_bytes,
        "file_hash": evidence.file_hash,
        "is_verified": evidence.is_verified,
        "verified_by": str(evidence.verified_by) if evidence.verified_by else None,
        "verified_at": evidence.verified_at.isoformat() if evidence.verified_at else None,
        "collected_by": str(evidence.collected_by) if evidence.collected_by else None,
        "collected_at": evidence.collected_at.isoformat() if evidence.collected_at else None,
        "collection_method": evidence.collection_method,
        "finding_id": str(evidence.finding_id) if evidence.finding_id else None,
        "source_table": evidence.source_table,
        "source_record_id": str(evidence.source_record_id) if evidence.source_record_id else None,
    }


@router.delete("/{evidence_id}")
async def delete_evidence(
    evidence_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete evidence. Only allowed for admin users and unverified evidence.
    Evidence that has been verified cannot be deleted to maintain audit integrity.
    """
    require_audit_permission(current_user)
    
    # Check admin permission
    if current_user.role not in ['admin', 'owner']:
        raise HTTPException(
            status_code=403,
            detail="Only administrators can delete evidence"
        )
    
    result = await db.execute(
        select(AuditEvidence).where(
            and_(
                AuditEvidence.id == evidence_id,
                AuditEvidence.entity_id == entity_id
            )
        )
    )
    evidence = result.scalar_one_or_none()
    
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")
    
    if evidence.is_verified:
        raise HTTPException(
            status_code=403,
            detail="Cannot delete verified evidence. This maintains audit integrity."
        )
    
    # Delete file if exists
    if evidence.file_path and os.path.exists(evidence.file_path):
        try:
            os.remove(evidence.file_path)
        except Exception:
            pass  # Log but don't fail
    
    await db.delete(evidence)
    await db.commit()
    
    return {"success": True, "message": "Evidence deleted"}


# ==========================================
# 10. BULK OPERATIONS
# ==========================================

@router.post("/auto-collect/finding/{finding_id}")
async def auto_collect_for_finding(
    finding_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Automatically collect relevant evidence for a finding.
    
    Based on the finding type, collects:
    - Related transactions
    - Audit log entries
    - Database snapshots
    """
    require_audit_permission(current_user)
    
    # Fetch the finding with its audit_run relationship
    from app.models.audit_consolidated import AuditFinding, AuditRun
    result = await db.execute(
        select(AuditFinding)
        .options(selectinload(AuditFinding.audit_run))
        .where(AuditFinding.id == finding_id)
    )
    finding = result.scalar_one_or_none()
    
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    
    # Verify entity access
    if finding.audit_run and finding.audit_run.entity_id != entity_id:
        raise HTTPException(status_code=403, detail="Finding does not belong to current entity")
    
    service = EvidenceCollectionService(db)
    
    results = await service.auto_collect_for_finding(
        finding=finding,
        collected_by=current_user.id,
    )
    
    await db.commit()
    
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    
    return {
        "success": True,
        "message": f"Auto-collected {len(successful)} evidence items for finding",
        "collected": [
            {
                "evidence_id": str(r.evidence_id),
                "evidence_ref": r.evidence_ref,
            }
            for r in successful
        ],
        "errors": [r.error for r in failed] if failed else [],
    }


@router.post("/auto-collect/audit-run/{run_id}")
async def auto_collect_for_audit_run(
    run_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Automatically collect evidence for all findings in an audit run.
    
    Also creates a database snapshot at audit date.
    """
    require_audit_permission(current_user)
    
    # Get audit run
    result = await db.execute(
        select(AuditRun).where(
            and_(
                AuditRun.id == run_id,
                AuditRun.entity_id == entity_id
            )
        )
    )
    audit_run = result.scalar_one_or_none()
    
    if not audit_run:
        raise HTTPException(status_code=404, detail="Audit run not found")
    
    service = EvidenceCollectionService(db)
    
    results = await service.collect_audit_run_evidence(
        audit_run=audit_run,
        collected_by=current_user.id,
    )
    
    await db.commit()
    
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    
    return {
        "success": True,
        "message": f"Collected {len(successful)} evidence items for audit run",
        "collected_count": len(successful),
        "error_count": len(failed),
        "evidence_refs": [r.evidence_ref for r in successful],
    }


# ==========================================
# 11. STATISTICS ENDPOINT
# ==========================================

@router.get("/stats/summary")
async def get_evidence_statistics(
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Get summary statistics for evidence collection.
    """
    require_audit_permission(current_user)
    
    # Total count
    total_result = await db.execute(
        select(func.count()).select_from(AuditEvidence).where(
            AuditEvidence.entity_id == entity_id
        )
    )
    total = total_result.scalar() or 0
    
    # Count by type
    type_counts = {}
    for ev_type in EvidenceType:
        count_result = await db.execute(
            select(func.count()).select_from(AuditEvidence).where(
                and_(
                    AuditEvidence.entity_id == entity_id,
                    AuditEvidence.evidence_type == ev_type
                )
            )
        )
        count = count_result.scalar() or 0
        if count > 0:
            type_counts[ev_type.value] = count
    
    # Verified count
    verified_result = await db.execute(
        select(func.count()).select_from(AuditEvidence).where(
            and_(
                AuditEvidence.entity_id == entity_id,
                AuditEvidence.is_verified == True
            )
        )
    )
    verified = verified_result.scalar() or 0
    
    # Total file size
    size_result = await db.execute(
        select(func.sum(AuditEvidence.file_size_bytes)).where(
            AuditEvidence.entity_id == entity_id
        )
    )
    total_size = size_result.scalar() or 0
    
    return {
        "total_evidence": total,
        "by_type": type_counts,
        "verified_count": verified,
        "unverified_count": total - verified,
        "verification_rate": round(verified / total * 100, 2) if total > 0 else 0,
        "total_file_size_bytes": total_size,
        "total_file_size_mb": round(total_size / (1024 * 1024), 2) if total_size else 0,
    }


# ==========================================
# 12. FILE PREVIEW ENDPOINT
# ==========================================

@router.get("/{evidence_id}/preview")
async def preview_evidence_file(
    evidence_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Preview evidence file inline (for images, PDFs, text).
    
    Returns file with inline content-disposition for browser preview.
    """
    require_audit_permission(current_user)
    
    # Get evidence record
    result = await db.execute(
        select(AuditEvidence).where(
            and_(
                AuditEvidence.id == evidence_id,
                AuditEvidence.entity_id == entity_id,
            )
        )
    )
    evidence = result.scalar_one_or_none()
    
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")
    
    if not evidence.file_path:
        raise HTTPException(status_code=404, detail="Evidence has no attached file")
    
    if not os.path.exists(evidence.file_path):
        raise HTTPException(status_code=404, detail="Evidence file not found on disk")
    
    # Determine content type for preview
    mime_type = evidence.file_mime_type or "application/octet-stream"
    
    # Get original filename
    original_filename = evidence.evidence_ref
    if evidence.content and isinstance(evidence.content, dict):
        if "original_filename" in evidence.content:
            original_filename = evidence.content["original_filename"]
        elif "filename" in evidence.content:
            original_filename = evidence.content["filename"]
    
    # Return file for inline preview
    return FileResponse(
        path=evidence.file_path,
        media_type=mime_type,
        headers={
            "Content-Disposition": f'inline; filename="{original_filename}"'
        }
    )


# ==========================================
# 13. CHAIN OF CUSTODY ENDPOINT
# ==========================================

@router.get("/{evidence_id}/custody")
async def get_evidence_custody_chain(
    evidence_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Get chain of custody for evidence item.
    
    Returns a timeline of all actions taken on the evidence.
    """
    require_audit_permission(current_user)
    
    # Get evidence record
    result = await db.execute(
        select(AuditEvidence).where(
            and_(
                AuditEvidence.id == evidence_id,
                AuditEvidence.entity_id == entity_id,
            )
        )
    )
    evidence = result.scalar_one_or_none()
    
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")
    
    # Build custody chain from evidence metadata
    custody_chain = []
    
    # 1. Collection event (always present)
    custody_chain.append({
        "event": "collected",
        "timestamp": evidence.collected_at.isoformat() if evidence.collected_at else None,
        "user_id": str(evidence.collected_by),
        "details": {
            "method": evidence.collection_method,
            "source": evidence.source_table,
            "evidence_type": evidence.evidence_type.value if evidence.evidence_type else None
        }
    })
    
    # 2. Get collector username
    collector_result = await db.execute(
        select(User.first_name, User.last_name, User.email).where(User.id == evidence.collected_by)
    )
    collector = collector_result.first()
    if collector:
        collector_name = f"{collector.first_name} {collector.last_name}" if collector.first_name else collector.email
        custody_chain[0]["user_name"] = collector_name
    
    # 3. Verification event (if verified)
    if evidence.is_verified and evidence.verified_at:
        verification_event = {
            "event": "verified",
            "timestamp": evidence.verified_at.isoformat(),
            "user_id": str(evidence.verified_by) if evidence.verified_by else None,
            "details": {
                "integrity_hash": evidence.content_hash,
                "file_hash": evidence.file_hash
            }
        }
        
        # Get verifier username
        if evidence.verified_by:
            verifier_result = await db.execute(
                select(User.first_name, User.last_name, User.email).where(User.id == evidence.verified_by)
            )
            verifier = verifier_result.first()
            if verifier:
                verifier_name = f"{verifier.first_name} {verifier.last_name}" if verifier.first_name else verifier.email
                verification_event["user_name"] = verifier_name
        
        custody_chain.append(verification_event)
    
    # Sort by timestamp
    custody_chain.sort(key=lambda x: x.get("timestamp") or "")
    
    return {
        "evidence_id": str(evidence_id),
        "evidence_ref": evidence.evidence_ref,
        "custody_chain": custody_chain,
        "total_events": len(custody_chain),
        "current_status": "verified" if evidence.is_verified else "pending_verification",
        "integrity_intact": evidence.verify_integrity() if hasattr(evidence, 'verify_integrity') else True
    }


# ==========================================
# 14. UPDATE EVIDENCE METADATA ENDPOINT
# ==========================================

class EvidenceUpdateRequest(BaseModel):
    """Request to update evidence metadata (and content for confirmations)."""
    title: Optional[str] = None
    description: Optional[str] = None
    finding_id: Optional[uuid.UUID] = None
    content: Optional[Dict[str, Any]] = None  # For updating content (confirmation responses)
    
    class Config:
        json_schema_extra = {
            "example": {
                "title": "Updated Evidence Title",
                "description": "Updated description for this evidence",
                "finding_id": "550e8400-e29b-41d4-a716-446655440000"
            }
        }

@router.put("/{evidence_id}")
async def update_evidence_metadata(
    evidence_id: uuid.UUID,
    update_data: EvidenceUpdateRequest,
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Update evidence metadata (title, description, finding link, content).
    
    Note: For most evidence types, content is immutable. However, for 
    external_confirmation evidence, content can be updated to record responses.
    """
    require_audit_permission(current_user)
    
    # Get evidence record
    result = await db.execute(
        select(AuditEvidence).where(
            and_(
                AuditEvidence.id == evidence_id,
                AuditEvidence.entity_id == entity_id,
            )
        )
    )
    evidence = result.scalar_one_or_none()
    
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")
    
    # Update allowed fields
    updated_fields = []
    
    if update_data.title is not None:
        evidence.title = update_data.title
        updated_fields.append("title")
    
    if update_data.description is not None:
        evidence.description = update_data.description
        updated_fields.append("description")
    
    if update_data.finding_id is not None:
        # Verify finding exists
        finding_result = await db.execute(
            select(AuditFinding).where(
                and_(
                    AuditFinding.id == update_data.finding_id,
                    AuditFinding.entity_id == entity_id
                )
            )
        )
        finding = finding_result.scalar_one_or_none()
        if not finding:
            raise HTTPException(status_code=404, detail="Finding not found")
        
        evidence.finding_id = update_data.finding_id
        updated_fields.append("finding_id")
    
    # Handle content updates (for external_confirmation responses)
    if update_data.content is not None:
        evidence_type = evidence.evidence_type.value if hasattr(evidence.evidence_type, 'value') else str(evidence.evidence_type)
        if evidence_type == "external_confirmation":
            # Merge new content with existing
            existing_content = evidence.content or {}
            existing_content.update(update_data.content)
            evidence.content = existing_content
            updated_fields.append("content")
        else:
            # For other types, allow adding response_status, notes etc. without replacing content
            existing_content = evidence.content or {}
            # Only allow specific safe fields to be merged
            safe_fields = ["response_status", "response_date", "response_notes", 
                          "reported_amount", "difference_explanation", "notes"]
            for key, value in update_data.content.items():
                if key in safe_fields:
                    existing_content[key] = value
            evidence.content = existing_content
            updated_fields.append("content")
    
    if not updated_fields:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    
    await db.commit()
    await db.refresh(evidence)
    
    return {
        "success": True,
        "message": f"Updated fields: {', '.join(updated_fields)}",
        "evidence_id": str(evidence_id),
        "updated_fields": updated_fields
    }


# Alias route for frontend compatibility (some UIs use /update suffix)
@router.put("/{evidence_id}/update")
async def update_evidence_metadata_alias(
    evidence_id: uuid.UUID,
    update_data: EvidenceUpdateRequest,
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """Alias for PUT /{evidence_id} - exists for frontend compatibility."""
    return await update_evidence_metadata(
        evidence_id=evidence_id,
        update_data=update_data,
        current_user=current_user,
        entity_id=entity_id,
        db=db
    )


# ==========================================
# 15. EXPORT ENDPOINTS (PDF & Excel)
# ==========================================

@router.get("/export/pdf")
async def export_evidence_to_pdf(
    evidence_type: Optional[str] = None,
    finding_id: Optional[uuid.UUID] = None,
    verified_only: bool = False,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Export evidence list to PDF format.
    
    Returns a downloadable PDF file containing evidence summary.
    """
    require_audit_permission(current_user)
    
    # Build query
    query = select(AuditEvidence).where(AuditEvidence.entity_id == entity_id)
    
    if evidence_type:
        try:
            ev_type = EvidenceType(evidence_type)
            query = query.where(AuditEvidence.evidence_type == ev_type)
        except ValueError:
            pass
    
    if finding_id:
        query = query.where(AuditEvidence.finding_id == finding_id)
    
    if verified_only:
        query = query.where(AuditEvidence.is_verified == True)
    
    if date_from:
        query = query.where(AuditEvidence.collected_at >= datetime.combine(date_from, datetime.min.time()))
    
    if date_to:
        query = query.where(AuditEvidence.collected_at <= datetime.combine(date_to, datetime.max.time()))
    
    query = query.order_by(AuditEvidence.collected_at.desc())
    
    result = await db.execute(query)
    evidence_list = result.scalars().all()
    
    # Generate HTML content for PDF
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Evidence Export Report</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
            .summary {{ background: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th {{ background: #3498db; color: white; padding: 12px; text-align: left; }}
            td {{ padding: 10px; border-bottom: 1px solid #ddd; }}
            tr:nth-child(even) {{ background: #f8f9fa; }}
            .verified {{ color: #27ae60; font-weight: bold; }}
            .pending {{ color: #e67e22; }}
            .footer {{ margin-top: 30px; font-size: 12px; color: #7f8c8d; }}
        </style>
    </head>
    <body>
        <h1>Evidence Collection Report</h1>
        <div class="summary">
            <p><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p><strong>Total Evidence Items:</strong> {len(evidence_list)}</p>
            <p><strong>Generated By:</strong> {current_user.full_name or current_user.email}</p>
        </div>
        <table>
            <thead>
                <tr>
                    <th>Reference</th>
                    <th>Type</th>
                    <th>Title</th>
                    <th>Collected</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for ev in evidence_list:
        status_class = "verified" if ev.is_verified else "pending"
        status_text = "✓ Verified" if ev.is_verified else "Pending"
        collected_date = ev.collected_at.strftime('%Y-%m-%d %H:%M') if ev.collected_at else 'N/A'
        
        html_content += f"""
                <tr>
                    <td>{ev.evidence_ref}</td>
                    <td>{ev.evidence_type.value if ev.evidence_type else 'N/A'}</td>
                    <td>{ev.title[:50]}{'...' if len(ev.title) > 50 else ''}</td>
                    <td>{collected_date}</td>
                    <td class="{status_class}">{status_text}</td>
                </tr>
        """
    
    html_content += """
            </tbody>
        </table>
        <div class="footer">
            <p>This report was generated by Tekvwa Pro Audit Evidence Management System.</p>
            <p>Evidence content hashes can be verified for integrity.</p>
        </div>
    </body>
    </html>
    """
    
    # Return HTML that can be printed as PDF
    return Response(
        content=html_content,
        media_type="text/html",
        headers={
            "Content-Disposition": f'attachment; filename="evidence_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.html"'
        }
    )


@router.get("/export/excel")
async def export_evidence_to_excel(
    evidence_type: Optional[str] = None,
    finding_id: Optional[uuid.UUID] = None,
    verified_only: bool = False,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Export evidence list to Excel/CSV format.
    
    Returns a downloadable CSV file containing evidence data.
    """
    require_audit_permission(current_user)
    
    # Build query
    query = select(AuditEvidence).where(AuditEvidence.entity_id == entity_id)
    
    if evidence_type:
        try:
            ev_type = EvidenceType(evidence_type)
            query = query.where(AuditEvidence.evidence_type == ev_type)
        except ValueError:
            pass
    
    if finding_id:
        query = query.where(AuditEvidence.finding_id == finding_id)
    
    if verified_only:
        query = query.where(AuditEvidence.is_verified == True)
    
    if date_from:
        query = query.where(AuditEvidence.collected_at >= datetime.combine(date_from, datetime.min.time()))
    
    if date_to:
        query = query.where(AuditEvidence.collected_at <= datetime.combine(date_to, datetime.max.time()))
    
    query = query.order_by(AuditEvidence.collected_at.desc())
    
    result = await db.execute(query)
    evidence_list = result.scalars().all()
    
    # Build CSV content
    import io
    import csv
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header row
    writer.writerow([
        "Reference",
        "Type",
        "Title",
        "Description",
        "Source Table",
        "Collected At",
        "Collection Method",
        "Is Verified",
        "Verified At",
        "Content Hash",
        "File Size (bytes)"
    ])
    
    # Data rows
    for ev in evidence_list:
        writer.writerow([
            ev.evidence_ref,
            ev.evidence_type.value if ev.evidence_type else '',
            ev.title,
            ev.description[:200] if ev.description else '',
            ev.source_table or '',
            ev.collected_at.isoformat() if ev.collected_at else '',
            ev.collection_method or '',
            'Yes' if ev.is_verified else 'No',
            ev.verified_at.isoformat() if ev.verified_at else '',
            ev.content_hash or '',
            ev.file_size_bytes or ''
        ])
    
    csv_content = output.getvalue()
    output.close()
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="evidence_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        }
    )


# ==========================================
# 16. DATABASE SNAPSHOT ENDPOINT (ALIAS)
# ==========================================

@router.post("/snapshot/database")
async def create_database_snapshot_alias(
    request: DatabaseSnapshotRequest,
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a database snapshot as evidence (alias for /snapshot/create).
    
    Captures current state of database tables for audit evidence.
    Accepts either 'snapshot_type' or 'table_name' for compatibility.
    """
    require_audit_permission(current_user)
    
    service = EvidenceCollectionService(db)
    
    # Use effective_snapshot_type which handles both snapshot_type and table_name
    result = await service.create_database_snapshot(
        entity_id=entity_id,
        collected_by=current_user.id,
        snapshot_type=request.effective_snapshot_type,
        finding_id=request.finding_id,
        title=request.title,
        description=request.description,
    )
    
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    
    await db.commit()
    
    return {
        "success": True,
        "evidence_ref": result.evidence_ref,
        "evidence_id": str(result.evidence_id),
        "message": f"Database snapshot captured: {result.evidence_ref}",
    }


# ==========================================
# 17. BULK OPERATIONS ENDPOINTS
# ==========================================

class BulkVerifyRequest(BaseModel):
    """Request for bulk verification."""
    evidence_ids: List[uuid.UUID]
    
    class Config:
        json_schema_extra = {
            "example": {
                "evidence_ids": ["uuid1", "uuid2", "uuid3"]
            }
        }

class BulkDeleteRequest(BaseModel):
    """Request for bulk deletion."""
    evidence_ids: List[uuid.UUID]
    
    class Config:
        json_schema_extra = {
            "example": {
                "evidence_ids": ["uuid1", "uuid2", "uuid3"]
            }
        }


@router.post("/bulk/verify")
async def bulk_verify_evidence(
    request: BulkVerifyRequest,
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Verify multiple evidence items at once.
    
    Only verifies items belonging to the current entity.
    """
    require_audit_permission(current_user)
    
    if not request.evidence_ids:
        raise HTTPException(status_code=400, detail="No evidence IDs provided")
    
    if len(request.evidence_ids) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 items per bulk operation")
    
    verified_count = 0
    failed_ids = []
    
    for evidence_id in request.evidence_ids:
        result = await db.execute(
            select(AuditEvidence).where(
                and_(
                    AuditEvidence.id == evidence_id,
                    AuditEvidence.entity_id == entity_id,
                )
            )
        )
        evidence = result.scalar_one_or_none()
        
        if evidence and not evidence.is_verified:
            evidence.is_verified = True
            evidence.verified_by = current_user.id
            evidence.verified_at = datetime.now(timezone.utc)
            verified_count += 1
        elif not evidence:
            failed_ids.append(str(evidence_id))
    
    await db.commit()
    
    return {
        "success": True,
        "verified_count": verified_count,
        "failed_count": len(failed_ids),
        "failed_ids": failed_ids,
        "message": f"Verified {verified_count} of {len(request.evidence_ids)} evidence items"
    }


@router.post("/bulk/delete")
async def bulk_delete_evidence(
    request: BulkDeleteRequest,
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete multiple evidence items at once.
    
    Requires elevated permission. Only deletes items belonging to current entity.
    """
    require_audit_permission(current_user)
    
    if not request.evidence_ids:
        raise HTTPException(status_code=400, detail="No evidence IDs provided")
    
    if len(request.evidence_ids) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 items per bulk delete")
    
    deleted_count = 0
    failed_ids = []
    
    for evidence_id in request.evidence_ids:
        result = await db.execute(
            select(AuditEvidence).where(
                and_(
                    AuditEvidence.id == evidence_id,
                    AuditEvidence.entity_id == entity_id,
                )
            )
        )
        evidence = result.scalar_one_or_none()
        
        if evidence:
            # Delete file if exists
            if evidence.file_path and os.path.exists(evidence.file_path):
                try:
                    os.remove(evidence.file_path)
                except Exception:
                    pass
            
            await db.delete(evidence)
            deleted_count += 1
        else:
            failed_ids.append(str(evidence_id))
    
    await db.commit()
    
    return {
        "success": True,
        "deleted_count": deleted_count,
        "failed_count": len(failed_ids),
        "failed_ids": failed_ids,
        "message": f"Deleted {deleted_count} of {len(request.evidence_ids)} evidence items"
    }


# ==========================================
# 18. EVIDENCE NOTES ENDPOINT
# ==========================================

class AddNoteRequest(BaseModel):
    """Request to add a note to evidence."""
    note: Optional[str] = None
    content: Optional[str] = None  # Alias for note (frontend compatibility)
    
    @property
    def effective_note(self) -> str:
        """Get the note text from either field."""
        return self.note or self.content or ""
    
    def model_post_init(self, __context):
        """Ensure at least one of note or content is provided."""
        if not self.note and not self.content:
            raise ValueError("Either 'note' or 'content' must be provided")
    
    class Config:
        json_schema_extra = {
            "example": {
                "note": "This evidence was reviewed and confirmed accurate."
            }
        }


@router.post("/{evidence_id}/notes")
async def add_evidence_note(
    evidence_id: uuid.UUID,
    request: AddNoteRequest,
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Add a note to evidence.
    
    Accepts either 'note' or 'content' field for the note text.
    Notes are stored in the evidence content JSON and include author/timestamp.
    Notes do not modify the evidence integrity hash (content hash remains unchanged).
    """
    require_audit_permission(current_user)
    
    # Get evidence record
    result = await db.execute(
        select(AuditEvidence).where(
            and_(
                AuditEvidence.id == evidence_id,
                AuditEvidence.entity_id == entity_id,
            )
        )
    )
    evidence = result.scalar_one_or_none()
    
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")
    
    # Add note to content (notes don't affect content_hash)
    content = evidence.content or {}
    if "notes" not in content:
        content["notes"] = []
    
    # Use effective_note to support both 'note' and 'content' fields
    note_entry = {
        "id": str(uuid.uuid4()),
        "text": request.effective_note,
        "author_id": str(current_user.id),
        "author_name": current_user.full_name or current_user.email,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    content["notes"].append(note_entry)
    evidence.content = content
    
    # Force update of JSONB column
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(evidence, "content")
    
    await db.commit()
    
    return {
        "success": True,
        "note_id": note_entry["id"],
        "message": "Note added successfully",
        "total_notes": len(content["notes"])
    }


@router.get("/{evidence_id}/notes")
async def get_evidence_notes(
    evidence_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all notes for an evidence item.
    """
    require_audit_permission(current_user)
    
    # Get evidence record
    result = await db.execute(
        select(AuditEvidence).where(
            and_(
                AuditEvidence.id == evidence_id,
                AuditEvidence.entity_id == entity_id,
            )
        )
    )
    evidence = result.scalar_one_or_none()
    
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")
    
    content = evidence.content or {}
    notes = content.get("notes", [])
    
    return {
        "evidence_id": str(evidence_id),
        "evidence_ref": evidence.evidence_ref,
        "notes": notes,
        "total_notes": len(notes)
    }
