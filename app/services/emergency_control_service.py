"""
Tekvwa Pro Audit - Emergency Control Service

Service layer for managing platform emergency controls.
Super Admin only feature for critical security operations.

Features:
- Platform-wide read-only mode
- Feature kill switches
- Emergency tenant suspension
- Maintenance mode
- Login lockdown

All actions are fully audited and require mandatory reasons.
"""

import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy import select, func, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.emergency_control import (
    EmergencyControl,
    PlatformStatus,
    EmergencyActionType,
    FeatureKey,
)
from app.models.organization import Organization
from app.models.user import User
from app.models.audit_consolidated import AuditLog, AuditAction


class EmergencyControlService:
    """
    Service for managing platform emergency controls.
    
    CRITICAL: All methods in this service should only be called
    by authenticated Super Admins. Access control should be
    enforced at the router level.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # ==========================================
    # PLATFORM STATUS OPERATIONS
    # ==========================================
    
    async def get_platform_status(self) -> PlatformStatus:
        """Get current platform status."""
        result = await self.db.execute(select(PlatformStatus).limit(1))
        status = result.scalar_one_or_none()
        
        if not status:
            # Create initial status if not exists
            status = PlatformStatus(
                is_read_only=False,
                is_maintenance_mode=False,
                is_login_locked=False,
                disabled_features=[],
            )
            self.db.add(status)
            await self.db.commit()
            await self.db.refresh(status)
        
        return status
    
    async def _update_platform_status(
        self,
        admin_id: uuid.UUID,
        **updates
    ) -> PlatformStatus:
        """Update platform status with audit trail."""
        status = await self.get_platform_status()
        
        for key, value in updates.items():
            if hasattr(status, key):
                setattr(status, key, value)
        
        status.last_changed_by_id = admin_id
        status.last_changed_at = datetime.utcnow()
        
        await self.db.commit()
        await self.db.refresh(status)
        return status
    
    # ==========================================
    # READ-ONLY MODE
    # ==========================================
    
    async def enable_read_only_mode(
        self,
        admin_id: uuid.UUID,
        reason: str,
        message: Optional[str] = None,
    ) -> Tuple[EmergencyControl, PlatformStatus]:
        """
        Enable platform-wide read-only mode.
        
        In read-only mode:
        - All write operations are blocked
        - Users can view data but not modify
        - Admin operations still work
        
        Args:
            admin_id: ID of the Super Admin initiating the action
            reason: Mandatory reason for enabling read-only mode
            message: Optional message to display to users
            
        Returns:
            Tuple of (EmergencyControl log entry, updated PlatformStatus)
        """
        # Check if already in read-only mode
        status = await self.get_platform_status()
        if status.is_read_only:
            raise ValueError("Platform is already in read-only mode")
        
        # Create emergency control log
        control = EmergencyControl(
            action_type=EmergencyActionType.READ_ONLY_MODE,
            target_type="platform",
            target_id=None,
            initiated_by_id=admin_id,
            reason=reason,
            started_at=datetime.utcnow(),
            is_active=True,
            action_metadata={"message": message} if message else None,
        )
        self.db.add(control)
        
        # Update platform status
        status = await self._update_platform_status(
            admin_id,
            is_read_only=True,
            maintenance_message=message,
        )
        
        # Create audit log
        await self._create_audit_log(
            admin_id,
            AuditAction.CREATE,
            "emergency_control",
            control.id,
            {"action": "enable_read_only_mode", "reason": reason},
        )
        
        await self.db.commit()
        await self.db.refresh(control)
        
        return control, status
    
    async def disable_read_only_mode(
        self,
        admin_id: uuid.UUID,
        reason: str,
    ) -> Tuple[EmergencyControl, PlatformStatus]:
        """
        Disable platform-wide read-only mode.
        
        Args:
            admin_id: ID of the Super Admin ending the action
            reason: Reason for disabling read-only mode
            
        Returns:
            Tuple of (updated EmergencyControl log entry, updated PlatformStatus)
        """
        # Check if in read-only mode
        status = await self.get_platform_status()
        if not status.is_read_only:
            raise ValueError("Platform is not in read-only mode")
        
        # Find active read-only control
        result = await self.db.execute(
            select(EmergencyControl).where(
                and_(
                    EmergencyControl.action_type == EmergencyActionType.READ_ONLY_MODE,
                    EmergencyControl.is_active == True,
                )
            ).order_by(EmergencyControl.started_at.desc()).limit(1)
        )
        control = result.scalar_one_or_none()
        
        if control:
            control.ended_at = datetime.utcnow()
            control.ended_by_id = admin_id
            control.end_reason = reason
            control.is_active = False
        
        # Update platform status
        status = await self._update_platform_status(
            admin_id,
            is_read_only=False,
            maintenance_message=None,
        )
        
        # Create audit log
        await self._create_audit_log(
            admin_id,
            AuditAction.UPDATE,
            "emergency_control",
            control.id if control else None,
            {"action": "disable_read_only_mode", "reason": reason},
        )
        
        await self.db.commit()
        if control:
            await self.db.refresh(control)
        
        return control, status
    
    # ==========================================
    # FEATURE KILL SWITCHES
    # ==========================================
    
    async def disable_feature(
        self,
        admin_id: uuid.UUID,
        feature_key: str,
        reason: str,
    ) -> Tuple[EmergencyControl, PlatformStatus]:
        """
        Disable a specific platform feature.
        
        Args:
            admin_id: ID of the Super Admin
            feature_key: Key of the feature to disable (from FeatureKey enum)
            reason: Mandatory reason for disabling
            
        Returns:
            Tuple of (EmergencyControl log entry, updated PlatformStatus)
        """
        # Validate feature key
        valid_features = [f.value for f in FeatureKey]
        if feature_key not in valid_features:
            raise ValueError(f"Invalid feature key. Valid keys: {valid_features}")
        
        # Check if already disabled
        status = await self.get_platform_status()
        if status.disabled_features and feature_key in status.disabled_features:
            raise ValueError(f"Feature '{feature_key}' is already disabled")
        
        # Create emergency control log
        control = EmergencyControl(
            action_type=EmergencyActionType.FEATURE_KILL_SWITCH,
            target_type="feature",
            target_id=feature_key,
            initiated_by_id=admin_id,
            reason=reason,
            started_at=datetime.utcnow(),
            is_active=True,
        )
        self.db.add(control)
        
        # Update platform status
        disabled_features = list(status.disabled_features or [])
        disabled_features.append(feature_key)
        
        status = await self._update_platform_status(
            admin_id,
            disabled_features=disabled_features,
        )
        
        # Create audit log
        await self._create_audit_log(
            admin_id,
            AuditAction.CREATE,
            "feature_kill_switch",
            control.id,
            {"feature": feature_key, "action": "disable", "reason": reason},
        )
        
        await self.db.commit()
        await self.db.refresh(control)
        
        return control, status
    
    async def enable_feature(
        self,
        admin_id: uuid.UUID,
        feature_key: str,
        reason: str,
    ) -> Tuple[Optional[EmergencyControl], PlatformStatus]:
        """
        Re-enable a disabled platform feature.
        
        Args:
            admin_id: ID of the Super Admin
            feature_key: Key of the feature to enable
            reason: Reason for re-enabling
            
        Returns:
            Tuple of (updated EmergencyControl if found, updated PlatformStatus)
        """
        # Check if feature is disabled
        status = await self.get_platform_status()
        if not status.disabled_features or feature_key not in status.disabled_features:
            raise ValueError(f"Feature '{feature_key}' is not currently disabled")
        
        # Find active kill switch for this feature
        result = await self.db.execute(
            select(EmergencyControl).where(
                and_(
                    EmergencyControl.action_type == EmergencyActionType.FEATURE_KILL_SWITCH,
                    EmergencyControl.target_id == feature_key,
                    EmergencyControl.is_active == True,
                )
            ).order_by(EmergencyControl.started_at.desc()).limit(1)
        )
        control = result.scalar_one_or_none()
        
        if control:
            control.ended_at = datetime.utcnow()
            control.ended_by_id = admin_id
            control.end_reason = reason
            control.is_active = False
        
        # Update platform status
        disabled_features = [f for f in status.disabled_features if f != feature_key]
        
        status = await self._update_platform_status(
            admin_id,
            disabled_features=disabled_features,
        )
        
        # Create audit log
        await self._create_audit_log(
            admin_id,
            AuditAction.UPDATE,
            "feature_kill_switch",
            control.id if control else None,
            {"feature": feature_key, "action": "enable", "reason": reason},
        )
        
        await self.db.commit()
        if control:
            await self.db.refresh(control)
        
        return control, status
    
    # ==========================================
    # EMERGENCY TENANT SUSPENSION
    # ==========================================
    
    async def emergency_suspend_tenant(
        self,
        admin_id: uuid.UUID,
        tenant_id: uuid.UUID,
        reason: str,
        notify_users: bool = True,
    ) -> Tuple[EmergencyControl, Organization]:
        """
        Emergency suspend a tenant (organization).
        
        This immediately blocks all access for the tenant's users.
        Different from regular suspension - this is for emergencies only.
        
        Args:
            admin_id: ID of the Super Admin
            tenant_id: ID of the tenant/organization to suspend
            reason: Mandatory reason for suspension
            notify_users: Whether to send notification to tenant users
            
        Returns:
            Tuple of (EmergencyControl log entry, updated Organization)
        """
        # Get tenant
        result = await self.db.execute(
            select(Organization).where(Organization.id == tenant_id)
        )
        tenant = result.scalar_one_or_none()
        
        if not tenant:
            raise ValueError(f"Tenant not found: {tenant_id}")
        
        if getattr(tenant, 'is_emergency_suspended', False):
            raise ValueError("Tenant is already emergency suspended")
        
        # Count affected users
        user_count_result = await self.db.execute(
            select(func.count(User.id)).where(User.organization_id == tenant_id)
        )
        affected_count = user_count_result.scalar() or 0
        
        # Create emergency control log
        control = EmergencyControl(
            action_type=EmergencyActionType.TENANT_EMERGENCY_SUSPEND,
            target_type="tenant",
            target_id=str(tenant_id),
            initiated_by_id=admin_id,
            reason=reason,
            started_at=datetime.utcnow(),
            is_active=True,
            affected_count=affected_count,
            action_metadata={
                "tenant_name": tenant.name,
                "notify_users": notify_users,
            },
        )
        self.db.add(control)
        
        # Update tenant
        tenant.is_emergency_suspended = True
        tenant.emergency_suspended_at = datetime.utcnow()
        tenant.emergency_suspended_by_id = admin_id
        tenant.emergency_suspension_reason = reason
        
        # Create audit log
        await self._create_audit_log(
            admin_id,
            AuditAction.UPDATE,
            "organization",
            tenant_id,
            {
                "action": "emergency_suspend",
                "reason": reason,
                "affected_users": affected_count,
            },
        )
        
        await self.db.commit()
        await self.db.refresh(control)
        await self.db.refresh(tenant)
        
        # TODO: If notify_users, send notifications via notification service
        
        return control, tenant
    
    async def lift_emergency_suspension(
        self,
        admin_id: uuid.UUID,
        tenant_id: uuid.UUID,
        reason: str,
    ) -> Tuple[Optional[EmergencyControl], Organization]:
        """
        Lift emergency suspension from a tenant.
        
        Args:
            admin_id: ID of the Super Admin
            tenant_id: ID of the tenant to unsuspend
            reason: Reason for lifting suspension
            
        Returns:
            Tuple of (updated EmergencyControl if found, updated Organization)
        """
        # Get tenant
        result = await self.db.execute(
            select(Organization).where(Organization.id == tenant_id)
        )
        tenant = result.scalar_one_or_none()
        
        if not tenant:
            raise ValueError(f"Tenant not found: {tenant_id}")
        
        if not getattr(tenant, 'is_emergency_suspended', False):
            raise ValueError("Tenant is not emergency suspended")
        
        # Find active suspension control
        result = await self.db.execute(
            select(EmergencyControl).where(
                and_(
                    EmergencyControl.action_type == EmergencyActionType.TENANT_EMERGENCY_SUSPEND,
                    EmergencyControl.target_id == str(tenant_id),
                    EmergencyControl.is_active == True,
                )
            ).order_by(EmergencyControl.started_at.desc()).limit(1)
        )
        control = result.scalar_one_or_none()
        
        if control:
            control.ended_at = datetime.utcnow()
            control.ended_by_id = admin_id
            control.end_reason = reason
            control.is_active = False
        
        # Update tenant
        tenant.is_emergency_suspended = False
        tenant.emergency_suspended_at = None
        tenant.emergency_suspended_by_id = None
        tenant.emergency_suspension_reason = None
        
        # Create audit log
        await self._create_audit_log(
            admin_id,
            AuditAction.UPDATE,
            "organization",
            tenant_id,
            {"action": "lift_emergency_suspension", "reason": reason},
        )
        
        await self.db.commit()
        if control:
            await self.db.refresh(control)
        await self.db.refresh(tenant)
        
        return control, tenant
    
    # ==========================================
    # MAINTENANCE MODE
    # ==========================================
    
    async def enable_maintenance_mode(
        self,
        admin_id: uuid.UUID,
        reason: str,
        message: str,
        expected_end: Optional[datetime] = None,
    ) -> Tuple[EmergencyControl, PlatformStatus]:
        """
        Enable platform maintenance mode.
        
        In maintenance mode:
        - All non-admin users see maintenance page
        - Only platform staff can access the system
        
        Args:
            admin_id: ID of the Super Admin
            reason: Reason for maintenance
            message: Message to display to users
            expected_end: Expected end time of maintenance
            
        Returns:
            Tuple of (EmergencyControl log entry, updated PlatformStatus)
        """
        status = await self.get_platform_status()
        if status.is_maintenance_mode:
            raise ValueError("Platform is already in maintenance mode")
        
        # Create emergency control log
        control = EmergencyControl(
            action_type=EmergencyActionType.MAINTENANCE_MODE,
            target_type="platform",
            target_id=None,
            initiated_by_id=admin_id,
            reason=reason,
            started_at=datetime.utcnow(),
            is_active=True,
            action_metadata={
                "message": message,
                "expected_end": expected_end.isoformat() if expected_end else None,
            },
        )
        self.db.add(control)
        
        # Update platform status
        status = await self._update_platform_status(
            admin_id,
            is_maintenance_mode=True,
            maintenance_message=message,
            maintenance_expected_end=expected_end,
        )
        
        await self._create_audit_log(
            admin_id,
            AuditAction.CREATE,
            "emergency_control",
            control.id,
            {"action": "enable_maintenance_mode", "reason": reason},
        )
        
        await self.db.commit()
        await self.db.refresh(control)
        
        return control, status
    
    async def disable_maintenance_mode(
        self,
        admin_id: uuid.UUID,
        reason: str,
    ) -> Tuple[Optional[EmergencyControl], PlatformStatus]:
        """Disable maintenance mode."""
        status = await self.get_platform_status()
        if not status.is_maintenance_mode:
            raise ValueError("Platform is not in maintenance mode")
        
        # Find active maintenance control
        result = await self.db.execute(
            select(EmergencyControl).where(
                and_(
                    EmergencyControl.action_type == EmergencyActionType.MAINTENANCE_MODE,
                    EmergencyControl.is_active == True,
                )
            ).order_by(EmergencyControl.started_at.desc()).limit(1)
        )
        control = result.scalar_one_or_none()
        
        if control:
            control.ended_at = datetime.utcnow()
            control.ended_by_id = admin_id
            control.end_reason = reason
            control.is_active = False
        
        status = await self._update_platform_status(
            admin_id,
            is_maintenance_mode=False,
            maintenance_message=None,
            maintenance_expected_end=None,
        )
        
        await self._create_audit_log(
            admin_id,
            AuditAction.UPDATE,
            "emergency_control",
            control.id if control else None,
            {"action": "disable_maintenance_mode", "reason": reason},
        )
        
        await self.db.commit()
        if control:
            await self.db.refresh(control)
        
        return control, status
    
    # ==========================================
    # LOGIN LOCKDOWN
    # ==========================================
    
    async def enable_login_lockdown(
        self,
        admin_id: uuid.UUID,
        reason: str,
        allow_admin_login: bool = True,
    ) -> Tuple[EmergencyControl, PlatformStatus]:
        """
        Enable platform-wide login lockdown.
        
        In login lockdown mode:
        - All non-admin users are blocked from logging in
        - Existing sessions may optionally be terminated
        - Only Super Admins can access the system
        
        Args:
            admin_id: ID of the Super Admin initiating the action
            reason: Mandatory reason for enabling login lockdown
            allow_admin_login: Whether to allow admin logins during lockdown
            
        Returns:
            Tuple of (EmergencyControl log entry, updated PlatformStatus)
        """
        # Check if already in login lockdown
        status = await self.get_platform_status()
        if status.is_login_locked:
            raise ValueError("Platform is already in login lockdown")
        
        # Create emergency control log
        control = EmergencyControl(
            action_type=EmergencyActionType.LOGIN_LOCKDOWN,
            target_type="platform",
            target_id=None,
            initiated_by_id=admin_id,
            reason=reason,
            started_at=datetime.utcnow(),
            is_active=True,
            action_metadata={"allow_admin_login": allow_admin_login},
        )
        self.db.add(control)
        
        # Update platform status
        status = await self._update_platform_status(
            admin_id,
            is_login_locked=True,
        )
        
        # Create audit log
        await self._create_audit_log(
            admin_id,
            AuditAction.CREATE,
            "emergency_control",
            control.id,
            {"action": "enable_login_lockdown", "reason": reason, "allow_admin_login": allow_admin_login},
        )
        
        await self.db.commit()
        await self.db.refresh(control)
        
        return control, status
    
    async def disable_login_lockdown(
        self,
        admin_id: uuid.UUID,
        reason: str,
    ) -> Tuple[Optional[EmergencyControl], PlatformStatus]:
        """
        Disable platform-wide login lockdown.
        
        Args:
            admin_id: ID of the Super Admin ending the action
            reason: Reason for disabling login lockdown
            
        Returns:
            Tuple of (updated EmergencyControl log entry, updated PlatformStatus)
        """
        # Check if in login lockdown
        status = await self.get_platform_status()
        if not status.is_login_locked:
            raise ValueError("Platform is not in login lockdown")
        
        # Find active login lockdown control
        result = await self.db.execute(
            select(EmergencyControl).where(
                and_(
                    EmergencyControl.action_type == EmergencyActionType.LOGIN_LOCKDOWN,
                    EmergencyControl.is_active == True,
                )
            ).order_by(EmergencyControl.started_at.desc()).limit(1)
        )
        control = result.scalar_one_or_none()
        
        if control:
            control.ended_at = datetime.utcnow()
            control.ended_by_id = admin_id
            control.end_reason = reason
            control.is_active = False
        
        # Update platform status
        status = await self._update_platform_status(
            admin_id,
            is_login_locked=False,
        )
        
        # Create audit log
        await self._create_audit_log(
            admin_id,
            AuditAction.UPDATE,
            "emergency_control",
            control.id if control else None,
            {"action": "disable_login_lockdown", "reason": reason},
        )
        
        await self.db.commit()
        if control:
            await self.db.refresh(control)
        
        return control, status
    
    # ==========================================
    # QUERY METHODS
    # ==========================================
    
    async def get_active_emergency_controls(self) -> List[EmergencyControl]:
        """Get all currently active emergency controls."""
        result = await self.db.execute(
            select(EmergencyControl)
            .where(EmergencyControl.is_active == True)
            .order_by(EmergencyControl.started_at.desc())
        )
        return list(result.scalars().all())
    
    async def get_emergency_control_history(
        self,
        action_type: Optional[EmergencyActionType] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[EmergencyControl]:
        """Get emergency control history with optional filter."""
        query = select(EmergencyControl)
        
        if action_type:
            query = query.where(EmergencyControl.action_type == action_type)
        
        query = query.order_by(EmergencyControl.started_at.desc())
        query = query.offset(offset).limit(limit)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_emergency_suspended_tenants(self) -> List[Organization]:
        """Get all emergency suspended tenants."""
        result = await self.db.execute(
            select(Organization).where(
                Organization.is_emergency_suspended == True
            )
        )
        return list(result.scalars().all())
    
    async def get_emergency_stats(self) -> Dict[str, Any]:
        """Get emergency control statistics."""
        status = await self.get_platform_status()
        
        # Count active controls by type
        active_controls = await self.get_active_emergency_controls()
        controls_by_type = {}
        for control in active_controls:
            action_type = control.action_type.value
            if action_type not in controls_by_type:
                controls_by_type[action_type] = 0
            controls_by_type[action_type] += 1
        
        # Count suspended tenants
        suspended_result = await self.db.execute(
            select(func.count(Organization.id)).where(
                Organization.is_emergency_suspended == True
            )
        )
        suspended_tenants = suspended_result.scalar() or 0
        
        return {
            "platform_status": {
                "is_read_only": status.is_read_only,
                "is_maintenance_mode": status.is_maintenance_mode,
                "is_login_locked": status.is_login_locked,
                "disabled_features": status.disabled_features or [],
                "maintenance_message": status.maintenance_message,
            },
            "active_controls_count": len(active_controls),
            "controls_by_type": controls_by_type,
            "suspended_tenants_count": suspended_tenants,
        }
    
    # ==========================================
    # HELPER METHODS
    # ==========================================
    
    async def _create_audit_log(
        self,
        user_id: uuid.UUID,
        action: AuditAction,
        resource_type: str,
        resource_id: Optional[uuid.UUID],
        details: Dict[str, Any],
    ) -> None:
        """Create an audit log entry."""
        audit_log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address="system",
        )
        self.db.add(audit_log)
    
    def is_feature_available(self, feature_key: str, status: PlatformStatus) -> bool:
        """Check if a feature is currently available."""
        if status.is_maintenance_mode:
            return False
        if status.disabled_features and feature_key in status.disabled_features:
            return False
        return True
