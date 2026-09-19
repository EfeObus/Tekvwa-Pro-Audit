# Tekvwa Pro Audit - Role-Based Access Control (RBAC) Documentation

**Document Version:** 2.2  
**Last Updated:** January 27, 2026  
**Status:** Production

## Overview

Tekvwa Pro Audit implements a comprehensive two-tier RBAC system:

1. **Platform Staff (Internal Tekvwa Employees)** - Manage the multi-tenant platform
2. **Organization Users (External Customers)** - Use the platform for their businesses

---

## 1. Platform Staff Roles

Platform staff are internal Tekvwa employees who manage the platform. They are identified by `is_platform_staff = True` and do not belong to any organization (`organization_id = NULL`).

### Role Hierarchy

| Role | Level | Description |
|------|-------|-------------|
| **Super Admin** | 5 | Full root access to entire platform |
| **Admin** | 4 | High-level operational access |
| **IT/Developer** | 3 | Backend and infrastructure access |
| **Customer Service** | 2 | View-only or impersonation access |
| **Marketing** | 2 | Analytics and communication dashboards |

### Super Admin

>  **Credentials:** Super Admin credentials are stored securely in environment variables.  
> See `.env.example` for the required configuration:
> ```env
> SUPER_ADMIN_EMAIL=<configured-in-env>
> SUPER_ADMIN_PASSWORD=<configured-in-env>
> SUPER_ADMIN_FIRST_NAME=<configured-in-env>
> SUPER_ADMIN_LAST_NAME=<configured-in-env>
> ```

**Responsibilities:**
- Platform-wide settings management
- Managing API keys for government gateways (NRS, JTB)
- Handling manual escalations
- Onboarding Admin and all other staff (highest access)
- **Emergency controls and kill switches** ✅ NEW
- **Cross-tenant user management** ✅ NEW
- **Organization verification approvals** ✅ NEW
- **Platform health monitoring** ✅ NEW
- **Global audit log viewing** ✅ NEW

**Permissions:**
- All platform permissions

**Implemented API Endpoints (31 total):**

| Category | Endpoints | Status |
|----------|-----------|--------|
| Emergency Controls | 6 | ✅ Implemented |
| User Search | 4 | ✅ Implemented |
| Staff Management | 4 | ✅ Implemented |
| Verification | 4 | ✅ Implemented |
| Audit Logs | 4 | ✅ Implemented |
| Health Metrics | 6 | ✅ Implemented |
| Tenant Management | 3 | ✅ Implemented |

### Admin

**Responsibilities:**
- Approving organization verification documents (CAC, TIN)
- Managing internal staff accounts (IT, CSR, Marketing)
- Viewing global analytics (without accessing private financial data)

**Permissions:**
- `onboard_staff` - Can onboard IT, CSR, Marketing
- `verify_organizations` - Approve/reject org documents
- `manage_internal_staff` - View and manage staff
- `view_global_analytics` - Platform-wide analytics
- `access_backend` - Backend access
- `view_user_data` - View user information
- `troubleshoot_submissions` - Debug NRS submissions
- `manage_campaigns` - Marketing campaigns
- `manage_referrals` - Referral engine
- `view_user_growth` - User growth stats

### IT/Developer

**Responsibilities:**
- Maintaining the Python/FastAPI codebase
- Monitoring PostgreSQL health
- Ensuring 24/7 uptime for NRS e-invoicing webhooks

**Permissions:**
- `access_backend`
- `manage_codebase`
- `monitor_database`
- `manage_webhooks`
- `troubleshoot_submissions`

### Customer Service (CSR)

**Responsibilities:**
- Troubleshooting "failed NRS submissions"
- Assisting with onboarding
- Explaining tax deadline alerts to non-technical users

**Permissions:**
- `view_user_data`
- `impersonate_user` (requires user permission)
- `troubleshoot_submissions`

### Marketing

**Responsibilities:**
- Running targeted in-app campaigns (e.g., "VAT deadline is in 2 days")
- Managing the referral engine
- Analyzing user growth trends

**Permissions:**
- `view_global_analytics`
- `manage_campaigns`
- `manage_referrals`
- `view_user_growth`

---

## 2. Organization Types

Organizations are categorized for compliance and feature differentiation:

