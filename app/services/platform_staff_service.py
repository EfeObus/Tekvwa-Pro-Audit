"""
Tekvwa Pro Audit - Platform Staff Management Service

Service for Super Admin to create, manage, and configure platform staff accounts.

Platform Staff Roles:
- SUPER_ADMIN: Full root access (only existing Super Admin can create)
- ADMIN: Operational access, organization verification
- IT_DEVELOPER: Backend and infrastructure access
- CUSTOMER_SERVICE: View-only or impersonation access
- MARKETING: Analytics and communication dashboards
"""

import logging
import secrets
import string
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from passlib.context import CryptContext
from sqlalchemy import func, select, and_, or_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User, PlatformRole, UserRole
from app.models.audit_consolidated import AuditLog

logger = logging.getLogger(__name__)

# Password hashing context
# Note: bcrypt 4.2+ requires truncate_error=False to avoid errors
pwd_context = CryptContext(
    schemes=["bcrypt"], 
    deprecated="auto",
    bcrypt__truncate_error=False
)


class PlatformStaffService:
    """Service for managing platform staff accounts."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def _generate_secure_password(self, length: int = 16) -> str:
        """Generate a secure random password."""
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        # Ensure at least one of each required character type
        password = [
            secrets.choice(string.ascii_uppercase),
            secrets.choice(string.ascii_lowercase),
            secrets.choice(string.digits),
            secrets.choice("!@#$%^&*"),
        ]
        # Fill the rest randomly
        password.extend(secrets.choice(alphabet) for _ in range(length - 4))
        # Shuffle to randomize position
        secrets.SystemRandom().shuffle(password)
        return ''.join(password)
    
    def _hash_password(self, password: str) -> str:
        """Hash a password using bcrypt."""
        return pwd_context.hash(password)
    
    def _verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return pwd_context.verify(plain_password, hashed_password)
    
    async def create_platform_staff(
        self,
        email: str,
        first_name: str,
        last_name: str,
        platform_role: PlatformRole,
        created_by: User,
        phone_number: Optional[str] = None,
        staff_notes: Optional[str] = None,
        send_welcome_email: bool = True,
        custom_password: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new platform staff account.
        
        Args:
            email: Staff email address
            first_name: First name
            last_name: Last name
            platform_role: Platform role to assign
            created_by: The Super Admin creating this account
            phone_number: Optional phone number
            staff_notes: Optional internal notes
            send_welcome_email: Whether to send welcome email
            custom_password: Optional custom password (if not set, generates secure random)
            
        Returns:
            Dict with created user info and temporary password (if generated)
        """
        # Validate creator is Super Admin
        if not created_by.is_platform_staff or created_by.platform_role != PlatformRole.SUPER_ADMIN:
            raise PermissionError("Only Super Admin can create platform staff accounts")
        
        # Check if email already exists
        existing = await self.db.execute(
            select(User).where(func.lower(User.email) == email.lower())
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Email {email} is already registered")
        
        # Only Super Admin can create another Super Admin
        if platform_role == PlatformRole.SUPER_ADMIN:
            # Additional verification - count existing Super Admins
            count_result = await self.db.execute(
                select(func.count(User.id)).where(
                    and_(
                        User.is_platform_staff == True,
                        User.platform_role == PlatformRole.SUPER_ADMIN
                    )
                )
            )
            super_admin_count = count_result.scalar() or 0
            if super_admin_count >= 3:
                raise ValueError("Maximum of 3 Super Admin accounts allowed")
        
        # Generate or use provided password
        temp_password = custom_password or self._generate_secure_password()
        hashed_password = self._hash_password(temp_password)
        
        # Create the staff user
        new_staff = User(
            email=email.lower().strip(),
            hashed_password=hashed_password,
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            phone_number=phone_number.strip() if phone_number else None,
            organization_id=None,  # Platform staff have no organization
            role=UserRole.VIEWER,  # Default role (not used for platform staff)
            is_platform_staff=True,
            platform_role=platform_role,
            onboarded_by_id=created_by.id,
            staff_notes=staff_notes,
            is_active=True,
            is_verified=True,  # Platform staff are auto-verified
            must_reset_password=True if not custom_password else False,  # Force reset if generated
        )
        
        self.db.add(new_staff)
        await self.db.flush()
        
        # Create audit log
        audit_log = AuditLog(
            user_id=created_by.id,
            user_email=created_by.email,
            action="create_platform_staff",
            table_name="users",
            record_id=new_staff.id,
            target_entity_type="platform_staff",
            target_entity_id=str(new_staff.id),
            new_values={
                "email": new_staff.email,
                "platform_role": platform_role.value,
                "first_name": first_name,
                "last_name": last_name,
            },
            description=f"Created platform staff account: {email} with role {platform_role.value}",
        )
        self.db.add(audit_log)
        
        await self.db.commit()
        await self.db.refresh(new_staff)
        
        logger.info(f"Super Admin {created_by.email} created platform staff: {email} ({platform_role.value})")
        
        result = {
            "success": True,
            "user": self._staff_to_dict(new_staff),
            "created_by": created_by.email,
        }
        
        # Include temporary password only if it was generated
        if not custom_password:
            result["temporary_password"] = temp_password
            result["must_reset_password"] = True
        
        return result
    
    async def list_platform_staff(
        self,
        role_filter: Optional[PlatformRole] = None,
        is_active: Optional[bool] = None,
        query: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        List all platform staff accounts with filters.
        
        Args:
            role_filter: Filter by platform role
            is_active: Filter by active status
            query: Search query (email, name)
            sort_by: Sort field
            sort_order: Sort direction (asc/desc)
            page: Page number
            page_size: Results per page
            
        Returns:
            Paginated list of platform staff
        """
        # Base query
        stmt = select(User).where(User.is_platform_staff == True)
        count_stmt = select(func.count(User.id)).where(User.is_platform_staff == True)
        
        # Apply filters
        if role_filter:
            stmt = stmt.where(User.platform_role == role_filter)
            count_stmt = count_stmt.where(User.platform_role == role_filter)
        
        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)
            count_stmt = count_stmt.where(User.is_active == is_active)
        
        if query:
            search_term = f"%{query.lower()}%"
            search_filter = or_(
                func.lower(User.email).like(search_term),
                func.lower(User.first_name).like(search_term),
                func.lower(User.last_name).like(search_term),
                func.lower(func.concat(User.first_name, ' ', User.last_name)).like(search_term),
            )
            stmt = stmt.where(search_filter)
            count_stmt = count_stmt.where(search_filter)
        
        # Get total count
        total_result = await self.db.execute(count_stmt)
        total_count = total_result.scalar() or 0
        
        # Apply sorting
        sort_column = getattr(User, sort_by, User.created_at)
        if sort_order.lower() == "desc":
            stmt = stmt.order_by(desc(sort_column))
        else:
            stmt = stmt.order_by(asc(sort_column))
        
        # Apply pagination
        page_size = min(page_size, 100)
        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)
        
        # Execute query
        result = await self.db.execute(stmt)
        staff_list = result.scalars().all()
        
        # Calculate pagination
        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
        
        return {
            "staff": [self._staff_to_dict(s) for s in staff_list],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_count": total_count,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_previous": page > 1,
            }
        }
    
    async def get_staff_details(self, staff_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a platform staff member.
        
        Args:
            staff_id: UUID of the staff member
            
        Returns:
            Detailed staff dict or None if not found
        """
        stmt = select(User).where(
            and_(
                User.id == staff_id,
                User.is_platform_staff == True
            )
        )
        
        result = await self.db.execute(stmt)
        staff = result.scalar_one_or_none()
        
        if not staff:
            return None
        
        # Get who onboarded this staff member
        onboarded_by = None
        if staff.onboarded_by_id:
            onboard_result = await self.db.execute(
                select(User).where(User.id == staff.onboarded_by_id)
            )
            onboarded_by_user = onboard_result.scalar_one_or_none()
            if onboarded_by_user:
                onboarded_by = {
                    "id": str(onboarded_by_user.id),
                    "email": onboarded_by_user.email,
                    "full_name": onboarded_by_user.full_name,
                }
        
        return {
            **self._staff_to_dict(staff),
            "staff_notes": staff.staff_notes,
            "onboarded_by": onboarded_by,
            "must_reset_password": staff.must_reset_password,
            "email_verified_at": staff.email_verified_at.isoformat() if staff.email_verified_at else None,
        }
    
    async def update_staff(
        self,
        staff_id: UUID,
        updated_by: User,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        phone_number: Optional[str] = None,
        platform_role: Optional[PlatformRole] = None,
        is_active: Optional[bool] = None,
        staff_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update a platform staff account.
        
        Args:
            staff_id: UUID of staff to update
            updated_by: The Super Admin making the update
            first_name: New first name
            last_name: New last name
            phone_number: New phone number
            platform_role: New platform role
            is_active: New active status
            staff_notes: New internal notes
            
        Returns:
            Updated staff info
        """
        # Validate updater is Super Admin
        if not updated_by.is_platform_staff or updated_by.platform_role != PlatformRole.SUPER_ADMIN:
            raise PermissionError("Only Super Admin can update platform staff accounts")
        
        # Get the staff member
        stmt = select(User).where(
            and_(
                User.id == staff_id,
                User.is_platform_staff == True
            )
        )
        result = await self.db.execute(stmt)
        staff = result.scalar_one_or_none()
        
        if not staff:
            raise ValueError("Platform staff member not found")
        
        # Cannot deactivate yourself
        if staff.id == updated_by.id and is_active is False:
            raise ValueError("Cannot deactivate your own account")
        
        # Cannot demote yourself from Super Admin
        if staff.id == updated_by.id and platform_role and platform_role != PlatformRole.SUPER_ADMIN:
            raise ValueError("Cannot demote your own Super Admin account")
        
        # Track changes
        old_values = {}
        new_values = {}
        
        # Apply updates
        if first_name is not None:
            old_values["first_name"] = staff.first_name
            new_values["first_name"] = first_name
            staff.first_name = first_name.strip()
        
        if last_name is not None:
            old_values["last_name"] = staff.last_name
            new_values["last_name"] = last_name
            staff.last_name = last_name.strip()
        
        if phone_number is not None:
            old_values["phone_number"] = staff.phone_number
            new_values["phone_number"] = phone_number
            staff.phone_number = phone_number.strip() if phone_number else None
        
        if platform_role is not None and platform_role != staff.platform_role:
            old_values["platform_role"] = staff.platform_role.value if staff.platform_role else None
            new_values["platform_role"] = platform_role.value
            staff.platform_role = platform_role
        
        if is_active is not None and is_active != staff.is_active:
            old_values["is_active"] = staff.is_active
            new_values["is_active"] = is_active
            staff.is_active = is_active
        
        if staff_notes is not None:
            old_values["staff_notes"] = "[REDACTED]" if staff.staff_notes else None
            new_values["staff_notes"] = "[UPDATED]" if staff_notes else None
            staff.staff_notes = staff_notes
        
        # Create audit log
        if new_values:
            audit_log = AuditLog(
                user_id=updated_by.id,
                user_email=updated_by.email,
                action="update_platform_staff",
                table_name="users",
                record_id=staff.id,
                target_entity_type="platform_staff",
                target_entity_id=str(staff.id),
                old_values=old_values,
                new_values=new_values,
                description=f"Updated platform staff: {staff.email}",
            )
            self.db.add(audit_log)
        
        await self.db.commit()
        await self.db.refresh(staff)
        
        logger.info(f"Super Admin {updated_by.email} updated platform staff: {staff.email}")
        
        return {
            "success": True,
            "user": self._staff_to_dict(staff),
            "changes": new_values,
        }
    
    async def reset_staff_password(
        self,
        staff_id: UUID,
        reset_by: User,
        new_password: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Reset a platform staff member's password.
        
        Args:
            staff_id: UUID of staff whose password to reset
            reset_by: The Super Admin performing the reset
            new_password: Optional new password (generates if not provided)
            
        Returns:
            Result with temporary password if generated
        """
        # Validate resetter is Super Admin
        if not reset_by.is_platform_staff or reset_by.platform_role != PlatformRole.SUPER_ADMIN:
            raise PermissionError("Only Super Admin can reset platform staff passwords")
        
        # Get the staff member
        stmt = select(User).where(
            and_(
                User.id == staff_id,
                User.is_platform_staff == True
            )
        )
        result = await self.db.execute(stmt)
        staff = result.scalar_one_or_none()
        
        if not staff:
            raise ValueError("Platform staff member not found")
        
        # Generate or use provided password
        temp_password = new_password or self._generate_secure_password()
        staff.hashed_password = self._hash_password(temp_password)
        staff.must_reset_password = True if not new_password else False
        
        # Create audit log
        audit_log = AuditLog(
            user_id=reset_by.id,
            user_email=reset_by.email,
            action="reset_platform_staff_password",
            table_name="users",
            record_id=staff.id,
            target_entity_type="platform_staff",
            target_entity_id=str(staff.id),
            description=f"Reset password for platform staff: {staff.email}",
        )
        self.db.add(audit_log)
        
        await self.db.commit()
        
        logger.info(f"Super Admin {reset_by.email} reset password for: {staff.email}")
        
        result = {
            "success": True,
            "message": f"Password reset for {staff.email}",
        }
        
        if not new_password:
            result["temporary_password"] = temp_password
            result["must_reset_password"] = True
        
        return result
    
    async def deactivate_staff(
        self,
        staff_id: UUID,
        deactivated_by: User,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Deactivate a platform staff account.
        
        Args:
            staff_id: UUID of staff to deactivate
            deactivated_by: The Super Admin performing deactivation
            reason: Optional reason for deactivation
            
        Returns:
            Result dict
        """
        # Validate deactivator is Super Admin
        if not deactivated_by.is_platform_staff or deactivated_by.platform_role != PlatformRole.SUPER_ADMIN:
            raise PermissionError("Only Super Admin can deactivate platform staff accounts")
        
        # Get the staff member
        stmt = select(User).where(
            and_(
                User.id == staff_id,
                User.is_platform_staff == True
            )
        )
        result = await self.db.execute(stmt)
        staff = result.scalar_one_or_none()
        
        if not staff:
            raise ValueError("Platform staff member not found")
        
        # Cannot deactivate yourself
        if staff.id == deactivated_by.id:
            raise ValueError("Cannot deactivate your own account")
        
        # Cannot deactivate the last Super Admin
        if staff.platform_role == PlatformRole.SUPER_ADMIN:
            count_result = await self.db.execute(
                select(func.count(User.id)).where(
                    and_(
                        User.is_platform_staff == True,
                        User.platform_role == PlatformRole.SUPER_ADMIN,
                        User.is_active == True,
                        User.id != staff_id
                    )
                )
            )
            remaining_super_admins = count_result.scalar() or 0
            if remaining_super_admins == 0:
                raise ValueError("Cannot deactivate the last active Super Admin")
        
        # Deactivate
        staff.is_active = False
        
        # Update notes with deactivation reason
        deactivation_note = f"\n[{datetime.utcnow().isoformat()}] Deactivated by {deactivated_by.email}"
        if reason:
            deactivation_note += f": {reason}"
        staff.staff_notes = (staff.staff_notes or "") + deactivation_note
        
        # Create audit log
        audit_log = AuditLog(
            user_id=deactivated_by.id,
            user_email=deactivated_by.email,
            action="deactivate_platform_staff",
            table_name="users",
            record_id=staff.id,
            target_entity_type="platform_staff",
            target_entity_id=str(staff.id),
            new_values={"is_active": False, "reason": reason},
            description=f"Deactivated platform staff: {staff.email}",
        )
        self.db.add(audit_log)
        
        await self.db.commit()
        
        logger.info(f"Super Admin {deactivated_by.email} deactivated platform staff: {staff.email}")
        
        return {
            "success": True,
            "message": f"Platform staff {staff.email} has been deactivated",
            "deactivated_at": datetime.utcnow().isoformat(),
        }
    
    async def reactivate_staff(
        self,
        staff_id: UUID,
        reactivated_by: User,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Reactivate a deactivated platform staff account.
        
        Args:
            staff_id: UUID of staff to reactivate
            reactivated_by: The Super Admin performing reactivation
            reason: Optional reason for reactivation
            
        Returns:
            Result dict
        """
        # Validate reactivator is Super Admin
        if not reactivated_by.is_platform_staff or reactivated_by.platform_role != PlatformRole.SUPER_ADMIN:
            raise PermissionError("Only Super Admin can reactivate platform staff accounts")
        
        # Get the staff member
        stmt = select(User).where(
            and_(
                User.id == staff_id,
                User.is_platform_staff == True
            )
        )
        result = await self.db.execute(stmt)
        staff = result.scalar_one_or_none()
        
        if not staff:
            raise ValueError("Platform staff member not found")
        
        if staff.is_active:
            raise ValueError("Staff member is already active")
        
        # Reactivate
        staff.is_active = True
        
        # Update notes
        reactivation_note = f"\n[{datetime.utcnow().isoformat()}] Reactivated by {reactivated_by.email}"
        if reason:
            reactivation_note += f": {reason}"
        staff.staff_notes = (staff.staff_notes or "") + reactivation_note
        
        # Create audit log
        audit_log = AuditLog(
            user_id=reactivated_by.id,
            user_email=reactivated_by.email,
            action="reactivate_platform_staff",
            table_name="users",
            record_id=staff.id,
            target_entity_type="platform_staff",
            target_entity_id=str(staff.id),
            new_values={"is_active": True, "reason": reason},
            description=f"Reactivated platform staff: {staff.email}",
        )
        self.db.add(audit_log)
        
        await self.db.commit()
        
        logger.info(f"Super Admin {reactivated_by.email} reactivated platform staff: {staff.email}")
        
        return {
            "success": True,
            "message": f"Platform staff {staff.email} has been reactivated",
            "reactivated_at": datetime.utcnow().isoformat(),
        }
    
    async def get_staff_stats(self) -> Dict[str, Any]:
        """
        Get platform staff statistics.
        
        Returns:
            Statistics dict
        """
        # Total staff count
        total_result = await self.db.execute(
            select(func.count(User.id)).where(User.is_platform_staff == True)
        )
        total_staff = total_result.scalar() or 0
        
        # Active staff count
        active_result = await self.db.execute(
            select(func.count(User.id)).where(
                and_(User.is_platform_staff == True, User.is_active == True)
            )
        )
        active_staff = active_result.scalar() or 0
        
        # Inactive staff count
        inactive_staff = total_staff - active_staff
        
        # Count by role
        role_result = await self.db.execute(
            select(User.platform_role, func.count(User.id))
            .where(and_(User.is_platform_staff == True, User.platform_role.isnot(None)))
            .group_by(User.platform_role)
        )
        role_counts = {role.value: count for role, count in role_result.all()}
        
        # Recent staff (last 30 days)
        from datetime import timedelta
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_result = await self.db.execute(
            select(func.count(User.id)).where(
                and_(
                    User.is_platform_staff == True,
                    User.created_at >= thirty_days_ago
                )
            )
        )
        recent_staff = recent_result.scalar() or 0
        
        return {
            "total_staff": total_staff,
            "active_staff": active_staff,
            "inactive_staff": inactive_staff,
            "staff_by_role": role_counts,
            "recent_staff_30d": recent_staff,
        }
    
    async def get_audit_history(
        self,
        staff_id: UUID,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get audit history for a platform staff member.
        
        Args:
            staff_id: UUID of the staff member
            limit: Maximum number of audit records
            
        Returns:
            List of audit log entries
        """
        stmt = select(AuditLog).where(
            or_(
                AuditLog.user_id == staff_id,  # Actions by this staff
                AuditLog.target_entity_id == str(staff_id)  # Actions on this staff
            )
        ).order_by(desc(AuditLog.created_at)).limit(limit)
        
        result = await self.db.execute(stmt)
        logs = result.scalars().all()
        
        return [
            {
                "id": str(log.id),
                "action": log.action,
                "user_email": log.user_email,
                "description": log.description,
                "changes": log.new_values,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]
    
    def _staff_to_dict(self, staff: User) -> Dict[str, Any]:
        """Convert staff user to dict."""
        return {
            "id": str(staff.id),
            "email": staff.email,
            "first_name": staff.first_name,
            "last_name": staff.last_name,
            "full_name": staff.full_name,
            "phone_number": staff.phone_number,
            "platform_role": staff.platform_role.value if staff.platform_role else None,
            "is_active": staff.is_active,
            "is_verified": staff.is_verified,
            "created_at": staff.created_at.isoformat() if staff.created_at else None,
            "updated_at": staff.updated_at.isoformat() if staff.updated_at else None,
        }
