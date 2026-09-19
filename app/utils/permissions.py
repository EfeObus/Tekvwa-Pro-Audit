"""
Tekvwa Pro Audit - Permissions System

Comprehensive RBAC permissions for platform staff and organization users.

NTAA 2025 Compliance Features:
- 72-Hour Legal Lock: CANCEL_NRS_SUBMISSION permission (Owner only)
- Maker-Checker SoD: VERIFY_WREN permission (cannot verify own transactions)
- External Accountant: Tax filing + reports without payroll or fund movement

Permission Matrix:
==================

Platform Staff Permissions:
---------------------------
| Permission                    | Super Admin | Admin | IT/Dev | CSR | Marketing |
|-------------------------------|-------------|-------|--------|-----|-----------|
| manage_platform_settings      | X           |       |        |     |           |
| manage_api_keys               | X           |       |        |     |           |
| handle_escalations            | X           |       |        |     |           |
| onboard_admin                 | X           |       |        |     |           |
| onboard_staff                 | X           | X     |        |     |           |
| verify_organizations          | X           | X     |        |     |           |
| manage_internal_staff         | X           | X     |        |     |           |
| view_global_analytics         | X           | X     |        |     | X         |
| access_backend                | X           | X     | X      |     |           |
| manage_codebase               | X           |       | X      |     |           |
| monitor_database              | X           |       | X      |     |           |
| manage_webhooks               | X           |       | X      |     |           |
| view_user_data                | X           | X     |        | X   |           |
| impersonate_user              | X           |       |        | X   |           |
| troubleshoot_submissions      | X           | X     | X      | X   |           |
| manage_campaigns              | X           | X     |        |     | X         |
| manage_referrals              | X           | X     |        |     | X         |
| view_user_growth              | X           | X     |        |     | X         |

Organization User Permissions (NTAA 2025 Updated):
--------------------------------------------------
| Permission                    | Owner | Admin | Accountant | Ext Acct | Auditor | Payroll | Inventory | Viewer |
|-------------------------------|-------|-------|------------|----------|---------|---------|-----------|--------|
| manage_organization           | X     |       |            |          |         |         |           |        |
| manage_users                  | X     | X     |            |          |         |         |           |        |
| manage_entities               | X     | X     |            |          |         |         |           |        |
| manage_settings               | X     | X     |            |          |         |         |           |        |
| view_all_transactions         | X     | X     | X          | X        | X       |         |           |        |
| create_transactions           | X     | X     | X          |          |         |         |           |        |
| edit_transactions             | X     | X     | X          |          |         |         |           |        |
| delete_transactions           | X     | X     |            |          |         |         |           |        |
| verify_wren (SoD)             | X     | X     | X          | X        |         |         |           |        |
| manage_invoices               | X     | X     | X          |          |         |         |           |        |
| cancel_nrs_submission (Lock)  | X     |       |            |          |         |         |           |        |
| view_invoices                 | X     | X     | X          | X        | X       |         |           | X      |
| manage_tax_filings            | X     | X     | X          | X        |         |         |           |        |
| view_tax_filings              | X     | X     | X          | X        | X       |         |           |        |
| manage_payroll                | X     | X     |            |          |         | X       |           |        |
| view_payroll                  | X     | X     | X          |          | X       | X       |           |        |
| manage_inventory              | X     | X     |            |          |         |         | X         |        |
| view_inventory                | X     | X     | X          |          | X       |         | X         | X      |
| view_reports                  | X     | X     | X          | X        | X       |         |           | X      |
| export_data                   | X     | X     | X          | X        | X       |         |           |        |
| manage_customers              | X     | X     | X          |          |         |         |           |        |
| view_customers                | X     | X     | X          | X        | X       |         |           | X      |
| manage_vendors                | X     | X     | X          |          |         |         | X         |        |
| view_vendors                  | X     | X     | X          | X        | X       |         | X         | X      |
"""

from enum import Enum
from typing import List, Set

from app.models.user import PlatformRole, UserRole


# ===========================================
# PERMISSION ENUMS
# ===========================================