| Type | Description | Tax Implications |
|------|-------------|------------------|
| **SME** | Small and Medium Enterprises | Standard tax obligations |
| **Small Business** | Micro businesses | May qualify for simplified compliance |
| **School** | Educational institutions | Education-specific exemptions |
| **Non-Profit** | NGOs and charitable organizations | Tax-exempt status possible |
| **Individual** | Solo practitioners/freelancers | Personal income tax focus |
| **Corporation** | Large corporations | Full CIT obligations |

---

## 3. Organization User Roles

Users within an organization have the following roles:

### Role Hierarchy

| Role | Level | Description |
|------|-------|-------------|
| **Owner** | 7 | Full access to organization |
| **Admin** | 6 | Administrative access |
| **Accountant** | 5 | Financial data access (internal) |
| **External Accountant** | 4 | External firm access (tax filing + reports only) |
| **Auditor** | 4 | Read-only access |
| **Payroll Manager** | 3 | Payroll access |
| **Inventory Manager** | 3 | Inventory access |
| **Viewer** | 1 | Limited read-only |

### External Accountant Role (NTAA 2025)

The **External Accountant** role is designed for outsourced accounting firms (similar to QuickBooks "Invite Accountant" feature). This is common in Nigeria where most SMEs hire external firms for tax compliance.

**Capabilities:**
- File tax returns on behalf of the organization
- View reports and export data
- Verify WREN status (Maker-Checker)
- View transactions, invoices, customers, vendors

**Restrictions:**
- Cannot manage payroll
- Cannot manage inventory
- Cannot edit or create invoices
- Cannot move funds or access banking

### Permission Matrix (NTAA 2025 Updated)

| Permission | Owner | Admin | Accountant | Ext Acct | Auditor | Payroll | Inventory | Viewer |
|------------|-------|-------|------------|----------|---------|---------|-----------|--------|
| Manage Organization | ✓ | | | | | | | |
| Manage Users | ✓ | ✓ | | | | | | |
| Manage Entities | ✓ | ✓ | | | | | | |
| Manage Settings | ✓ | ✓ | | | | | | |
| View Transactions | ✓ | ✓ | ✓ | ✓ | ✓ | | | |
| Create Transactions | ✓ | ✓ | ✓ | | | | | |
| Edit Transactions | ✓ | ✓ | ✓ | | | | | |
| Delete Transactions | ✓ | ✓ | | | | | | |
| **Verify WREN (SoD)** | ✓ | ✓ | ✓ | ✓ | | | | |
| Manage Invoices | ✓ | ✓ | ✓ | | | | | |
| **Cancel NRS Submission** | ✓ | | | | | | | |
| View Invoices | ✓ | ✓ | ✓ | ✓ | ✓ | | | ✓ |
| Manage Tax Filings | ✓ | ✓ | ✓ | | | | |
| View Tax Filings | ✓ | ✓ | ✓ | ✓ | | | |
| Manage Payroll | ✓ | ✓ | | | ✓ | | |
| View Payroll | ✓ | ✓ | ✓ | ✓ | ✓ | | |
| Manage Inventory | ✓ | ✓ | | | | ✓ | |
| View Inventory | ✓ | ✓ | ✓ | ✓ | | ✓ | ✓ |
| View Reports | ✓ | ✓ | ✓ | ✓ | | | ✓ |
| Export Data | ✓ | ✓ | ✓ | ✓ | | | |
| Manage Customers | ✓ | ✓ | ✓ | | | | |
| View Customers | ✓ | ✓ | ✓ | ✓ | | | ✓ |
| Manage Vendors | ✓ | ✓ | ✓ | | | ✓ | |
| View Vendors | ✓ | ✓ | ✓ | ✓ | | ✓ | ✓ |

---

## 4. API Endpoints

### Authentication & Registration (`/api/v1/auth`)

| Endpoint | Method | Description | Required Permission |
|----------|--------|-------------|---------------------|
| `/auth/register` | POST | Register new organization | Public |
| `/auth/login` | POST | User login | Public |
| `/auth/logout` | POST | User logout | Any authenticated user |
| `/auth/verify-email` | POST | Verify email with token | Public |
| `/auth/resend-verification` | POST | Resend verification email | Public |
| `/auth/forgot-password` | POST | Request password reset | Public |
| `/auth/reset-password` | POST | Reset password with token | Public |
| `/auth/nigeria/states` | GET | Get all Nigerian states (37) | Public |
| `/auth/nigeria/states/{state}/lgas` | GET | Get LGAs for a state | Public |

