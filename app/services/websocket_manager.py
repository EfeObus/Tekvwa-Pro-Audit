"""
Tekvwa Pro Audit - WebSocket Manager

Real-time notification delivery via WebSockets.

Features:
- Connection management per user/tenant
- Channel-based subscriptions (budget_alerts, fx_rates, approvals)
- Broadcast to specific users, tenants, or all connections
- Heartbeat and automatic reconnection support
- Message queuing for offline users

Channels:
- budget_alerts: Budget variance and threshold alerts
- fx_rates: FX rate change notifications
- approvals: Approval workflow notifications
- system: System-wide announcements
- audit: Audit log notifications (for admins)
"""

import asyncio
import uuid
import json
import logging
from datetime import datetime
from typing import Dict, Set, Optional, Any, List
from dataclasses import dataclass, field
from enum import Enum

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class NotificationChannel(str, Enum):
    """WebSocket notification channels."""
    BUDGET_ALERTS = "budget_alerts"
    FX_RATES = "fx_rates"
    APPROVALS = "approvals"
    INVOICES = "invoices"
    PAYMENTS = "payments"
    SYSTEM = "system"
    AUDIT = "audit"
    CONSOLIDATION = "consolidation"
    RECONCILIATION = "reconciliation"


@dataclass
class WebSocketConnection:
    """Represents a WebSocket connection."""
    websocket: WebSocket
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    entity_id: Optional[uuid.UUID] = None
    channels: Set[str] = field(default_factory=set)
    connected_at: datetime = field(default_factory=datetime.utcnow)
    last_heartbeat: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": str(self.user_id),
            "tenant_id": str(self.tenant_id),
            "entity_id": str(self.entity_id) if self.entity_id else None,
            "channels": list(self.channels),
            "connected_at": self.connected_at.isoformat(),
        }


@dataclass
class QueuedMessage:
    """Message queued for offline delivery."""
    user_id: uuid.UUID
    channel: str
    event_type: str
    data: Dict[str, Any]
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None