class PlatformPermission(str, Enum):
    """Permissions for platform staff."""
    
    # Super Admin Only
    MANAGE_PLATFORM_SETTINGS = "manage_platform_settings"
    MANAGE_API_KEYS = "manage_api_keys"
    HANDLE_ESCALATIONS = "handle_escalations"
    ONBOARD_ADMIN = "onboard_admin"
    
    # Admin and above
    ONBOARD_STAFF = "onboard_staff"
    VERIFY_ORGANIZATIONS = "verify_organizations"
    MANAGE_INTERNAL_STAFF = "manage_internal_staff"
    VIEW_GLOBAL_ANALYTICS = "view_global_analytics"
    
    # IT/Developer and above
    ACCESS_BACKEND = "access_backend"
    MANAGE_CODEBASE = "manage_codebase"
    MONITOR_DATABASE = "monitor_database"
    MANAGE_WEBHOOKS = "manage_webhooks"
    
    # CSR
    VIEW_USER_DATA = "view_user_data"
    IMPERSONATE_USER = "impersonate_user"
    TROUBLESHOOT_SUBMISSIONS = "troubleshoot_submissions"
    
    # Marketing
    MANAGE_CAMPAIGNS = "manage_campaigns"
    MANAGE_REFERRALS = "manage_referrals"
    VIEW_USER_GROWTH = "view_user_growth"


class OrganizationPermission(str, Enum):
    """Permissions for organization users."""
    
    # Organization Management
    MANAGE_ORGANIZATION = "manage_organization"
    MANAGE_USERS = "manage_users"
    MANAGE_ENTITIES = "manage_entities"
    MANAGE_SETTINGS = "manage_settings"
    
    # Transactions
    VIEW_ALL_TRANSACTIONS = "view_all_transactions"
    CREATE_TRANSACTIONS = "create_transactions"
    EDIT_TRANSACTIONS = "edit_transactions"
    DELETE_TRANSACTIONS = "delete_transactions"
    
    # WREN Compliance (NTAA 2025 - Maker-Checker SoD)
    VERIFY_WREN = "verify_wren"  # Can verify WREN status (cannot verify own transactions)
    
    # Invoices
    MANAGE_INVOICES = "manage_invoices"
    VIEW_INVOICES = "view_invoices"
    
    # NRS E-Invoicing (NTAA 2025 - 72-Hour Legal Lock)
    CANCEL_NRS_SUBMISSION = "cancel_nrs_submission"  # Owner only - cancel during 72-hour window
    
    # Tax
    MANAGE_TAX_FILINGS = "manage_tax_filings"
    VIEW_TAX_FILINGS = "view_tax_filings"
    
    # Payroll
    MANAGE_PAYROLL = "manage_payroll"
    VIEW_PAYROLL = "view_payroll"
    
    # Inventory
    MANAGE_INVENTORY = "manage_inventory"
    VIEW_INVENTORY = "view_inventory"
    
    # Reports
    VIEW_REPORTS = "view_reports"
    EXPORT_DATA = "export_data"
    
    # Customers
    MANAGE_CUSTOMERS = "manage_customers"
    VIEW_CUSTOMERS = "view_customers"
    
    # Vendors
    MANAGE_VENDORS = "manage_vendors"
    VIEW_VENDORS = "view_vendors"
    
    # Audit
    VIEW_AUDIT_LOGS = "view_audit_logs"


# ===========================================
# PERMISSION MAPPINGS
# ===========================================

