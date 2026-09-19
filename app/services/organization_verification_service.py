"""
Tekvwa Pro Audit - Enhanced Organization Verification Service

Provides comprehensive verification workflow for organizations:
- List organizations by verification status
- Start review (move to UNDER_REVIEW)
- Approve organization (VERIFIED)
- Reject organization (REJECTED)
- Request additional documents
- Get verification history from audit logs
- Download/view verification documents
"""

import uuid
import json
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple

from sqlalchemy import select, func, desc, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.organization import Organization, VerificationStatus
from app.models.user import User, PlatformRole
from app.models.audit_consolidated import AuditLog
from app.utils.permissions import PlatformPermission, has_platform_permission


class OrganizationVerificationService:
    """Service for managing organization verification workflows."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # ===========================================
    # PERMISSION CHECK
    # ===========================================
    
    def _check_verification_permission(self, user: User) -> None:
        """Check if user has permission to verify organizations."""
        if user.platform_role == PlatformRole.SUPER_ADMIN:
            return  # Super Admin always has permission
        
        if not has_platform_permission(
            user.platform_role,
            PlatformPermission.VERIFY_ORGANIZATIONS
        ):
            raise PermissionError("You don't have permission to verify organizations")
    
    # ===========================================
    # LIST/FILTER ORGANIZATIONS
    # ===========================================
    
    async def get_verification_stats(
        self,
        requesting_user: User,
    ) -> Dict[str, int]:
        """Get statistics about organization verification statuses."""
        self._check_verification_permission(requesting_user)
        
        # Count by status
        result = await self.db.execute(
            select(
                Organization.verification_status,
                func.count(Organization.id)
            )
            .group_by(Organization.verification_status)
        )
        
        status_counts = {
            "pending": 0,
            "submitted": 0,
            "under_review": 0,
            "verified": 0,
            "rejected": 0,
            "total": 0,
        }
        
        for status, count in result.all():
            status_counts[status.value] = count
            status_counts["total"] += count
        
        return status_counts
    
    async def list_organizations_for_verification(
        self,
        requesting_user: User,
        status_filter: Optional[str] = None,
        search_query: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[Organization], int]:
        """
        List organizations with optional filtering for verification workflow.
        
        Args:
            requesting_user: User requesting the list
            status_filter: Filter by verification status (pending, submitted, under_review, verified, rejected)
            search_query: Search by name or email
            skip: Number of records to skip (pagination)
            limit: Max number of records to return
            
        Returns:
            Tuple of (list of organizations, total count)
        """
        self._check_verification_permission(requesting_user)
        
        # Build base query
        query = select(Organization)
        count_query = select(func.count(Organization.id))
        
        conditions = []
        
        # Status filter
        if status_filter:
            if status_filter == "pending_review":
                # Combine submitted and under_review for "pending review"
                conditions.append(
                    or_(
                        Organization.verification_status == VerificationStatus.SUBMITTED,
                        Organization.verification_status == VerificationStatus.UNDER_REVIEW
                    )
                )
            else:
                try:
                    status = VerificationStatus(status_filter)
                    conditions.append(Organization.verification_status == status)
                except ValueError:
                    pass  # Invalid status, ignore filter
        
        # Search filter
        if search_query:
            search_term = f"%{search_query}%"
            conditions.append(
                or_(
                    Organization.name.ilike(search_term),
                    Organization.email.ilike(search_term),
                    Organization.contact_email.ilike(search_term),
                )
            )
        
        # Apply conditions
        if conditions:
            query = query.where(and_(*conditions))
            count_query = count_query.where(and_(*conditions))
        
        # Get total count
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0
        
        # Apply ordering and pagination
        query = query.order_by(
            # Prioritize pending items first
            Organization.verification_status.asc(),
            Organization.created_at.desc()
        ).offset(skip).limit(limit)
        
        result = await self.db.execute(query)
        organizations = list(result.scalars().all())
        
        return organizations, total
    
    # ===========================================
    # VERIFICATION WORKFLOW ACTIONS
    # ===========================================
    
    async def start_review(
        self,
        requesting_user: User,
        organization_id: uuid.UUID,
        notes: Optional[str] = None,
    ) -> Organization:
        """
        Start reviewing an organization (move from SUBMITTED to UNDER_REVIEW).
        
        Args:
            requesting_user: Admin starting the review
            organization_id: Organization to review
            notes: Optional notes
            
        Returns:
            Updated organization
        """
        self._check_verification_permission(requesting_user)
        
        org = await self._get_organization(organization_id)
        
        if org.verification_status != VerificationStatus.SUBMITTED:
            raise ValueError(
                f"Can only start review for organizations with 'submitted' status. "
                f"Current status: {org.verification_status.value}"
            )
        
        # Update status
        org.verification_status = VerificationStatus.UNDER_REVIEW
        org.verified_by_id = str(requesting_user.id)
        if notes:
            org.verification_notes = notes
        
        await self.db.commit()
        await self.db.refresh(org)
        
        # Log the action
        await self._log_verification_action(
            organization_id=organization_id,
            action="start_review",
            user=requesting_user,
            notes=notes,
            old_status="submitted",
            new_status="under_review",
        )
        
        return org
    
    async def approve_organization(
        self,
        requesting_user: User,
        organization_id: uuid.UUID,
        notes: Optional[str] = None,
    ) -> Organization:
        """
        Approve an organization's verification.
        
        Args:
            requesting_user: Admin approving
            organization_id: Organization to approve
            notes: Optional approval notes
            
        Returns:
            Updated organization
        """
        self._check_verification_permission(requesting_user)
        
        org = await self._get_organization(organization_id)
        old_status = org.verification_status.value
        
        if org.verification_status not in [
            VerificationStatus.SUBMITTED, 
            VerificationStatus.UNDER_REVIEW
        ]:
            raise ValueError(
                f"Can only approve organizations with 'submitted' or 'under_review' status. "
                f"Current status: {org.verification_status.value}"
            )
        
        # Update status
        org.verification_status = VerificationStatus.VERIFIED
        org.verified_by_id = str(requesting_user.id)
        org.verification_notes = notes
        
        await self.db.commit()
        await self.db.refresh(org)
        
        # Log the action
        await self._log_verification_action(
            organization_id=organization_id,
            action="approve",
            user=requesting_user,
            notes=notes,
            old_status=old_status,
            new_status="verified",
        )
        
        return org
    
    async def reject_organization(
        self,
        requesting_user: User,
        organization_id: uuid.UUID,
        reason: str,
    ) -> Organization:
        """
        Reject an organization's verification.
        
        Args:
            requesting_user: Admin rejecting
            organization_id: Organization to reject
            reason: Rejection reason (required)
            
        Returns:
            Updated organization
        """
        self._check_verification_permission(requesting_user)
        
        if not reason or len(reason.strip()) < 5:
            raise ValueError("Rejection reason is required (minimum 5 characters)")
        
        org = await self._get_organization(organization_id)
        old_status = org.verification_status.value
        
        if org.verification_status not in [
            VerificationStatus.SUBMITTED, 
            VerificationStatus.UNDER_REVIEW
        ]:
            raise ValueError(
                f"Can only reject organizations with 'submitted' or 'under_review' status. "
                f"Current status: {org.verification_status.value}"
            )
        
        # Update status
        org.verification_status = VerificationStatus.REJECTED
        org.verified_by_id = str(requesting_user.id)
        org.verification_notes = reason
        
        await self.db.commit()
        await self.db.refresh(org)
        
        # Log the action
        await self._log_verification_action(
            organization_id=organization_id,
            action="reject",
            user=requesting_user,
            notes=reason,
            old_status=old_status,
            new_status="rejected",
        )
        
        return org
    
    async def request_additional_documents(
        self,
        requesting_user: User,
        organization_id: uuid.UUID,
        requested_documents: List[str],
        notes: str,
    ) -> Organization:
        """
        Request additional documents from an organization.
        Keeps status at UNDER_REVIEW but adds notes about requested documents.
        
        Args:
            requesting_user: Admin requesting documents
            organization_id: Organization
            requested_documents: List of document types requested
            notes: Instructions for the organization
            
        Returns:
            Updated organization
        """
        self._check_verification_permission(requesting_user)
        
        if not requested_documents or not notes:
            raise ValueError("Requested documents and notes are required")
        
        org = await self._get_organization(organization_id)
        old_status = org.verification_status.value
        
        if org.verification_status not in [
            VerificationStatus.SUBMITTED, 
            VerificationStatus.UNDER_REVIEW
        ]:
            raise ValueError(
                f"Can only request documents for organizations with 'submitted' or 'under_review' status. "
                f"Current status: {org.verification_status.value}"
            )
        
        # Keep at UNDER_REVIEW
        org.verification_status = VerificationStatus.UNDER_REVIEW
        org.verified_by_id = str(requesting_user.id)
        org.verification_notes = f"[DOCUMENTS REQUESTED: {', '.join(requested_documents)}]\n{notes}"
        
        await self.db.commit()
        await self.db.refresh(org)
        
        # Log the action
        await self._log_verification_action(
            organization_id=organization_id,
            action="request_documents",
            user=requesting_user,
            notes=notes,
            old_status=old_status,
            new_status="under_review",
            metadata={"requested_documents": requested_documents},
        )
        
        return org
    
    async def reset_to_submitted(
        self,
        requesting_user: User,
        organization_id: uuid.UUID,
        reason: str,
    ) -> Organization:
        """
        Reset a rejected organization back to submitted status.
        Allows them to be reviewed again after resubmitting documents.
        
        Args:
            requesting_user: Super Admin performing reset
            organization_id: Organization to reset
            reason: Reason for reset
            
        Returns:
            Updated organization
        """
        # Only Super Admin can reset
        if requesting_user.platform_role != PlatformRole.SUPER_ADMIN:
            raise PermissionError("Only Super Admin can reset verification status")
        
        org = await self._get_organization(organization_id)
        old_status = org.verification_status.value
        
        # Update status
        org.verification_status = VerificationStatus.SUBMITTED
        org.verified_by_id = str(requesting_user.id)
        org.verification_notes = f"[RESET] {reason}"
        
        await self.db.commit()
        await self.db.refresh(org)
        
        # Log the action
        await self._log_verification_action(
            organization_id=organization_id,
            action="reset_status",
            user=requesting_user,
            notes=reason,
            old_status=old_status,
            new_status="submitted",
        )
        
        return org
    
    # ===========================================
    # VERIFICATION HISTORY
    # ===========================================
    
    async def get_verification_history(
        self,
        requesting_user: User,
        organization_id: uuid.UUID,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get verification history for an organization from audit logs.
        
        Args:
            requesting_user: Admin requesting history
            organization_id: Organization to get history for
            limit: Max records to return
            
        Returns:
            List of verification history entries
        """
        self._check_verification_permission(requesting_user)
        
        # Query audit logs for this organization's verification actions
        # Use target_entity_type and target_entity_id (actual AuditLog model fields)
        result = await self.db.execute(
            select(AuditLog)
            .where(
                and_(
                    AuditLog.target_entity_type == "organization_verification",
                    AuditLog.target_entity_id == str(organization_id),
                )
            )
            .order_by(desc(AuditLog.created_at))
            .limit(limit)
        )
        
        logs = result.scalars().all()
        
        history = []
        for log in logs:
            # Use new_values or changes for details since AuditLog doesn't have 'details' field
            details = log.new_values or log.changes or {}
            entry = {
                "id": str(log.id),
                "action": log.action,
                "user_id": str(log.user_id) if log.user_id else None,
                "user_email": log.user_email,
                "details": details if isinstance(details, dict) else {},
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            history.append(entry)
        
        return history
    
    # ===========================================
    # DOCUMENT ACCESS
    # ===========================================
    
    async def get_organization_details(
        self,
        requesting_user: User,
        organization_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Get detailed organization information for verification review.
        
        Args:
            requesting_user: Admin viewing details
            organization_id: Organization to view
            
        Returns:
            Organization details including documents
        """
        self._check_verification_permission(requesting_user)
        
        org = await self._get_organization(organization_id)
        
        # Get user count for this organization
        from app.models.user import User as UserModel
        user_count_result = await self.db.execute(
            select(func.count(UserModel.id))
            .where(UserModel.organization_id == organization_id)
        )
        user_count = user_count_result.scalar() or 0
        
        # Get admin user if exists
        admin_result = await self.db.execute(
            select(UserModel)
            .where(
                and_(
                    UserModel.organization_id == organization_id,
                    UserModel.role == "admin"
                )
            )
            .limit(1)
        )
        admin = admin_result.scalar_one_or_none()
        
        # Parse additional documents
        additional_docs = []
        if org.additional_documents:
            try:
                additional_docs = json.loads(org.additional_documents)
            except (json.JSONDecodeError, TypeError):
                pass
        
        return {
            "id": str(org.id),
            "name": org.name,
            "slug": org.slug,
            "email": org.email,
            "phone": org.phone,
            "organization_type": org.organization_type.value if org.organization_type else None,
            "subscription_tier": org.subscription_tier.value if org.subscription_tier else None,
            "verification_status": org.verification_status.value if org.verification_status else "pending",
            "verification_notes": org.verification_notes,
            "verified_by_id": str(org.verified_by_id) if org.verified_by_id else None,
            "is_emergency_suspended": org.is_emergency_suspended,
            "emergency_suspension_reason": org.emergency_suspension_reason,
            "user_count": user_count,
            "created_at": org.created_at.isoformat() if org.created_at else None,
            "updated_at": org.updated_at.isoformat() if org.updated_at else None,
            "documents": {
                "cac_document_path": org.cac_document_path,
                "tin_document_path": org.tin_document_path,
                "additional_documents": additional_docs,
            },
            "admin_contact": {
                "name": f"{admin.first_name} {admin.last_name}" if admin else None,
                "email": admin.email if admin else None,
                "phone": admin.phone_number if admin else None,
            } if admin else None,
        }
    
    # ===========================================
    # HELPER METHODS
    # ===========================================
    
    async def _get_organization(self, organization_id: uuid.UUID) -> Organization:
        """Get organization by ID or raise error."""
        result = await self.db.execute(
            select(Organization).where(Organization.id == organization_id)
        )
        org = result.scalar_one_or_none()
        
        if not org:
            raise ValueError(f"Organization not found: {organization_id}")
        
        return org
    
    async def _log_verification_action(
        self,
        organization_id: uuid.UUID,
        action: str,
        user: User,
        notes: Optional[str] = None,
        old_status: Optional[str] = None,
        new_status: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log a verification action to the audit log."""
        # Build details dict for new_values (actual AuditLog field)
        details = {
            "action": action,
            "old_status": old_status,
            "new_status": new_status,
            "notes": notes,
            **(metadata or {}),
        }
        
        # Use actual AuditLog model fields (target_entity_type/target_entity_id, not resource_type/resource_id)
        audit_log = AuditLog(
            id=uuid.uuid4(),
            user_id=user.id,
            user_email=user.email,
            action=f"verification_{action}",
            target_entity_type="organization_verification",
            target_entity_id=str(organization_id),
            organization_id=organization_id,
            new_values=details,  # Use new_values instead of non-existent 'details' field
            ip_address=None,  # Not available in service layer
            user_agent=None,
        )
        
        self.db.add(audit_log)
        await self.db.commit()