### Staff Management (`/api/v1/staff`)

| Endpoint | Method | Description | Required Permission |
|----------|--------|-------------|---------------------|
| `/staff/onboard` | POST | Onboard new staff | `onboard_staff` |
| `/staff` | GET | List all staff | `manage_internal_staff` |
| `/staff/{id}` | GET | Get staff details | `manage_internal_staff` |
| `/staff/{id}/role` | PUT | Update staff role | Super Admin only |
| `/staff/{id}/deactivate` | POST | Deactivate staff | `manage_internal_staff` |
| `/staff/{id}/reactivate` | POST | Reactivate staff | `manage_internal_staff` |
| `/staff/verifications/pending` | GET | List pending verifications | `verify_organizations` |
| `/staff/verifications/{id}/verify` | POST | Approve organization | `verify_organizations` |
| `/staff/verifications/{id}/reject` | POST | Reject organization | `verify_organizations` |
| `/staff/analytics/user-growth` | GET | User growth stats | `view_user_growth` |

### Organization User Management (`/api/v1/organizations`)

| Endpoint | Method | Description | Required Permission |
|----------|--------|-------------|---------------------|
| `/{org_id}/users` | GET | List org users | `manage_users` |
| `/{org_id}/users/invite` | POST | Invite new user | `manage_users` |
| `/{org_id}/users/{id}/role` | PUT | Update user role | `manage_users` |
| `/{org_id}/users/{id}/deactivate` | POST | Deactivate user | `manage_users` |
| `/{org_id}/users/{id}/reactivate` | POST | Reactivate user | `manage_users` |
| `/{org_id}/users/{id}/entity-access` | PUT | Update entity access | `manage_users` |
| `/me/impersonation` | POST | Toggle CSR impersonation | Any authenticated user |

---

## 5. Organization Verification Flow

```
1. Organization Created → Status: PENDING
       ↓
2. User Uploads CAC/TIN Documents → Status: SUBMITTED
       ↓
3. Admin Reviews Documents → Status: UNDER_REVIEW
       ↓
4a. Approved → Status: VERIFIED (Full platform access)
4b. Rejected → Status: REJECTED (Needs resubmission)
```

---

## 6. Onboarding Hierarchy

### Platform Staff Onboarding

```
Super Admin
    ├── Can onboard: Admin, IT/Developer, CSR, Marketing
    │
Admin
    ├── Can onboard: IT/Developer, CSR, Marketing
    │
IT/Developer, CSR, Marketing
    └── Cannot onboard anyone
```

### Organization User Onboarding

```
Owner
    ├── Can invite: All roles (Admin, Accountant, Auditor, etc.)
    │
Admin
    ├── Can invite: Accountant, Auditor, Payroll Manager, Inventory Manager, Viewer
    │
Other roles
    └── Cannot invite anyone
```

---

## 7. Security Features

### Staff First Login Password Reset

When platform staff are onboarded by Super Admin or Admin:
- The `must_reset_password` flag is set to `True`
- On first login, staff are automatically redirected to the Settings page
- A security banner prompts them to change their password
- Staff cannot access other features until password is changed
- After successful password change, `must_reset_password` is cleared

This ensures that:
1. Temporary onboarding passwords are never used beyond first login
2. Each staff member sets their own secure password
3. Onboarding admins never know the final password

### CSR Impersonation

- Users can grant/revoke impersonation permission
- CSR can only impersonate users who have explicitly allowed it
- Platform staff cannot be impersonated
- All impersonation actions are logged in audit trail

### Email Verification

- New organization users must verify their email before full access
- Verification tokens expire after 24 hours
- Users can request new verification emails via `/api/v1/auth/resend-verification`
- Platform staff are pre-verified during onboarding

### Rate Limiting (Recommended)

Consider adding rate limiting for:
- Login attempts
- Staff onboarding
- User invitations
- Password reset requests

---

## 8. Database Schema Changes

The RBAC implementation adds:

