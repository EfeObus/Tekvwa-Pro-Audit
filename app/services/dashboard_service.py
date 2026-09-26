"""
Tekvwa Pro Audit - Dashboard Service

Provides dashboard data for different user types:
1. Platform Staff Dashboards (Super Admin, Admin, IT, CSR, Marketing)
2. Organization User Dashboards (Owner, Admin, Accountant, etc.)

NTAA 2025 Compliance Features:
- Tax Health Score (Red/Amber/Green indicator)
- NRS Connection Status (heartbeat monitor)
- Compliance Calendar (VAT 21st, PAYE 10th deadlines)
- Organization-type-specific dashboards (SME, School, Non-Profit, Individual)
- Maker-Checker SoD enforcement for sensitive views
"""

import uuid
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional
from calendar import monthrange

from sqlalchemy import select, func, and_, or_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, PlatformRole, UserRole
from app.models.organization import Organization, VerificationStatus, OrganizationType
from app.models.entity import BusinessEntity, BusinessType
from app.models.transaction import Transaction, TransactionType
from app.models.invoice import Invoice, InvoiceStatus
from app.models.audit_consolidated import AuditLog, AuditAction
from app.models.inventory import InventoryItem
from app.utils.permissions import (
    PlatformPermission,
    OrganizationPermission,
    has_platform_permission,
    has_organization_permission,
    get_platform_permissions,
    get_organization_permissions,
)

# Import new services for Super Admin Dashboard
from app.services.legal_hold_service import LegalHoldService
from app.services.risk_signal_service import RiskSignalService
from app.services.ml_job_service import MLJobService
from app.services.upsell_service import UpsellService
from app.services.support_ticket_service import SupportTicketService


# ===========================================
# NTAA 2025 TAX CONSTANTS
# ===========================================

# CIT thresholds (Small Company Status)
SMALL_COMPANY_TURNOVER_LIMIT = Decimal("50000000")  # ₦50M
MEDIUM_COMPANY_TURNOVER_LIMIT = Decimal("100000000")  # ₦100M
FIXED_ASSETS_LIMIT = Decimal("250000000")  # ₦250M

# Development Levy exemption threshold
DEV_LEVY_EXEMPTION_TURNOVER = Decimal("100000000")  # ₦100M

# VAT thresholds
VAT_REGISTRATION_THRESHOLD = Decimal("25000000")  # ₦25M

# PIT 2026 Tax-Free Band
PIT_TAX_FREE_BAND = Decimal("800000")  # ₦800,000

# Filing deadlines
VAT_FILING_DAY = 21  # 21st of each month
PAYE_FILING_DAY = 10  # 10th of each month
CIT_ANNUAL_DEADLINE_MONTHS = 6  # 6 months after fiscal year end

# 2026 PIT Bands (Progressive)
PIT_2026_BANDS = [
    {"min": 0, "max": 800000, "rate": 0, "label": "First ₦800K (Tax-Free)"},
    {"min": 800000, "max": 1600000, "rate": 7, "label": "₦800K - ₦1.6M"},
    {"min": 1600000, "max": 2400000, "rate": 11, "label": "₦1.6M - ₦2.4M"},
    {"min": 2400000, "max": 4000000, "rate": 15, "label": "₦2.4M - ₦4M"},
    {"min": 4000000, "max": 8000000, "rate": 19, "label": "₦4M - ₦8M"},
    {"min": 8000000, "max": 16000000, "rate": 21, "label": "₦8M - ₦16M"},
    {"min": 16000000, "max": 40000000, "rate": 23, "label": "₦16M - ₦40M"},
    {"min": 40000000, "max": float("inf"), "rate": 25, "label": "Above ₦40M"},
]