class WebSocketManager:
    """
    Manages WebSocket connections for real-time notifications.
    
    Implements:
    - Connection tracking by user and tenant
    - Channel-based pub/sub
    - Message broadcasting
    - Offline message queuing
    """
    
    _instance: Optional["WebSocketManager"] = None
    
    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # Connection storage: connection_id -> WebSocketConnection
        self._connections: Dict[str, WebSocketConnection] = {}
        
        # Index by user_id for quick lookup
        self._user_connections: Dict[uuid.UUID, Set[str]] = {}
        
        # Index by tenant_id for tenant-wide broadcasts
        self._tenant_connections: Dict[uuid.UUID, Set[str]] = {}
        
        # Index by channel for channel broadcasts
        self._channel_connections: Dict[str, Set[str]] = {}
        
        # Message queue for offline users
        self._message_queue: Dict[uuid.UUID, List[QueuedMessage]] = {}
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
        
        self._initialized = True
        logger.info("WebSocketManager initialized")
    
    async def connect(
        self,
        websocket: WebSocket,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        entity_id: Optional[uuid.UUID] = None,
        channels: Optional[List[str]] = None
    ) -> str:
        """
        Accept and register a new WebSocket connection.
        
        Returns:
            Connection ID
        """
        await websocket.accept()
        connection_id = str(uuid.uuid4())
        
        async with self._lock:
            # Create connection object
            connection = WebSocketConnection(
                websocket=websocket,
                user_id=user_id,
                tenant_id=tenant_id,
                entity_id=entity_id,
                channels=set(channels or [NotificationChannel.SYSTEM.value]),
            )
            
            # Store connection
            self._connections[connection_id] = connection
            
            # Index by user
            if user_id not in self._user_connections:
                self._user_connections[user_id] = set()
            self._user_connections[user_id].add(connection_id)
            
            # Index by tenant
            if tenant_id not in self._tenant_connections:
                self._tenant_connections[tenant_id] = set()
            self._tenant_connections[tenant_id].add(connection_id)
            
            # Index by channels
            for channel in connection.channels:
                if channel not in self._channel_connections:
                    self._channel_connections[channel] = set()
                self._channel_connections[channel].add(connection_id)
        
        logger.info(
            f"WebSocket connected: user={user_id}, tenant={tenant_id}, "
            f"channels={channels}, connection_id={connection_id}"
        )
        
        # Send queued messages
        await self._deliver_queued_messages(user_id)
        
        # Send connection confirmation
        await self.send_to_connection(
            connection_id,
            "connected",
            {
                "connection_id": connection_id,
                "channels": list(connection.channels),
                "timestamp": datetime.utcnow().isoformat(),
            }
        )
        
        return connection_id
    
    async def disconnect(self, connection_id: str):
        """Remove a WebSocket connection."""
        async with self._lock:
            if connection_id not in self._connections:
                return
            
            connection = self._connections[connection_id]
            
            # Remove from user index
            if connection.user_id in self._user_connections:
                self._user_connections[connection.user_id].discard(connection_id)
                if not self._user_connections[connection.user_id]:
                    del self._user_connections[connection.user_id]
            
            # Remove from tenant index
            if connection.tenant_id in self._tenant_connections:
                self._tenant_connections[connection.tenant_id].discard(connection_id)
                if not self._tenant_connections[connection.tenant_id]:
                    del self._tenant_connections[connection.tenant_id]
            
            # Remove from channel indices
            for channel in connection.channels:
                if channel in self._channel_connections:
                    self._channel_connections[channel].discard(connection_id)
                    if not self._channel_connections[channel]:
                        del self._channel_connections[channel]
            
            # Remove connection
            del self._connections[connection_id]
        
        logger.info(f"WebSocket disconnected: connection_id={connection_id}")
    
    async def subscribe(self, connection_id: str, channels: List[str]):
        """Subscribe a connection to additional channels."""
        async with self._lock:
            if connection_id not in self._connections:
                return
            
            connection = self._connections[connection_id]
            
            for channel in channels:
                connection.channels.add(channel)
                if channel not in self._channel_connections:
                    self._channel_connections[channel] = set()
                self._channel_connections[channel].add(connection_id)
        
        await self.send_to_connection(
            connection_id,
            "subscribed",
            {"channels": channels}
        )
    
    async def unsubscribe(self, connection_id: str, channels: List[str]):
        """Unsubscribe a connection from channels."""
        async with self._lock:
            if connection_id not in self._connections:
                return
            
            connection = self._connections[connection_id]
            
            for channel in channels:
                connection.channels.discard(channel)
                if channel in self._channel_connections:
                    self._channel_connections[channel].discard(connection_id)
        
        await self.send_to_connection(
            connection_id,
            "unsubscribed",
            {"channels": channels}
        )
    
    async def send_to_connection(
        self,
        connection_id: str,
        event_type: str,
        data: Dict[str, Any]
    ) -> bool:
        """Send a message to a specific connection."""
        if connection_id not in self._connections:
            return False
        
        connection = self._connections[connection_id]
        
        try:
            message = {
                "event": event_type,
                "data": data,
                "timestamp": datetime.utcnow().isoformat(),
            }
            await connection.websocket.send_json(message)
            return True
        except Exception as e:
            logger.error(f"Error sending to connection {connection_id}: {e}")
            await self.disconnect(connection_id)
            return False
    
    async def send_to_user(
        self,
        user_id: uuid.UUID,
        event_type: str,
        data: Dict[str, Any],
        channel: Optional[str] = None,
        queue_if_offline: bool = True
    ):
        """
        Send a message to all connections for a user.
        
        Args:
            user_id: Target user
            event_type: Type of event
            data: Event data
            channel: Optional channel filter
            queue_if_offline: Whether to queue if user is offline
        """
        connection_ids = self._user_connections.get(user_id, set())
        
        if not connection_ids and queue_if_offline:
            # User is offline, queue the message
            await self._queue_message(user_id, channel or "system", event_type, data)
            return
        
        for connection_id in list(connection_ids):
            connection = self._connections.get(connection_id)
            if connection:
                # Check channel subscription if specified
                if channel and channel not in connection.channels:
                    continue
                await self.send_to_connection(connection_id, event_type, data)
    
    async def send_to_tenant(
        self,
        tenant_id: uuid.UUID,
        event_type: str,
        data: Dict[str, Any],
        channel: Optional[str] = None
    ):
        """Send a message to all users in a tenant."""
        connection_ids = self._tenant_connections.get(tenant_id, set())
        
        for connection_id in list(connection_ids):
            connection = self._connections.get(connection_id)
            if connection:
                if channel and channel not in connection.channels:
                    continue
                await self.send_to_connection(connection_id, event_type, data)
    
    async def broadcast_to_channel(
        self,
        channel: str,
        event_type: str,
        data: Dict[str, Any],
        exclude_user: Optional[uuid.UUID] = None
    ):
        """Broadcast a message to all connections subscribed to a channel."""
        connection_ids = self._channel_connections.get(channel, set())
        
        for connection_id in list(connection_ids):
            connection = self._connections.get(connection_id)
            if connection:
                if exclude_user and connection.user_id == exclude_user:
                    continue
                await self.send_to_connection(connection_id, event_type, data)
    
    async def broadcast_all(self, event_type: str, data: Dict[str, Any]):
        """Broadcast to all connections (e.g., system announcements)."""
        for connection_id in list(self._connections.keys()):
            await self.send_to_connection(connection_id, event_type, data)
    
    async def _queue_message(
        self,
        user_id: uuid.UUID,
        channel: str,
        event_type: str,
        data: Dict[str, Any]
    ):
        """Queue a message for offline delivery."""
        async with self._lock:
            if user_id not in self._message_queue:
                self._message_queue[user_id] = []
            
            # Limit queue size per user
            if len(self._message_queue[user_id]) >= 100:
                self._message_queue[user_id].pop(0)
            
            self._message_queue[user_id].append(QueuedMessage(
                user_id=user_id,
                channel=channel,
                event_type=event_type,
                data=data,
            ))
    
    async def _deliver_queued_messages(self, user_id: uuid.UUID):
        """Deliver queued messages when user connects."""
        async with self._lock:
            if user_id not in self._message_queue:
                return
            
            messages = self._message_queue.pop(user_id, [])
        
        for msg in messages:
            await self.send_to_user(
                user_id,
                msg.event_type,
                msg.data,
                channel=msg.channel,
                queue_if_offline=False
            )
    
    async def heartbeat(self, connection_id: str):
        """Update heartbeat timestamp for a connection."""
        if connection_id in self._connections:
            self._connections[connection_id].last_heartbeat = datetime.utcnow()
            await self.send_to_connection(
                connection_id,
                "pong",
                {"timestamp": datetime.utcnow().isoformat()}
            )
    
    def get_connection_count(self) -> int:
        """Get total number of active connections."""
        return len(self._connections)
    
    def get_user_connections(self, user_id: uuid.UUID) -> int:
        """Get number of connections for a user."""
        return len(self._user_connections.get(user_id, set()))
    
    def get_stats(self) -> Dict[str, Any]:
        """Get WebSocket manager statistics."""
        return {
            "total_connections": len(self._connections),
            "unique_users": len(self._user_connections),
            "unique_tenants": len(self._tenant_connections),
            "channels": {
                channel: len(connection_ids)
                for channel, connection_ids in self._channel_connections.items()
            },
            "queued_messages": sum(
                len(msgs) for msgs in self._message_queue.values()
            ),
        }


