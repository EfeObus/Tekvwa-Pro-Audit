"""
TekVwarho ProAudit - Audit Trail Service

Comprehensive audit logging for compliance.
"""

import uuid
from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Optional, Union, Tuple
from dataclasses import dataclass

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_consolidated import AuditLog, AuditAction
from app.models.user import User


@dataclass
class AuditEntry:
    """Audit log entry data."""
    entity_type: str
    entity_id: str
    action: str
    user_id: Optional[str] = None
    changes: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None


class AuditService:
    """Service for managing audit trail and compliance logging."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def log_action(
        self,
        business_entity_id: uuid.UUID,
        entity_type: str,
        entity_id: str,
        action: AuditAction,
        user_id: Optional[uuid.UUID] = None,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditLog:
        """
        Log an audit action.
        
        Args:
            business_entity_id: The business entity this action relates to
            entity_type: Type of entity (e.g., 'transaction', 'invoice')
            entity_id: ID of the affected entity
            action: Type of action performed
            user_id: ID of user who performed the action
            old_values: Previous values (for updates)
            new_values: New values (for creates/updates)
            ip_address: Client IP address
            user_agent: Client user agent
        
        Returns:
            Created AuditLog record
        """
        # Calculate changes for updates
        changes = None
        if action == AuditAction.UPDATE and old_values and new_values:
            changes = self._calculate_changes(old_values, new_values)
        
        # Fetch user email if user_id is provided
        user_email = "info@tekvwa.org"  # Default for system actions
        if user_id:
            user_result = await self.db.execute(
                select(User).where(User.id == user_id)
            )
            user = user_result.scalar_one_or_none()
            if user:
                user_email = user.email
        
        audit_log = AuditLog(
            entity_id=business_entity_id,
            target_entity_type=entity_type,
            target_entity_id=entity_id,
            action=action.value if hasattr(action, 'value') else str(action),  # Convert enum to string
            user_id=user_id,
            user_email=user_email,
            table_name=entity_type,  # Required field - use entity_type
            record_id=uuid.UUID(entity_id) if entity_id and len(entity_id) == 36 else uuid.uuid4(),  # Required field
            old_values=old_values,
            new_values=new_values,
            changes=changes,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        
        self.db.add(audit_log)
        await self.db.flush()
        await self.db.commit()  # Ensure the audit log is persisted
        
        return audit_log
    
    def _calculate_changes(
        self,
        old_values: Dict[str, Any],
        new_values: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Calculate what changed between old and new values."""
        changes = {}
        
        all_keys = set(old_values.keys()) | set(new_values.keys())
        
        for key in all_keys:
            old_val = old_values.get(key)
            new_val = new_values.get(key)
            
            if old_val != new_val:
                changes[key] = {
                    "old": old_val,
                    "new": new_val,
                }
        
        return changes
    
    async def get_audit_logs(
        self,
        entity_id: uuid.UUID,
        target_entity_type: Optional[str] = None,
        target_entity_id: Optional[str] = None,
        action: Optional[AuditAction] = None,
        user_id: Optional[uuid.UUID] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        skip: int = 0,
        limit: int = 100,
        return_total: bool = False,
    ) -> Union[List[AuditLog], Tuple[List[AuditLog], int]]:
        """
        Get audit logs with optional filtering.
        
        Args:
            entity_id: Business entity ID
            target_entity_type: Filter by entity type
            target_entity_id: Filter by specific entity
            action: Filter by action type
            user_id: Filter by user
            start_date: Filter by date range start
            end_date: Filter by date range end
            skip: Pagination offset
            limit: Pagination limit
            return_total: If True, return (logs, total_count) tuple
        
        Returns:
            List of matching audit logs, or tuple of (logs, total_count) if return_total=True
        """
        # Build base filter conditions
        conditions = [AuditLog.entity_id == entity_id]
        
        if target_entity_type:
            conditions.append(AuditLog.target_entity_type == target_entity_type)
        
        if target_entity_id:
            conditions.append(AuditLog.target_entity_id == target_entity_id)
        
        if action:
            conditions.append(AuditLog.action == action)
        
        if user_id:
            conditions.append(AuditLog.user_id == user_id)
        
        if start_date:
            conditions.append(func.date(AuditLog.created_at) >= start_date)
        
        if end_date:
            conditions.append(func.date(AuditLog.created_at) <= end_date)
        
        # Get total count if requested
        total = 0
        if return_total:
            count_query = select(func.count(AuditLog.id)).where(*conditions)
            count_result = await self.db.execute(count_query)
            total = count_result.scalar() or 0
        
        # Get paginated results
        query = select(AuditLog).where(*conditions)
        query = query.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit)
        
        result = await self.db.execute(query)
        logs = list(result.scalars().all())
        
        if return_total:
            return logs, total
        return logs
    
    async def get_entity_history(
        self,
        entity_id: uuid.UUID,
        target_entity_type: str,
        target_entity_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Get complete history of changes for a specific entity.
        
        Returns chronological list of all changes made to the entity.
        """
        logs = await self.get_audit_logs(
            entity_id=entity_id,
            target_entity_type=target_entity_type,
            target_entity_id=target_entity_id,
            limit=1000,
        )
        
        history = []
        for log in reversed(logs):  # Oldest first
            entry = {
                "timestamp": log.created_at.isoformat(),
                "action": log.action if isinstance(log.action, str) else log.action.value,
                "user_id": str(log.user_id) if log.user_id else None,
            }
            
            if log.action == AuditAction.CREATE:
                entry["values"] = log.new_values
            elif log.action == AuditAction.UPDATE:
                entry["changes"] = log.changes
            elif log.action == AuditAction.DELETE:
                entry["deleted_values"] = log.old_values
            
            history.append(entry)
        
        return history
    
    async def get_user_activity(
        self,
        entity_id: uuid.UUID,
        user_id: uuid.UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Get activity summary for a specific user."""
        query = select(
            AuditLog.action,
            AuditLog.target_entity_type,
            func.count(AuditLog.id).label("count"),
        ).where(
            AuditLog.entity_id == entity_id
        ).where(
            AuditLog.user_id == user_id
        ).group_by(
            AuditLog.action,
            AuditLog.target_entity_type,
        )
        
        if start_date:
            query = query.where(func.date(AuditLog.created_at) >= start_date)
        
        if end_date:
            query = query.where(func.date(AuditLog.created_at) <= end_date)
        
        result = await self.db.execute(query)
        
        activity = {}
        for row in result:
            action_name = row.action if isinstance(row.action, str) else row.action.value
            if action_name not in activity:
                activity[action_name] = {}
            activity[action_name][row.target_entity_type] = row.count
        
        return {
            "user_id": str(user_id),
            "entity_id": str(entity_id),
            "period": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None,
            },
            "activity": activity,
        }
    
    async def get_audit_summary(
        self,
        entity_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """Generate audit summary report."""
        # Count by action type
        action_counts = await self.db.execute(
            select(
                AuditLog.action,
                func.count(AuditLog.id).label("count"),
            )
            .where(AuditLog.entity_id == entity_id)
            .where(func.date(AuditLog.created_at) >= start_date)
            .where(func.date(AuditLog.created_at) <= end_date)
            .group_by(AuditLog.action)
        )
        
        by_action = {(row.action if isinstance(row.action, str) else row.action.value): row.count for row in action_counts}
        
        # Count by entity type
        entity_counts = await self.db.execute(
            select(
                AuditLog.target_entity_type,
                func.count(AuditLog.id).label("count"),
            )
            .where(AuditLog.entity_id == entity_id)
            .where(func.date(AuditLog.created_at) >= start_date)
            .where(func.date(AuditLog.created_at) <= end_date)
            .group_by(AuditLog.target_entity_type)
        )
        
        by_entity_type = {row.target_entity_type: row.count for row in entity_counts}
        
        # Count by user
        user_counts = await self.db.execute(
            select(
                AuditLog.user_id,
                func.count(AuditLog.id).label("count"),
            )
            .where(AuditLog.entity_id == entity_id)
            .where(func.date(AuditLog.created_at) >= start_date)
            .where(func.date(AuditLog.created_at) <= end_date)
            .group_by(AuditLog.user_id)
        )
        
        by_user = {
            str(row.user_id) if row.user_id else "system": row.count 
            for row in user_counts
        }
        
        # Total count
        total = await self.db.scalar(
            select(func.count(AuditLog.id))
            .where(AuditLog.entity_id == entity_id)
            .where(func.date(AuditLog.created_at) >= start_date)
            .where(func.date(AuditLog.created_at) <= end_date)
        ) or 0
        
        return {
            "entity_id": str(entity_id),
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "generated_at": datetime.utcnow().isoformat(),
            "total_events": total,
            "by_action": by_action,
            "by_entity_type": by_entity_type,
            "by_user": by_user,
        }
    
    # ===========================================
    # COMPLIANCE HELPERS
    # ===========================================
    
    async def log_login(
        self,
        user_id: uuid.UUID,
        entity_id: Optional[uuid.UUID],
        ip_address: Optional[str] = None,
        success: bool = True,
    ) -> AuditLog:
        """Log user login attempt."""
        return await self.log_action(
            business_entity_id=entity_id or uuid.UUID(int=0),
            entity_type="user",
            entity_id=str(user_id),
            action=AuditAction.LOGIN if success else AuditAction.LOGIN_FAILED,
            user_id=user_id,
            ip_address=ip_address,
            new_values={"success": success},
        )
    
    async def log_nrs_submission(
        self,
        entity_id: uuid.UUID,
        invoice_id: uuid.UUID,
        user_id: Optional[uuid.UUID],
        irn: str,
        success: bool = True,
        error: Optional[str] = None,
    ) -> AuditLog:
        """Log NRS e-invoice submission."""
        return await self.log_action(
            business_entity_id=entity_id,
            entity_type="invoice",
            entity_id=str(invoice_id),
            action=AuditAction.NRS_SUBMIT,
            user_id=user_id,
            new_values={
                "irn": irn,
                "success": success,
                "error": error,
            },
        )
    
    async def log_document_upload(
        self,
        entity_id: uuid.UUID,
        user_id: uuid.UUID,
        file_id: str,
        filename: str,
        file_type: str,
    ) -> AuditLog:
        """Log document upload."""
        return await self.log_action(
            business_entity_id=entity_id,
            entity_type="document",
            entity_id=file_id,
            action=AuditAction.UPLOAD,
            user_id=user_id,
            new_values={
                "filename": filename,
                "file_type": file_type,
            },
        )
    
    async def log_export(
        self,
        entity_id: uuid.UUID,
        user_id: uuid.UUID,
        export_type: str,
        parameters: Dict[str, Any],
    ) -> AuditLog:
        """Log data export."""
        return await self.log_action(
            business_entity_id=entity_id,
            entity_type="export",
            entity_id=export_type,
            action=AuditAction.EXPORT,
            user_id=user_id,
            new_values=parameters,
        )