# Platform role to permissions mapping
PLATFORM_ROLE_PERMISSIONS: dict[PlatformRole, Set[PlatformPermission]] = {
    PlatformRole.SUPER_ADMIN: {
        # All permissions
        PlatformPermission.MANAGE_PLATFORM_SETTINGS,
        PlatformPermission.MANAGE_API_KEYS,
        PlatformPermission.HANDLE_ESCALATIONS,
        PlatformPermission.ONBOARD_ADMIN,
        PlatformPermission.ONBOARD_STAFF,
        PlatformPermission.VERIFY_ORGANIZATIONS,
        PlatformPermission.MANAGE_INTERNAL_STAFF,
        PlatformPermission.VIEW_GLOBAL_ANALYTICS,
        PlatformPermission.ACCESS_BACKEND,
        PlatformPermission.MANAGE_CODEBASE,
        PlatformPermission.MONITOR_DATABASE,
        PlatformPermission.MANAGE_WEBHOOKS,
        PlatformPermission.VIEW_USER_DATA,
        PlatformPermission.IMPERSONATE_USER,
        PlatformPermission.TROUBLESHOOT_SUBMISSIONS,
        PlatformPermission.MANAGE_CAMPAIGNS,
        PlatformPermission.MANAGE_REFERRALS,
        PlatformPermission.VIEW_USER_GROWTH,
    },
    PlatformRole.ADMIN: {
        PlatformPermission.ONBOARD_STAFF,
        PlatformPermission.VERIFY_ORGANIZATIONS,
        PlatformPermission.MANAGE_INTERNAL_STAFF,
        PlatformPermission.VIEW_GLOBAL_ANALYTICS,
        PlatformPermission.ACCESS_BACKEND,
        PlatformPermission.VIEW_USER_DATA,
        PlatformPermission.TROUBLESHOOT_SUBMISSIONS,
        PlatformPermission.MANAGE_CAMPAIGNS,
        PlatformPermission.MANAGE_REFERRALS,
        PlatformPermission.VIEW_USER_GROWTH,
    },
    PlatformRole.IT_DEVELOPER: {
        PlatformPermission.ACCESS_BACKEND,
        PlatformPermission.MANAGE_CODEBASE,
        PlatformPermission.MONITOR_DATABASE,
        PlatformPermission.MANAGE_WEBHOOKS,
        PlatformPermission.TROUBLESHOOT_SUBMISSIONS,
    },
    PlatformRole.CUSTOMER_SERVICE: {
        PlatformPermission.VIEW_USER_DATA,
        PlatformPermission.IMPERSONATE_USER,
        PlatformPermission.TROUBLESHOOT_SUBMISSIONS,
    },
    PlatformRole.MARKETING: {
        PlatformPermission.VIEW_GLOBAL_ANALYTICS,
        PlatformPermission.MANAGE_CAMPAIGNS,
        PlatformPermission.MANAGE_REFERRALS,
        PlatformPermission.VIEW_USER_GROWTH,
    },
}

