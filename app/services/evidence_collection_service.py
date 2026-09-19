"""
Tekvwa Pro Audit - Evidence Collection Service

Comprehensive evidence collection service providing:
1. Document Upload & Storage
2. Screenshot Capture
3. Transaction Record Collection
4. Computed Values with Audit Trail
5. System Log Extraction
6. Point-in-Time Database Snapshots
7. Third-Party Confirmation Management
8. Auto-Collection During Audit Runs

All evidence is immutable and hash-verified.
"""

import uuid
import hashlib
import json
import os
import aiofiles
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple, BinaryIO
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select, func, and_, or_, text, cast, String as SqlString
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_consolidated import (
    AuditEvidence, EvidenceType,
    AuditRun, AuditFinding, FindingCategory,
    AuditLog, AuditAction,
)
from app.models.transaction import Transaction, TransactionType
from app.models.accounting import JournalEntry, JournalEntryLine, ChartOfAccounts


# Configuration
EVIDENCE_UPLOAD_DIR = Path("./uploads/evidence")
ALLOWED_MIME_TYPES = {
    # Documents
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "text/csv": ".csv",
    "text/plain": ".txt",
    # Images
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/tiff": ".tiff",
}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


@dataclass
class EvidenceCollectionResult:
    """Result of evidence collection operation."""
    success: bool
    evidence_id: Optional[uuid.UUID] = None
    evidence_ref: Optional[str] = None
    content_hash: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class EvidenceCollectionService:
    """
    Comprehensive service for collecting, storing, and managing audit evidence.
    
    Features:
    - File upload with hash verification
    - Automatic transaction snapshots
    - Calculation audit trails
    - Log extraction
    - Database point-in-time snapshots
    - Third-party confirmation tracking
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self._ensure_upload_directory()
    
    def _ensure_upload_directory(self):
        """Ensure the evidence upload directory exists."""
        EVIDENCE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    
    def _calculate_hash(self, data: bytes) -> str:
        """Calculate SHA-256 hash of binary data."""
        return hashlib.sha256(data).hexdigest()
    
    def _calculate_content_hash(self, content: Dict[str, Any]) -> str:
        """Calculate SHA-256 hash of JSON content."""
        data_str = json.dumps(content, sort_keys=True, default=str)
        return hashlib.sha256(data_str.encode()).hexdigest()
    
    async def _generate_evidence_ref(self, entity_id: uuid.UUID, prefix: str = "EVID") -> str:
        """Generate unique evidence reference."""
        # Count existing evidence for this entity
        stmt = select(func.count()).select_from(AuditEvidence).where(
            AuditEvidence.entity_id == entity_id
        )
        result = await self.db.execute(stmt)
        count = result.scalar() or 0
        
        year = datetime.now().year
        return f"{prefix}-{year}-{count + 1:05d}"
    
    # ==========================================
    # 1. DOCUMENT UPLOAD
    # ==========================================
    
    async def upload_document(
        self,
        entity_id: uuid.UUID,
        file_content: bytes,
        filename: str,
        mime_type: str,
        collected_by: uuid.UUID,
        title: Optional[str] = None,
        description: Optional[str] = None,
        finding_id: Optional[uuid.UUID] = None,
        audit_run_id: Optional[uuid.UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> EvidenceCollectionResult:
        """
        Upload a document as immutable evidence.
        
        Args:
            entity_id: Business entity ID
            file_content: Binary file content
            filename: Original filename
            mime_type: MIME type of the file
            collected_by: User ID who uploaded
            title: Evidence title (defaults to filename)
            description: Evidence description
            finding_id: Optional link to audit finding
            audit_run_id: Optional link to audit run
            metadata: Additional metadata
        
        Returns:
            EvidenceCollectionResult with evidence details
        """
        try:
            # Validate MIME type
            if mime_type not in ALLOWED_MIME_TYPES:
                return EvidenceCollectionResult(
                    success=False,
                    error=f"File type not allowed: {mime_type}. Allowed: {', '.join(ALLOWED_MIME_TYPES.keys())}"
                )
            
            # Validate file size
            if len(file_content) > MAX_FILE_SIZE:
                return EvidenceCollectionResult(
                    success=False,
                    error=f"File too large. Maximum size: {MAX_FILE_SIZE / 1024 / 1024} MB"
                )
            
            # Calculate file hash
            file_hash = self._calculate_hash(file_content)
            
            # Generate unique filename with hash prefix
            ext = ALLOWED_MIME_TYPES.get(mime_type, ".bin")
            safe_filename = f"{file_hash[:16]}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
            file_path = EVIDENCE_UPLOAD_DIR / str(entity_id) / safe_filename
            
            # Ensure entity subdirectory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write file
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(file_content)
            
            # Create evidence content
            content = {
                "original_filename": filename,
                "mime_type": mime_type,
                "file_size_bytes": len(file_content),
                "file_hash": file_hash,
                "upload_timestamp": datetime.now().isoformat(),
                "metadata": metadata or {},
            }
            
            # Generate reference
            evidence_ref = await self._generate_evidence_ref(entity_id, "DOC")
            
            # Create evidence record
            evidence = AuditEvidence(
                entity_id=entity_id,
                finding_id=finding_id,
                evidence_ref=evidence_ref,
                evidence_type=EvidenceType.DOCUMENT,
                title=title or filename,
                description=description or f"Document upload: {filename}",
                content=content,
                content_hash=self._calculate_content_hash(content),
                file_path=str(file_path),
                file_mime_type=mime_type,
                file_size_bytes=len(file_content),
                file_hash=file_hash,
                collected_by=collected_by,
                collection_method="manual_upload",
            )
            
            self.db.add(evidence)
            await self.db.flush()
            await self.db.refresh(evidence)
            
            return EvidenceCollectionResult(
                success=True,
                evidence_id=evidence.id,
                evidence_ref=evidence.evidence_ref,
                content_hash=evidence.content_hash,
                metadata={
                    "file_path": str(file_path),
                    "file_size": len(file_content),
                    "file_hash": file_hash,
                }
            )
            
        except Exception as e:
            return EvidenceCollectionResult(
                success=False,
                error=f"Upload failed: {str(e)}"
            )
    
    # ==========================================
    # 2. SCREENSHOT CAPTURE
    # ==========================================
    
    async def upload_screenshot(
        self,
        entity_id: uuid.UUID,
        image_content: bytes,
        collected_by: uuid.UUID,
        title: str,
        description: Optional[str] = None,
        finding_id: Optional[uuid.UUID] = None,
        source_url: Optional[str] = None,
        capture_timestamp: Optional[datetime] = None,
    ) -> EvidenceCollectionResult:
        """
        Upload a screenshot as evidence.
        
        Args:
            entity_id: Business entity ID
            image_content: Binary image content (PNG or JPEG)
            collected_by: User ID
            title: Screenshot title
            description: Description of what the screenshot shows
            finding_id: Optional link to finding
            source_url: URL where screenshot was captured (if applicable)
            capture_timestamp: When the screenshot was taken
        
        Returns:
            EvidenceCollectionResult
        """
        try:
            # Detect image type from magic bytes
            mime_type = "image/png"  # Default
            if image_content[:2] == b'\xff\xd8':
                mime_type = "image/jpeg"
            elif image_content[:8] == b'\x89PNG\r\n\x1a\n':
                mime_type = "image/png"
            elif image_content[:6] in (b'GIF87a', b'GIF89a'):
                mime_type = "image/gif"
            
            # Calculate hash
            file_hash = self._calculate_hash(image_content)
            
            # Generate filename
            ext = ALLOWED_MIME_TYPES.get(mime_type, ".png")
            safe_filename = f"screenshot_{file_hash[:16]}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
            file_path = EVIDENCE_UPLOAD_DIR / str(entity_id) / "screenshots" / safe_filename
            
            # Ensure directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write file
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(image_content)
            
            # Create content
            content = {
                "mime_type": mime_type,
                "file_size_bytes": len(image_content),
                "file_hash": file_hash,
                "source_url": source_url,
                "capture_timestamp": (capture_timestamp or datetime.now()).isoformat(),
            }
            
            evidence_ref = await self._generate_evidence_ref(entity_id, "SCRN")
            
            evidence = AuditEvidence(
                entity_id=entity_id,
                finding_id=finding_id,
                evidence_ref=evidence_ref,
                evidence_type=EvidenceType.SCREENSHOT,
                title=title,
                description=description or f"Screenshot: {title}",
                content=content,
                content_hash=self._calculate_content_hash(content),
                file_path=str(file_path),
                file_mime_type=mime_type,
                file_size_bytes=len(image_content),
                file_hash=file_hash,
                collected_by=collected_by,
                collection_method="screenshot_capture",
            )
            
            self.db.add(evidence)
            await self.db.flush()
            await self.db.refresh(evidence)
            
            return EvidenceCollectionResult(
                success=True,
                evidence_id=evidence.id,
                evidence_ref=evidence.evidence_ref,
                content_hash=evidence.content_hash,
                metadata={"file_path": str(file_path)}
            )
            
        except Exception as e:
            return EvidenceCollectionResult(
                success=False,
                error=f"Screenshot upload failed: {str(e)}"
            )
    
    # ==========================================
    # 3. TRANSACTION RECORD COLLECTION
    # ==========================================
    
    async def collect_transaction_records(
        self,
        entity_id: uuid.UUID,
        collected_by: uuid.UUID,
        transaction_ids: Optional[List[uuid.UUID]] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        finding_id: Optional[uuid.UUID] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        transaction_type: Optional[str] = None,
    ) -> EvidenceCollectionResult:
        """
        Collect transaction records as evidence.
        
        Can collect specific transactions by ID or all transactions in a date range.
        Creates an immutable snapshot of the transaction data.
        
        Args:
            entity_id: Business entity ID
            collected_by: User ID
            transaction_ids: Specific transaction IDs to collect
            date_from: Start date for range collection
            date_to: End date for range collection
            finding_id: Optional link to finding
            title: Evidence title
            description: Evidence description
            transaction_type: Filter by type ('all', 'journal_entries', 'income', 'expense', etc.)
        
        Returns:
            EvidenceCollectionResult
        """
        try:
            # Build query
            stmt = select(Transaction).where(Transaction.entity_id == entity_id)
            
            if transaction_ids:
                stmt = stmt.where(Transaction.id.in_(transaction_ids))
            elif date_from and date_to:
                stmt = stmt.where(
                    and_(
                        Transaction.transaction_date >= date_from,
                        Transaction.transaction_date <= date_to,
                    )
                )
            
            # Apply transaction_type filter
            if transaction_type and transaction_type != 'all':
                if transaction_type == 'journal_entries':
                    # Filter for journal entries (all income and expense transactions)
                    stmt = stmt.where(Transaction.transaction_type.in_([
                        TransactionType.INCOME,
                        TransactionType.EXPENSE
                    ]))
                elif transaction_type == 'income':
                    stmt = stmt.where(Transaction.transaction_type == TransactionType.INCOME)
                elif transaction_type == 'expense':
                    stmt = stmt.where(Transaction.transaction_type == TransactionType.EXPENSE)
                # If unknown type, don't filter (collect all)
            
            stmt = stmt.order_by(Transaction.transaction_date.desc())
            
            result = await self.db.execute(stmt)
            transactions = result.scalars().all()
            
            if not transactions:
                return EvidenceCollectionResult(
                    success=False,
                    error="No transactions found matching criteria"
                )
            
            # Serialize transactions
            transaction_data = []
            for txn in transactions:
                transaction_data.append({
                    "id": str(txn.id),
                    "transaction_date": txn.transaction_date.isoformat() if txn.transaction_date else None,
                    "transaction_type": txn.transaction_type.value if txn.transaction_type else None,
                    "amount": str(txn.amount) if txn.amount else "0",
                    "vat_amount": str(txn.vat_amount) if txn.vat_amount else "0",
                    "wht_amount": str(txn.wht_amount) if txn.wht_amount else "0",
                    "total_amount": str(txn.total_amount) if txn.total_amount else "0",
                    "description": txn.description,
                    "reference": txn.reference,
                    "wren_status": txn.wren_status.value if txn.wren_status else None,
                    "created_at": txn.created_at.isoformat() if txn.created_at else None,
                })
            
            content = {
                "collection_type": "transaction_records",
                "collection_timestamp": datetime.now().isoformat(),
                "date_range": {
                    "from": date_from.isoformat() if date_from else None,
                    "to": date_to.isoformat() if date_to else None,
                },
                "transaction_count": len(transaction_data),
                "total_amount": str(sum(Decimal(t["amount"]) for t in transaction_data)),
                "transactions": transaction_data,
            }
            
            evidence_ref = await self._generate_evidence_ref(entity_id, "TXN")
            
            evidence = AuditEvidence(
                entity_id=entity_id,
                finding_id=finding_id,
                evidence_ref=evidence_ref,
                evidence_type=EvidenceType.TRANSACTION,
                title=title or f"Transaction Records ({len(transaction_data)} records)",
                description=description or f"Snapshot of {len(transaction_data)} transactions",
                source_table="transactions",
                content=content,
                content_hash=self._calculate_content_hash(content),
                collected_by=collected_by,
                collection_method="automated_collection",
            )
            
            self.db.add(evidence)
            await self.db.flush()
            await self.db.refresh(evidence)
            
            return EvidenceCollectionResult(
                success=True,
                evidence_id=evidence.id,
                evidence_ref=evidence.evidence_ref,
                content_hash=evidence.content_hash,
                metadata={
                    "transaction_count": len(transaction_data),
                    "date_range": content["date_range"],
                }
            )
            
        except Exception as e:
            return EvidenceCollectionResult(
                success=False,
                error=f"Transaction collection failed: {str(e)}"
            )
    
    # ==========================================
    # 4. COMPUTED VALUES AUDIT TRAIL
    # ==========================================
    
    async def collect_calculation_evidence(
        self,
        entity_id: uuid.UUID,
        collected_by: uuid.UUID,
        calculation_type: str,
        inputs: Dict[str, Any],
        outputs: Dict[str, Any],
        formula_description: str,
        finding_id: Optional[uuid.UUID] = None,
        title: Optional[str] = None,
        regulatory_reference: Optional[str] = None,
    ) -> EvidenceCollectionResult:
        """
        Collect computed values as evidence with full audit trail.
        
        Captures the complete calculation process: inputs, formula, and outputs.
        
        Args:
            entity_id: Business entity ID
            collected_by: User ID
            calculation_type: Type of calculation (e.g., "paye_tax", "vat", "trial_balance")
            inputs: Input values used in calculation
            outputs: Output/result values
            formula_description: Human-readable description of the formula
            finding_id: Optional link to finding
            title: Evidence title
            regulatory_reference: Regulatory reference (e.g., "FIRS PAYE Guidelines 2024")
        
        Returns:
            EvidenceCollectionResult
        """
        try:
            content = {
                "calculation_type": calculation_type,
                "calculation_timestamp": datetime.now().isoformat(),
                "inputs": inputs,
                "outputs": outputs,
                "formula_description": formula_description,
                "regulatory_reference": regulatory_reference,
                "audit_trail": {
                    "calculated_by": str(collected_by),
                    "calculation_engine": "Tekvwa Pro Audit v1.0",
                    "precision": "2 decimal places",
                }
            }
            
            evidence_ref = await self._generate_evidence_ref(entity_id, "CALC")
            
            evidence = AuditEvidence(
                entity_id=entity_id,
                finding_id=finding_id,
                evidence_ref=evidence_ref,
                evidence_type=EvidenceType.CALCULATION,
                title=title or f"Calculation: {calculation_type}",
                description=f"Computed values for {calculation_type} with full audit trail. {formula_description}",
                content=content,
                content_hash=self._calculate_content_hash(content),
                collected_by=collected_by,
                collection_method="system_generated",
            )
            
            self.db.add(evidence)
            await self.db.flush()
            await self.db.refresh(evidence)
            
            return EvidenceCollectionResult(
                success=True,
                evidence_id=evidence.id,
                evidence_ref=evidence.evidence_ref,
                content_hash=evidence.content_hash,
                metadata={
                    "calculation_type": calculation_type,
                    "input_count": len(inputs),
                    "output_count": len(outputs),
                }
            )
            
        except Exception as e:
            return EvidenceCollectionResult(
                success=False,
                error=f"Calculation evidence collection failed: {str(e)}"
            )
    
    # ==========================================
    # 5. SYSTEM LOG EXTRACTION
    # ==========================================
    
    async def extract_system_logs(
        self,
        entity_id: uuid.UUID,
        collected_by: uuid.UUID,
        date_from: date,
        date_to: date,
        log_types: Optional[List[str]] = None,
        user_ids: Optional[List[uuid.UUID]] = None,
        finding_id: Optional[uuid.UUID] = None,
        title: Optional[str] = None,
    ) -> EvidenceCollectionResult:
        """
        Extract system audit logs as evidence.
        
        Captures audit trail from the system's audit log table.
        
        Args:
            entity_id: Business entity ID
            collected_by: User ID
            date_from: Start date for log extraction
            date_to: End date for log extraction
            log_types: Filter by specific action types
            user_ids: Filter by specific user IDs
            finding_id: Optional link to finding
            title: Evidence title
        
        Returns:
            EvidenceCollectionResult
        """
        try:
            # Query audit logs
            stmt = select(AuditLog).where(
                and_(
                    AuditLog.entity_id == entity_id,
                    AuditLog.created_at >= datetime.combine(date_from, datetime.min.time()),
                    AuditLog.created_at <= datetime.combine(date_to, datetime.max.time()),
                )
            )
            
            if log_types:
                # Convert log types to lowercase values that match database varchar values
                # Cast the column to avoid PostgreSQL enum type mismatch
                normalized_log_types = [lt.lower() for lt in log_types]
                stmt = stmt.where(cast(AuditLog.action, SqlString).in_(normalized_log_types))
            
            if user_ids:
                stmt = stmt.where(AuditLog.user_id.in_(user_ids))
            
            stmt = stmt.order_by(AuditLog.created_at.asc())
            
            result = await self.db.execute(stmt)
            logs = result.scalars().all()
            
            # Serialize logs
            log_data = []
            for log in logs:
                log_data.append({
                    "id": str(log.id),
                    "timestamp": log.created_at.isoformat() if log.created_at else None,
                    "user_id": str(log.user_id) if log.user_id else None,
                    "action": log.action.value if hasattr(log.action, 'value') else str(log.action),
                    "target_entity_type": log.target_entity_type,
                    "target_entity_id": str(log.target_entity_id) if log.target_entity_id else None,
                    "ip_address": log.ip_address if hasattr(log, 'ip_address') else None,
                    "description": log.description if hasattr(log, 'description') else None,
                })
            
            content = {
                "collection_type": "system_logs",
                "extraction_timestamp": datetime.now().isoformat(),
                "date_range": {
                    "from": date_from.isoformat(),
                    "to": date_to.isoformat(),
                },
                "filters": {
                    "log_types": log_types,
                    "user_ids": [str(uid) for uid in user_ids] if user_ids else None,
                },
                "log_count": len(log_data),
                "logs": log_data,
            }
            
            evidence_ref = await self._generate_evidence_ref(entity_id, "LOG")
            
            evidence = AuditEvidence(
                entity_id=entity_id,
                finding_id=finding_id,
                evidence_ref=evidence_ref,
                evidence_type=EvidenceType.LOG_EXTRACT,
                title=title or f"System Logs ({len(log_data)} entries)",
                description=f"Audit log extraction from {date_from} to {date_to}",
                source_table="audit_logs",
                content=content,
                content_hash=self._calculate_content_hash(content),
                collected_by=collected_by,
                collection_method="automated_extraction",
            )
            
            self.db.add(evidence)
            await self.db.flush()
            await self.db.refresh(evidence)
            
            return EvidenceCollectionResult(
                success=True,
                evidence_id=evidence.id,
                evidence_ref=evidence.evidence_ref,
                content_hash=evidence.content_hash,
                metadata={
                    "log_count": len(log_data),
                    "date_range": content["date_range"],
                }
            )
            
        except Exception as e:
            return EvidenceCollectionResult(
                success=False,
                error=f"Log extraction failed: {str(e)}"
            )
    
    # ==========================================
    # 6. POINT-IN-TIME DATABASE SNAPSHOT
    # ==========================================
    
    async def create_database_snapshot(
        self,
        entity_id: uuid.UUID,
        collected_by: uuid.UUID,
        snapshot_type: str,
        finding_id: Optional[uuid.UUID] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> EvidenceCollectionResult:
        """
        Create a point-in-time snapshot of key database tables.
        
        Captures current state of critical financial data.
        
        Args:
            entity_id: Business entity ID
            collected_by: User ID
            snapshot_type: Type of snapshot (e.g., "trial_balance", "gl_balances", "full")
            finding_id: Optional link to finding
            title: Evidence title
            description: Evidence description
        
        Returns:
            EvidenceCollectionResult
        """
        try:
            snapshot_data = {
                "snapshot_type": snapshot_type,
                "snapshot_timestamp": datetime.now().isoformat(),
                "entity_id": str(entity_id),
                "tables": {},
            }
            
            # Snapshot Chart of Accounts
            if snapshot_type in ["full", "chart_of_accounts", "trial_balance"]:
                coa_stmt = select(ChartOfAccounts).where(ChartOfAccounts.entity_id == entity_id)
                coa_result = await self.db.execute(coa_stmt)
                accounts = coa_result.scalars().all()
                
                snapshot_data["tables"]["chart_of_accounts"] = [
                    {
                        "id": str(acc.id),
                        "account_code": acc.account_code,
                        "account_name": acc.account_name,
                        "account_type": acc.account_type.value if hasattr(acc.account_type, 'value') else str(acc.account_type),
                        "balance": str(acc.current_balance) if hasattr(acc, 'current_balance') else "0",
                        "is_active": acc.is_active if hasattr(acc, 'is_active') else True,
                    }
                    for acc in accounts
                ]
            
            # Snapshot Journal Entry totals
            if snapshot_type in ["full", "journal_entries", "trial_balance"]:
                je_stmt = select(
                    func.sum(JournalEntry.total_debit).label("total_debits"),
                    func.sum(JournalEntry.total_credit).label("total_credits"),
                    func.count(JournalEntry.id).label("entry_count"),
                ).where(JournalEntry.entity_id == entity_id)
                
                je_result = await self.db.execute(je_stmt)
                je_totals = je_result.first()
                
                snapshot_data["tables"]["journal_entries_summary"] = {
                    "total_debits": str(je_totals.total_debits or 0),
                    "total_credits": str(je_totals.total_credits or 0),
                    "entry_count": je_totals.entry_count or 0,
                    "is_balanced": (je_totals.total_debits or 0) == (je_totals.total_credits or 0),
                }
            
            # Snapshot Transaction totals
            if snapshot_type in ["full", "transactions"]:
                txn_stmt = select(
                    func.sum(Transaction.amount).label("total_amount"),
                    func.sum(Transaction.vat_amount).label("total_vat"),
                    func.count(Transaction.id).label("transaction_count"),
                ).where(Transaction.entity_id == entity_id)
                
                txn_result = await self.db.execute(txn_stmt)
                txn_totals = txn_result.first()
                
                snapshot_data["tables"]["transactions_summary"] = {
                    "total_amount": str(txn_totals.total_amount or 0),
                    "total_vat": str(txn_totals.total_vat or 0),
                    "transaction_count": txn_totals.transaction_count or 0,
                }
            
            evidence_ref = await self._generate_evidence_ref(entity_id, "SNAP")
            
            evidence = AuditEvidence(
                entity_id=entity_id,
                finding_id=finding_id,
                evidence_ref=evidence_ref,
                evidence_type=EvidenceType.DATABASE_SNAPSHOT,
                title=title or f"Database Snapshot: {snapshot_type}",
                description=description or f"Point-in-time database snapshot ({snapshot_type})",
                content=snapshot_data,
                content_hash=self._calculate_content_hash(snapshot_data),
                collected_by=collected_by,
                collection_method="automated_snapshot",
            )
            
            self.db.add(evidence)
            await self.db.flush()
            await self.db.refresh(evidence)
            
            return EvidenceCollectionResult(
                success=True,
                evidence_id=evidence.id,
                evidence_ref=evidence.evidence_ref,
                content_hash=evidence.content_hash,
                metadata={
                    "snapshot_type": snapshot_type,
                    "tables_captured": list(snapshot_data["tables"].keys()),
                }
            )
            
        except Exception as e:
            return EvidenceCollectionResult(
                success=False,
                error=f"Database snapshot failed: {str(e)}"
            )
    
    # ==========================================
    # 7. THIRD-PARTY CONFIRMATION
    # ==========================================
    
    async def create_confirmation_request(
        self,
        entity_id: uuid.UUID,
        collected_by: uuid.UUID,
        confirmation_type: str,
        third_party_name: str,
        third_party_contact: str,
        request_details: Dict[str, Any],
        expected_response_date: date,
        finding_id: Optional[uuid.UUID] = None,
        title: Optional[str] = None,
    ) -> EvidenceCollectionResult:
        """
        Create a third-party confirmation request as evidence.
        
        Tracks external confirmation requests and their status.
        
        Args:
            entity_id: Business entity ID
            collected_by: User ID
            confirmation_type: Type (e.g., "bank_balance", "vendor_balance", "customer_balance")
            third_party_name: Name of the third party
            third_party_contact: Contact information
            request_details: Details of what's being confirmed
            expected_response_date: Expected date for response
            finding_id: Optional link to finding
            title: Evidence title
        
        Returns:
            EvidenceCollectionResult
        """
        try:
            content = {
                "confirmation_type": confirmation_type,
                "request_timestamp": datetime.now().isoformat(),
                "third_party": {
                    "name": third_party_name,
                    "contact": third_party_contact,
                },
                "request_details": request_details,
                "expected_response_date": expected_response_date.isoformat(),
                "status": "pending",
                "response": None,
                "response_date": None,
                "verified_by": None,
            }
            
            evidence_ref = await self._generate_evidence_ref(entity_id, "CONF")
            
            evidence = AuditEvidence(
                entity_id=entity_id,
                finding_id=finding_id,
                evidence_ref=evidence_ref,
                evidence_type=EvidenceType.EXTERNAL_CONFIRMATION,
                title=title or f"Confirmation Request: {third_party_name}",
                description=f"{confirmation_type} confirmation from {third_party_name}",
                content=content,
                content_hash=self._calculate_content_hash(content),
                collected_by=collected_by,
                collection_method="manual_request",
            )
            
            self.db.add(evidence)
            await self.db.flush()
            await self.db.refresh(evidence)
            
            return EvidenceCollectionResult(
                success=True,
                evidence_id=evidence.id,
                evidence_ref=evidence.evidence_ref,
                content_hash=evidence.content_hash,
                metadata={
                    "confirmation_type": confirmation_type,
                    "third_party": third_party_name,
                    "expected_response_date": expected_response_date.isoformat(),
                }
            )
            
        except Exception as e:
            return EvidenceCollectionResult(
                success=False,
                error=f"Confirmation request creation failed: {str(e)}"
            )
    
    async def record_confirmation_response(
        self,
        evidence_id: uuid.UUID,
        response_data: Dict[str, Any],
        response_file_content: Optional[bytes] = None,
        response_file_name: Optional[str] = None,
        verified_by: Optional[uuid.UUID] = None,
    ) -> EvidenceCollectionResult:
        """
        Record the response to a confirmation request.
        
        Note: This creates a NEW evidence record linked to the original,
        preserving immutability of the original request.
        
        Args:
            evidence_id: Original confirmation request evidence ID
            response_data: Response details
            response_file_content: Optional file attachment
            response_file_name: Optional filename
            verified_by: User ID who verified the response
        
        Returns:
            EvidenceCollectionResult for the new response evidence
        """
        try:
            # Get original evidence
            stmt = select(AuditEvidence).where(AuditEvidence.id == evidence_id)
            result = await self.db.execute(stmt)
            original = result.scalar_one_or_none()
            
            if not original:
                return EvidenceCollectionResult(
                    success=False,
                    error="Original confirmation request not found"
                )
            
            if original.evidence_type != EvidenceType.EXTERNAL_CONFIRMATION:
                return EvidenceCollectionResult(
                    success=False,
                    error="Evidence is not a confirmation request"
                )
            
            # Create response content
            response_content = {
                "original_request_id": str(evidence_id),
                "original_request_ref": original.evidence_ref,
                "response_timestamp": datetime.now().isoformat(),
                "response_data": response_data,
                "verification_status": "verified" if verified_by else "pending_verification",
                "verified_by": str(verified_by) if verified_by else None,
            }
            
            # Handle file attachment
            file_path = None
            file_hash = None
            if response_file_content and response_file_name:
                file_hash = self._calculate_hash(response_file_content)
                safe_filename = f"confirmation_response_{file_hash[:16]}.pdf"
                file_path = EVIDENCE_UPLOAD_DIR / str(original.entity_id) / "confirmations" / safe_filename
                file_path.parent.mkdir(parents=True, exist_ok=True)
                
                async with aiofiles.open(file_path, "wb") as f:
                    await f.write(response_file_content)
                
                response_content["file_name"] = response_file_name
                response_content["file_hash"] = file_hash
            
            evidence_ref = await self._generate_evidence_ref(original.entity_id, "RESP")
            
            evidence = AuditEvidence(
                entity_id=original.entity_id,
                finding_id=original.finding_id,
                evidence_ref=evidence_ref,
                evidence_type=EvidenceType.EXTERNAL_CONFIRMATION,
                title=f"Response: {original.title}",
                description=f"Response to confirmation request {original.evidence_ref}",
                content=response_content,
                content_hash=self._calculate_content_hash(response_content),
                file_path=str(file_path) if file_path else None,
                file_hash=file_hash,
                collected_by=verified_by or original.collected_by,
                collection_method="confirmation_response",
                is_verified=bool(verified_by),
                verified_by=verified_by,
                verified_at=datetime.now() if verified_by else None,
            )
            
            self.db.add(evidence)
            await self.db.flush()
            await self.db.refresh(evidence)
            
            return EvidenceCollectionResult(
                success=True,
                evidence_id=evidence.id,
                evidence_ref=evidence.evidence_ref,
                content_hash=evidence.content_hash,
                metadata={
                    "original_request_ref": original.evidence_ref,
                    "is_verified": bool(verified_by),
                }
            )
            
        except Exception as e:
            return EvidenceCollectionResult(
                success=False,
                error=f"Response recording failed: {str(e)}"
            )
    
    # ==========================================
    # 8. AUTO-COLLECTION DURING AUDIT RUNS
    # ==========================================
    
    async def auto_collect_for_finding(
        self,
        finding: AuditFinding,
        collected_by: uuid.UUID,
    ) -> List[EvidenceCollectionResult]:
        """
        Automatically collect relevant evidence for an audit finding.
        
        Based on the finding category and type, collects appropriate evidence.
        
        Args:
            finding: The audit finding to collect evidence for
            collected_by: User ID
        
        Returns:
            List of EvidenceCollectionResult for each evidence collected
        """
        results = []
        entity_id = finding.audit_run.entity_id if finding.audit_run else None
        
        if not entity_id:
            return [EvidenceCollectionResult(success=False, error="Finding has no associated entity")]
        
        try:
            # Based on finding category, collect appropriate evidence
            
            # For transaction-related findings, collect the affected transactions
            if finding.category in [FindingCategory.FRAUD_INDICATOR, FindingCategory.TAX_DISCREPANCY]:
                if finding.affected_record_ids:
                    result = await self.collect_transaction_records(
                        entity_id=entity_id,
                        collected_by=collected_by,
                        transaction_ids=[uuid.UUID(rid) for rid in finding.affected_record_ids[:50]],
                        finding_id=finding.id,
                        title=f"Transactions for Finding: {finding.finding_ref}",
                        description=f"Auto-collected transactions related to {finding.title}",
                    )
                    results.append(result)
            
            # For control deficiency, collect relevant logs
            if finding.category == FindingCategory.CONTROL_DEFICIENCY:
                result = await self.extract_system_logs(
                    entity_id=entity_id,
                    collected_by=collected_by,
                    date_from=finding.audit_run.period_start if finding.audit_run else date.today() - timedelta(days=30),
                    date_to=finding.audit_run.period_end if finding.audit_run else date.today(),
                    finding_id=finding.id,
                    title=f"Audit Logs for Finding: {finding.finding_ref}",
                )
                results.append(result)
            
            # Always create a calculation evidence for the finding's impact
            if finding.affected_amount and finding.affected_amount > 0:
                result = await self.collect_calculation_evidence(
                    entity_id=entity_id,
                    collected_by=collected_by,
                    calculation_type="finding_impact",
                    inputs={
                        "finding_ref": finding.finding_ref,
                        "affected_records": finding.affected_records,
                        "risk_level": finding.risk_level.value if finding.risk_level else "medium",
                    },
                    outputs={
                        "affected_amount": str(finding.affected_amount),
                        "impact_assessment": finding.impact,
                    },
                    formula_description="Finding impact calculation based on affected records and amounts",
                    finding_id=finding.id,
                    title=f"Impact Calculation: {finding.finding_ref}",
                )
                results.append(result)
            
            return results
            
        except Exception as e:
            return [EvidenceCollectionResult(success=False, error=f"Auto-collection failed: {str(e)}")]
    
    async def collect_audit_run_evidence(
        self,
        audit_run: AuditRun,
        collected_by: uuid.UUID,
    ) -> List[EvidenceCollectionResult]:
        """
        Collect comprehensive evidence for an audit run.
        
        Creates a database snapshot and collects summary evidence.
        
        Args:
            audit_run: The audit run to collect evidence for
            collected_by: User ID
        
        Returns:
            List of EvidenceCollectionResult
        """
        results = []
        
        try:
            # Create database snapshot at audit start
            result = await self.create_database_snapshot(
                entity_id=audit_run.entity_id,
                collected_by=collected_by,
                snapshot_type="full",
                title=f"Audit Run Snapshot: {audit_run.run_id}",
                description=f"Database state at start of audit run {audit_run.run_id}",
            )
            results.append(result)
            
            # Collect transactions for the audit period
            result = await self.collect_transaction_records(
                entity_id=audit_run.entity_id,
                collected_by=collected_by,
                date_from=audit_run.period_start,
                date_to=audit_run.period_end,
                title=f"Audit Period Transactions: {audit_run.run_id}",
                description=f"All transactions in audit period {audit_run.period_start} to {audit_run.period_end}",
            )
            results.append(result)
            
            # Extract audit logs for the period
            result = await self.extract_system_logs(
                entity_id=audit_run.entity_id,
                collected_by=collected_by,
                date_from=audit_run.period_start,
                date_to=audit_run.period_end,
                title=f"Audit Period Logs: {audit_run.run_id}",
            )
            results.append(result)
            
            return results
            
        except Exception as e:
            return [EvidenceCollectionResult(success=False, error=f"Audit run evidence collection failed: {str(e)}")]
    
    # ==========================================
    # VERIFICATION & RETRIEVAL
    # ==========================================
    
    async def verify_evidence_integrity(
        self,
        evidence_id: uuid.UUID,
        entity_id: Optional[uuid.UUID] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Verify the integrity of evidence by recalculating its hash.
        
        Args:
            evidence_id: Evidence ID to verify
            entity_id: Optional entity ID for security check
        
        Returns:
            Tuple of (is_valid, computed_hash, details_dict)
        """
        stmt = select(AuditEvidence).where(AuditEvidence.id == evidence_id)
        if entity_id:
            stmt = stmt.where(AuditEvidence.entity_id == entity_id)
        
        result = await self.db.execute(stmt)
        evidence = result.scalar_one_or_none()
        
        details: Dict[str, Any] = {}
        
        if not evidence:
            return False, "", {"error": "Evidence not found"}
        
        # Recalculate content hash
        current_hash = self._calculate_content_hash(evidence.content)
        details["content_hash_matches"] = (current_hash == evidence.content_hash)
        details["stored_content_hash"] = evidence.content_hash
        details["computed_content_hash"] = current_hash
        
        if current_hash != evidence.content_hash:
            details["error"] = "Content integrity compromised"
            return False, current_hash, details
        
        # Verify file hash if present
        file_hash_valid = None
        if evidence.file_path and evidence.file_hash:
            try:
                async with aiofiles.open(evidence.file_path, "rb") as f:
                    file_content = await f.read()
                current_file_hash = self._calculate_hash(file_content)
                
                file_hash_valid = (current_file_hash == evidence.file_hash)
                details["file_hash_valid"] = file_hash_valid
                details["stored_file_hash"] = evidence.file_hash
                details["computed_file_hash"] = current_file_hash
                
                if not file_hash_valid:
                    details["error"] = "File integrity compromised"
                    return False, current_hash, details
            except FileNotFoundError:
                details["file_hash_valid"] = False
                details["error"] = f"Evidence file not found: {evidence.file_path}"
                return False, current_hash, details
        
        details["verified"] = True
        details["verification_message"] = "Evidence integrity verified"
        return True, current_hash, details
    
    async def get_evidence_by_id(
        self,
        evidence_id: uuid.UUID,
    ) -> Optional[AuditEvidence]:
        """Get evidence by ID."""
        stmt = select(AuditEvidence).where(AuditEvidence.id == evidence_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_evidence_by_ref(
        self,
        evidence_ref: str,
    ) -> Optional[AuditEvidence]:
        """Get evidence by reference."""
        stmt = select(AuditEvidence).where(AuditEvidence.evidence_ref == evidence_ref)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def list_evidence(
        self,
        entity_id: uuid.UUID,
        evidence_type: Optional[EvidenceType] = None,
        finding_id: Optional[uuid.UUID] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[AuditEvidence], int]:
        """
        List evidence with filtering and pagination.
        
        Returns:
            Tuple of (evidence_list, total_count)
        """
        stmt = select(AuditEvidence).where(AuditEvidence.entity_id == entity_id)
        
        if evidence_type:
            stmt = stmt.where(AuditEvidence.evidence_type == evidence_type)
        
        if finding_id:
            stmt = stmt.where(AuditEvidence.finding_id == finding_id)
        
        if date_from:
            stmt = stmt.where(AuditEvidence.collected_at >= datetime.combine(date_from, datetime.min.time()))
        
        if date_to:
            stmt = stmt.where(AuditEvidence.collected_at <= datetime.combine(date_to, datetime.max.time()))
        
        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0
        
        # Paginate
        stmt = stmt.order_by(AuditEvidence.collected_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        
        result = await self.db.execute(stmt)
        evidence_list = result.scalars().all()
        
        return evidence_list, total
    
    async def get_evidence_file(
        self,
        evidence_id: uuid.UUID,
    ) -> Optional[Tuple[bytes, str, str]]:
        """
        Get evidence file content.
        
        Returns:
            Tuple of (content, filename, mime_type) or None
        """
        evidence = await self.get_evidence_by_id(evidence_id)
        
        if not evidence or not evidence.file_path:
            return None
        
        try:
            async with aiofiles.open(evidence.file_path, "rb") as f:
                content = await f.read()
            
            filename = evidence.content.get("original_filename", "evidence_file")
            mime_type = evidence.file_mime_type or "application/octet-stream"
            
            return content, filename, mime_type
        except FileNotFoundError:
            return None
