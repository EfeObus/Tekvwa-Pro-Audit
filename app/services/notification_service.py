"""
Tekvwa Pro Audit - Notification Service

Handles in-app notifications and email alerts.
Fully integrated with database for persistent notification storage.
"""

import uuid
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, and_, update, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.notification import (
    Notification as NotificationModel,
    NotificationType,
    NotificationPriority,
    NotificationChannel,
)
from app.services.email_service import EmailService, EmailMessage

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for managing notifications with full database integration."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.email_service = EmailService()
    
    async def create_notification(
        self,
        user_id: uuid.UUID,
        title: str,
        message: str,
        notification_type: NotificationType = NotificationType.INFO,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        entity_id: Optional[uuid.UUID] = None,
        channels: Optional[List[str]] = None,
        action_url: Optional[str] = None,
        action_label: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        expires_at: Optional[datetime] = None,
        send_email: bool = False,
        email_address: Optional[str] = None,
    ) -> NotificationModel:
        """
        Create a new notification for a user.
        
        Args:
            user_id: The user to notify
            title: Notification title
            message: Notification message
            notification_type: Type of notification
            priority: Priority level
            entity_id: Optional associated business entity
            channels: Delivery channels (defaults to ['in_app'])
            action_url: Optional URL for action button
            action_label: Optional label for action button
            metadata: Additional data to store
            expires_at: When the notification expires
            send_email: Whether to also send an email
            email_address: Email address for email notification
        """
        if channels is None:
            channels = ["in_app"]
        
        notification = NotificationModel(
            user_id=user_id,
            entity_id=entity_id,
            title=title,
            message=message,
            notification_type=notification_type,
            priority=priority,
            channels=channels,
            action_url=action_url,
            action_label=action_label,
            metadata=metadata,
            expires_at=expires_at,
            is_read=False,
            email_sent=False,
        )
        
        self.db.add(notification)
        await self.db.flush()
        await self.db.refresh(notification)
        
        logger.info(f"Notification created for user {user_id}: {title}")
        
        # Send email if requested
        if send_email and email_address:
            try:
                email_sent = await self.email_service.send_email(EmailMessage(
                    to=[email_address],
                    subject=title,
                    body_text=message,
                    body_html=f"<p>{message}</p>" + (
                        f'<p><a href="{action_url}">{action_label or "View Details"}</a></p>'
                        if action_url else ""
                    ),
                ))
                if email_sent:
                    notification.mark_email_sent()
                    await self.db.flush()
            except Exception as e:
                logger.error(f"Failed to send email notification: {e}")
        
        await self.db.commit()
        return notification
    
    async def get_notification_by_id(
        self,
        notification_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[NotificationModel]:
        """Get a notification by ID for a specific user."""
        result = await self.db.execute(
            select(NotificationModel)
            .where(NotificationModel.id == notification_id)
            .where(NotificationModel.user_id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def get_user_notifications(
        self,
        user_id: uuid.UUID,
        is_read: Optional[bool] = None,
        entity_id: Optional[uuid.UUID] = None,
        notification_type: Optional[NotificationType] = None,
        priority: Optional[NotificationPriority] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[NotificationModel], int]:
        """
        Get notifications for a user with optional filters.
        
        Returns:
            Tuple of (notifications, total_count)
        """
        query = (
            select(NotificationModel)
            .where(NotificationModel.user_id == user_id)
        )
        
        # Apply filters
        if is_read is not None:
            query = query.where(NotificationModel.is_read == is_read)
        
        if entity_id:
            query = query.where(NotificationModel.entity_id == entity_id)
        
        if notification_type:
            query = query.where(NotificationModel.notification_type == notification_type)
        
        if priority:
            query = query.where(NotificationModel.priority == priority)
        
        # Exclude expired notifications
        query = query.where(
            (NotificationModel.expires_at == None) |
            (NotificationModel.expires_at > datetime.utcnow())
        )
        
        # Count total
        count_query = (
            select(func.count(NotificationModel.id))
            .where(NotificationModel.user_id == user_id)
        )
        if is_read is not None:
            count_query = count_query.where(NotificationModel.is_read == is_read)
        
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0
        
        # Apply pagination and ordering
        query = (
            query
            .order_by(NotificationModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        
        result = await self.db.execute(query)
        notifications = list(result.scalars().all())
        
        return notifications, total
    
    async def get_unread_count(self, user_id: uuid.UUID) -> int:
        """Get count of unread notifications for a user."""
        result = await self.db.execute(
            select(func.count(NotificationModel.id))
            .where(NotificationModel.user_id == user_id)
            .where(NotificationModel.is_read == False)
            .where(
                (NotificationModel.expires_at == None) |
                (NotificationModel.expires_at > datetime.utcnow())
            )
        )
        return result.scalar() or 0
    
    async def mark_as_read(
        self,
        notification_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Mark a notification as read."""
        notification = await self.get_notification_by_id(notification_id, user_id)
        
        if not notification:
            return False
        
        notification.mark_as_read()
        await self.db.commit()
        
        logger.info(f"Notification {notification_id} marked as read")
        return True
    
    async def mark_all_as_read(
        self,
        user_id: uuid.UUID,
        entity_id: Optional[uuid.UUID] = None,
    ) -> int:
        """Mark all notifications as read for a user."""
        now = datetime.utcnow()
        
        query = (
            update(NotificationModel)
            .where(NotificationModel.user_id == user_id)
            .where(NotificationModel.is_read == False)
        )
        
        if entity_id:
            query = query.where(NotificationModel.entity_id == entity_id)
        
        result = await self.db.execute(query.values(is_read=True, read_at=now))
        
        await self.db.commit()
        
        count = result.rowcount
        logger.info(f"Marked {count} notifications as read for user {user_id}")
        return count
    
    async def delete_notification(
        self,
        notification_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Delete a notification."""
        result = await self.db.execute(
            delete(NotificationModel)
            .where(NotificationModel.id == notification_id)
            .where(NotificationModel.user_id == user_id)
        )
        
        await self.db.commit()
        return result.rowcount > 0
    
    async def delete_old_notifications(
        self,
        days_old: int = 90,
    ) -> int:
        """Delete notifications older than specified days."""
        cutoff = datetime.utcnow() - timedelta(days=days_old)
        
        result = await self.db.execute(
            delete(NotificationModel)
            .where(NotificationModel.created_at < cutoff)
        )
        
        await self.db.commit()
        
        count = result.rowcount
        logger.info(f"Deleted {count} old notifications")
        return count
    
    async def delete_read_notifications(self, user_id: uuid.UUID) -> int:
        """Delete all read notifications for a user."""
        result = await self.db.execute(
            delete(NotificationModel)
            .where(NotificationModel.user_id == user_id)
            .where(NotificationModel.is_read == True)
        )
        
        await self.db.commit()
        return result.rowcount
    
    async def has_urgent_unread(self, user_id: uuid.UUID) -> bool:
        """Check if user has any urgent unread notifications."""
        result = await self.db.execute(
            select(func.count(NotificationModel.id))
            .where(NotificationModel.user_id == user_id)
            .where(NotificationModel.is_read == False)
            .where(NotificationModel.priority == NotificationPriority.URGENT)
            .where(
                (NotificationModel.expires_at == None) |
                (NotificationModel.expires_at > datetime.utcnow())
            )
        )
        return (result.scalar() or 0) > 0
    
    async def get_user_preferences(self, user_id: uuid.UUID) -> Dict[str, Any]:
        """Get notification preferences for a user."""
        # In a full implementation, this would query a user_preferences table
        # For now, return default preferences
        return {
            "email_tax_reminders": True,
            "email_invoice_updates": True,
            "email_payment_received": True,
            "email_low_stock_alerts": True,
            "email_compliance_warnings": True,
            "email_marketing": False,
            "in_app_all": True,
            "push_enabled": False,
        }
    
    async def update_user_preferences(
        self,
        user_id: uuid.UUID,
        **kwargs,
    ) -> Dict[str, Any]:
        """Update notification preferences for a user."""
        # In a full implementation, this would update a user_preferences table
        # For now, merge with defaults and return
        preferences = await self.get_user_preferences(user_id)
        preferences.update(kwargs)
        return preferences
    
    # ===========================================
    # CONVENIENCE METHODS FOR SPECIFIC NOTIFICATIONS
    # ===========================================
    
    async def notify_invoice_overdue(
        self,
        user_id: uuid.UUID,
        entity_id: uuid.UUID,
        invoice_number: str,
        customer_name: str,
        amount: float,
        days_overdue: int,
        email_address: Optional[str] = None,
    ) -> NotificationModel:
        """Send invoice overdue notification."""
        return await self.create_notification(
            user_id=user_id,
            entity_id=entity_id,
            notification_type=NotificationType.INVOICE_OVERDUE,
            priority=NotificationPriority.HIGH,
            title="Invoice Overdue",
            message=f"Invoice {invoice_number} for {customer_name} (₦{amount:,.2f}) is {days_overdue} days overdue.",
            action_url=f"/invoices?search={invoice_number}",
            action_label="View Invoice",
            metadata={
                "invoice_number": invoice_number,
                "customer_name": customer_name,
                "amount": amount,
                "days_overdue": days_overdue,
            },
            send_email=email_address is not None,
            email_address=email_address,
        )
    
    async def notify_low_stock(
        self,
        user_id: uuid.UUID,
        entity_id: uuid.UUID,
        item_name: str,
        current_stock: int,
        reorder_level: int,
        item_id: Optional[uuid.UUID] = None,
    ) -> NotificationModel:
        """Send low stock notification."""
        return await self.create_notification(
            user_id=user_id,
            entity_id=entity_id,
            notification_type=NotificationType.LOW_STOCK_ALERT,
            priority=NotificationPriority.HIGH,
            title="Low Stock Alert",
            message=f"{item_name} is running low. Current stock: {current_stock} (Reorder at: {reorder_level})",
            action_url="/inventory?filter=low_stock",
            action_label="View Inventory",
            metadata={
                "item_id": str(item_id) if item_id else None,
                "item_name": item_name,
                "current_stock": current_stock,
                "reorder_level": reorder_level,
            },
        )
    
    async def notify_vat_reminder(
        self,
        user_id: uuid.UUID,
        entity_id: uuid.UUID,
        period: str,
        deadline: str,
        days_until: int,
        vat_amount: Optional[float] = None,
        email_address: Optional[str] = None,
    ) -> NotificationModel:
        """Send VAT filing reminder."""
        priority = NotificationPriority.URGENT if days_until <= 3 else NotificationPriority.HIGH
        
        return await self.create_notification(
            user_id=user_id,
            entity_id=entity_id,
            notification_type=NotificationType.VAT_REMINDER,
            priority=priority,
            title="VAT Filing Reminder",
            message=f"VAT return for {period} is due on {deadline} ({days_until} days remaining)." + (
                f" Estimated VAT: ₦{vat_amount:,.2f}" if vat_amount else ""
            ),
            action_url="/reports?tab=tax",
            action_label="View VAT Report",
            metadata={
                "period": period,
                "deadline": deadline,
                "days_until": days_until,
                "vat_amount": vat_amount,
            },
            send_email=email_address is not None,
            email_address=email_address,
        )
    
    async def notify_nrs_success(
        self,
        user_id: uuid.UUID,
        entity_id: uuid.UUID,
        invoice_number: str,
        irn: str,
    ) -> NotificationModel:
        """Send NRS submission success notification."""
        return await self.create_notification(
            user_id=user_id,
            entity_id=entity_id,
            notification_type=NotificationType.NRS_SUBMISSION_SUCCESS,
            priority=NotificationPriority.NORMAL,
            title="NRS Submission Successful",
            message=f"Invoice {invoice_number} submitted to NRS. IRN: {irn}",
            action_url=f"/invoices?search={invoice_number}",
            action_label="View Invoice",
            metadata={
                "invoice_number": invoice_number,
                "irn": irn,
            },
        )
    
    async def notify_nrs_failed(
        self,
        user_id: uuid.UUID,
        entity_id: uuid.UUID,
        invoice_number: str,
        error_message: str,
    ) -> NotificationModel:
        """Send NRS submission failure notification."""
        return await self.create_notification(
            user_id=user_id,
            entity_id=entity_id,
            notification_type=NotificationType.NRS_SUBMISSION_FAILED,
            priority=NotificationPriority.URGENT,
            title="NRS Submission Failed",
            message=f"Invoice {invoice_number} failed to submit to NRS: {error_message}",
            action_url=f"/invoices?search={invoice_number}",
            action_label="Retry Submission",
            metadata={
                "invoice_number": invoice_number,
                "error_message": error_message,
            },
        )
    
    async def notify_payment_received(
        self,
        user_id: uuid.UUID,
        entity_id: uuid.UUID,
        invoice_number: str,
        amount: float,
        payment_method: str,
    ) -> NotificationModel:
        """Send payment received notification."""
        return await self.create_notification(
            user_id=user_id,
            entity_id=entity_id,
            notification_type=NotificationType.INVOICE_PAID,
            priority=NotificationPriority.NORMAL,
            title="Payment Received",
            message=f"Payment of ₦{amount:,.2f} received for invoice {invoice_number} via {payment_method}.",
            action_url=f"/invoices?search={invoice_number}",
            action_label="View Invoice",
            metadata={
                "invoice_number": invoice_number,
                "amount": amount,
                "payment_method": payment_method,
            },
        )
    
    async def notify_compliance_warning(
        self,
        user_id: uuid.UUID,
        entity_id: uuid.UUID,
        warning_type: str,
        message: str,
        deadline: Optional[str] = None,
        email_address: Optional[str] = None,
    ) -> NotificationModel:
        """Send compliance warning notification."""
        return await self.create_notification(
            user_id=user_id,
            entity_id=entity_id,
            notification_type=NotificationType.COMPLIANCE_WARNING,
            priority=NotificationPriority.URGENT,
            title=f"Compliance Alert: {warning_type}",
            message=message,
            action_url="/dashboard",
            action_label="View Compliance Status",
            metadata={
                "warning_type": warning_type,
                "deadline": deadline,
            },
            send_email=email_address is not None,
            email_address=email_address,
        )

