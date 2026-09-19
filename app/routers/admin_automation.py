"""
TekVwarho ProAudit - Platform Automation Router

Super Admin endpoints for managing workflow automation rules.
Automates platform operations, notifications, and scheduled tasks.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import uuid4
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import require_super_admin
from app.models.user import User
from app.models.audit_consolidated import AuditLog, AuditAction

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/automation",
    tags=["Admin - Automation"],
)


# ========= ENUMS =========

class TriggerType(str, Enum):
    SCHEDULED = "scheduled"
    EVENT = "event"
    THRESHOLD = "threshold"
    MANUAL = "manual"


class ActionType(str, Enum):
    SEND_EMAIL = "send_email"
    SEND_NOTIFICATION = "send_notification"
    WEBHOOK = "webhook"
    DISABLE_ACCOUNT = "disable_account"
    ENABLE_ACCOUNT = "enable_account"
    CREATE_AUDIT_LOG = "create_audit_log"
    RUN_SCRIPT = "run_script"
    GENERATE_REPORT = "generate_report"


class RuleStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


# ========= SCHEMAS =========

class TriggerConfig(BaseModel):
    """Trigger configuration."""
    type: TriggerType
    # Scheduled trigger config
    cron_expression: Optional[str] = None
    # Event trigger config
    event_name: Optional[str] = None
    # Threshold trigger config
    metric_name: Optional[str] = None
    operator: Optional[str] = None  # >, <, =, >=, <=
    threshold_value: Optional[float] = None


class ConditionConfig(BaseModel):
    """Condition for rule execution."""
    field: str
    operator: str  # equals, contains, greater_than, less_than, etc.
    value: Any


class ActionConfig(BaseModel):
    """Action to execute."""
    type: ActionType
    # Email action
    email_template: Optional[str] = None
    email_recipients: Optional[List[str]] = None
    # Notification action
    notification_title: Optional[str] = None
    notification_message: Optional[str] = None
    # Webhook action
    webhook_url: Optional[str] = None
    webhook_method: Optional[str] = "POST"
    webhook_headers: Optional[Dict[str, str]] = None
    webhook_payload: Optional[Dict[str, Any]] = None
    # Script action
    script_name: Optional[str] = None
    script_params: Optional[Dict[str, Any]] = None


class CreateAutomationRuleRequest(BaseModel):
    """Request to create an automation rule."""
    name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    trigger: TriggerConfig
    conditions: List[ConditionConfig] = Field(default=[])
    actions: List[ActionConfig] = Field(..., min_length=1)
    priority: int = Field(default=5, ge=1, le=10)
    max_executions_per_hour: Optional[int] = Field(None, ge=1, le=1000)


class UpdateAutomationRuleRequest(BaseModel):
    """Request to update an automation rule."""
    name: Optional[str] = Field(None, min_length=3, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    trigger: Optional[TriggerConfig] = None
    conditions: Optional[List[ConditionConfig]] = None
    actions: Optional[List[ActionConfig]] = None
    status: Optional[RuleStatus] = None
    priority: Optional[int] = Field(None, ge=1, le=10)
    max_executions_per_hour: Optional[int] = Field(None, ge=1, le=1000)


# ========= In-memory store =========

_automation_rules: List[Dict[str, Any]] = [
    {
        "id": str(uuid4()),
        "name": "Trial Expiry Warning",
        "description": "Send email notification when trial is about to expire",
        "trigger": {
            "type": TriggerType.SCHEDULED,
            "cron_expression": "0 9 * * *",  # Daily at 9 AM
        },
        "conditions": [
            {"field": "trial_days_remaining", "operator": "less_than", "value": 7}
        ],
        "actions": [
            {
                "type": ActionType.SEND_EMAIL,
                "email_template": "trial_expiry_warning",
                "email_recipients": ["{{organization.admin_email}}"],
            }
        ],
        "status": RuleStatus.ACTIVE,
        "priority": 7,
        "max_executions_per_hour": 50,
        "created_at": datetime.utcnow() - timedelta(days=60),
        "created_by": "info@tekvwa.org",
        "last_modified": datetime.utcnow() - timedelta(days=5),
        "execution_count": 234,
        "last_executed": datetime.utcnow() - timedelta(hours=15),
    },
    {
        "id": str(uuid4()),
        "name": "Failed Login Alert",
        "description": "Alert security team on multiple failed login attempts",
        "trigger": {
            "type": TriggerType.THRESHOLD,
            "metric_name": "failed_login_attempts",
            "operator": ">=",
            "threshold_value": 5,
        },
        "conditions": [
            {"field": "time_window_minutes", "operator": "less_than", "value": 15}
        ],
        "actions": [
            {
                "type": ActionType.SEND_NOTIFICATION,
                "notification_title": "Security Alert",
                "notification_message": "Multiple failed login attempts detected for {{user.email}}",
            },
            {
                "type": ActionType.CREATE_AUDIT_LOG,
            },
        ],
        "status": RuleStatus.ACTIVE,
        "priority": 10,
        "max_executions_per_hour": 100,
        "created_at": datetime.utcnow() - timedelta(days=90),
        "created_by": "info@tekvwa.org",
        "last_modified": datetime.utcnow() - timedelta(days=30),
        "execution_count": 47,
        "last_executed": datetime.utcnow() - timedelta(hours=48),
    },
    {
        "id": str(uuid4()),
        "name": "Daily Backup Report",
        "description": "Generate and email daily backup status report",
        "trigger": {
            "type": TriggerType.SCHEDULED,
            "cron_expression": "0 6 * * *",  # Daily at 6 AM
        },
        "conditions": [],
        "actions": [
            {
                "type": ActionType.GENERATE_REPORT,
                "script_name": "backup_status_report",
            },
            {
                "type": ActionType.SEND_EMAIL,
                "email_template": "backup_report",
                "email_recipients": ["info@tekvwa.org"],
            },
        ],
        "status": RuleStatus.ACTIVE,
        "priority": 5,
        "max_executions_per_hour": 1,
        "created_at": datetime.utcnow() - timedelta(days=120),
        "created_by": "info@tekvwa.org",
        "last_modified": datetime.utcnow() - timedelta(days=60),
        "execution_count": 120,
        "last_executed": datetime.utcnow() - timedelta(hours=18),
    },
]

_execution_logs: List[Dict[str, Any]] = []


# ========= ENDPOINTS =========

@router.get("")
async def list_automation_rules(
    status_filter: Optional[RuleStatus] = Query(None),
    trigger_type: Optional[TriggerType] = Query(None),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    List all automation rules.
    """
    rules = _automation_rules.copy()
    
    if status_filter:
        rules = [r for r in rules if r["status"] == status_filter]
    
    if trigger_type:
        rules = [r for r in rules if r["trigger"]["type"] == trigger_type]
    
    # Sort by priority (descending)
    rules.sort(key=lambda r: r["priority"], reverse=True)
    
    return {
        "success": True,
        "data": {
            "rules": rules,
            "total": len(rules),
            "active_count": len([r for r in _automation_rules if r["status"] == RuleStatus.ACTIVE]),
            "paused_count": len([r for r in _automation_rules if r["status"] == RuleStatus.PAUSED]),
        },
    }


