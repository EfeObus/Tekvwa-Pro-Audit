"""
Tekvwa Pro Audit - WebSocket Router

Real-time notification endpoints via WebSocket.

Endpoints:
- /ws/{token}: Main WebSocket connection endpoint
- Supports authentication via token parameter
- Channel subscription/unsubscription
- Heartbeat for connection health
"""

import uuid
import json
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query, status
from fastapi.responses import JSONResponse
from jose import jwt, JWTError
from pydantic import BaseModel

from app.config import settings
from app.services.websocket_manager import (
    WebSocketManager,
    NotificationChannel,
    get_ws_manager,
    get_notification_broadcaster,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["WebSocket"])


# ===========================================
# SCHEMAS
# ===========================================

class WebSocketStats(BaseModel):
    """WebSocket statistics response."""
    total_connections: int
    unique_users: int
    unique_tenants: int
    channels: dict
    queued_messages: int


class ChannelSubscription(BaseModel):
    """Channel subscription request."""
    channels: List[str]


# ===========================================
# HELPER FUNCTIONS
# ===========================================

def decode_ws_token(token: str) -> Optional[dict]:
    """
    Decode and validate WebSocket authentication token.
    
    Uses the same JWT secret as the main API authentication.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        return payload
    except JWTError as e:
        logger.warning(f"Invalid WebSocket token: {e}")
        return None


async def authenticate_websocket(
    websocket: WebSocket,
    token: Optional[str] = None
) -> Optional[dict]:
    """
    Authenticate WebSocket connection.
    
    Token can be provided via:
    1. Query parameter: ?token=xxx
    2. First message after connection
    """
    if token:
        return decode_ws_token(token)
    
    # Wait for authentication message
    try:
        auth_msg = await websocket.receive_json()
        if auth_msg.get("type") == "auth" and auth_msg.get("token"):
            return decode_ws_token(auth_msg["token"])
    except Exception as e:
        logger.error(f"WebSocket authentication error: {e}")
    
    return None


# ===========================================
# WEBSOCKET ENDPOINT
# ===========================================

@router.websocket("")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    channels: Optional[str] = Query(None),
):
    """
    Main WebSocket connection endpoint.
    
    Query Parameters:
        token: JWT authentication token
        channels: Comma-separated list of channels to subscribe to
    
    Message Types (client -> server):
        - {"type": "auth", "token": "..."}: Authenticate (if token not in query)
        - {"type": "subscribe", "channels": ["channel1", "channel2"]}
        - {"type": "unsubscribe", "channels": ["channel1"]}
        - {"type": "ping"}: Heartbeat
    
    Message Types (server -> client):
        - {"event": "connected", "data": {...}}
        - {"event": "subscribed", "data": {"channels": [...]}}
        - {"event": "unsubscribed", "data": {"channels": [...]}}
        - {"event": "pong", "data": {"timestamp": "..."}}
        - {"event": "<event_type>", "data": {...}}
    """
    ws_manager = get_ws_manager()
    connection_id = None
    
    try:
        # Authenticate
        user_data = await authenticate_websocket(websocket, token)
        
        if not user_data:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            logger.warning("WebSocket authentication failed")
            return
        
        user_id = uuid.UUID(user_data.get("sub"))
        tenant_id = uuid.UUID(user_data.get("tenant_id")) if user_data.get("tenant_id") else None
        entity_id = uuid.UUID(user_data.get("entity_id")) if user_data.get("entity_id") else None
        
        if not tenant_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            logger.warning(f"WebSocket connection rejected: no tenant_id for user {user_id}")
            return
        
        # Parse initial channels
        initial_channels = []
        if channels:
            initial_channels = [c.strip() for c in channels.split(",") if c.strip()]
        
        # Default channels
        if not initial_channels:
            initial_channels = [
                NotificationChannel.SYSTEM.value,
                NotificationChannel.APPROVALS.value,
            ]
        
        # Connect
        connection_id = await ws_manager.connect(
            websocket=websocket,
            user_id=user_id,
            tenant_id=tenant_id,
            entity_id=entity_id,
            channels=initial_channels,
        )
        
        # Message loop
        while True:
            try:
                data = await websocket.receive_json()
                msg_type = data.get("type")
                
                if msg_type == "ping":
                    await ws_manager.heartbeat(connection_id)
                
                elif msg_type == "subscribe":
                    channels_to_add = data.get("channels", [])
                    if channels_to_add:
                        await ws_manager.subscribe(connection_id, channels_to_add)
                
                elif msg_type == "unsubscribe":
                    channels_to_remove = data.get("channels", [])
                    if channels_to_remove:
                        await ws_manager.unsubscribe(connection_id, channels_to_remove)
                
                else:
                    # Unknown message type
                    await ws_manager.send_to_connection(
                        connection_id,
                        "error",
                        {"message": f"Unknown message type: {msg_type}"}
                    )
                    
            except json.JSONDecodeError:
                await ws_manager.send_to_connection(
                    connection_id,
                    "error",
                    {"message": "Invalid JSON message"}
                )
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {connection_id}")
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    
    finally:
        if connection_id:
            await ws_manager.disconnect(connection_id)


@router.websocket("/notifications")
async def notifications_websocket(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
):
    """
    Simplified WebSocket endpoint for notifications only.
    
    Auto-subscribes to all notification channels.
    """
    ws_manager = get_ws_manager()
    connection_id = None
    
    try:
        user_data = await authenticate_websocket(websocket, token)
        
        if not user_data:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        user_id = uuid.UUID(user_data.get("sub"))
        tenant_id = uuid.UUID(user_data.get("tenant_id")) if user_data.get("tenant_id") else None
        entity_id = uuid.UUID(user_data.get("entity_id")) if user_data.get("entity_id") else None
        
        if not tenant_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # Subscribe to all notification channels
        all_channels = [ch.value for ch in NotificationChannel]
        
        connection_id = await ws_manager.connect(
            websocket=websocket,
            user_id=user_id,
            tenant_id=tenant_id,
            entity_id=entity_id,
            channels=all_channels,
        )
        
        # Keep connection alive
        while True:
            try:
                data = await websocket.receive_json()
                if data.get("type") == "ping":
                    await ws_manager.heartbeat(connection_id)
            except json.JSONDecodeError:
                pass
    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Notifications WebSocket error: {e}")
    finally:
        if connection_id:
            await ws_manager.disconnect(connection_id)


# ===========================================
# HTTP ENDPOINTS FOR WEBSOCKET MANAGEMENT
# ===========================================

@router.get("/stats", response_model=WebSocketStats)
async def get_websocket_stats():
    """
    Get WebSocket connection statistics.
    
    Returns current connection counts, channel subscriptions, and queue status.
    """
    ws_manager = get_ws_manager()
    stats = ws_manager.get_stats()
    return WebSocketStats(**stats)


@router.get("/channels")
async def get_available_channels():
    """
    Get list of available notification channels.
    
    Returns channel names and descriptions.
    """
    return {
        "channels": [
            {
                "name": ch.value,
                "description": _get_channel_description(ch)
            }
            for ch in NotificationChannel
        ]
    }


def _get_channel_description(channel: NotificationChannel) -> str:
    """Get human-readable description for a channel."""
    descriptions = {
        NotificationChannel.BUDGET_ALERTS: "Budget variance and threshold alerts",
        NotificationChannel.FX_RATES: "Foreign exchange rate change notifications",
        NotificationChannel.APPROVALS: "Approval workflow notifications",
        NotificationChannel.INVOICES: "Invoice status updates",
        NotificationChannel.PAYMENTS: "Payment received notifications",
        NotificationChannel.SYSTEM: "System-wide announcements",
        NotificationChannel.AUDIT: "Audit log notifications (admin only)",
        NotificationChannel.CONSOLIDATION: "Consolidation process notifications",
        NotificationChannel.RECONCILIATION: "Bank reconciliation notifications",
    }
    return descriptions.get(channel, "Notifications")