# Organization role to permissions mapping
ORGANIZATION_ROLE_PERMISSIONS: dict[UserRole, Set[OrganizationPermission]] = {
    UserRole.OWNER: {
        # All permissions including NTAA 2025 exclusive permissions
        OrganizationPermission.MANAGE_ORGANIZATION,
        OrganizationPermission.MANAGE_USERS,
        OrganizationPermission.MANAGE_ENTITIES,
        OrganizationPermission.MANAGE_SETTINGS,
        OrganizationPermission.VIEW_ALL_TRANSACTIONS,
        OrganizationPermission.CREATE_TRANSACTIONS,
        OrganizationPermission.EDIT_TRANSACTIONS,
        OrganizationPermission.DELETE_TRANSACTIONS,
        OrganizationPermission.VERIFY_WREN,  # NTAA 2025
        OrganizationPermission.MANAGE_INVOICES,
        OrganizationPermission.VIEW_INVOICES,
        OrganizationPermission.CANCEL_NRS_SUBMISSION,  # NTAA 2025 - Owner only
        OrganizationPermission.MANAGE_TAX_FILINGS,
        OrganizationPermission.VIEW_TAX_FILINGS,
        OrganizationPermission.MANAGE_PAYROLL,
        OrganizationPermission.VIEW_PAYROLL,
        OrganizationPermission.MANAGE_INVENTORY,
        OrganizationPermission.VIEW_INVENTORY,
        OrganizationPermission.VIEW_REPORTS,
        OrganizationPermission.EXPORT_DATA,
        OrganizationPermission.MANAGE_CUSTOMERS,
        OrganizationPermission.VIEW_CUSTOMERS,
        OrganizationPermission.MANAGE_VENDORS,
        OrganizationPermission.VIEW_VENDORS,
        OrganizationPermission.VIEW_AUDIT_LOGS,
    },
    UserRole.ADMIN: {
        OrganizationPermission.MANAGE_USERS,
        OrganizationPermission.MANAGE_ENTITIES,
        OrganizationPermission.MANAGE_SETTINGS,
        OrganizationPermission.VIEW_ALL_TRANSACTIONS,
        OrganizationPermission.CREATE_TRANSACTIONS,
        OrganizationPermission.EDIT_TRANSACTIONS,
        OrganizationPermission.DELETE_TRANSACTIONS,
        OrganizationPermission.VERIFY_WREN,  # NTAA 2025
        OrganizationPermission.MANAGE_INVOICES,
        OrganizationPermission.VIEW_INVOICES,
        OrganizationPermission.MANAGE_TAX_FILINGS,
        OrganizationPermission.VIEW_TAX_FILINGS,
        OrganizationPermission.MANAGE_PAYROLL,
        OrganizationPermission.VIEW_PAYROLL,
        OrganizationPermission.MANAGE_INVENTORY,
        OrganizationPermission.VIEW_INVENTORY,
        OrganizationPermission.VIEW_REPORTS,
        OrganizationPermission.EXPORT_DATA,
        OrganizationPermission.MANAGE_CUSTOMERS,
        OrganizationPermission.VIEW_CUSTOMERS,
        OrganizationPermission.MANAGE_VENDORS,
        OrganizationPermission.VIEW_VENDORS,
        OrganizationPermission.VIEW_AUDIT_LOGS,
    },
    UserRole.ACCOUNTANT: {
        OrganizationPermission.VIEW_ALL_TRANSACTIONS,
        OrganizationPermission.CREATE_TRANSACTIONS,
        OrganizationPermission.EDIT_TRANSACTIONS,
        OrganizationPermission.VERIFY_WREN,  # NTAA 2025 (cannot verify own)
        OrganizationPermission.MANAGE_INVOICES,
        OrganizationPermission.VIEW_INVOICES,
        OrganizationPermission.MANAGE_TAX_FILINGS,
        OrganizationPermission.VIEW_TAX_FILINGS,
        OrganizationPermission.VIEW_PAYROLL,
        OrganizationPermission.VIEW_INVENTORY,
        OrganizationPermission.VIEW_REPORTS,
        OrganizationPermission.EXPORT_DATA,
        OrganizationPermission.MANAGE_CUSTOMERS,
        OrganizationPermission.VIEW_CUSTOMERS,
        OrganizationPermission.MANAGE_VENDORS,
        OrganizationPermission.VIEW_VENDORS,
    },
    # NTAA 2025: External Accountant (like QuickBooks "Invite Accountant")
    # Can file tax returns and view reports but NO payroll/inventory editing/fund movement
    UserRole.EXTERNAL_ACCOUNTANT: {
        OrganizationPermission.VIEW_ALL_TRANSACTIONS,
        OrganizationPermission.VERIFY_WREN,  # Can verify WREN (cannot verify own)
        OrganizationPermission.VIEW_INVOICES,
        OrganizationPermission.MANAGE_TAX_FILINGS,  # File returns for client
        OrganizationPermission.VIEW_TAX_FILINGS,
        OrganizationPermission.VIEW_PAYROLL,  # Per RBAC matrix
        OrganizationPermission.VIEW_INVENTORY,  # Per RBAC matrix
        OrganizationPermission.VIEW_REPORTS,
        OrganizationPermission.EXPORT_DATA,
        OrganizationPermission.VIEW_CUSTOMERS,
        OrganizationPermission.VIEW_VENDORS,
        # NO payroll management, NO inventory management, NO invoice editing, NO fund movement
    },
    UserRole.AUDITOR: {
        OrganizationPermission.VIEW_ALL_TRANSACTIONS,
        OrganizationPermission.VIEW_INVOICES,
        OrganizationPermission.VIEW_TAX_FILINGS,
        OrganizationPermission.VIEW_PAYROLL,
        # NO VIEW_INVENTORY per RBAC matrix
        OrganizationPermission.VIEW_REPORTS,
        # NO EXPORT_DATA per RBAC matrix
        OrganizationPermission.VIEW_CUSTOMERS,
        OrganizationPermission.VIEW_VENDORS,
        OrganizationPermission.VIEW_AUDIT_LOGS,
    },
    UserRole.PAYROLL_MANAGER: {
        OrganizationPermission.MANAGE_PAYROLL,
        OrganizationPermission.VIEW_PAYROLL,
        OrganizationPermission.MANAGE_VENDORS,  # Per RBAC matrix
        OrganizationPermission.VIEW_VENDORS,    # Per RBAC matrix
    },
    UserRole.INVENTORY_MANAGER: {
        OrganizationPermission.MANAGE_INVENTORY,
        OrganizationPermission.VIEW_INVENTORY,
        OrganizationPermission.MANAGE_VENDORS,
        OrganizationPermission.VIEW_VENDORS,
    },
    UserRole.VIEWER: {
        OrganizationPermission.VIEW_INVOICES,
        OrganizationPermission.VIEW_INVENTORY,
        OrganizationPermission.VIEW_REPORTS,
        OrganizationPermission.VIEW_CUSTOMERS,
        OrganizationPermission.VIEW_VENDORS,
    },
}


