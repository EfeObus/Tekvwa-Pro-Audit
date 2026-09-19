# Tekvwa Pro Audit - Complete Accounting System Documentation

**Version:** 2.5.0  
**Last Updated:** January 27, 2026  
**Status:** Production-Ready  
**Market:** Nigerian Business Context

---

## Table of Contents

1. [System Architecture](#1-system-architecture)
2. [Core Accounting Modules](#2-core-accounting-modules)
3. [Bank Reconciliation (The Control Spine)](#3-bank-reconciliation-the-control-spine)
4. [Multi-Currency / FX Module](#4-multi-currency--fx-module)
5. [Budget Management](#5-budget-management)
6. [Nigerian Tax Integration](#6-nigerian-tax-integration)
7. [Month-End Close Workflow](#7-month-end-close-workflow)
8. [Database Design](#8-database-design)
9. [API Reference](#9-api-reference)
10. [Frontend Guide](#10-frontend-guide)
11. [Security & Compliance](#11-security--compliance)
12. [Audit Trail & Controls](#12-audit-trail--controls)
13. [SKU Feature Matrix](#13-sku-feature-matrix)

---

## 1. System Architecture

### Big Picture Data Flow

```
Users
 ↓
Transactions (Sales, Expenses, Payroll, Inventory)
 ↓
Sub-ledgers (AR, AP, Assets, Payroll)
 ↓
GENERAL LEDGER (Single Source of Truth)
 ↓
Bank GL Accounts
 ↓
BANK RECONCILIATION
 ↓
External Bank Statements (Reality)
```

### Core Philosophy

A complete accounting system must:

1. **Record transactions** - Day-to-day business activity
2. **Classify them correctly** - Accounts, taxes, periods
3. **Prove accuracy** - Controls, reconciliation, audit trail

**Bank reconciliation is the proof layer that validates everything else.**

---

## 2. Core Accounting Modules

### 2.1 Chart of Accounts (COA)

The foundation of the accounting system. Every other module depends on this.

**Nigerian Standard Account Structure:**

| Range | Type | Examples |
|-------|------|----------|
| 1000-1999 | Assets | Cash, Bank, AR, Inventory, Fixed Assets |
| 2000-2999 | Liabilities | AP, VAT Payable, WHT Payable, Loans |
| 3000-3999 | Equity | Share Capital, Retained Earnings |
| 4000-4999 | Revenue | Sales, Service Income, Interest |
| 5000-5999 | Expenses | COGS, Salaries, Bank Charges, EMTL |

**Key Account Codes:**

```python
# Bank Accounts (Link to Bank Reconciliation)
1120 - Bank Accounts (Header)
1121 - GTBank Current Account
1122 - Zenith Bank Current Account
1123 - UBA Domiciliary Account

# Tax Accounts (Nigerian Specific)
1160 - VAT Receivable (Input VAT)
1170 - WHT Receivable
2130 - VAT Payable (Output VAT)
2140 - WHT Payable
2150 - PAYE Payable
2160 - Pension Payable

# Expense Accounts (Bank Charges)
5100 - Bank Charges
5200 - EMTL Expense (Electronic Money Transfer Levy)
5210 - Stamp Duty Expense
```

**API Endpoints:**

```
GET  /api/v1/entities/{entity_id}/accounting/chart-of-accounts
POST /api/v1/entities/{entity_id}/accounting/chart-of-accounts
GET  /api/v1/entities/{entity_id}/accounting/chart-of-accounts/tree
POST /api/v1/entities/{entity_id}/accounting/chart-of-accounts/initialize
```

### 2.2 General Ledger (GL)

The central accounting engine. All modules post to the GL.

**Features:**

- Double-entry enforcement (debits must equal credits)
- Journal entries (manual & automated)
- Period-based posting
- Immutable audit trail
- Account balance tracking (YTD debit/credit)

**Journal Entry Types:**

```python
MANUAL = "manual"           # User-created entries
SALES = "sales"             # From invoices
PURCHASE = "purchase"       # From bills
RECEIPT = "receipt"         # Customer payments
PAYMENT = "payment"         # Vendor payments
PAYROLL = "payroll"         # Salary postings
DEPRECIATION = "depreciation"
TAX_ADJUSTMENT = "tax_adjustment"
BANK_RECONCILIATION = "bank_reconciliation"  # ← From reconciliation
INVENTORY_ADJUSTMENT = "inventory_adjustment"
CLOSING_ENTRY = "closing_entry"
```

**Connection to Bank Reconciliation:**

- Reconciliation compares GL bank balance vs bank statement
- Reconciliation creates adjusting journal entries
- Locked reconciliations lock GL periods

### 2.3 Accounts Receivable (AR)

**Features:**
- Customer management
- Invoice generation
- Receipt recording
- Credit notes
- WHT deduction handling

**Posting Rules:**

```
Invoice Created:
  Dr Accounts Receivable (1130)
  Cr Sales Revenue (4100)
  Cr VAT Payable (2130) - if applicable

Payment Received:
  Dr Bank (1120)
  Cr Accounts Receivable (1130)

WHT Deducted by Customer:
  Dr Bank (1120) - Net amount
  Dr WHT Receivable (1170) - WHT amount
  Cr Accounts Receivable (1130) - Gross amount
```

**Connection to Bank Reconciliation:**

- Customer payments appear on bank statement
- Reconciliation confirms payment actually hit the bank
- Unmatched receipts = deposits in transit or errors
- WHT-deducted payments reconciled net, tax posted separately

### 2.4 Accounts Payable (AP)

**Features:**
- Vendor management
- Bill recording
- Payment processing
- WHT application

**Posting Rules:**

```
Bill Recorded:
  Dr Expense/Inventory
  Dr VAT Receivable (1160) - if applicable
  Cr Accounts Payable (2110)

Payment Made:
  Dr Accounts Payable (2110)
  Cr Bank (1120)
  Cr WHT Payable (2140) - if WHT applied
```

**Connection to Bank Reconciliation:**

- Supplier payments must appear on bank statement
- Outstanding cheques remain unreconciled
- Bank charges deducted automatically reconciled
- Reversals detected and corrected

### 2.5 Cash & Bank Management

**Features:**
- Multiple bank accounts (Current, Savings, Domiciliary)
- Inter-bank transfers
- Currency support (NGN, USD, GBP, EUR)
- API integrations (Mono, Okra, Stitch)

**Connection to Bank Reconciliation:**

- Primary module reconciliation operates on
- Transfers require two reconciliations (source & destination)
- FX differences identified during reconciliation

### 2.6 Tax Management (Nigeria-Specific)

**VAT (7.5%):**
- Output VAT on sales
- Input VAT on purchases (recoverable)
- Monthly filing to FIRS

**WHT Rates:**
- Professional services: 10%
- Contracts: 5%
- Directors' fees: 10%
- Dividends: 10%

**Other Taxes:**
- EMTL: ₦50 on electronic inflows > ₦10,000
- Stamp Duty: ₦50 on electronic transfers > ₦10,000
- CIT: 0%/20%/30% based on company size
- TET: 2.5% of assessable profits
- Development Levy: 4% for large companies

**Connection to Bank Reconciliation:**

- EMTL & stamp duty often appear only in bank statements
- Reconciliation auto-detects and posts tax entries
- WHT net receipts reconciled correctly
- Tax balances proven via bank activity

### 2.7 Fixed Assets & Depreciation

**Features:**
- Asset register
- Depreciation schedules (Straight-line, Reducing balance)
- Disposal tracking
- Capital gains calculation

**Connection to Bank Reconciliation:**

- Asset purchases paid via bank
- Reconciliation confirms asset payment cleared
- Prevents "ghost assets" not actually paid for

### 2.8 Inventory & COGS

**Features:**
- Stock tracking
- Purchase recording
- COGS calculation
- Write-off management

**Connection to Bank Reconciliation:**

- Supplier payments tied to inventory purchases
- Reconciliation validates cash outflow
- Flags unpaid inventory purchases

### 2.9 Payroll

**Features:**
- Salary processing
- PAYE calculation (2026 bands)
- Pension deductions (employer/employee)
- NHF / NSITF contributions
- Bulk payment generation

**Connection to Bank Reconciliation:**

- Salary bulk payments reconciled
- Statutory remittances confirmed
- Failed salary payments detected

---

## 3. Bank Reconciliation (The Control Spine)

### Where It Sits in the System

```
Sales / Expenses / Payroll / Inventory
            ↓
     Sub-ledgers (AR, AP, etc.)
            ↓
       General Ledger
            ↓
     Bank GL Account Balance
            ↓
   BANK RECONCILIATION
            ↓
   Real Bank Statement Balance
```

**Reconciliation is the ONLY place internal records meet external reality.**

### What Bank Reconciliation Does

1. **Validates cash accuracy** - Book balance vs bank balance
2. **Detects missing entries** - Charges not recorded
3. **Detects duplicate entries** - Errors in posting
4. **Detects fraud or errors** - Unauthorized transactions
5. **Forces proper period closing** - No close without reconciliation
6. **Produces audit evidence** - Reconciliation statements

### Bank Statement Import Sources

| Source | Method | Nigerian Banks |
|--------|--------|----------------|
| Mono API | Direct connection | All major banks |
| Okra API | Direct connection | All major banks |
| Stitch API | Direct connection | Select banks |
| CSV Upload | Manual import | Any bank |
| Excel Upload | Manual import | Any bank |
| MT940 Upload | SWIFT format | Corporate accounts |
| PDF OCR | Document scanning | Legacy statements |

### Transaction Matching Engine

**Matching Types:**

```python
EXACT = "exact"              # Amount + Date match exactly
FUZZY = "fuzzy"              # Within tolerance (±3 days, ±0.01%)
ONE_TO_MANY = "one_to_many"  # 1 bank txn matches multiple book entries
MANY_TO_ONE = "many_to_one"  # Multiple bank txns match 1 book entry
RULE_BASED = "rule_based"    # Custom matching rules
MANUAL = "manual"            # User-confirmed match
```

**Matching Algorithm:**

```python
for each bank_txn:
    if exact_match(ledger_txn):
        match()
    elif fuzzy_match(±3 days, ±0.01%):
        suggest()
    elif many_to_one_possible():
        partial_match()
    else:
        mark_unreconciled()
```

### Nigerian Charge Auto-Detection

The system automatically detects and classifies:

| Charge Type | Detection Pattern | GL Account |
|-------------|-------------------|------------|
| EMTL | "EMTL", "E-Levy", ₦50 amount | 5200 |
| Stamp Duty | "Stamp Duty", "SD", ₦50 amount | 5210 |
| SMS Fee | "SMS Alert", "Notification" | 5100 |
| VAT on Charges | "VAT" in charge context | 1160 |
| WHT | "WHT", "Withholding" | 1170 |
| NIP Fee | "NIP", "NIBSS", "Transfer" | 5100 |
| POS Fee | "POS", "Card Transaction" | 5100 |
| Maintenance | "COT", "Maintenance Fee" | 5100 |

### GL Journal Entry Creation

When adjustments are posted, the system creates proper double-entry journals:

```
EMTL Charge (₦50):
  Dr EMTL Expense (5200)    ₦50
  Cr Bank (1120)            ₦50

Stamp Duty (₦50):
  Dr Stamp Duty (5210)      ₦50
  Cr Bank (1120)            ₦50

Interest Earned (₦1,000):
  Dr Bank (1120)            ₦1,000
  Cr Interest Income (4200) ₦1,000

VAT on Bank Charges (₦75):
  Dr VAT Receivable (1160)  ₦75
  Cr Bank (1120)            ₦75
```

### Reconciliation Workflow

```
1. SELECT BANK + PERIOD
        ↓
2. IMPORT STATEMENT
   - CSV upload
   - API sync
   - Manual entry
        ↓
3. AUTO-MATCH
   - Run matching engine
   - Review suggested matches
   - Confirm/reject matches
        ↓
4. RESOLVE EXCEPTIONS
   - Unmatched bank items → Add to books
   - Unmatched book items → Outstanding cheques/deposits
   - Charges → Auto-detect and create adjustments
        ↓
5. GENERATE ADJUSTING JOURNALS
   - Create GL entries for charges
   - Post to correct accounts
        ↓
6. CONFIRM BALANCES
   - Adjusted bank balance = Adjusted book balance
   - Difference must be ZERO
        ↓
7. SUBMIT FOR REVIEW
   - Manager approval required
        ↓
8. APPROVE & LOCK
   - Lock reconciliation
   - Lock related GL period
```

### Outstanding Items Management

**Types:**

- **Deposits in Transit**: Recorded in books, not yet on bank statement
- **Outstanding Cheques**: Issued but not yet cleared
- **Bank Errors**: Discrepancies to investigate
- **Book Errors**: Corrections needed

**Carry-Forward:**

Outstanding items automatically carry forward to the next reconciliation period.

---

## 4. Multi-Currency / FX Module

> **SKU Requirement:** Professional tier or higher (`Feature.MULTI_CURRENCY`)

The Foreign Exchange module provides IAS 21 compliant multi-currency support for Nigerian businesses dealing with foreign transactions.

### Functional Currency

Each business entity has a designated **functional currency** (typically NGN for Nigerian entities). All foreign currency transactions are translated to the functional currency.

### Supported Currencies

| Currency | Code | Description |
|----------|------|-------------|
| Nigerian Naira | NGN | Default functional currency |
| US Dollar | USD | Common for imports/exports |
| Euro | EUR | European trade |
| British Pound | GBP | UK trade |

### FX Transaction Flow

```
Foreign Currency Transaction
        ↓
Record at Spot Rate (Transaction Date)
        ↓
Monitor Rate Changes
        ↓
Settlement/Period-End
        ↓
Calculate FX Gain/Loss
        ↓
Post to GL (7100/7200 accounts)
```

### Realized FX Gains/Losses

When foreign currency transactions are settled:

```
Original USD Invoice: $1,000 @ 1,500 = ₦1,500,000
Payment Rate: $1,000 @ 1,520 = ₦1,520,000
FX Gain: ₦20,000

Journal Entry:
Dr Cash (1010)           ₦1,520,000
Cr AR (1200)             ₦1,500,000
Cr Realized FX Gain (7100)  ₦20,000
```

### Period-End Revaluation

Monetary items (AR, AP, Cash) are revalued at closing rates:

```
Open USD AR: $5,000 @ 1,500 = ₦7,500,000
Closing Rate: 1,480 NGN/USD
Revalued: $5,000 @ 1,480 = ₦7,400,000
Unrealized Loss: ₦100,000

Journal Entry:
Dr Unrealized FX Loss (7210)  ₦100,000
Cr Accounts Receivable (1200) ₦100,000
```

### GL Account Structure

| Account | Name | Type |
|---------|------|------|
| 7100 | Realized FX Gain | Income |
| 7110 | Unrealized FX Gain | Income |
| 7200 | Realized FX Loss | Expense |
| 7210 | Unrealized FX Loss | Expense |

### API Endpoints

```
GET  /api/v1/entities/{entity_id}/fx/exchange-rates
POST /api/v1/entities/{entity_id}/fx/exchange-rates
POST /api/v1/entities/{entity_id}/fx/convert
POST /api/v1/entities/{entity_id}/fx/realized-gain-loss
POST /api/v1/entities/{entity_id}/fx/revaluation
GET  /api/v1/entities/{entity_id}/fx/exposure-report
```

**Connection to Bank Reconciliation:**
- FX differences detected during bank import reconciliation
- Multi-currency bank accounts reconciled in transaction currency
- FX gains/losses auto-calculated and posted

---

## 5. Budget Management

> **SKU Requirement:** Professional tier or higher (`Feature.BUDGET_MANAGEMENT`)

The Budget Module enables comprehensive financial planning with variance analysis and rolling forecasts.

### Budget Structure

```
Budget (FY2026)
├── Budget Periods (Monthly/Quarterly/Annual)
│   ├── Revenue Line Items
│   ├── Expense Line Items
│   └── CapEx Line Items
└── Budget Versions
    ├── v1 - Original
    └── v2 - Mid-year Revision
```

### Budget Status Lifecycle

```
DRAFT → SUBMITTED → PENDING_APPROVAL → APPROVED → ACTIVE
              ↓
          REJECTED → DRAFT (revision required)
```

### Variance Analysis

| Variance Type | Formula | Favorable When |
|---------------|---------|----------------|
| Revenue | Actual - Budget | Actual > Budget |
| Expense | Budget - Actual | Actual < Budget |
| Percentage | (Variance / Budget) × 100 | Depends on type |

### Variance Example

```
Q1 Sales Revenue:
Budget:  ₦100,000,000
Actual:  ₦108,000,000
Variance: ₦8,000,000 (8% Favorable)

Q1 Salaries Expense:
Budget:  ₦30,000,000
Actual:  ₦32,000,000
Variance: -₦2,000,000 (6.67% Unfavorable)
```

### Approval Workflows

Supports M-of-N approval with multiple modes:

| Mode | Description |
|------|-------------|
| **Sequential** | Approvers must approve in order |
| **Parallel** | All approvers can approve simultaneously |
| **Any** | Any single approver can approve |

### Rolling Forecasts

Combine actuals with projections:

```
YTD Actual (Jan-Jun): ₦225,000,000
Original Annual Budget: ₦500,000,000
Remaining Budget (Jul-Dec): ₦275,000,000
Adjusted Forecast Q3: ₦140,000,000
Adjusted Forecast Q4: ₦165,000,000
Forecast Annual: ₦530,000,000 (+6%)
```

### API Endpoints

```
POST /api/v1/entities/{entity_id}/budgets
GET  /api/v1/entities/{entity_id}/budgets
GET  /api/v1/entities/{entity_id}/budgets/{id}
POST /api/v1/entities/{entity_id}/budgets/{id}/line-items
POST /api/v1/entities/{entity_id}/budgets/{id}/submit
POST /api/v1/entities/{entity_id}/budgets/{id}/approve
GET  /api/v1/entities/{entity_id}/budgets/{id}/variance
POST /api/v1/entities/{entity_id}/budgets/{id}/forecast
```

**Connection to GL:**
- Variance analysis pulls actual amounts from GL
- Budget accounts linked to Chart of Accounts
- Department/cost center budgets tied to accounting dimensions

---

## 6. Nigerian Tax Integration

### VAT Integration

```python
# From Invoice
Invoice Total: ₦1,000,000
VAT (7.5%):    ₦75,000

# Posting
Dr AR                     ₦1,075,000
Cr Revenue               ₦1,000,000
Cr VAT Payable              ₦75,000

# Bank Reconciliation confirms receipt
```

### WHT Credit Notes

```python
# Customer deducts WHT (10%)
Invoice: ₦100,000
WHT (10%): ₦10,000
Received: ₦90,000

# Posting
Dr Bank            ₦90,000
Dr WHT Receivable  ₦10,000
Cr AR             ₦100,000

# Reconciliation validates ₦90,000 receipt
```

### EMTL Auto-Posting

```python
# Bank statement shows EMTL
Amount: ₦50
Description: "EMTL CHARGE"

# System auto-detects and suggests
Dr EMTL Expense (5200)  ₦50
Cr Bank (1120)          ₦50
```

---

## 5. Month-End Close Workflow

### Enforced Order

```
1. POST ALL TRANSACTIONS
   - All drafts must be posted
   - No pending entries
        ↓
2. RECONCILE ALL BANK ACCOUNTS
   - Every bank account reconciled
   - Reconciliation approved
   - All adjustments posted to GL
        ↓
3. REVIEW OUTSTANDING ITEMS
   - Outstanding cheques documented
   - Deposits in transit explained
        ↓
4. LOCK THE PERIOD
   - Admin approval required
   - Period becomes read-only
        ↓
5. GENERATE FINANCIAL STATEMENTS
   - Trial balance
   - Income statement
   - Balance sheet
   - Cash flow statement
```

### Period Close Checklist

The system validates before closing:

- [ ] All journal entries posted
- [ ] All bank accounts reconciled up to period end
- [ ] All reconciliation adjustments posted to GL
- [ ] Trial balance is balanced
- [ ] Outstanding items reviewed and documented

**If any check fails → Period cannot be closed**

### API Endpoint

```
POST /api/v1/entities/{entity_id}/accounting/periods/{period_id}/close

Response:
{
  "success": false,
  "blocking_issues": [
    "GTBank (1234): Reconciled to 2026-01-15 only, need to 2026-01-31",
    "3 unposted journal entries"
  ]
}
```

---

## 6. Database Design

### Key Tables

```sql
-- Chart of Accounts
chart_of_accounts (
  id, entity_id, account_code, account_name,
  account_type, account_sub_type, normal_balance,
  parent_id, level, is_header, current_balance,
  is_tax_account, tax_type, tax_rate,
  is_reconcilable, bank_account_id
)

-- Journal Entries
journal_entries (
  id, entity_id, entry_date, reference,
  description, entry_type, status,
  total_debit, total_credit,
  fiscal_period_id, source_type, source_id
)

journal_entry_lines (
  id, journal_entry_id, account_code,
  account_id, description,
  debit_amount, credit_amount, line_number
)

-- Bank Reconciliation
bank_accounts (
  id, entity_id, bank_name, account_name,
  account_number, account_type, currency,
  opening_balance, current_balance,
  gl_account_code, last_reconciled_date,
  mono_account_id, okra_account_id, stitch_account_id
)

bank_statement_transactions (
  id, bank_account_id, reconciliation_id,
  transaction_date, description, reference,
  debit_amount, credit_amount, running_balance,
  match_status, match_type, match_confidence,
  is_bank_charge, is_emtl, is_stamp_duty, is_vat, is_wht
)

bank_reconciliations (
  id, bank_account_id, reconciliation_date,
  period_start, period_end,
  statement_opening_balance, statement_closing_balance,
  book_opening_balance, book_closing_balance,
  adjusted_bank_balance, adjusted_book_balance,
  difference, status,
  deposits_in_transit, outstanding_checks, bank_charges
)

reconciliation_adjustments (
  id, reconciliation_id, adjustment_type,
  amount, description, affects_bank, affects_book,
  gl_account_code, is_posted, journal_entry_id
)

-- Fiscal Periods
fiscal_periods (
  id, entity_id, fiscal_year_id,
  period_name, start_date, end_date,
  status, bank_reconciled, closed_at
)
```

### Critical Relationships

```
One bank account → many bank transactions
One reconciliation → many matches
One match → many bank txns + many GL txns
One adjustment → one journal entry (when posted)
One fiscal period → many journal entries
```

---

## 7. API Reference

### Chart of Accounts

```
GET    /api/v1/entities/{entity_id}/accounting/chart-of-accounts
POST   /api/v1/entities/{entity_id}/accounting/chart-of-accounts
GET    /api/v1/entities/{entity_id}/accounting/chart-of-accounts/{id}
PUT    /api/v1/entities/{entity_id}/accounting/chart-of-accounts/{id}
GET    /api/v1/entities/{entity_id}/accounting/chart-of-accounts/tree
POST   /api/v1/entities/{entity_id}/accounting/chart-of-accounts/initialize
```

### Journal Entries

```
GET    /api/v1/entities/{entity_id}/accounting/journal-entries
POST   /api/v1/entities/{entity_id}/accounting/journal-entries
GET    /api/v1/entities/{entity_id}/accounting/journal-entries/{id}
POST   /api/v1/entities/{entity_id}/accounting/journal-entries/{id}/post
POST   /api/v1/entities/{entity_id}/accounting/journal-entries/{id}/reverse
```

### Financial Reports

```
GET    /api/v1/entities/{entity_id}/accounting/reports/trial-balance
GET    /api/v1/entities/{entity_id}/accounting/reports/income-statement
GET    /api/v1/entities/{entity_id}/accounting/reports/balance-sheet
GET    /api/v1/entities/{entity_id}/accounting/reports/account-ledger/{account_id}
```

### Bank Reconciliation

```
# Bank Accounts
GET    /bank-reconciliation/accounts
POST   /bank-reconciliation/accounts
GET    /bank-reconciliation/accounts/{id}
PATCH  /bank-reconciliation/accounts/{id}
POST   /bank-reconciliation/accounts/{id}/import/csv
POST   /bank-reconciliation/accounts/{id}/sync

# Reconciliations
GET    /bank-reconciliation/reconciliations
POST   /bank-reconciliation/reconciliations
GET    /bank-reconciliation/reconciliations/{id}
GET    /bank-reconciliation/reconciliations/{id}/transactions
GET    /bank-reconciliation/reconciliations/{id}/adjustments
GET    /bank-reconciliation/reconciliations/{id}/unmatched-items

# Matching
POST   /bank-reconciliation/reconciliations/{id}/auto-match
POST   /bank-reconciliation/reconciliations/{id}/manual-match
POST   /bank-reconciliation/transactions/{id}/unmatch

# Adjustments
POST   /bank-reconciliation/reconciliations/{id}/adjustments
POST   /bank-reconciliation/reconciliations/{id}/adjustments/auto-create-charges
POST   /bank-reconciliation/reconciliations/{id}/create-journal-entries
DELETE /bank-reconciliation/adjustments/{id}

# Workflow
POST   /bank-reconciliation/reconciliations/{id}/submit
POST   /bank-reconciliation/reconciliations/{id}/approve
POST   /bank-reconciliation/reconciliations/{id}/reject

# Period Validation
GET    /bank-reconciliation/validate-for-period-close?period_end_date=2026-01-31

# Reporting
GET    /bank-reconciliation/summary
GET    /bank-reconciliation/reconciliations/{id}/report
GET    /bank-reconciliation/accounts/{id}/outstanding-items?as_of_date=2026-01-31
```

### Period Management

```
GET    /api/v1/entities/{entity_id}/accounting/fiscal-years
POST   /api/v1/entities/{entity_id}/accounting/fiscal-years
GET    /api/v1/entities/{entity_id}/accounting/periods
GET    /api/v1/entities/{entity_id}/accounting/periods/{id}/close-checklist
POST   /api/v1/entities/{entity_id}/accounting/periods/{id}/close
```

---

## 8. Frontend Guide

### Accounting Module (accounting.html)

**Features:**
- Chart of Accounts tree view with hierarchy
- Account details panel
- Journal entry creation/posting
- Fiscal period management
- Financial reports (Trial Balance, P&L, Balance Sheet)

**Key Actions:**
- Initialize Default COA
- Create/Edit accounts
- Create journal entries
- View account ledger
- Close periods

### Bank Reconciliation Module (bank_reconciliation.html)

**Features:**
- Bank account management
- Statement import (CSV, API sync)
- Transaction matching interface
- Adjustment management
- Reconciliation workflow

**Key Actions:**
- Add bank account (Nigerian banks dropdown)
- Import CSV statements
- Sync from Mono/Okra/Stitch
- Auto-match transactions
- Auto-detect bank charges
- Post adjustments to GL
- Submit for review
- Approve/reject reconciliation

---

## 9. Security & Compliance

### NDPA/NITDA 2023 Compliance

- PII encryption (AES-256-GCM)
- Field-level encryption for sensitive data
- Nigerian data sovereignty (geo-fencing)
- Right-to-erasure support

### Access Control

- Role-based access (Admin, Accountant, Manager, Auditor)
- Entity-level data isolation
- Auditor read-only enforcement

### Audit Trail

- All changes logged with timestamp and user
- Immutable journal entries
- Hash-chain verification for ledger integrity

---

## 10. Audit Trail & Controls

### What Auditors Ask

1. Are bank accounts reconciled?
2. Are periods locked?
3. Are reconciling items explained?
4. Is there an audit trail for all changes?
5. Can transactions be reproduced?

### Evidence Provided

- Bank reconciliation statements
- Outstanding items reports
- Adjustment journals
- Period close documentation
- Trial balance at period end

### Final Mental Model

```
Transactions record INTENT
Ledger records ACCOUNTING
Bank statement records REALITY
Bank reconciliation proves TRUTH
```

**That's why reconciliation is the centerpiece of a full accounting system.**

---

## 11. Sub-Ledger to GL Integration

This section documents how all sub-ledger modules post to the General Ledger,
ensuring complete integration where "every naira in the bank is explained."

### 11.1 Invoice GL Posting

When an invoice is finalized (`finalize_invoice()`):

```
Dr Accounts Receivable (1130)    [Total Amount]
Cr Sales Revenue (4100)          [Base Amount]
Cr VAT Payable (2130)            [VAT Amount]
```

**Service:** `app/services/invoice_service.py`  
**Method:** `_post_invoice_to_gl()`

### 11.2 Payment Receipt GL Posting

When a customer payment is recorded (`record_payment()`):

```
Dr Bank (linked GL account)      [Payment Amount]
Dr WHT Receivable (1170)         [WHT Deducted by Customer]
Cr Accounts Receivable (1130)    [Total Payment]
```

**Service:** `app/services/invoice_service.py`  
**Method:** `_post_payment_to_gl()`

### 11.3 Vendor Bill GL Posting (Expense Recording)

When an expense transaction is created:

```
Dr Expense Account (5xxx)        [Base Amount]
Dr VAT Input (1180)              [VAT if recoverable]
Cr Accounts Payable (2110)       [Total - WHT]
Cr WHT Payable (2140)            [WHT if applicable]
```

**Service:** `app/services/transaction_service.py`  
**Method:** `_post_expense_to_gl()`

### 11.4 Vendor Payment GL Posting

When paying a vendor (`record_vendor_payment()`):

```
Dr Accounts Payable (2110)       [Payment + WHT]
Cr Bank (linked GL account)      [Payment Amount]
Cr WHT Payable (2140)            [WHT Withheld]
```

**Service:** `app/services/transaction_service.py`  
**Method:** `record_vendor_payment()`

### 11.5 Payroll GL Posting

When payroll is processed (`process_payroll()`):

```
Dr Salary Expense (5200)         [Gross Salaries]
Dr Employer Pension (5210)       [Employer 10%]
Dr Employer NSITF (5220)         [Employer 1%]
Cr PAYE Payable (2150)           [Employee PAYE]
Cr Pension Payable (2160)        [Employee 8% + Employer 10%]
Cr NHF Payable (2170)            [NHF 2.5%]
Cr NSITF Payable (2180)          [Employer 1%]
Cr Salaries Payable (2190)       [Net Pay]
```

**Service:** `app/services/payroll_service.py`  
**Method:** `_post_payroll_to_gl()`

### 11.6 Depreciation GL Posting

When depreciation runs (`run_depreciation()`):

```
Dr Depreciation Expense (5300)       [Monthly Depreciation]
Cr Accumulated Depreciation (1240)   [Monthly Depreciation]
```

**Service:** `app/services/fixed_asset_service.py`  
**Method:** `_post_depreciation_to_gl()`

### 11.7 Asset Disposal GL Posting

When an asset is disposed (`dispose_asset()`):

```
# Remove Asset
Dr Accumulated Depreciation (1240)   [Total Depreciation]
Dr Bank/Receivable (proceeds)        [Disposal Proceeds]
Cr Fixed Assets (1200)               [Original Cost]

# Record Gain/Loss
Dr/Cr Gain/Loss on Disposal (4200/5350)   [Net Gain or Loss]
```

**Service:** `app/services/fixed_asset_service.py`  
**Method:** `_post_disposal_to_gl()`

### 11.8 Inventory COGS GL Posting

When inventory is sold (`record_sale()`):

```
Dr Cost of Goods Sold (5000)     [Quantity x Unit Cost]
Cr Inventory (1210)              [Quantity x Unit Cost]
```

When inventory is written off (`create_write_off()`):

```
Dr Write-off Expense (5400)      [Write-off Value]
Cr Inventory (1210)              [Write-off Value]
```

**Service:** `app/services/inventory_service.py`  
**Methods:** `_post_cogs_to_gl()`, `_post_writeoff_to_gl()`

### 11.9 Cash Flow Statement Report

The system generates a Cash Flow Statement using the indirect method:

**API Endpoint:** `GET /api/v1/entities/{entity_id}/accounting/reports/cash-flow-statement`

**Sections:**
1. **Operating Activities** - Net income adjusted for non-cash items and working capital
2. **Investing Activities** - Asset purchases, disposals, investments
3. **Financing Activities** - Debt, equity, dividends

**Service:** `app/services/accounting_service.py`  
**Method:** `get_cash_flow_statement()`

---

## 12. Bank-GL Integration

### 12.1 Bank Account GL Linkage

Every bank account must be linked to a GL account for proper reconciliation.

**Validation Endpoint:** `GET /api/v1/entities/{entity_id}/bank/accounts/{account_id}/gl-linkage`

**Bulk Validation:** `GET /api/v1/entities/{entity_id}/bank/gl-linkage/validate-all`

**Link Bank to GL:** `POST /api/v1/entities/{entity_id}/bank/accounts/{account_id}/link-gl`

### 12.2 GL Transaction Matching

Bank reconciliation can match statement transactions directly to GL journal entries:

**Get GL Transactions:** `GET /api/v1/entities/{entity_id}/bank/reconciliations/{id}/gl-transactions`

**Manual Match:** `POST /api/v1/entities/{entity_id}/bank/reconciliations/{id}/match-to-gl`

**Auto Match to GL:** `POST /api/v1/entities/{entity_id}/bank/reconciliations/{id}/auto-match-gl`

This creates a complete audit trail from bank statement to GL entry.

---

## Summary

When the system is fully connected:

Every naira in the bank is explained  
Every difference is justified  
Every period is defensible  
The accounting system is trustworthy  

### GL Account Codes Reference

| Code | Account Name | Type |
|------|-------------|------|
| 1120 | Bank | Asset |
| 1130 | Accounts Receivable | Asset |
| 1170 | WHT Receivable | Asset |
| 1180 | VAT Receivable (Input) | Asset |
| 1200 | Fixed Assets | Asset |
| 1210 | Inventory | Asset |
| 1240 | Accumulated Depreciation | Contra Asset |
| 2110 | Accounts Payable | Liability |
| 2130 | VAT Payable (Output) | Liability |
| 2140 | WHT Payable | Liability |
| 2150 | PAYE Payable | Liability |
| 2160 | Pension Payable | Liability |
| 2170 | NHF Payable | Liability |
| 2180 | NSITF Payable | Liability |
| 2190 | Salaries Payable | Liability |
| 4100 | Sales Revenue | Revenue |
| 4200 | Gain on Asset Disposal | Revenue |
| 5000 | Cost of Goods Sold | Expense |
| 5100 | General Expense | Expense |
| 5200 | Salary Expense | Expense |
| 5210 | Employer Pension | Expense |
| 5220 | Employer NSITF | Expense |
| 5300 | Depreciation Expense | Expense |
| 5350 | Loss on Asset Disposal | Expense |
| 5400 | Inventory Write-off | Expense |

---

## 13. Financial Reports UI (v2.4.0)

### 13.1 Cash Flow Statement (Indirect Method)

The Cash Flow Statement is now available in the accounting.html Financial Reports tab.

**Location:** `templates/accounting.html` → Reports Tab → Report Type: "Cash Flow Statement (Indirect)"

**API Endpoint:** `GET /api/v1/entities/{entity_id}/accounting/reports/cash-flow-statement`

**Display Sections:**
1. **Operating Activities** - Net income, adjustments for non-cash items, working capital changes
2. **Investing Activities** - Asset purchases, disposals
3. **Financing Activities** - Debt, equity, dividends
4. **Summary** - Beginning cash, net change, ending cash

### 13.2 AR/AP Aging Reports

Aging reports with GL reconciliation are now accessible from the accounting module.

**Location:** `templates/accounting.html` → Reports Tab → Report Type: "AR Aging Report" or "AP Aging Report"

**API Endpoints:**
- AR: `GET /api/v1/entities/{entity_id}/reports/aging?report_type=receivable`
- AP: `GET /api/v1/entities/{entity_id}/reports/aging?report_type=payable`

**Display Features:**
- Summary cards: Total Outstanding, Total Overdue, Overdue %, GL Balance
- Aging buckets table: Current, 1-30, 31-60, 61-90, Over 90 days
- Color-coded severity indicators
- Automated recommendations

---

## 14. Intercompany Transactions (v2.4.0)

### 14.1 Overview

Intercompany transactions track transfers between entities in the same group for consolidation purposes.

**Model:** `app/models/advanced_accounting.py` → `IntercompanyTransaction`

### 14.2 API Endpoints

```
POST /api/v1/advanced/intercompany              # Create intercompany transaction
GET  /api/v1/advanced/intercompany              # List transactions with filters
POST /api/v1/advanced/intercompany/eliminate    # Mark for consolidation elimination
GET  /api/v1/advanced/intercompany/summary      # Balance summary by group
```

### 14.3 Transaction Types

- `sale` - Intercompany sale of goods/services
- `purchase` - Intercompany purchase
- `loan` - Intercompany loan
- `dividend` - Intercompany dividend
- `management_fee` - Management fee allocation

### 14.4 Elimination for Consolidation

Intercompany transactions can be marked as "eliminated" during consolidated financial statement preparation.

```json
POST /api/v1/advanced/intercompany/eliminate
{
  "transaction_ids": ["uuid1", "uuid2"],
  "elimination_date": "2026-01-31"
}
```

---

## 15. Period Lock Hard Enforcement (v2.4.0)

### 15.1 Overview

The system now enforces strict period controls with differentiated error messages.

**Service:** `app/services/accounting_service.py`

### 15.2 Period Status Validation

When creating/posting/reversing journal entries, the system checks:

| Period Status | Action | Result |
|---------------|--------|--------|
| OPEN | Create/Post/Reverse | Yes Allowed |
| CLOSED | Create/Post/Reverse | No "Reopen the period or use a different date" |
| LOCKED | Create/Post/Reverse | No "Period has been permanently locked" |

### 15.3 Error Messages

```python
# LOCKED Period
ValueError: "Cannot post to locked period 'January 2026'. Period has been permanently locked and no further entries are allowed."

# CLOSED Period  
ValueError: "Cannot post to closed period 'January 2026'. Reopen the period or use a different date."
```

### 15.4 Affected Methods

- `create_journal_entry()` - Validates before creating
- `post_journal_entry()` - Validates before posting
- `reverse_journal_entry()` - Validates reversal date period
---

## 16. SKU Feature Matrix (v2.5.0)

### Commercial Tier Structure

| Tier | Monthly Price (NGN) | Target Users |
|------|---------------------|--------------|
| **Core** | ₦25,000 - ₦75,000 | 1-5 users, SMEs |
| **Professional** | ₦150,000 - ₦400,000 | 5-25 users, Growing businesses |
| **Enterprise** | ₦1,000,000 - ₦5,000,000+ | 25+ users, Multi-entity |

### Accounting Module Feature Availability

| Feature | Core | Professional | Enterprise |
|---------|:----:|:------------:|:----------:|
| General Ledger | ✅ | ✅ | ✅ |
| Chart of Accounts | ✅ | ✅ | ✅ |
| Journal Entries | ✅ | ✅ | ✅ |
| Basic Invoicing | ✅ | ✅ | ✅ |
| Customer/Vendor Mgmt | ✅ | ✅ | ✅ |
| Basic Reports | ✅ | ✅ | ✅ |
| Basic Inventory | ✅ | ✅ | ✅ |
| Bank Reconciliation | ❌ | ✅ | ✅ |
| **Multi-Currency / FX** | ❌ | ✅ | ✅ |
| **Budget Management** | ❌ | ✅ | ✅ |
| Fixed Assets | ❌ | ✅ | ✅ |
| Payroll | ❌ | ✅ | ✅ |
| Advanced Reports | ❌ | ✅ | ✅ |
| E-Invoicing / NRS | ❌ | ✅ | ✅ |
| WORM Audit Vault | ❌ | ❌ | ✅ |
| Intercompany | ❌ | ❌ | ✅ |
| Multi-Entity | ❌ | ❌ | ✅ |
| Consolidation | ❌ | ❌ | ✅ |
| Segregation of Duties | ❌ | ❌ | ✅ |

### Feature Gate Implementation

All tier-restricted features use the `require_feature()` dependency:

```python
from app.dependencies import require_feature
from app.models.sku_enums import Feature

# Router-level enforcement
fx_feature_gate = require_feature([Feature.MULTI_CURRENCY])

router = APIRouter(
    prefix="/api/v1/entities/{entity_id}/fx",
    dependencies=[Depends(fx_feature_gate)],
)
```

### Error Response for Unauthorized Access

When a Core tier user attempts to access Professional/Enterprise features:

```json
HTTP 403 Forbidden
{
  "detail": "Feature 'multi_currency' requires Pro Audit Professional tier. Current tier: Core. Upgrade to access this feature."
}
```

### Intelligence Add-on Features

For ML/AI capabilities, the Intelligence Add-on (₦250,000 - ₦1,000,000/mo) is required:

| Feature | Standard | Advanced |
|---------|:--------:|:--------:|
| ML Anomaly Detection | ✅ | ✅ |
| Benford's Law Analysis | ✅ | ✅ |
| Z-Score Analysis | ✅ | ✅ |
| Fraud Detection | ✅ | ✅ |
| OCR Extraction | ✅ | ✅ |
| Predictive Forecasting | ✅ | ✅ |
| Custom ML Training | ❌ | ✅ |
| Behavioral Analytics | ❌ | ✅ |
| NLP Processing | ❌ | ✅ |

---

*Document End*