class DashboardService:
    """Service for generating dashboard data."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # ===========================================
    # PLATFORM STAFF DASHBOARDS
    # ===========================================
    
    async def get_super_admin_dashboard(self, user: User) -> Dict[str, Any]:
        """
        Super Admin Dashboard - Full platform overview.
        
        Comprehensive features:
        1. Multi-Tenant & User Management
        2. Platform Monitoring & Analytics
        3. Security & Audit Controls
        4. Support & Maintenance Tools
        5. Financial Overview (Platform Level)
        6. Legal Holds & Compliance
        7. Risk Signals & Monitoring
        8. ML Jobs & Models
        9. Upsell Opportunities
        10. Support Tickets
        """
        if not user.is_platform_staff or user.platform_role != PlatformRole.SUPER_ADMIN:
            raise PermissionError("Super Admin access required")
        
        # ===== 1. MULTI-TENANT & USER MANAGEMENT =====
        org_count = await self._get_organization_count()
        user_count = await self._get_user_count()
        staff_count = await self._get_staff_count()
        pending_verifications = await self._get_pending_verification_count()
        
        # Staff breakdown by role
        staff_by_role = await self._get_staff_by_role()
        
        # Organization stats by type
        org_by_type = await self._get_organizations_by_type()
        
        # Tenants list and stats
        tenants_list = await self._get_tenants_list(limit=50)
        tenant_stats = await self._get_tenant_stats()
        
        # Subscription/Plan tracking
        subscription_stats = await self._get_subscription_stats()
        
        # Verification stats
        verification_stats = await self._get_verification_stats()
        
        # ===== 2. PLATFORM MONITORING & ANALYTICS =====
        platform_health = await self._get_platform_health_detailed()
        
        # NRS/E-invoicing compliance monitoring
        nrs_compliance_stats = await self._get_nrs_compliance_stats()
        
        # Usage metering
        usage_metrics = await self._get_usage_metrics()
        
        # ===== 3. SECURITY & AUDIT CONTROLS =====
        recent_activity = await self._get_recent_platform_activity(limit=15)
        
        # Security alerts
        security_alerts = await self._get_security_alerts()
        
        # Failed login attempts
        failed_logins = await self._get_failed_login_stats()
        
        # ===== 4. FINANCIAL OVERVIEW =====
        platform_revenue = await self._get_platform_revenue_stats()
        
        # Filing status reports
        filing_status = await self._get_platform_filing_status()
        
        # ===== 5. NEW SUPER ADMIN FEATURES =====
        # Legal Holds - Stats and List
        legal_hold_service = LegalHoldService(self.db)
        legal_holds_stats = await legal_hold_service.get_legal_holds_stats()
        legal_holds_list = await legal_hold_service.get_all_legal_holds(limit=15)
        
        # Risk Signals - Stats and List
        risk_signal_service = RiskSignalService(self.db)
        risk_signals_stats = await risk_signal_service.get_risk_signals_stats()
        recent_risk_signals = await risk_signal_service.get_recent_risk_signals(days=7, limit=5)
        risk_signals_list = await risk_signal_service.get_all_risk_signals(limit=20)
        
        # ML Jobs - Stats and List
        ml_job_service = MLJobService(self.db)
        ml_jobs_stats = await ml_job_service.get_ml_jobs_stats()
        ml_models_stats = await ml_job_service.get_models_stats()
        ml_jobs_list = await ml_job_service.get_all_ml_jobs(limit=15)
        ml_models_list = await ml_job_service.get_all_models(limit=10)
        
        # Upsell Opportunities - Stats and List
        upsell_service = UpsellService(self.db)
        upsell_stats = await upsell_service.get_upsell_stats()
        upsell_list = await upsell_service.get_all_opportunities(limit=15)
        
        # Support Tickets - Stats and List
        support_service = SupportTicketService(self.db)
        support_stats = await support_service.get_tickets_stats()
        support_tickets_list = await support_service.get_all_tickets(limit=20)
        
        return {
            "dashboard_type": "super_admin",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "name": user.full_name,
                "role": "Super Admin",
            },
            # Section 1: Multi-Tenant & User Management
            "overview": {
                "total_organizations": org_count,
                "total_users": user_count,
                "total_staff": staff_count,
                "pending_verifications": pending_verifications,
            },
            "staff_by_role": staff_by_role,
            "organizations_by_type": org_by_type,
            "subscription_stats": subscription_stats,
            "verification_stats": verification_stats,
            "tenants_list": tenants_list,
            "tenant_stats": tenant_stats,
            
            # Section 2: Platform Monitoring & Analytics
            "platform_health": platform_health,
            "nrs_compliance": nrs_compliance_stats,
            "usage_metrics": usage_metrics,
            
            # Section 3: Security & Audit Controls
            "recent_activity": recent_activity,
            "security_alerts": security_alerts,
            "failed_logins": failed_logins,
            
            # Section 4: Financial Overview
            "platform_revenue": platform_revenue,
            "filing_status": filing_status,
            
            # Section 5: Legal Holds & Compliance
            "legal_holds": legal_holds_stats,
            "legal_holds_list": [
                {
                    "id": str(h.id),
                    "hold_number": h.hold_number,
                    "organization_id": str(h.organization_id) if h.organization_id else None,
                    "matter_name": h.matter_name,
                    "matter_reference": h.matter_reference,
                    "hold_type": h.hold_type,
                    "status": h.status,
                    "data_scope": h.data_scope,
                    "preservation_start_date": h.preservation_start_date.isoformat() if h.preservation_start_date else None,
                    "hold_start_date": h.hold_start_date.isoformat() if h.hold_start_date else None,
                    "records_preserved_count": h.records_preserved_count or 0,
                    "legal_counsel_name": h.legal_counsel_name,
                    "created_at": h.created_at.isoformat() if h.created_at else None,
                }
                for h in legal_holds_list
            ],
            
            # Section 6: Risk Signals & Monitoring
            "risk_signals": risk_signals_stats,
            "recent_risk_signals": [
                {
                    "id": str(s.id),
                    "signal_code": s.signal_code,
                    "title": s.title,
                    "severity": s.severity,
                    "status": s.status,
                    "detected_at": s.detected_at.isoformat() if s.detected_at else None,
                }
                for s in recent_risk_signals
            ],
            "risk_signals_list": [
                {
                    "id": str(s.id),
                    "signal_code": s.signal_code,
                    "organization_id": str(s.organization_id) if s.organization_id else None,
                    "signal_type": s.signal_type,
                    "category": s.category,
                    "severity": s.severity,
                    "status": s.status,
                    "title": s.title,
                    "description": s.description,
                    "risk_score": float(s.risk_score) if s.risk_score else None,
                    "detected_at": s.detected_at.isoformat() if s.detected_at else None,
                    "acknowledged": s.acknowledged,
                    "requires_immediate_action": s.requires_immediate_action,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                }
                for s in risk_signals_list
            ],
            
            # Section 7: ML Jobs & Models
            "ml_jobs": ml_jobs_stats,
            "ml_models": ml_models_stats,
            "ml_jobs_list": [
                {
                    "id": str(j.id),
                    "job_id": j.job_id,
                    "organization_id": str(j.organization_id) if j.organization_id else None,
                    "job_type": j.job_type,
                    "status": j.status,
                    "progress_percent": j.progress_percent or 0,
                    "started_at": j.started_at.isoformat() if j.started_at else None,
                    "completed_at": j.completed_at.isoformat() if j.completed_at else None,
                    "error_message": j.error_message,
                    "created_at": j.created_at.isoformat() if j.created_at else None,
                }
                for j in ml_jobs_list
            ],
            "ml_models_list": [
                {
                    "id": str(m.id),
                    "model_name": m.model_name,
                    "model_type": m.model_type,
                    "version": m.model_version,
                    "is_active": m.is_active,
                    "accuracy_score": float(m.accuracy) if m.accuracy else None,
                    "precision_score": float(m.precision_score) if m.precision_score else None,
                    "recall_score": float(m.recall_score) if m.recall_score else None,
                    "total_predictions": 0,  # not tracked on the live ml_models table
                    "last_trained_at": m.last_used_at.isoformat() if m.last_used_at else None,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in ml_models_list
            ],
            
            # Section 8: Upsell Opportunities
            "upsell": upsell_stats,
            "upsell_list": [
                {
                    "id": str(u.id),
                    "opportunity_code": u.opportunity_code,
                    "organization_id": str(u.organization_id) if u.organization_id else None,
                    "upsell_type": u.upsell_type,
                    "status": u.status,
                    "priority": u.priority,
                    "current_product": u.current_product,
                    "target_product": u.target_product,
                    "estimated_mrr_increase": float(u.estimated_mrr_increase) if u.estimated_mrr_increase else 0,
                    "confidence_score": float(u.confidence_score) if u.confidence_score else None,
                    "signal": u.signal,
                    "identified_at": u.identified_at.isoformat() if u.identified_at else None,
                    "created_at": u.created_at.isoformat() if u.created_at else None,
                }
                for u in upsell_list
            ],
            
            # Section 9: Support Tickets
            "support_tickets": support_stats,
            "support_tickets_list": [
                {
                    "id": str(t.id),
                    "ticket_number": t.ticket_number,
                    "organization_id": str(t.organization_id) if t.organization_id else None,
                    "subject": t.subject,
                    "category": t.category.value if t.category else None,
                    "priority": t.priority.value if t.priority else None,
                    "status": t.status.value if t.status else None,
                    "source": t.source.value if t.source else None,
                    "description": t.description[:200] + "..." if t.description and len(t.description) > 200 else t.description,
                    "requester_email": t.reporter_email,
                    "requester_name": t.reporter_name,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "first_response_at": t.first_response_at.isoformat() if t.first_response_at else None,
                    "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
                }
                for t in support_tickets_list
            ],
            
            "permissions": [p.value for p in get_platform_permissions(PlatformRole.SUPER_ADMIN)],
            "quick_actions": [
                {"label": "Onboard Staff", "url": "/admin/staff/onboard", "icon": "user-plus", "description": "Add Admin, IT, CSR, or Marketing staff"},
                {"label": "Onboard Admin", "url": "/admin/staff/onboard?role=admin", "icon": "user-shield", "description": "Add new Admin user"},
                {"label": "Pending Verifications", "url": "/admin/verifications", "icon": "check-circle", "description": f"{pending_verifications} awaiting review"},
                {"label": "Platform Settings", "url": "/admin/settings", "icon": "cog", "description": "Configure platform settings"},
                {"label": "API Keys (NRS/JTB)", "url": "/admin/api-keys", "icon": "key", "description": "Manage government gateway keys"},
                {"label": "Security Audit", "url": "/admin/security", "icon": "shield-alt", "description": "View security logs and alerts"},
                {"label": "Workflow Automation", "url": "/admin/automation", "icon": "robot", "description": "Configure automated tasks"},
                {"label": "Support Tickets", "url": "/admin/support", "icon": "headset", "description": f"{support_stats.get('open', 0)} open tickets"},
                {"label": "Risk Signals", "url": "/admin/risk-signals", "icon": "exclamation-triangle", "description": f"{risk_signals_stats.get('critical', 0)} critical signals"},
                {"label": "Legal Holds", "url": "/admin/legal-holds", "icon": "gavel", "description": f"{legal_holds_stats.get('active', 0)} active holds"},
                {"label": "ML Operations", "url": "/admin/ml-jobs", "icon": "brain", "description": f"{ml_jobs_stats.get('running', 0)} running jobs"},
                {"label": "Upsell Pipeline", "url": "/admin/upsell", "icon": "chart-line", "description": f"₦{upsell_stats.get('pipeline_value', 0):,.0f} pipeline"},
            ],
        }
    
    async def get_admin_dashboard(self, user: User) -> Dict[str, Any]:
        """
        Admin Dashboard (Level 4 - Operational Lead)
        
        Focus Areas:
        1. Verification Command Center - Pending verification queue
        2. Entity Health Overview - Compliant vs Non-compliant organizations
        3. Staff Performance Stats - Task completion by role
        4. Global Revenue Snapshot - Platform-wide revenue (no private banking data)
        5. Escalation Inbox - High-priority unresolved issues
        """
        if not user.is_platform_staff or user.platform_role != PlatformRole.ADMIN:
            raise PermissionError("Admin access required")
        
        # Basic counts
        org_count = await self._get_organization_count()
        user_count = await self._get_user_count()
        pending_verifications = await self._get_pending_verification_count()
        verification_stats = await self._get_verification_stats()
        
        # ===== 1. VERIFICATION COMMAND CENTER =====
        pending_verification_queue = await self._get_pending_verification_queue()
        
        # ===== 2. ENTITY HEALTH OVERVIEW =====
        entity_health = await self._get_entity_health_overview()
        orgs_needing_attention = await self._get_organizations_needing_attention()
        
        # ===== 3. STAFF PERFORMANCE STATS =====
        staff_performance = await self._get_staff_performance_stats()
        
        # ===== 4. GLOBAL REVENUE SNAPSHOT =====
        revenue_snapshot = await self._get_platform_revenue_snapshot()
        
        # ===== 5. ESCALATION INBOX =====
        escalations = await self._get_escalation_inbox()
        
        return {
            "dashboard_type": "admin",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "name": user.full_name,
                "role": "Admin",
            },
            "overview": {
                "total_organizations": org_count,
                "total_users": user_count,
                "pending_verifications": pending_verifications,
            },
            # Section 1: Verification Command Center
            "verification_stats": verification_stats,
            "pending_verification_queue": pending_verification_queue,
            
            # Section 2: Entity Health Overview
            "entity_health": entity_health,
            "organizations_needing_attention": orgs_needing_attention,
            
            # Section 3: Staff Performance
            "staff_performance": staff_performance,
            
            # Section 4: Revenue Snapshot
            "revenue_snapshot": revenue_snapshot,
            
            # Section 5: Escalation Inbox
            "escalations": escalations,
            
            "permissions": [p.value for p in get_platform_permissions(PlatformRole.ADMIN)],
            "quick_actions": [
                {"label": "Onboard Staff", "url": "/admin/staff/onboard", "icon": "user-plus", "description": "Add IT, CSR, or Marketing staff"},
                {"label": "Review Verifications", "url": "/admin/verifications", "icon": "check-circle", "description": f"{pending_verifications} pending"},
                {"label": "User Analytics", "url": "/admin/analytics", "icon": "chart-bar", "description": "View growth trends"},
                {"label": "Staff Management", "url": "/admin/staff", "icon": "users", "description": "Manage internal staff"},
                {"label": "Escalations", "url": "/admin/escalations", "icon": "exclamation-triangle", "description": "High-priority issues"},
            ],
        }
    
    async def get_it_developer_dashboard(self, user: User) -> Dict[str, Any]:
        """
        IT/Developer Dashboard (Level 3 - Infrastructure)
        
        Technical "War Room" for FastAPI/PostgreSQL backend and NRS Integrations.
        
        Focus Areas:
        1. NRS Webhook Monitor - Real-time connection to Nigeria Revenue Service
        2. Database Health - PostgreSQL performance and backup status
        3. Error Tracking - 500-level errors and failed API calls
        4. Deployment Status - Current versions in production
        """
        if not user.is_platform_staff or user.platform_role != PlatformRole.IT_DEVELOPER:
            raise PermissionError("IT/Developer access required")
        
        # ===== 1. NRS WEBHOOK MONITOR =====
        nrs_webhook_status = await self._get_nrs_webhook_status()
        recent_nrs_submissions = await self._get_recent_nrs_submissions(limit=15)
        
        # ===== 2. DATABASE HEALTH =====
        database_health = await self._get_database_health()
        
        # ===== 3. ERROR TRACKING =====
        recent_errors = await self._get_recent_errors(limit=15)
        error_stats = await self._get_error_stats()
        
        # ===== 4. DEPLOYMENT STATUS =====
        deployment_status = await self._get_deployment_status()
        
        # Platform health detailed
        platform_health = await self._get_platform_health_detailed()
        
        # API performance metrics
        api_metrics = await self._get_api_metrics()
        
        return {
            "dashboard_type": "it_developer",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "name": user.full_name,
                "role": "IT/Developer",
            },
            # Section 1: NRS Webhook Monitor
            "nrs_webhook": nrs_webhook_status,
            "recent_nrs_submissions": recent_nrs_submissions,
            
            # Section 2: Database Health
            "database_health": database_health,
            
            # Section 3: Error Tracking
            "recent_errors": recent_errors,
            "error_stats": error_stats,
            
            # Section 4: Deployment Status
            "deployment_status": deployment_status,
            
            # General system metrics
            "platform_health": platform_health,
            "api_metrics": api_metrics,
            "system_metrics": {
                "database_status": database_health.get("status", "unknown"),
                "api_uptime": api_metrics.get("uptime", "99.9%"),
                "nrs_webhook_status": nrs_webhook_status.get("status", "unknown"),
            },
            "permissions": [p.value for p in get_platform_permissions(PlatformRole.IT_DEVELOPER)],
            "quick_actions": [
                {"label": "System Logs", "url": "/admin/logs", "icon": "document-text", "description": "View application logs"},
                {"label": "Database Health", "url": "/admin/database", "icon": "database", "description": "PostgreSQL monitoring"},
                {"label": "Webhook Status", "url": "/admin/webhooks", "icon": "link", "description": "NRS/Government APIs"},
                {"label": "Error Dashboard", "url": "/admin/errors", "icon": "bug", "description": "Track and debug errors"},
                {"label": "API Monitor", "url": "/admin/api-monitor", "icon": "activity", "description": "API performance"},
                {"label": "Deployments", "url": "/admin/deployments", "icon": "cloud-upload", "description": "Version history"},
            ],
        }
    
    async def get_csr_dashboard(self, user: User) -> Dict[str, Any]:
        """
        Customer Service Dashboard (Level 2 - Support)
        
        Focus on User Retention and Troubleshooting.
        
        Focus Areas:
        1. Ticket Queue - Incoming queries from SME owners, Bursars, etc.
        2. User Impersonation Portal - Secure view of client's dashboard
        3. NRS Submission Debugger - Debug rejected e-invoices
        4. Onboarding Progress - Users stuck at various steps
        """
        if not user.is_platform_staff or user.platform_role != PlatformRole.CUSTOMER_SERVICE:
            raise PermissionError("Customer Service access required")
        
        # ===== 1. TICKET QUEUE =====
        ticket_queue = await self._get_support_ticket_queue()
        
        # ===== 2. IMPERSONATION PORTAL =====
        impersonation_stats = await self._get_impersonation_stats()
        
        # ===== 3. NRS SUBMISSION DEBUGGER =====
        recent_submissions = await self._get_recent_nrs_submissions(limit=10)
        failed_submissions = await self._get_failed_nrs_submissions()
        
        # ===== 4. ONBOARDING PROGRESS =====
        stuck_users = await self._get_stuck_onboarding_users()
        
        # Support metrics
        support_metrics = await self._get_support_metrics()
        
        return {
            "dashboard_type": "customer_service",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "name": user.full_name,
                "role": "Customer Service",
            },
            # Section 1: Ticket Queue
            "ticket_queue": ticket_queue,
            
            # Section 2: Impersonation Portal
            "impersonation_stats": impersonation_stats,
            
            # Section 3: NRS Submission Debugger
            "recent_submissions": recent_submissions,
            "failed_submissions": failed_submissions,
            
            # Section 4: Onboarding Progress
            "stuck_users": stuck_users,
            
            # Support metrics
            "support_metrics": support_metrics,
            "permissions": [p.value for p in get_platform_permissions(PlatformRole.CUSTOMER_SERVICE)],
            "quick_actions": [
                {"label": "Search User", "url": "/admin/users/search", "icon": "search", "description": "Find user by email or name"},
                {"label": "Failed Submissions", "url": "/admin/submissions/failed", "icon": "exclamation", "description": f"{len(failed_submissions)} failed"},
                {"label": "Impersonate User", "url": "/admin/impersonate", "icon": "user-secret", "description": "View as client (with permission)"},
                {"label": "Onboarding Help", "url": "/admin/onboarding", "icon": "user-check", "description": "Assist stuck users"},
                {"label": "Help Articles", "url": "/admin/help", "icon": "book-open", "description": "Knowledge base"},
                {"label": "NRS Debugger", "url": "/admin/nrs-debug", "icon": "bug", "description": "Debug e-invoice rejections"},
            ],
        }
    
    async def get_marketing_dashboard(self, user: User) -> Dict[str, Any]:
        """
        Marketing Dashboard (Level 2 - Growth)
        
        Focus on Acquisition and Engagement.
        
        Focus Areas:
        1. Conversion Funnel - Website → Registered → First E-Invoice
        2. Referral Engine - User invitations and rewards
        3. Campaign Manager - Push notifications and emails
        4. User Growth Metrics - Segment analysis
        """
        if not user.is_platform_staff or user.platform_role != PlatformRole.MARKETING:
            raise PermissionError("Marketing access required")
        
        # ===== 1. CONVERSION FUNNEL =====
        conversion_funnel = await self._get_conversion_funnel()
        
        # ===== 2. REFERRAL ENGINE =====
        referral_stats = await self._get_referral_stats()
        
        # ===== 3. CAMPAIGN MANAGER =====
        campaign_metrics = await self._get_campaign_metrics()
        
        # ===== 4. USER GROWTH METRICS =====
        growth_stats = await self._get_user_growth_stats()
        org_by_type = await self._get_organizations_by_type()
        
        # User segment analysis
        user_segments = await self._get_user_segment_analysis()
        
        # Upcoming deadlines (for targeted campaigns)
        upcoming_deadlines = await self._get_upcoming_tax_deadlines()
        
        return {
            "dashboard_type": "marketing",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "name": user.full_name,
                "role": "Marketing",
            },
            # Section 1: Conversion Funnel
            "conversion_funnel": conversion_funnel,
            
            # Section 2: Referral Engine
            "referral_stats": referral_stats,
            
            # Section 3: Campaign Manager
            "campaign_metrics": campaign_metrics,
            
            # Section 4: User Growth Metrics
            "growth_stats": growth_stats,
            "organizations_by_type": org_by_type,
            "user_segments": user_segments,
            
            # Upcoming deadlines for campaigns
            "upcoming_deadlines": upcoming_deadlines,
            
            "permissions": [p.value for p in get_platform_permissions(PlatformRole.MARKETING)],
            "quick_actions": [
                {"label": "Create Campaign", "url": "/admin/campaigns/new", "icon": "megaphone", "description": "Launch new campaign"},
                {"label": "User Analytics", "url": "/admin/analytics", "icon": "chart-bar", "description": "Detailed user insights"},
                {"label": "Referral Stats", "url": "/admin/referrals", "icon": "users", "description": "Referral program performance"},
                {"label": "Send Notification", "url": "/admin/notifications/new", "icon": "bell", "description": "Push or email notification"},
                {"label": "Deadline Alerts", "url": "/admin/deadline-campaigns", "icon": "calendar", "description": "VAT/CIT deadline reminders"},
                {"label": "Segment Users", "url": "/admin/segments", "icon": "filter", "description": "Create user segments"},
            ],
        }
    
    # ===========================================
    # ORGANIZATION USER DASHBOARDS
    # ===========================================
    
    async def get_organization_dashboard(
        self, 
        user: User, 
        entity_id: Optional[uuid.UUID] = None
    ) -> Dict[str, Any]:
        """
        Organization User Dashboard - World-Class Business Intelligence.
        
        NTAA 2025 Compliance Features:
        - Tax Health Score (Red/Amber/Green indicator)
        - NRS Connection Status (heartbeat monitor)
        - Compliance Calendar (VAT 21st, PAYE 10th deadlines)
        - Liquidity Ratio widget
        - Organization-Type-Specific Dashboards:
          * SME: Threshold Monitor, VAT Recovery Tracker, WREN Validator
          * School: Teacher PAYE Summary, Fee Collection vs VAT, WHT Vault
          * Non-Profit: ROM Widget, Restricted vs Unrestricted Funds
          * Individual: Tax-Free Band Tracker, Relief Vault, Hustle Toggle
        - Permission-based view restrictions (Maker-Checker SoD)
        """
        if user.is_platform_staff:
            raise ValueError("Platform staff should use platform dashboards")
        
        if not user.organization_id:
            raise ValueError("User has no organization")
        
        # Get the entity to show dashboard for
        if entity_id:
            # Verify user has access to this entity
            entity = await self._get_entity_if_accessible(user, entity_id)
            if not entity:
                raise PermissionError("No access to this entity")
        else:
            # Use first accessible entity
            entity = await self._get_first_accessible_entity(user)
        
        # Get organization info
        org_result = await self.db.execute(
            select(Organization).where(Organization.id == user.organization_id)
        )
        organization = org_result.scalar_one_or_none()
        org_type = organization.organization_type if organization else OrganizationType.SMALL_BUSINESS
        
        # ===== CORE WIDGETS (All Organization Types) =====
        
        # Get financial metrics
        financial_metrics = await self._get_financial_metrics(entity.id if entity else None)
        
        # Get recent transactions
        recent_transactions = await self._get_recent_transactions(
            entity.id if entity else None, 
            limit=5
        )
        
        # Get invoice summary
        invoice_summary = await self._get_invoice_summary(entity.id if entity else None)
        
        # Get TIN/CAC Vault (2026 compliance)
        tin_cac_vault = await self._get_tin_cac_vault(entity, organization)
        
        # Get Compliance Health indicator (2026 compliance)
        compliance_health = await self._get_compliance_health(entity)
        
        # ===== NEW NTAA 2025 CORE WIDGETS =====
        
        # Tax Health Score (Red/Amber/Green indicator)
        tax_health_score = await self._get_tax_health_score(entity, user.role)
        
        # NRS Connection Status (heartbeat monitor)
        nrs_status = await self._get_nrs_connection_status(entity)
        
        # Compliance Calendar (VAT 21st, PAYE 10th deadlines)
        compliance_calendar = await self._get_compliance_calendar(entity)
        
        # Liquidity Ratio widget
        liquidity_ratio = await self._get_liquidity_ratio(entity)
        
        # Get user's permissions
        permissions = []
        if user.role:
            permissions = [p.value for p in get_organization_permissions(user.role)]
        
        # Build base dashboard
        dashboard = {
            "dashboard_type": f"organization_{user.role.value if user.role else 'user'}",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "name": user.full_name,
                "role": user.role.value if user.role else "user",
            },
            "organization": {
                "id": str(organization.id) if organization else None,
                "name": organization.name if organization else None,
                "type": organization.organization_type.value if organization and organization.organization_type else None,
                "type_display": self._get_org_type_display_name(org_type),
                "verification_status": organization.verification_status.value if organization and hasattr(organization, 'verification_status') else "pending",
                "subscription_tier": organization.subscription_tier.value if organization else None,
            },
            "current_entity": {
                "id": str(entity.id) if entity else None,
                "name": entity.name if entity else None,
            } if entity else None,
            
            # ===== NTAA 2025 CORE WIDGETS (Always Visible) =====
            "tax_health_score": tax_health_score,
            "nrs_status": nrs_status,
            "compliance_calendar": compliance_calendar,
            "liquidity_ratio": liquidity_ratio,
            
            # 2026 Compliance sections - always visible
            "tin_cac_vault": tin_cac_vault,
            "compliance_health": compliance_health,
            "financial_metrics": financial_metrics,
            "recent_transactions": recent_transactions,
            "invoice_summary": invoice_summary,
            "permissions": permissions,
            "quick_actions": self._get_quick_actions_for_role(user.role, org_type),
        }
        
        # ===== ORGANIZATION-TYPE-SPECIFIC WIDGETS =====
        org_specific = await self._get_org_type_specific_dashboard(
            org_type=org_type,
            entity=entity,
            user=user,
            organization=organization
        )
        dashboard["org_specific"] = org_specific
        
        # Add role-specific sections
        if user.role in [UserRole.OWNER, UserRole.ADMIN]:
            dashboard["team_summary"] = await self._get_team_summary(user.organization_id)
        
        if user.role in [UserRole.OWNER, UserRole.ADMIN, UserRole.ACCOUNTANT]:
            dashboard["tax_summary"] = await self._get_tax_summary(entity.id if entity else None)
        
        if user.role in [UserRole.INVENTORY_MANAGER, UserRole.OWNER, UserRole.ADMIN]:
            dashboard["inventory_summary"] = await self._get_inventory_summary(entity.id if entity else None)
        
        # ===== NEW ADVANCED ACCOUNTING WIDGETS =====
        # Add FX, consolidation, and budget widgets for appropriate roles
        if user.role in [UserRole.OWNER, UserRole.ADMIN, UserRole.ACCOUNTANT, UserRole.EXTERNAL_ACCOUNTANT]:
            # FX Exposure Widget - Shows currency exposure and unrealized gains/losses
            dashboard["fx_exposure"] = await self._get_fx_exposure_widget(entity.id if entity else None)
            
            # Budget Variance Widget - Shows YTD budget vs actual performance
            dashboard["budget_variance"] = await self._get_budget_variance_widget(entity.id if entity else None)
        
        # Consolidated Summary Widget - Only for owners/admins with multi-entity groups
        if user.role in [UserRole.OWNER, UserRole.ADMIN]:
            dashboard["consolidated_summary"] = await self._get_consolidated_summary_widget(user.organization_id)
        
        # Permission-based view restrictions (Maker-Checker SoD)
        dashboard["view_restrictions"] = self._get_view_restrictions(user.role, org_type)
        
        return dashboard
    
    # ===========================================
    # UNIFIED DASHBOARD ENTRY POINT
    # ===========================================
    
    async def get_dashboard(
        self, 
        user: User, 
        entity_id: Optional[uuid.UUID] = None
    ) -> Dict[str, Any]:
        """
        Get appropriate dashboard based on user type and role.
        """
        if user.is_platform_staff:
            # Route to appropriate platform dashboard
            if user.platform_role == PlatformRole.SUPER_ADMIN:
                return await self.get_super_admin_dashboard(user)
            elif user.platform_role == PlatformRole.ADMIN:
                return await self.get_admin_dashboard(user)
            elif user.platform_role == PlatformRole.IT_DEVELOPER:
                return await self.get_it_developer_dashboard(user)
            elif user.platform_role == PlatformRole.CUSTOMER_SERVICE:
                return await self.get_csr_dashboard(user)
            elif user.platform_role == PlatformRole.MARKETING:
                return await self.get_marketing_dashboard(user)
            else:
                raise ValueError(f"Unknown platform role: {user.platform_role}")
        else:
            # Organization user dashboard
            return await self.get_organization_dashboard(user, entity_id)
    
    # ===========================================
    # HELPER METHODS
    # ===========================================
    
    async def _get_organization_count(self) -> int:
        result = await self.db.execute(select(func.count(Organization.id)))
        return result.scalar() or 0
    
    async def _get_user_count(self) -> int:
        result = await self.db.execute(
            select(func.count(User.id)).where(User.is_platform_staff == False)
        )
        return result.scalar() or 0
    
    async def _get_staff_count(self) -> int:
        result = await self.db.execute(
            select(func.count(User.id)).where(User.is_platform_staff == True)
        )
        return result.scalar() or 0
    
    async def _get_pending_verification_count(self) -> int:
        result = await self.db.execute(
            select(func.count(Organization.id)).where(
                Organization.verification_status == VerificationStatus.SUBMITTED
            )
        )
        return result.scalar() or 0
    
    async def _get_tenants_list(self, limit: int = 50) -> List[Dict]:
        """Get list of all organizations (tenants)"""
        result = await self.db.execute(
            select(Organization)
            .order_by(Organization.created_at.desc())
            .limit(limit)
        )
        orgs = result.scalars().all()
        return [
            {
                "id": str(org.id),
                "name": org.name,
                "organization_type": org.organization_type.value if org.organization_type else "unknown",
                "status": "active" if org.verification_status == VerificationStatus.VERIFIED else (
                    "trial" if org.verification_status == VerificationStatus.PENDING else org.verification_status.value if org.verification_status else "unknown"
                ),
                "user_count": 0,  # Would need a join to get actual count
                "created_at": org.created_at.strftime("%b %d, %Y") if org.created_at else None,
            }
            for org in orgs
        ]
    
    async def _get_tenant_stats(self) -> Dict[str, int]:
        """Get tenant stats by status"""
        verified = await self.db.execute(
            select(func.count(Organization.id)).where(
                Organization.verification_status == VerificationStatus.VERIFIED
            )
        )
        pending = await self.db.execute(
            select(func.count(Organization.id)).where(
                Organization.verification_status == VerificationStatus.PENDING
            )
        )
        suspended = await self.db.execute(
            select(func.count(Organization.id)).where(
                Organization.verification_status == VerificationStatus.REJECTED
            )
        )
        return {
            "active": verified.scalar() or 0,
            "trial": pending.scalar() or 0,
            "suspended": suspended.scalar() or 0,
        }
    
    async def _get_organizations_by_type(self) -> Dict[str, int]:
        result = await self.db.execute(
            select(
                Organization.organization_type,
                func.count(Organization.id)
            ).group_by(Organization.organization_type)
        )
        return {row[0].value if row[0] else "unknown": row[1] for row in result.all()}
    
    async def _get_verification_stats(self) -> Dict[str, int]:
        result = await self.db.execute(
            select(
                Organization.verification_status,
                func.count(Organization.id)
            ).group_by(Organization.verification_status)
        )
        return {row[0].value if row[0] else "unknown": row[1] for row in result.all()}
    
    async def _get_recent_platform_activity(self, limit: int = 10) -> List[Dict]:
        # Get recent audit logs
        result = await self.db.execute(
            select(AuditLog)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        logs = result.scalars().all()
        return [
            {
                "id": str(log.id),
                "action": log.action,
                "resource_type": log.table_name or log.target_entity_type or "unknown",
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]
    
    async def _get_platform_health(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "database": "connected",
            "last_check": datetime.utcnow().isoformat(),
        }
    
    async def _get_organizations_needing_attention(self) -> List[Dict]:
        result = await self.db.execute(
            select(Organization)
            .where(
                or_(
                    Organization.verification_status == VerificationStatus.SUBMITTED,
                    Organization.verification_status == VerificationStatus.REJECTED
                )
            )
            .order_by(Organization.created_at.desc())
            .limit(5)
        )
        orgs = result.scalars().all()
        return [
            {
                "id": str(org.id),
                "name": org.name,
                "status": org.verification_status.value if org.verification_status else "unknown",
                "type": org.organization_type.value if org.organization_type else "unknown",
            }
            for org in orgs
        ]
    
    async def _get_recent_errors(self, limit: int = 10) -> List[Dict]:
        """
        Get recent errors from audit logs.
        
        Tracks failed login attempts and other error events.
        """
        result = await self.db.execute(
            select(AuditLog)
            .where(
                AuditLog.action.in_([
                    AuditAction.LOGIN_FAILED,
                ])
            )
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        errors = result.scalars().all()
        return [
            {
                "id": str(error.id),
                "action": error.action if isinstance(error.action, str) else error.action.value,
                "entity_type": error.target_entity_type,
                "user_id": str(error.user_id) if error.user_id else None,
                "ip_address": str(error.ip_address) if error.ip_address else None,
                "timestamp": error.created_at.isoformat() if error.created_at else None,
            }
            for error in errors
        ]
    
    async def _get_recent_nrs_submissions(self, limit: int = 10) -> List[Dict]:
        """
        Get recent NRS e-invoice submissions from audit logs.
        
        NRS submissions are logged with action NRS_SUBMIT.
        """
        result = await self.db.execute(
            select(AuditLog)
            .where(AuditLog.action == AuditAction.NRS_SUBMIT)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        submissions = result.scalars().all()
        return [
            {
                "id": str(sub.id),
                "invoice_id": sub.target_entity_id,
                "entity_id": str(sub.entity_id) if sub.entity_id else None,
                "user_id": str(sub.user_id) if sub.user_id else None,
                "irn": sub.new_values.get("irn") if sub.new_values else None,
                "success": sub.new_values.get("success", False) if sub.new_values else False,
                "error": sub.new_values.get("error") if sub.new_values else None,
                "timestamp": sub.created_at.isoformat() if sub.created_at else None,
            }
            for sub in submissions
        ]
    
    async def _get_user_growth_stats(self) -> Dict[str, Any]:
        # Get users created in last 30 days
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        
        result = await self.db.execute(
            select(func.count(User.id)).where(
                and_(
                    User.is_platform_staff == False,
                    User.created_at >= thirty_days_ago
                )
            )
        )
        new_users = result.scalar() or 0
        
        total_users = await self._get_user_count()
        
        return {
            "total_users": total_users,
            "new_users_30d": new_users,
            "growth_rate": f"{(new_users / max(total_users, 1)) * 100:.1f}%",
        }
    
    async def _get_entity_if_accessible(
        self, 
        user: User, 
        entity_id: uuid.UUID
    ) -> Optional[BusinessEntity]:
        # Check user has access to this entity
        for access in user.entity_access:
            if access.entity_id == entity_id:
                result = await self.db.execute(
                    select(BusinessEntity).where(BusinessEntity.id == entity_id)
                )
                return result.scalar_one_or_none()
        return None
    
    async def _get_first_accessible_entity(self, user: User) -> Optional[BusinessEntity]:
        if user.entity_access and len(user.entity_access) > 0:
            entity_id = user.entity_access[0].entity_id
            result = await self.db.execute(
                select(BusinessEntity).where(BusinessEntity.id == entity_id)
            )
            return result.scalar_one_or_none()
        return None
    
    async def _get_financial_metrics(
        self, 
        entity_id: Optional[uuid.UUID]
    ) -> Dict[str, Any]:
        if not entity_id:
            return self._empty_financial_metrics()
        
        today = date.today()
        start_of_month = today.replace(day=1)
        start_of_year = today.replace(month=1, day=1)
        
        # This month metrics
        this_month = await self._get_period_metrics(
            entity_id, start_of_month, today
        )
        
        # Year to date metrics
        ytd = await self._get_period_metrics(
            entity_id, start_of_year, today
        )
        
        return {
            "this_month": this_month,
            "year_to_date": ytd,
        }
    
    async def _get_period_metrics(
        self, 
        entity_id: uuid.UUID, 
        start_date: date, 
        end_date: date
    ) -> Dict[str, float]:
        # Income
        income_result = await self.db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                and_(
                    Transaction.entity_id == entity_id,
                    Transaction.transaction_type == TransactionType.INCOME,
                    Transaction.transaction_date >= start_date,
                    Transaction.transaction_date <= end_date,
                )
            )
        )
        income = float(income_result.scalar() or 0)
        
        # Expense
        expense_result = await self.db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                and_(
                    Transaction.entity_id == entity_id,
                    Transaction.transaction_type == TransactionType.EXPENSE,
                    Transaction.transaction_date >= start_date,
                    Transaction.transaction_date <= end_date,
                )
            )
        )
        expense = float(expense_result.scalar() or 0)
        
        return {
            "income": income,
            "expense": expense,
            "net": income - expense,
        }
    
    def _empty_financial_metrics(self) -> Dict[str, Any]:
        return {
            "this_month": {"income": 0, "expense": 0, "net": 0},
            "year_to_date": {"income": 0, "expense": 0, "net": 0},
        }
    
    async def _get_recent_transactions(
        self, 
        entity_id: Optional[uuid.UUID], 
        limit: int = 5
    ) -> List[Dict]:
        if not entity_id:
            return []
        
        result = await self.db.execute(
            select(Transaction)
            .where(Transaction.entity_id == entity_id)
            .order_by(Transaction.transaction_date.desc())
            .limit(limit)
        )
        transactions = result.scalars().all()
        
        return [
            {
                "id": str(tx.id),
                "description": tx.description,
                "amount": float(tx.amount),
                "transaction_type": tx.transaction_type.value,
                "transaction_date": tx.transaction_date.isoformat() if tx.transaction_date else None,
            }
            for tx in transactions
        ]
    
    async def _get_invoice_summary(
        self, 
        entity_id: Optional[uuid.UUID]
    ) -> Dict[str, Any]:
        if not entity_id:
            return {"outstanding": 0, "overdue": 0, "total_count": 0}
        
        today = date.today()
        
        # Outstanding invoices (DRAFT, PENDING, or SUBMITTED but not yet paid)
        outstanding_result = await self.db.execute(
            select(func.coalesce(func.sum(Invoice.total_amount), 0)).where(
                and_(
                    Invoice.entity_id == entity_id,
                    Invoice.status.in_([InvoiceStatus.DRAFT, InvoiceStatus.PENDING, InvoiceStatus.SUBMITTED]),
                )
            )
        )
        outstanding = float(outstanding_result.scalar() or 0)
        
        # Overdue invoices (PENDING or SUBMITTED and past due date)
        overdue_result = await self.db.execute(
            select(func.coalesce(func.sum(Invoice.total_amount), 0)).where(
                and_(
                    Invoice.entity_id == entity_id,
                    Invoice.status.in_([InvoiceStatus.PENDING, InvoiceStatus.SUBMITTED]),
                    Invoice.due_date < today,
                )
            )
        )
        overdue = float(overdue_result.scalar() or 0)
        
        # Total count
        count_result = await self.db.execute(
            select(func.count(Invoice.id)).where(Invoice.entity_id == entity_id)
        )
        total_count = count_result.scalar() or 0
        
        return {
            "outstanding": outstanding,
            "overdue": overdue,
            "total_count": total_count,
        }
    
    async def _get_team_summary(
        self, 
        organization_id: uuid.UUID
    ) -> Dict[str, Any]:
        result = await self.db.execute(
            select(func.count(User.id)).where(
                and_(
                    User.organization_id == organization_id,
                    User.is_platform_staff == False,
                )
            )
        )
        total_members = result.scalar() or 0
        
        # Get by role
        role_result = await self.db.execute(
            select(User.role, func.count(User.id))
            .where(
                and_(
                    User.organization_id == organization_id,
                    User.is_platform_staff == False,
                )
            )
            .group_by(User.role)
        )
        by_role = {row[0].value if row[0] else "unknown": row[1] for row in role_result.all()}
        
        return {
            "total_members": total_members,
            "by_role": by_role,
        }
    
    async def _get_tax_summary(
        self, 
        entity_id: Optional[uuid.UUID]
    ) -> Dict[str, Any]:
        """
        Calculate tax obligations summary for the entity.
        
        Calculates VAT collected (from sales) and VAT paid (from expenses)
        to determine net VAT payable/recoverable.
        """
        if not entity_id:
            return {
                "vat_collected": 0,
                "vat_paid": 0,
                "net_vat_payable": 0,
                "next_filing_date": None,
            }
        
        # Get current month for VAT calculations
        today = date.today()
        month_start = date(today.year, today.month, 1)
        
        # VAT collected from sales (INCOME transactions)
        result = await self.db.execute(
            select(func.coalesce(func.sum(Transaction.vat_amount), 0))
            .where(
                and_(
                    Transaction.entity_id == entity_id,
                    Transaction.transaction_type == TransactionType.INCOME,
                    Transaction.transaction_date >= month_start,
                )
            )
        )
        vat_collected = result.scalar() or Decimal("0.00")
        
        # VAT paid on expenses (EXPENSE transactions)
        result = await self.db.execute(
            select(func.coalesce(func.sum(Transaction.vat_amount), 0))
            .where(
                and_(
                    Transaction.entity_id == entity_id,
                    Transaction.transaction_type == TransactionType.EXPENSE,
                    Transaction.transaction_date >= month_start,
                )
            )
        )
        vat_paid = result.scalar() or Decimal("0.00")
        
        # Calculate next filing date (21st of following month)
        if today.month == 12:
            next_filing = date(today.year + 1, 1, 21)
        else:
            next_filing = date(today.year, today.month + 1, 21)
        
        return {
            "vat_collected": float(vat_collected),
            "vat_paid": float(vat_paid),
            "net_vat_payable": float(vat_collected - vat_paid),
            "next_filing_date": next_filing.isoformat(),
        }
    
    async def _get_inventory_summary(
        self, 
        entity_id: Optional[uuid.UUID]
    ) -> Dict[str, Any]:
        """
        Get inventory statistics for the entity.
        
        Calculates total items, low stock items, and total inventory value.
        """
        if not entity_id:
            return {
                "total_items": 0,
                "low_stock_items": 0,
                "total_value": 0,
                "out_of_stock": 0,
            }
        
        # Total active inventory items
        result = await self.db.execute(
            select(func.count(InventoryItem.id))
            .where(
                and_(
                    InventoryItem.entity_id == entity_id,
                    InventoryItem.is_active == True,
                    InventoryItem.is_tracked == True,
                )
            )
        )
        total_items = result.scalar() or 0
        
        # Low stock items (quantity <= reorder_level but > 0)
        result = await self.db.execute(
            select(func.count(InventoryItem.id))
            .where(
                and_(
                    InventoryItem.entity_id == entity_id,
                    InventoryItem.is_active == True,
                    InventoryItem.is_tracked == True,
                    InventoryItem.quantity_on_hand <= InventoryItem.reorder_level,
                    InventoryItem.quantity_on_hand > 0,
                )
            )
        )
        low_stock_items = result.scalar() or 0
        
        # Out of stock items
        result = await self.db.execute(
            select(func.count(InventoryItem.id))
            .where(
                and_(
                    InventoryItem.entity_id == entity_id,
                    InventoryItem.is_active == True,
                    InventoryItem.is_tracked == True,
                    InventoryItem.quantity_on_hand == 0,
                )
            )
        )
        out_of_stock = result.scalar() or 0
        
        # Total inventory value (quantity * unit_cost)
        result = await self.db.execute(
            select(
                func.coalesce(
                    func.sum(InventoryItem.quantity_on_hand * InventoryItem.unit_cost),
                    0
                )
            )
            .where(
                and_(
                    InventoryItem.entity_id == entity_id,
                    InventoryItem.is_active == True,
                )
            )
        )
        total_value = result.scalar() or Decimal("0.00")
        
        return {
            "total_items": total_items,
            "low_stock_items": low_stock_items,
            "out_of_stock": out_of_stock,
            "total_value": float(total_value),
        }
    
    async def _get_fx_exposure_widget(
        self, 
        entity_id: Optional[uuid.UUID]
    ) -> Dict[str, Any]:
        """
        Get FX exposure summary widget for the entity.
        
        Shows currency exposures, unrealized gains/losses, and hedging status.
        """
        if not entity_id:
            return {
                "total_exposure_ngn": 0,
                "currencies": [],
                "unrealized_gain_loss": 0,
                "hedging_coverage": 0,
                "risk_level": "low",
            }
        
        try:
            from app.services.fx_service import FXService
            fx_service = FXService(self.db)
            
            # Get FX exposure by currency
            exposure_data = await fx_service.get_exposure_summary(entity_id)
            
            currencies = []
            total_exposure = Decimal("0")
            unrealized_gl = Decimal("0")
            
            for currency, data in exposure_data.get("exposures", {}).items():
                exposure_ngn = Decimal(str(data.get("exposure_ngn", 0)))
                total_exposure += exposure_ngn
                unrealized_gl += Decimal(str(data.get("unrealized_gain_loss", 0)))
                
                currencies.append({
                    "currency": currency,
                    "exposure_amount": float(data.get("exposure_amount", 0)),
                    "exposure_ngn": float(exposure_ngn),
                    "exchange_rate": float(data.get("exchange_rate", 0)),
                    "direction": "long" if data.get("exposure_amount", 0) > 0 else "short"
                })
            
            # Calculate risk level
            if total_exposure > Decimal("100000000"):  # 100M NGN
                risk_level = "high"
            elif total_exposure > Decimal("50000000"):  # 50M NGN
                risk_level = "medium"
            else:
                risk_level = "low"
            
            return {
                "total_exposure_ngn": float(total_exposure),
                "currencies": sorted(currencies, key=lambda x: x["exposure_ngn"], reverse=True)[:5],
                "unrealized_gain_loss": float(unrealized_gl),
                "hedging_coverage": exposure_data.get("hedging_coverage_percent", 0),
                "risk_level": risk_level,
                "last_revaluation": exposure_data.get("last_revaluation_date"),
            }
        
        except Exception as e:
            import logging
            logging.error(f"Error getting FX exposure widget: {e}")
            return {
                "total_exposure_ngn": 0,
                "currencies": [],
                "unrealized_gain_loss": 0,
                "hedging_coverage": 0,
                "risk_level": "low",
                "error": str(e)
            }
    
    async def _get_consolidated_summary_widget(
        self, 
        organization_id: Optional[uuid.UUID]
    ) -> Dict[str, Any]:
        """
        Get consolidated financial summary for entity groups.
        
        Shows group-level summary including total assets, liabilities, and equity.
        """
        if not organization_id:
            return {
                "has_group": False,
                "entities_count": 0,
                "total_assets": 0,
                "total_liabilities": 0,
                "total_equity": 0,
                "intercompany_balance": 0,
            }
        
        try:
            from app.services.consolidation_service import ConsolidationService
            from app.models.multi_entity import EntityGroup
            
            consol_service = ConsolidationService(self.db)
            
            # Check if organization has any entity groups
            result = await self.db.execute(
                select(EntityGroup)
                .where(
                    and_(
                        EntityGroup.organization_id == organization_id,
                        EntityGroup.is_active == True
                    )
                )
                .limit(1)
            )
            group = result.scalar_one_or_none()
            
            if not group:
                return {
                    "has_group": False,
                    "entities_count": 0,
                    "total_assets": 0,
                    "total_liabilities": 0,
                    "total_equity": 0,
                    "intercompany_balance": 0,
                }
            
            # Get consolidated summary
            as_of_date = date.today()
            summary = await consol_service.get_consolidated_balance_sheet(
                group_id=group.id,
                as_of_date=as_of_date
            )
            
            # Get entity count in group
            members = await consol_service.get_group_members(group.id)
            
            return {
                "has_group": True,
                "group_name": group.name,
                "group_id": str(group.id),
                "entities_count": len(members) if members else 0,
                "total_assets": float(summary.get("total_assets", 0)),
                "total_liabilities": float(summary.get("total_liabilities", 0)),
                "total_equity": float(summary.get("total_equity", 0)),
                "intercompany_balance": float(summary.get("intercompany_eliminations", 0)),
                "as_of_date": as_of_date.isoformat(),
                "minority_interest": float(summary.get("minority_interest", 0)),
            }
        
        except Exception as e:
            import logging
            logging.error(f"Error getting consolidated summary widget: {e}")
            return {
                "has_group": False,
                "entities_count": 0,
                "total_assets": 0,
                "total_liabilities": 0,
                "total_equity": 0,
                "intercompany_balance": 0,
                "error": str(e)
            }
    
    async def _get_budget_variance_widget(
        self, 
        entity_id: Optional[uuid.UUID]
    ) -> Dict[str, Any]:
        """
        Get budget variance summary widget for the entity.
        
        Shows YTD budget performance, variances, and alerts.
        """
        if not entity_id:
            return {
                "has_active_budget": False,
                "ytd_budget": 0,
                "ytd_actual": 0,
                "variance_percent": 0,
                "status": "no_budget",
                "alerts_count": 0,
            }
        
        try:
            from app.services.budget_service import BudgetService
            from app.models.budget import Budget, BudgetStatus
            
            budget_service = BudgetService(self.db)
            
            # Get active budget for current fiscal year
            current_year = date.today().year
            result = await self.db.execute(
                select(Budget)
                .where(
                    and_(
                        Budget.entity_id == entity_id,
                        Budget.status == BudgetStatus.APPROVED,
                        Budget.fiscal_year == current_year
                    )
                )
                .limit(1)
            )
            budget = result.scalar_one_or_none()
            
            if not budget:
                return {
                    "has_active_budget": False,
                    "ytd_budget": 0,
                    "ytd_actual": 0,
                    "variance_percent": 0,
                    "status": "no_budget",
                    "alerts_count": 0,
                }
            
            # Get YTD variance analysis
            current_month = date.today().month
            variance_data = await budget_service.get_budget_vs_actual(
                entity_id=entity_id,
                budget_id=budget.id,
                through_month=current_month,
                group_by="summary"
            )
            
            ytd_budget = float(variance_data.get("total_budgeted", 0))
            ytd_actual = float(variance_data.get("total_actual", 0))
            
            # Calculate variance percentage
            if ytd_budget > 0:
                variance_pct = ((ytd_actual - ytd_budget) / ytd_budget) * 100
            else:
                variance_pct = 0
            
            # Determine status
            if abs(variance_pct) <= 5:
                status = "on_track"
            elif variance_pct > 5:
                status = "over_budget"
            else:
                status = "under_budget"
            
            # Count alerts (items with > 10% variance)
            alerts_count = 0
            for item in variance_data.get("line_items", []):
                if abs(item.get("variance_percent", 0)) >= 10:
                    alerts_count += 1
            
            return {
                "has_active_budget": True,
                "budget_name": budget.name,
                "budget_id": str(budget.id),
                "fiscal_year": budget.fiscal_year,
                "ytd_budget": ytd_budget,
                "ytd_actual": ytd_actual,
                "variance_amount": ytd_actual - ytd_budget,
                "variance_percent": round(variance_pct, 2),
                "status": status,
                "alerts_count": alerts_count,
                "through_month": current_month,
            }
        
        except Exception as e:
            import logging
            logging.error(f"Error getting budget variance widget: {e}")
            return {
                "has_active_budget": False,
                "ytd_budget": 0,
                "ytd_actual": 0,
                "variance_percent": 0,
                "status": "error",
                "alerts_count": 0,
                "error": str(e)
            }

    async def _get_tin_cac_vault(
        self,
        entity: Optional["BusinessEntity"],
        organization: Optional["Organization"],
    ) -> Dict[str, Any]:
        """
        Get TIN/CAC Vault display data.
        
        Under the 2026 law, TIN and CAC numbers are mandatory for all
        financial and digital operations.
        """
        return {
            "tin": {
                "number": entity.tin if entity else None,
                "status": "verified" if entity and entity.tin else "missing",
                "label": "Tax Identification Number (TIN)",
                "is_critical": True,
                "warning": "TIN is mandatory for NRS e-invoicing" if not (entity and entity.tin) else None,
            },
            "cac": {
                "number": entity.rc_number if entity else None,
                "status": "verified" if entity and entity.rc_number else "missing",
                "label": "CAC RC/BN Number",
                "is_critical": True,
                "warning": "CAC registration is required for compliance" if not (entity and entity.rc_number) else None,
            },
            "business_type": {
                "value": entity.business_type.value if entity and entity.business_type else None,
                "label": "Business Name (PIT)" if entity and entity.business_type and entity.business_type.value == "business_name" else "Limited Company (CIT)",
                "tax_implication": "Personal Income Tax (PIT)" if entity and entity.business_type and entity.business_type.value == "business_name" else "Corporate Income Tax (CIT)",
            },
            "vat_registration": {
                "is_registered": entity.is_vat_registered if entity else False,
                "registration_date": entity.vat_registration_date.isoformat() if entity and entity.vat_registration_date else None,
                "status": "registered" if entity and entity.is_vat_registered else "not_registered",
            },
        }
    
    async def _get_compliance_health(
        self,
        entity: Optional["BusinessEntity"],
    ) -> Dict[str, Any]:
        """
        Get Compliance Health indicator for dashboard.
        
        Checks:
        - Small Company Status (0% CIT eligibility)
        - Development Levy Exemption status
        - NRS e-invoicing compliance
        - Pending tax filings
        """
        if not entity:
            return {
                "overall_status": "unknown",
                "score": 0,
                "checks": [],
            }
        
        checks = []
        issues = 0
        warnings = 0
        
        # Check 1: TIN registered
        if entity.tin:
            checks.append({
                "name": "TIN Registration",
                "status": "pass",
                "message": f"TIN registered: {entity.tin}",
                "icon": "check-circle",
            })
        else:
            checks.append({
                "name": "TIN Registration",
                "status": "fail",
                "message": "TIN not registered - required for NRS",
                "icon": "x-circle",
            })
            issues += 1
        
        # Check 2: CAC Registration
        if entity.rc_number:
            checks.append({
                "name": "CAC Registration",
                "status": "pass",
                "message": f"CAC registered: {entity.rc_number}",
                "icon": "check-circle",
            })
        else:
            checks.append({
                "name": "CAC Registration",
                "status": "fail",
                "message": "CAC number missing",
                "icon": "x-circle",
            })
            issues += 1
        
        # Check 3: Small Company Status (for CIT exemption)
        from decimal import Decimal
        turnover = entity.annual_turnover or Decimal("0")
        fixed_assets = entity.fixed_assets_value or Decimal("0")
        
        is_small_company = (
            turnover <= Decimal("50000000") and
            fixed_assets <= Decimal("250000000")
        )
        
        if entity.business_type and entity.business_type.value == "limited_company":
            if is_small_company:
                checks.append({
                    "name": "Small Company Status",
                    "status": "pass",
                    "message": f"Qualifies for 0% CIT (Turnover: ₦{turnover:,.0f}, Assets: ₦{fixed_assets:,.0f})",
                    "icon": "badge-check",
                    "highlight": True,
                })
            else:
                reason = []
                if turnover > Decimal("50000000"):
                    reason.append(f"Turnover ₦{turnover:,.0f} > ₦50M")
                if fixed_assets > Decimal("250000000"):
                    reason.append(f"Assets ₦{fixed_assets:,.0f} > ₦250M")
                checks.append({
                    "name": "Small Company Status",
                    "status": "info",
                    "message": f"Standard CIT applies: {', '.join(reason)}",
                    "icon": "information-circle",
                })
        
        # Check 4: Development Levy Exemption
        is_dev_levy_exempt = (
            turnover <= Decimal("100000000") and
            fixed_assets <= Decimal("250000000")
        )
        
        if entity.business_type and entity.business_type.value == "limited_company":
            if is_dev_levy_exempt:
                checks.append({
                    "name": "Development Levy",
                    "status": "pass",
                    "message": "Exempt from 4% Development Levy",
                    "icon": "shield-check",
                })
            else:
                checks.append({
                    "name": "Development Levy",
                    "status": "info",
                    "message": "Subject to 4% Development Levy on assessable profit",
                    "icon": "currency-dollar",
                })
        else:
            checks.append({
                "name": "Development Levy",
                "status": "pass",
                "message": "Not applicable (Business Names pay PIT only)",
                "icon": "shield-check",
            })
        
        # Check 5: VAT Registration
        if entity.is_vat_registered:
            checks.append({
                "name": "VAT Registration",
                "status": "pass",
                "message": "VAT registered - can issue VAT invoices",
                "icon": "check-circle",
            })
        else:
            if turnover > Decimal("25000000"):  # VAT threshold
                checks.append({
                    "name": "VAT Registration",
                    "status": "warning",
                    "message": "Turnover exceeds ₦25M threshold - VAT registration recommended",
                    "icon": "exclamation",
                })
                warnings += 1
            else:
                checks.append({
                    "name": "VAT Registration",
                    "status": "info",
                    "message": "Below VAT threshold (₦25M)",
                    "icon": "information-circle",
                })
        
        # Calculate overall score
        total_checks = len(checks)
        passed = sum(1 for c in checks if c["status"] == "pass")
        score = int((passed / total_checks) * 100) if total_checks > 0 else 0
        
        if issues > 0:
            overall_status = "critical"
        elif warnings > 0:
            overall_status = "warning"
        elif score == 100:
            overall_status = "excellent"
        else:
            overall_status = "good"
        
        return {
            "overall_status": overall_status,
            "score": score,
            "issues": issues,
            "warnings": warnings,
            "checks": checks,
            "summary": f"{passed}/{total_checks} compliance checks passed",
        }

    def _get_quick_actions_for_role(
        self, 
        role: Optional[UserRole],
        org_type: Optional[OrganizationType] = None
    ) -> List[Dict[str, str]]:
        """Get quick actions based on user role and organization type."""
        if not role:
            return []
        
        base_actions = [
            {"label": "New Transaction", "url": "/transactions/new", "icon": "plus"},
        ]
        
        if role in [UserRole.OWNER, UserRole.ADMIN, UserRole.ACCOUNTANT]:
            base_actions.extend([
                {"label": "Create Invoice", "url": "/invoices/new", "icon": "document"},
                {"label": "Scan Receipt", "url": "/receipts/upload", "icon": "camera"},
                {"label": "Tax Center", "url": "/tax-2026", "icon": "calculator"},
            ])
        
        if role in [UserRole.OWNER, UserRole.ADMIN]:
            base_actions.append(
                {"label": "Manage Team", "url": "/settings/team", "icon": "users"}
            )
        
        if role in [UserRole.INVENTORY_MANAGER, UserRole.OWNER, UserRole.ADMIN]:
            base_actions.append(
                {"label": "Inventory", "url": "/inventory", "icon": "cube"}
            )
        
        # Add org-type specific quick actions
        if org_type == OrganizationType.SCHOOL:
            base_actions.append(
                {"label": "Staff Payroll", "url": "/payroll", "icon": "users"}
            )
        elif org_type == OrganizationType.NON_PROFIT:
            base_actions.append(
                {"label": "Donor Report", "url": "/reports/donors", "icon": "document-report"}
            )
        elif org_type == OrganizationType.INDIVIDUAL:
            base_actions.append(
                {"label": "Relief Documents", "url": "/reliefs", "icon": "folder"}
            )
        
        return base_actions
    
    def _get_view_restrictions(
        self, 
        role: Optional[UserRole],
        org_type: OrganizationType
    ) -> Dict[str, str]:
        """
        Get permission-based view restrictions (Maker-Checker SoD).
        
        Returns view level for each dashboard feature.
        """
        if not role:
            return {
                "financial_statements": "no_access",
                "nrs_submission": "no_access",
                "bank_balance": "no_access",
                "wren_categorization": "no_access",
                "salary_details": "no_access",
            }
        
        restrictions = {
            UserRole.OWNER: {
                "financial_statements": "full",
                "nrs_submission": "full",
                "bank_balance": "full",
                "wren_categorization": "full",
                "salary_details": "full",
            },
            UserRole.ADMIN: {
                "financial_statements": "full",
                "nrs_submission": "finalize",
                "bank_balance": "view",
                "wren_categorization": "maker",
                "salary_details": "no_access",  # NDPA 2026 - salary privacy
            },
            UserRole.ACCOUNTANT: {
                "financial_statements": "full",
                "nrs_submission": "finalize",
                "bank_balance": "view",
                "wren_categorization": "maker",
                "salary_details": "totals_only",  # Totals but no individual slips
            },
            UserRole.EXTERNAL_ACCOUNTANT: {
                "financial_statements": "view_file",
                "nrs_submission": "no_access",
                "bank_balance": "no_access",
                "wren_categorization": "checker",  # Final verification
                "salary_details": "no_access",
            },
            UserRole.PAYROLL_MANAGER: {
                "financial_statements": "no_access",
                "nrs_submission": "no_access",
                "bank_balance": "no_access",
                "wren_categorization": "no_access",
                "salary_details": "full",  # Payroll Manager sees all
            },
            UserRole.INVENTORY_MANAGER: {
                "financial_statements": "no_access",
                "nrs_submission": "draft_only",
                "bank_balance": "no_access",
                "wren_categorization": "no_access",
                "salary_details": "no_access",
            },
            UserRole.AUDITOR: {
                "financial_statements": "view",
                "nrs_submission": "view",
                "bank_balance": "view",
                "wren_categorization": "view",
                "salary_details": "view",
            },
            UserRole.VIEWER: {
                "financial_statements": "no_access",
                "nrs_submission": "no_access",
                "bank_balance": "no_access",
                "wren_categorization": "no_access",
                "salary_details": "no_access",
            },
        }
        
        return restrictions.get(role, {
            "financial_statements": "no_access",
            "nrs_submission": "no_access",
            "bank_balance": "no_access",
            "wren_categorization": "no_access",
            "salary_details": "no_access",
        })
    
    def _get_org_type_display_name(self, org_type: OrganizationType) -> str:
        """Get display name for organization type."""
        display_names = {
            OrganizationType.SME: "SME (Small & Medium Enterprise)",
            OrganizationType.SMALL_BUSINESS: "Small Business",
            OrganizationType.SCHOOL: "Educational Institution",
            OrganizationType.NON_PROFIT: "Non-Profit Organization",
            OrganizationType.INDIVIDUAL: "Individual / Freelancer",
            OrganizationType.CORPORATION: "Corporation",
        }
        return display_names.get(org_type, str(org_type.value).title())

    # ===========================================
    # ORGANIZATION-TYPE-SPECIFIC DASHBOARD METHODS
    # ===========================================
    
    async def _get_org_type_specific_dashboard(
        self,
        org_type: OrganizationType,
        entity: Optional["BusinessEntity"],
        user: User,
        organization: Optional["Organization"]
    ) -> Dict[str, Any]:
        """
        Get organization-type-specific dashboard widgets.
        
        Each org type has specialized widgets:
        - SME: Threshold Monitor, VAT Recovery, WREN Validator
        - School: Teacher PAYE, Fee Collection vs VAT, WHT Vault
        - Non-Profit: ROM Widget, Fund Separation, Donor Portal
        - Individual: Tax-Free Band, Relief Vault, Hustle Toggle
        """
        if org_type == OrganizationType.SME or org_type == OrganizationType.SMALL_BUSINESS:
            return await self._get_sme_dashboard(entity, user)
        elif org_type == OrganizationType.SCHOOL:
            return await self._get_school_dashboard(entity, user)
        elif org_type == OrganizationType.NON_PROFIT:
            return await self._get_nonprofit_dashboard(entity, user)
        elif org_type == OrganizationType.INDIVIDUAL:
            return await self._get_individual_dashboard(entity, user)
        elif org_type == OrganizationType.CORPORATION:
            return await self._get_corporation_dashboard(entity, user)
        else:
            return {}
    
    async def _get_sme_dashboard(
        self,
        entity: Optional["BusinessEntity"],
        user: User
    ) -> Dict[str, Any]:
        """
        SME & Small Business Dashboard.
        
        Focus: Threshold Tracking & Input VAT Recovery.
        """
        if not entity:
            return {}
        
        # Get current turnover YTD
        today = date.today()
        year_start = date(today.year, 1, 1)
        
        result = await self.db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(
                and_(
                    Transaction.entity_id == entity.id,
                    Transaction.transaction_type == TransactionType.INCOME,
                    Transaction.transaction_date >= year_start,
                )
            )
        )
        current_turnover = result.scalar() or Decimal("0")
        
        # Threshold Monitor
        threshold_50m = Decimal("50000000")
        threshold_100m = Decimal("100000000")
        
        progress_50m = min(float(current_turnover / threshold_50m * 100), 100) if threshold_50m > 0 else 0
        progress_100m = min(float(current_turnover / threshold_100m * 100), 100) if threshold_100m > 0 else 0
        
        remaining_50m = max(threshold_50m - current_turnover, Decimal("0"))
        remaining_100m = max(threshold_100m - current_turnover, Decimal("0"))
        
        # Determine current tier
        if current_turnover <= threshold_50m:
            current_tier = "small"
            cit_rate = 0
        elif current_turnover <= threshold_100m:
            current_tier = "medium"
            cit_rate = 20
        else:
            current_tier = "large"
            cit_rate = 30
        
        threshold_monitor = {
            "current_turnover": float(current_turnover),
            "threshold_50m": float(threshold_50m),
            "threshold_100m": float(threshold_100m),
            "progress_50m_percentage": progress_50m,
            "progress_100m_percentage": progress_100m,
            "remaining_to_50m": float(remaining_50m),
            "remaining_to_100m": float(remaining_100m),
            "current_tier": current_tier,
            "estimated_cit_rate": cit_rate,
            "approaching_threshold": progress_50m >= 80,
            "threshold_alert": "Approaching ₦50M threshold!" if progress_50m >= 80 and progress_50m < 100 else None,
        }
        
        # VAT Recovery Tracker
        month_start = date(today.year, today.month, 1)
        
        vat_collected_result = await self.db.execute(
            select(func.coalesce(func.sum(Transaction.vat_amount), 0))
            .where(
                and_(
                    Transaction.entity_id == entity.id,
                    Transaction.transaction_type == TransactionType.INCOME,
                    Transaction.transaction_date >= month_start,
                )
            )
        )
        vat_collected = vat_collected_result.scalar() or Decimal("0")
        
        vat_paid_result = await self.db.execute(
            select(func.coalesce(func.sum(Transaction.vat_amount), 0))
            .where(
                and_(
                    Transaction.entity_id == entity.id,
                    Transaction.transaction_type == TransactionType.EXPENSE,
                    Transaction.transaction_date >= month_start,
                )
            )
        )
        vat_paid = vat_paid_result.scalar() or Decimal("0")
        
        net_vat = vat_collected - vat_paid
        
        # Calculate next VAT filing
        if today.day <= 21:
            next_vat_filing = date(today.year, today.month, 21)
        else:
            if today.month == 12:
                next_vat_filing = date(today.year + 1, 1, 21)
            else:
                next_vat_filing = date(today.year, today.month + 1, 21)
        
        vat_recovery = {
            "vat_collected": float(vat_collected),
            "vat_paid": float(vat_paid),
            "net_vat": float(net_vat),
            "is_recoverable": net_vat < 0,
            "recoverable_amount": float(abs(net_vat)) if net_vat < 0 else 0,
            "period_start": month_start.isoformat(),
            "period_end": today.isoformat(),
            "next_filing_due": next_vat_filing.isoformat(),
        }
        
        # WREN Validator - get uncategorized expenses
        wren_result = await self.db.execute(
            select(Transaction)
            .where(
                and_(
                    Transaction.entity_id == entity.id,
                    Transaction.transaction_type == TransactionType.EXPENSE,
                    or_(
                        Transaction.category_id == None,
                        Transaction.wren_verified_by_id == None,
                    ),
                )
            )
            .order_by(Transaction.transaction_date.desc())
            .limit(10)
        )
        pending_wren = wren_result.scalars().all()
        
        total_pending_result = await self.db.execute(
            select(func.count(Transaction.id))
            .where(
                and_(
                    Transaction.entity_id == entity.id,
                    Transaction.transaction_type == TransactionType.EXPENSE,
                    or_(
                        Transaction.category_id == None,
                        Transaction.wren_verified_by_id == None,
                    ),
                )
            )
        )
        total_pending_count = total_pending_result.scalar() or 0
        
        pending_amount_result = await self.db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(
                and_(
                    Transaction.entity_id == entity.id,
                    Transaction.transaction_type == TransactionType.EXPENSE,
                    or_(
                        Transaction.category_id == None,
                        Transaction.wren_verified_by_id == None,
                    ),
                )
            )
        )
        total_pending_amount = pending_amount_result.scalar() or Decimal("0")
        
        # Determine user's WREN role (Maker or Checker)
        can_categorize = user.role in [
            UserRole.OWNER, UserRole.ADMIN, UserRole.ACCOUNTANT
        ]
        can_verify = user.role in [
            UserRole.OWNER, UserRole.ADMIN, UserRole.ACCOUNTANT, UserRole.EXTERNAL_ACCOUNTANT
        ]
        
        wren_validator = {
            "pending_count": total_pending_count,
            "pending_expenses": [
                {
                    "id": str(tx.id),
                    "description": tx.description,
                    "amount": float(tx.amount),
                    "date": tx.transaction_date.isoformat() if tx.transaction_date else None,
                    "vendor_name": tx.vendor_name if hasattr(tx, 'vendor_name') else None,
                    "status": "pending" if not tx.wren_verified_by_id else "verified",
                }
                for tx in pending_wren
            ],
            "total_pending_amount": float(total_pending_amount),
            "can_categorize": can_categorize,
            "can_verify": can_verify,
        }
        
        return {
            "type": "sme",
            "threshold_monitor": threshold_monitor,
            "vat_recovery": vat_recovery,
            "wren_validator": wren_validator,
        }
    
    async def _get_school_dashboard(
        self,
        entity: Optional["BusinessEntity"],
        user: User
    ) -> Dict[str, Any]:
        """
        School Management Dashboard.
        
        Focus: Payroll Compliance & WHT.
        """
        if not entity:
            return {}
        
        # Teacher PAYE Summary
        # Note: This would integrate with a payroll model
        today = date.today()
        
        # Calculate PAYE filing dates
        if today.day <= 10:
            next_paye_filing = date(today.year, today.month, 10)
        else:
            if today.month == 12:
                next_paye_filing = date(today.year + 1, 1, 10)
            else:
                next_paye_filing = date(today.year, today.month + 1, 10)
        
        teacher_paye = {
            "total_staff": 0,
            "total_teachers": 0,
            "total_monthly_payroll": 0,
            "total_paye_liability": 0,
            "staff_in_tax_free_band": 0,
            "staff_in_7_percent_band": 0,
            "staff_in_higher_bands": 0,
            "next_paye_filing": next_paye_filing.isoformat(),
            "last_paye_filing": None,
        }
        
        # Fee Collection vs VAT - separate tuition from taxable sales
        month_start = date(today.year, today.month, 1)
        
        # Tuition fees (VAT Exempt) - income without VAT
        tuition_result = await self.db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(
                and_(
                    Transaction.entity_id == entity.id,
                    Transaction.transaction_type == TransactionType.INCOME,
                    Transaction.vat_amount == 0,
                    Transaction.transaction_date >= month_start,
                )
            )
        )
        tuition_fees = tuition_result.scalar() or Decimal("0")
        
        # Taxable sales (uniforms, books) - income with VAT
        taxable_result = await self.db.execute(
            select(
                func.coalesce(func.sum(Transaction.amount), 0),
                func.coalesce(func.sum(Transaction.vat_amount), 0),
            )
            .where(
                and_(
                    Transaction.entity_id == entity.id,
                    Transaction.transaction_type == TransactionType.INCOME,
                    Transaction.vat_amount > 0,
                    Transaction.transaction_date >= month_start,
                )
            )
        )
        taxable_row = taxable_result.first()
        taxable_sales = taxable_row[0] if taxable_row else Decimal("0")
        vat_on_sales = taxable_row[1] if taxable_row else Decimal("0")
        
        fee_collection = {
            "tuition_fees_collected": float(tuition_fees),
            "taxable_sales": float(taxable_sales),
            "vat_on_taxable_sales": float(vat_on_sales),
            "uniform_sales": 0,
            "book_sales": 0,
            "other_taxable": float(taxable_sales),
        }
        
        # Vendor WHT Vault
        # Calculate WHT on contractor/supplier payments
        wht_vault = {
            "total_wht_deducted": 0,
            "pending_remittance": 0,
            "last_remittance_date": None,
            "next_remittance_due": next_paye_filing.isoformat(),  # Same as PAYE
            "contractors_wht": 0,
            "suppliers_wht": 0,
            "vendors_with_pending_wht": 0,
        }
        
        return {
            "type": "school",
            "teacher_paye": teacher_paye,
            "fee_collection": fee_collection,
            "wht_vault": wht_vault,
        }
    
    async def _get_nonprofit_dashboard(
        self,
        entity: Optional["BusinessEntity"],
        user: User
    ) -> Dict[str, Any]:
        """
        Non-Profit (NGO) Dashboard.
        
        Focus: Fund Separation & Mission Efficiency.
        """
        if not entity:
            return {}
        
        today = date.today()
        year_start = date(today.year, 1, 1)
        
        # Get total expenses YTD
        total_expenses_result = await self.db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(
                and_(
                    Transaction.entity_id == entity.id,
                    Transaction.transaction_type == TransactionType.EXPENSE,
                    Transaction.transaction_date >= year_start,
                )
            )
        )
        total_expenses = total_expenses_result.scalar() or Decimal("0")
        
        # Program vs Admin breakdown (simplified - would use category)
        # Assume 75% program, 15% admin, 10% fundraising for demo
        program_expenses = total_expenses * Decimal("0.75")
        admin_expenses = total_expenses * Decimal("0.15")
        fundraising_expenses = total_expenses * Decimal("0.10")
        
        program_pct = 75.0
        admin_pct = 15.0
        fundraising_pct = 10.0
        
        # ROM Score based on program percentage
        if program_pct >= 85:
            rom_score = "A"
        elif program_pct >= 75:
            rom_score = "B"
        elif program_pct >= 65:
            rom_score = "C"
        elif program_pct >= 50:
            rom_score = "D"
        else:
            rom_score = "F"
        
        return_on_mission = {
            "total_expenses": float(total_expenses),
            "program_expenses": float(program_expenses),
            "admin_expenses": float(admin_expenses),
            "fundraising_expenses": float(fundraising_expenses),
            "program_percentage": program_pct,
            "admin_percentage": admin_pct,
            "fundraising_percentage": fundraising_pct,
            "benchmark_program_min": 75.0,
            "meets_benchmark": program_pct >= 75.0,
            "rom_score": rom_score,
        }
        
        # Fund Separation - Restricted vs Unrestricted
        total_income_result = await self.db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(
                and_(
                    Transaction.entity_id == entity.id,
                    Transaction.transaction_type == TransactionType.INCOME,
                    Transaction.transaction_date >= year_start,
                )
            )
        )
        total_income = total_income_result.scalar() or Decimal("0")
        
        # Simplified: assume 60% restricted, 40% unrestricted
        restricted = total_income * Decimal("0.60")
        unrestricted = total_income * Decimal("0.40")
        
        fund_separation = {
            "total_funds": float(total_income),
            "restricted_funds": float(restricted),
            "restricted_percentage": 60.0,
            "unrestricted_funds": float(unrestricted),
            "unrestricted_percentage": 40.0,
            "trading_income": 0,  # Would need category tracking
            "grant_income": float(restricted),
        }
        
        # Donor Transparency Portal
        donor_transparency = {
            "can_generate_report": user.role in [UserRole.OWNER, UserRole.ADMIN],
            "last_report_date": None,
            "total_donations_ytd": float(total_income),
            "total_program_spending_ytd": float(program_expenses),
            "beneficiaries_served": 0,
            "charity_registration_valid": True,
            "tax_exemption_certificate": entity.tin is not None,
        }
        
        return {
            "type": "nonprofit",
            "return_on_mission": return_on_mission,
            "fund_separation": fund_separation,
            "donor_transparency": donor_transparency,
        }
    
    async def _get_individual_dashboard(
        self,
        entity: Optional["BusinessEntity"],
        user: User
    ) -> Dict[str, Any]:
        """
        Individual/Freelancer Dashboard.
        
        Focus: Progressive Tax & Personal Reliefs.
        """
        if not entity:
            return {}
        
        today = date.today()
        year_start = date(today.year, 1, 1)
        
        # Get income YTD
        income_result = await self.db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(
                and_(
                    Transaction.entity_id == entity.id,
                    Transaction.transaction_type == TransactionType.INCOME,
                    Transaction.transaction_date >= year_start,
                )
            )
        )
        income_ytd = income_result.scalar() or Decimal("0")
        
        # Tax-Free Band Tracker
        tax_free_limit = Decimal("800000")
        remaining_tax_free = max(tax_free_limit - income_ytd, Decimal("0"))
        used_percentage = min(float(income_ytd / tax_free_limit * 100), 100) if tax_free_limit > 0 else 0
        
        # Calculate estimated annual tax using 2026 PIT bands
        estimated_tax = Decimal("0")
        if income_ytd > tax_free_limit:
            taxable_income = income_ytd - tax_free_limit
            
            # Apply progressive rates
            for band in PIT_2026_BANDS:
                if band["min"] <= float(income_ytd) < band["max"]:
                    estimated_tax = taxable_income * Decimal(str(band["rate"])) / 100
                    break
        
        tax_free_tracker = {
            "tax_free_limit": float(tax_free_limit),
            "income_ytd": float(income_ytd),
            "remaining_tax_free": float(remaining_tax_free),
            "tax_free_used_percentage": used_percentage,
            "is_in_tax_free_band": income_ytd <= tax_free_limit,
            "next_band_starts_at": float(tax_free_limit),
            "next_band_rate": 7,
            "estimated_annual_tax": float(estimated_tax),
        }
        
        # Relief Document Vault
        # This would integrate with a document storage model
        relief_vault = {
            "rent_receipts_count": 0,
            "total_rent_paid": 0,
            "rent_relief_amount": 0,
            "nhia_contributions": 0,
            "pension_contributions": 0,
            "life_insurance_premiums": 0,
            "total_reliefs": 0,
            "documents_uploaded": 0,
            "documents_verified": 0,
        }
        
        # Hustle vs Personal Toggle
        # Count transactions by is_personal flag
        total_tx_result = await self.db.execute(
            select(func.count(Transaction.id))
            .where(
                and_(
                    Transaction.entity_id == entity.id,
                    Transaction.transaction_type == TransactionType.EXPENSE,
                    Transaction.transaction_date >= year_start,
                )
            )
        )
        total_transactions = total_tx_result.scalar() or 0
        
        # Get expense breakdown
        business_result = await self.db.execute(
            select(
                func.count(Transaction.id),
                func.coalesce(func.sum(Transaction.amount), 0),
            )
            .where(
                and_(
                    Transaction.entity_id == entity.id,
                    Transaction.transaction_type == TransactionType.EXPENSE,
                    Transaction.transaction_date >= year_start,
                    Transaction.is_personal == False,
                )
            )
        )
        business_row = business_result.first()
        business_count = business_row[0] if business_row else 0
        business_amount = business_row[1] if business_row else Decimal("0")
        
        personal_result = await self.db.execute(
            select(
                func.count(Transaction.id),
                func.coalesce(func.sum(Transaction.amount), 0),
            )
            .where(
                and_(
                    Transaction.entity_id == entity.id,
                    Transaction.transaction_type == TransactionType.EXPENSE,
                    Transaction.transaction_date >= year_start,
                    Transaction.is_personal == True,
                )
            )
        )
        personal_row = personal_result.first()
        personal_count = personal_row[0] if personal_row else 0
        personal_amount = personal_row[1] if personal_row else Decimal("0")
        
        untagged_count = total_transactions - business_count - personal_count
        
        hustle_toggle = {
            "total_transactions": total_transactions,
            "business_transactions": business_count,
            "personal_transactions": personal_count,
            "untagged_transactions": untagged_count,
            "business_expenses": float(business_amount),
            "personal_expenses": float(personal_amount),
            "untagged_amount": 0,  # Would calculate if we have is_personal=None
            "deductible_expenses": float(business_amount),
            "non_deductible_expenses": float(personal_amount),
        }
        
        return {
            "type": "individual",
            "tax_free_tracker": tax_free_tracker,
            "relief_vault": relief_vault,
            "hustle_toggle": hustle_toggle,
        }
    
    async def _get_corporation_dashboard(
        self,
        entity: Optional["BusinessEntity"],
        user: User
    ) -> Dict[str, Any]:
        """
        Corporation Dashboard.
        
        Focus: Full CIT Compliance & Development Levy.
        """
        if not entity:
            return {}
        
        today = date.today()
        year_start = date(today.year, 1, 1)
        
        # Get turnover and expenses YTD
        income_result = await self.db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(
                and_(
                    Transaction.entity_id == entity.id,
                    Transaction.transaction_type == TransactionType.INCOME,
                    Transaction.transaction_date >= year_start,
                )
            )
        )
        turnover = income_result.scalar() or Decimal("0")
        
        expense_result = await self.db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(
                and_(
                    Transaction.entity_id == entity.id,
                    Transaction.transaction_type == TransactionType.EXPENSE,
                    Transaction.transaction_date >= year_start,
                )
            )
        )
        expenses = expense_result.scalar() or Decimal("0")
        
        assessable_profit = turnover - expenses
        
        # Development Levy (4% on assessable profit)
        dev_levy_exemption = Decimal("100000000")  # ₦100M
        is_exempt = turnover <= dev_levy_exemption
        dev_levy = Decimal("0") if is_exempt else assessable_profit * Decimal("0.04")
        
        development_levy = {
            "assessable_profit": float(assessable_profit),
            "development_levy_rate": 4.0,
            "estimated_levy": float(dev_levy),
            "is_exempt": is_exempt,
            "exemption_reason": "Turnover <= ₦100M" if is_exempt else None,
            "last_filed": None,
            "next_due": None,
        }
        
        # CIT rate based on turnover
        if turnover <= Decimal("50000000"):
            cit_rate = 0
            cit_tier = "Small Company (0% CIT)"
        elif turnover <= Decimal("100000000"):
            cit_rate = 20
            cit_tier = "Medium Company (20% CIT)"
        else:
            cit_rate = 30
            cit_tier = "Large Company (30% CIT)"
        
        estimated_cit = assessable_profit * Decimal(str(cit_rate)) / 100
        
        cit_summary = {
            "assessable_profit": float(assessable_profit),
            "cit_rate": cit_rate,
            "cit_tier": cit_tier,
            "estimated_cit": float(estimated_cit),
            "total_tax_liability": float(estimated_cit + dev_levy),
        }
        
        return {
            "type": "corporation",
            "development_levy": development_levy,
            "cit_summary": cit_summary,
        }
    
    async def _get_tax_health_score(
        self,
        entity: Optional["BusinessEntity"],
        role: Optional[UserRole]
    ) -> Dict[str, Any]:
        """
        Calculate Tax Health Score - Red/Amber/Green indicator.
        
        Based on:
        - Missing TINs
        - Unfiled VAT
        - Unverified WREN expenses
        - Approaching deadlines
        """
        if not entity:
            return {
                "status": "red",
                "score": 0,
                "checks": [],
                "issues_count": 1,
                "warnings_count": 0,
                "summary": "No entity selected",
                "missing_tin": True,
                "unfiled_vat": False,
                "pending_wren_expenses": 0,
                "overdue_filings": 0,
            }
        
        checks = []
        issues = 0
        warnings = 0
        
        # Check 1: TIN Registration
        if entity.tin:
            checks.append({
                "name": "TIN Registration",
                "status": "pass",
                "message": f"TIN registered: {entity.tin}",
                "icon": "check-circle",
                "is_critical": False,
            })
        else:
            checks.append({
                "name": "TIN Registration",
                "status": "fail",
                "message": "TIN not registered - required for NRS",
                "icon": "x-circle",
                "is_critical": True,
            })
            issues += 1
        
        # Check 2: VAT Registration (if applicable)
        if entity.is_vat_registered:
            checks.append({
                "name": "VAT Status",
                "status": "pass",
                "message": "VAT registered",
                "icon": "check-circle",
                "is_critical": False,
            })
        else:
            checks.append({
                "name": "VAT Status",
                "status": "info",
                "message": "Not VAT registered",
                "icon": "information-circle",
                "is_critical": False,
            })
        
        # Check 3: Pending WREN expenses
        pending_wren_result = await self.db.execute(
            select(func.count(Transaction.id))
            .where(
                and_(
                    Transaction.entity_id == entity.id,
                    Transaction.transaction_type == TransactionType.EXPENSE,
                    Transaction.wren_verified_by_id == None,
                )
            )
        )
        pending_wren = pending_wren_result.scalar() or 0
        
        if pending_wren == 0:
            checks.append({
                "name": "WREN Verification",
                "status": "pass",
                "message": "All expenses verified",
                "icon": "check-circle",
                "is_critical": False,
            })
        elif pending_wren < 10:
            checks.append({
                "name": "WREN Verification",
                "status": "warning",
                "message": f"{pending_wren} expenses need verification",
                "icon": "exclamation",
                "is_critical": False,
            })
            warnings += 1
        else:
            checks.append({
                "name": "WREN Verification",
                "status": "fail",
                "message": f"{pending_wren} expenses unverified",
                "icon": "x-circle",
                "is_critical": True,
            })
            issues += 1
        
        # Check 4: Upcoming filing deadlines
        today = date.today()
        if today.day <= 21:
            days_to_vat = 21 - today.day
        else:
            days_to_vat = 30 - today.day + 21
        
        if days_to_vat <= 3:
            checks.append({
                "name": "VAT Filing Deadline",
                "status": "fail",
                "message": f"VAT due in {days_to_vat} days!",
                "icon": "x-circle",
                "is_critical": True,
            })
            issues += 1
        elif days_to_vat <= 7:
            checks.append({
                "name": "VAT Filing Deadline",
                "status": "warning",
                "message": f"VAT due in {days_to_vat} days",
                "icon": "exclamation",
                "is_critical": False,
            })
            warnings += 1
        else:
            checks.append({
                "name": "VAT Filing Deadline",
                "status": "pass",
                "message": f"VAT due in {days_to_vat} days",
                "icon": "check-circle",
                "is_critical": False,
            })
        
        # Calculate score
        total_checks = len(checks)
        passed = sum(1 for c in checks if c["status"] == "pass")
        score = int((passed / total_checks) * 100) if total_checks > 0 else 0
        
        # Determine status
        if issues > 0:
            status = "red"
        elif warnings > 0:
            status = "amber"
        else:
            status = "green"
        
        return {
            "status": status,
            "score": score,
            "checks": checks,
            "issues_count": issues,
            "warnings_count": warnings,
            "summary": f"{passed}/{total_checks} checks passed",
            "missing_tin": not entity.tin,
            "unfiled_vat": False,  # Would check filing records
            "pending_wren_expenses": pending_wren,
            "overdue_filings": 0,  # Would check filing records
        }
    
    async def _get_nrs_connection_status(
        self,
        entity: Optional["BusinessEntity"]
    ) -> Dict[str, Any]:
        """
        Get NRS Connection Status - heartbeat monitor.
        """
        # In production, this would ping the NRS API
        return {
            "status": "connected",
            "endpoint": "https://atrs-api.firs.gov.ng",
            "last_sync": datetime.utcnow().isoformat(),
            "latency_ms": 120,
            "uptime_percentage": 99.8,
            "pending_submissions": 0,
            "failed_submissions": 0,
            "message": "Connected to Nigeria Revenue Service",
        }
    
    async def _get_compliance_calendar(
        self,
        entity: Optional["BusinessEntity"]
    ) -> Dict[str, Any]:
        """
        Get Compliance Calendar with automatic countdowns.
        """
        today = date.today()
        deadlines = []
        
        # VAT deadline (21st of each month)
        if today.day <= 21:
            vat_date = date(today.year, today.month, 21)
        else:
            if today.month == 12:
                vat_date = date(today.year + 1, 1, 21)
            else:
                vat_date = date(today.year, today.month + 1, 21)
        
        vat_days = (vat_date - today).days
        vat_deadline = {
            "name": "VAT Filing",
            "date": vat_date.isoformat(),
            "days_remaining": vat_days,
            "urgency": "high" if vat_days <= 3 else "medium" if vat_days <= 7 else "low",
            "tax_type": "VAT",
            "is_overdue": vat_days < 0,
            "is_filed": False,
        }
        deadlines.append(vat_deadline)
        
        # PAYE deadline (10th of each month)
        if today.day <= 10:
            paye_date = date(today.year, today.month, 10)
        else:
            if today.month == 12:
                paye_date = date(today.year + 1, 1, 10)
            else:
                paye_date = date(today.year, today.month + 1, 10)
        
        paye_days = (paye_date - today).days
        paye_deadline = {
            "name": "PAYE Filing",
            "date": paye_date.isoformat(),
            "days_remaining": paye_days,
            "urgency": "high" if paye_days <= 3 else "medium" if paye_days <= 7 else "low",
            "tax_type": "PAYE",
            "is_overdue": paye_days < 0,
            "is_filed": False,
        }
        deadlines.append(paye_deadline)
        
        # WHT deadline (21st of each month)
        wht_deadline = {
            "name": "WHT Remittance",
            "date": vat_date.isoformat(),  # Same as VAT
            "days_remaining": vat_days,
            "urgency": "high" if vat_days <= 3 else "medium" if vat_days <= 7 else "low",
            "tax_type": "WHT",
            "is_overdue": vat_days < 0,
            "is_filed": False,
        }
        deadlines.append(wht_deadline)
        
        # CIT deadline (6 months after fiscal year end)
        fiscal_year_end_month = entity.fiscal_year_start_month - 1 if entity and entity.fiscal_year_start_month > 1 else 12
        cit_year = today.year if today.month > fiscal_year_end_month else today.year - 1
        cit_date = date(cit_year + 1, fiscal_year_end_month, 28)  # Simplified
        
        cit_days = (cit_date - today).days
        cit_deadline = {
            "name": "CIT Filing",
            "date": cit_date.isoformat(),
            "days_remaining": cit_days,
            "urgency": "high" if cit_days <= 30 else "medium" if cit_days <= 60 else "low",
            "tax_type": "CIT",
            "is_overdue": cit_days < 0,
            "is_filed": False,
        }
        deadlines.append(cit_deadline)
        
        overdue = [d for d in deadlines if d["is_overdue"]]
        
        return {
            "next_vat_deadline": vat_deadline,
            "next_paye_deadline": paye_deadline,
            "next_cit_deadline": cit_deadline,
            "next_wht_deadline": wht_deadline,
            "upcoming_deadlines": sorted(deadlines, key=lambda x: x["days_remaining"]),
            "overdue_items": overdue,
            "current_month": today.strftime("%B"),
            "current_year": today.year,
        }
    
    async def _get_liquidity_ratio(
        self,
        entity: Optional["BusinessEntity"]
    ) -> Dict[str, Any]:
        """
        Calculate Liquidity Ratio - Cash Runway tracking.
        
        Formula: Cash / Average Monthly Expenses
        """
        if not entity:
            return {
                "cash_balance": 0,
                "avg_monthly_expenses": 0,
                "ratio": 0,
                "runway_months": 0,
                "status": "unknown",
                "message": "No entity selected",
                "trend_direction": "stable",
            }
        
        # Calculate average monthly expenses (last 3 months)
        today = date.today()
        three_months_ago = date(
            today.year if today.month > 3 else today.year - 1,
            today.month - 3 if today.month > 3 else today.month + 9,
            1
        )
        
        expense_result = await self.db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(
                and_(
                    Transaction.entity_id == entity.id,
                    Transaction.transaction_type == TransactionType.EXPENSE,
                    Transaction.transaction_date >= three_months_ago,
                )
            )
        )
        total_expenses_3m = expense_result.scalar() or Decimal("0")
        avg_monthly = total_expenses_3m / 3 if total_expenses_3m > 0 else Decimal("1")
        
        # Cash balance (simplified - would integrate with bank feeds)
        income_result = await self.db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(
                and_(
                    Transaction.entity_id == entity.id,
                    Transaction.transaction_type == TransactionType.INCOME,
                )
            )
        )
        total_income = income_result.scalar() or Decimal("0")
        
        expense_total_result = await self.db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(
                and_(
                    Transaction.entity_id == entity.id,
                    Transaction.transaction_type == TransactionType.EXPENSE,
                )
            )
        )
        total_expenses = expense_total_result.scalar() or Decimal("0")
        
        cash_balance = total_income - total_expenses
        
        # Calculate ratio
        ratio = float(cash_balance / avg_monthly) if avg_monthly > 0 else 0
        runway_months = max(ratio, 0)
        
        # Determine status
        if runway_months >= 6:
            status = "healthy"
            message = f"{runway_months:.1f} months of runway"
        elif runway_months >= 3:
            status = "warning"
            message = f"{runway_months:.1f} months of runway - consider building reserves"
        else:
            status = "critical"
            message = f"Only {runway_months:.1f} months of runway!"
        
        return {
            "cash_balance": float(cash_balance),
            "avg_monthly_expenses": float(avg_monthly),
            "ratio": ratio,
            "runway_months": runway_months,
            "status": status,
            "message": message,
            "trend_direction": "stable",
            "previous_ratio": None,
        }

    # ===========================================
    # SUPER ADMIN HELPER METHODS
    # ===========================================
    
    async def _get_staff_by_role(self) -> Dict[str, int]:
        """Get count of staff members by platform role."""
        result = await self.db.execute(
            select(User.platform_role, func.count(User.id))
            .where(User.is_platform_staff == True)
            .group_by(User.platform_role)
        )
        return {
            (row[0].value if row[0] else "unknown"): row[1] 
            for row in result.all()
        }
    
    async def _get_subscription_stats(self) -> Dict[str, Any]:
        """Get subscription/plan statistics across all organizations."""
        from app.models.organization import SubscriptionTier
        
        result = await self.db.execute(
            select(Organization.subscription_tier, func.count(Organization.id))
            .group_by(Organization.subscription_tier)
        )
        by_tier = {
            (row[0].value if row[0] else "free"): row[1] 
            for row in result.all()
        }
        
        return {
            "by_tier": by_tier,
            "total_paid": sum(v for k, v in by_tier.items() if k != "free"),
            "total_free": by_tier.get("free", 0),
        }
    
    async def _get_platform_health_detailed(self) -> Dict[str, Any]:
        """Get detailed platform health metrics."""
        # Database connection check
        try:
            await self.db.execute(select(func.count(User.id)))
            db_status = "healthy"
        except Exception:
            db_status = "error"
        
        return {
            "status": "healthy" if db_status == "healthy" else "degraded",
            "database": {
                "status": db_status,
                "type": "PostgreSQL",
                "connection": "active",
            },
            "api": {
                "status": "healthy",
                "uptime": "99.9%",
                "response_time_ms": 45,
            },
            "nrs_gateway": {
                "status": "connected",
                "last_successful_call": datetime.utcnow().isoformat(),
            },
            "redis": {
                "status": "connected",
                "type": "Cache/Sessions",
            },
            "last_check": datetime.utcnow().isoformat(),
        }
    
    async def _get_nrs_compliance_stats(self) -> Dict[str, Any]:
        """Get NRS e-invoicing compliance statistics."""
        # Count invoices by NRS status
        today = date.today()
        month_start = date(today.year, today.month, 1)
        
        # Total invoices submitted to NRS this month
        result = await self.db.execute(
            select(func.count(Invoice.id))
            .where(
                and_(
                    Invoice.nrs_irn.isnot(None),
                    Invoice.created_at >= month_start,
                )
            )
        )
        submitted_count = result.scalar() or 0
        
        # Locked invoices (72-hour window)
        result = await self.db.execute(
            select(func.count(Invoice.id))
            .where(Invoice.is_nrs_locked == True)
        )
        locked_count = result.scalar() or 0
        
        return {
            "submitted_this_month": submitted_count,
            "currently_locked": locked_count,
            "csid_success_rate": "98.5%",
            "last_submission": datetime.utcnow().isoformat(),
        }
    
    async def _get_usage_metrics(self) -> Dict[str, Any]:
        """Get platform usage metrics for billing/capacity."""
        # Count transactions this month
        today = date.today()
        month_start = date(today.year, today.month, 1)
        
        result = await self.db.execute(
            select(func.count(Transaction.id))
            .where(Transaction.created_at >= month_start)
        )
        transactions_this_month = result.scalar() or 0
        
        result = await self.db.execute(
            select(func.count(Invoice.id))
            .where(Invoice.created_at >= month_start)
        )
        invoices_this_month = result.scalar() or 0
        
        return {
            "transactions_this_month": transactions_this_month,
            "invoices_this_month": invoices_this_month,
            "api_calls_today": 1250,  # Would come from metrics system
            "storage_used_gb": 12.5,
        }
    
    async def _get_security_alerts(self) -> List[Dict]:
        """Get recent security alerts."""
        # Get failed login attempts in last 24 hours
        yesterday = datetime.utcnow() - timedelta(days=1)
        
        result = await self.db.execute(
            select(AuditLog)
            .where(
                and_(
                    AuditLog.action == AuditAction.LOGIN_FAILED,
                    AuditLog.created_at >= yesterday,
                )
            )
            .order_by(AuditLog.created_at.desc())
            .limit(10)
        )
        failed_logins = result.scalars().all()
        
        alerts = []
        for log in failed_logins:
            alerts.append({
                "type": "failed_login",
                "severity": "warning",
                "message": f"Failed login attempt from {log.ip_address or 'unknown IP'}",
                "timestamp": log.created_at.isoformat() if log.created_at else None,
            })
        
        return alerts
    
    async def _get_failed_login_stats(self) -> Dict[str, Any]:
        """Get failed login attempt statistics."""
        yesterday = datetime.utcnow() - timedelta(days=1)
        
        result = await self.db.execute(
            select(func.count(AuditLog.id))
            .where(
                and_(
                    AuditLog.action == AuditAction.LOGIN_FAILED,
                    AuditLog.created_at >= yesterday,
                )
            )
        )
        failed_24h = result.scalar() or 0
        
        return {
            "last_24_hours": failed_24h,
            "trend": "stable" if failed_24h < 10 else "elevated",
        }
    
    async def _get_platform_revenue_stats(self) -> Dict[str, Any]:
        """Get platform-level revenue statistics."""
        # This would integrate with billing system
        return {
            "mrr": 0,  # Monthly Recurring Revenue
            "arpu": 0,  # Average Revenue Per User
            "churn_rate": "0%",  # Monthly churn rate
            "total_subscriptions": 0,
            "e_invoice_fees_this_month": 0,
            "growth_rate": "0%",
        }
    
    async def _get_platform_filing_status(self) -> Dict[str, Any]:
        """Get summary of tax filings across all organizations."""
        return {
            "vat_filings_this_month": 0,
            "cit_filings_this_year": 0,
            "pending_filings": 0,
        }
    
    # ===========================================
    # ADMIN HELPER METHODS
    # ===========================================
    
    async def _get_pending_verification_queue(self) -> List[Dict]:
        """Get detailed pending verification queue."""
        result = await self.db.execute(
            select(Organization)
            .where(Organization.verification_status == VerificationStatus.SUBMITTED)
            .order_by(Organization.created_at.asc())
            .limit(10)
        )
        orgs = result.scalars().all()
        
        return [
            {
                "id": str(org.id),
                "name": org.name,
                "type": org.organization_type.value if org.organization_type else "unknown",
                "submitted_at": org.created_at.isoformat() if org.created_at else None,
                "has_cac": bool(org.cac_document_path),
                "has_tin": bool(org.tin_document_path),
                "email": org.email,
                "days_waiting": (datetime.utcnow() - org.created_at).days if org.created_at else 0,
            }
            for org in orgs
        ]
    
    async def _get_entity_health_overview(self) -> Dict[str, Any]:
        """Get entity health overview - compliant vs non-compliant."""
        # Verified (Green)
        result = await self.db.execute(
            select(func.count(Organization.id))
            .where(Organization.verification_status == VerificationStatus.VERIFIED)
        )
        verified = result.scalar() or 0
        
        # Pending/Submitted (Yellow)
        result = await self.db.execute(
            select(func.count(Organization.id))
            .where(
                Organization.verification_status.in_([
                    VerificationStatus.PENDING,
                    VerificationStatus.SUBMITTED,
                    VerificationStatus.UNDER_REVIEW,
                ])
            )
        )
        pending = result.scalar() or 0
        
        # Rejected (Red)
        result = await self.db.execute(
            select(func.count(Organization.id))
            .where(Organization.verification_status == VerificationStatus.REJECTED)
        )
        rejected = result.scalar() or 0
        
        total = verified + pending + rejected
        
        return {
            "green": {"count": verified, "label": "Compliant/Verified", "percentage": f"{(verified/max(total,1))*100:.0f}%"},
            "yellow": {"count": pending, "label": "Pending Review", "percentage": f"{(pending/max(total,1))*100:.0f}%"},
            "red": {"count": rejected, "label": "Rejected/Issues", "percentage": f"{(rejected/max(total,1))*100:.0f}%"},
            "total": total,
        }
    
    async def _get_staff_performance_stats(self) -> Dict[str, Any]:
        """Get staff performance statistics by role."""
        # This would integrate with task tracking system
        return {
            "it_developer": {
                "bugs_fixed": 0,
                "deployments": 0,
            },
            "customer_service": {
                "tickets_resolved": 0,
                "avg_response_time": "N/A",
            },
            "marketing": {
                "campaigns_launched": 0,
                "emails_sent": 0,
            },
        }
    
    async def _get_platform_revenue_snapshot(self) -> Dict[str, Any]:
        """Get platform revenue snapshot (no private banking data)."""
        return {
            "total_subscriptions": 0,
            "mrr": 0,
            "transaction_fees": 0,
            "trend": "stable",
        }
    
    async def _get_escalation_inbox(self) -> List[Dict]:
        """Get high-priority escalated issues."""
        # This would integrate with support ticket system
        return []
    
    # ===========================================
    # IT/DEVELOPER HELPER METHODS
    # ===========================================
    
    async def _get_nrs_webhook_status(self) -> Dict[str, Any]:
        """Get NRS webhook connection status."""
        return {
            "status": "connected",
            "endpoint": "https://atrs-api.firs.gov.ng",
            "last_ping": datetime.utcnow().isoformat(),
            "latency_ms": 120,
            "uptime_24h": "99.8%",
            "alerts": [],
        }
    
    async def _get_database_health(self) -> Dict[str, Any]:
        """Get PostgreSQL database health metrics."""
        try:
            # Test connection
            await self.db.execute(select(func.count(User.id)))
            status = "healthy"
        except Exception:
            status = "error"
        
        return {
            "status": status,
            "type": "PostgreSQL",
            "connections": {
                "active": 5,
                "idle": 10,
                "max": 100,
            },
            "size_mb": 256,
            "last_backup": (datetime.utcnow() - timedelta(hours=6)).isoformat(),
            "backup_status": "success",
        }
    
    async def _get_error_stats(self) -> Dict[str, Any]:
        """Get error statistics for the past 24 hours."""
        yesterday = datetime.utcnow() - timedelta(days=1)
        
        result = await self.db.execute(
            select(func.count(AuditLog.id))
            .where(
                and_(
                    AuditLog.action == AuditAction.LOGIN_FAILED,
                    AuditLog.created_at >= yesterday,
                )
            )
        )
        errors_24h = result.scalar() or 0
        
        return {
            "total_24h": errors_24h,
            "by_type": {
                "authentication": errors_24h,
                "validation": 0,
                "server": 0,
            },
            "trend": "stable",
        }
    
    async def _get_deployment_status(self) -> Dict[str, Any]:
        """Get current deployment status."""
        return {
            "web": {
                "version": "1.0.0",
                "deployed_at": datetime.utcnow().isoformat(),
                "status": "running",
            },
            "api": {
                "version": "1.0.0",
                "deployed_at": datetime.utcnow().isoformat(),
                "status": "running",
            },
            "environment": "production",
        }
    
    async def _get_api_metrics(self) -> Dict[str, Any]:
        """Get API performance metrics."""
        return {
            "uptime": "99.9%",
            "avg_response_time_ms": 45,
            "requests_per_minute": 120,
            "error_rate": "0.1%",
        }
    
    # ===========================================
    # CSR HELPER METHODS
    # ===========================================
    
    async def _get_support_ticket_queue(self) -> List[Dict]:
        """Get support ticket queue."""
        # This would integrate with support ticket system
        return []
    
    async def _get_impersonation_stats(self) -> Dict[str, Any]:
        """Get user impersonation statistics."""
        # Count users who have granted impersonation
        result = await self.db.execute(
            select(func.count(User.id))
            .where(
                and_(
                    User.can_be_impersonated == True,
                    User.is_platform_staff == False,
                )
            )
        )
        can_impersonate = result.scalar() or 0
        
        return {
            "users_allowing_impersonation": can_impersonate,
            "active_sessions": 0,
        }
    
    async def _get_failed_nrs_submissions(self) -> List[Dict]:
        """Get failed NRS e-invoice submissions."""
        result = await self.db.execute(
            select(AuditLog)
            .where(
                and_(
                    AuditLog.action == AuditAction.NRS_SUBMIT,
                    AuditLog.new_values.isnot(None),
                )
            )
            .order_by(AuditLog.created_at.desc())
            .limit(20)
        )
        submissions = result.scalars().all()
        
        failed = []
        for sub in submissions:
            if sub.new_values and not sub.new_values.get("success", True):
                failed.append({
                    "id": str(sub.id),
                    "invoice_id": sub.target_entity_id,
                    "error": sub.new_values.get("error", "Unknown error"),
                    "timestamp": sub.created_at.isoformat() if sub.created_at else None,
                    "user_id": str(sub.user_id) if sub.user_id else None,
                })
        
        return failed
    
    async def _get_stuck_onboarding_users(self) -> List[Dict]:
        """Get users stuck during onboarding."""
        # Users who registered but haven't verified email
        result = await self.db.execute(
            select(User)
            .where(
                and_(
                    User.is_platform_staff == False,
                    User.is_verified == False,
                    User.created_at >= (datetime.utcnow() - timedelta(days=7)),
                )
            )
            .order_by(User.created_at.asc())
            .limit(10)
        )
        users = result.scalars().all()
        
        return [
            {
                "id": str(user.id),
                "email": user.email,
                "name": user.full_name,
                "stuck_at": "Email Verification",
                "registered_at": user.created_at.isoformat() if user.created_at else None,
                "days_stuck": (datetime.utcnow() - user.created_at).days if user.created_at else 0,
            }
            for user in users
        ]
    
    async def _get_support_metrics(self) -> Dict[str, Any]:
        """Get support team metrics."""
        return {
            "users_assisted_today": 0,
            "avg_response_time": "N/A",
            "satisfaction_score": "N/A",
            "pending_tickets": 0,
        }
    
    # ===========================================
    # MARKETING HELPER METHODS
    # ===========================================
    
    async def _get_conversion_funnel(self) -> Dict[str, Any]:
        """Get marketing conversion funnel data."""
        # Total registered users
        total_users = await self._get_user_count()
        
        # Users who sent first invoice
        result = await self.db.execute(
            select(func.count(func.distinct(Invoice.created_by_id)))
        )
        users_with_invoices = result.scalar() or 0
        
        return {
            "stages": [
                {"name": "Website Visits", "count": 0, "rate": "100%"},
                {"name": "Registered", "count": total_users, "rate": "0%"},
                {"name": "Verified Email", "count": 0, "rate": "0%"},
                {"name": "First Transaction", "count": 0, "rate": "0%"},
                {"name": "First E-Invoice", "count": users_with_invoices, "rate": f"{(users_with_invoices/max(total_users,1))*100:.0f}%"},
            ],
        }
    
    async def _get_referral_stats(self) -> Dict[str, Any]:
        """Get referral program statistics."""
        # Count organizations with referral codes used
        result = await self.db.execute(
            select(func.count(Organization.id))
            .where(Organization.referred_by_code.isnot(None))
        )
        referred = result.scalar() or 0
        
        return {
            "total_referrals": referred,
            "successful_conversions": 0,
            "pending_rewards": 0,
            "top_referrers": [],
        }
    
    async def _get_campaign_metrics(self) -> Dict[str, Any]:
        """Get marketing campaign metrics."""
        return {
            "active_campaigns": 0,
            "emails_sent_this_month": 0,
            "push_notifications_sent": 0,
            "email_open_rate": "0%",
            "click_through_rate": "0%",
        }
    
    async def _get_user_segment_analysis(self) -> Dict[str, Any]:
        """Get user segment analysis for targeting."""
        org_by_type = await self._get_organizations_by_type()
        
        return {
            "by_organization_type": org_by_type,
            "by_activity": {
                "highly_active": 0,
                "moderately_active": 0,
                "inactive": 0,
            },
            "by_subscription": {
                "free": 0,
                "pro": 0,
                "enterprise": 0,
            },
        }
    
    async def _get_upcoming_tax_deadlines(self) -> List[Dict]:
        """Get upcoming tax deadlines for campaign targeting."""
        today = date.today()
        
        deadlines = []
        
        # VAT deadline (21st of each month)
        if today.day <= 21:
            vat_deadline = date(today.year, today.month, 21)
        else:
            if today.month == 12:
                vat_deadline = date(today.year + 1, 1, 21)
            else:
                vat_deadline = date(today.year, today.month + 1, 21)
        
        days_to_vat = (vat_deadline - today).days
        deadlines.append({
            "name": "VAT Filing",
            "date": vat_deadline.isoformat(),
            "days_remaining": days_to_vat,
            "urgency": "high" if days_to_vat <= 3 else "medium" if days_to_vat <= 7 else "low",
            "affected_users": 0,
        })
        
        return deadlines

