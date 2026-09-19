# Tekvwa Pro Audit - Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.6.0] - 2026-01-27

### Super Admin Dashboard - Full Platform Management Release

This release delivers a complete Super Admin Dashboard with 31 API endpoints for platform-wide 
management, emergency controls, cross-tenant operations, and health monitoring.

### Added

#### Emergency Controls - Kill Switches (IMPL-001)
- `POST /admin/emergency/platform/read-only` - Toggle platform read-only mode
- `GET /admin/emergency/platform/status` - Get platform emergency status
- `POST /admin/emergency/tenant/{tenant_id}/suspend` - Emergency suspend tenant
- `DELETE /admin/emergency/tenant/{tenant_id}/suspend` - Lift tenant suspension
- `POST /admin/emergency/feature/{feature_name}/disable` - Disable feature globally
- `DELETE /admin/emergency/feature/{feature_name}/disable` - Re-enable feature
- New router: `app/routers/admin_emergency.py` (22KB)

#### Cross-Tenant User Search (IMPL-002)
- `GET /admin/users/search` - Search users across all tenants with filters
- `GET /admin/users/{user_id}` - Get user details
- `GET /admin/users/{user_id}/activity` - Get user activity history
- `POST /admin/users/{user_id}/suspend` - Suspend/unsuspend user
- New router: `app/routers/admin_user_search.py` (9.7KB)
- New service: `app/services/admin_user_search_service.py` (15KB)

#### Platform Staff Management (IMPL-003)
- `GET /admin/staff` - List all platform staff
- `POST /admin/staff` - Create new platform staff
- `GET /admin/staff/{staff_id}` - Get staff details
- `PUT /admin/staff/{staff_id}` - Update staff
- New router: `app/routers/admin_platform_staff.py` (17.5KB)
- New service: `app/services/staff_management_service.py` (22KB)

#### Organization Verification Workflow (IMPL-004)
- `GET /admin/verifications` - List pending verifications
- `GET /admin/verifications/{org_id}` - Get verification details
- `POST /admin/verifications/{org_id}/approve` - Approve organization
- `POST /admin/verifications/{org_id}/reject` - Reject organization
- New router: `app/routers/admin_verification.py` (17KB)

#### Global Audit Log Viewer (IMPL-005)
- `GET /admin/audit-logs` - List all audit logs (paginated)
- `GET /admin/audit-logs/stats` - Get audit statistics
- `GET /admin/audit-logs/{log_id}` - Get specific log details
- `GET /admin/audit-logs/export` - Export audit logs (CSV/JSON)
- New router: `app/routers/admin_audit_logs.py` (12.2KB)
- New service: `app/services/admin_audit_log_service.py` (21KB)

#### Platform Health Metrics (IMPL-006)
- `GET /admin/health` - Overall platform health
- `GET /admin/health/database` - Database health metrics
- `GET /admin/health/services` - External service status
- `GET /admin/health/metrics` - Detailed system metrics
- `GET /admin/health/tenants/summary` - Tenant health summary
- `GET /admin/health/alerts` - Active platform alerts
- New router: `app/routers/admin_health.py` (5.6KB)
- New service: `app/services/admin_health_service.py` (21KB)

#### Admin Tenant Management
- `GET /admin/tenants` - List all tenants with filters
- `GET /admin/tenants/{tenant_id}` - Get tenant details
- `PUT /admin/tenants/{tenant_id}` - Update tenant
- Router: `app/routers/admin_tenants.py` (14.7KB)

#### Admin SKU/Billing Management
- Router: `app/routers/admin_sku.py` (34.4KB)
- Platform-level SKU configuration

### Fixed

#### Bug Fix in admin_tenants.py
- Fixed references to non-existent Organization model fields
- `Organization.is_active` → `not Organization.is_emergency_suspended`
- `Organization.contact_email` → `Organization.email`
- `Organization.suspended_reason` → `Organization.emergency_suspension_reason`
- `Organization.suspended_at` → `Organization.emergency_suspended_at`

### Documentation Updated
- `SUPER_ADMIN_IMPLEMENTATION_ROADMAP.md` - Updated with implementation status
- `TECHNICAL_ARCHITECTURE.md` - Added Super Admin API endpoints (v2.2)
- `SECURITY_ARCHITECTURE.md` - Added platform security controls
- `RBAC_DOCUMENTATION.md` - Added Super Admin dashboard endpoints (v2.2)
- `BUILD_PROGRESS.md` - Added Super Admin section (v2.3.0)

### Test Results
- **31/31 Super Admin endpoints passing** (100% pass rate)
- New audit script: `scripts/audit_super_admin.py`
- All endpoints tested with live database

---

## [2.5.0] - 2026-01-22

### Commercial SKU System & Multi-Tier Monetization Release

This release introduces a comprehensive SKU (Stock Keeping Unit) system for commercial deployment, 
enabling tiered pricing, feature gating, usage metering, and subscription management for the 
Nigerian market.

### Added

#### Commercial Pricing Structure (Nigerian Naira)
- **Core Tier**: ₦25,000 - ₦75,000/month (Small businesses, 1-5 users)
- **Professional Tier**: ₦150,000 - ₦400,000/month (Growing SMEs, 5-25 users)
- **Enterprise Tier**: ₦1,000,000 - ₦5,000,000+/month (Multi-national corporations)
- **Intelligence Add-on**: ₦250,000 - ₦1,000,000/month (ML/AI features)

#### Database Models & Tables
- `sku_pricing` - Tier pricing configuration with NGN currency support
- `tenant_skus` - Organization subscription assignments with trial support
- `usage_records` - Monthly usage tracking per metric type
- `usage_events` - Granular usage event logging
- `feature_access_logs` - Feature access audit trail with denial reasons
- `payment_transactions` - **NEW** Complete payment tracking table:
  - Paystack identifiers (reference, access_code, authorization_url)
  - Transaction details (status, amount_kobo, currency, fees)
  - SKU context (tier, billing_cycle, intelligence_addon)
  - Payment method info (card_type, last4, bank_name)
  - Timestamps (initiated_at, completed_at, webhook_received_at)
  - Full Paystack response storage (JSON)
  - Webhook idempotency tracking (webhook_event_id)

#### SKU Configuration (`app/config/sku_config.py`)
- `SKUTier` enum: CORE, PROFESSIONAL, ENTERPRISE
- `IntelligenceAddon` enum: STANDARD, ADVANCED
- `Feature` enum: 40+ feature flags for gating
- `TierPricing` dataclass with monthly/annual pricing
- `TierLimits` dataclass with usage limits per tier
- `TIER_FEATURES_CONFIG` - Feature sets per tier

