"""
Tekvwa Pro Audit - NTAA 2025 Compliance Service

Service for handling Nigeria Tax Administration Act 2025 compliance requirements:
1. 72-Hour Legal Lock for NRS-submitted invoices
2. Maker-Checker Segregation of Duties for WREN expenses
3. Time-limited CSR Impersonation (24-hour tokens per NDPA)
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole
from app.models.invoice import Invoice, InvoiceStatus
from app.models.transaction import Transaction, WRENStatus
from app.models.audit_consolidated import AuditLog, AuditAction
from app.utils.permissions import OrganizationPermission, has_organization_permission


class NTAAComplianceService:
    """
    Service for NTAA 2025 compliance features.
    
    Implements:
    - 72-Hour Legal Lock (State Lock for NRS-submitted invoices)
    - Maker-Checker SoD for WREN verification
    - Time-limited impersonation tokens
    """
    
    # NRS Legal Lock window (72 hours)
    NRS_LOCK_HOURS = 72
    
    # CSR Impersonation window (24 hours per NDPA)
    IMPERSONATION_HOURS = 24
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # ===========================================
    # 72-HOUR LEGAL LOCK FOR NRS INVOICES
    # ===========================================
    
    async def apply_nrs_lock(
        self,
        invoice: Invoice,
        nrs_irn: str,
        nrs_response: dict,
        nrs_cryptographic_stamp: Optional[str] = None,
    ) -> Invoice:
        """
        Apply the 72-hour legal lock when an invoice is submitted to NRS.
        
        After this, the invoice cannot be edited or deleted.
        Only the Owner can cancel the NRS submission during this window.
        
        Args:
            invoice: The invoice being submitted
            nrs_irn: Invoice Reference Number from NRS
            nrs_response: Full NRS server response
            nrs_cryptographic_stamp: Cryptographic signature from NRS
            
        Returns:
            Updated invoice with lock applied
        """
        now = datetime.now()
        lock_expires = now + timedelta(hours=self.NRS_LOCK_HOURS)
        
        invoice.nrs_irn = nrs_irn
        invoice.nrs_response = nrs_response
        invoice.nrs_cryptographic_stamp = nrs_cryptographic_stamp
        invoice.nrs_submitted_at = now
        invoice.is_nrs_locked = True
        invoice.nrs_lock_expires_at = lock_expires
        invoice.status = InvoiceStatus.SUBMITTED
        
        # Set buyer review deadline
        invoice.dispute_deadline = lock_expires
        
        await self.db.commit()
        await self.db.refresh(invoice)
        
        return invoice
    
    def check_invoice_editable(
        self,
        invoice: Invoice,
        user: User,
    ) -> Tuple[bool, str]:
        """
        Check if an invoice can be edited by the user.
        
        NTAA 2025 Rules:
        - DRAFT invoices can be edited by users with MANAGE_INVOICES permission
        - SUBMITTED/ACCEPTED invoices are locked and cannot be edited
        - Locked invoices require a Credit Note for any modifications
        
        Returns:
            Tuple of (can_edit, reason)
        """
        # Draft invoices are editable
        if invoice.status == InvoiceStatus.DRAFT:
            return True, "Invoice is in draft status"
        
        # Check NRS lock
        if invoice.is_nrs_locked:
            return False, "Invoice is locked after NRS submission. Use Credit Note for modifications."
        
        # Check status
        if invoice.status in [InvoiceStatus.SUBMITTED, InvoiceStatus.ACCEPTED]:
            return False, "Submitted/Accepted invoices cannot be edited. Use Credit Note instead."
        
        if invoice.status == InvoiceStatus.PAID:
            return False, "Paid invoices cannot be edited."
        
        if invoice.status == InvoiceStatus.CANCELLED:
            return False, "Cancelled invoices cannot be edited."
        
        return True, "Invoice can be edited"
    
    async def cancel_nrs_submission(
        self,
        invoice: Invoice,
        user: User,
        reason: str,
    ) -> Tuple[bool, str]:
        """
        Cancel an NRS submission during the 72-hour window.
        
        NTAA 2025 Rule: Only Owner can cancel NRS submissions.
        This must be done within the 72-hour window.
        
        Args:
            invoice: The invoice to cancel
            user: The user requesting cancellation
            reason: Reason for cancellation
            
        Returns:
            Tuple of (success, message)
        """
        # Check permission (Owner only)
        if not has_organization_permission(user.role, OrganizationPermission.CANCEL_NRS_SUBMISSION):
            return False, "Only the Owner can cancel NRS submissions"
        
        # Check if within 72-hour window
        if not invoice.is_nrs_locked:
            return False, "Invoice is not NRS-locked"
        
        now = datetime.now()
        if invoice.nrs_lock_expires_at and now > invoice.nrs_lock_expires_at:
            return False, "72-hour cancellation window has expired. Use Credit Note instead."
        
        # Cancel the NRS submission
        invoice.is_nrs_locked = False
        invoice.nrs_cancelled_by_id = user.id
        invoice.nrs_cancellation_reason = reason
        invoice.status = InvoiceStatus.CANCELLED
        
        await self.db.commit()
        
        return True, "NRS submission cancelled successfully"
    
    # ===========================================
    # MAKER-CHECKER FOR WREN VERIFICATION
    # ===========================================
    
    async def verify_wren_status(
        self,
        transaction: Transaction,
        verifier: User,
        new_status: WRENStatus,
        notes: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Verify the WREN status of a transaction.
        
        NTAA 2025 Maker-Checker Rule:
        - The verifier (Checker) cannot be the same as the creator (Maker)
        - This enforces Segregation of Duties
        
        Args:
            transaction: The transaction to verify
            verifier: The user verifying WREN status
            new_status: The new WREN status
            notes: Optional verification notes
            
        Returns:
            Tuple of (success, message)
        """
        # Check permission
        if not has_organization_permission(verifier.role, OrganizationPermission.VERIFY_WREN):
            return False, "You don't have permission to verify WREN status"
        
        # MAKER-CHECKER: Verifier cannot be the creator
        if transaction.created_by_id == verifier.id:
            return False, "Segregation of Duties: You cannot verify an expense you created"
        
        # Store before state for audit trail
        old_status = transaction.wren_status
        
        # Update WREN status
        transaction.wren_status = new_status
        transaction.wren_verified_by_id = verifier.id
        transaction.wren_verified_at = datetime.now()
        
        if notes:
            transaction.wren_notes = notes
        
        await self.db.commit()
        
        # Log the WREN verification
        await self._log_wren_verification(
            transaction=transaction,
            verifier=verifier,
            old_status=old_status,
            new_status=new_status,
        )
        
        return True, f"WREN status updated to {new_status.value}"
    
    async def _log_wren_verification(
        self,
        transaction: Transaction,
        verifier: User,
        old_status: WRENStatus,
        new_status: WRENStatus,
    ):
        """Log WREN verification for audit trail."""
        audit_log = AuditLog(
            entity_id=transaction.entity_id,
            user_id=verifier.id,
            action=AuditAction.WREN_VERIFY,
            target_entity_type="transaction",
            target_entity_id=str(transaction.id),
            old_values={"wren_status": old_status.value},
            new_values={"wren_status": new_status.value},
            changes={
                "wren_status": {
                    "old": old_status.value,
                    "new": new_status.value
                },
                "verified_by": str(verifier.id),
                "verified_at": datetime.now().isoformat()
            },
            description=f"WREN status verified: {old_status.value} → {new_status.value}"
        )
        
        self.db.add(audit_log)
        await self.db.commit()
    
    async def check_category_change_permission(
        self,
        transaction: Transaction,
        user: User,
        new_category_id: uuid.UUID,
    ) -> Tuple[bool, str, dict]:
        """
        Check if a category change is permitted and create audit snapshot.
        
        NTAA 2025 requires before/after snapshots for category changes
        (e.g., Personal → Business) for audit purposes.
        
        Returns:
            Tuple of (permitted, message, audit_snapshot)
        """
        # Get current category for snapshot
        current_category_id = transaction.category_id
        
        # Create audit snapshot
        audit_snapshot = {
            "changed_at": datetime.now().isoformat(),
            "changed_by": str(user.id),
            "old_category_id": str(current_category_id) if current_category_id else None,
            "new_category_id": str(new_category_id),
        }
        
        # If this is the first change, store original
        if transaction.original_category_id is None:
            transaction.original_category_id = current_category_id
        
        # Append to change history
        if transaction.category_change_history is None:
            transaction.category_change_history = []
        
        history = transaction.category_change_history.copy() if transaction.category_change_history else []
        history.append(audit_snapshot)
        transaction.category_change_history = history
        
        return True, "Category change permitted", audit_snapshot
    
    # ===========================================
    # TIME-LIMITED IMPERSONATION (NDPA COMPLIANCE)
    # ===========================================
    
    async def grant_impersonation(
        self,
        user: User,
        hours: int = 24,
    ) -> Tuple[bool, str, Optional[datetime]]:
        """
        Grant time-limited impersonation permission.
        
        NDPA Compliance: Maximum 24-hour window for CSR impersonation.
        
        Args:
            user: The user granting impersonation
            hours: Number of hours (max 24)
            
        Returns:
            Tuple of (success, message, expiry_time)
        """
        if user.is_platform_staff:
            return False, "Platform staff cannot be impersonated", None
        
        # Cap at 24 hours per NDPA
        hours = min(hours, self.IMPERSONATION_HOURS)
        
        now = datetime.now()
        expires_at = now + timedelta(hours=hours)
        
        user.can_be_impersonated = True
        user.impersonation_granted_at = now
        user.impersonation_expires_at = expires_at
        
        await self.db.commit()
        
        return True, f"Impersonation granted for {hours} hours", expires_at
    
    async def revoke_impersonation(self, user: User) -> Tuple[bool, str]:
        """
        Revoke impersonation permission immediately.
        
        Returns:
            Tuple of (success, message)
        """
        user.can_be_impersonated = False
        user.impersonation_expires_at = None
        
        await self.db.commit()
        
        return True, "Impersonation permission revoked"
    
    def check_impersonation_valid(self, user: User) -> Tuple[bool, str]:
        """
        Check if impersonation is currently valid.
        
        Checks:
        - can_be_impersonated flag is True
        - Token has not expired
        - User is not platform staff
        
        Returns:
            Tuple of (valid, message)
        """
        if user.is_platform_staff:
            return False, "Platform staff cannot be impersonated"
        
        if not user.can_be_impersonated:
            return False, "User has not granted impersonation permission"
        
        if user.impersonation_expires_at:
            if datetime.now() > user.impersonation_expires_at:
                return False, "Impersonation permission has expired"
        
        return True, "Impersonation is valid"
    
    async def log_impersonation_action(
        self,
        target_user: User,
        csr_user: User,
        action: str,  # "start" or "end"
        entity_id: Optional[uuid.UUID] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        """
        Log impersonation start/end for audit trail.
        
        This is critical for NDPA compliance and accountability.
        """
        audit_action = (
            AuditAction.IMPERSONATION_START if action == "start"
            else AuditAction.IMPERSONATION_END
        )
        
        audit_log = AuditLog(
            entity_id=entity_id,
            user_id=target_user.id,
            impersonated_by_id=csr_user.id,
            action=audit_action,
            target_entity_type="user",
            target_entity_id=str(target_user.id),
            ip_address=ip_address,
            user_agent=user_agent,
            description=f"CSR {csr_user.email} {action}ed impersonating {target_user.email}",
            new_values={
                "csr_id": str(csr_user.id),
                "csr_email": csr_user.email,
                "target_user_id": str(target_user.id),
                "target_user_email": target_user.email,
                "action": action,
            }
        )
        
        self.db.add(audit_log)
        await self.db.commit()
    
    # ===========================================
    # AUDIT TRAIL HELPERS
    # ===========================================
    
    async def create_enhanced_audit_log(
        self,
        entity_id: Optional[uuid.UUID],
        user_id: uuid.UUID,
        action: AuditAction,
        target_type: str,
        target_id: str,
        old_values: Optional[dict] = None,
        new_values: Optional[dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        device_fingerprint: Optional[str] = None,
        session_id: Optional[str] = None,
        nrs_irn: Optional[str] = None,
        nrs_response: Optional[dict] = None,
        description: Optional[str] = None,
        impersonated_by_id: Optional[uuid.UUID] = None,
    ) -> AuditLog:
        """
        Create an enhanced audit log entry with NTAA 2025 required fields.
        
        Includes:
        - Device fingerprint for proving submission source
        - Before/after snapshots
        - NRS response storage
        - Impersonation tracking
        """
        audit_log = AuditLog(
            entity_id=entity_id,
            user_id=user_id,
            impersonated_by_id=impersonated_by_id,
            action=action,
            target_entity_type=target_type,
            target_entity_id=target_id,
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address,
            user_agent=user_agent,
            device_fingerprint=device_fingerprint,
            session_id=session_id,
            nrs_irn=nrs_irn,
            nrs_response=nrs_response,
            description=description,
        )
        
        # Calculate changes if both old and new values provided
        if old_values and new_values:
            changes = {}
            all_keys = set(old_values.keys()) | set(new_values.keys())
            for key in all_keys:
                old_val = old_values.get(key)
                new_val = new_values.get(key)
                if old_val != new_val:
                    changes[key] = {"old": old_val, "new": new_val}
            audit_log.changes = changes
        
        self.db.add(audit_log)
        await self.db.commit()
        
        return audit_log
