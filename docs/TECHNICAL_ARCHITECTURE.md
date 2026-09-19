# Tekvwa Pro Audit - Technical Architecture Document

**Document Version:** 2.2  
**Date:** January 27, 2026  
**Status:** Production Architecture  
**Classification:** Internal Technical Document  

---

## Current System Statistics

| Metric | Value |
|--------|-------|
| **Total Routes** | 558 |
| **API Endpoints** | 502 |
| **Admin API Endpoints** | 31 |
| **View Routes** | 52 |
| **Database Models** | 84 exports |
| **Test Coverage** | 313 tests passing |
| **Security Middleware** | 6 layers |
| **Templates** | 26 HTML files |

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture Principles](#2-architecture-principles)
3. [High-Level Architecture](#3-high-level-architecture)
4. [Technology Stack](#4-technology-stack)
5. [Component Architecture](#5-component-architecture)
6. [Data Architecture](#6-data-architecture)
7. [API Design](#7-api-design)
8. [Security Architecture](#8-security-architecture)
9. [Integration Architecture](#9-integration-architecture)
10. [Infrastructure & Deployment](#10-infrastructure--deployment)
11. [Performance Requirements](#11-performance-requirements)
12. [MVP Scope Definition](#12-mvp-scope-definition)

---

## 1. System Overview

### 1.1 Purpose

Tekvwa Pro Audit is a cloud-native, multi-tenant SaaS platform designed to provide Nigerian businesses with integrated financial management and tax compliance capabilities, with native support for the 2026 NRS e-invoicing mandate.

### 1.2 Key System Characteristics

| Characteristic | Requirement |
|----------------|-------------|
| **Availability** | 99.5% uptime (MVP), 99.9% (Production) |
| **Scalability** | Support 100K+ concurrent users |
| **Data Residency** | Nigeria or ECOWAS region |
| **Offline Support** | Core transaction recording |
| **Multi-tenancy** | Logical separation per business entity |

---

## 2. Architecture Principles

### 2.1 Guiding Principles

1. **Nigeria-First Design**
   - Optimize for intermittent connectivity
   - Support low-bandwidth scenarios
   - Host data within regulatory boundaries

2. **Security by Default**
   - Encrypt all data at rest and in transit
   - Implement least-privilege access
   - Audit all financial transactions

3. **Modular Monolith First**
   - Start with well-structured monolith
   - Design for future service extraction
   - Avoid premature microservices complexity

4. **API-First**
   - All functionality exposed via REST APIs
   - Enable third-party integrations
   - Support mobile and web clients equally

5. **Compliance-Ready**
   - Immutable audit logs
   - NRS-compliant data formats
   - NITDA data protection compliance

---

## 3. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                                    │
├──────────────────────┬──────────────────────┬──────────────────────────────┤
│   Web Application    │   Desktop App        │   Third-Party Integrations   │
│   (Jinja2 + HTMX)    │   (Future: Win/Mac)  │   (REST API)                 │
└──────────┬───────────┴──────────┬───────────┴──────────────┬───────────────┘
           │                      │                          │
           ▼                      ▼                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           API GATEWAY (Kong/AWS API Gateway)                 │
│                    Rate Limiting • Auth • Load Balancing                     │
└─────────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         APPLICATION LAYER                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   Auth      │  │  Financial  │  │    Tax      │  │  Reporting  │        │
│  │   Module    │  │   Module    │  │   Module    │  │   Module    │        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  Inventory  │  │   Payroll   │  │   Banking   │  │ E-Invoicing │        │
│  │   Module    │  │   Module    │  │   Module    │  │   Module    │        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
│                                                                              │
│                    Core Services (FastAPI / Python 3.11+)                    │
└─────────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          DATA LAYER                                          │
├──────────────────────┬──────────────────────┬───────────────────────────────┤
│   PostgreSQL         │   Redis              │   S3/Blob Storage             │
│   (Primary DB)       │   (Cache/Queue)      │   (Documents/OCR)             │
└──────────────────────┴──────────────────────┴───────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     EXTERNAL INTEGRATIONS                                    │
├──────────────────────┬──────────────────────┬───────────────────────────────┤
│   NRS E-Invoice API  │   Bank APIs          │   OCR Service                 │
│   TIN Verification   │   Payment Gateways   │   Email/SMS/WhatsApp          │
└──────────────────────┴──────────────────────┴───────────────────────────────┘
```

---

## 4. Technology Stack

### 4.1 Recommended Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| **Backend API** | FastAPI 0.110+ | High performance, async support, automatic OpenAPI docs, Python 3.11+ |
| **Web Frontend** | Jinja2 Templates + HTMX | Server-side rendering, reduces complexity, fast interactions |
| **Database** | PostgreSQL 15+ | ACID compliance, JSON support, proven reliability |
| **ORM** | SQLAlchemy 2.0 + Alembic | Async support, migrations, Python-native |
| **Cache** | Redis 7 | Session management, rate limiting, background tasks |
| **Task Queue** | Celery + Redis | Background jobs, e-invoice retry logic |
| **Object Storage** | AWS S3 / Azure Blob | Document storage, OCR images |
| **OCR Engine** | Azure Form Recognizer | Superior receipt recognition, Naira support |
| **PDF Generation** | WeasyPrint / ReportLab | Python-native PDF generation |
| **Authentication** | FastAPI-Users + OAuth2 | JWT tokens, OAuth support, secure auth |
| **Validation** | Pydantic v2 | Fast data validation, serialization |
| **Hosting** | AWS (eu-west-1 or af-south-1) | Closest regions to Nigeria |

### 4.2 Alternative Considerations

| Decision | Option A (Recommended) | Option B | Reasoning |
|----------|------------------------|----------|-----------|
| Backend | FastAPI | Django | FastAPI offers superior async performance, automatic OpenAPI docs |
| Database | PostgreSQL | MySQL | Financial data needs ACID, relational integrity, JSON support |
| Frontend | Jinja2 + HTMX | React SPA | Simpler architecture, faster development, no API duplication |
| Auth | FastAPI-Users | Auth0 | Faster MVP, lower cost, no vendor lock-in |

---

## 5. Component Architecture

### 5.1 FastAPI Project Structure

```
tekvwa_pro_audit/
├── main.py                 # FastAPI application entry point
├── requirements.txt
├── pyproject.toml
├── alembic.ini             # Database migrations config
├── alembic/
│   └── versions/           # Migration files
│
├── app/
│   ├── __init__.py
│   ├── config.py           # Settings and environment config
│   ├── database.py         # SQLAlchemy async engine setup
│   ├── dependencies.py     # Shared dependencies
│   │
│   ├── models/             # SQLAlchemy models
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── entity.py
│   │   ├── transaction.py
│   │   ├── invoice.py
│   │   ├── vendor.py
│   │   └── category.py
│   │
│   ├── schemas/            # Pydantic schemas
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── entity.py
│   │   ├── transaction.py
│   │   ├── invoice.py
│   │   └── tax.py
│   │
│   ├── routers/            # API route handlers
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── entities.py
│   │   ├── transactions.py
│   │   ├── invoices.py
│   │   ├── vendors.py
│   │   ├── inventory.py
│   │   ├── reports.py
│   │   ├── tax.py
│   │   └── ocr.py
│   │
│   ├── services/           # Business logic
│   │   ├── __init__.py
│   │   ├── nrs_client.py        # NRS e-invoicing API client
│   │   ├── pdf_generator.py     # PDF report generation
│   │   ├── ocr_service.py       # Azure Form Recognizer
│   │   ├── tin_verifier.py      # TIN verification service
│   │   └── tax_calculators/
│   │       ├── vat.py
│   │       ├── paye.py
│   │       ├── cit.py
│   │       └── wht.py
│   │
│   ├── tasks/              # Celery background tasks
│   │   ├── __init__.py
│   │   ├── celery_app.py
│   │   ├── invoice_tasks.py
│   │   ├── ocr_tasks.py
│   │   └── notification_tasks.py
│   │
│   └── utils/              # Utility functions
│       ├── __init__.py
│       ├── nigeria_data.py      # Nigeria states & LGAs (37 states, 774 LGAs)
│       ├── security.py
│       └── validators.py
│
├── templates/              # Jinja2 templates (for web UI)
│   ├── base.html
│   ├── dashboard/
│   ├── invoices/
│   ├── expenses/
│   └── components/
│
├── static/                 # CSS, JS, images
│   ├── css/
│   ├── js/
│   └── images/
│
└── tests/                  # Test suite
    ├── conftest.py
    ├── test_auth.py
    ├── test_invoices.py
    └── test_tax.py
```

### 5.2 Core Services

#### E-Invoicing Service

```python
# app/services/nrs_client.py
from typing import Optional
from dataclasses import dataclass
import httpx
import qrcode
from app.config import settings

@dataclass
class NRSResponse:
    success: bool
    irn: Optional[str] = None
    qr_data: Optional[str] = None
    error_message: Optional[str] = None

class NRSClient:
    """Async client for NRS E-Invoicing API"""
    
    def __init__(self):
        self.base_url = settings.NRS_API_URL
        self.api_key = settings.NRS_API_KEY
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def generate_invoice_payload(self, invoice) -> dict:
        """Generate NRS-compliant invoice payload"""
        pass
    
    async def submit_invoice(self, invoice) -> NRSResponse:
        """Submit invoice to NRS and get IRN"""
        pass
    
    def generate_qr_code(self, irn: str) -> bytes:
        """Generate QR code from IRN"""
        pass
    
    async def validate_invoice(self, invoice) -> dict:
        """Validate invoice before submission"""
        pass
```

#### Tax Calculation Service

```python
# app/services/tax_calculators/vat.py
from decimal import Decimal
from dataclasses import dataclass
from typing import List
from pydantic import BaseModel

class VATSummary(BaseModel):
    output_vat: Decimal
    input_vat: Decimal
    net_payable: Decimal
    non_recoverable: Decimal
    explanation: str

class VATCalculator:
    """VAT calculation with Input Recovery under Nigeria Tax Act 2025"""
    
    VAT_RATE = Decimal('0.075')  # 7.5% per Section 148
    
    def calculate_output_vat(self, sales_amount: Decimal) -> Decimal:
        """Calculate VAT on sales"""
        return sales_amount * self.VAT_RATE
    
    def calculate_input_vat_recovery(
        self, 
        expenses: List[dict]
    ) -> tuple[Decimal, Decimal]:
        """Calculate recoverable Input VAT based on WREN compliance"""
        recoverable = Decimal('0')
        non_recoverable = Decimal('0')
        
        for expense in expenses:
            vat_amount = expense['vat_amount']
            if expense['wren_compliant']:
                recoverable += vat_amount
            else:
                non_recoverable += vat_amount
        
        return recoverable, non_recoverable
    
    def calculate_net_vat(
        self, 
        output_vat: Decimal, 
        input_vat: Decimal
    ) -> VATSummary:
        """Calculate net VAT payable with explanation per Section 156"""
        pass
```

---

## 6. Data Architecture

### 6.1 Entity Relationship Diagram (Core)

```
┌──────────────────┐       ┌──────────────────┐
│   Organization   │───┬───│   BusinessEntity │
├──────────────────┤   │   ├──────────────────┤
│ id               │   │   │ id               │
│ name             │   │   │ org_id (FK)      │
│ subscription_tier│   │   │ name             │
│ created_at       │   │   │ tin              │
└──────────────────┘   │   │ fiscal_year_start│
                       │   └──────────────────┘
                       │            │
         ┌─────────────┴────────────┼──────────────────┐
         │                          │                  │
         ▼                          ▼                  ▼
┌──────────────────┐    ┌──────────────────┐   ┌──────────────────┐
│      User        │    │   Transaction    │   │     Invoice      │
├──────────────────┤    ├──────────────────┤   ├──────────────────┤
│ id               │    │ id               │   │ id               │
│ email            │    │ entity_id (FK)   │   │ entity_id (FK)   │
│ org_id (FK)      │    │ type (INCOME/EXP)│   │ customer_id (FK) │
│ role             │    │ amount           │   │ invoice_number   │
│ entities_access[]│    │ category_id (FK) │   │ subtotal         │
└──────────────────┘    │ vat_amount       │   │ vat_amount       │
                        │ wren_compliant   │   │ total            │
                        │ date             │   │ status           │
                        │ vendor_id (FK)   │   │ nrs_irn          │
                        │ receipt_url      │   │ qr_code_url      │
                        │ created_by (FK)  │   │ submitted_at     │
                        └──────────────────┘   └──────────────────┘
                                 │
                        ┌────────┴────────┐
                        ▼                 ▼
              ┌──────────────────┐ ┌──────────────────┐
              │     Vendor       │ │    Category      │
              ├──────────────────┤ ├──────────────────┤
              │ id               │ │ id               │
              │ entity_id (FK)   │ │ name             │
              │ name             │ │ type             │
              │ tin              │ │ wren_default     │
              │ tin_verified     │ │ vat_treatment    │
              │ vat_registered   │ └──────────────────┘
              │ created_at       │
              └──────────────────┘
```

### 6.2 Multi-Tenancy Strategy

**Approach:** Shared database with tenant isolation via `entity_id`

```sql
-- All financial tables include entity_id
-- Row-Level Security (RLS) enforces isolation

CREATE POLICY entity_isolation ON transactions
  USING (entity_id IN (SELECT entity_id FROM user_entity_access WHERE user_id = current_user_id()));
```

### 6.3 Audit Trail Design

```sql
CREATE TABLE audit_log (
  id UUID PRIMARY KEY,
  entity_id UUID NOT NULL,
  user_id UUID NOT NULL,
  action VARCHAR(50) NOT NULL,  -- CREATE, UPDATE, DELETE, VIEW
  table_name VARCHAR(100) NOT NULL,
  record_id UUID NOT NULL,
  old_values JSONB,
  new_values JSONB,
  ip_address INET,
  user_agent TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Immutable: No UPDATE or DELETE permissions on this table
```

---

## 7. API Design

### 7.1 API Standards

| Standard | Specification |
|----------|---------------|
| Protocol | REST over HTTPS |
| Format | JSON |
| Versioning | URL path (`/api/v1/...`) |
| Authentication | Bearer token (JWT) |
| Pagination | Cursor-based |
| Error Format | RFC 7807 Problem Details |

### 7.2 Core API Endpoints

```yaml
# Authentication
POST   /api/v1/auth/login
POST   /api/v1/auth/register
POST   /api/v1/auth/refresh
POST   /api/v1/auth/logout
POST   /api/v1/auth/verify-email
POST   /api/v1/auth/resend-verification
POST   /api/v1/auth/forgot-password
POST   /api/v1/auth/reset-password

# Nigeria Address Data (Public)
GET    /api/v1/auth/nigeria/states                  # Returns all 37 Nigerian states
GET    /api/v1/auth/nigeria/states/{state}/lgas     # Returns LGAs for a specific state

# Organizations & Entities
GET    /api/v1/organizations/me
GET    /api/v1/entities
POST   /api/v1/entities
GET    /api/v1/entities/{id}
PATCH  /api/v1/entities/{id}

# Transactions
GET    /api/v1/entities/{entityId}/transactions
POST   /api/v1/entities/{entityId}/transactions
GET    /api/v1/entities/{entityId}/transactions/{id}
PATCH  /api/v1/entities/{entityId}/transactions/{id}
DELETE /api/v1/entities/{entityId}/transactions/{id}

# Invoices
GET    /api/v1/entities/{entityId}/invoices
POST   /api/v1/entities/{entityId}/invoices
GET    /api/v1/entities/{entityId}/invoices/{id}
POST   /api/v1/entities/{entityId}/invoices/{id}/submit-nrs
GET    /api/v1/entities/{entityId}/invoices/{id}/pdf

# Vendors
GET    /api/v1/entities/{entityId}/vendors
POST   /api/v1/entities/{entityId}/vendors
POST   /api/v1/vendors/verify-tin

# Inventory
GET    /api/v1/entities/{entityId}/inventory
POST   /api/v1/entities/{entityId}/inventory
PATCH  /api/v1/entities/{entityId}/inventory/{id}
POST   /api/v1/entities/{entityId}/inventory/{id}/write-off

# Payroll
GET    /api/v1/entities/{entityId}/employees
POST   /api/v1/entities/{entityId}/employees
POST   /api/v1/entities/{entityId}/payrun
GET    /api/v1/entities/{entityId}/payrun/{id}

# Reports
GET    /api/v1/entities/{entityId}/reports/trial-balance
GET    /api/v1/entities/{entityId}/reports/profit-loss
GET    /api/v1/entities/{entityId}/reports/balance-sheet
GET    /api/v1/entities/{entityId}/reports/vat-summary
POST   /api/v1/entities/{entityId}/reports/generate-audit-pack

# Tax Calculations
GET    /api/v1/entities/{entityId}/tax/vat-liability
GET    /api/v1/entities/{entityId}/tax/cit-computation
POST   /api/v1/entities/{entityId}/tax/paye-calculate

# OCR
POST   /api/v1/ocr/scan-receipt
GET    /api/v1/ocr/jobs/{jobId}

# Banking
POST   /api/v1/entities/{entityId}/banking/connect
GET    /api/v1/entities/{entityId}/banking/accounts
POST   /api/v1/entities/{entityId}/banking/sync
GET    /api/v1/entities/{entityId}/banking/reconciliation
```

### 7.3 Error Response Format

```json
{
  "type": "https://api.tekvwa.com/errors/validation-error",
  "title": "Validation Error",
  "status": 400,
  "detail": "The TIN format is invalid. Expected format: 12345678-0001",
  "instance": "/api/v1/vendors/verify-tin",
  "errors": [
    {
      "field": "tin",
      "message": "Invalid TIN format"
    }
  ]
}
```

### 7.4 Super Admin API Endpoints (Platform Management)

These endpoints require `platform_staff` role with `Super Admin` access level. All endpoints return JSON and support pagination where applicable.

```yaml
# Emergency Controls - Kill Switches & Platform Safety
POST   /admin/emergency/platform/read-only           # Toggle platform read-only mode
GET    /admin/emergency/platform/status              # Get platform emergency status
POST   /admin/emergency/tenant/{tenant_id}/suspend   # Emergency suspend a tenant
DELETE /admin/emergency/tenant/{tenant_id}/suspend   # Lift tenant suspension
POST   /admin/emergency/feature/{feature_name}/disable # Disable feature globally
DELETE /admin/emergency/feature/{feature_name}/disable # Re-enable feature

# Cross-Tenant User Search & Management
GET    /admin/users/search                           # Search users across all tenants
GET    /admin/users/{user_id}                        # Get user details
GET    /admin/users/{user_id}/activity               # Get user activity history
POST   /admin/users/{user_id}/suspend                # Suspend/unsuspend user

# Platform Staff Management
GET    /admin/staff                                  # List all platform staff
POST   /admin/staff                                  # Create new platform staff
GET    /admin/staff/{staff_id}                       # Get staff details
PUT    /admin/staff/{staff_id}                       # Update staff

# Organization Verification Workflow
GET    /admin/verifications                          # List pending verifications
GET    /admin/verifications/{org_id}                 # Get verification details
POST   /admin/verifications/{org_id}/approve         # Approve organization
POST   /admin/verifications/{org_id}/reject          # Reject organization

# Global Audit Log Viewer
GET    /admin/audit-logs                             # List all audit logs (paginated)
GET    /admin/audit-logs/stats                       # Get audit statistics
GET    /admin/audit-logs/{log_id}                    # Get specific log details
GET    /admin/audit-logs/export                      # Export audit logs

# Platform Health Metrics
GET    /admin/health                                 # Overall platform health
GET    /admin/health/database                        # Database health metrics
GET    /admin/health/services                        # External service status
GET    /admin/health/metrics                         # Detailed system metrics
GET    /admin/health/tenants/summary                 # Tenant health summary
GET    /admin/health/alerts                          # Active platform alerts

# Tenant Management
GET    /admin/tenants                                # List all tenants
GET    /admin/tenants/{tenant_id}                    # Get tenant details
PUT    /admin/tenants/{tenant_id}                    # Update tenant

# SKU/Billing Management
GET    /admin/skus                                   # List all SKUs
POST   /admin/skus                                   # Create new SKU
GET    /admin/skus/{sku_id}                          # Get SKU details
PUT    /admin/skus/{sku_id}                          # Update SKU
```

---

## 8. Security Architecture

### 8.1 Authentication & Authorization

```
┌─────────────────────────────────────────────────────────────┐
│                    AUTHENTICATION FLOW                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   User → Login → Auth0/Clerk → JWT Token → API Gateway     │
│                                                             │
│   Token Contents:                                           │
│   {                                                         │
│     "sub": "user_12345",                                    │
│     "org_id": "org_67890",                                  │
│     "entities": ["entity_111", "entity_222"],               │
│     "role": "accountant",                                   │
│     "permissions": ["read:transactions", "write:expenses"]  │
│   }                                                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 8.2 Role-Based Access Control

#### Tenant-Level Roles

| Role | Permissions |
|------|-------------|
| **Owner** | Full access to all resources |
| **Admin** | Manage users, settings; Full financial access |
| **Accountant** | Create/edit transactions, invoices, reports |
| **Payroll** | Manage employees and payroll only |
| **Inventory** | Manage stock only |
| **Auditor** | Read-only access to all financial data |
| **Viewer** | Dashboard and reports only |

#### Platform Staff Roles (Super Admin Dashboard)

| Role | Permissions |
|------|-------------|
| **Super Admin** | Full platform access including emergency controls, user management, verification approvals, health monitoring |
| **IT Developer** | Platform health monitoring, audit log viewing, technical diagnostics |
| **CSR** | User search, basic support functions, read-only tenant info |
| **Support Manager** | Escalated support actions, tenant verification review |

**Platform Staff Authentication:**
- Requires `is_platform_staff = true` flag on user
- JWT tokens include `platform_role` claim
- All actions logged to global audit log
- MFA enforcement configurable per role

### 8.3 Data Encryption

| Data State | Encryption |
|------------|------------|
| In Transit | TLS 1.3 |
| At Rest (DB) | AES-256 via managed encryption |
| At Rest (Files) | S3 server-side encryption |
| Sensitive Fields | Application-level encryption (TIN, bank details) |

### 8.4 Security Controls

- **Rate Limiting:** 100 req/min per user, 1000 req/min per org
- **Input Validation:** Strict schema validation on all inputs
- **SQL Injection:** Parameterized queries via ORM
- **XSS:** Content Security Policy headers
- **CSRF:** SameSite cookies, token validation
- **Audit Logging:** All financial operations logged

### 8.5 NDPA/NITDA Security Implementation (v2.1.0)

The following security middleware stack is loaded in order:

```
┌─────────────────────────────────────────────────────────────┐
│                    SECURITY MIDDLEWARE STACK                 │
├─────────────────────────────────────────────────────────────┤
│  1. RequestLoggingMiddleware    - Security event logging    │
│  2. SecurityHeadersMiddleware   - CSP, HSTS, X-Frame-Options│
│  3. CSRFMiddleware              - Double-submit validation  │
│  4. AccountLockoutMiddleware    - Pre-login lockout check   │
│  5. RateLimitingMiddleware      - Per-endpoint rate limits  │
│  6. GeoFencingMiddleware        - Nigerian IP enforcement   │
└─────────────────────────────────────────────────────────────┘
```

#### PII Encryption (AES-256-GCM)

| PII Category | Encryption | Masking Example |
|--------------|------------|-----------------|
| BVN | AES-256-GCM | `***45***901` |
| NIN | AES-256-GCM | `***56***234` |
| RSA PIN | AES-256-GCM | `PEN***678901234` |
| Bank Account | AES-256-GCM | `******7890` |
| TIN | AES-256-GCM | `12***-0001` |
| Phone | AES-256-GCM | `+234***4567` |

#### Rate Limiting Configuration

| Endpoint | Limit | Window | Purpose |
|----------|-------|--------|---------|
| `/auth/login` | 5 | 1 min | Brute force protection |
| `/auth/register` | 3 | 1 min | Account spam prevention |
| `/tax/*/calculate` | 30 | 1 min | API abuse prevention |
| `/*/nrs/*` | 10 | 1 min | FIRS rate compliance |
| `/auth/forgot-password` | 3 | 15 min | Email spam prevention |
| General API | 100 | 1 min | Overall protection |

#### Account Lockout (Progressive)

| Failed Attempts | Lockout Duration |
|-----------------|------------------|
| 1-4 | None |
| 5 | 1 minute |
| 6 | 5 minutes |
| 7 | 15 minutes |
| 8 | 1 hour |
| 9+ | 24 hours |

### 8.6 Email Verification

New organization users must verify their email before accessing full features:
- Verification token generated on registration (24-hour expiry)
- Token sent via transactional email (Outlook SMTP/SendGrid/Mailgun)
- Verification endpoint: `POST /api/v1/auth/verify-email`
- Resend endpoint: `POST /api/v1/auth/resend-verification`

### 8.6 Staff Onboarding Security

Platform staff onboarded by Super Admin/Admin must reset password on first login:
- `must_reset_password` flag set during onboarding
- Automatic redirect to Settings page with security banner
- Password change clears the flag and grants full access
- Ensures onboarding passwords are never used beyond initial login

### 8.7 Global Error Handling

Consistent error responses across all API endpoints:
- HTTP Exceptions: Standard status codes with JSON body
- Validation Errors: Detailed field-level error information
- Business Logic Errors: 400 Bad Request with clear message
- Permission Errors: 403 Forbidden
- Unhandled Errors: 500 with sanitized message (detailed in dev mode)

---

## 9. Integration Architecture

### 9.1 NRS E-Invoicing Integration

```
┌──────────────────────────────────────────────────────────────────┐
│                  NRS E-INVOICING FLOW                            │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Tekvwa                          NRS Portal                   │
│      │                                  │                        │
│      │  1. Prepare Invoice Payload      │                        │
│      │  (JSON with digital signature)   │                        │
│      │ ───────────────────────────────► │                        │
│      │                                  │                        │
│      │  2. Validation Response          │                        │
│      │  (Success/Error)                 │                        │
│      │ ◄─────────────────────────────── │                        │
│      │                                  │                        │
│      │  3. IRN + QR Code Data           │                        │
│      │  (If Success)                    │                        │
│      │ ◄─────────────────────────────── │                        │
│      │                                  │                        │
│      │  4. Store IRN, Generate PDF      │                        │
│      │                                  │                        │
└──────────────────────────────────────────────────────────────────┘

Retry Logic:
- Initial failure: Immediate retry (1x)
- Network timeout: Exponential backoff (30s, 1m, 5m, 15m)
- Max retries: 10 within 24 hours
- Queue for manual review if all retries fail
```

### 9.2 Bank Integration Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                  BANK INTEGRATION OPTIONS                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Option 1: Direct Bank APIs                                      │
│  ─────────────────────────                                       │
│  • GTBank, Access, UBA have developer APIs                       │
│  • Requires individual integrations                              │
│  • Best for transaction data                                     │
│                                                                  │
│  Option 2: Open Banking Aggregator (e.g., Mono, Okra)           │
│  ─────────────────────────────────────────────────               │
│  • Single integration, multiple banks                            │
│  • Account linking via user consent                              │
│  • Real-time transaction sync                                    │
│  • Recommended for MVP                                           │
│                                                                  │
│  Data Flow:                                                      │
│  User → Link Bank → Mono/Okra OAuth → Consent → Sync Enabled    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 9.3 OCR Integration

```
┌──────────────────────────────────────────────────────────────────┐
│                     OCR RECEIPT FLOW                             │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. User captures/uploads receipt image                          │
│  2. Image uploaded to S3 (presigned URL)                         │
│  3. Background job triggers Azure Form Recognizer                │
│  4. Extracted data: Vendor, Amount, Date, Items                  │
│  5. Confidence scores returned with each field                   │
│  6. User reviews/corrects in UI                                  │
│  7. Expense created with receipt attachment                      │
│                                                                  │
│  Fallback: Google Cloud Vision if Azure unavailable             │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 10. Infrastructure & Deployment

### 10.1 Cloud Architecture (AWS)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         AWS ARCHITECTURE                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Route 53 (DNS)                                                     │
│       │                                                             │
│       ▼                                                             │
│  CloudFront (CDN) ─────────► S3 (Static Assets)                    │
│       │                                                             │
│       ▼                                                             │
│  Application Load Balancer                                          │
│       │                                                             │
│       ▼                                                             │
│  ECS Fargate (API Containers)                                       │
│  ├── api-service (x3 instances)                                     │
│  └── worker-service (x2 instances)                                  │
│       │                                                             │
│       ├──────────────► RDS PostgreSQL (Primary + Read Replica)     │
│       │                                                             │
│       ├──────────────► ElastiCache Redis (Cluster)                 │
│       │                                                             │
│       └──────────────► S3 (Documents)                              │
│                                                                     │
│  Secrets Manager (API Keys, DB Credentials)                         │
│  CloudWatch (Logs, Metrics, Alerts)                                 │
│  WAF (Web Application Firewall)                                     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 10.2 Environment Strategy

| Environment | Purpose | Infrastructure |
|-------------|---------|----------------|
| **Development** | Local development | Docker Compose |
| **Staging** | Integration testing | AWS (reduced capacity) |
| **Production** | Live users | AWS (full capacity) |

### 10.3 CI/CD Pipeline

```yaml
# GitHub Actions Pipeline
name: Deploy

on:
  push:
    branches: [main, staging]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run Tests
        run: npm test

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - name: Build Docker Image
        run: docker build -t tekvwa-api .
      - name: Push to ECR
        run: aws ecr push ...

  deploy-staging:
    needs: build
    if: github.ref == 'refs/heads/staging'
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to ECS Staging
        run: aws ecs update-service ...

  deploy-production:
    needs: build
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to ECS Production
        run: aws ecs update-service ...
```

---

## 11. Performance Requirements

### 11.1 Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| API Response Time (p50) | < 200ms | New Relic/DataDog |
| API Response Time (p95) | < 500ms | New Relic/DataDog |
| Page Load Time (FCP) | < 1.5s | Lighthouse |
| Web App Initial Load | < 3s | Lighthouse |
| OCR Processing Time | < 10s | Custom metrics |
| NRS Submission Time | < 5s | Custom metrics |

### 11.2 Scalability Targets

| Metric | MVP | Year 1 | Year 3 |
|--------|-----|--------|--------|
| Concurrent Users | 500 | 5,000 | 50,000 |
| Transactions/Day | 10,000 | 100,000 | 1,000,000 |
| E-Invoices/Day | 1,000 | 10,000 | 100,000 |
| Data Storage | 100 GB | 1 TB | 10 TB |

### 11.3 Optimization Strategies

1. **Database:** Read replicas, connection pooling, query optimization
2. **Caching:** Redis for session, frequently accessed lookups
3. **CDN:** Static assets, PDF reports served from edge
4. **Background Jobs:** OCR, report generation, bank sync off main thread

---

## 12. MVP Scope Definition

### 12.1 MVP Features (Phase 1 - 12 Weeks)

| Module | MVP Scope | Deferred to Later |
|--------|-----------|-------------------|
| **Auth** | Email login, single user per org | SSO, MFA, Team management |
| **Entities** | Single business entity | Multi-entity support |
| **Expenses** | Manual entry + OCR | Recurring expenses |
| **Income** | Manual entry | Bank sync auto-detection |
| **Invoices** | Create, PDF, NRS submit | Credit notes, recurring |
| **VAT** | Output VAT tracking | Full input VAT recovery |
| **Vendors** | Add vendor, TIN verification | Procurement history |
| **Inventory** | Basic stock tracking | Write-offs, alerts |
| **Reports** | P&L, Trial Balance | Balance sheet, Cash flow |
| **Payroll** | Deferred entirely | Full PAYE calculation |
| **Banking** | Deferred entirely | Bank sync, reconciliation |

### 12.2 MVP Technical Scope

| Component | MVP | Post-MVP |
|-----------|-----|----------|
| Web App | FastAPI + Jinja2 + HTMX (responsive) | Progressive Web App (PWA) |
| Desktop App | Deferred | Windows & macOS native apps (Electron/Tauri) |
| Backend | FastAPI modular monolith | Service extraction if needed |
| Database | PostgreSQL | Read replicas |
| Hosting | AWS (single region) | Multi-AZ, DR |
| OCR | Azure Form Recognizer | Custom model training |

Note: There will be no mobile application. Future development will focus on 
desktop applications for Windows and macOS platforms.

### 12.3 MVP Success Criteria

1. [x] User can create account and set up business
2. [x] User can record expenses (manual + OCR)
3. [x] User can record income
4. [x] User can create and submit e-invoice to NRS
5. [x] User can generate P&L report
6. [x] User can verify vendor TIN
7. [x] System calculates output VAT correctly

---

## Appendix A: Technology Alternatives Considered

| Decision | Chosen | Alternative | Why Not |
|----------|--------|-------------|---------|
| Backend Framework | FastAPI | Django | FastAPI offers superior async performance, automatic OpenAPI docs, Pydantic validation |
| Frontend | Jinja2 Templates + HTMX | React SPA | Simpler architecture, no API duplication, faster development |
| Database | PostgreSQL | MySQL | Better JSON support, advanced features, reliability |
| Hosting | AWS | Azure/GCP | More mature Africa region support |
| OCR | Azure Form Recognizer | Google Vision | Better structured data extraction |

---

## Appendix B: Cost Estimates (Monthly)

| Resource | MVP | Year 1 | Notes |
|----------|-----|--------|-------|
| EC2/ECS | $150 | $600 | FastAPI + Celery workers |
| RDS PostgreSQL | $150 | $500 | db.t3.medium -> db.r5.large |
| ElastiCache Redis | $50 | $150 | cache.t3.micro -> cache.m5.large |
| S3 + CloudFront | $50 | $200 | Document storage + CDN |
| Azure Form Recognizer | $100 | $500 | 1000 -> 5000 pages/month |
| Monitoring | $50 | $200 | CloudWatch + Sentry |
| **Total** | **$550** | **$2,150** | |

---

*Document prepared by Tekvwa Pro Audit Engineering Team*