**Users Table:**
- `is_platform_staff` (Boolean) - Platform staff flag
- `platform_role` (Enum) - Platform role
- `onboarded_by_id` (UUID) - Who onboarded this user
- `staff_notes` (Text) - Internal notes
- `can_be_impersonated` (Boolean) - CSR impersonation permission

**Organizations Table:**
- `organization_type` (Enum) - Organization type
- `verification_status` (Enum) - Verification status
- `cac_document_path` (String) - CAC document
- `tin_document_path` (String) - TIN document
- `additional_documents` (Text/JSON) - Other docs
- `verification_notes` (Text) - Admin notes
- `verified_by_id` (String) - Admin who verified
- `referral_code` (String) - Referral code
- `referred_by_code` (String) - Referring org code

---

## 9. Environment Variables

```env
# Super Admin Configuration (DO NOT commit actual values)
SUPER_ADMIN_EMAIL=<configured-in-env>
SUPER_ADMIN_PASSWORD=<configured-in-env>
SUPER_ADMIN_FIRST_NAME=<configured-in-env>
SUPER_ADMIN_LAST_NAME=<configured-in-env>
```

>  **Security Note:** Super Admin credentials are stored securely in `.env` (not committed to version control) and seeded to the database on first startup. Never expose actual credentials in documentation or code.

---

## 10. Quick Start

### Login as Super Admin

```bash
curl -X POST http://localhost:5120/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "$SUPER_ADMIN_EMAIL",
    "password": "$SUPER_ADMIN_PASSWORD"
  }'
```

>  Replace `$SUPER_ADMIN_EMAIL` and `$SUPER_ADMIN_PASSWORD` with the values from your `.env` file.

### Onboard an Admin

```bash
curl -X POST http://localhost:5120/api/v1/staff/onboard \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <super_admin_token>" \
  -d '{
    "email": "newadmin@example.com",
    "password": "<secure-password>",
    "first_name": "John",
    "last_name": "Admin",
    "platform_role": "admin"
  }'
```

>  Use a strong password meeting the platform's password policy. The new staff member will be required to change this password on first login.

### Check Current User Permissions

```bash
curl -X GET http://localhost:5120/api/v1/auth/me \
  -H "Authorization: Bearer <token>"
```

---

## 12. Dashboard System

Tekvwa Pro Audit provides role-specific dashboards for different user types.

### Dashboard Routing

When a user navigates to `/dashboard`, the system automatically routes them to the appropriate dashboard:

| User Type | Dashboard | Template |
|-----------|-----------|----------|
| Platform Staff | Staff Dashboard | `staff_dashboard.html` |
| Organization User | Business Dashboard | `dashboard.html` |

### Platform Staff Dashboards

Each platform role sees a customized dashboard:

#### Super Admin Dashboard
- Total organizations, users, and staff counts
- Pending verification count
- Organizations by type breakdown
- Verification status distribution
- Recent platform activity (audit logs)
- Platform health metrics
- Quick actions: Onboard Staff, Pending Verifications, Platform Settings, API Keys

#### Admin Dashboard
- Organization and user counts
- Pending verifications
- Verification statistics
- Organizations needing attention (submitted, rejected)
- Quick actions: Onboard Staff, Review Verifications, User Analytics

#### IT/Developer Dashboard
- Platform health status
- Database status
- API uptime
- NRS webhook status
- Recent errors
- Quick actions: System Logs, Database Health, Webhook Status

#### Customer Service Dashboard
- Users assisted today
- Pending issues count
- Failed NRS submissions
- Recent submission status
- Quick actions: Search User, Failed Submissions, Help Articles

#### Marketing Dashboard
- User growth statistics (total, new in 30 days, growth rate)
- Organizations by type
- Campaign metrics
- Quick actions: Create Campaign, User Analytics, Referral Stats

### Organization User Dashboards

Organization users see a business-focused dashboard with:

- **Financial Metrics**: This month and YTD income, expense, net
- **Invoice Summary**: Outstanding amounts, overdue count
- **Recent Transactions**: Latest 5 transactions
- **Quick Actions**: Based on user role
- **Team Summary**: (Owner/Admin only) Member count by role
- **Tax Summary**: (Owner/Admin/Accountant) VAT collected/paid
- **Inventory Summary**: (Owner/Admin/Inventory Manager) Stock counts

