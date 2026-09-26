# Tekvwa Pro Audit - Data Model & Entity Relationship Diagrams

## Document Information

| Attribute | Value |
|-----------|-------|
| Version | 1.0.0 |
| Last Updated | January 2026 |
| Classification | Internal / Audit |
| Compliance | NTAA 2025, NDPA 2023, IFRS |

---

## Table of Contents

1. [Overview](#1-overview)
2. [Domain Model Diagram](#2-domain-model-diagram)
3. [Core Entity Relationships](#3-core-entity-relationships)
4. [Accounting Module ERD](#4-accounting-module-erd)
5. [Audit Trail Module ERD](#5-audit-trail-module-erd)
6. [Payroll Module ERD](#6-payroll-module-erd)
7. [Tax Compliance Module ERD](#7-tax-compliance-module-erd)
8. [Bank Reconciliation Module ERD](#8-bank-reconciliation-module-erd)
9. [Data Dictionary](#9-data-dictionary)
10. [Referential Integrity Rules](#10-referential-integrity-rules)

---

## 1. Overview

Tekvwa Pro Audit uses a **multi-tenant, entity-scoped architecture** where:

- **Organizations** are the top-level tenant boundary
- **Business Entities** represent individual companies within an organization
- All financial data is scoped to a Business Entity
- Users can have access to multiple entities with different roles

### Key Design Principles

1. **Entity Isolation**: All financial data belongs to exactly one Business Entity
2. **Immutable Audit Trail**: Audit logs are append-only with no update/delete
3. **Referential Integrity**: Foreign keys with appropriate cascade rules
4. **Soft Deletes**: Records marked as deleted, never physically removed
5. **Temporal Data**: Created/updated timestamps on all records

---

## 2. Domain Model Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              TEKVWA PRO AUDIT - DOMAIN MODEL                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────┐
│    ORGANIZATION      │ ◄─────────────────────────────────────────────────────────┐
│    (Multi-Tenant)    │                                                           │
├──────────────────────┤                                                           │
│ • name               │                                                           │
│ • organization_type  │          ┌──────────────────────┐                        │
│ • subscription_tier  │          │        USER          │────────────────────────┤
│ • verification_status│◄─────────│   (Authentication)   │                        │
└──────────┬───────────┘          ├──────────────────────┤                        │
           │ 1:N                  │ • email              │                        │
           │                      │ • role (organization)│                        │
           ▼                      │ • platform_role      │                        │
┌──────────────────────┐          │ • is_platform_staff  │                        │
│   BUSINESS_ENTITY    │          └──────────────────────┘                        │
│   (Company/Ledger)   │                    │                                     │
├──────────────────────┤                    │                                     │
│ • name               │                    │ N:M                                 │
│ • tin                │                    ▼                                     │
│ • rc_number          │          ┌──────────────────────┐                        │
│ • business_type      │          │  USER_ENTITY_ACCESS  │                        │
│ • is_vat_registered  │◄─────────│   (Role per Entity)  │                        │
│ • fiscal_year_start  │          ├──────────────────────┤                        │
└──────────┬───────────┘          │ • role               │                        │
           │                      │ • permissions        │                        │
           │ 1:N (All Financial   └──────────────────────┘                        │
           │      Data Scoped)                                                    │
           │                                                                       │
           ├─────────────┬─────────────┬─────────────┬─────────────┬─────────────┤
           │             │             │             │             │             │
           ▼             ▼             ▼             ▼             ▼             ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
    │ CHART OF │  │ JOURNAL  │  │ INVOICE  │  │TRANSACTION│  │ PAYROLL  │  │   BANK   │
    │ ACCOUNTS │  │ ENTRIES  │  │          │  │          │  │          │  │ ACCOUNTS │
    └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘
```

---

## 3. Core Entity Relationships

### 3.1 Organization & User Hierarchy

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                           ORGANIZATION & USER HIERARCHY                                  │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────┐
│                            ORGANIZATION                                    │
│  PK: id (UUID)                                                            │
├───────────────────────────────────────────────────────────────────────────┤
│  name: VARCHAR(255) NOT NULL                                              │
│  slug: VARCHAR(100) UNIQUE NOT NULL                                       │
│  organization_type: ENUM('sme','small_business','school','non_profit',    │
│                          'individual','corporation')                       │
│  subscription_tier: ENUM('free','starter','professional','enterprise')    │
│  verification_status: ENUM('pending','submitted','under_review',          │
│                            'verified','rejected')                          │
│  email: VARCHAR(255)                                                      │
│  phone: VARCHAR(20)                                                       │
│  is_active: BOOLEAN DEFAULT TRUE                                          │
│  created_at: TIMESTAMP WITH TIME ZONE                                     │
│  updated_at: TIMESTAMP WITH TIME ZONE                                     │
└───────────────────────────────────────────────────────────────────────────┘
         │
         │ 1:N
         ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                            BUSINESS_ENTITY                                 │
│  PK: id (UUID)                                                            │
│  FK: organization_id → organizations(id) ON DELETE CASCADE                │
├───────────────────────────────────────────────────────────────────────────┤
│  name: VARCHAR(255) NOT NULL                                              │
│  legal_name: VARCHAR(255)                                                 │
│  tin: VARCHAR(20) -- Tax Identification Number                            │
│  rc_number: VARCHAR(20) -- CAC Registration Number                        │
│  business_type: ENUM('business_name','limited_company')                   │
│  address_line1, address_line2, city, state, lga, country                  │
│  email, phone, website                                                    │
│  fiscal_year_start_month: INTEGER DEFAULT 1                               │
│  currency: VARCHAR(3) DEFAULT 'NGN'                                       │
│  is_vat_registered: BOOLEAN DEFAULT FALSE                                 │
│  vat_registration_date: DATE                                              │
│  is_active: BOOLEAN DEFAULT TRUE                                          │
│  created_at, updated_at: TIMESTAMP WITH TIME ZONE                         │
└───────────────────────────────────────────────────────────────────────────┘
         │                          │
         │ 1:N                      │ N:M (via user_entity_access)
         ▼                          ▼
┌─────────────────────┐    ┌───────────────────────────────────────────────────────────────┐
│  (All Entity Data)  │    │                           USER                                │
│  • Invoices         │    │  PK: id (UUID)                                                │
│  • Transactions     │    │  FK: organization_id → organizations(id) ON DELETE CASCADE   │
│  • Journal Entries  │    ├───────────────────────────────────────────────────────────────┤
│  • Chart of Accounts│    │  email: VARCHAR(255) UNIQUE NOT NULL                          │
│  • Employees        │    │  hashed_password: VARCHAR(255) NOT NULL                       │
│  • Bank Accounts    │    │  full_name: VARCHAR(255)                                      │
│  • Audit Logs       │    │  phone: VARCHAR(20)                                           │
│  • etc.             │    │  role: ENUM('owner','admin','accountant','external_accountant'│
└─────────────────────┘    │              'auditor','payroll_manager','inventory_manager', │
                           │              'viewer')                                        │
                           │  is_platform_staff: BOOLEAN DEFAULT FALSE                     │
                           │  platform_role: ENUM('super_admin','admin','it_developer',   │
                           │                      'customer_service','marketing')          │
                           │  is_active, is_verified, is_locked: BOOLEAN                  │
                           │  last_login: TIMESTAMP WITH TIME ZONE                         │
                           └───────────────────────────────────────────────────────────────┘
                                          │
                                          │ 1:N
                                          ▼
                           ┌───────────────────────────────────────────────────────────────┐
                           │                    USER_ENTITY_ACCESS                         │
                           │  PK: id (UUID)                                                │
                           │  FK: user_id → users(id) ON DELETE CASCADE                   │
                           │  FK: entity_id → business_entities(id) ON DELETE CASCADE     │
                           ├───────────────────────────────────────────────────────────────┤
                           │  role: ENUM (role specific to this entity)                   │
                           │  permissions: JSONB                                          │
                           │  is_default: BOOLEAN                                         │
                           │  granted_at: TIMESTAMP WITH TIME ZONE                        │
                           │  granted_by_id: UUID                                         │
                           │  UNIQUE(user_id, entity_id)                                  │
                           └───────────────────────────────────────────────────────────────┘
```

**Access enforcement note:** this diagram shows the *data* relationships (an entity belongs to one
organization; a user may have specific per-entity grants via `USER_ENTITY_ACCESS`). The actual
*enforcement* that a request for a given `entity_id` belongs to the caller's own organization happens
at the application layer, not via a database constraint or row-level security policy — see
`docs/TECHNICAL_ARCHITECTURE.md` §6.2 for the `require_entity_access` dependency every entity-scoped
API endpoint must use.

---

## 4. Accounting Module ERD

### 4.1 Chart of Accounts & General Ledger

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                         ACCOUNTING MODULE - GENERAL LEDGER                               │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────┐
│                          CHART_OF_ACCOUNTS                                 │
│  PK: id (UUID)                                                            │
│  FK: entity_id → business_entities(id) ON DELETE CASCADE                  │
│  FK: parent_id → chart_of_accounts(id) ON DELETE SET NULL (Self-ref)     │
│  FK: bank_account_id → bank_accounts(id) ON DELETE SET NULL              │
├───────────────────────────────────────────────────────────────────────────┤
│  account_code: VARCHAR(20) NOT NULL                                       │
│  account_name: VARCHAR(200) NOT NULL                                      │
│  description: TEXT                                                        │
│  account_type: ENUM('asset','liability','equity','revenue','expense')     │
│  account_sub_type: ENUM('cash','bank','accounts_receivable','inventory',  │
│                         'fixed_asset','accounts_payable','vat_payable'...)│
│  normal_balance: ENUM('debit','credit')                                   │
│  level: INTEGER DEFAULT 1                                                 │
│  is_header: BOOLEAN DEFAULT FALSE                                         │
│  opening_balance: DECIMAL(18,2) DEFAULT 0                                 │
│  current_balance: DECIMAL(18,2) DEFAULT 0                                 │
│  ytd_debit: DECIMAL(18,2) DEFAULT 0                                       │
│  ytd_credit: DECIMAL(18,2) DEFAULT 0                                      │
│  is_tax_account: BOOLEAN DEFAULT FALSE                                    │
│  tax_type: VARCHAR(50) -- vat_output, vat_input, wht_payable, paye, etc  │
│  is_system_account: BOOLEAN DEFAULT FALSE                                 │
│  is_active: BOOLEAN DEFAULT TRUE                                          │
│  is_reconcilable: BOOLEAN DEFAULT FALSE                                   │
│  UNIQUE(entity_id, account_code)                                          │
└───────────────────────────────────────────────────────────────────────────┘
         │
         │ 1:N
         ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                          JOURNAL_ENTRY_LINE                                │
│  PK: id (UUID)                                                            │
│  FK: journal_entry_id → journal_entries(id) ON DELETE CASCADE            │
│  FK: account_id → chart_of_accounts(id) ON DELETE RESTRICT               │
├───────────────────────────────────────────────────────────────────────────┤
│  line_number: INTEGER NOT NULL                                            │
│  description: VARCHAR(500)                                                │
│  debit_amount: DECIMAL(18,2) DEFAULT 0                                    │
│  credit_amount: DECIMAL(18,2) DEFAULT 0                                   │
│  reference: VARCHAR(100)                                                  │
│  dimension_data: JSONB -- cost center, project, department               │
│  CHECK(debit_amount >= 0 AND credit_amount >= 0)                         │
│  CHECK(NOT(debit_amount > 0 AND credit_amount > 0))                      │
└───────────────────────────────────────────────────────────────────────────┘
         ▲
         │ N:1
         │
┌───────────────────────────────────────────────────────────────────────────┐
│                            JOURNAL_ENTRY                                   │
│  PK: id (UUID)                                                            │
│  FK: entity_id → business_entities(id) ON DELETE CASCADE                  │
│  FK: fiscal_period_id → fiscal_periods(id) ON DELETE RESTRICT            │
│  FK: created_by_id → users(id) ON DELETE SET NULL                        │
│  FK: approved_by_id → users(id) ON DELETE SET NULL                       │
│  FK: reversed_entry_id → journal_entries(id) -- For reversals            │
├───────────────────────────────────────────────────────────────────────────┤
│  entry_number: VARCHAR(50) NOT NULL                                       │
│  entry_date: DATE NOT NULL                                                │
│  description: VARCHAR(500)                                                │
│  entry_type: ENUM('manual','sales','purchase','receipt','payment',        │
│                   'payroll','depreciation','tax_adjustment',              │
│                   'bank_reconciliation','inventory_adjustment',           │
│                   'opening_balance','closing_entry','reversal','system')  │
│  status: ENUM('draft','pending','posted','reversed','voided')             │
│  total_debit: DECIMAL(18,2) NOT NULL                                      │
│  total_credit: DECIMAL(18,2) NOT NULL                                     │
│  is_auto_generated: BOOLEAN DEFAULT FALSE                                 │
│  source_document_type: VARCHAR(50)                                        │
│  source_document_id: UUID                                                 │
│  posted_at: TIMESTAMP WITH TIME ZONE                                      │
│  reversed_at: TIMESTAMP WITH TIME ZONE                                    │
│  CHECK(total_debit = total_credit) -- Balanced entry                     │
│  UNIQUE(entity_id, entry_number)                                          │
└───────────────────────────────────────────────────────────────────────────┘
         │
         │ N:1
         ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                            FISCAL_PERIOD                                   │
│  PK: id (UUID)                                                            │
│  FK: entity_id → business_entities(id) ON DELETE CASCADE                  │
│  FK: fiscal_year_id → fiscal_years(id) ON DELETE CASCADE                 │
├───────────────────────────────────────────────────────────────────────────┤
│  period_name: VARCHAR(50) NOT NULL                                        │
│  period_number: INTEGER NOT NULL                                          │
│  start_date: DATE NOT NULL                                                │
│  end_date: DATE NOT NULL                                                  │
│  status: ENUM('open','pending_close','closed','locked','reopened')        │
│  closed_at: TIMESTAMP WITH TIME ZONE                                      │
│  closed_by_id: UUID                                                       │
└───────────────────────────────────────────────────────────────────────────┘
         │
         │ N:1
         ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                             FISCAL_YEAR                                    │
│  PK: id (UUID)                                                            │
│  FK: entity_id → business_entities(id) ON DELETE CASCADE                  │
├───────────────────────────────────────────────────────────────────────────┤
│  year_name: VARCHAR(50) NOT NULL                                          │
│  start_date: DATE NOT NULL                                                │
│  end_date: DATE NOT NULL                                                  │
│  is_current: BOOLEAN DEFAULT FALSE                                        │
│  is_closed: BOOLEAN DEFAULT FALSE                                         │
│  UNIQUE(entity_id, year_name)                                             │
└───────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Transactions, Invoices & Customers

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                      ACCOUNTING MODULE - TRANSACTIONS & INVOICES                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────┐
│                             CUSTOMER                                       │
│  PK: id (UUID)                                                            │
│  FK: entity_id → business_entities(id) ON DELETE CASCADE                  │
├───────────────────────────────────────────────────────────────────────────┤
│  name: VARCHAR(255) NOT NULL                                              │
│  email: VARCHAR(255)                                                      │
│  phone: VARCHAR(20)                                                       │
│  tin: VARCHAR(20) -- Customer's TIN for WHT                              │
│  address: TEXT                                                            │
│  is_vat_registered: BOOLEAN                                               │
│  credit_limit: DECIMAL(15,2)                                              │
│  payment_terms: INTEGER DEFAULT 30                                        │
│  is_active: BOOLEAN DEFAULT TRUE                                          │
└───────────────────────────────────────────────────────────────────────────┘
         │
         │ 1:N
         ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                              INVOICE                                       │
│  PK: id (UUID)                                                            │
│  FK: entity_id → business_entities(id) ON DELETE CASCADE                  │
│  FK: customer_id → customers(id) ON DELETE SET NULL                       │
├───────────────────────────────────────────────────────────────────────────┤
│  invoice_number: VARCHAR(50) NOT NULL                                     │
│  invoice_date: DATE NOT NULL                                              │
│  due_date: DATE NOT NULL                                                  │
│  subtotal: DECIMAL(15,2) NOT NULL                                         │
│  vat_amount: DECIMAL(15,2) DEFAULT 0                                      │
│  discount_amount: DECIMAL(15,2) DEFAULT 0                                 │
│  total_amount: DECIMAL(15,2) NOT NULL                                     │
│  amount_paid: DECIMAL(15,2) DEFAULT 0                                     │
│  status: ENUM('draft','pending','submitted','accepted','rejected',        │
│               'disputed','cancelled','paid','partially_paid')             │
│  vat_treatment: ENUM('standard','zero_rated','exempt')                    │
│  vat_rate: DECIMAL(5,2) DEFAULT 7.50                                      │
│  ─────────────────────────────────────────────────────────────────────    │
│  NRS E-INVOICING (NTAA 2025):                                             │
│  nrs_irn: VARCHAR(100) UNIQUE -- Invoice Reference Number                │
│  nrs_qr_code_data: TEXT                                                   │
│  nrs_submitted_at: TIMESTAMP                                              │
│  nrs_response: JSONB                                                      │
│  nrs_status: ENUM('not_submitted','pending','accepted','rejected')        │
│  is_nrs_locked: BOOLEAN DEFAULT FALSE -- 72-hour legal lock              │
│  buyer_status: ENUM('pending','accepted','auto_accepted','rejected')      │
│  UNIQUE(entity_id, invoice_number)                                        │
└───────────────────────────────────────────────────────────────────────────┘
         │
         │ 1:N
         ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                           INVOICE_LINE                                     │
│  PK: id (UUID)                                                            │
│  FK: invoice_id → invoices(id) ON DELETE CASCADE                         │
│  FK: inventory_item_id → inventory_items(id) ON DELETE SET NULL          │
├───────────────────────────────────────────────────────────────────────────┤
│  line_number: INTEGER NOT NULL                                            │
│  description: VARCHAR(500)                                                │
│  quantity: DECIMAL(15,4) NOT NULL                                         │
│  unit_price: DECIMAL(15,2) NOT NULL                                       │
│  discount_percent: DECIMAL(5,2) DEFAULT 0                                 │
│  vat_rate: DECIMAL(5,2)                                                   │
│  line_total: DECIMAL(15,2) NOT NULL                                       │
│  vat_amount: DECIMAL(15,2) NOT NULL                                       │
└───────────────────────────────────────────────────────────────────────────┘


┌───────────────────────────────────────────────────────────────────────────┐
│                            TRANSACTION                                     │
│  PK: id (UUID)                                                            │
│  FK: entity_id → business_entities(id) ON DELETE CASCADE                  │
│  FK: category_id → categories(id) ON DELETE SET NULL                     │
│  FK: vendor_id → vendors(id) ON DELETE SET NULL                          │
│  FK: created_by_id → users(id) ON DELETE SET NULL                        │
│  FK: wren_verified_by_id → users(id) ON DELETE SET NULL                  │
├───────────────────────────────────────────────────────────────────────────┤
│  transaction_type: ENUM('income','expense')                               │
│  transaction_date: DATE NOT NULL                                          │
│  amount: DECIMAL(15,2) NOT NULL                                           │
│  vat_amount: DECIMAL(15,2) DEFAULT 0                                      │
│  wht_amount: DECIMAL(15,2) DEFAULT 0                                      │
│  total_amount: DECIMAL(15,2) NOT NULL                                     │
│  description: VARCHAR(500) NOT NULL                                       │
│  reference: VARCHAR(100)                                                  │
│  ─────────────────────────────────────────────────────────────────────    │
│  WREN COMPLIANCE (Maker-Checker):                                         │
│  wren_status: ENUM('compliant','non_compliant','review_required')         │
│  wren_notes: TEXT                                                         │
│  wren_verified_at: TIMESTAMP                                              │
│  -- CONSTRAINT: wren_verified_by_id != created_by_id (SoD)               │
│  ─────────────────────────────────────────────────────────────────────    │
│  AUDIT FIELDS:                                                            │
│  created_by_id, modified_by_id: UUID                                     │
│  created_at, updated_at: TIMESTAMP WITH TIME ZONE                         │
└───────────────────────────────────────────────────────────────────────────┘
         │
         │ N:1
         ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                              VENDOR                                        │
│  PK: id (UUID)                                                            │
│  FK: entity_id → business_entities(id) ON DELETE CASCADE                  │
├───────────────────────────────────────────────────────────────────────────┤
│  name: VARCHAR(255) NOT NULL                                              │
│  email: VARCHAR(255)                                                      │
│  phone: VARCHAR(20)                                                       │
│  tin: VARCHAR(20) -- For WHT calculations                                │
│  vat_registered: BOOLEAN                                                  │
│  address: TEXT                                                            │
│  payment_terms: INTEGER                                                   │
│  is_active: BOOLEAN DEFAULT TRUE                                          │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Audit Trail Module ERD

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              AUDIT TRAIL MODULE                                          │
│                          (NTAA 2025 5-Year Retention)                                   │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────┐
│                             AUDIT_LOG                                      │
│  PK: id (UUID)                                                            │
│  FK: entity_id → business_entities(id) ON DELETE CASCADE                  │
│  FK: user_id → users(id) ON DELETE SET NULL                              │
│  *** APPEND-ONLY TABLE - NO UPDATE/DELETE ***                            │
├───────────────────────────────────────────────────────────────────────────┤
│  action: ENUM('create','update','delete','view','export','login',         │
│               'logout','login_failed','nrs_submit','nrs_cancel',          │
│               'nrs_credit_note','upload','download','wren_verify',        │
│               'wren_reject','category_change','impersonation_start',      │
│               'impersonation_end','impersonation_grant','impersonation_revoke')│
│  target_entity_type: VARCHAR(100) -- invoice, transaction, employee, etc │
│  target_entity_id: VARCHAR(100)                                           │
│  description: TEXT                                                        │
│  ─────────────────────────────────────────────────────────────────────    │
│  CHANGE TRACKING:                                                         │
│  old_values: JSONB -- Before state                                       │
│  new_values: JSONB -- After state                                        │
│  changes: JSONB -- Delta/diff                                            │
│  ─────────────────────────────────────────────────────────────────────    │
│  DEVICE FINGERPRINT (NTAA 2025):                                          │
│  ip_address: INET                                                         │
│  user_agent: TEXT                                                         │
│  device_fingerprint: VARCHAR(255)                                         │
│  session_id: VARCHAR(255)                                                 │
│  ─────────────────────────────────────────────────────────────────────    │
│  NRS INTEGRATION:                                                         │
│  nrs_irn: VARCHAR(100) -- For NRS submissions                            │
│  nrs_response: JSONB -- Full NRS response                                │
│  ─────────────────────────────────────────────────────────────────────    │
│  created_at: TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()             │
│  INDEX: (entity_id, created_at)                                          │
│  INDEX: (entity_id, action)                                              │
│  INDEX: (entity_id, target_entity_type, target_entity_id)                │
└───────────────────────────────────────────────────────────────────────────┘


┌───────────────────────────────────────────────────────────────────────────┐
│                             AUDIT_RUN                                      │
│  PK: id (UUID)                                                            │
│  FK: entity_id → business_entities(id) ON DELETE CASCADE                  │
│  FK: initiated_by_id → users(id) ON DELETE SET NULL                      │
├───────────────────────────────────────────────────────────────────────────┤
│  run_number: VARCHAR(50) NOT NULL                                         │
│  run_type: ENUM('tax_compliance','financial_statement','vat_audit',       │
│                 'wht_audit','paye_audit','benfords_law','zscore_anomaly', │
│                 'nrs_gap_analysis','three_way_matching',                  │
│                 'hash_chain_integrity','full_forensic','compliance_replay',│
│                 'behavioral_analytics','custom')                          │
│  title: VARCHAR(255) NOT NULL                                             │
│  description: TEXT                                                        │
│  status: ENUM('pending','running','completed','failed','cancelled')       │
│  ─────────────────────────────────────────────────────────────────────    │
│  PARAMETERS (for reproducibility):                                        │
│  parameters: JSONB                                                        │
│  fiscal_year: INTEGER                                                     │
│  start_date: DATE                                                         │
│  end_date: DATE                                                           │
│  ─────────────────────────────────────────────────────────────────────    │
│  RESULTS:                                                                 │
│  findings_count: INTEGER DEFAULT 0                                        │
│  critical_count: INTEGER DEFAULT 0                                        │
│  high_count: INTEGER DEFAULT 0                                            │
│  medium_count: INTEGER DEFAULT 0                                          │
│  low_count: INTEGER DEFAULT 0                                             │
│  result_summary: JSONB                                                    │
│  ─────────────────────────────────────────────────────────────────────    │
│  TIMING:                                                                  │
│  started_at: TIMESTAMP                                                    │
│  completed_at: TIMESTAMP                                                  │
│  duration_seconds: FLOAT                                                  │
│  is_reproducible: BOOLEAN DEFAULT TRUE                                   │
│  UNIQUE(entity_id, run_number)                                            │
└───────────────────────────────────────────────────────────────────────────┘
         │
         │ 1:N
         ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                           AUDIT_FINDING                                    │
│  PK: id (UUID)                                                            │
│  FK: audit_run_id → audit_runs(id) ON DELETE CASCADE                     │
│  FK: entity_id → business_entities(id) ON DELETE CASCADE                  │
├───────────────────────────────────────────────────────────────────────────┤
│  finding_code: VARCHAR(50) NOT NULL                                       │
│  title: VARCHAR(255) NOT NULL                                             │
│  description: TEXT NOT NULL                                               │
│  risk_level: ENUM('critical','high','medium','low','informational')       │
│  category: ENUM('fraud_indicator','compliance_gap','data_integrity',      │
│                 'policy_violation','process_weakness','control_deficiency',│
│                 'documentation_gap','tax_discrepancy',                    │
│                 'financial_misstatement')                                 │
│  affected_records: INTEGER DEFAULT 0                                      │
│  financial_impact: DECIMAL(18,2)                                          │
│  recommendation: TEXT                                                     │
│  affected_record_ids: JSONB -- Array of affected record IDs              │
│  raw_data: JSONB -- Supporting data                                      │
│  is_resolved: BOOLEAN DEFAULT FALSE                                       │
│  resolved_at: TIMESTAMP                                                   │
│  resolution_notes: TEXT                                                   │
└───────────────────────────────────────────────────────────────────────────┘


┌───────────────────────────────────────────────────────────────────────────┐
│                           AUDIT_EVIDENCE                                   │
│  PK: id (UUID)                                                            │
│  FK: audit_run_id → audit_runs(id) ON DELETE CASCADE                     │
│  FK: finding_id → audit_findings(id) ON DELETE SET NULL                  │
│  *** IMMUTABLE - Hash verified ***                                       │
├───────────────────────────────────────────────────────────────────────────┤
│  evidence_type: ENUM('document','transaction','calculation','screenshot', │
│                      'log_extract','database_snapshot',                   │
│                      'external_confirmation','system_generated')          │
│  title: VARCHAR(255) NOT NULL                                             │
│  description: TEXT                                                        │
│  source: VARCHAR(255)                                                     │
│  content: JSONB -- Evidence content                                      │
│  content_hash: VARCHAR(64) NOT NULL -- SHA-256 integrity hash           │
│  file_path: VARCHAR(500)                                                  │
│  file_size: BIGINT                                                        │
│  mime_type: VARCHAR(100)                                                  │
│  captured_at: TIMESTAMP NOT NULL                                          │
│  is_verified: BOOLEAN DEFAULT FALSE                                       │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Payroll Module ERD

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                               PAYROLL MODULE                                             │
│                    (Nigerian PAYE, Pension, NHF, NSITF, ITF)                            │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────┐
│                              EMPLOYEE                                      │
│  PK: id (UUID)                                                            │
│  FK: entity_id → business_entities(id) ON DELETE CASCADE                  │
│  FK: user_id → users(id) ON DELETE SET NULL (for self-service)           │
│  FK: department_id → departments(id) ON DELETE SET NULL                  │
├───────────────────────────────────────────────────────────────────────────┤
│  employee_id: VARCHAR(50) NOT NULL -- Staff ID                           │
│  first_name, last_name, middle_name: VARCHAR(100)                        │
│  email: VARCHAR(255)                                                      │
│  phone: VARCHAR(20)                                                       │
│  date_of_birth: DATE                                                      │
│  gender: ENUM('male','female','other')                                    │
│  marital_status: ENUM('single','married','divorced','widowed')            │
│  address: TEXT                                                            │
│  state_of_origin: VARCHAR(50)                                             │
│  ─────────────────────────────────────────────────────────────────────    │
│  EMPLOYMENT:                                                              │
│  employment_type: ENUM('full_time','part_time','contract','intern',       │
│                        'probation','consultant')                          │
│  employment_status: ENUM('active','inactive','terminated','resigned',     │
│                          'retired','suspended','on_leave')                │
│  hire_date: DATE NOT NULL                                                 │
│  termination_date: DATE                                                   │
│  job_title: VARCHAR(100)                                                  │
│  ─────────────────────────────────────────────────────────────────────    │
│  TAX IDENTIFIERS:                                                         │
│  tin: VARCHAR(20) -- Tax Identification Number                           │
│  nin: VARCHAR(20) -- National Identification Number                      │
│  pension_pin: VARCHAR(20) -- PenCom PIN                                  │
│  pfa_name: VARCHAR(100) -- Pension Fund Administrator                    │
│  ─────────────────────────────────────────────────────────────────────    │
│  BANK DETAILS:                                                            │
│  bank_name: ENUM (Nigerian banks)                                        │
│  bank_account_number: VARCHAR(20)                                         │
│  bank_account_name: VARCHAR(100)                                          │
│  UNIQUE(entity_id, employee_id)                                           │
└───────────────────────────────────────────────────────────────────────────┘
         │
         │ 1:N                                    1:N
         ▼                                         ▼
┌─────────────────────────────┐          ┌─────────────────────────────┐
│     SALARY_STRUCTURE        │          │     EMPLOYEE_DEDUCTION      │
│  FK: employee_id            │          │  FK: employee_id            │
├─────────────────────────────┤          ├─────────────────────────────┤
│  basic_salary: DECIMAL      │          │  deduction_type: ENUM       │
│  housing_allowance: DECIMAL │          │  amount: DECIMAL            │
│  transport_allowance: DECIMAL│          │  start_date: DATE          │
│  meal_allowance: DECIMAL    │          │  end_date: DATE             │
│  utility_allowance: DECIMAL │          │  is_recurring: BOOLEAN      │
│  other_allowances: JSONB    │          └─────────────────────────────┘
│  effective_date: DATE       │
│  is_current: BOOLEAN        │
└─────────────────────────────┘


┌───────────────────────────────────────────────────────────────────────────┐
│                            PAYROLL_RUN                                     │
│  PK: id (UUID)                                                            │
│  FK: entity_id → business_entities(id) ON DELETE CASCADE                  │
│  FK: created_by_id → users(id)                                           │
│  FK: approved_by_id → users(id)                                          │
├───────────────────────────────────────────────────────────────────────────┤
│  run_number: VARCHAR(50) NOT NULL                                         │
│  pay_period_start: DATE NOT NULL                                          │
│  pay_period_end: DATE NOT NULL                                            │
│  payment_date: DATE NOT NULL                                              │
│  frequency: ENUM('weekly','bi_weekly','monthly')                          │
│  status: ENUM('draft','pending_approval','approved','processing',         │
│               'completed','paid','cancelled')                             │
│  ─────────────────────────────────────────────────────────────────────    │
│  TOTALS:                                                                  │
│  total_gross: DECIMAL(18,2)                                               │
│  total_deductions: DECIMAL(18,2)                                          │
│  total_net: DECIMAL(18,2)                                                 │
│  total_employer_cost: DECIMAL(18,2)                                       │
│  ─────────────────────────────────────────────────────────────────────    │
│  STATUTORY TOTALS:                                                        │
│  total_paye: DECIMAL(18,2)                                                │
│  total_pension_employee: DECIMAL(18,2)                                    │
│  total_pension_employer: DECIMAL(18,2)                                    │
│  total_nhf: DECIMAL(18,2)                                                 │
│  total_nsitf: DECIMAL(18,2)                                               │
│  total_itf: DECIMAL(18,2)                                                 │
│  employee_count: INTEGER                                                  │
│  UNIQUE(entity_id, run_number)                                            │
└───────────────────────────────────────────────────────────────────────────┘
         │
         │ 1:N
         ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                            PAYROLL_ITEM                                    │
│  PK: id (UUID)                                                            │
│  FK: payroll_run_id → payroll_runs(id) ON DELETE CASCADE                 │
│  FK: employee_id → employees(id) ON DELETE CASCADE                       │
├───────────────────────────────────────────────────────────────────────────┤
│  EARNINGS:                                                                │
│  basic_salary: DECIMAL(15,2)                                              │
│  housing_allowance: DECIMAL(15,2)                                         │
│  transport_allowance: DECIMAL(15,2)                                       │
│  other_earnings: JSONB                                                    │
│  gross_pay: DECIMAL(15,2)                                                 │
│  ─────────────────────────────────────────────────────────────────────    │
│  STATUTORY DEDUCTIONS:                                                    │
│  paye: DECIMAL(15,2) -- Personal Income Tax                              │
│  pension_employee: DECIMAL(15,2) -- 8% employee contribution             │
│  nhf: DECIMAL(15,2) -- 2.5% National Housing Fund                        │
│  ─────────────────────────────────────────────────────────────────────    │
│  EMPLOYER CONTRIBUTIONS (not deducted from employee):                     │
│  pension_employer: DECIMAL(15,2) -- 10% employer contribution            │
│  nsitf: DECIMAL(15,2) -- 1% NSITF                                        │
│  itf: DECIMAL(15,2) -- 1% ITF (for 5+ employees)                         │
│  ─────────────────────────────────────────────────────────────────────    │
│  other_deductions: JSONB -- loans, cooperative, etc                      │
│  total_deductions: DECIMAL(15,2)                                          │
│  net_pay: DECIMAL(15,2)                                                   │
│  payment_status: ENUM('pending','paid','failed')                          │
│  UNIQUE(payroll_run_id, employee_id)                                      │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Tax Compliance Module ERD

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                            TAX COMPLIANCE MODULE                                         │
│                        (VAT, WHT, PAYE, CIT, EMTL)                                       │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────┐
│                             TAX_PERIOD                                     │
│  PK: id (UUID)                                                            │
│  FK: entity_id → business_entities(id) ON DELETE CASCADE                  │
├───────────────────────────────────────────────────────────────────────────┤
│  period_type: ENUM('monthly','quarterly','annually')                       │
│  year: INTEGER NOT NULL                                                   │
│  month: INTEGER -- 1-12 for monthly                                       │
│  quarter: INTEGER -- 1-4 for quarterly                                    │
│  start_date: DATE NOT NULL                                                │
│  end_date: DATE NOT NULL                                                  │
│  due_date: DATE NOT NULL                                                  │
│  is_filed: BOOLEAN DEFAULT FALSE                                          │
│  filed_date: DATE                                                         │
└───────────────────────────────────────────────────────────────────────────┘
         │
         │ 1:1
         ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                             VAT_RECORD                                     │
│  PK: id (UUID)                                                            │
│  FK: entity_id → business_entities(id) ON DELETE CASCADE                  │
│  FK: tax_period_id → tax_periods(id) ON DELETE SET NULL                  │
├───────────────────────────────────────────────────────────────────────────┤
│  period_start: DATE NOT NULL                                              │
│  period_end: DATE NOT NULL                                                │
│  ─────────────────────────────────────────────────────────────────────    │
│  OUTPUT VAT (Collected from sales):                                       │
│  output_vat: DECIMAL(15,2) DEFAULT 0                                      │
│  output_vat_base: DECIMAL(15,2) DEFAULT 0 -- Taxable sales               │
│  ─────────────────────────────────────────────────────────────────────    │
│  INPUT VAT (Paid on purchases):                                           │
│  input_vat: DECIMAL(15,2) DEFAULT 0                                       │
│  input_vat_base: DECIMAL(15,2) DEFAULT 0                                  │
│  wren_compliant_input: DECIMAL(15,2) DEFAULT 0 -- Recoverable            │
│  non_compliant_input: DECIMAL(15,2) DEFAULT 0 -- Non-recoverable         │
│  ─────────────────────────────────────────────────────────────────────    │
│  CALCULATION:                                                             │
│  vat_payable: DECIMAL(15,2) -- Output - Compliant Input                  │
│  vat_refundable: DECIMAL(15,2) -- If Input > Output                      │
│  ─────────────────────────────────────────────────────────────────────    │
│  STATUS:                                                                  │
│  is_filed: BOOLEAN DEFAULT FALSE                                          │
│  filed_at: TIMESTAMP                                                      │
│  filing_reference: VARCHAR(100)                                           │
└───────────────────────────────────────────────────────────────────────────┘


┌───────────────────────────────────────────────────────────────────────────┐
│                           WHT_TRANSACTION                                  │
│  PK: id (UUID)                                                            │
│  FK: entity_id → business_entities(id) ON DELETE CASCADE                  │
│  FK: vendor_id → vendors(id) ON DELETE SET NULL                          │
│  FK: invoice_id → invoices(id) ON DELETE SET NULL                        │
├───────────────────────────────────────────────────────────────────────────┤
│  transaction_date: DATE NOT NULL                                          │
│  gross_amount: DECIMAL(15,2) NOT NULL                                     │
│  wht_rate: DECIMAL(5,2) NOT NULL -- 5%, 10%, etc                         │
│  wht_amount: DECIMAL(15,2) NOT NULL                                       │
│  net_amount: DECIMAL(15,2) NOT NULL                                       │
│  wht_type: ENUM('contract','dividend','rent','professional',              │
│                 'directors_fee','interest','royalty')                     │
│  vendor_tin: VARCHAR(20)                                                  │
│  description: TEXT                                                        │
│  remittance_status: ENUM('pending','remitted','failed')                   │
│  remitted_at: DATE                                                        │
└───────────────────────────────────────────────────────────────────────────┘


┌───────────────────────────────────────────────────────────────────────────┐
│                            PAYE_RECORD                                     │
│  PK: id (UUID)                                                            │
│  FK: entity_id → business_entities(id) ON DELETE CASCADE                  │
│  FK: tax_period_id → tax_periods(id) ON DELETE SET NULL                  │
│  FK: payroll_run_id → payroll_runs(id) ON DELETE SET NULL                │
├───────────────────────────────────────────────────────────────────────────┤
│  period_month: INTEGER NOT NULL                                           │
│  period_year: INTEGER NOT NULL                                            │
│  ─────────────────────────────────────────────────────────────────────    │
│  TOTALS:                                                                  │
│  total_gross_emoluments: DECIMAL(15,2)                                    │
│  total_taxable_income: DECIMAL(15,2)                                      │
│  total_paye_deducted: DECIMAL(15,2)                                       │
│  employee_count: INTEGER                                                  │
│  ─────────────────────────────────────────────────────────────────────    │
│  REMITTANCE:                                                              │
│  remittance_status: ENUM('pending','remitted','failed')                   │
│  remitted_at: DATE                                                        │
│  remittance_reference: VARCHAR(100)                                       │
│  state_irs: VARCHAR(50) -- Which State IRS                               │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Bank Reconciliation Module ERD

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                         BANK RECONCILIATION MODULE                                       │
│               (Multi-Channel Import, Auto-Matching, Nigerian Charges)                   │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────┐
│                            BANK_ACCOUNT                                    │
│  PK: id (UUID)                                                            │
│  FK: entity_id → business_entities(id) ON DELETE CASCADE                  │
│  FK: gl_account_id → chart_of_accounts(id) ON DELETE SET NULL            │
├───────────────────────────────────────────────────────────────────────────┤
│  account_name: VARCHAR(255) NOT NULL                                      │
│  bank_name: VARCHAR(100) NOT NULL                                         │
│  account_number: VARCHAR(20) NOT NULL                                     │
│  account_type: ENUM('current','savings','domiciliary','fixed_deposit')    │
│  currency: ENUM('NGN','USD','GBP','EUR')                                  │
│  ─────────────────────────────────────────────────────────────────────    │
│  BALANCES:                                                                │
│  opening_balance: DECIMAL(18,2) DEFAULT 0                                 │
│  current_balance: DECIMAL(18,2) DEFAULT 0 -- Book balance                │
│  last_statement_balance: DECIMAL(18,2) -- Bank balance                   │
│  last_reconciled_date: DATE                                               │
│  ─────────────────────────────────────────────────────────────────────    │
│  API INTEGRATION:                                                         │
│  integration_type: ENUM('mono_api','okra_api','stitch_api','manual')      │
│  integration_id: VARCHAR(255) -- External provider account ID            │
│  integration_status: ENUM('connected','disconnected','error')             │
│  last_sync_at: TIMESTAMP                                                  │
│  is_active: BOOLEAN DEFAULT TRUE                                          │
│  UNIQUE(entity_id, account_number)                                        │
└───────────────────────────────────────────────────────────────────────────┘
         │
         │ 1:N
         ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                        BANK_STATEMENT_LINE                                 │
│  PK: id (UUID)                                                            │
│  FK: bank_account_id → bank_accounts(id) ON DELETE CASCADE               │
│  FK: reconciliation_id → bank_reconciliations(id) ON DELETE SET NULL     │
├───────────────────────────────────────────────────────────────────────────┤
│  statement_date: DATE NOT NULL                                            │
│  value_date: DATE                                                         │
│  description: TEXT NOT NULL                                               │
│  reference: VARCHAR(100)                                                  │
│  debit_amount: DECIMAL(18,2) DEFAULT 0                                    │
│  credit_amount: DECIMAL(18,2) DEFAULT 0                                   │
│  running_balance: DECIMAL(18,2)                                           │
│  ─────────────────────────────────────────────────────────────────────    │
│  IMPORT SOURCE:                                                           │
│  source: ENUM('mono_api','okra_api','csv_upload','excel_upload',          │
│               'mt940_upload','pdf_ocr','manual_entry')                    │
│  external_id: VARCHAR(255) -- Provider transaction ID                    │
│  raw_data: JSONB -- Original imported data                               │
│  ─────────────────────────────────────────────────────────────────────    │
│  MATCHING:                                                                │
│  match_status: ENUM('unmatched','suggested','auto_matched',               │
│                     'manual_matched','partially_matched',                 │
│                     'reconciled','excluded','disputed')                   │
│  match_confidence: DECIMAL(5,2) -- 0-100%                                 │
│  matched_transaction_ids: JSONB -- Array of matched book transactions    │
│  ─────────────────────────────────────────────────────────────────────    │
│  NIGERIAN CHARGES:                                                        │
│  charge_type: ENUM('emtl','stamp_duty','vat','wht','bank_charge','other') │
│  is_bank_charge: BOOLEAN DEFAULT FALSE                                    │
│  auto_categorized: BOOLEAN DEFAULT FALSE                                  │
│  INDEX: (bank_account_id, statement_date)                                │
│  INDEX: (bank_account_id, match_status)                                  │
└───────────────────────────────────────────────────────────────────────────┘


┌───────────────────────────────────────────────────────────────────────────┐
│                        BANK_RECONCILIATION                                 │
│  PK: id (UUID)                                                            │
│  FK: bank_account_id → bank_accounts(id) ON DELETE CASCADE               │
│  FK: prepared_by_id → users(id) ON DELETE SET NULL                       │
│  FK: approved_by_id → users(id) ON DELETE SET NULL                       │
├───────────────────────────────────────────────────────────────────────────┤
│  period_start: DATE NOT NULL                                              │
│  period_end: DATE NOT NULL                                                │
│  ─────────────────────────────────────────────────────────────────────    │
│  BALANCES:                                                                │
│  opening_book_balance: DECIMAL(18,2)                                      │
│  closing_book_balance: DECIMAL(18,2)                                      │
│  opening_bank_balance: DECIMAL(18,2)                                      │
│  closing_bank_balance: DECIMAL(18,2)                                      │
│  ─────────────────────────────────────────────────────────────────────    │
│  OUTSTANDING ITEMS:                                                       │
│  outstanding_deposits: DECIMAL(18,2) -- Deposits not yet on statement   │
│  outstanding_payments: DECIMAL(18,2) -- Checks not yet cleared          │
│  bank_errors: DECIMAL(18,2)                                               │
│  book_errors: DECIMAL(18,2)                                               │
│  ─────────────────────────────────────────────────────────────────────    │
│  RECONCILIATION:                                                          │
│  reconciled_balance: DECIMAL(18,2)                                        │
│  difference: DECIMAL(18,2) -- Should be 0 when reconciled               │
│  is_balanced: BOOLEAN DEFAULT FALSE                                       │
│  ─────────────────────────────────────────────────────────────────────    │
│  STATUS:                                                                  │
│  status: ENUM('draft','in_progress','pending_approval','approved',        │
│               'rejected','finalized')                                     │
│  prepared_at: TIMESTAMP                                                   │
│  approved_at: TIMESTAMP                                                   │
│  notes: TEXT                                                              │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## 9. Data Dictionary

### 9.1 Common Fields (All Tables)

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key, auto-generated |
| `created_at` | TIMESTAMP WITH TIME ZONE | Record creation time |
| `updated_at` | TIMESTAMP WITH TIME ZONE | Last modification time |
| `is_active` | BOOLEAN | Soft delete flag |

### 9.2 Nigerian-Specific Fields

| Field | Table(s) | Description |
|-------|----------|-------------|
| `tin` | business_entities, customers, vendors, employees | Tax Identification Number (FIRS) |
| `rc_number` | business_entities | CAC Registration Number |
| `nin` | employees | National Identification Number |
| `pension_pin` | employees | PenCom Pension PIN |
| `nrs_irn` | invoices, audit_log | NRS Invoice Reference Number |
| `lga` | business_entities | Local Government Area |
| `state_irs` | paye_records | State Inland Revenue Service |
| `emtl` | bank_statement_line | Electronic Money Transfer Levy |

### 9.3 Currency & Amount Fields

| Convention | Description |
|------------|-------------|
| `DECIMAL(15,2)` | Standard monetary amounts in Naira |
| `DECIMAL(18,2)` | Large amounts (balances, totals) |
| `DECIMAL(5,2)` | Percentages (tax rates, discounts) |
| All amounts | Stored in Naira (NGN), not Kobo |

---

## 10. Referential Integrity Rules

### 10.1 Cascade Rules

| Relationship | On Delete | Rationale |
|--------------|-----------|-----------|
| Organization → Business Entity | CASCADE | Entity cannot exist without organization |
| Business Entity → All Financial Data | CASCADE | Financial data is scoped to entity |
| User → Audit Log | SET NULL | Preserve audit trail, mark user as deleted |
| Invoice → Invoice Lines | CASCADE | Lines are part of invoice |
| Payroll Run → Payroll Items | CASCADE | Items are part of run |
| Journal Entry → Journal Lines | CASCADE | Lines are part of entry |
| Parent Account → Child Account | SET NULL | Preserve hierarchy |

### 10.2 Constraints

| Constraint | Table | Description |
|------------|-------|-------------|
| `CHECK(total_debit = total_credit)` | journal_entries | Balanced double-entry |
| `CHECK(debit_amount >= 0)` | journal_entry_line | No negative amounts |
| `UNIQUE(entity_id, account_code)` | chart_of_accounts | Unique codes per entity |
| `UNIQUE(entity_id, invoice_number)` | invoices | Unique invoice numbers |
| `wren_verified_by_id != created_by_id` | transactions | Maker-Checker SoD |

### 10.3 Indexes

All tables have indexes on:
- `entity_id` (entity scoping)
- `created_at` (temporal queries)
- Common filter columns (status, type, date)
- Foreign keys (automatic in most databases)

---

## Appendix: Database Statistics

| Module | Tables | Estimated Rows (Typical SME/Year) |
|--------|--------|----------------------------------|
| Core (Org/Entity/User) | 4 | < 100 |
| Accounting (COA, Journal) | 6 | 10,000 - 50,000 |
| Invoices & Transactions | 5 | 5,000 - 20,000 |
| Payroll | 8 | 1,000 - 5,000 |
| Tax Compliance | 5 | 500 - 2,000 |
| Bank Reconciliation | 5 | 5,000 - 20,000 |
| Audit Trail | 4 | 50,000 - 200,000 |
| **Total** | **~37** | **~300,000/year** |

---
*For internal use and regulatory compliance documentation*
