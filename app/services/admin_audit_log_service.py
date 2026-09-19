"""
Tekvwa Pro Audit - Admin Global Audit Log Service

Service for platform-wide audit log viewing, searching, and analytics.
Cross-tenant visibility for Super Admin users.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
from enum import Enum

from sqlalchemy import select, func, and_, or_, desc, asc, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.audit_consolidated import AuditLog, AuditAction
from app.models.organization import Organization
from app.models.user import User

logger = logging.getLogger(__name__)


class AuditLogSeverity(str, Enum):
    """Severity levels for audit log entries."""
    CRITICAL = "critical"     # Security breaches, unauthorized access
    HIGH = "high"            # Data modifications, deletions
    MEDIUM = "medium"        # Configuration changes
    LOW = "low"              # Read operations, views
    INFO = "info"            # Login, logout, general activity


class AdminAuditLogService:
    """Service for platform-wide audit log management."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        
        # Define action severity mappings
        self.action_severity = {
            # Critical - Security related
            "login_failed": AuditLogSeverity.CRITICAL,
            "unauthorized_access": AuditLogSeverity.CRITICAL,
            "permission_denied": AuditLogSeverity.CRITICAL,
            "password_reset": AuditLogSeverity.CRITICAL,
            "account_locked": AuditLogSeverity.CRITICAL,
            "suspicious_activity": AuditLogSeverity.CRITICAL,
            
            # High - Data modifications
            "delete": AuditLogSeverity.HIGH,
            "bulk_delete": AuditLogSeverity.HIGH,
            "data_export": AuditLogSeverity.HIGH,
            "verification_reject": AuditLogSeverity.HIGH,
            "emergency_suspend": AuditLogSeverity.HIGH,
            "emergency_action": AuditLogSeverity.HIGH,
            
            # Medium - Configuration changes
            "create": AuditLogSeverity.MEDIUM,
            "update": AuditLogSeverity.MEDIUM,
            "verification_approve": AuditLogSeverity.MEDIUM,
            "verification_start_review": AuditLogSeverity.MEDIUM,
            "feature_toggle": AuditLogSeverity.MEDIUM,
            "settings_change": AuditLogSeverity.MEDIUM,
            
            # Low - Read operations
            "view": AuditLogSeverity.LOW,
            "read": AuditLogSeverity.LOW,
            "search": AuditLogSeverity.LOW,
            "list": AuditLogSeverity.LOW,
            
            # Info - General activity
            "login": AuditLogSeverity.INFO,
            "logout": AuditLogSeverity.INFO,
            "session_start": AuditLogSeverity.INFO,
            "session_end": AuditLogSeverity.INFO,
        }
    
    def _get_action_severity(self, action: str) -> AuditLogSeverity:
        """Get severity level for an action."""
        action_lower = action.lower() if action else ""
        return self.action_severity.get(action_lower, AuditLogSeverity.INFO)
    
    async def get_global_audit_logs(
        self,
        organization_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        user_email: Optional[str] = None,
        action: Optional[str] = None,
        action_contains: Optional[str] = None,
        target_entity_type: Optional[str] = None,
        severity: Optional[AuditLogSeverity] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        ip_address: Optional[str] = None,
        search_query: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Search audit logs across all organizations.
        
        Args:
            organization_id: Filter by organization
            user_id: Filter by user ID
            user_email: Filter by user email (partial match)
            action: Filter by exact action
            action_contains: Filter by action containing string
            target_entity_type: Filter by entity type
            severity: Filter by severity level
            start_date: Filter from date
            end_date: Filter to date
            ip_address: Filter by IP address
            search_query: Full-text search across multiple fields
            sort_by: Sort field
            sort_order: Sort order (asc/desc)
            page: Page number
            page_size: Results per page
            
        Returns:
            Tuple of (logs list, total count)
        """
        conditions = []
        
        # Organization filter
        if organization_id:
            conditions.append(AuditLog.organization_id == organization_id)
        
        # User filters
        if user_id:
            conditions.append(AuditLog.user_id == user_id)
        
        if user_email:
            conditions.append(AuditLog.user_email.ilike(f"%{user_email}%"))
        
        # Action filters
        if action:
            conditions.append(AuditLog.action == action)
        
        if action_contains:
            conditions.append(AuditLog.action.ilike(f"%{action_contains}%"))
        
        # Entity type filter
        if target_entity_type:
            conditions.append(AuditLog.target_entity_type == target_entity_type)
        
        # Severity filter - filter by action patterns
        if severity:
            severity_actions = [
                k for k, v in self.action_severity.items() 
                if v == severity
            ]
            if severity_actions:
                conditions.append(
                    or_(*[AuditLog.action.ilike(f"%{a}%") for a in severity_actions])
                )
        
        # Date range filters
        if start_date:
            conditions.append(func.date(AuditLog.created_at) >= start_date)
        
        if end_date:
            conditions.append(func.date(AuditLog.created_at) <= end_date)
        
        # IP address filter
        if ip_address:
            conditions.append(AuditLog.ip_address.ilike(f"%{ip_address}%"))
        
        # Full-text search
        if search_query:
            search_pattern = f"%{search_query}%"
            conditions.append(
                or_(
                    AuditLog.user_email.ilike(search_pattern),
                    AuditLog.action.ilike(search_pattern),
                    AuditLog.target_entity_type.ilike(search_pattern),
                    AuditLog.target_entity_id.ilike(search_pattern),
                    AuditLog.description.ilike(search_pattern) if hasattr(AuditLog, 'description') else False,
                )
            )
        
        # Count total
        count_query = select(func.count(AuditLog.id))
        if conditions:
            count_query = count_query.where(and_(*conditions))
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0
        
        # Build main query
        query = select(AuditLog)
        if conditions:
            query = query.where(and_(*conditions))
        
        # Apply sorting
        sort_column = getattr(AuditLog, sort_by, AuditLog.created_at)
        if sort_order.lower() == "asc":
            query = query.order_by(asc(sort_column))
        else:
            query = query.order_by(desc(sort_column))
        
        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)
        
        result = await self.db.execute(query)
        logs = result.scalars().all()
        
        # Fetch organization names for context
        org_ids = {log.organization_id for log in logs if log.organization_id}
        org_names = {}
        if org_ids:
            org_query = select(Organization.id, Organization.name).where(
                Organization.id.in_(org_ids)
            )
            org_result = await self.db.execute(org_query)
            org_names = {str(row.id): row.name for row in org_result.all()}
        
        # Format results
        formatted_logs = []
        for log in logs:
            # Handle ip_address which may be an IPv4Address/IPv6Address object
            ip_addr = log.ip_address
            if ip_addr is not None:
                ip_addr = str(ip_addr)
            
            formatted_logs.append({
                "id": str(log.id),
                "organization_id": str(log.organization_id) if log.organization_id else None,
                "organization_name": org_names.get(str(log.organization_id), "System"),
                "user_id": str(log.user_id) if log.user_id else None,
                "user_email": log.user_email,
                "action": log.action,
                "severity": self._get_action_severity(log.action).value,
                "target_entity_type": log.target_entity_type,
                "target_entity_id": log.target_entity_id,
                "table_name": log.table_name,
                "record_id": str(log.record_id) if log.record_id else None,
                "old_values": log.old_values,
                "new_values": log.new_values,
                "changes": log.changes,
                "ip_address": ip_addr,
                "user_agent": log.user_agent,
                "description": getattr(log, 'description', None),
                "created_at": log.created_at.isoformat() if log.created_at else None,
            })
        
        return formatted_logs, total
    
    async def get_audit_log_detail(self, log_id: UUID) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific audit log entry."""
        query = select(AuditLog).where(AuditLog.id == log_id)
        result = await self.db.execute(query)
        log = result.scalar_one_or_none()
        
        if not log:
            return None
        
        # Get organization name
        org_name = "System"
        if log.organization_id:
            org_query = select(Organization.name).where(
                Organization.id == log.organization_id
            )
            org_result = await self.db.execute(org_query)
            org_name = org_result.scalar() or "Unknown"
        
        # Get user details
        user_details = None
        if log.user_id:
            user_query = select(User).where(User.id == log.user_id)
            user_result = await self.db.execute(user_query)
            user = user_result.scalar_one_or_none()
            if user:
                user_details = {
                    "id": str(user.id),
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "is_platform_staff": user.is_platform_staff,
                    "platform_role": user.platform_role.value if user.platform_role else None,
                }
        
        # Handle ip_address which may be an IPv4Address/IPv6Address object
        ip_addr = log.ip_address
        if ip_addr is not None:
            ip_addr = str(ip_addr)
        
        return {
            "id": str(log.id),
            "organization_id": str(log.organization_id) if log.organization_id else None,
            "organization_name": org_name,
            "user_id": str(log.user_id) if log.user_id else None,
            "user_email": log.user_email,
            "user_details": user_details,
            "action": log.action,
            "severity": self._get_action_severity(log.action).value,
            "target_entity_type": log.target_entity_type,
            "target_entity_id": log.target_entity_id,
            "table_name": log.table_name,
            "record_id": str(log.record_id) if log.record_id else None,
            "old_values": log.old_values,
            "new_values": log.new_values,
            "changes": log.changes,
            "ip_address": ip_addr,
            "user_agent": log.user_agent,
            "device_fingerprint": log.device_fingerprint,
            "session_id": log.session_id,
            "geo_location": getattr(log, 'geo_location', None),
            "description": getattr(log, 'description', None),
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
    
    async def get_audit_statistics(
        self,
        organization_id: Optional[UUID] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Get audit log statistics for platform or specific organization."""
        conditions = []
        
        if organization_id:
            conditions.append(AuditLog.organization_id == organization_id)
        
        if not start_date:
            start_date = date.today() - timedelta(days=30)
        if not end_date:
            end_date = date.today()
        
        conditions.append(func.date(AuditLog.created_at) >= start_date)
        conditions.append(func.date(AuditLog.created_at) <= end_date)
        
        base_filter = and_(*conditions) if conditions else True
        
        # Total count
        total_query = select(func.count(AuditLog.id)).where(base_filter)
        total_result = await self.db.execute(total_query)
        total_logs = total_result.scalar() or 0
        
        # Unique users
        users_query = select(func.count(func.distinct(AuditLog.user_id))).where(base_filter)
        users_result = await self.db.execute(users_query)
        unique_users = users_result.scalar() or 0
        
        # Unique organizations
        orgs_query = select(func.count(func.distinct(AuditLog.organization_id))).where(base_filter)
        orgs_result = await self.db.execute(orgs_query)
        unique_orgs = orgs_result.scalar() or 0
        
        # Actions by type
        actions_query = select(
            AuditLog.action,
            func.count(AuditLog.id).label("count")
        ).where(base_filter).group_by(AuditLog.action).order_by(desc("count")).limit(20)
        actions_result = await self.db.execute(actions_query)
        actions_breakdown = [
            {"action": row.action, "count": row.count}
            for row in actions_result.all()
        ]
        
        # Entity types breakdown
        entities_query = select(
            AuditLog.target_entity_type,
            func.count(AuditLog.id).label("count")
        ).where(
            and_(base_filter, AuditLog.target_entity_type.isnot(None))
        ).group_by(AuditLog.target_entity_type).order_by(desc("count")).limit(20)
        entities_result = await self.db.execute(entities_query)
        entities_breakdown = [
            {"entity_type": row.target_entity_type, "count": row.count}
            for row in entities_result.all()
        ]
        
        # Daily activity (last 30 days)
        daily_query = select(
            func.date(AuditLog.created_at).label("date"),
            func.count(AuditLog.id).label("count")
        ).where(base_filter).group_by(func.date(AuditLog.created_at)).order_by("date")
        daily_result = await self.db.execute(daily_query)
        daily_activity = [
            {"date": str(row.date), "count": row.count}
            for row in daily_result.all()
        ]
        
        # Top organizations by activity
        top_orgs_query = select(
            AuditLog.organization_id,
            func.count(AuditLog.id).label("count")
        ).where(
            and_(base_filter, AuditLog.organization_id.isnot(None))
        ).group_by(AuditLog.organization_id).order_by(desc("count")).limit(10)
        top_orgs_result = await self.db.execute(top_orgs_query)
        top_org_ids = [row.organization_id for row in top_orgs_result.all()]
        
        # Get organization names
        top_orgs = []
        if top_org_ids:
            org_names_query = select(Organization.id, Organization.name).where(
                Organization.id.in_(top_org_ids)
            )
            org_names_result = await self.db.execute(org_names_query)
            org_names = {row.id: row.name for row in org_names_result.all()}
            
            # Re-run counts with names
            for row in (await self.db.execute(top_orgs_query)).all():
                top_orgs.append({
                    "organization_id": str(row.organization_id),
                    "organization_name": org_names.get(row.organization_id, "Unknown"),
                    "count": row.count
                })
        
        # Severity breakdown
        severity_counts = {s.value: 0 for s in AuditLogSeverity}
        for action_row in actions_breakdown:
            severity = self._get_action_severity(action_row["action"])
            severity_counts[severity.value] += action_row["count"]
        
        return {
            "period": {
                "start_date": str(start_date),
                "end_date": str(end_date),
            },
            "total_logs": total_logs,
            "unique_users": unique_users,
            "unique_organizations": unique_orgs,
            "actions_breakdown": actions_breakdown,
            "entities_breakdown": entities_breakdown,
            "severity_breakdown": [
                {"severity": k, "count": v} for k, v in severity_counts.items()
            ],
            "daily_activity": daily_activity,
            "top_organizations": top_orgs,
        }
    
    async def get_distinct_actions(self) -> List[str]:
        """Get all distinct action types in the system."""
        query = select(func.distinct(AuditLog.action)).order_by(AuditLog.action)
        result = await self.db.execute(query)
        return [row[0] for row in result.all() if row[0]]
    
    async def get_distinct_entity_types(self) -> List[str]:
        """Get all distinct entity types in the system."""
        query = select(func.distinct(AuditLog.target_entity_type)).where(
            AuditLog.target_entity_type.isnot(None)
        ).order_by(AuditLog.target_entity_type)
        result = await self.db.execute(query)
        return [row[0] for row in result.all() if row[0]]
    
    async def get_user_activity_summary(
        self,
        user_id: UUID,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Get activity summary for a specific user."""
        start_date = date.today() - timedelta(days=days)
        
        # Get user info
        user_query = select(User).where(User.id == user_id)
        user_result = await self.db.execute(user_query)
        user = user_result.scalar_one_or_none()
        
        if not user:
            return {"error": "User not found"}
        
        # Get audit logs for this user
        logs_query = select(AuditLog).where(
            and_(
                AuditLog.user_id == user_id,
                func.date(AuditLog.created_at) >= start_date
            )
        ).order_by(desc(AuditLog.created_at))
        logs_result = await self.db.execute(logs_query)
        logs = logs_result.scalars().all()
        
        # Actions breakdown
        action_counts = {}
        for log in logs:
            action = log.action or "unknown"
            action_counts[action] = action_counts.get(action, 0) + 1
        
        # IP addresses used - convert to strings to handle IPv4Address/IPv6Address objects
        ip_addresses = list(set(str(log.ip_address) for log in logs if log.ip_address))
        
        # Organizations accessed
        org_ids = list(set(log.organization_id for log in logs if log.organization_id))
        org_names = {}
        if org_ids:
            org_query = select(Organization.id, Organization.name).where(
                Organization.id.in_(org_ids)
            )
            org_result = await self.db.execute(org_query)
            org_names = {str(row.id): row.name for row in org_result.all()}
        
        return {
            "user": {
                "id": str(user.id),
                "email": user.email,
                "name": f"{user.first_name} {user.last_name}".strip(),
                "is_platform_staff": user.is_platform_staff,
                "platform_role": user.platform_role.value if user.platform_role else None,
            },
            "period_days": days,
            "total_activities": len(logs),
            "actions_breakdown": [
                {"action": k, "count": v} for k, v in sorted(
                    action_counts.items(), key=lambda x: x[1], reverse=True
                )
            ],
            "ip_addresses": ip_addresses,
            "organizations_accessed": [
                {"id": str(oid), "name": org_names.get(str(oid), "Unknown")}
                for oid in org_ids
            ],
            "recent_activities": [
                {
                    "id": str(log.id),
                    "action": log.action,
                    "target_entity_type": log.target_entity_type,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                }
                for log in logs[:20]
            ],
        }
