"""
Tekvwa Pro Audit - Receipts Router

API endpoints for receipt upload, OCR processing, and document management.
"""

from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from io import BytesIO

from app.database import get_async_session
from app.dependencies import get_current_active_user, record_usage_event
from app.models.user import User
from app.models.audit_consolidated import AuditAction
from app.models.sku import UsageMetricType
from app.services.entity_service import EntityService
from app.services.ocr_service import OCRService, ExtractedReceiptData
from app.services.file_storage_service import FileStorageService, FileCategory
from app.services.audit_service import AuditService
from app.schemas.auth import MessageResponse


router = APIRouter()


# ===========================================
# SCHEMAS
# ===========================================

class ReceiptUploadResponse(BaseModel):
    """Response after receipt upload."""
    file_id: str
    url: str
    filename: str
    content_type: str
    size: int
    extracted_data: Optional[dict] = None


class ExtractedDataResponse(BaseModel):
    """Extracted receipt data response."""
    vendor_name: Optional[str]
    vendor_address: Optional[str]
    vendor_tin: Optional[str]
    receipt_number: Optional[str]
    transaction_date: Optional[str]
    subtotal: Optional[float]
    vat_amount: Optional[float]
    total_amount: Optional[float]
    currency: str
    payment_method: Optional[str]
    line_items: Optional[List[dict]]
    confidence_score: float
    provider: str


class FileInfoResponse(BaseModel):
    """File information response."""
    file_id: str
    url: str
    filename: Optional[str]
    content_type: Optional[str]
    size: int
    created_at: Optional[str]
    category: Optional[str]


class CreateTransactionFromReceiptRequest(BaseModel):
    """Request to create transaction from receipt data."""
    file_id: str
    vendor_id: Optional[UUID] = None
    category_id: Optional[UUID] = None
    description: Optional[str] = None
    amount: float = Field(..., gt=0)
    vat_amount: Optional[float] = Field(0, ge=0)
    transaction_date: date
    notes: Optional[str] = None


# ===========================================
# HELPER FUNCTIONS
# ===========================================

async def verify_entity_access(
    entity_id: UUID,
    user: User,
    db: AsyncSession,
) -> None:
    """Verify user has access to the entity."""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity_by_id(entity_id, user)
    
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business entity not found",
        )
    
    has_access = any(
        access.entity_id == entity_id 
        for access in user.entity_access
    )
    
    if not has_access and entity.organization_id != user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this business entity",
        )


# ===========================================
# RECEIPT UPLOAD ENDPOINTS
# ===========================================