### Dashboard API Endpoints

| Endpoint | Method | Description | Required |
|----------|--------|-------------|----------|
| `/api/v1/staff/dashboard` | GET | Platform staff dashboard data | Platform staff |
| `/api/v1/entities/{id}/reports/dashboard` | GET | Organization dashboard data | Organization user |

### Super Admin Dashboard API Endpoints (NEW)

The following API endpoints are available exclusively to Super Admin and authorized platform staff:

#### Emergency Controls (`/admin/emergency/`)

| Endpoint | Method | Description | Required Role |
|----------|--------|-------------|---------------|
| `/admin/emergency/platform/read-only` | POST | Toggle platform read-only mode | Super Admin |
| `/admin/emergency/platform/status` | GET | Get platform emergency status | Super Admin, IT Dev |
| `/admin/emergency/tenant/{tenant_id}/suspend` | POST | Emergency suspend a tenant | Super Admin |
| `/admin/emergency/tenant/{tenant_id}/suspend` | DELETE | Lift tenant suspension | Super Admin |
| `/admin/emergency/feature/{feature_name}/disable` | POST | Disable feature globally | Super Admin |
| `/admin/emergency/feature/{feature_name}/disable` | DELETE | Re-enable feature | Super Admin |

#### Cross-Tenant User Search (`/admin/users/`)

| Endpoint | Method | Description | Required Role |
|----------|--------|-------------|---------------|
| `/admin/users/search` | GET | Search users across all tenants | Super Admin, CSR |
| `/admin/users/{user_id}` | GET | Get user details | Super Admin, CSR |
| `/admin/users/{user_id}/activity` | GET | Get user activity history | Super Admin |
| `/admin/users/{user_id}/suspend` | POST | Suspend/unsuspend user | Super Admin |

#### Platform Staff Management (`/admin/staff/`)

| Endpoint | Method | Description | Required Role |
|----------|--------|-------------|---------------|
| `/admin/staff` | GET | List all platform staff | Super Admin |
| `/admin/staff` | POST | Create new platform staff | Super Admin |
| `/admin/staff/{staff_id}` | GET | Get staff details | Super Admin |
| `/admin/staff/{staff_id}` | PUT | Update staff | Super Admin |

#### Organization Verification (`/admin/verifications/`)

| Endpoint | Method | Description | Required Role |
|----------|--------|-------------|---------------|
| `/admin/verifications` | GET | List pending verifications | Super Admin, Admin |
| `/admin/verifications/{org_id}` | GET | Get verification details | Super Admin, Admin |
| `/admin/verifications/{org_id}/approve` | POST | Approve organization | Super Admin, Admin |
| `/admin/verifications/{org_id}/reject` | POST | Reject organization | Super Admin, Admin |

#### Global Audit Log Viewer (`/admin/audit-logs/`)

| Endpoint | Method | Description | Required Role |
|----------|--------|-------------|---------------|
| `/admin/audit-logs` | GET | List all audit logs (paginated) | Super Admin, IT Dev |
| `/admin/audit-logs/stats` | GET | Get audit statistics | Super Admin |
| `/admin/audit-logs/{log_id}` | GET | Get specific log details | Super Admin, IT Dev |
| `/admin/audit-logs/export` | GET | Export audit logs | Super Admin |

#### Platform Health Metrics (`/admin/health/`)

| Endpoint | Method | Description | Required Role |
|----------|--------|-------------|---------------|
| `/admin/health` | GET | Overall platform health | Super Admin, IT Dev |
| `/admin/health/database` | GET | Database health metrics | Super Admin, IT Dev |
| `/admin/health/services` | GET | External service status | Super Admin, IT Dev |
| `/admin/health/metrics` | GET | Detailed system metrics | Super Admin, IT Dev |
| `/admin/health/tenants/summary` | GET | Tenant health summary | Super Admin |
| `/admin/health/alerts` | GET | Active platform alerts | Super Admin, IT Dev |

#### Tenant Management (`/admin/tenants/`)

| Endpoint | Method | Description | Required Role |
|----------|--------|-------------|---------------|
| `/admin/tenants` | GET | List all tenants | Super Admin, CSR |
| `/admin/tenants/{tenant_id}` | GET | Get tenant details | Super Admin, CSR |
| `/admin/tenants/{tenant_id}` | PUT | Update tenant | Super Admin |

