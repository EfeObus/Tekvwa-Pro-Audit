# TekVwarho ProAudit

> **Nigeria's Premier Tax Compliance & Business Management Platform for the 2026 Tax Reform Era**

[![License: Proprietary](https://img.shields.io/badge/License-Proprietary-red.svg)](LICENSE)
[![Nigeria Tax Compliant](https://img.shields.io/badge/NRS-2026%20Compliant-blue.svg)](#)
[![NDPA Compliant](https://img.shields.io/badge/NDPA-2023%20Compliant-green.svg)](#)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-green.svg)](#)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](#)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green.svg)](#)

---

## Overview

TekVwarho ProAudit is a comprehensive financial management and tax compliance solution designed specifically for Nigerian businesses navigating the **2026 Tax Reform landscape**. The platform integrates real-time NRS (Nigeria Revenue Service) e-invoicing, automated tax calculations, and audit-ready financial reporting into a single, unified system.

**Copyright (c) 2026 Tekvwa IT Solutions LTD. All Rights Reserved.**

### Why TekVwarho ProAudit?

With Nigeria's historic 2026 tax reforms introducing:
- **Progressive PAYE brackets** (starting with ₦800,000 tax-free threshold)
- **Mandatory e-invoicing** via the NRS portal
- **Input VAT recovery** on services and fixed assets
- **Small business exemptions** (0% CIT for turnover ≤ ₦50M)
- **4% Development Levy** for larger enterprises
- **Capital Gains taxed at CIT rate** (merged into corporate income)

...businesses need a modern, integrated solution that handles compliance automatically while providing actionable financial insights.

---

## Version 2.6.0 - Multi-Currency FX & Budget Management (January 2026)

### Overview
This release adds **Multi-Currency/Foreign Exchange** and **Budget Management** modules with full SKU feature gating enforcement.

### Multi-Currency / FX Module (Professional+)
Complete foreign exchange management integrated with the General Ledger:

| Feature | Description |
|---------|-------------|
| **Exchange Rate Management** | Daily/weekly rate feeds, manual entry, historical rates |
| **Foreign Currency Invoices** | Issue invoices in USD, EUR, GBP, etc. |
| **AR/AP Revaluation** | Period-end revaluation with gain/loss recognition |
| **Realized FX Gain/Loss** | Automatic recognition on payment receipt/disbursement |
| **Unrealized FX Gain/Loss** | Period-end mark-to-market adjustments |
| **Multi-Currency Bank Recon** | Reconcile foreign currency bank accounts |

**GL Integration:**
- Account 7100: Foreign Exchange Gains (Revenue)
- Account 7200: Foreign Exchange Losses (Expense)
- Compliant with IAS 21 (Effects of Changes in Foreign Exchange Rates)

**API Endpoints:**
```
GET  /api/v1/entities/{id}/fx/rates              # List exchange rates
POST /api/v1/entities/{id}/fx/rates              # Add exchange rate
GET  /api/v1/entities/{id}/fx/rates/history      # Historical rates
POST /api/v1/entities/{id}/fx/convert            # Currency conversion
POST /api/v1/entities/{id}/fx/revalue            # Period-end revaluation
GET  /api/v1/entities/{id}/fx/exposure           # Currency exposure report
```

### Budget Management Module (Professional+)
Comprehensive budgeting with variance analysis:

| Feature | Description |
|---------|-------------|
| **Budget Creation** | Annual, quarterly, monthly budgets |
| **Budget Line Items** | Linked to Chart of Accounts |
| **Variance Analysis** | Budget vs Actual comparison |
| **Rolling Forecasts** | Adjust budgets based on actuals |
| **Department Budgets** | Cost center budget allocation |
| **Approval Workflows** | Multi-level budget approval |

**API Endpoints:**
```
GET  /api/v1/entities/{id}/budgets               # List budgets
POST /api/v1/entities/{id}/budgets               # Create budget
GET  /api/v1/entities/{id}/budgets/{id}          # Get budget details
GET  /api/v1/entities/{id}/budgets/{id}/variance # Variance analysis
POST /api/v1/entities/{id}/budgets/{id}/forecast # Rolling forecast
```

### SKU Feature Gating
All features now enforced via `require_feature()` dependency:

```python
# Example: FX endpoints require MULTI_CURRENCY feature
fx_feature_gate = require_feature([Feature.MULTI_CURRENCY])
router = APIRouter(dependencies=[Depends(fx_feature_gate)])
```

**Tier Access Matrix:**
| Feature | Core | Professional | Enterprise |
|---------|:----:|:------------:|:----------:|
| Multi-Currency/FX | ❌ | ✅ | ✅ |
| Budget Management | ❌ | ✅ | ✅ |
| Budget Variance | ❌ | ✅ | ✅ |

---

## Version 2.5.0 - Commercial SKU System & Multi-Tier Monetization

### Pricing Tiers (Nigerian Naira)

| Tier | Monthly Price | Target Market | Users |
|------|---------------|---------------|-------|
| **Core** | ₦25,000 - ₦75,000 | Small businesses, Startups | 1-5 |
| **Professional** | ₦150,000 - ₦400,000 | Growing SMEs, Accounting firms | 5-25 |
| **Enterprise** | ₦1,000,000 - ₦5,000,000+ | Multi-nationals, Regulated industries | Unlimited |
| **Intelligence** (Add-on) | ₦250,000 - ₦1,000,000 | Audit teams, Forensic accountants | Any |

### Feature Highlights by Tier

| Feature | Core | Professional | Enterprise |
|---------|:----:|:------------:|:----------:|
| General Ledger & Chart of Accounts | ✅ | ✅ | ✅ |
| Journal Entries & Basic Reports | ✅ | ✅ | ✅ |
| Tax Engine & Invoicing | ✅ | ✅ | ✅ |
| **Multi-Currency / FX** | ❌ | ✅ | ✅ |
| **Budget Management** | ❌ | ✅ | ✅ |
| Payroll & Bank Reconciliation | ❌ | ✅ | ✅ |
| Fixed Assets & Expense Claims | ❌ | ✅ | ✅ |
| E-Invoicing / NRS Compliance | ❌ | ✅ | ✅ |
| WORM Audit Vault | ❌ | ❌ | ✅ |
| Multi-Entity & Intercompany | ❌ | ❌ | ✅ |
| SOX/IFRS Compliance | ❌ | ❌ | ✅ |
| Full API Access | ❌ | ❌ | ✅ |

### Billing & Payments
- **Payment Provider:** Paystack (Nigerian market leader)
- **Billing Cycles:** Monthly or Annual (20% discount)
- **Trial Period:** 14 days free (Professional tier)
- **Usage Metering:** Transactions, invoices, API calls, storage, users
- **Currency:** Nigerian Naira (₦) - amounts stored in kobo

### Paystack Integration (Production-Ready)
Fully implemented payment processing with real API integration:

| Feature | Status | Description |
|---------|--------|-------------|
| Payment Initialization | Yes | Real API calls via httpx async client |
| Payment Verification | Yes | Transaction status verification |
| Webhook Handling | Yes | HMAC-SHA512 signature verification |
| Payment History | Yes | Paginated transaction history API |
| Subscription Management | Yes | Upgrade/downgrade flow |
| Refunds | Yes | Full and partial refund support |

### Payment API Endpoints
```
GET  /api/v1/billing/pricing              # Get tier pricing
GET  /api/v1/billing/subscription         # Current subscription
POST /api/v1/billing/checkout             # Create payment intent
GET  /api/v1/billing/payments             # Payment history (paginated)
GET  /api/v1/billing/payments/{id}        # Payment details
POST /api/v1/billing/webhook/paystack     # Webhook handler (secured)
```

### Payment Flow
```
1. User selects tier → POST /checkout
2. System initializes Paystack → Returns authorization_url
3. User pays on Paystack checkout page
4. Paystack sends webhook → Signature verified
5. PaymentTransaction updated → TenantSKU upgraded
```

### Security Features
- **Webhook Signature Verification** - HMAC-SHA512 with constant-time comparison
- **Idempotency** - Webhook event ID prevents duplicate processing
- **PCI Compliant** - No card data stored (handled by Paystack)
- **Stub Mode** - Graceful fallback when credentials missing

**Full Documentation:** [docs/PAYMENT_MODULE_DOCUMENTATION.md](docs/PAYMENT_MODULE_DOCUMENTATION.md)

---

## Version 2.2.0 - World-Class Forensic Audit System

### Overview
TekVwarho ProAudit now includes a **world-class forensic audit system** designed for Nigerian tax compliance and enterprise-grade auditing. The system provides:

- **Benford's Law Analysis** - Statistical fraud detection using first/second digit distribution
- **Z-Score Anomaly Detection** - Identify statistical outliers in transaction data
- **NRS Gap Analysis** - FIRS National Revenue Service compliance checking
- **Hash Chain Immutable Ledger** - Blockchain-like transaction integrity
- **WORM Storage** - Write-Once-Read-Many document vault (AWS S3 Object Lock)
- **3-Way Matching** - Purchase Order, Goods Receipt, Invoice reconciliation
- **Tax Explainability** - Detailed calculation breakdowns with legal references
- **Compliance Replay Engine** - Recalculate taxes using historical rules

### Benford's Law Analysis
Detects potential fraud by analyzing the distribution of leading digits in transaction amounts:
- **Chi-square Testing**: Statistical significance testing
- **First & Second Digit Analysis**: Comprehensive distribution checks
- **Risk Levels**: conforming, non_conforming, critically_non_conforming
- **Flagged Transactions**: Automatic identification of suspicious patterns

### Z-Score Anomaly Detection
Identifies transactions that are statistically unusual:
- **Grouped Analysis**: By transaction type, vendor, or category
- **Severity Levels**: high (Z > 5), medium (Z 4-5), low (Z 3-4)
- **Configurable Thresholds**: Customizable sensitivity

### NRS Gap Analysis
FIRS National Revenue Service compliance checking:
- **IRN Validation**: Invoice Reference Number format checks
- **e-Invoice Compliance**: NRS registration verification
- **Signatory Requirements**: Authorized signatory validation
- **Missing Document Detection**: Identify compliance gaps

### Hash Chain Immutable Ledger
Blockchain-like integrity for financial records:
- **SHA-256 Hash Chain**: Each entry linked to previous
- **Tamper Detection**: Automatic integrity verification
- **Chain Reconstruction**: Detailed verification reports
- **Merkle Root**: Chain-level integrity proof

### WORM Storage (Audit Vault)
Legal-grade document retention:
- **AWS S3 Object Lock**: Immutable storage
- **7-Year Retention**: Nigerian tax compliance
- **Document Types**: Tax filings, invoices, statements, audit reports
- **Hash Verification**: Document integrity proof

### 3-Way Matching
Purchase Order - Goods Receipt - Invoice reconciliation:
- **Automatic Matching**: Smart document correlation
- **Tolerance Levels**: Configurable price/quantity tolerances
- **Match Status**: perfect_match, partial_match, no_match
- **Discrepancy Reports**: Detailed variance analysis

### Advanced Audit Features
Enterprise-grade capabilities:
- **Tax Explainability Layer**: PAYE, VAT, WHT, CIT calculation breakdowns
- **Compliance Replay Engine**: Historical rule recalculation
- **Regulatory Confidence Score**: Quantified compliance metrics
- **Third-Party Attestation**: Digital auditor sign-off workflow
- **Behavioral Analytics**: Round-number bias, velocity anomalies

### New API Endpoints
```
# Forensic Audit
GET  /api/v1/entities/{id}/forensic-audit/overview
POST /api/v1/entities/{id}/forensic-audit/benfords-law
POST /api/v1/entities/{id}/forensic-audit/z-score
POST /api/v1/entities/{id}/forensic-audit/nrs-gap-analysis
POST /api/v1/entities/{id}/forensic-audit/three-way-match
POST /api/v1/entities/{id}/forensic-audit/full
POST /api/v1/entities/{id}/forensic-audit/integrity/verify
GET  /api/v1/entities/{id}/forensic-audit/worm-storage/status

# Audit Logs
GET  /api/v1/entities/{id}/audit/logs
GET  /api/v1/entities/{id}/audit/history/{resource_type}/{resource_id}
GET  /api/v1/entities/{id}/audit/summary
GET  /api/v1/entities/{id}/audit/export

# Advanced Audit
POST /api/v1/entities/{id}/advanced-audit/explainability/paye
POST /api/v1/entities/{id}/advanced-audit/replay/calculate
POST /api/v1/entities/{id}/advanced-audit/attestation/register
```

### New Frontend Pages
- `/audit` - Main audit dashboard with forensic analysis tools
- `/audit-logs` - Filterable audit log viewer with export
- `/advanced-audit` - Enterprise audit tools (explainability, attestation)
- `/worm-storage` - WORM vault management and verification

---

## Version 2.4.1 - Frontend Implementation Release

### Overview
Complete frontend implementations for intercompany transactions and GL-Bank linkage validation.

### Intercompany Transactions UI
New "Intercompany" tab in the Accounting module (`/accounting`):
- **Summary Dashboard** - Total transactions, volume, uneliminated amounts
- **Transaction List** - Filterable list with elimination status
- **Create Transaction** - Full modal with entity group, from/to entities, type selection
- **Elimination Tools** - Single and bulk elimination for consolidation
- **Balance Summary** - By transaction type with progress indicators

### GL-Bank Linkage Validation UI
New "GL Linkage" button in Bank Reconciliation (`/bank-reconciliation`):
- **Validation Summary** - Total, linked, unlinked, invalid account counts
- **Issues List** - Unlinked/invalid accounts with "Link GL" action
- **Linked Accounts Table** - Shows GL codes and account names
- **Link GL Dialog** - Quick select buttons for Nigerian Standard COA

---

## Version 2.4.0 - Enhanced Financial Reporting & Period Controls

### Overview
This release adds comprehensive financial reporting UI, intercompany transaction management, and enhanced period lock enforcement.

### Financial Reports UI
New report types in the Accounting module (`/accounting` → Reports tab):
- **Cash Flow Statement (Indirect Method)** - Operating, Investing, Financing activities
- **AR Aging Report** - Accounts Receivable aging with GL reconciliation
- **AP Aging Report** - Accounts Payable aging with GL reconciliation

### Intercompany Transaction API
```
POST /api/v1/advanced/intercompany              # Create transaction
GET  /api/v1/advanced/intercompany              # List with filters
POST /api/v1/advanced/intercompany/eliminate    # Mark for elimination
GET  /api/v1/advanced/intercompany/summary      # Balance summary
```

### Period Lock Hard Enforcement
- LOCKED periods now return: "Period has been permanently locked"
- CLOSED periods now return: "Reopen the period or use a different date"
- Validation in `create_journal_entry()`, `post_journal_entry()`, `reverse_journal_entry()`

---

## Version 2.3.0 - Complete GL Integration

### Overview
All sub-ledger modules now post to the General Ledger automatically, ensuring "every naira in the bank is explained."

### Sub-Ledger GL Posting
| Module | Trigger | Journal Entry |
|--------|---------|--------------|
| **Invoices** | `finalize_invoice()` | Dr AR, Cr Revenue, Cr VAT |
| **Payments** | `record_payment()` | Dr Bank, Dr WHT Recv, Cr AR |
| **Expenses** | `create_transaction()` | Dr Expense, Dr VAT Input, Cr AP |
| **Vendor Pay** | `record_vendor_payment()` | Dr AP, Cr Bank, Cr WHT |
| **Payroll** | `process_payroll()` | Full Nigerian payroll journal |
| **Depreciation** | `run_depreciation()` | Dr Depr Expense, Cr Accum Depr |
| **Disposal** | `dispose_asset()` | Asset removal + Gain/Loss |
| **Inventory** | `record_sale()` | Dr COGS, Cr Inventory |

### New Cash Flow Statement Endpoint
```
GET /api/v1/entities/{id}/accounting/reports/cash-flow-statement
```

### Bank-GL Integration
```
GET  /api/v1/entities/{id}/bank/accounts/{id}/gl-linkage
GET  /api/v1/entities/{id}/bank/gl-linkage/validate-all
POST /api/v1/entities/{id}/bank/accounts/{id}/link-gl
GET  /api/v1/entities/{id}/bank/reconciliations/{id}/gl-transactions
POST /api/v1/entities/{id}/bank/reconciliations/{id}/auto-match-gl
```

### New Files Created
```
app/schemas/audit.py                    - Comprehensive Pydantic schemas
templates/audit_dashboard.html          - Main audit dashboard
templates/audit_logs.html               - Audit log viewer
templates/advanced_audit.html           - Enterprise audit tools
templates/worm_storage.html             - WORM vault management
docs/AUDIT_SYSTEM_DOCUMENTATION.md      - Complete documentation
```

### Documentation
For complete audit system documentation, see:
- [`docs/AUDIT_SYSTEM_DOCUMENTATION.md`](docs/AUDIT_SYSTEM_DOCUMENTATION.md)
- [`docs/WORLD_CLASS_AUDIT_DOCUMENTATION.md`](docs/WORLD_CLASS_AUDIT_DOCUMENTATION.md)

---

## Version 2.2.1 - 5 Critical Advanced Audit Features

### Overview
Building on the world-class forensic audit system, TekVwarho ProAudit now implements **5 critical audit compliance features** required by Nigerian FIRS, NTAA 2025, and CAMA 2020.

### 1. Auditor Read-Only Role (Hard-Enforced)
Enterprise-grade access control for external auditors:
- **Hard Enforcement**: All write operations blocked at API level
- **Forbidden Actions**: create, update, delete, submit, cancel, approve, reject
- **Allowed Actions**: view, read, list, get, export, download only
- **Session Tracking**: Complete audit trail of all auditor activities
- **Action Logging**: Every auditor action logged with timestamps

### 2. Evidence Immutability (Files + Records)
Tamper-proof evidence collection and verification:
- **SHA-256 Hashing**: Every piece of evidence hashed at creation
- **Hash Verification**: Detect any tampering through recalculation
- **Evidence Types**: Documents, screenshots, database records, calculations, correspondence
- **File Uploads**: Immediate hash capture on receipt
- **Integrity Proof**: Cryptographic verification on demand

### 3. Reproducible Audit Runs
Deterministic audit execution for verification:
- **Rule Versioning**: Capture exact version of audit rules used
- **Data Snapshots**: Preserve state of data at audit time
- **Parameter Capture**: Store all inputs for exact reproduction
- **Reproduce Function**: Re-run any audit with identical results
- **Comparison Reports**: Compare original vs reproduction

### 4. Human-Readable Findings
Regulator-friendly audit reports:
- **Plain Language**: `to_human_readable()` method on all findings
- **Risk Classification**: Critical, High, Medium, Low, Info
- **Categories**: Tax Calculation, VAT/WHT/PAYE Compliance, Documentation, Internal Control
- **Recommendations**: Actionable remediation steps
- **Regulatory References**: Links to specific laws and sections
- **Management Response**: Built-in response tracking

### 5. Exportable Audit Output
Multiple export formats for different stakeholders:
- **PDF Reports**: Formatted for FIRS regulatory submission
- **CSV Data**: For external analysis and verification
- **Hash Verification**: All exports include integrity proof
- **Executive Summary**: High-level findings for management
- **Detailed Findings**: Complete technical documentation

### New API Endpoints (25+)
```
# Auditor Role Management
GET  /api/audit-system/role/check-permissions
POST /api/audit-system/role/validate-action

# Auditor Sessions
POST /api/audit-system/sessions/start
POST /api/audit-system/sessions/{session_id}/end
GET  /api/audit-system/sessions/my-sessions
GET  /api/audit-system/sessions/{session_id}/actions

# Audit Runs (Reproducible)
POST /api/audit-system/runs/create
POST /api/audit-system/runs/{run_id}/execute
POST /api/audit-system/runs/{run_id}/reproduce
GET  /api/audit-system/runs/list
GET  /api/audit-system/runs/{run_id}

# Findings (Human-Readable)
POST /api/audit-system/findings/create
GET  /api/audit-system/findings/by-run/{run_id}
GET  /api/audit-system/findings/{finding_id}/human-readable

# Evidence (Immutable)
POST /api/audit-system/evidence/create
POST /api/audit-system/evidence/upload-file
GET  /api/audit-system/evidence/{evidence_id}/verify
GET  /api/audit-system/evidence/by-run/{run_id}

# Export
GET  /api/audit-system/export/run/{run_id}/pdf
GET  /api/audit-system/export/run/{run_id}/csv
GET  /api/audit-system/export/findings/{finding_id}/pdf

# Dashboard
GET  /api/audit-system/dashboard/stats
```

### New Database Tables
- `audit_runs` - Reproducible audit execution records
- `audit_findings` - Human-readable findings with risk levels
- `audit_evidence` - Immutable evidence with SHA-256 hashes
- `auditor_sessions` - Session tracking for auditor access
- `auditor_action_logs` - Individual action logging

### New Files
```
app/models/audit_system.py              - 5 models, 7 enums
app/services/audit_system_service.py    - 5 service classes
app/routers/audit_system.py             - 25+ API endpoints
alembic/versions/20260107_1800_audit_system.py - Database migration
```

---

## Version 2.1.0 - Security & Compliance Suite (NDPA/NITDA 2023)

### Nigerian Data Protection Compliance
TekVwarho ProAudit now includes **enterprise-grade security** features fully compliant with Nigeria's Data Protection Act 2023 (NDPA) and NITDA guidelines.

#### PII Encryption (AES-256-GCM)
- **Field-Level Encryption**: BVN, NIN, RSA PIN, bank accounts, TIN, phone numbers
- **Authenticated Encryption**: AES-256-GCM with integrity verification
- **Key Rotation**: Versioned key management for security updates
- **PIIMasker**: Display-safe masking (`12345678901` → `***45***901`)

#### Nigerian Data Sovereignty
- **Geo-Fencing**: Restrict access to Nigerian IP ranges only
- **Nigerian ISP Blocks**: MTN, Airtel, Glo, 9mobile, MainOne, Rack Centre
- **AFRINIC Allocations**: Verified Nigerian IP address ranges
- **Logging**: All access attempts logged for compliance audits

#### Right-to-Erasure Workflow
- **NDPA Article 36 Compliance**: Data subject deletion requests
- **Statutory Retention**: Automatic 7-year hold for tax records
- **Audit Trail**: Complete logging of erasure activities
- **Selective Erasure**: Delete only non-statutory data

#### Rate Limiting & DDoS Protection
| Endpoint Category | Limit | Window |
|-------------------|-------|--------|
| Login | 5 requests | 1 minute |
| Registration | 3 requests | 1 minute |
| Tax Calculators | 30 requests | 1 minute |
| NRS Submission | 10 requests | 1 minute |
| Password Reset | 3 requests | 15 minutes |
| General API | 100 requests | 1 minute |

#### CSRF Protection (HTMX)
- **Double-Submit Cookie Pattern**: Industry-standard CSRF protection
- **HTMX Integration**: Automatic X-CSRF-Token header injection
- **SameSite Cookies**: Strict cookie configuration
- **Bearer Token Bypass**: API requests use JWT authentication

#### XSS Protection & Security Headers
- **Content Security Policy**: `default-src 'self'` with trusted sources
- **X-Frame-Options**: DENY (clickjacking protection)
- **HSTS**: 1-year max-age with includeSubDomains
- **X-Content-Type-Options**: nosniff
- **Referrer-Policy**: strict-origin-when-cross-origin

#### Brute Force Protection
- **Account Lockout**: 5 failed attempts maximum
- **Progressive Lockout**: 1min → 5min → 15min → 1hr → 24hr
- **Automatic Unlock**: Time-based lockout expiry
- **Login Integration**: Pre-authentication lockout check

#### Nigerian Validators
- `validate_nigerian_tin`: FIRS TIN format (10 characters)
- `validate_nigerian_bvn`: BVN format (11 digits)
- `validate_nigerian_nin`: NIN format (11 digits)
- `validate_nigerian_phone`: Nigerian phone (+234/0 prefix)
- `validate_nigerian_account`: NUBAN account (10 digits)

### Security Middleware Stack
The application loads 6 security middleware layers in optimal order:
1. **RequestLoggingMiddleware** - Security event logging
2. **SecurityHeadersMiddleware** - CSP, HSTS, X-Frame-Options
3. **CSRFMiddleware** - Double-submit cookie validation
4. **AccountLockoutMiddleware** - Pre-login lockout check
5. **RateLimitingMiddleware** - Per-endpoint rate limiting
6. **GeoFencingMiddleware** - Nigerian IP enforcement

### New Security Files
```
app/utils/ndpa_security.py     - NDPA security utilities (~700 lines)
app/middleware/security.py     - Security middleware (~500 lines)
app/middleware/__init__.py     - Middleware package exports
docs/SECURITY_ARCHITECTURE.md  - Security documentation
```

---

## Version 2.0.0 - Business Intelligence & Executive Compensation Suite

### BIK (Benefit-in-Kind) Automator for Executive Compensation
TekVwarho ProAudit now includes a **comprehensive BIK calculation engine** that automatically values executive benefits using 2026 Nigerian tax rules.

#### Vehicle Benefits
- **Saloon Car**: 5% of vehicle cost
- **SUV/Crossover**: 5% of vehicle cost + 25% premium
- **Pick-up Truck**: 4% of vehicle cost (commercial use)
- **Luxury Vehicle**: 7.5% of vehicle cost + luxury surcharge
- **Driver Benefit**: ₦600,000/year flat rate

#### Accommodation Benefits
- **Rented (Unfurnished)**: 7.5% of annual rent
- **Rented (Furnished)**: 10% of annual rent
- **Company-Owned**: 15% of annual salary
- **Furniture Allowance**: 10% of furniture value

#### Other Benefits
- **Utilities**: 100% of employer-paid amounts (electricity, water, gas, internet)
- **Domestic Staff**: ₦500,000/year per staff member
- **Generator**: 10% of cost + fuel allowance

#### PAYE on BIK
- Automatic PAYE calculation using 2026 progressive brackets
- Integration with payroll for consolidated tax reporting

### NIBSS Pension Direct-Debit Generator
Generate **bank-ready NIBSS XML files** for bulk pension payments to all licensed Pension Fund Administrators.

#### Supported PFAs (20+)
ARM, Stanbic IBTC, Leadway, AIICO, AXA Mansard, Crusader Sterling, Fidelity, First Guarantee, 
IEI Anchor, NLPC, NPF Pensions, Oak Pensions, OAK, PAL Pensions, Premium, Radix, 
Sigma, Tangerine, Trustfund, Veritas Glanvills

#### Features
- **NIBSS NIP Bulk Payment Format**: Bank-compatible XML structure
- **RSA PIN Validation**: Verify employee pension registration numbers
- **Multi-Batch Processing**: Handle thousands of pension payments
- **CSV Export**: Alternative format for bank uploads
- **Summary Reports**: Reconciliation-ready payment summaries

### Growth Radar & Tax Threshold Intelligence
Smart monitoring system that tracks your business growth and alerts you before crossing critical **tax thresholds**.

#### Nigerian Tax Thresholds Monitored
| Threshold | Amount | Tax Implications |
|-----------|--------|------------------|
| Small → Medium | ₦25,000,000 | CIT changes from 0% to 20% |
| Medium → Large | ₦100,000,000 | CIT 30%, Dev Levy 4%, TET 2.5% |
| VAT Registration | ₦25,000,000 | Mandatory VAT collection |

#### Features
- **Proximity Analysis**: Distance to next threshold in percentage
- **Growth Projection**: Months until threshold breach
- **Transition Planning**: Preparation checklist for bracket changes
- **Alert Levels**: Normal → Info → Warning → Critical → Exceeded

### Stock Write-off VAT Workflow
Automated handling of **inventory write-offs** with proper VAT input adjustment documentation.

#### Write-off Reasons Supported
- Expired goods (with expiry date validation)
- Damaged/defective stock
- Obsolete inventory
- Theft/loss (with police report)
- Spoilage (perishables)
- Quality failures (QC rejected)
- Sample distribution (marketing)
- Regulatory destruction (compliance)

#### VAT Adjustment
- Automatic 7.5% VAT input reversal calculation
- FIRS-compliant adjustment documentation
- Approval workflow integration
- Supporting document tracking

### Multi-Location Inventory Transfers
Full support for **inventory movements** between warehouses, stores, and production facilities.

#### Transfer Types
- Warehouse to Warehouse
- Store to Store
- Warehouse to Store
- Store to Warehouse
- Production to Warehouse
- Warehouse to Production
- Warehouse to Customer (Direct Ship)

#### Interstate Levy Calculation
- **0.5% Levy**: Automatically applied for cross-state transfers
- All 37 Nigerian states + FCT supported
- Levy documentation for state revenue authorities

### Robust Error Handling System
Enterprise-grade **exception handling** with 50+ custom error types for comprehensive error management.

#### Exception Categories
- **Validation Errors**: Field-level validation with Nigerian-specific rules
- **Authentication**: Login, token, and session errors
- **Authorization**: Role-based permission denials
- **Business Rules**: Domain-specific violations
- **Tax Calculations**: Nigerian tax computation errors
- **NRS Integration**: FIRS e-invoicing failures
- **Database**: Connection and integrity errors
- **External Services**: Third-party API failures

#### Nigerian-Specific Validators
- TIN format validation (FIRS format)
- BVN validation (11-digit format)
- Nigerian bank account validation
- RSA PIN validation (PEN + 12 digits)

### New API Endpoints

#### Business Intelligence
```
POST /api/v1/business-intelligence/bik/calculate
GET  /api/v1/business-intelligence/bik/rates
POST /api/v1/business-intelligence/pension/generate-nibss-file
POST /api/v1/business-intelligence/pension/generate-nibss-file/download
GET  /api/v1/business-intelligence/pension/pfa-list
POST /api/v1/business-intelligence/pension/validate-rsapin
GET  /api/v1/business-intelligence/growth-radar
GET  /api/v1/business-intelligence/growth-radar/thresholds
GET  /api/v1/business-intelligence/growth-radar/projection
POST /api/v1/business-intelligence/inventory/write-off
GET  /api/v1/business-intelligence/inventory/write-off/reasons
POST /api/v1/business-intelligence/inventory/write-off/{id}/vat-adjustment-doc
POST /api/v1/business-intelligence/inventory/transfer
GET  /api/v1/business-intelligence/inventory/transfer/states
GET  /api/v1/business-intelligence/inventory/transfer/types
```

### New Services Created
- `app/services/bik_automator.py` - BIK calculation engine
- `app/services/nibss_pension.py` - NIBSS XML generation
- `app/services/growth_radar.py` - Threshold monitoring
- `app/services/inventory_management.py` - Write-off and transfer workflows
- `app/utils/error_handling.py` - Comprehensive error system

### Documentation
- `docs/ADVANCED_ACCOUNTING_MODULE.md` - Complete module documentation

---

## Version 1.9.0 - Payroll System with Nigerian 2026 Compliance

### Complete Payroll Management
TekVwarho ProAudit now includes a **full-featured payroll system** designed specifically for Nigerian businesses, with complete 2026 Tax Reform compliance built-in.

### Nigerian Tax Reform 2026 - PAYE Compliance
- **New Tax-Free Threshold**: ₦800,000 annual (was ₦300,000) - employees earning below this pay no PAYE
- **Progressive PAYE Bands**:
  - ₦0 - ₦800,000: 0% (Exempt)
  - ₦800,001 - ₦2,400,000: 15%
  - ₦2,400,001 - ₦4,800,000: 20%
  - ₦4,800,001 - ₦7,200,000: 25%
  - Above ₦7,200,000: 30%
- **Consolidated Relief Allowance (CRA)**: ₦200,000 + 20% of Gross Income
- **2026 Rent Relief**: 20% of annual rent paid (max ₦500,000)
- **Life Insurance Premium Relief**: Monthly premiums (max ₦250,000/year)

### Statutory Deductions
- **Pension Contribution**: 8% employee / 10% employer (per PenCom guidelines)
- **NHF**: 2.5% of basic salary (for eligible employees)
- **NSITF**: 1% employer contribution
- **ITF**: 1% employer contribution for qualifying companies

### Employee Management
- **Comprehensive Employee Records**: Personal details, employment info, compliance data
- **Bank Account Management**: Multiple accounts per employee, primary account designation
- **Nigerian PFA Integration**: All 20 licensed Pension Fund Administrators supported
- **Leave Management**: Annual, sick, maternity, paternity, and other leave types

### Payroll Processing
- **Automated Salary Calculation**: Gross pay, deductions, net pay in one click
- **Payroll Runs**: Monthly, bi-weekly, or weekly pay periods
- **Approval Workflow**: Draft → Pending Approval → Approved → Processing → Paid
- **Bank Schedule Generation**: Payment file export for bank uploads
- **Payslip Generation**: Detailed payslips with all earnings and deductions

### Remittance Tracking
- **PAYE Remittance**: Track monthly PAYE submissions to state tax authorities
- **Pension Remittance**: Monitor PFA contribution transfers
- **NHF/NSITF/ITF Tracking**: Complete statutory remittance management
- **Due Date Alerts**: Never miss a compliance deadline

### Salary Calculator
- **Interactive Calculator**: Real-time net salary calculation
- **What-If Analysis**: Compare different salary structures
- **Tax Breakdown**: See exactly how PAYE is calculated
- **Employer Cost View**: Total cost-to-company analysis

### New API Endpoints
- `POST /api/v1/payroll/employees` - Create employee
- `GET /api/v1/payroll/employees` - List employees
- `POST /api/v1/payroll/payroll-runs` - Create payroll run
- `POST /api/v1/payroll/payroll-runs/{id}/process` - Process payroll
- `GET /api/v1/payroll/payslips` - List payslips
- `POST /api/v1/payroll/calculate-salary` - Calculate salary breakdown
- `GET /api/v1/payroll/remittances` - List statutory remittances
- `GET /api/v1/payroll/dashboard` - Payroll dashboard stats

### Frontend Pages
- **Payroll Dashboard**: At-a-glance payroll metrics and pending actions
- **Employees Tab**: Full employee directory with search and filters
- **Payroll Runs Tab**: View and manage all payroll runs
- **Remittances Tab**: Track all statutory remittance obligations
- **Loans Tab**: Employee loan and salary advance management
- **Salary Calculator Modal**: Interactive 2026-compliant calculator

### Database Schema
New tables added via Alembic migration `20260106_1600_add_payroll_system.py`:
- `employees` - Employee master records
- `employee_bank_accounts` - Bank account details
- `payroll_runs` - Payroll batch processing
- `payslips` - Individual employee payslips
- `payslip_items` - Earnings and deduction line items
- `statutory_remittances` - PAYE, pension, NHF tracking
- `employee_loans` - Loan and advance management
- `loan_repayments` - Loan repayment history
- `employee_leaves` - Leave requests and approvals
- `payroll_settings` - Entity-level payroll configuration

---

## Version 1.8.0 - Nigeria Address Fields & Registration Improvements

### Nigeria States & LGAs API
- **Complete Nigeria Data**: All 37 states and 774 Local Government Areas
- **REST API Endpoints**: `/api/v1/auth/nigeria/states` and `/api/v1/auth/nigeria/states/{state}/lgas`
- **Authoritative Data Source**: Accurate and comprehensive Nigeria geographic data
- **State Validation**: State and LGA validation for business entity addresses

### Registration Flow Improvements
- **Dynamic LGA Dropdown**: LGA field auto-populates based on selected state
- **State-Dependent Selection**: JavaScript-powered cascading dropdowns
- **Address Field Enhancement**: Both business entities and user profiles support LGA
- **Improved UX**: Clean, intuitive registration form with Nigerian address support

### Email Verification Enhancements
- **Verification Tracking**: New database fields track verification status
- **`email_verification_token`**: Secure token storage in database
- **`email_verification_sent_at`**: Timestamp for token expiry validation
- **`email_verified_at`**: Record of successful verification time
- **`is_invited_user`**: Distinguishes invited users from self-registered users

### Database Migration
- **New LGA Column**: Added `lga` column to `business_entities` table
- **User Verification Fields**: Added 4 new columns to `users` table
- **Alembic Migration**: `20260106_1400_add_lga_email_verification.py`

---

## Version 1.7.0 - Bulk Operations & Export Improvements

### Bulk Operations
- **Bulk Import**: CSV/Excel import for customers, vendors, inventory, and transactions
- **Bulk Delete**: Delete multiple records at once with confirmation
- **Background Processing**: Large imports handled via Celery workers
- **Progress Tracking**: Real-time progress indicators for bulk operations

### Export Enhancements  
- **Multi-Format Export**: PDF, Excel, CSV export for all data types
- **Custom Date Ranges**: Filter exports by date range
- **Template Support**: Downloadable CSV templates for bulk imports

---

## Version 1.6.0 - Security & Authentication Enhancements

### Email Verification System
- **Registration Verification**: New users receive verification email with secure token
- **Resend Verification**: Users can request new verification emails
- **Full URL Links**: Email links include complete URLs for better deliverability

### Staff Onboarding Security
- **Forced Password Reset**: Newly onboarded staff/admins must change password on first login
- **Security Banner**: Clear notification prompting password change
- **Automatic Redirect**: Staff redirected to settings page until password is changed

### Password Security Features
- **Password Visibility Toggle**: Eye icon to show/hide passwords on all auth forms
- **Password Reset Flow**: Complete forgot password → email → reset password workflow

### Global Error Handling
- **Consistent Error Responses**: All errors return standardized JSON format
- **Exception Types Handled**:
  - HTTP Exceptions (4xx/5xx)
  - Request Validation Errors (422)
  - Pydantic Validation Errors
  - Business Logic Errors (ValueError)
  - Permission Errors (403)
  - Unhandled Exceptions (500)
- **Development Mode**: Detailed error messages for debugging
- **Production Mode**: Sanitized error messages for security

---

## Version 1.4.0 - Complete 2026 Compliance

### TIN Validation (NRS Portal Integration)
- **Real-time TIN Verification**: Validate TINs via [NRS TaxID Portal](https://taxid.nrs.gov.ng/)
- **Individual Validation**: Verify individuals using 11-digit NIN (National Identification Number)
- **Corporate Validation**: Support for Business Name, Company, Incorporated Trustee, Limited Partnership, LLP
- **Vendor Compliance Check**: Pre-contract verification with **₦5,000,000** penalty warning

### 15% Minimum Effective Tax Rate (ETR)
- **Large Company Threshold**: Applies to businesses with turnover >= **₦50 billion**
- **MNE Constituents**: Applies to groups with revenue >= **€750 million**
- **Top-up Tax Calculation**: Automatic ETR shortfall detection and top-up calculation

### Capital Gains Tax (CGT) at 30%
- **New Rate for Large Companies**: CGT increased from 10% to **30%**
- **Small Company Exemption**: Turnover ≤ ₦100M AND assets ≤ ₦250M retain 10% rate
- **Indexation Allowance**: Inflation adjustment for long-held assets

### Zero-Rated VAT Input Credit Tracking
- **Refund Eligibility**: Track input VAT on zero-rated supplies (food, education, healthcare, exports)
- **IRN Validation**: Only purchases with valid NRS IRN qualify for refund
- **Claim Generation**: Automated refund claim calculation

### Peppol BIS Billing 3.0 Export
- **UBL 2.1 XML Export**: Peppol-compliant structured invoice format
- **JSON Export**: API-friendly invoice representation
- **CSID Generation**: Cryptographic Stamp Identifier for invoice integrity
- **QR Code Embedding**: Verification data for invoice authentication

### Compliance Penalty Tracker
- **Late Filing**: ₦100,000 first month + ₦50,000 subsequent months
- **Unregistered Vendor**: ₦5,000,000 fixed penalty
- **B2C Late Reporting**: ₦10,000 per transaction (max ₦500,000/day)
- **Tax Remittance**: 10% + 2% monthly interest for VAT/PAYE/WHT

---

## Version 1.3.0 - Fixed Assets & Dashboard

### Fixed Asset Register
- Complete capital asset tracking with depreciation (Straight Line, Reducing Balance, Units of Production)
- Automatic capital gain/loss calculation on disposal (taxed at CIT rate under 2026 reform)
- VAT recovery on capital assets via vendor IRN validation
- Standard Nigerian depreciation rates built-in

### Compliance Health Dashboard
- **TIN/CAC Vault**: Prominent display of tax credentials with verification status
- **Compliance Health Score**: Real-time compliance indicator (0-100%)
- **Small Company Status**: Automatic 0% CIT eligibility check
- **Development Levy Status**: Exemption threshold monitoring

### B2C Real-time Reporting
- Automatic reporting of B2C transactions over ₦50,000 to NRS within 24 hours
- Configurable reporting thresholds per entity

---

## Key Features

### Core Business Operations

| Feature | Description |
|---------|-------------|
| **Inventory Management** | Real-time stock tracking with automated low-stock alerts. "Stock-to-Tax" linking for expired/damaged goods write-offs |
| **Multi-Entity Accounts** | Separate ledgers for multiple businesses with Role-Based Access Control (Owner, Accountant, Auditor views) |
| **Supply Chain Tracking** | Vendor management with integrated TIN verification, VAT-compliance status tracking |
| **Expense & Income** | Automated categorization, WREN flagging for tax-deductible expenses |
| **Financial Reports** | One-click audit-ready PDFs: Trial Balance, P&L, Fixed Asset Registers |
| **Fixed Asset Register** | Capital asset tracking, depreciation schedules, capital gains reporting |

### 2026 Tax Compliance Engine

| Feature | Description |
|---------|-------------|
| **NRS E-Invoicing** | Real-time B2B/B2C invoice validation, automatic IRN and QR Code generation |
| **TIN Validation** | Real-time TIN verification via NRS TaxID portal (Individual/Corporate) |
| **Input VAT Recovery** | Track VAT paid on services and fixed assets as credits to reduce final VAT liability |
| **Zero-Rated VAT Tracker** | Track refund-eligible input VAT on zero-rated supplies (IRN validated) |
| **Smart Tax Logic** | Automatic 0% CIT for small businesses, 4% Development Levy for larger companies |
| **Minimum ETR (15%)** | Top-up tax calculation for companies with ₦50B+ turnover |
| **CGT at 30%** | Capital Gains Tax for large companies (small company exemption) |
| **Progressive PAYE** | Payroll module with 2026 tax bands (₦800,000 tax-free bracket support) |
| **72-Hour Dispute Window** | Track buyer rejections within the 72-hour window with legal lock protection |
| **B2C Real-time Reporting** | 24-hour NRS reporting for B2C transactions over ₦50,000 |
| **Compliance Penalties** | Automatic penalty calculation (late filing, unregistered vendor, B2C late) |
| **Peppol BIS 3.0** | Export invoices as UBL 2.1 XML/JSON for international trade |

### Advanced Financial Pipeline

| Feature | Description |
|---------|-------------|
| **Audit Vault** | 5-year digital record keeping compliant with NTAA requirements |
| **Asset Register** | Depreciation tracking and Capital Gains merged into CIT reporting |
| **Self-Assessment** | Pre-fills NRS forms based on yearly data for TaxPro Max upload |
| **TaxPro Max Export** | Ready-file CSV/Excel exports formatted for TaxPro Max upload requirements |
| **WHT Manager** | Automatic Withholding Tax calculations by service type and payee |
| **Compliance Health** | Real-time compliance score with automated threshold monitoring |

### NRS Integration (NEW in v2.2.0)

| Feature | Description |
|---------|-------------|
| **Invoice IRN Submission** | Submit invoices to NRS for Invoice Reference Number generation |
| **IRN Status Tracking** | Real-time status checking for submitted invoice IRNs |
| **TIN Validation API** | Single and bulk TIN validation (up to 100 at once) |
| **Buyer Dispute System** | Submit buyer disputes within 72-hour window |
| **B2C Transaction Reporting** | 2026 compliant real-time B2C reporting to NRS |
| **Health Monitoring** | NRS API health check and status monitoring |

### Bank Reconciliation (NEW in v2.2.0)

| Feature | Description |
|---------|-------------|
| **Bank Account Management** | Track multiple bank accounts with CBN bank codes |
| **Statement Import** | Import bank statements (CSV, OFX, PDF) with auto-parsing |
| **Auto-Matching** | Fuzzy matching of bank transactions to system records |
| **Manual Matching** | Manual transaction matching/unmatching interface |
| **Reconciliation Workflow** | Full workflow: create → adjust → complete → approve |
| **Variance Analysis** | Reconciliation summary with discrepancy reporting |

### Expense Claims (NEW in v2.2.0)

| Feature | Description |
|---------|-------------|
| **Employee Expense Claims** | Submit and track employee expense reimbursements |
| **12 Expense Categories** | Travel, Accommodation, Meals, Transport, Communication, etc. |
| **Multi-Item Claims** | Multiple expense items per claim with receipt tracking |
| **Approval Workflow** | Multi-level approval/rejection with comments |
| **Tax Deductibility** | Track tax-deductible expenses with GL account codes |
| **Payment Tracking** | Track claim payment status and dates |

### Business Intelligence & ML (NEW in v2.4.1)

| Feature | Description |
|---------|-------------|
| **Cash Flow Forecasting** | Time series prediction using Exponential Smoothing, ARIMA, or LSTM neural networks |
| **Growth Prediction** | Revenue, expense, and profit forecasting with polynomial regression and neural networks |
| **NLP Analysis** | Sentiment analysis, named entity recognition, keyword extraction, and document classification |
| **OCR Processing** | Intelligent document extraction for receipts, invoices, and financial documents (Nigerian VAT compliant) |
| **Custom Model Training** | Train and deploy custom ML models for business-specific predictions |
| **ML Dashboard** | Unified view of all AI-powered insights for each business entity |
| **Anomaly Detection** | Identify statistical outliers in transaction data using Z-score analysis |

#### ML/AI API Endpoints
```
POST /api/v1/ml/forecast/cash-flow      # Generate cash flow forecast
POST /api/v1/ml/predict/growth          # Growth prediction
POST /api/v1/ml/nlp/analyze             # NLP text analysis
POST /api/v1/ml/ocr/process             # OCR document processing
POST /api/v1/ml/train/neural-network    # Train custom model
GET  /api/v1/ml/dashboard/{entity_id}   # ML insights dashboard
GET  /api/v1/ml/models                  # List trained models
POST /api/v1/ml/anomaly/detect          # Anomaly detection
```

For detailed documentation, see [Business Intelligence Documentation](docs/BUSINESS_INTELLIGENCE_DOCUMENTATION.md).

---

## Test Coverage

Comprehensive test suite verified with **433 tests passing**:

| Category | Tests | Status |
|----------|-------|--------|
| **Tax Calculators** (VAT, PAYE, WHT, CIT) | 28 tests | Passing |
| **2026 Tax Compliance** | 177 tests | Passing |
| **API & Authentication** | 50 tests | Passing |
| **Transaction Service** | 11 tests | Passing |
| **Compliance Health** | 47 tests | Passing |
| **Integration Tests** | 120+ tests | Passing |
| **Total** | **433 tests** | **All Passing** |

### Tax Calculator Details

| Tax Type | Tests | Status |
|----------|-------|--------|
| **VAT** (7.5%) | 4 tests | Passing |
| **PAYE** (2026 Bands) | 6 tests | Passing |
| **WHT** (By Service Type) | 7 tests | Passing |
| **CIT** (0%/20%/30%) | 6 tests | Passing |
| **Band Detection** | 5 tests | Passing |
| **Minimum ETR** (15%) | 5 tests | Passing |
| **CGT** (30% Large Co.) | 6 tests | Passing |
| **TIN Validation** | 10 tests | Passing |
| **Penalty Tracking** | 8 tests | Passing |
| **Peppol Export** | 6 tests | Passing |

---

## Target Users

1. **Small & Medium Enterprises (SMEs)** - Simplified compliance for the 0% CIT bracket
2. **Large Corporations** - Complex multi-entity management with Development Levy tracking
3. **Tax Consultants/Auditors** - Read-only audit views and export capabilities
4. **Accountants** - Day-to-day financial management and reconciliation
5. **External Accountants** - Client access for tax filings (time-limited)

---

## Technical Stack

```
Backend:        Python 3.11+ with FastAPI 0.110+
Database:       PostgreSQL 15+
ORM:            SQLAlchemy 2.0 + Alembic (Migrations)
Frontend:       Jinja2 Templates + HTMX + Alpine.js + TailwindCSS
E-Invoicing:    NRS API Integration (REST/Async)
Authentication: FastAPI-Users + OAuth2/JWT
Validation:     Pydantic v2
Task Queue:     Celery + Redis
PDF Generation: WeasyPrint / ReportLab
Hosting:        AWS / Azure (Nigeria Region for data residency)
Platforms:      Web (Responsive), Desktop (Windows/macOS - Future)
```

Note: No mobile application is planned. Future development will focus on 
native desktop applications for Windows and macOS.

---

## Project Structure

```
TekVwarho-ProAudit/
├── docs/
│   ├── BUSINESS_CASE.md          # Business justification & ROI
│   ├── USE_CASES.md              # Detailed use case scenarios
│   ├── UI_UX_RESEARCH.md         # User research & design guidelines
│   ├── TECHNICAL_ARCHITECTURE.md # System design & API specs
│   ├── WIREFRAMES.md             # Comprehensive wireframe designs
│   ├── COMPLIANCE_REQUIREMENTS.md # Nigeria 2026 tax law compliance
│   ├── ROADMAP.md                # Development phases & timeline
│   └── RECOMMENDATIONS.md        # Strategic guidance
├── app/                          # FastAPI application
│   ├── config.py                 # Settings & environment config
│   ├── database.py               # SQLAlchemy async engine
│   ├── models/                   # SQLAlchemy models
│   ├── schemas/                  # Pydantic schemas
│   ├── routers/                  # API route handlers
│   ├── services/                 # Business logic
│   │   └── tax_calculators/      # VAT, PAYE, CIT, WHT
│   └── tasks/                    # Celery background tasks
├── templates/                    # Jinja2 HTML templates
├── static/                       # CSS, JS, images
├── tests/                        # Test suites
├── main.py                       # FastAPI entry point
├── README.md                     # This file
├── LICENSE                       # Tekvwa IT Solutions LTD Proprietary License
├── CONTRIBUTING.md               # Contribution guidelines
├── requirements.txt              # Python dependencies
├── pyproject.toml                # Python project config
└── alembic.ini                   # Database migration config
```

---

## Getting Started

**Project is currently in the documentation and planning phase.**

### Prerequisites (Planned)
- Python 3.11+
- PostgreSQL 15+
- NRS Developer Account (for e-invoicing sandbox)

### Installation (Coming Soon)

```bash
# Clone the repository
git clone https://github.com/EfeObus/TekVwarho-ProAudit.git
cd TekVwarho-ProAudit

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Run database migrations
alembic upgrade head

# Start development server
uvicorn main:app --reload --port 8000
```

---

## System Statistics (v2.5.0)

| Metric | Value |
|--------|-------|
| **Total Routes** | 550+ |
| **API Endpoints** | 495+ |
| **View Routes** | 55 |
| **Database Models** | 91 exports |
| **Test Coverage** | 468 tests passing |
| **Security Middleware** | 8 layers (incl. SKU) |
| **Templates** | 30 HTML files |
| **Services** | 52+ service modules |
| **Routers** | 34 API routers |
| **SKU Feature Flags** | 40+ |

---

## Compliance Certifications

- [x] NRS E-Invoicing Integration (Development & Production APIs)
- [x] NDPA 2023 Data Protection Compliance
- [x] NITDA Security Guidelines
- [ ] ISO 27001 Information Security (Planned)

---

## License

**PROPRIETARY - All Rights Reserved**

This software is the intellectual property of Tekvwa IT Solutions LTD. It may not be sold, resold, redistributed, or sublicensed. Use is permitted for personal and educational purposes only.

See [LICENSE](LICENSE) for full terms and conditions.

This software complies with Nigerian law including:
- Companies and Allied Matters Act (CAMA) 2020
- Nigeria Data Protection Regulation (NDPR) 2019
- Nigeria Data Protection Act 2023
- Copyright Act (Cap C28, LFN 2004)

---

## Contact

- **Company:** Tekvwa IT Solutions LTD
- **Email:** info@tekvwa.org
- **GitHub:** [EfeObus/TekVwarho-ProAudit](https://github.com/EfeObus/TekVwarho-ProAudit)

---

## Acknowledgments

- Nigeria Revenue Service (NRS) for the 2026 Tax Reform framework
- Federal Inland Revenue Service (FIRS) documentation
- Nigerian business community for feedback and validation

---

*Copyright (c) 2026 Tekvwa IT Solutions LTD. All Rights Reserved.*
*Built for Nigerian businesses navigating the new tax landscape.*
# Force redeploy Fri Jan 30 14:39:30 EST 2026