#### Paystack Configuration (`app/config.py`)
- `PAYSTACK_SECRET_KEY` - API authentication (sk_test_* or sk_live_*)
- `PAYSTACK_PUBLIC_KEY` - Frontend checkout integration
- `PAYSTACK_WEBHOOK_SECRET` - Webhook signature verification
- `PAYSTACK_BASE_URL` - API base URL (default: https://api.paystack.co)
- `paystack_headers` property - Pre-built auth headers
- `paystack_is_live` property - Live vs test mode detection

#### Billing Service (`app/services/billing_service.py`)
- **PaystackProvider class** - Production-ready API integration
  - `initialize_payment()` - Initialize transaction with Paystack
  - `verify_payment()` - Verify transaction status
  - `create_subscription()` - Create recurring subscription
  - `cancel_subscription()` - Disable subscription
  - `refund_payment()` - Full/partial refunds
  - `get_transaction()` - Fetch transaction details
  - `list_transactions()` - List all transactions
  - `resolve_account()` - Bank account resolution
- Real httpx async HTTP client (not stub mode)
- Automatic retry and timeout handling
- Graceful fallback to stub mode when credentials missing
- Subscription price calculation (monthly/annual with 20% discount)
- Payment reference generation (TVP-{org}-{timestamp} format)
- Nigerian Naira formatting utilities

#### Billing API (`app/routers/billing.py`)
- `GET /api/v1/billing/pricing` - Get tier pricing (Core, Professional, Enterprise)
- `GET /api/v1/billing/subscription` - Current organization subscription
- `POST /api/v1/billing/checkout` - Create payment intent, returns Paystack URL
- `GET /api/v1/billing/payments` - Payment history (paginated, filterable)
- `GET /api/v1/billing/payments/{id}` - Single payment details
- `POST /api/v1/billing/webhook/paystack` - Secured webhook handler

#### Webhook Security (`app/routers/billing.py`)
- `verify_paystack_signature()` - HMAC-SHA512 verification
- Constant-time comparison (prevents timing attacks)
- Returns HTTP 400 for invalid signatures
- Logs security warnings in production without secret

#### Usage Alert Service (`app/services/usage_alert_service.py`)
- Alert thresholds: WARNING (80%), CRITICAL (90%), EXCEEDED (100%)
- Multi-channel notifications: EMAIL, IN_APP, WEBHOOK
- Configurable alert preferences per organization

#### SKU Middleware (`app/middleware/sku_middleware.py`)
- `SKUFeatureMiddleware` - Automatic feature gating based on tenant tier
- `SKUContextMiddleware` - Injects SKU context into requests

#### Self-Service Upgrade Flow
- `templates/checkout.html` - Multi-step checkout with Alpine.js
  - Step 1: Plan selection (Core/Professional/Enterprise)
  - Step 2: Billing cycle (Monthly/Annual with 15% discount)
  - Step 3: Intelligence add-on upsell
  - Step 4: Additional users configuration
- `templates/payment_success.html` - Success page with confetti animation
- `templates/payment_failed.html` - Failure page with retry options
- `static/js/upgrade-modal.js` - Global upgrade prompt component

#### Unit Tests (`tests/test_sku_system.py`)
- 35 comprehensive tests covering:
  - Feature flag configuration
  - TenantSKU model operations
  - Billing service pricing calculations
  - Usage alert thresholds
  - Tier limits enforcement
  - Nigerian Naira price formatting

#### Paystack Tests (`tests/test_paystack_provider.py`)
- 25 comprehensive tests covering:
  - Webhook signature verification (valid, invalid, tampered)
  - PaystackProvider stub mode
  - PaystackProvider real mode (mocked httpx)
  - API timeout and network error handling
  - BillingService pricing calculations
  - PaymentTransaction model properties
  - Integration tests with mocked database

#### Documentation
- `docs/PAYMENT_MODULE_DOCUMENTATION.md` - Comprehensive payment documentation:
  - Architecture diagrams and component overview
  - Configuration and environment variables
  - Complete payment flow with sequence diagrams
  - All API endpoints with request/response examples
  - Database model schema and amount handling
  - Security best practices and webhook verification
  - Nigerian Naira pricing tiers
  - Error handling and troubleshooting
  - Testing guide with mocking examples
  - Production deployment checklist

### Changed
- `app/models/audit_consolidated.py` - Made `entity_id` and `user_id` nullable for system-level audit events
- `app/routers/auth.py` - Fixed login audit logging to use `datetime.utcnow()` instead of missing `_now()` method
- `app/services/auth_service.py` - Registration now creates 14-day trial `TenantSKU` automatically

### Fixed
- `test_login_success` - Fixed `AttributeError: 'AuthService' object has no attribute '_now'`
- `test_login_wrong_password` - Fixed `NotNullViolationError` for `entity_id` in audit_logs

### Technical Details
- All 493 tests passing (3 skipped) - 25 new payment tests
- Paystack integration **production-ready** (real API calls, not stubs)
- 20% annual discount calculated automatically
- Usage metering for transactions, invoices, API calls, storage, users
- Feature access logged with denial reasons for upgrade prompts
- Webhook signature verification with HMAC-SHA512
- Payment transactions stored with full audit trail
- Alembic migration: `20260122_1920_add_payment_transactions.py`

### Documentation
- `docs/COMMERCIAL_SKU_STRUCTURE.md` - Comprehensive SKU documentation (551 lines)
- Updated `.env` with Paystack configuration section

---

## [2.4.1] - 2026-01-18

### Frontend Implementations for Backend Features

This release adds complete frontend implementations for intercompany transactions
and GL-Bank linkage validation features that were previously API-only.

### Added

#### Intercompany Transactions UI (`templates/accounting.html`)
- **New "Intercompany" tab** in the accounting module
- Summary cards: Total Transactions, Total Volume, Uneliminated Amount
- Transaction list with filtering (show/hide eliminated)
- Create intercompany transaction modal:
  - Entity group selection
  - From/To entity selection with validation
  - Transaction type: Sale, Purchase, Loan, Dividend, Management Fee
  - Amount, currency, date, and description fields
- Single transaction elimination with confirmation
- Bulk elimination for consolidation preparation
- Elimination progress bar with percentage
- Entity balance summary by transaction type
- Right panel showing group selection and balance breakdown

#### GL-Bank Linkage Validation UI (`templates/bank_reconciliation.html`)
- **New "GL Linkage" button** in header toolbar
- GL Linkage Validation modal with:
  - Summary cards: Total Accounts, Properly Linked, Unlinked, Invalid
  - All-green validation status indicator
  - Issues list with issue type and resolution actions
  - Properly linked accounts table with GL codes
  - Recommendations section
- Link GL Account dialog:
  - Shows bank account details
  - GL account code input field
  - Quick select buttons for Nigerian Standard COA (1120, 1121, 1122, 1123)
- Automatic refresh after linking
- Integration with `/api/v1/entities/bank-reconciliation/gl-linkage/validate-all`
- Integration with `/api/v1/entities/bank-reconciliation/accounts/{id}/link-gl`

### Technical Details

#### accounting.html Changes
- Added `intercompany` tab button with building icon
- Added state variables: `entityGroups`, `groupEntities`, `selectedGroupId`, `intercompanyTransactions`, `intercompanySummary`, `showIntercompanyModal`, `intercompanyFilters`, `intercompanyForm`, `entityNameCache`
- Added loading state `loading.intercompany`
- Added methods: `loadEntityGroups()`, `loadIntercompanyData()`, `loadGroupEntities()`, `loadIntercompanyTransactions()`, `loadIntercompanySummary()`, `getEntityName()`, `createIntercompanyTransaction()`, `markForElimination()`, `bulkEliminate()`, `viewIntercompanyDetails()`, `resetIntercompanyForm()`

#### bank_reconciliation.html Changes
- Added GL Linkage button with shield icon
- Added modals: `showGLLinkageModal`, `showLinkGLModal`
- Added state: `validatingGLLinkage`, `linkingGL`, `glLinkageResult`, `linkGLForm`
- Added methods: `validateAllGLLinkages()`, `showLinkGLDialog()`, `linkGLAccount()`, `validateSingleGLLinkage()`

### Tests
- All 433 tests passing
- 3 tests skipped (expected)

---

## [2.4.0] - 2026-01-19

### Enhanced Financial Reporting & Period Controls Release

This release adds comprehensive financial reporting UI, intercompany transaction management,
and enhanced period lock enforcement for audit compliance.

### Added

#### Financial Reports UI Enhancements (`templates/accounting.html`)
- **Cash Flow Statement Report UI**
  - Full indirect method display with Operating, Investing, Financing sections
  - Net income adjustments and working capital changes breakdown
  - Beginning/ending cash summary with net change calculation
  - Color-coded sections for easy identification

- **AR/AP Aging Reports UI**
  - Integrated accounts receivable aging with GL reconciliation
  - Integrated accounts payable aging with GL reconciliation
  - Visual aging buckets: Current, 1-30, 31-60, 61-90, Over 90 days
  - Summary cards showing total outstanding, overdue %, and GL balance
  - Automated recommendations based on aging analysis

#### Intercompany Transaction API (`app/routers/advanced_accounting.py`)
- `POST /api/v1/advanced/intercompany` - Create intercompany transaction
- `GET /api/v1/advanced/intercompany` - List intercompany transactions with filters
- `POST /api/v1/advanced/intercompany/eliminate` - Mark transactions for consolidation elimination
- `GET /api/v1/advanced/intercompany/summary` - Get intercompany balance summary by group
- New schemas: `IntercompanyTransactionCreate`, `IntercompanyTransactionResponse`, `IntercompanyEliminationRequest`

#### Period Lock Hard Enforcement (`app/services/accounting_service.py`)
- Enhanced `create_journal_entry()` with explicit LOCKED period validation
- Enhanced `post_journal_entry()` with explicit LOCKED period validation
- Enhanced `reverse_journal_entry()` with explicit LOCKED period validation
- Clear error messages distinguishing LOCKED vs CLOSED vs non-existent periods:
  - LOCKED: "Period has been permanently locked and no further entries are allowed"
  - CLOSED: "Reopen the period or use a different date"

### Changed
- Report type selector now includes 6 options: Trial Balance, Income Statement, Balance Sheet, Cash Flow Statement, AR Aging, AP Aging
- Date filter inputs dynamically show/hide based on selected report type

### Technical Details
- All 433 tests pass
- No database migrations required (using existing models)
- Backward compatible with existing accounting.html functionality

---

## [2.3.0] - 2026-01-19

### Complete GL Integration Release

This release completes the integration between all sub-ledger modules and the General Ledger,
ensuring "every naira in the bank is explained."

### Added

#### Sub-Ledger to GL Posting Integration
All sub-ledger modules now automatically post to the General Ledger:

- **Invoice GL Posting** (`app/services/invoice_service.py`)
  - `finalize_invoice()` now posts: Dr AR, Cr Revenue, Cr VAT Payable
  - `record_payment()` now posts: Dr Bank, Dr WHT Receivable, Cr AR
  - New method: `_post_invoice_to_gl()`, `_post_payment_to_gl()`

- **Vendor/Expense GL Posting** (`app/services/transaction_service.py`)
  - `create_transaction()` now posts expenses: Dr Expense, Dr VAT Input, Cr AP
  - New method: `record_vendor_payment()` with GL posting
  - New method: `_post_expense_to_gl()`, `_post_income_to_gl()`

- **Payroll GL Posting** (`app/services/payroll_service.py`)
  - `process_payroll()` now posts full Nigerian payroll journal
  - Journal includes: Salary, Pension (8%/10%), NHF (2.5%), NSITF (1%), PAYE
  - New method: `_post_payroll_to_gl()`

- **Fixed Asset GL Posting** (`app/services/fixed_asset_service.py`)
  - `run_depreciation()` now posts: Dr Depreciation Expense, Cr Accumulated Depreciation
  - `dispose_asset()` now posts disposal with gain/loss calculation
  - New methods: `_post_depreciation_to_gl()`, `_post_disposal_to_gl()`

- **Inventory GL Posting** (`app/services/inventory_service.py`)
  - `record_sale()` now posts COGS: Dr COGS, Cr Inventory
  - `create_write_off()` now posts: Dr Write-off Expense, Cr Inventory
  - New methods: `_post_cogs_to_gl()`, `_post_writeoff_to_gl()`

#### Cash Flow Statement Report
- New endpoint: `GET /api/v1/entities/{entity_id}/accounting/reports/cash-flow-statement`
- Implements indirect method with Operating, Investing, Financing activities
- Service method: `accounting_service.get_cash_flow_statement()`
- New schemas: `CashFlowStatementReport`, `CashFlowItem`, `CashFlowCategory`

#### Bank-GL Integration
- **GL Linkage Validation**
  - `GET /accounts/{id}/gl-linkage` - Validate single bank account GL linkage
  - `GET /gl-linkage/validate-all` - Validate all bank accounts
  - `POST /accounts/{id}/link-gl` - Link bank account to GL account

- **GL Transaction Matching**
  - `GET /reconciliations/{id}/gl-transactions` - Get GL entries for bank account
  - `POST /reconciliations/{id}/match-to-gl` - Match statement to GL entry
  - `POST /reconciliations/{id}/auto-match-gl` - Auto-match to GL entries
  - New service methods: `get_gl_transactions_for_bank()`, `match_statement_to_gl()`, `auto_match_to_gl()`

### Changed

- All GL posting methods include `post_to_gl: bool = True` parameter for optional bypass
- Updated documentation in `docs/COMPLETE_ACCOUNTING_SYSTEM.md` with GL integration details
- Added GL Account Codes Reference table to documentation

### Technical Details

- All GL posting uses `AccountingService.post_to_gl()` as the integration point
- Nigerian Standard COA codes used consistently (1xxx Assets, 2xxx Liabilities, etc.)
- GL postings respect fiscal period locks via `get_open_period_for_date()`
- 433 tests passing (3 skipped)

---

## [2.2.0] - 2026-01-07

### System Audit & Module Expansion Release

This release addresses findings from comprehensive 17-phase system audit and adds critical missing modules.

### Fixed

#### Critical Bug Fixes
- **Tax Intelligence Decimal Error**: Fixed `decimal.InvalidOperation` in `tax_intelligence.py` line 97
  - Changed `Decimal("float('inf')")` to `Decimal("999999999999")` (effectively infinite for tax bracket calculations)
  - This was causing crashes during tax analysis operations

- **Model Relationship Integrity**: Fixed missing ORM relationships between models
  - Added `Employee.entity` relationship with `back_populates="employees"`
  - Added `PayrollRun.entity` relationship with `back_populates="payroll_runs"`
  - Added `BusinessEntity.employees` and `BusinessEntity.payroll_runs` inverse relationships
  - Ensures proper cascade operations and ORM navigation

### Added

#### NRS Integration Router (`app/routers/nrs.py`)
Complete Nigerian Revenue Service (NRS) integration API:
- `POST /api/v1/nrs/invoices/submit` - Submit invoice for IRN generation
- `GET /api/v1/nrs/invoices/{irn}/status` - Check invoice IRN status
- `POST /api/v1/nrs/tin/validate` - Validate single TIN
- `POST /api/v1/nrs/tin/validate/bulk` - Bulk TIN validation (up to 100)
- `POST /api/v1/nrs/disputes/submit` - Submit buyer dispute for invoice
- `POST /api/v1/nrs/b2c/report` - B2C transaction reporting (2026 compliance)
- `GET /api/v1/nrs/b2c/status` - Check B2C reporting status
- `GET /api/v1/nrs/health` - NRS API health check

#### Bank Reconciliation Module
Complete bank account reconciliation system for Nigerian businesses:
- **Models** (`app/models/bank_reconciliation.py`):
  - `BankAccount` - Bank account management with CBN bank codes
  - `BankStatement` - Statement import tracking
  - `BankStatementTransaction` - Individual transaction records
  - `BankReconciliation` - Reconciliation workflow state
- **Service** (`app/services/bank_reconciliation_service.py`):
  - Bank account CRUD operations
  - Statement import with transaction parsing (CSV/OFX/PDF)
  - Auto-matching using fuzzy logic (amount + date + description)
  - Manual matching/unmatching capabilities
  - Full reconciliation workflow (create → adjust → complete → approve)
  - Summary statistics and analytics
- **Router** (`app/routers/bank_reconciliation.py`):
  - Complete REST API for all bank reconciliation operations
  - Entity-scoped endpoints with authentication

#### Expense Claims Module
Employee expense claim management with approval workflow:
- **Models** (`app/models/expense_claims.py`):
  - `ExpenseClaim` - Main claim with workflow status
  - `ExpenseClaimItem` - Individual expense line items
  - 12 expense categories (Travel, Accommodation, Meals, etc.)
  - Nigerian compliance fields (is_tax_deductible, gl_account_code)
- **Service** (`app/services/expense_claims_service.py`):
  - Expense claim CRUD with line items
  - Multi-level approval/rejection workflow
  - Payment tracking and status updates
  - Summary statistics and category breakdown
- **Router** (`app/routers/expense_claims.py`):
  - Complete REST API for expense claims management
  - Entity-scoped endpoints with authentication

### New Files
- `app/routers/nrs.py` - NRS integration router (~500 lines)
- `app/models/bank_reconciliation.py` - Bank reconciliation models (~200 lines)
- `app/services/bank_reconciliation_service.py` - Bank reconciliation service (~400 lines)
- `app/routers/bank_reconciliation.py` - Bank reconciliation API router (~300 lines)
- `app/models/expense_claims.py` - Expense claims models (~150 lines)
- `app/services/expense_claims_service.py` - Expense claims service (~300 lines)
- `app/routers/expense_claims.py` - Expense claims API router (~250 lines)

### Changed
- `app/services/tax_intelligence.py` - Fixed Decimal infinity bug
- `app/models/entity.py` - Added employees and payroll_runs relationships
- `app/models/payroll.py` - Added entity relationship to Employee and PayrollRun
- `main.py` - Registered new routers (nrs, bank_reconciliation, expense_claims)

### Verified
- **433 tests passing** (3 skipped, 74 warnings)
- **648+ total routes** (including new NRS and module routes)
- All new modules import and integrate correctly
- Full frontend-backend integration maintained

---

## [2.1.0] - 2026-01-06

### Security & Compliance Suite (NDPA/NITDA 2023)

This release introduces comprehensive enterprise security and Nigerian Data Protection Act compliance.

### Added

#### Data Privacy & Encryption
- **PII Encryption Engine**: AES-256-GCM field-level encryption for sensitive data (BVN, NIN, RSA PIN, bank accounts)
- **PIIMasker Utility**: Display-safe masking for all 14 PII categories
- **Key Rotation Support**: Versioned key management for security updates
- **Right-to-Erasure Service**: NDPA Article 36 compliance with statutory retention validation

#### Network & Access Security
- **Geo-Fencing Middleware**: Nigerian IP range enforcement (AFRINIC allocations)
- **Rate Limiting**: Per-endpoint protection (Login 5/min, Register 3/min, Tax calculators 30/min, NRS 10/min)
- **Account Lockout**: Progressive lockout (1min → 5min → 15min → 1hr → 24hr after 5 failed attempts)

#### Web Application Security
- **CSRF Protection**: Double-submit cookie pattern with HTMX integration
- **Content Security Policy**: Strict CSP headers with NRS/NIBSS trusted sources
- **Security Headers**: X-Frame-Options DENY, HSTS, X-Content-Type-Options nosniff

#### Nigerian Validators
- `validate_nigerian_tin`: FIRS TIN format (10 characters)
- `validate_nigerian_bvn`: BVN format (11 digits)
- `validate_nigerian_nin`: NIN format (11 digits)
- `validate_nigerian_phone`: Nigerian phone (+234/0 prefix)
- `validate_nigerian_account`: NUBAN account (10 digits)

### New Files
- `app/utils/ndpa_security.py` - NDPA security utilities (~700 lines)
- `app/middleware/security.py` - Security middleware stack (~500 lines)
- `app/middleware/__init__.py` - Middleware package exports
- `docs/SECURITY_ARCHITECTURE.md` - Comprehensive security documentation
- `docs/SYSTEM_AUDIT_REPORT.md` - System audit and verification report

### Changed
- `templates/base.html` - Added CSRF token JavaScript for HTMX
- `templates/reports.html` - Fixed self-assessment API endpoint path
- `main.py` - Integrated security middleware stack
- `app/routers/auth.py` - Integrated AccountLockoutManager in login endpoint

### Verified
- **313 tests passing** (3 skipped)
- **527 total routes** (471 API, 52 view routes)
- **84 database model exports**
- Complete frontend-backend integration verified

---

## [2.0.0] - 2026-01-06

### Business Intelligence & Executive Compensation Suite

This major release introduces advanced business intelligence features for Nigerian tax compliance.

### Added

#### BIK (Benefit-in-Kind) Automator
- Vehicle BIK calculation (5% of cost + 25% for private use)
- Accommodation benefit (7.5% rental, 15% owned of annual salary)
- Driver benefit (₦600,000/year flat rate)
- Domestic staff benefit (₦500,000/year per staff)
- PAYE calculation on BIK using 2026 tax brackets

#### NIBSS Pension Direct-Debit Generation
- NIBSS NIP Bulk Payment XML format
- All 20+ licensed PFAs supported
- RSA PIN validation (PEN + 12 digits format)
- CSV export alternative

#### Growth Radar & Tax Threshold Alerts
- Threshold proximity analysis (₦25M, ₦100M)
- Growth projection from historical data
- Tax bracket transition planning

#### Stock Write-off VAT Workflow
- 9 write-off reasons supported
- VAT input adjustment calculation (7.5%)
- Approval workflow integration

#### Multi-Location Inventory Transfers
- 7 transfer types supported
- Interstate levy calculation (0.5%)
- All 37 Nigerian states + FCT supported

---

## [1.9.0] - 2026-01-06

### Payroll System with Nigerian 2026 Tax Reform Compliance

This major release introduces a comprehensive payroll management system with full Nigerian tax compliance, including the 2026 Tax Reform PAYE changes.

### Added

#### Payroll Core System
- **Payroll Service**: `app/services/payroll_service.py` - Complete payroll calculation engine (1,295 lines)
- **Payroll Models**: `app/models/payroll.py` - Enhanced SQLAlchemy models for all payroll entities
- **Payroll Schemas**: `app/schemas/payroll.py` - Pydantic schemas for API request/response validation
- **Payroll Router**: `app/routers/payroll.py` - 20 REST API endpoints for payroll management
- **Payroll Views**: `app/routers/payroll_views.py` - HTML page routes for frontend

#### Nigerian 2026 Tax Reform PAYE Compliance
- **New Tax-Free Threshold**: ₦800,000 annual (increased from ₦300,000)
- **Progressive PAYE Bands**:
  - ₦0 - ₦800,000: 0% (Exempt)
  - ₦800,001 - ₦2,400,000: 15%
  - ₦2,400,001 - ₦4,800,000: 20%
  - ₦4,800,001 - ₦7,200,000: 25%
  - Above ₦7,200,000: 30%
- **Consolidated Relief Allowance (CRA)**: ₦200,000 + 20% of Gross Income
- **2026 Rent Relief**: 20% of annual rent paid (max ₦500,000/year)
- **Life Insurance Premium Relief**: Monthly premiums (max ₦250,000/year)

#### Statutory Deductions & Contributions
- **Employee Pension**: 8% of pensionable earnings (Basic + Housing + Transport)
- **Employer Pension**: 10% of pensionable earnings
- **NHF**: 2.5% of basic salary for qualifying employees
- **NSITF**: 1% employer contribution
- **ITF**: 1% employer contribution for qualifying organizations

#### Employee Management
- Full employee records with Nigerian compliance fields (NIN, BVN, TIN, Tax State)
- Multiple bank accounts per employee with primary designation
- All 20 licensed Nigerian PFAs supported
- Department and job grade classification
- Leave entitlement and balance tracking

#### Payroll Processing
- Payroll run management (monthly, bi-weekly, weekly)
- Automated gross/deductions/net calculation
- Approval workflow: Draft → Pending Approval → Approved → Processing → Paid
- Bank schedule generation for payment file uploads
- Payslip generation with itemized earnings and deductions

#### Remittance Tracking
- PAYE remittance tracking by state tax authority
- Pension remittance to PFAs
- NHF, NSITF, ITF remittance management
- Due date tracking and payment recording

#### Loan Management
- Employee loans and salary advances
- Configurable repayment schedules
- Automatic payroll deduction integration
- Loan balance tracking

#### Leave Management
- Leave request and approval workflow
- Multiple leave types (annual, sick, maternity, paternity, etc.)
- Leave balance tracking

#### Frontend Templates
- **Main Payroll Page**: `templates/payroll.html` - Dashboard with 5 tabs (841 lines)
- **Employee Modal**: `templates/partials/payroll/employee_modal.html`
- **Run Payroll Modal**: `templates/partials/payroll/run_payroll_modal.html`
- **Salary Calculator Modal**: `templates/partials/payroll/salary_calculator_modal.html`
- **Payslip Modal**: `templates/partials/payroll/payslip_modal.html`
- **Payroll Run Details**: `templates/payroll_run_details.html`
- Navigation updated with Payroll link in `templates/base.html`

#### API Endpoints
- `POST /api/v1/payroll/employees` - Create new employee
- `GET /api/v1/payroll/employees` - List employees with filters
- `GET /api/v1/payroll/employees/{id}` - Get employee details
- `PUT /api/v1/payroll/employees/{id}` - Update employee
- `POST /api/v1/payroll/employees/{id}/bank-accounts` - Add bank account
- `POST /api/v1/payroll/payroll-runs` - Create payroll run
- `GET /api/v1/payroll/payroll-runs` - List payroll runs
- `GET /api/v1/payroll/payroll-runs/{id}` - Get payroll run details
- `POST /api/v1/payroll/payroll-runs/{id}/process` - Process payroll
- `POST /api/v1/payroll/payroll-runs/{id}/approve` - Approve payroll
- `POST /api/v1/payroll/payroll-runs/{id}/mark-paid` - Mark as paid
- `GET /api/v1/payroll/payslips` - List payslips
- `GET /api/v1/payroll/payslips/{id}` - Get payslip details
- `POST /api/v1/payroll/calculate-salary` - Calculate salary breakdown
- `GET /api/v1/payroll/remittances` - List statutory remittances
- `PUT /api/v1/payroll/remittances/{id}` - Update remittance status
- `GET /api/v1/payroll/bank-schedule/{run_id}` - Generate bank schedule
- `GET /api/v1/payroll/dashboard` - Get payroll dashboard stats
- `GET /api/v1/payroll/departments` - List departments

#### Database Migration
- **Migration**: `alembic/versions/20260106_1600_add_payroll_system.py` (489 lines)
- **Tables Created**:
  - `employees` - Employee master records with comprehensive fields
  - `employee_bank_accounts` - Bank account details with Nigerian banks
  - `payroll_runs` - Payroll batch processing records
  - `payslips` - Individual employee payslips
  - `payslip_items` - Earnings and deduction line items
  - `statutory_remittances` - PAYE, pension, NHF tracking
  - `employee_loans` - Loan and advance management
  - `loan_repayments` - Loan repayment history
  - `employee_leaves` - Leave requests and approvals
  - `payroll_settings` - Entity-level payroll configuration
- **Enums Created**: EmploymentType, EmploymentStatus, PayrollFrequency, BankName, PayrollStatus, PayItemType, PayItemCategory, LoanType, LoanStatus, LeaveType, LeaveStatus, PensionFundAdministrator

### Fixed

- **Fixed**: `ForwardRef('UploadFile')` error in `transactions.py` - Added proper `UploadFile` import from FastAPI
- **Fixed**: Duplicate index creation in payroll migration - Removed redundant `op.create_index()` calls for columns with `index=True`
- **Added**: `get_current_entity_id` dependency function in `app/dependencies.py` for cookie-based entity selection

### Dependencies

- **New Dependency**: `get_current_entity_id` - Retrieves current entity from cookie or user's first accessible entity

---

## [1.8.0] - 2026-01-06

### Nigeria Address Fields & Email Verification

This release adds comprehensive Nigerian state/LGA address selection and enhanced email verification for user registration.

### Added

#### Nigeria States & LGAs API
- **New API**: `GET /api/v1/auth/nigeria/states` - Returns all 37 Nigerian states (36 states + FCT)
- **New API**: `GET /api/v1/auth/nigeria/states/{state}/lgas` - Returns LGAs for a specific state
- **New Module**: `app/utils/nigeria_data.py` - Complete authoritative data for all 774 Nigerian LGAs
- Helper functions: `get_all_states()`, `get_lgas_by_state()`, `validate_state_lga()`, `get_state_count()`, `get_total_lga_count()`

#### Registration Flow Improvements
- **LGA Dropdown**: Dynamic LGA selection based on chosen state in registration form
- **State Validation**: All 37 Nigerian states available in dropdown
- **UI Enhancement**: LGA dropdown loads automatically when state is selected
- **Form Validation**: LGA is now required for registration

#### Email Verification Enhancements
- **New Field**: `email_verification_token` - Stored in database for verification tracking
- **New Field**: `email_verification_sent_at` - Timestamp when verification email was sent
- **New Field**: `email_verified_at` - Timestamp when email was verified
- **New Field**: `is_invited_user` - Boolean to distinguish invited users from self-registered
- Invited users are pre-verified (admin vouches for them)
- Self-registered users must verify email

#### Database Migration
- **Migration**: `20260106_1400_add_lga_email_verification.py`
- Added `lga` column to `business_entities` table
- Added email verification fields to `users` table
- Created index on `email_verification_token` for efficient lookups

### Fixed

- **Fixed**: Missing `Path` import in `self_assessment.py` - Changed `Query` to `Path` for path parameter validation
- **Fixed**: Missing `verify_entity_access` function - Added to `app/dependencies.py` as shared function
- **Fixed**: Missing `BaseModel` and `Query` imports in `auth.py`
- **Centralized**: `verify_entity_access` function now shared from dependencies module

---

## [1.7.1] - 2026-01-04

### Comprehensive Routes & Database Audit

This release includes a full audit of all API routes, endpoints, database migrations, and comprehensive documentation updates.

### Fixed

#### Database Migration Chain
- **Fixed**: Migration `20260104_0930_add_must_reset_password.py` - Corrected `down_revision` from `20260103_1700_add_missing_2026_columns` to `20260103_1700_add_missing_columns`
- **Fixed**: Migration `20260104_1500_sync_models_with_db.py` - Added enum existence checks to prevent duplicate type creation errors
- Successfully ran all pending migrations: `20260104_0930`, `20260104_1054`, `20260104_1500_sync_models_with_db`

#### Database Sync Migration
- **New Migration**: `20260104_1500_sync_models_with_db.py` - Syncs all model definitions with database
- **New Table**: `notifications` with all 17+ columns for compliance alerts
- **New Columns in transactions**: `wht_amount`, `wht_service_type`, `wht_payee_type`
- **New Columns in invoices**: `is_b2c_reportable`, `b2c_reported_at`, `b2c_report_reference`, `b2c_report_deadline`
- **New Columns in fixed_assets**: `department`, `assigned_to`, `warranty_expiry`, `notes`, `asset_metadata`

### Audited

#### All 18 Routers Verified
| Router | Prefix | Endpoints | Status |
|--------|--------|-----------|--------|
| auth.py | /api/v1/auth | 10 endpoints | Verified |
| audit.py | /api/v1/entities/{entity_id}/audit | 12 endpoints | Verified |
| categories.py | /api/v1/entities | 3 endpoints | Verified |
| customers.py | /api/v1/entities | 5 endpoints | Verified |
| entities.py | /api/v1/entities | 5 endpoints | Verified |
| fixed_assets.py | /api/v1/fixed-assets | 10 endpoints | Verified |
| inventory.py | /api/v1/entities | 15+ endpoints | Verified |
| invoices.py | /api/v1/entities | 12+ endpoints | Verified |
| organization_users.py | /api/v1/organizations | 8 endpoints | Verified |
| receipts.py | /api/v1/entities | 5+ endpoints | Verified |
| reports.py | /api/v1/entities | 15+ endpoints | Verified |
| sales.py | /api/v1/entities | 8+ endpoints | Verified |
| staff.py | /api/v1/staff | 10+ endpoints | Verified |
| tax.py | /api/v1/tax | 10+ endpoints | Verified |
| tax_2026.py | /api/v1/tax-2026 | 30+ endpoints | Verified |
| transactions.py | /api/v1/entities | 6 endpoints | Verified |
| vendors.py | /api/v1/entities | 6 endpoints | Verified |
| views.py | / (HTML) | 15+ pages | Verified |

### Test Results
- **313 tests passing**
- **3 skipped** (optional features)
- All routes and endpoints match backend implementations

---

## [1.7.0] - 2026-01-04

### Compliance Health & Threshold Monitoring

This release adds dedicated compliance health API endpoints with real-time threshold monitoring for 2026 Nigeria Tax Reform compliance.

### Added

#### Compliance Health API Endpoints
- **New Endpoint**: `GET /{entity_id}/reports/compliance-health` - Real-time compliance score with automated threshold monitoring
- **New Endpoint**: `GET /{entity_id}/reports/compliance-health/thresholds` - Current threshold status for all compliance metrics
- **New Endpoint**: `GET /{entity_id}/reports/compliance-health/alerts` - Compliance threshold alerts by severity
- **New Endpoint**: `POST /{entity_id}/reports/compliance-health/subscribe` - Subscribe to compliance threshold notifications

#### ComplianceHealthService
- **New Service**: `app/services/compliance_health_service.py` - Dedicated service for compliance monitoring
- Real-time compliance score calculation (0-100%)
- 6 comprehensive compliance checks:
  - TIN Registration (required for NRS)
  - CAC Registration
  - Small Company Status (0% CIT: Turnover ≤₦50M, Assets ≤₦250M)
  - Development Levy Exemption (Turnover ≤₦100M, Assets ≤₦250M)
  - VAT Registration (₦25M threshold)
  - NRS e-Invoicing Readiness

#### Threshold Monitoring Features
- Automatic alerts at 80% of threshold limits
- Critical alerts for exceeded thresholds
- Warning alerts for approaching thresholds
- Info alerts for status changes
- Headroom calculation (remaining before threshold)
- Percentage usage tracking

#### Compliance Health Tests
- **47 new tests** for compliance health feature:
  - `TestComplianceHealthThresholds` - Threshold value verification
  - `TestComplianceHealthScoring` - Score calculation tests
  - `TestComplianceHealthChecks` - Individual check verification
  - `TestComplianceAlerts` - Alert generation tests
  - `TestComplianceThresholdCalculations` - Percentage and headroom calculations
  - `TestComplianceHealthIntegration` - Integration tests

### 2026 Tax Reform Thresholds Implemented
| Threshold | Value | Purpose |
|-----------|-------|---------|
| VAT Registration | ₦25M annual turnover | Mandatory VAT registration |
| Small Company Turnover | ₦50M | 0% CIT eligibility |
| Small Company Assets | ₦250M | 0% CIT eligibility |
| Development Levy Turnover | ₦100M | 4% levy exemption |
| Development Levy Assets | ₦250M | 4% levy exemption |

### Test Results
- **313 tests passing** (up from 266)
- **3 skipped** (optional features)
- All compliance health tests pass

---

## [1.6.0] - 2026-01-04

### Security & Authentication Enhancements

This release adds comprehensive authentication improvements, email verification, and staff onboarding security features.

### Added

#### Email Verification for Registration
- **New Endpoint**: `POST /api/v1/auth/verify-email` - Verify email with token
- **New Endpoint**: `POST /api/v1/auth/resend-verification` - Resend verification email
- **New Template**: `verify_email.html` - Email verification page
- **New Functions**: `create_email_verification_token()`, `verify_email_verification_token()` in security utils
- **New Method**: `send_verification_email()` in EmailService
- Verification emails sent automatically on registration

#### Staff Onboarding Security
- **New Field**: `must_reset_password` in User model
- Forces newly onboarded staff to reset password on first login
- Automatic redirect to settings page with password reset prompt
- `must_reset_password` flag cleared after successful password change

#### Password Visibility Toggle
- Added eye icon toggle to show/hide password on all auth forms
- Implemented in: login, register, reset_password, forgot_password

#### Global Error Handling
- Added comprehensive exception handlers in main.py
- Handlers for: HTTPException, RequestValidationError, ValidationError, ValueError, PermissionError
- Consistent JSON error responses with proper status codes
- Structured logging for all errors

### Changed

#### Email Service Configuration
- Email service now properly reads from environment variables via settings
- Uses `settings.mail_server`, `settings.mail_port`, `settings.mail_username`, `settings.mail_password`
- Added `base_url` configuration for email links

#### Password Reset Flow
- Password reset emails now use full URLs with base_url
- Verification emails use full URLs with base_url
- URLs default to `http://localhost:5120` for development

### Fixed

- Removed unnecessary emojis from templates (base, sales, tax_2026, dashboard)
- Replaced print statements with proper logging in main.py
- Fixed email service to use correct settings attributes

### Database Migration

- **New Migration**: `20260104_0930_add_must_reset_password.py`
  - Adds `must_reset_password` boolean column to users table

---

## [1.5.0] - 2026-01-04

### Notification System & Background Tasks

This release adds a complete notification system, Celery background tasks, and improved email services.

### Added

#### Notification Model & Service
- **New Model**: `Notification` with 17 notification types
  - Types: Invoice Overdue, Payment Received, Low Stock Alert, VAT/PAYE Deadlines, NRS Success/Failed, Compliance Warning, System Alerts, and more
  - Priority levels: LOW, MEDIUM, HIGH, URGENT
  - Channels: IN_APP, EMAIL, BOTH
  - Relationships to User and BusinessEntity
- **New Service**: `NotificationService` with full CRUD operations
  - `create_notification()` - Create new notifications
  - `get_user_notifications()` - Get with filtering and pagination
  - `get_unread_count()` - Count unread notifications
  - `mark_as_read()` / `mark_all_as_read()` - Mark notifications read
  - Convenience methods: `notify_invoice_overdue()`, `notify_low_stock()`, `notify_vat_reminder()`, etc.

#### Email Service (Multi-Provider)
- **Providers**: SendGrid, Mailgun, SMTP, Mock (for development)
- Auto-selection based on environment configuration
- Error handling with logging
- Template-ready body support

#### Celery Background Tasks
- **New File**: `app/celery_app.py` - Celery configuration
- **New File**: `app/tasks/celery_tasks.py` - Background task implementations
- Redis as message broker and result backend
- Task routing for email, NRS, and default queues
- Beat scheduler with 9 scheduled tasks:
  - `check_overdue_invoices_task` - Daily at 6 AM
  - `check_low_stock_task` - Daily at 7 AM
  - `check_vat_deadlines_task` - Daily at 8 AM
  - `check_paye_deadlines_task` - Daily at 8:30 AM
  - `retry_failed_nrs_submissions_task` - Every 15 minutes
  - `cleanup_old_notifications_task` - Weekly on Sunday
  - `archive_old_audit_logs_task` - Monthly on 1st
  - `generate_monthly_tax_summary_task` - Monthly on 2nd
  - `send_email_task` - Async email sending

#### Dashboard Service Improvements
- `_get_tax_summary()` - Real VAT calculations from transactions
- `_get_inventory_summary()` - Actual inventory statistics with low stock counts
- `_get_recent_errors()` - Error tracking from audit logs
- `_get_recent_nrs_submissions()` - NRS submission history

#### Integration Tests
- **New File**: `tests/test_integration.py`
- Invoice workflow tests
- Notification system tests
- Email service mock tests
- Tax calculator tests (VAT 2026, Development Levy)
- Dashboard service tests
- Celery task tests (mocked)
- Audit logging tests

### Changed
- Updated `docker-compose.yml` with Celery worker and beat commands
- Updated `.env.example` with email provider and Celery configuration
- Updated `app/services/__init__.py` with 45 exports
- Updated `app/schemas/__init__.py` with comprehensive exports
- Updated `app/models/__init__.py` with Notification exports

---

## [1.4.0] - 2026-01-03

### 🇳🇬 2026 Nigeria Tax Reform - Complete Compliance Implementation

This release implements ALL mandatory 2026 Nigeria Tax Reform compliance requirements including TIN Validation, Penalty Tracking, Minimum ETR, CGT at 30%, Peppol BIS Billing 3.0, and Zero-Rated VAT tracking.

### Added

#### TIN Validation Service (NRS Portal Integration)
- **New Service**: `TINValidationService` for real-time TIN validation via https://taxid.nrs.gov.ng/
  - Individual TIN validation via NIN (National Identification Number)
  - Corporate TIN validation (Business Name, Company, Incorporated Trustee, Limited Partnership, LLP)
  - `validate_tin()` - Validate any TIN with format checking
  - `validate_individual_by_nin()` - Validate individual TIN using 11-digit NIN
  - `bulk_validate_tins()` - Bulk validation for multiple TINs
  - `check_vendor_compliance()` - Pre-contract vendor TIN verification with ₦5M penalty warning
  - Sandbox mode simulation for development/testing
  - Caching support for reduced API calls

#### Compliance Penalty Tracker (2026 Penalty Schedule)
- **New Service**: `CompliancePenaltyService` for penalty calculation and tracking
  - `calculate_late_filing_penalty()` - ₦100,000 first month + ₦50,000 subsequent months
  - `calculate_unregistered_vendor_penalty()` - ₦5,000,000 fixed penalty
  - `calculate_b2c_late_reporting_penalty()` - ₦10,000 per transaction (max ₦500,000/day)
  - `calculate_tax_remittance_penalty()` - 10% + 2% monthly interest for VAT/PAYE/WHT
- **New Model**: `PenaltyRecord` for tracking incurred penalties
- Penalty types: Late Filing, Unregistered Vendor, B2C Late Reporting, E-Invoice Non-Compliance, Invalid TIN, Missing Records, NRS Access Denial, VAT/PAYE/WHT Non-Remittance

#### 15% Minimum Effective Tax Rate (ETR) Calculator
- **New Calculator**: `MinimumETRCalculator` for large companies and MNE constituents
  - Applies to companies with turnover >= ₦50 billion
  - Applies to MNE constituents with group revenue >= €750 million
  - Calculates ETR shortfall and top-up tax required
  - `check_minimum_etr_applicability()` - Check if company is subject
  - `calculate_minimum_etr()` - Calculate top-up tax to meet 15% minimum

#### Capital Gains Tax (CGT) at 30% for Large Companies
- **New Calculator**: `CGTCalculator` with 2026 rates
  - CGT rate increased from 10% to 30% for large companies
  - Small company exemption (turnover <= ₦100M AND assets <= ₦250M)
  - Indexation allowance for inflation adjustment
  - `classify_company()` - Determine company classification for CGT
  - `calculate_cgt()` - Full CGT calculation with exemptions

#### Zero-Rated VAT Input Credit Tracker
- **New Tracker**: `ZeroRatedVATTracker` for refund claim management
  - Track zero-rated sales (food, education, healthcare, exports)
  - Track input VAT paid with IRN validation
  - Only purchases with valid NRS IRN are refund-eligible
  - `record_zero_rated_sale()` - Record zero-rated transactions
  - `record_input_vat()` - Record input VAT for potential refund
  - `calculate_refund_claim()` - Calculate total refundable VAT

#### Peppol BIS Billing 3.0 E-Invoice Export
- **New Service**: `PeppolExportService` for structured digital invoice formats
  - UBL 2.1 XML export (Peppol BIS Billing 3.0 compliant)
  - JSON representation for API integration
  - CSID (Cryptographic Stamp Identifier) generation
  - QR code data embedding with invoice verification info
  - `to_ubl_xml()` - Export as UBL 2.1 XML
  - `to_json()` - Export as Peppol JSON
  - `generate_csid()` - Generate cryptographic stamp
  - `generate_qr_code_data()` - Generate QR verification data

### Enhanced

#### Configuration
- Added `nrs_tin_api_url` for TIN validation portal
- Added `nrs_tin_api_key` for separate TIN API authentication

#### Tax Calculators Package
- Exported all new calculators from `tax_calculators/__init__.py`
- Added convenience functions for Minimum ETR and CGT calculations

### Tests

#### New Test Suite: `test_2026_compliance.py`
- TIN validation format tests (10+ tests)
- Penalty calculation tests (late filing, vendor, VAT)
- Minimum ETR threshold and calculation tests
- CGT calculation and exemption tests
- Zero-rated VAT refund eligibility tests
- Peppol export XML and JSON tests

---

## [1.3.0] - 2026-01-03

### 🇳🇬 2026 Nigeria Tax Reform - Full Compliance Update

This release implements comprehensive 2026 Nigeria Tax Reform compliance features including Fixed Asset Register, Enhanced Dashboard with Compliance Health Indicator, and B2C Real-time Reporting.

### Added

#### Fixed Asset Register (Capital Asset Tracking)
- **New Model**: `FixedAsset` for tracking capital assets
  - Asset categories: Land, Buildings, Plant & Machinery, Motor Vehicles, Computer Equipment, Furniture & Fittings, Intangible Assets
  - Depreciation methods: Straight Line, Reducing Balance, Units of Production
  - Standard depreciation rates per Nigerian tax law (Land 0%, Buildings 10%, Motor Vehicles 25%, Computer Equipment 25%, etc.)
  - Disposal tracking with automatic capital gain/loss calculation
  - VAT recovery on capital assets via vendor IRN validation
- **New Model**: `DepreciationEntry` for period-by-period depreciation tracking
- **New Service**: `FixedAssetService` with:
  - Full CRUD operations for assets
  - `run_depreciation()` - Batch depreciation posting for fiscal periods
  - `dispose_asset()` - Asset disposal with capital gain/loss calculation (taxed at CIT rate under 2026 reform)
  - `get_depreciation_schedule()` - Fiscal year depreciation schedule
  - `get_capital_gains_report()` - Capital gains report for CIT calculation
  - Auto-update of entity's `fixed_assets_value` for Development Levy threshold
- **New Router**: `/api/v1/fixed-assets` with endpoints:
  - `POST /` - Create fixed asset
  - `GET /entity/{entity_id}` - List assets for entity
  - `GET /{asset_id}` - Get asset details
  - `PATCH /{asset_id}` - Update asset
  - `POST /depreciation/run` - Run depreciation for period
  - `GET /entity/{entity_id}/depreciation-schedule` - Get depreciation schedule
  - `POST /{asset_id}/dispose` - Dispose of asset
  - `GET /entity/{entity_id}/summary` - Get asset register summary
  - `GET /entity/{entity_id}/capital-gains` - Get capital gains report

#### TIN/CAC Vault Dashboard Display
- Prominent display of Tax Identification Number (TIN) in dashboard
- Prominent display of CAC RC/BN Number in dashboard
- Verification status indicators (verified/missing) with warnings
- Business type display with tax implication (PIT vs CIT)
- VAT registration status display

#### Compliance Health Indicator
- Overall compliance score (0-100%)
- Status levels: Excellent, Good, Warning, Critical
- Automated compliance checks:
  - TIN Registration status
  - CAC Registration status
  - Small Company Status (0% CIT eligibility: turnover ≤ ₦50M, assets ≤ ₦250M)
  - Development Levy Exemption status (turnover ≤ ₦100M, assets ≤ ₦250M)
  - VAT Registration threshold check (₦25M threshold)
- Color-coded progress bar and status icons

#### B2C Real-time Reporting (24-Hour Reporting)
- New fields in BusinessEntity model:
  - `b2c_realtime_reporting_enabled`: Toggle for B2C real-time reporting
  - `b2c_reporting_threshold`: Configurable threshold (default ₦50,000)
- New NRS service methods:
  - `submit_b2c_transaction_report()` - Submit B2C transactions over threshold to NRS
  - `get_b2c_reporting_status()` - Check B2C reporting compliance status

### Enhanced

#### Dashboard Service
- New helper methods:
  - `_get_tin_cac_vault()` - TIN/CAC vault data for dashboard
  - `_get_compliance_health()` - Compliance health indicator data
- Updated `get_organization_dashboard()` to include:
  - TIN/CAC Vault section
  - Compliance Health indicator
  - Small Company Status
  - Development Levy status

#### Dashboard UI Template
- Added TIN/CAC Vault section with verification status indicators
- Added Compliance Health indicator with progress bar
- Added compliance checks display with color-coded status icons
- Business type and tax implication display

#### Auth Router
- Added `GET /api/v1/auth/dashboard` endpoint for full dashboard data with compliance information

### Database Migrations

- Added migration `20260103_1600_add_fixed_assets.py`:
  - Creates `fixed_assets` table with depreciation and disposal fields
  - Creates `depreciation_entries` table for period-by-period tracking
  - Creates enums: `assetcategory`, `assetstatus`, `depreciationmethod`, `disposaltype`
  - Creates indexes for efficient querying

### Tax Calculation System (Verified)

All 28 tax calculator tests passing:
- **VAT**: 7.5% standard rate, zero-rated, and exempt categories
- **PAYE**: 2026 progressive bands (0%/15%/20%/25%/30%)
- **WHT**: Professional services, consultancy, construction, rent, dividends, royalties, contract supply
- **CIT**: Small (0%), Medium (20%), Large (30%) based on turnover thresholds

---

## [1.2.0] - 2026-01-03

### 🇳🇬 NTAA 2025 Compliance Update

This release implements critical Nigeria Tax Administration Act (NTAA) 2025 compliance features to ensure the platform is "Nigeria 2026-Ready."

### Added

#### 72-Hour Legal Lock (Invoice State Lock)
- **NRS Submission Lock**: Once an invoice is submitted to NRS, it is locked and cannot be edited or deleted
- **Owner-Only Cancellation**: Only the `Owner` role can cancel an NRS submission during the 72-hour window
- **Credit Note Requirement**: Any post-submission modifications require a formal NRS-tracked Credit Note
- New fields in Invoice model:
  - `is_nrs_locked`: Boolean flag for lock status
  - `nrs_lock_expires_at`: 72-hour window expiry timestamp
  - `nrs_cancelled_by_id`: UUID of Owner who cancelled (if any)
  - `nrs_cancellation_reason`: Reason for cancellation
  - `nrs_cryptographic_stamp`: NRS cryptographic signature for audit verification
- New permission: `CANCEL_NRS_SUBMISSION` (Owner only)

#### Maker-Checker Segregation of Duties (SoD) for WREN Expenses
- **Segregation of Duties**: Accountant cannot verify WREN status on expenses they created
- **Maker**: Person who creates/uploads the expense
- **Checker**: Person who verifies WREN status (must be different from Maker)
- New fields in Transaction model:
  - `created_by_id`: UUID of user who created the transaction (Maker)
  - `wren_verified_by_id`: UUID of user who verified WREN status (Checker)
  - `wren_verified_at`: Timestamp of WREN verification
  - `original_category_id`: Original category for audit trail
  - `category_change_history`: JSONB history of category changes (before/after snapshots)
- New permission: `VERIFY_WREN` for WREN verification

#### External Accountant Role
- New role `EXTERNAL_ACCOUNTANT` for outsourced accounting firms (like QuickBooks "Invite Accountant")
- Permissions include:
  - `MANAGE_TAX_FILINGS` - File returns for client
  - `VIEW_REPORTS` - View reports
  - `EXPORT_DATA` - Export data
  - `VERIFY_WREN` - Verify WREN status
  - `VIEW_ALL_TRANSACTIONS` - View transactions
  - `VIEW_INVOICES` - View invoices
  - `VIEW_CUSTOMERS` / `VIEW_VENDORS` - View contacts
- Does NOT have:
  - `MANAGE_PAYROLL` - Cannot access payroll
  - `MANAGE_INVENTORY` - Cannot manage inventory
  - `MANAGE_INVOICES` - Cannot edit invoices
  - Any fund movement permissions

#### Enhanced Audit Log (NTAA 2025 Compliant)
- **IP & Device Fingerprint**: Mandatory for proving who submitted tax returns
- **Before/After Snapshots**: Stores original values when categories change (e.g., Personal → Business)
- **NRS Server Response Storage**: Stores IRN and Cryptographic Stamp directly in audit log
- **Impersonation Tracking**: Logs when CSR is impersonating a user
- New fields in AuditLog model:
  - `organization_id`: For multi-tenant queries
  - `impersonated_by_id`: CSR user ID if impersonating
  - `device_fingerprint`: Browser/device fingerprint
  - `session_id`: Session ID for tracking related actions
  - `geo_location`: Approximate location from IP
  - `nrs_irn`: NRS Invoice Reference Number
  - `nrs_response`: Full NRS server response
  - `description`: Human-readable description
- New audit actions:
  - `NRS_CREDIT_NOTE`
  - `WREN_VERIFY`
  - `WREN_REJECT`
  - `CATEGORY_CHANGE`
  - `IMPERSONATION_START`
  - `IMPERSONATION_END`
  - `IMPERSONATION_GRANT`
  - `IMPERSONATION_REVOKE`

#### Time-Limited CSR Impersonation (NDPA Compliance)
- **24-Hour Maximum**: Impersonation permission expires after 24 hours (per Nigeria Data Protection Act)
- **User-Granted**: Users explicitly grant access for a specific duration
- **Audit Trail**: All impersonation actions are logged
- New fields in User model:
  - `impersonation_expires_at`: When impersonation permission expires
  - `impersonation_granted_at`: When impersonation was granted

#### New NTAA Compliance Service
- `app/services/ntaa_compliance_service.py` - Centralized service for:
  - 72-hour legal lock management
  - Maker-Checker WREN verification
  - Time-limited impersonation
  - Enhanced audit logging

### Changed

#### User Model
- Added datetime imports for impersonation expiry
- Updated docstring with NTAA 2025 compliance features
- Added `EXTERNAL_ACCOUNTANT` to `UserRole` enum

#### Invoice Model
- Changed `nrs_response` from Text to JSONB for structured storage
- Added comprehensive NRS lock fields

#### Transaction Model
- Added datetime imports
- Added JSONB import for category change history
- Added Maker-Checker fields

#### Permissions System
- Updated permission matrix to include External Accountant
- Added `VERIFY_WREN` permission
- Added `CANCEL_NRS_SUBMISSION` permission (Owner only)
- Updated role hierarchy to include External Accountant at level 4

### Security

#### Credential Security
- **REMOVED** hardcoded Super Admin credentials from documentation
- Super Admin credentials are now **exclusively** stored in environment variables
- Updated documentation to reference `.env.example` for configuration

### Documentation

- Updated RBAC_DOCUMENTATION.md with:
  - Removed hardcoded credentials (security fix)
  - Added External Accountant role documentation
  - Updated permission matrix with NTAA 2025 permissions
  - Added NTAA 2025 compliance section

---

## [1.1.0] - 2026-01-02

### Added

#### Role-Based Access Control (RBAC)
- Two-tier RBAC system implemented:
  1. **Platform Staff** (Internal Tekvwa employees)
     - Super Admin, Admin, IT/Developer, Customer Service, Marketing
  2. **Organization Users** (External customers)
     - Owner, Admin, Accountant, Auditor, Payroll Manager, Inventory Manager, Viewer

#### Platform Staff Management
- Staff onboarding with hierarchy enforcement
- Staff deactivation/reactivation
- Role updates (Super Admin only)
- Organization verification workflow

#### Organization Verification
- Verification status tracking (Pending, Submitted, Under Review, Verified, Rejected)
- Document upload (CAC, TIN, additional documents)
- Admin approval workflow
- Referral code system

#### Dashboard System
- Role-specific dashboards for all user types
- Platform staff dashboards with operational metrics
- Organization user dashboards with financial metrics

---

## [1.0.0] - 2025-12-15

### Added

- Initial release of Tekvwa Pro Audit
- Core accounting features (transactions, invoices, inventory)
- NRS e-invoicing integration
- VAT, PAYE, CIT, WHT calculators (2026 Tax Reform compliant)
- Multi-entity support
- Customer and vendor management
- Receipt scanning and OCR
- Financial reporting

---

## Migration Notes

### Upgrading to 1.2.0

1. **Database Migration Required**
   ```bash
   # Run the NTAA 2025 migration
   alembic upgrade head
   ```

2. **Environment Variables**
   Ensure your `.env` file includes:
   ```env
   SUPER_ADMIN_EMAIL=your-admin@domain.com
   SUPER_ADMIN_PASSWORD=your-secure-password
   ```

3. **Breaking Changes**
   - External Accountant role added - update any role-based logic
   - Invoice editing now checks NRS lock status
   - WREN verification requires Maker-Checker validation

4. **New Dependencies**
   No new external dependencies required.

---

## Compliance Reference

### NTAA 2025 Sections Addressed

| Section | Requirement | Implementation |
|---------|-------------|----------------|
| CTC (Continuous Transaction Controls) | Real-time invoice validation | 72-Hour Legal Lock |
| Strict Liability | Director accountability | Enhanced Audit Trail |
| WREN | Expense deductibility | Maker-Checker SoD |
| E-Invoicing | NRS integration | IRN + Crypto Stamp storage |

### NDPA Compliance

| Requirement | Implementation |
|-------------|----------------|
| Time-limited data access | 24-hour impersonation tokens |
| Audit trail | Impersonation logging |
| User consent | Explicit grant required |