@router.post("")
async def create_automation_rule(
    request: CreateAutomationRuleRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Create a new automation rule.
    """
    new_rule = {
        "id": str(uuid4()),
        "name": request.name,
        "description": request.description,
        "trigger": request.trigger.model_dump(),
        "conditions": [c.model_dump() for c in request.conditions],
        "actions": [a.model_dump() for a in request.actions],
        "status": RuleStatus.ACTIVE,
        "priority": request.priority,
        "max_executions_per_hour": request.max_executions_per_hour,
        "created_at": datetime.utcnow(),
        "created_by": current_user.email,
        "last_modified": datetime.utcnow(),
        "execution_count": 0,
        "last_executed": None,
    }
    
    _automation_rules.append(new_rule)
    
    # Log audit
    audit_log = AuditLog(
        user_id=current_user.id,
        action=AuditAction.AUTOMATION_RULE_CREATED,
        entity_type="automation_rule",
        entity_id=None,
        changes={"name": request.name, "trigger_type": request.trigger.type},
        ip_address="system",
    )
    db.add(audit_log)
    await db.commit()
    
    logger.info(f"Super Admin {current_user.email} created automation rule '{request.name}'")
    
    return {
        "success": True,
        "message": "Automation rule created",
        "data": new_rule,
    }


@router.get("/{rule_id}")
async def get_automation_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Get details of a specific automation rule.
    """
    rule = next((r for r in _automation_rules if r["id"] == rule_id), None)
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Automation rule not found",
        )
    
    return {
        "success": True,
        "data": rule,
    }