### Authentication for Dashboards

The dashboard system uses HTTP-only cookies for server-side authentication:

1. **Login**: Token stored in cookie `access_token`
2. **Entity Selection**: Entity ID stored in cookie `entity_id`
3. **Logout**: Both cookies are cleared

---

## 13. NTAA 2025 Compliance Features

Tekvwa Pro Audit implements critical Nigeria Tax Administration Act (NTAA) 2025 compliance features.

### 72-Hour Legal Lock (Invoice State Lock)

Under the NTAA 2025, the government has introduced "Continuous Transaction Controls" (CTC). Buyers have 72 hours to accept or reject an e-invoice on the NRS portal.

**Implementation:**
- Once an invoice is submitted to NRS, it is **locked** (`is_nrs_locked = true`)
- Locked invoices cannot be edited or deleted
- Only the **Owner** can cancel an NRS submission during the 72-hour window
- After the window expires, modifications require a formal **Credit Note**

**New Fields:**
| Field | Description |
|-------|-------------|
| `is_nrs_locked` | Boolean flag - true when submitted to NRS |
| `nrs_lock_expires_at` | 72-hour window expiry timestamp |
| `nrs_cryptographic_stamp` | NRS cryptographic signature for audit |
| `nrs_cancelled_by_id` | Owner who cancelled (if any) |
| `nrs_cancellation_reason` | Reason for cancellation |

**Permission Required:**
- `CANCEL_NRS_SUBMISSION` - Owner only

>  **Legal Warning**: Modifying a "Submitted" invoice without a formal NRS-tracked Credit Note is a criminal offense under the NTAA 2025.

### Maker-Checker Segregation of Duties (SoD)

The 2026 law strictly penalizes mixing personal and business funds. For WREN (Wholly, Reasonably, Exclusively, Necessarily) expense verification:

**Rules:**
- **Maker** (Staff): Creates/uploads an expense
- **Checker** (Accountant): Verifies WREN status
- The Checker **cannot** verify an expense they created (SoD enforcement)

**New Fields in Transactions:**
| Field | Description |
|-------|-------------|
| `created_by_id` | Maker - who created the transaction |
| `wren_verified_by_id` | Checker - who verified WREN status |
| `wren_verified_at` | When verification was performed |
| `original_category_id` | Original category for audit trail |
| `category_change_history` | Before/after snapshots of category changes |

**Permission Required:**
- `VERIFY_WREN` - Available to Owner, Admin, Accountant, External Accountant

### Time-Limited CSR Impersonation (NDPA Compliance)

Per the Nigeria Data Protection Act (NDPA), impersonation access must be time-limited:

**Rules:**
- Maximum **24-hour** window for CSR impersonation
- Users explicitly **grant** access (not a permanent toggle)
- Automatic expiration after the granted period
- All impersonation actions are logged in audit trail

**New Fields in Users:**
| Field | Description |
|-------|-------------|
| `impersonation_granted_at` | When access was granted |
| `impersonation_expires_at` | When access expires (max 24 hours) |

### Enhanced Audit Trail (NTAA 2025 Compliant)

The audit log now captures mandatory fields for tax return submission verification:

**Required Fields:**
| Field | Purpose |
|-------|---------|
| `ip_address` | Prove source of tax return submission |
| `device_fingerprint` | Browser/device identification |
| `user_agent` | Browser information |
| `session_id` | Track related actions |
| `geo_location` | Approximate location (fraud detection) |
| `impersonated_by_id` | If CSR is acting on behalf of user |

**Before/After Snapshots:**
- Category changes (e.g., Personal → Business) store original values
- Required for protecting Owner during government audits

**NRS Response Storage:**
- `nrs_irn` - Invoice Reference Number
- `nrs_response` - Full server response including cryptographic stamp

---

## 14. Migration

Run the migration to add RBAC and NTAA 2025 fields:

```bash
alembic upgrade head
```

This will create:
- New enum types (PlatformRole, OrganizationType, VerificationStatus, UserRole with EXTERNAL_ACCOUNTANT)
- Add new columns to users, organizations, invoices, transactions, and audit_logs tables
- Create necessary indexes