# ===========================================
# NOTIFICATION HELPERS
# ===========================================

class NotificationBroadcaster:
    """
    High-level notification broadcasting utilities.
    
    Use these methods from services to send real-time notifications.
    """
    
    def __init__(self, ws_manager: Optional[WebSocketManager] = None):
        self.ws_manager = ws_manager or WebSocketManager()
    
    async def notify_budget_alert(
        self,
        tenant_id: uuid.UUID,
        entity_id: uuid.UUID,
        budget_id: uuid.UUID,
        budget_name: str,
        alert_type: str,  # "threshold_exceeded", "variance_warning", "status_change"
        details: Dict[str, Any],
        target_users: Optional[List[uuid.UUID]] = None
    ):
        """
        Send budget alert notification.
        
        Args:
            tenant_id: Tenant ID
            entity_id: Business entity ID
            budget_id: Budget ID
            budget_name: Budget name for display
            alert_type: Type of alert
            details: Alert details (variance %, accounts, etc.)
            target_users: Optional specific users to notify
        """
        data = {
            "budget_id": str(budget_id),
            "budget_name": budget_name,
            "entity_id": str(entity_id),
            "alert_type": alert_type,
            "details": details,
        }
        
        if target_users:
            for user_id in target_users:
                await self.ws_manager.send_to_user(
                    user_id,
                    "budget_alert",
                    data,
                    channel=NotificationChannel.BUDGET_ALERTS.value
                )
        else:
            await self.ws_manager.send_to_tenant(
                tenant_id,
                "budget_alert",
                data,
                channel=NotificationChannel.BUDGET_ALERTS.value
            )
    
    async def notify_fx_rate_change(
        self,
        tenant_id: uuid.UUID,
        from_currency: str,
        to_currency: str,
        old_rate: float,
        new_rate: float,
        rate_date: str,
        change_pct: float
    ):
        """Send FX rate change notification."""
        data = {
            "from_currency": from_currency,
            "to_currency": to_currency,
            "old_rate": old_rate,
            "new_rate": new_rate,
            "rate_date": rate_date,
            "change_pct": change_pct,
            "direction": "up" if new_rate > old_rate else "down",
        }
        
        await self.ws_manager.send_to_tenant(
            tenant_id,
            "fx_rate_change",
            data,
            channel=NotificationChannel.FX_RATES.value
        )
    
    async def notify_approval_request(
        self,
        user_id: uuid.UUID,
        request_type: str,  # "budget", "journal", "payment", "revaluation"
        request_id: uuid.UUID,
        request_title: str,
        requestor_name: str,
        priority: str = "normal"
    ):
        """Send approval request notification."""
        data = {
            "request_type": request_type,
            "request_id": str(request_id),
            "request_title": request_title,
            "requestor_name": requestor_name,
            "priority": priority,
            "action_url": f"/approvals/{request_type}/{request_id}",
        }
        
        await self.ws_manager.send_to_user(
            user_id,
            "approval_request",
            data,
            channel=NotificationChannel.APPROVALS.value
        )
    
    async def notify_approval_decision(
        self,
        user_id: uuid.UUID,
        request_type: str,
        request_id: uuid.UUID,
        request_title: str,
        decision: str,  # "approved", "rejected", "more_info_needed"
        approver_name: str,
        comments: Optional[str] = None
    ):
        """Send approval decision notification."""
        data = {
            "request_type": request_type,
            "request_id": str(request_id),
            "request_title": request_title,
            "decision": decision,
            "approver_name": approver_name,
            "comments": comments,
        }
        
        await self.ws_manager.send_to_user(
            user_id,
            "approval_decision",
            data,
            channel=NotificationChannel.APPROVALS.value
        )
    
    async def notify_invoice_status(
        self,
        tenant_id: uuid.UUID,
        invoice_id: uuid.UUID,
        invoice_number: str,
        status: str,
        customer_name: str,
        amount: float,
        currency: str = "NGN"
    ):
        """Send invoice status change notification."""
        data = {
            "invoice_id": str(invoice_id),
            "invoice_number": invoice_number,
            "status": status,
            "customer_name": customer_name,
            "amount": amount,
            "currency": currency,
        }
        
        await self.ws_manager.send_to_tenant(
            tenant_id,
            "invoice_status",
            data,
            channel=NotificationChannel.INVOICES.value
        )
    
    async def notify_payment_received(
        self,
        tenant_id: uuid.UUID,
        payment_id: uuid.UUID,
        invoice_number: Optional[str],
        customer_name: str,
        amount: float,
        payment_method: str,
        currency: str = "NGN"
    ):
        """Send payment received notification."""
        data = {
            "payment_id": str(payment_id),
            "invoice_number": invoice_number,
            "customer_name": customer_name,
            "amount": amount,
            "payment_method": payment_method,
            "currency": currency,
        }
        
        await self.ws_manager.send_to_tenant(
            tenant_id,
            "payment_received",
            data,
            channel=NotificationChannel.PAYMENTS.value
        )
    
    async def notify_consolidation_complete(
        self,
        tenant_id: uuid.UUID,
        group_id: uuid.UUID,
        group_name: str,
        period: str,
        status: str,
        summary: Dict[str, Any]
    ):
        """Send consolidation completion notification."""
        data = {
            "group_id": str(group_id),
            "group_name": group_name,
            "period": period,
            "status": status,
            "summary": summary,
        }
        
        await self.ws_manager.send_to_tenant(
            tenant_id,
            "consolidation_complete",
            data,
            channel=NotificationChannel.CONSOLIDATION.value
        )
    
    async def notify_system_announcement(
        self,
        title: str,
        message: str,
        priority: str = "normal",
        action_url: Optional[str] = None
    ):
        """Broadcast system-wide announcement."""
        data = {
            "title": title,
            "message": message,
            "priority": priority,
            "action_url": action_url,
        }
        
        await self.ws_manager.broadcast_all("system_announcement", data)


# Global instance
ws_manager = WebSocketManager()
notification_broadcaster = NotificationBroadcaster(ws_manager)


def get_ws_manager() -> WebSocketManager:
    """Get the global WebSocket manager instance."""
    return ws_manager


def get_notification_broadcaster() -> NotificationBroadcaster:
    """Get the global notification broadcaster instance."""
    return notification_broadcaster