@router.put("/{rule_id}")
async def update_automation_rule(
    rule_id: str,
    request: UpdateAutomationRuleRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Update an automation rule.
    """
    rule = next((r for r in _automation_rules if r["id"] == rule_id), None)
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Automation rule not found",
        )
    
    old_values = {"name": rule["name"], "status": rule["status"]}
    
    if request.name:
        rule["name"] = request.name
    if request.description is not None:
        rule["description"] = request.description
    if request.trigger:
        rule["trigger"] = request.trigger.model_dump()
    if request.conditions is not None:
        rule["conditions"] = [c.model_dump() for c in request.conditions]
    if request.actions:
        rule["actions"] = [a.model_dump() for a in request.actions]
    if request.status:
        rule["status"] = request.status
    if request.priority is not None:
        rule["priority"] = request.priority
    if request.max_executions_per_hour is not None:
        rule["max_executions_per_hour"] = request.max_executions_per_hour
    
    rule["last_modified"] = datetime.utcnow()
    
    # Log audit
    audit_log = AuditLog(
        user_id=current_user.id,
        action=AuditAction.AUTOMATION_RULE_UPDATED,
        entity_type="automation_rule",
        entity_id=None,
        changes={"rule_id": rule_id, "old": old_values, "new": {"name": rule["name"], "status": str(rule["status"])}},
        ip_address="system",
    )
    db.add(audit_log)
    await db.commit()
    
    logger.info(f"Super Admin {current_user.email} updated automation rule '{rule['name']}'")
    
    return {
        "success": True,
        "message": "Automation rule updated",
        "data": rule,
    }


@router.delete("/{rule_id}")
async def delete_automation_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Delete an automation rule.
    """
    rule = next((r for r in _automation_rules if r["id"] == rule_id), None)
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Automation rule not found",
        )
    
    _automation_rules.remove(rule)
    
    # Log audit
    audit_log = AuditLog(
        user_id=current_user.id,
        action=AuditAction.AUTOMATION_RULE_DELETED,
        entity_type="automation_rule",
        entity_id=None,
        changes={"rule_id": rule_id, "name": rule["name"]},
        ip_address="system",
    )
    db.add(audit_log)
    await db.commit()
    
    logger.info(f"Super Admin {current_user.email} deleted automation rule '{rule['name']}'")
    
    return {
        "success": True,
        "message": "Automation rule deleted",
    }


@router.post("/{rule_id}/toggle")
async def toggle_automation_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Toggle an automation rule between active and paused.
    """
    rule = next((r for r in _automation_rules if r["id"] == rule_id), None)
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Automation rule not found",
        )
    
    old_status = rule["status"]
    
    if rule["status"] == RuleStatus.ACTIVE:
        rule["status"] = RuleStatus.PAUSED
    elif rule["status"] == RuleStatus.PAUSED:
        rule["status"] = RuleStatus.ACTIVE
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot toggle a disabled rule",
        )
    
    rule["last_modified"] = datetime.utcnow()
    
    # Log audit
    audit_log = AuditLog(
        user_id=current_user.id,
        action=AuditAction.AUTOMATION_RULE_TOGGLED,
        entity_type="automation_rule",
        entity_id=None,
        changes={"rule_id": rule_id, "old_status": str(old_status), "new_status": str(rule["status"])},
        ip_address="system",
    )
    db.add(audit_log)
    await db.commit()
    
    logger.info(f"Super Admin {current_user.email} toggled automation rule '{rule['name']}' to {rule['status']}")
    
    return {
        "success": True,
        "message": f"Automation rule {rule['status']}",
        "data": {"status": rule["status"]},
    }


@router.post("/{rule_id}/execute")
async def execute_automation_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Manually execute an automation rule (for testing).
    """
    rule = next((r for r in _automation_rules if r["id"] == rule_id), None)
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Automation rule not found",
        )
    
    # Simulate execution
    execution_log = {
        "id": str(uuid4()),
        "rule_id": rule_id,
        "rule_name": rule["name"],
        "trigger_type": "manual",
        "triggered_by": current_user.email,
        "executed_at": datetime.utcnow(),
        "status": "success",
        "actions_executed": len(rule["actions"]),
        "duration_ms": 245,
        "details": "Manual execution triggered by Super Admin",
    }
    
    _execution_logs.append(execution_log)
    
    rule["execution_count"] += 1
    rule["last_executed"] = datetime.utcnow()
    
    # Log audit
    audit_log = AuditLog(
        user_id=current_user.id,
        action=AuditAction.AUTOMATION_RULE_EXECUTED,
        entity_type="automation_rule",
        entity_id=None,
        changes={"rule_id": rule_id, "name": rule["name"], "trigger": "manual"},
        ip_address="system",
    )
    db.add(audit_log)
    await db.commit()
    
    logger.info(f"Super Admin {current_user.email} manually executed automation rule '{rule['name']}'")
    
    return {
        "success": True,
        "message": "Automation rule executed",
        "data": execution_log,
    }