# ===========================================
# PERMISSION HELPER FUNCTIONS
# ===========================================

def get_platform_permissions(role: PlatformRole) -> Set[PlatformPermission]:
    """Get all permissions for a platform role."""
    return PLATFORM_ROLE_PERMISSIONS.get(role, set())


def get_organization_permissions(role: UserRole) -> Set[OrganizationPermission]:
    """Get all permissions for an organization role."""
    return ORGANIZATION_ROLE_PERMISSIONS.get(role, set())


def has_platform_permission(role: PlatformRole, permission: PlatformPermission) -> bool:
    """Check if a platform role has a specific permission."""
    return permission in get_platform_permissions(role)


def has_organization_permission(role: UserRole, permission: OrganizationPermission) -> bool:
    """Check if an organization role has a specific permission."""
    return permission in get_organization_permissions(role)


def get_all_permissions_for_platform_roles(roles: List[PlatformRole]) -> Set[PlatformPermission]:
    """Get all permissions for multiple platform roles."""
    permissions = set()
    for role in roles:
        permissions.update(get_platform_permissions(role))
    return permissions


def get_all_permissions_for_organization_roles(roles: List[UserRole]) -> Set[OrganizationPermission]:
    """Get all permissions for multiple organization roles."""
    permissions = set()
    for role in roles:
        permissions.update(get_organization_permissions(role))
    return permissions


# ===========================================
# ROLE HIERARCHY
# ===========================================

PLATFORM_ROLE_HIERARCHY = {
    PlatformRole.SUPER_ADMIN: 5,
    PlatformRole.ADMIN: 4,
    PlatformRole.IT_DEVELOPER: 3,
    PlatformRole.CUSTOMER_SERVICE: 2,
    PlatformRole.MARKETING: 2,
}

ORGANIZATION_ROLE_HIERARCHY = {
    UserRole.OWNER: 7,
    UserRole.ADMIN: 6,
    UserRole.ACCOUNTANT: 5,
    UserRole.EXTERNAL_ACCOUNTANT: 4,  # Same level as Auditor
    UserRole.AUDITOR: 4,
    UserRole.PAYROLL_MANAGER: 3,
    UserRole.INVENTORY_MANAGER: 3,
    UserRole.VIEWER: 1,
}


def get_platform_role_level(role: PlatformRole) -> int:
    """Get the hierarchy level of a platform role."""
    return PLATFORM_ROLE_HIERARCHY.get(role, 0)


def get_organization_role_level(role: UserRole) -> int:
    """Get the hierarchy level of an organization role."""
    return ORGANIZATION_ROLE_HIERARCHY.get(role, 0)


def is_platform_role_higher_or_equal(role1: PlatformRole, role2: PlatformRole) -> bool:
    """Check if role1 is higher or equal to role2 in hierarchy."""
    return get_platform_role_level(role1) >= get_platform_role_level(role2)


def is_organization_role_higher_or_equal(role1: UserRole, role2: UserRole) -> bool:
    """Check if role1 is higher or equal to role2 in hierarchy."""
    return get_organization_role_level(role1) >= get_organization_role_level(role2)
