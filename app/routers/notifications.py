"""
Tekvwa Pro Audit - Notifications Router

API endpoints for managing user notifications.

Features:
- List notifications with filtering
- Mark as read (single/all)
- Delete notifications
- Notification preferences
- Unread count
"""

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import get_current_active_user
from app.models.user import User
from app.models.notification import NotificationType, NotificationPriority
from app.services.notification_service import NotificationService


router = APIRouter(prefix="/notifications", tags=["Notifications"])


# ===========================================
# REQUEST/RESPONSE SCHEMAS
# ===========================================

class NotificationResponse(BaseModel):
    """Schema for notification response."""
    id: uuid.UUID
    title: str
    message: str
    notification_type: str
    priority: str
    is_read: bool
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    entity_id: Optional[uuid.UUID] = None
    metadata: Optional[dict] = None
    created_at: datetime
    expires_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    """Schema for notification list response."""
    notifications: List[NotificationResponse]
    total: int
    unread_count: int


class UnreadCountResponse(BaseModel):
    """Schema for unread count response."""
    unread_count: int
    has_urgent: bool


class NotificationPreferences(BaseModel):
    """Schema for notification preferences."""
    email_tax_reminders: bool = True
    email_invoice_updates: bool = True
    email_payment_received: bool = True
    email_low_stock_alerts: bool = True
    email_compliance_warnings: bool = True
    email_marketing: bool = False
    in_app_all: bool = True
    push_enabled: bool = False


class UpdatePreferencesRequest(BaseModel):
    """Request schema for updating preferences."""
    email_tax_reminders: Optional[bool] = None
    email_invoice_updates: Optional[bool] = None
    email_payment_received: Optional[bool] = None
    email_low_stock_alerts: Optional[bool] = None
    email_compliance_warnings: Optional[bool] = None
    email_marketing: Optional[bool] = None
    in_app_all: Optional[bool] = None
    push_enabled: Optional[bool] = None


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    success: bool = True


# ===========================================
# HELPER FUNCTIONS
# ===========================================

def notification_to_response(notification) -> NotificationResponse:
    """Convert notification model to response."""
    return NotificationResponse(
        id=notification.id,
        title=notification.title,
        message=notification.message,
        notification_type=notification.notification_type.value if notification.notification_type else "info",
        priority=notification.priority.value if notification.priority else "normal",
        is_read=notification.is_read,
        action_url=notification.action_url,
        action_label=notification.action_label,
        entity_id=notification.entity_id,
        metadata=notification.metadata,
        created_at=notification.created_at,
        expires_at=notification.expires_at,
    )


# ===========================================
# ENDPOINTS
# ===========================================

@router.get(
    "",
    response_model=NotificationListResponse,
    summary="List notifications",
    description="Get all notifications for the current user with optional filtering.",
)
async def list_notifications(
    is_read: Optional[bool] = Query(None, description="Filter by read status"),
    notification_type: Optional[str] = Query(None, description="Filter by notification type"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    entity_id: Optional[uuid.UUID] = Query(None, description="Filter by entity"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """List notifications for the current user."""
    service = NotificationService(db)
    
    # Parse notification type if provided
    type_enum = None
    if notification_type:
        try:
            type_enum = NotificationType(notification_type)
        except ValueError:
            pass  # Ignore invalid types
    
    # Parse priority if provided
    priority_enum = None
    if priority:
        try:
            priority_enum = NotificationPriority(priority)
        except ValueError:
            pass
    
    notifications, total = await service.get_user_notifications(
        user_id=current_user.id,
        is_read=is_read,
        notification_type=type_enum,
        priority=priority_enum,
        entity_id=entity_id,
        limit=limit,
        offset=offset,
    )
    
    unread_count = await service.get_unread_count(current_user.id)
    
    return NotificationListResponse(
        notifications=[notification_to_response(n) for n in notifications],
        total=total,
        unread_count=unread_count,
    )


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
    summary="Get unread notification count",
    description="Get the count of unread notifications and whether there are urgent ones.",
)
async def get_unread_count(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get unread notification count."""
    service = NotificationService(db)
    
    unread_count = await service.get_unread_count(current_user.id)
    has_urgent = await service.has_urgent_unread(current_user.id)
    
    return UnreadCountResponse(
        unread_count=unread_count,
        has_urgent=has_urgent,
    )


@router.get(
    "/{notification_id}",
    response_model=NotificationResponse,
    summary="Get notification",
    description="Get a specific notification by ID.",
)
async def get_notification(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get a specific notification."""
    service = NotificationService(db)
    
    notification = await service.get_notification_by_id(
        notification_id=notification_id,
        user_id=current_user.id,
    )
    
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    
    return notification_to_response(notification)


@router.post(
    "/{notification_id}/read",
    response_model=MessageResponse,
    summary="Mark notification as read",
    description="Mark a single notification as read.",
)
async def mark_as_read(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Mark a notification as read."""
    service = NotificationService(db)
    
    success = await service.mark_as_read(
        notification_id=notification_id,
        user_id=current_user.id,
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    
    return MessageResponse(message="Notification marked as read")


@router.post(
    "/read-all",
    response_model=MessageResponse,
    summary="Mark all notifications as read",
    description="Mark all unread notifications as read.",
)
async def mark_all_as_read(
    entity_id: Optional[uuid.UUID] = Query(None, description="Only mark for specific entity"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Mark all notifications as read."""
    service = NotificationService(db)
    
    count = await service.mark_all_as_read(
        user_id=current_user.id,
        entity_id=entity_id,
    )
    
    return MessageResponse(message=f"Marked {count} notifications as read")


@router.delete(
    "/{notification_id}",
    response_model=MessageResponse,
    summary="Delete notification",
    description="Delete a notification.",
)
async def delete_notification(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Delete a notification."""
    service = NotificationService(db)
    
    success = await service.delete_notification(
        notification_id=notification_id,
        user_id=current_user.id,
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    
    return MessageResponse(message="Notification deleted")


@router.delete(
    "",
    response_model=MessageResponse,
    summary="Delete all read notifications",
    description="Delete all notifications that have been read.",
)
async def delete_read_notifications(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Delete all read notifications."""
    service = NotificationService(db)
    
    count = await service.delete_read_notifications(user_id=current_user.id)
    
    return MessageResponse(message=f"Deleted {count} read notifications")


@router.get(
    "/preferences/current",
    response_model=NotificationPreferences,
    summary="Get notification preferences",
    description="Get the current user's notification preferences.",
)
async def get_preferences(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get notification preferences."""
    service = NotificationService(db)
    
    preferences = await service.get_user_preferences(current_user.id)
    
    return NotificationPreferences(**preferences)


@router.put(
    "/preferences",
    response_model=NotificationPreferences,
    summary="Update notification preferences",
    description="Update the current user's notification preferences.",
)
async def update_preferences(
    request: UpdatePreferencesRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Update notification preferences."""
    service = NotificationService(db)
    
    update_data = request.model_dump(exclude_unset=True)
    preferences = await service.update_user_preferences(
        user_id=current_user.id,
        **update_data,
    )
    
    return NotificationPreferences(**preferences)


@router.get(
    "/types/list",
    summary="List notification types",
    description="Get all available notification types.",
)
async def list_notification_types():
    """List all notification types."""
    return {
        "types": [
            {"value": t.value, "name": t.name}
            for t in NotificationType
        ]
    }