@router.get("/{rule_id}/logs")
async def get_rule_execution_logs(
    rule_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    Get execution logs for an automation rule.
    """
    rule = next((r for r in _automation_rules if r["id"] == rule_id), None)
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Automation rule not found",
        )
    
    logs = [l for l in _execution_logs if l["rule_id"] == rule_id]
    logs.sort(key=lambda l: l["executed_at"], reverse=True)
    
    return {
        "success": True,
        "data": {
            "rule_id": rule_id,
            "rule_name": rule["name"],
            "logs": logs[:limit],
            "total_executions": rule["execution_count"],
        },
    }


@router.get("/triggers/types")
async def list_trigger_types(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    List available trigger types and their configurations.
    """
    triggers = [
        {
            "type": TriggerType.SCHEDULED,
            "name": "Scheduled",
            "description": "Execute at specific times using cron expressions",
            "config_fields": ["cron_expression"],
        },
        {
            "type": TriggerType.EVENT,
            "name": "Event",
            "description": "Execute when a specific event occurs",
            "config_fields": ["event_name"],
            "available_events": [
                "user.created", "user.login", "user.failed_login",
                "organization.created", "organization.upgraded",
                "transaction.created", "invoice.paid", "invoice.overdue",
                "audit.anomaly_detected", "backup.completed", "backup.failed",
            ],
        },
        {
            "type": TriggerType.THRESHOLD,
            "name": "Threshold",
            "description": "Execute when a metric crosses a threshold",
            "config_fields": ["metric_name", "operator", "threshold_value"],
            "available_metrics": [
                "failed_login_attempts", "active_sessions", "storage_usage_percent",
                "cpu_usage_percent", "memory_usage_percent", "api_error_rate",
                "response_time_ms", "active_users",
            ],
        },
        {
            "type": TriggerType.MANUAL,
            "name": "Manual",
            "description": "Execute only when manually triggered",
            "config_fields": [],
        },
    ]
    
    return {
        "success": True,
        "data": triggers,
    }


@router.get("/actions/types")
async def list_action_types(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_super_admin()),
):
    """
    List available action types and their configurations.
    """
    actions = [
        {
            "type": ActionType.SEND_EMAIL,
            "name": "Send Email",
            "description": "Send an email notification",
            "config_fields": ["email_template", "email_recipients"],
        },
        {
            "type": ActionType.SEND_NOTIFICATION,
            "name": "Send Notification",
            "description": "Send an in-app notification",
            "config_fields": ["notification_title", "notification_message"],
        },
        {
            "type": ActionType.WEBHOOK,
            "name": "Webhook",
            "description": "Call an external webhook",
            "config_fields": ["webhook_url", "webhook_method", "webhook_headers", "webhook_payload"],
        },
        {
            "type": ActionType.DISABLE_ACCOUNT,
            "name": "Disable Account",
            "description": "Disable a user or organization account",
            "config_fields": [],
        },
        {
            "type": ActionType.CREATE_AUDIT_LOG,
            "name": "Create Audit Log",
            "description": "Create an audit log entry",
            "config_fields": [],
        },
        {
            "type": ActionType.GENERATE_REPORT,
            "name": "Generate Report",
            "description": "Generate a system report",
            "config_fields": ["script_name", "script_params"],
        },
    ]
    
    return {
        "success": True,
        "data": actions,
    }
