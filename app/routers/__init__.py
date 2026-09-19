"""
Tekvwa Pro Audit - Routers Package

FastAPI route handlers.

Routers:
- auth: Authentication (login, register, password reset)
- staff: Platform staff management (RBAC for internal users)
- organization_users: Organization user management
- entities: Business entity management
- categories: Transaction categories
- vendors: Vendor management
- customers: Customer management  
- transactions: Transaction management
- invoices: Invoice management
- inventory: Inventory management
- receipts: Receipt/file management
- reports: Reports and dashboard
- audit: Audit trail
- tax: Tax management
- tax_2026: 2026 Tax Reform APIs
- fixed_assets: Fixed Asset Register (2026)
- dashboard: Organization dashboards API (NTAA 2025)
- notifications: In-app notifications
- self_assessment: Tax self-assessment and returns
- organization_settings: Organization settings, subscriptions, API keys
- bulk_operations: Bulk import/export operations
- exports: Report and data exports
- search_analytics: Global search and analytics
- payroll: Payroll management with Nigerian compliance
- payroll_views: Payroll HTML page views
- views: HTML page views
- advanced_accounting: 2026 Tax Reform advanced features (3-way matching, WHT vault, approvals, AI)
- business_intelligence: BIK Automator, NIBSS Pension, Growth Radar, Inventory Management
- forensic_audit: World-class forensic audit (Benford's Law, Z-score, NRS Gap Analysis, WORM)
- advanced_audit: Enterprise audit (Explainability, Replay, Confidence Scoring, Attestation, Export, Behavioral)
- audit_system: Advanced Audit System (Immutable Evidence, Reproducible Runs, Auditor Read-Only, Human-Readable Findings)
- admin_sku: Platform admin SKU management (tier pricing in Naira, trials, usage analytics)
"""

from app.routers import (
    auth,
    staff,
    organization_users,
    entities,
    categories,
    vendors,
    customers,
    transactions,
    invoices,
    inventory,
    receipts,
    reports,
    audit,
    tax,
    tax_2026,
    fixed_assets,
    dashboard,
    notifications,
    self_assessment,
    organization_settings,
    bulk_operations,
    exports,
    search_analytics,
    payroll,
    payroll_views,
    payroll_advanced,
    views,
    sales,
    advanced_accounting,
    business_intelligence,
    forensic_audit,
    advanced_audit,
    audit_system,
    nrs,
    bank_reconciliation,
    expense_claims,
    ml_ai,
    evidence_routes,
    accounting,
    admin_sku,
    admin_tenants,
    billing,
    advanced_billing,
    support_tickets,
    legal_holds,
    ml_jobs,
    risk_signals,
    upsell,
    admin_emergency,
    admin_user_search,
    admin_platform_staff,
    admin_verification,
    admin_audit_logs,
    admin_health,
    admin_settings,
    admin_security,
    admin_api_keys,
    admin_automation,
)

__all__ = [
    "auth",
    "staff",
    "organization_users",
    "entities",
    "categories",
    "vendors",
    "customers",
    "transactions",
    "invoices",
    "inventory",
    "receipts",
    "reports",
    "audit",
    "tax",
    "tax_2026",
    "fixed_assets",
    "dashboard",
    "notifications",
    "self_assessment",
    "organization_settings",
    "bulk_operations",
    "exports",
    "search_analytics",
    "payroll",
    "payroll_views",
    "payroll_advanced",
    "views",
    "sales",
    "advanced_accounting",
    "business_intelligence",
    "forensic_audit",
    "advanced_audit",
    "audit_system",
    "nrs",
    "bank_reconciliation",
    "expense_claims",
    "ml_ai",
    "evidence_routes",
    "accounting",
    "admin_sku",
    "admin_tenants",
    "billing",
    "advanced_billing",
    "support_tickets",
    "legal_holds",
    "ml_jobs",
    "risk_signals",
    "upsell",
    "admin_emergency",
    "admin_user_search",
    "admin_platform_staff",
    "admin_verification",
    "admin_audit_logs",
    "admin_health",
    "admin_settings",
    "admin_security",
    "admin_api_keys",
    "admin_automation",
]