@router.post(
    "/{entity_id}/receipts/upload",
    response_model=ReceiptUploadResponse,
    summary="Upload receipt with OCR",
)
async def upload_receipt(
    entity_id: UUID,
    file: UploadFile = File(...),
    process_ocr: bool = Query(True, description="Process with OCR"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Upload a receipt image for OCR processing.
    
    Supported formats: JPEG, PNG, PDF
    
    Returns the uploaded file info and extracted data (if OCR enabled).
    """
    await verify_entity_access(entity_id, current_user, db)
    
    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "image/jpg", "application/pdf"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Allowed: {allowed_types}",
        )
    
    # Read file content
    file_content = await file.read()
    
    # Check file size (max 10MB)
    max_size = 10 * 1024 * 1024
    if len(file_content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large. Maximum size is 10MB",
        )
    
    # Upload file to storage
    storage_service = FileStorageService()
    upload_result = await storage_service.upload_file(
        entity_id=entity_id,
        file_content=file_content,
        filename=file.filename or "receipt",
        content_type=file.content_type,
        category=FileCategory.RECEIPT,
        metadata={
            "uploaded_by": str(current_user.id),
            "original_filename": file.filename,
        },
    )
    
    # Process OCR if enabled
    extracted_data = None
    if process_ocr:
        ocr_service = OCRService()
        receipt_data = await ocr_service.process_receipt(
            file_content=file_content,
            filename=file.filename or "receipt",
            content_type=file.content_type,
        )
        extracted_data = receipt_data.to_dict()
    
    # Audit log for receipt upload
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="receipt",
        entity_id=upload_result["file_id"],
        action=AuditAction.CREATE,
        user_id=current_user.id,
        new_values={
            "filename": upload_result["filename"],
            "content_type": upload_result["content_type"],
            "size": upload_result["size"],
            "ocr_processed": process_ocr,
        },
    )
    
    # Record OCR usage metering if OCR was processed
    if process_ocr and current_user.organization_id:
        await record_usage_event(
            db=db,
            organization_id=current_user.organization_id,
            metric_type=UsageMetricType.OCR_PAGES,
            entity_id=entity_id,
            user_id=current_user.id,
            resource_type="receipt_ocr",
            resource_id=upload_result["file_id"],
        )
    
    return ReceiptUploadResponse(
        file_id=upload_result["file_id"],
        url=upload_result["url"],
        filename=upload_result["filename"],
        content_type=upload_result["content_type"],
        size=upload_result["size"],
        extracted_data=extracted_data,
    )


@router.post(
    "/{entity_id}/receipts/{file_id}/reprocess",
    response_model=ExtractedDataResponse,
    summary="Reprocess receipt OCR",
)
async def reprocess_receipt_ocr(
    entity_id: UUID,
    file_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Reprocess an existing receipt with OCR.
    
    Useful if initial processing failed or to get updated extraction.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    storage_service = FileStorageService()
    
    try:
        file_content, content_type = await storage_service.download_file(file_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt file not found",
        )
    
    ocr_service = OCRService()
    receipt_data = await ocr_service.process_receipt(
        file_content=file_content,
        filename=file_id,
        content_type=content_type,
    )
    
    return ExtractedDataResponse(
        vendor_name=receipt_data.vendor_name,
        vendor_address=receipt_data.vendor_address,
        vendor_tin=receipt_data.vendor_tin,
        receipt_number=receipt_data.receipt_number,
        transaction_date=receipt_data.transaction_date.isoformat() if receipt_data.transaction_date else None,
        subtotal=receipt_data.subtotal,
        vat_amount=receipt_data.vat_amount,
        total_amount=receipt_data.total_amount,
        currency=receipt_data.currency,
        payment_method=receipt_data.payment_method,
        line_items=[
            {
                "description": item.description,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "amount": item.amount,
            }
            for item in (receipt_data.line_items or [])
        ],
        confidence_score=receipt_data.confidence_score,
        provider=receipt_data.provider,
    )


@router.post(
    "/{entity_id}/receipts/{file_id}/create-transaction",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Create transaction from receipt",
)
async def create_transaction_from_receipt(
    entity_id: UUID,
    file_id: str,
    request: CreateTransactionFromReceiptRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Create a transaction from receipt data.
    
    The receipt file will be attached to the transaction.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    from app.services.transaction_service import TransactionService
    from app.models.transaction import TransactionType
    
    transaction_service = TransactionService(db)
    
    transaction = await transaction_service.create_transaction(
        entity_id=entity_id,
        transaction_type=TransactionType.EXPENSE,
        amount=request.amount,
        vat_amount=request.vat_amount,
        description=request.description or "Receipt expense",
        transaction_date=request.transaction_date,
        vendor_id=request.vendor_id,
        category_id=request.category_id,
        notes=request.notes,
        receipt_url=file_id,
        created_by=current_user.id,
    )
    
    return {
        "message": "Transaction created successfully",
        "transaction_id": str(transaction.id),
        "receipt_file_id": file_id,
    }


# ===========================================
# FILE MANAGEMENT ENDPOINTS
# ===========================================

@router.get(
    "/{entity_id}/files",
    response_model=List[FileInfoResponse],
    summary="List files",
)
async def list_files(
    entity_id: UUID,
    category: Optional[str] = Query(None, description="File category filter"),
    limit: Optional[int] = Query(None, ge=1, le=500, description="Maximum number of files to return"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """List all files for a business entity."""
    await verify_entity_access(entity_id, current_user, db)
    
    storage_service = FileStorageService()
    
    file_category = None
    if category:
        try:
            file_category = FileCategory(category)
        except ValueError:
            pass
    
    files = await storage_service.list_files(
        entity_id=entity_id,
        category=file_category,
    )
    
    # Apply limit if specified
    if limit is not None:
        files = files[:limit]
    
    return [FileInfoResponse(**f) for f in files]


@router.get(
    "/{entity_id}/files/{file_id:path}",
    summary="Download file",
)
async def download_file(
    entity_id: UUID,
    file_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Download a file."""
    await verify_entity_access(entity_id, current_user, db)
    
    # Verify file belongs to entity
    if not file_id.startswith(str(entity_id)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this file",
        )
    
    storage_service = FileStorageService()
    
    try:
        file_content, content_type = await storage_service.download_file(file_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )
    
    return StreamingResponse(
        BytesIO(file_content),
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{file_id.split("/")[-1]}"',
        },
    )


@router.delete(
    "/{entity_id}/files/{file_id:path}",
    response_model=MessageResponse,
    summary="Delete file",
)
async def delete_file(
    entity_id: UUID,
    file_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Delete a file."""
    await verify_entity_access(entity_id, current_user, db)
    
    # Verify file belongs to entity
    if not file_id.startswith(str(entity_id)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this file",
        )
    
    storage_service = FileStorageService()
    deleted = await storage_service.delete_file(file_id)
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )
    
    # Audit log for file deletion
    audit_service = AuditService(db)
    await audit_service.log_action(
        business_entity_id=entity_id,
        entity_type="receipt",
        entity_id=file_id,
        action=AuditAction.DELETE,
        user_id=current_user.id,
        old_values={"file_id": file_id},
    )
    
    return MessageResponse(message="File deleted successfully")


@router.post(
    "/{entity_id}/documents/upload",
    response_model=ReceiptUploadResponse,
    summary="Upload document",
)
async def upload_document(
    entity_id: UUID,
    file: UploadFile = File(...),
    category: str = Query("other", description="Document category"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Upload a general document (invoice, certificate, report, etc.).
    
    No OCR processing - for storing reference documents.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    # Read file content
    file_content = await file.read()
    
    # Check file size (max 25MB for documents)
    max_size = 25 * 1024 * 1024
    if len(file_content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large. Maximum size is 25MB",
        )
    
    # Determine category
    try:
        file_category = FileCategory(category)
    except ValueError:
        file_category = FileCategory.OTHER
    
    storage_service = FileStorageService()
    upload_result = await storage_service.upload_file(
        entity_id=entity_id,
        file_content=file_content,
        filename=file.filename or "document",
        content_type=file.content_type,
        category=file_category,
        metadata={
            "uploaded_by": str(current_user.id),
            "original_filename": file.filename,
        },
    )
    
    return ReceiptUploadResponse(
        file_id=upload_result["file_id"],
        url=upload_result["url"],
        filename=upload_result["filename"],
        content_type=upload_result["content_type"],
        size=upload_result["size"],
        extracted_data=None,
    )


# ===========================================
# RECEIPT LIST & SEARCH
# ===========================================

class ReceiptItemResponse(BaseModel):
    """Receipt item in list response."""
    id: str
    file_id: str
    url: str
    filename: str
    content_type: str
    size: int
    uploaded_at: str
    uploaded_by: Optional[str]
    linked_transaction_id: Optional[str]
    ocr_processed: bool
    vendor_name: Optional[str]
    total_amount: Optional[float]
    transaction_date: Optional[str]


class ReceiptListResponse(BaseModel):
    """Response for receipt list."""
    receipts: List[ReceiptItemResponse]
    total: int
    page: int
    per_page: int
    has_unlinked: int


@router.get(
    "/{entity_id}/receipts",
    response_model=ReceiptListResponse,
    summary="List all receipts",
)
async def list_receipts(
    entity_id: UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    linked: Optional[bool] = Query(None, description="Filter by linked status"),
    start_date: Optional[date] = Query(None, description="Filter by upload date from"),
    end_date: Optional[date] = Query(None, description="Filter by upload date to"),
    search: Optional[str] = Query(None, description="Search by vendor name or filename"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    List all receipts for the entity.
    
    Supports filtering by:
    - Linked status (receipts attached to transactions)
    - Date range
    - Vendor name or filename search
    
    Use unlinked filter to find receipts that need to be matched to transactions.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    storage_service = FileStorageService()
    
    # Get all receipt files
    files = await storage_service.list_files(
        entity_id=entity_id,
        category=FileCategory.RECEIPT,
    )
    
    # Filter and transform
    receipts = []
    unlinked_count = 0
    
    for f in files:
        # Check link status
        is_linked = f.get("linked_transaction_id") is not None
        if not is_linked:
            unlinked_count += 1
        
        if linked is not None and is_linked != linked:
            continue
        
        # Search filter
        if search:
            vendor_match = search.lower() in (f.get("vendor_name") or "").lower()
            filename_match = search.lower() in (f.get("filename") or "").lower()
            if not (vendor_match or filename_match):
                continue
        
        receipts.append(ReceiptItemResponse(
            id=f.get("file_id", ""),
            file_id=f.get("file_id", ""),
            url=f.get("url", ""),
            filename=f.get("filename", ""),
            content_type=f.get("content_type", ""),
            size=f.get("size", 0),
            uploaded_at=f.get("created_at", ""),
            uploaded_by=f.get("metadata", {}).get("uploaded_by"),
            linked_transaction_id=f.get("linked_transaction_id"),
            ocr_processed=f.get("ocr_processed", False),
            vendor_name=f.get("vendor_name"),
            total_amount=f.get("total_amount"),
            transaction_date=f.get("transaction_date"),
        ))
    
    # Paginate
    start = (page - 1) * per_page
    end = start + per_page
    paginated = receipts[start:end]
    
    return ReceiptListResponse(
        receipts=paginated,
        total=len(receipts),
        page=page,
        per_page=per_page,
        has_unlinked=unlinked_count,
    )


# ===========================================
# BATCH UPLOAD
# ===========================================

class BatchUploadItemResult(BaseModel):
    """Result for a single item in batch upload."""
    filename: str
    success: bool
    file_id: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None
    extracted_data: Optional[dict] = None


class BatchUploadResponse(BaseModel):
    """Response for batch receipt upload."""
    total_uploaded: int
    successful: int
    failed: int
    results: List[BatchUploadItemResult]


@router.post(
    "/{entity_id}/receipts/batch-upload",
    response_model=BatchUploadResponse,
    summary="Batch upload receipts",
)
async def batch_upload_receipts(
    entity_id: UUID,
    files: List[UploadFile] = File(..., description="Multiple receipt files"),
    process_ocr: bool = Query(True, description="Process all with OCR"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Upload multiple receipts in a single request.
    
    Supports up to 20 files per batch.
    Each file is processed independently - failures don't affect others.
    
    Returns detailed results for each file including any OCR extracted data.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    max_files = 20
    if len(files) > max_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many files. Maximum {max_files} files per batch.",
        )
    
    allowed_types = ["image/jpeg", "image/png", "image/jpg", "application/pdf"]
    max_size = 10 * 1024 * 1024
    
    storage_service = FileStorageService()
    ocr_service = OCRService()
    
    results = []
    successful = 0
    failed = 0
    
    for file in files:
        try:
            # Validate file type
            if file.content_type not in allowed_types:
                results.append(BatchUploadItemResult(
                    filename=file.filename or "unknown",
                    success=False,
                    error=f"Unsupported file type: {file.content_type}",
                ))
                failed += 1
                continue
            
            # Read content
            file_content = await file.read()
            
            # Validate size
            if len(file_content) > max_size:
                results.append(BatchUploadItemResult(
                    filename=file.filename or "unknown",
                    success=False,
                    error="File too large (max 10MB)",
                ))
                failed += 1
                continue
            
            # Upload file
            upload_result = await storage_service.upload_file(
                entity_id=entity_id,
                file_content=file_content,
                filename=file.filename or "receipt",
                content_type=file.content_type,
                category=FileCategory.RECEIPT,
                metadata={
                    "uploaded_by": str(current_user.id),
                    "original_filename": file.filename,
                    "batch_upload": True,
                },
            )
            
            # Process OCR if enabled
            extracted_data = None
            if process_ocr:
                try:
                    receipt_data = await ocr_service.process_receipt(
                        file_content=file_content,
                        filename=file.filename or "receipt",
                        content_type=file.content_type,
                    )
                    extracted_data = receipt_data.to_dict()
                except Exception:
                    pass  # OCR failure shouldn't fail upload
            
            results.append(BatchUploadItemResult(
                filename=file.filename or "unknown",
                success=True,
                file_id=upload_result["file_id"],
                url=upload_result["url"],
                extracted_data=extracted_data,
            ))
            successful += 1
            
        except Exception as e:
            results.append(BatchUploadItemResult(
                filename=file.filename or "unknown",
                success=False,
                error=str(e),
            ))
            failed += 1
    
    return BatchUploadResponse(
        total_uploaded=len(files),
        successful=successful,
        failed=failed,
        results=results,
    )


# ===========================================
# LINK RECEIPTS TO TRANSACTIONS
# ===========================================

class LinkReceiptRequest(BaseModel):
    """Request to link receipt to transaction."""
    transaction_id: UUID


class LinkReceiptResponse(BaseModel):
    """Response for linking receipt."""
    receipt_id: str
    transaction_id: str
    message: str


@router.post(
    "/{entity_id}/receipts/{receipt_id}/link",
    response_model=LinkReceiptResponse,
    summary="Link receipt to transaction",
)
async def link_receipt_to_transaction(
    entity_id: UUID,
    receipt_id: str,
    request: LinkReceiptRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Link a receipt to an existing transaction.
    
    This attaches the receipt file to the transaction for record-keeping
    and WREN compliance verification.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    from app.services.transaction_service import TransactionService
    
    transaction_service = TransactionService(db)
    
    # Get the transaction
    transaction = await transaction_service.get_transaction_by_id(request.transaction_id)
    
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )
    
    if transaction.entity_id != entity_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Transaction does not belong to this entity",
        )
    
    # Verify receipt exists
    storage_service = FileStorageService()
    
    try:
        file_info = await storage_service.get_file_info(receipt_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt file not found",
        )
    
    # Link the receipt to the transaction
    await transaction_service.attach_receipt(
        transaction_id=request.transaction_id,
        receipt_url=receipt_id,
    )
    
    await db.commit()
    
    return LinkReceiptResponse(
        receipt_id=receipt_id,
        transaction_id=str(request.transaction_id),
        message="Receipt linked to transaction successfully",
    )


@router.post(
    "/{entity_id}/receipts/{receipt_id}/unlink",
    response_model=MessageResponse,
    summary="Unlink receipt from transaction",
)
async def unlink_receipt_from_transaction(
    entity_id: UUID,
    receipt_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Unlink a receipt from its associated transaction.
    
    The receipt file remains but is no longer attached to the transaction.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    from app.services.transaction_service import TransactionService
    
    transaction_service = TransactionService(db)
    
    # Find transaction with this receipt
    transaction = await transaction_service.find_by_receipt_url(receipt_id)
    
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No transaction linked to this receipt",
        )
    
    if transaction.entity_id != entity_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Transaction does not belong to this entity",
        )
    
    # Remove the receipt link
    await transaction_service.detach_receipt(transaction.id)
    
    await db.commit()
    
    return MessageResponse(
        message="Receipt unlinked from transaction successfully",
        success=True,
    )


class BulkLinkRequest(BaseModel):
    """Request for bulk linking receipts."""
    links: List[dict] = Field(..., description="List of {receipt_id, transaction_id} pairs")


class BulkLinkResponse(BaseModel):
    """Response for bulk linking."""
    total: int
    successful: int
    failed: int
    errors: List[dict]


@router.post(
    "/{entity_id}/receipts/bulk-link",
    response_model=BulkLinkResponse,
    summary="Bulk link receipts to transactions",
)
async def bulk_link_receipts(
    entity_id: UUID,
    request: BulkLinkRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Link multiple receipts to transactions in a single request.
    
    Useful for matching imported receipts to existing transactions.
    """
    await verify_entity_access(entity_id, current_user, db)
    
    from app.services.transaction_service import TransactionService
    
    transaction_service = TransactionService(db)
    
    successful = 0
    failed = 0
    errors = []
    
    for link in request.links:
        receipt_id = link.get("receipt_id")
        transaction_id = link.get("transaction_id")
        
        if not receipt_id or not transaction_id:
            errors.append({
                "receipt_id": receipt_id,
                "error": "Missing receipt_id or transaction_id",
            })
            failed += 1
            continue
        
        try:
            import uuid
            tid = uuid.UUID(transaction_id)
            
            await transaction_service.attach_receipt(
                transaction_id=tid,
                receipt_url=receipt_id,
            )
            successful += 1
            
        except Exception as e:
            errors.append({
                "receipt_id": receipt_id,
                "transaction_id": transaction_id,
                "error": str(e),
            })
            failed += 1
    
    await db.commit()
    
    return BulkLinkResponse(
        total=len(request.links),
        successful=successful,
        failed=failed,
        errors=errors,
    )
