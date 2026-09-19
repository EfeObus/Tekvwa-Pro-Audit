"""
Tekvwa Pro Audit - Admin User Search Service

Cross-tenant user search service for Super Admin functionality.
Allows searching users across all organizations with advanced filters.

Security:
- Super Admin only access
- Full audit logging of searches
- No sensitive data exposure in search results

Features:
- Search by email, name, phone
- Filter by organization
- Filter by role (platform or organization)
- Filter by status (active/inactive, verified/unverified)
- Pagination support
- Sort by multiple fields
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, func, or_, select, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from app.models.user import User, UserRole, PlatformRole
from app.models.organization import Organization

logger = logging.getLogger(__name__)


class AdminUserSearchService:
    """
    Service for cross-tenant user search operations.
    
    Restricted to Super Admin role only.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def search_users(
        self,
        query: Optional[str] = None,
        organization_id: Optional[UUID] = None,
        platform_role: Optional[PlatformRole] = None,
        org_role: Optional[UserRole] = None,
        is_active: Optional[bool] = None,
        is_verified: Optional[bool] = None,
        is_platform_staff: Optional[bool] = None,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        Search users across all organizations with filters.
        
        Args:
            query: Search term for email, first_name, last_name, phone
            organization_id: Filter by specific organization
            platform_role: Filter by platform staff role
            org_role: Filter by organization user role
            is_active: Filter by active status
            is_verified: Filter by verification status
            is_platform_staff: Filter platform staff vs org users
            created_after: Filter users created after date
            created_before: Filter users created before date
            sort_by: Field to sort by
            sort_order: 'asc' or 'desc'
            page: Page number (1-indexed)
            page_size: Results per page (max 100)
            
        Returns:
            Dict with users list, total count, and pagination info
        """
        # Build base query with eager loading
        stmt = select(User).options(
            joinedload(User.organization)
        )
        
        # Apply filters
        conditions = []
        
        # Text search across multiple fields
        if query:
            search_term = f"%{query.lower()}%"
            conditions.append(
                or_(
                    func.lower(User.email).like(search_term),
                    func.lower(User.first_name).like(search_term),
                    func.lower(User.last_name).like(search_term),
                    func.lower(func.concat(User.first_name, ' ', User.last_name)).like(search_term),
                    User.phone_number.like(f"%{query}%") if query.replace('+', '').replace('-', '').replace(' ', '').isdigit() else False,
                )
            )
        
        # Organization filter
        if organization_id:
            conditions.append(User.organization_id == organization_id)
        
        # Platform role filter
        if platform_role:
            conditions.append(User.platform_role == platform_role)
            conditions.append(User.is_platform_staff == True)
        
        # Organization role filter
        if org_role:
            conditions.append(User.role == org_role)
            conditions.append(User.is_platform_staff == False)
        
        # Status filters
        if is_active is not None:
            conditions.append(User.is_active == is_active)
        
        if is_verified is not None:
            conditions.append(User.is_verified == is_verified)
        
        # Platform staff filter
        if is_platform_staff is not None:
            conditions.append(User.is_platform_staff == is_platform_staff)
        
        # Date range filters
        if created_after:
            conditions.append(User.created_at >= created_after)
        
        if created_before:
            conditions.append(User.created_at <= created_before)
        
        # Apply all conditions
        if conditions:
            stmt = stmt.where(and_(*conditions))
        
        # Get total count before pagination
        count_stmt = select(func.count()).select_from(User)
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        
        total_result = await self.db.execute(count_stmt)
        total_count = total_result.scalar() or 0
        
        # Apply sorting
        sort_column = self._get_sort_column(sort_by)
        if sort_order.lower() == "desc":
            stmt = stmt.order_by(desc(sort_column))
        else:
            stmt = stmt.order_by(asc(sort_column))
        
        # Apply pagination
        page_size = min(page_size, 100)  # Max 100 per page
        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)
        
        # Execute query
        result = await self.db.execute(stmt)
        users = result.unique().scalars().all()
        
        # Calculate pagination metadata
        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
        
        # Convert users to dicts
        user_dicts = [self._user_to_dict(user) for user in users if isinstance(user, User)]
        
        return {
            "users": user_dicts,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_count": total_count,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_previous": page > 1,
            }
        }
    
    async def get_user_details(self, user_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get detailed user information for Super Admin view.
        
        Args:
            user_id: UUID of the user to retrieve
            
        Returns:
            Detailed user dict or None if not found
        """
        stmt = select(User).options(
            joinedload(User.organization),
            selectinload(User.entity_access)
        ).where(User.id == user_id)
        
        result = await self.db.execute(stmt)
        user = result.unique().scalar_one_or_none()
        
        if not user:
            return None
        
        return self._user_to_detailed_dict(user)
    
    async def get_user_activity_summary(self, user_id: UUID) -> Dict[str, Any]:
        """
        Get user activity summary for Super Admin.
        
        Args:
            user_id: UUID of the user
            
        Returns:
            Activity summary dict
        """
        # Get the user first
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            return {"error": "User not found"}
        
        return {
            "user_id": str(user_id),
            "email": user.email,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_activity": user.updated_at.isoformat() if user.updated_at else None,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "email_verified_at": user.email_verified_at.isoformat() if user.email_verified_at else None,
        }
    
    async def get_organizations_for_filter(self) -> List[Dict[str, Any]]:
        """
        Get list of all organizations for filter dropdown.
        
        Returns:
            List of organization dicts with id, name, and user count
        """
        # Get organizations with user counts
        stmt = select(
            Organization.id,
            Organization.name,
            Organization.slug,
            func.count(User.id).label("user_count")
        ).outerjoin(
            User, User.organization_id == Organization.id
        ).group_by(
            Organization.id,
            Organization.name,
            Organization.slug
        ).order_by(Organization.name)
        
        result = await self.db.execute(stmt)
        rows = result.all()
        
        return [
            {
                "id": str(row.id),
                "name": row.name,
                "slug": row.slug,
                "user_count": row.user_count,
            }
            for row in rows
        ]
    
    async def get_user_stats(self) -> Dict[str, Any]:
        """
        Get platform-wide user statistics.
        
        Returns:
            Dict with various user counts and stats
        """
        # Total users
        total_stmt = select(func.count(User.id))
        total_result = await self.db.execute(total_stmt)
        total_users = total_result.scalar() or 0
        
        # Active users
        active_stmt = select(func.count(User.id)).where(User.is_active == True)
        active_result = await self.db.execute(active_stmt)
        active_users = active_result.scalar() or 0
        
        # Verified users
        verified_stmt = select(func.count(User.id)).where(User.is_verified == True)
        verified_result = await self.db.execute(verified_stmt)
        verified_users = verified_result.scalar() or 0
        
        # Platform staff count
        staff_stmt = select(func.count(User.id)).where(User.is_platform_staff == True)
        staff_result = await self.db.execute(staff_stmt)
        platform_staff = staff_result.scalar() or 0
        
        # Organization users
        org_users = total_users - platform_staff
        
        # Users by platform role
        platform_role_stmt = select(
            User.platform_role,
            func.count(User.id)
        ).where(
            User.is_platform_staff == True,
            User.platform_role.isnot(None)
        ).group_by(User.platform_role)
        
        platform_role_result = await self.db.execute(platform_role_stmt)
        users_by_platform_role = {
            str(row[0].value) if row[0] else "unknown": row[1]
            for row in platform_role_result.all()
        }
        
        # Users by organization role
        org_role_stmt = select(
            User.role,
            func.count(User.id)
        ).where(
            User.is_platform_staff == False,
            User.role.isnot(None)
        ).group_by(User.role)
        
        org_role_result = await self.db.execute(org_role_stmt)
        users_by_org_role = {
            str(row[0].value) if row[0] else "unknown": row[1]
            for row in org_role_result.all()
        }
        
        # Recent signups (last 7 days)
        from datetime import timedelta
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        recent_stmt = select(func.count(User.id)).where(User.created_at >= seven_days_ago)
        recent_result = await self.db.execute(recent_stmt)
        recent_signups = recent_result.scalar() or 0
        
        return {
            "total_users": total_users,
            "active_users": active_users,
            "inactive_users": total_users - active_users,
            "verified_users": verified_users,
            "unverified_users": total_users - verified_users,
            "platform_staff": platform_staff,
            "organization_users": org_users,
            "users_by_platform_role": users_by_platform_role,
            "users_by_org_role": users_by_org_role,
            "recent_signups_7d": recent_signups,
        }
    
    def _get_sort_column(self, sort_by: str):
        """Map sort field name to column."""
        sort_columns = {
            "created_at": User.created_at,
            "updated_at": User.updated_at,
            "email": User.email,
            "first_name": User.first_name,
            "last_name": User.last_name,
            "is_active": User.is_active,
            "is_verified": User.is_verified,
        }
        return sort_columns.get(sort_by, User.created_at)
    
    def _user_to_dict(self, user: User) -> Dict[str, Any]:
        """Convert user to dict for search results."""
        # Access organization
        org_data = None
        if user.organization:
            org_data = {
                "id": str(user.organization.id),
                "name": user.organization.name,
                "slug": user.organization.slug,
            }
        
        return {
            "id": str(user.id),
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": user.full_name,
            "phone_number": user.phone_number,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "is_platform_staff": user.is_platform_staff,
            "platform_role": user.platform_role.value if user.platform_role else None,
            "role": user.role.value if user.role else None,
            "organization": org_data,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        }
    
    def _user_to_detailed_dict(self, user: User) -> Dict[str, Any]:
        """Convert user to detailed dict for user detail view."""
        base_dict = self._user_to_dict(user)
        
        # Add detailed fields
        base_dict.update({
            "is_superuser": user.is_superuser,
            "must_reset_password": user.must_reset_password,
            "is_invited_user": user.is_invited_user,
            "can_be_impersonated": user.can_be_impersonated,
            "impersonation_expires_at": user.impersonation_expires_at.isoformat() if user.impersonation_expires_at else None,
            "impersonation_granted_at": user.impersonation_granted_at.isoformat() if user.impersonation_granted_at else None,
            "email_verified_at": user.email_verified_at.isoformat() if user.email_verified_at else None,
            "email_verification_sent_at": user.email_verification_sent_at.isoformat() if user.email_verification_sent_at else None,
            "staff_notes": user.staff_notes if user.is_platform_staff else None,
            "onboarded_by_id": str(user.onboarded_by_id) if user.onboarded_by_id else None,
            "entity_access_count": len(user.entity_access) if user.entity_access else 0,
        })
        
        return base_dict
