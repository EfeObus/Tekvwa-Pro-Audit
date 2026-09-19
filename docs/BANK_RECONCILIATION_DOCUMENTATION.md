# Bank Reconciliation Module Documentation

## Overview

Tekvwa Pro Audit's Bank Reconciliation module is a comprehensive, Nigerian-market-ready solution for reconciling bank statements with internal accounting records. It features automatic Nigerian bank charge detection (EMTL, Stamp Duty, VAT, WHT), integration with Nigerian open banking APIs (Mono, Okra, Stitch), and intelligent transaction matching algorithms.

## Table of Contents

1. [Features](#features)
2. [Architecture](#architecture)
3. [Database Models](#database-models)
4. [API Endpoints](#api-endpoints)
5. [Nigerian Banking Integration](#nigerian-banking-integration)
6. [Transaction Matching](#transaction-matching)
7. [Charge Detection](#charge-detection)
8. [Workflow Management](#workflow-management)
9. [Frontend Interface](#frontend-interface)
10. [Configuration](#configuration)
11. [Testing](#testing)

---

## Features

### Core Features
- **Bank Account Management**: Create and manage multiple bank accounts (Current, Savings, Domiciliary)
- **Statement Import**: CSV import with customizable column mapping
- **API Integration**: Mono, Okra, Stitch API support for automatic statement fetching
- **Transaction Matching**: 5 intelligent matching strategies (Exact, Fuzzy, Rule-based, One-to-Many, Many-to-One)
- **Nigerian Charge Detection**: Automatic detection of EMTL, Stamp Duty, VAT, WHT, SMS fees, POS fees
- **Adjustment Management**: Create, post, and manage reconciliation adjustments
- **Workflow**: Draft → In Progress → In Review → Approved/Rejected → Completed
- **Reporting**: Comprehensive reconciliation reports and summaries

### Nigerian-Specific Features
- Support for NUBAN (Nigeria Uniform Bank Account Number) format
- All major Nigerian commercial banks, merchant banks, microfinance banks
- EMTL (Electronic Money Transfer Levy) detection - ₦50 on transfers ≥₦10,000
- Stamp Duty detection - ₦50 on receipts
- VAT (7.5%) detection on banking services
- WHT (Withholding Tax) detection
- NIP (NIBSS Instant Payment) transaction support
- POS (Point of Sale) transaction handling
- USSD transaction recognition

---

## Architecture

### Service Layer

```
app/services/
├── bank_reconciliation_service.py   # Main service (~1,840 lines)
├── bank_integration_service.py      # API integrations
└── matching_engine.py               # Transaction matching algorithms
```

### Models

```
app/models/
└── bank_reconciliation.py           # Database models (~1,158 lines)
    ├── BankAccount
    ├── BankStatementTransaction
    ├── BankReconciliation
    ├── ReconciliationAdjustment
    ├── UnmatchedItem
    ├── BankChargeRule
    ├── MatchingRule
    └── BankStatementImport
```

### Router

```
app/routers/
└── bank_reconciliation.py           # API endpoints (~1,077 lines)
```

---

## Database Models

### BankAccount
Stores bank account information with API integration support.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| entity_id | UUID | Business entity reference |
| bank_name | String | Name of the bank |
| account_number | String | NUBAN account number (10 digits) |
| account_name | String | Account holder name |
| account_type | Enum | CURRENT, SAVINGS, DOMICILIARY, CORPORATE, ESCROW |
| currency | Enum | NGN, USD, GBP, EUR |
| opening_balance | Decimal | Initial balance |
| current_balance | Decimal | Current balance |
| mono_account_id | String | Mono API account identifier |
| okra_account_id | String | Okra API account identifier |
| stitch_account_id | String | Stitch API account identifier |
| gl_account_code | String | Linked GL account |
| is_active | Boolean | Active status |

### BankStatementTransaction
Individual bank statement transactions.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| bank_account_id | UUID | Reference to bank account |
| reconciliation_id | UUID | Reference to reconciliation (optional) |
| transaction_date | Date | Transaction date |
| value_date | Date | Value date |
| description | String | Transaction narration |
| reference | String | Transaction reference |
| debit_amount | Decimal | Debit amount |
| credit_amount | Decimal | Credit amount |
| balance | Decimal | Running balance |
| source | Enum | MONO_API, OKRA_API, CSV_IMPORT, MANUAL_ENTRY, etc. |
| match_status | Enum | UNMATCHED, AUTO_MATCHED, MANUAL_MATCHED, RECONCILED |
| match_confidence | Integer | Match confidence score (0-100) |
| is_bank_charge | Boolean | Is this a bank charge? |
| is_emtl | Boolean | Is EMTL charge? |
| is_stamp_duty | Boolean | Is Stamp Duty? |
| is_vat | Boolean | Is VAT charge? |
| is_wht | Boolean | Is WHT charge? |

### BankReconciliation
Reconciliation sessions.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| bank_account_id | UUID | Reference to bank account |
| reconciliation_date | Date | Date of reconciliation |
| period_start | Date | Statement period start |
| period_end | Date | Statement period end |
| statement_opening_balance | Decimal | Bank statement opening |
| statement_closing_balance | Decimal | Bank statement closing |
| book_opening_balance | Decimal | Book opening balance |
| book_closing_balance | Decimal | Book closing balance |
| adjusted_book_balance | Decimal | Book balance after adjustments |
| difference | Decimal | Reconciliation difference |
| status | Enum | DRAFT, IN_PROGRESS, IN_REVIEW, APPROVED, REJECTED, COMPLETED |
| matched_transactions | Integer | Count of matched transactions |
| unmatched_transactions | Integer | Count of unmatched transactions |
| bank_charges | Decimal | Total bank charges |

### ReconciliationAdjustment
Reconciliation adjustments.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| reconciliation_id | UUID | Reference to reconciliation |
| adjustment_type | Enum | See adjustment types below |
| amount | Decimal | Adjustment amount |
| description | String | Adjustment description |
| affects_bank | Boolean | Affects bank balance? |
| affects_book | Boolean | Affects book balance? |
| is_posted | Boolean | Posted to GL? |
| journal_entry_id | UUID | Linked journal entry |

**Adjustment Types:**
- `deposit_in_transit` - Deposits not yet credited by bank
- `outstanding_check` - Checks issued but not presented
- `bank_charges` - General bank charges
- `emtl` - Electronic Money Transfer Levy (₦50)
- `stamp_duty` - Stamp Duty (₦50)
- `vat` - Value Added Tax (7.5%)
- `wht` - Withholding Tax
- `interest_earned` - Interest income
- `sms_fee` - SMS alert fees
- `maintenance_fee` - Account maintenance
- `atm_fee` - ATM charges
- `transfer_fee` - Transfer charges
- `pos_fee` - POS charges
- `card_fee` - Card-related fees
- `bank_error` - Bank errors
- `book_error` - Accounting errors
- `other` - Other adjustments

---

## API Endpoints

### Bank Accounts

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/accounts` | List all bank accounts |
| POST | `/accounts` | Create new bank account |
| GET | `/accounts/{id}` | Get account details |
| PATCH | `/accounts/{id}` | Update account |
| POST | `/accounts/{id}/connect/mono` | Connect Mono API |
| POST | `/accounts/{id}/connect/okra` | Connect Okra API |
| POST | `/accounts/{id}/sync` | Sync transactions from API |
| POST | `/accounts/{id}/import/csv` | Import CSV statement |

### Reconciliations

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/reconciliations` | List reconciliations |
| POST | `/reconciliations` | Create reconciliation |
| GET | `/reconciliations/{id}` | Get reconciliation details |
| GET | `/reconciliations/{id}/transactions` | Get transactions |
| POST | `/reconciliations/{id}/auto-match` | Run auto-matching |
| POST | `/reconciliations/{id}/manual-match` | Manual match transactions |

### Workflow

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/reconciliations/{id}/submit` | Submit for review |
| POST | `/reconciliations/{id}/approve` | Approve reconciliation |
| POST | `/reconciliations/{id}/reject` | Reject reconciliation |
| POST | `/reconciliations/{id}/reopen` | Reopen reconciliation |
| POST | `/reconciliations/{id}/complete` | Complete reconciliation |

### Adjustments

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/reconciliations/{id}/adjustments` | List adjustments |
| POST | `/reconciliations/{id}/adjustments` | Add adjustment |
| DELETE | `/adjustments/{id}` | Delete adjustment |
| POST | `/reconciliations/{id}/adjustments/auto-create-charges` | Auto-create charge adjustments |
| POST | `/reconciliations/{id}/adjustments/post` | Post adjustments to GL |

### Unmatched Items

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/reconciliations/{id}/unmatched-items` | List unmatched items |
| POST | `/reconciliations/{id}/unmatched-items/auto-create` | Auto-create unmatched items |
| POST | `/unmatched-items/{id}/resolve` | Resolve item |

### Rules

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/charge-rules` | List charge detection rules |
| POST | `/charge-rules` | Create charge rule |
| GET | `/matching-rules` | List matching rules |
| POST | `/matching-rules` | Create matching rule |

### Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/summary` | Get reconciliation summary |

---

## Nigerian Banking Integration

### Mono API

[Mono](https://mono.co) provides Nigerian bank data aggregation.

**Setup:**
```env
MONO_SECRET_KEY=your-mono-secret-key
MONO_PUBLIC_KEY=your-mono-public-key
MONO_WEBHOOK_SECRET=your-mono-webhook-secret
MONO_SANDBOX_MODE=True
MONO_BASE_URL=https://api.withmono.com
```

**Integration Flow:**
1. User initiates Mono Connect widget
2. User authenticates with their bank
3. Mono returns an authorization code
4. Backend exchanges code for account ID
5. System syncs transactions from Mono

### Okra API

[Okra](https://okra.ng) provides Nigerian open banking services.

**Setup:**
```env
OKRA_SECRET_KEY=your-okra-secret-key
OKRA_CLIENT_TOKEN=your-okra-client-token
OKRA_PUBLIC_KEY=your-okra-public-key
OKRA_SANDBOX_MODE=True
OKRA_BASE_URL=https://api.okra.ng/v2
```

### Stitch API

[Stitch](https://stitch.money) provides payment integration services.

**Setup:**
```env
STITCH_CLIENT_ID=your-stitch-client-id
STITCH_CLIENT_SECRET=your-stitch-client-secret
STITCH_SANDBOX_MODE=True
STITCH_BASE_URL=https://api.stitch.money
```

---

## Transaction Matching

### Matching Strategies

1. **Exact Match** (Confidence: 100%)
   - Same date, amount, and reference
   
2. **Fuzzy Match** (Confidence: 70-95%)
   - Date tolerance: ±3 days
   - Amount tolerance: Configurable (default 0.01)
   - Description similarity matching

3. **Rule-Based Match** (Confidence: Based on rule)
   - Custom rules defined by user
   - Pattern matching on description
   - Vendor/payee matching

4. **One-to-Many Match**
   - Single bank transaction to multiple book entries
   - Sum of book entries equals bank amount

5. **Many-to-One Match**
   - Multiple bank transactions to single book entry
   - Useful for split payments

### Auto-Match Configuration

```python
class MatchingConfig:
    enable_exact_match: bool = True
    enable_fuzzy_match: bool = True
    enable_rule_match: bool = True
    date_tolerance_days: int = 3
    amount_tolerance: Decimal = Decimal("0.01")
    min_confidence_threshold: int = 70
```

---

## Charge Detection

### Nigerian Bank Charges

| Charge Type | Detection Pattern | Typical Amount |
|-------------|-------------------|----------------|
| EMTL | `EMTL`, `E-LEVY`, `TRANSFER LEVY` | ₦50 per transfer ≥₦10,000 |
| Stamp Duty | `STAMP DUTY`, `STD`, `S/DUTY` | ₦50 per credit |
| VAT | `VAT`, `VALUE ADDED TAX` | 7.5% |
| WHT | `WHT`, `WITHHOLDING TAX` | Various rates |
| SMS Fee | `SMS`, `ALERT FEE`, `NOTIFICATION` | ₦4-50 |
| Account Maintenance | `COT`, `MAINTENANCE`, `MANAGEMENT FEE` | Varies |
| POS Fee | `POS`, `MERCHANT` | 0.5% capped |
| NIP Fee | `NIP`, `NIBSS`, `INTERBANK` | ₦10-50 |

### Charge Detection Patterns

```python
NIGERIAN_CHARGE_PATTERNS = {
    'emtl': [
        r'EMTL', r'E-LEVY', r'ELECTRONIC\s*MONEY\s*TRANSFER',
        r'TRANSFER\s*LEVY'
    ],
    'stamp_duty': [
        r'STAMP\s*DUTY', r'STD', r'S/DUTY', r'STAMP\s*D'
    ],
    'vat': [
        r'VAT', r'VALUE\s*ADDED\s*TAX', r'V\.A\.T'
    ],
    'sms': [
        r'SMS', r'ALERT\s*FEE', r'NOTIFICATION\s*CHARGE'
    ],
    # ... more patterns
}
```

---

## Workflow Management

### Reconciliation States

```
┌─────────┐    ┌─────────────┐    ┌───────────┐    ┌──────────┐
│  DRAFT  │───>│ IN_PROGRESS │───>│ IN_REVIEW │───>│ APPROVED │
└─────────┘    └─────────────┘    └───────────┘    └──────────┘
                                         │               │
                                         v               v
                                  ┌──────────┐    ┌───────────┐
                                  │ REJECTED │    │ COMPLETED │
                                  └──────────┘    └───────────┘
```

### State Transitions

| From | To | Action | Requirements |
|------|-----|--------|--------------|
| DRAFT | IN_PROGRESS | Start working | None |
| IN_PROGRESS | IN_REVIEW | Submit | Difference = 0 |
| IN_REVIEW | APPROVED | Approve | Reviewer permission |
| IN_REVIEW | REJECTED | Reject | Reviewer permission |
| APPROVED | COMPLETED | Complete | All adjustments posted |
| REJECTED | IN_PROGRESS | Reopen | None |

---

## Frontend Interface

### Main Components

1. **Bank Accounts Panel**
   - List of connected bank accounts
   - Account balance display
   - API connection status
   - Last reconciliation date

2. **Reconciliations Panel**
   - List of reconciliations by account
   - Status indicators
   - Period and difference display

3. **Transactions Tab**
   - Filter: All, Unmatched, Matched, Charges
   - Columns: Date, Description, Debit, Credit, Status, Confidence
   - Nigerian charge indicators (EMTL, Stamp Duty, VAT, WHT)
   - Match/Unmatch actions

4. **Adjustments Tab**
   - List of adjustments
   - Type, amount, affects (Bank/Book)
   - Posted status
   - Post to GL action

5. **Unmatched Items Tab**
   - List of unmatched items
   - Resolution actions

### Modals

- **Add Bank Account**: Nigerian banks dropdown with 80+ banks
- **New Reconciliation**: Period selection, balance inputs
- **Import CSV**: File upload, column mapping
- **Add Adjustment**: Type selection, amount, description

---

## Configuration

### Environment Variables

```env
# Bank Aggregation APIs
MONO_SECRET_KEY=your-mono-secret-key
MONO_PUBLIC_KEY=your-mono-public-key
MONO_WEBHOOK_SECRET=your-mono-webhook-secret
MONO_SANDBOX_MODE=True
MONO_BASE_URL=https://api.withmono.com

OKRA_SECRET_KEY=your-okra-secret-key
OKRA_CLIENT_TOKEN=your-okra-client-token
OKRA_PUBLIC_KEY=your-okra-public-key
OKRA_SANDBOX_MODE=True
OKRA_BASE_URL=https://api.okra.ng/v2

STITCH_CLIENT_ID=your-stitch-client-id
STITCH_CLIENT_SECRET=your-stitch-client-secret
STITCH_SANDBOX_MODE=True
STITCH_BASE_URL=https://api.stitch.money
```

### Default Charge Rules (Migration Seeds)

The migration automatically seeds the following charge detection rules:

| Rule Name | Pattern | Adjustment Type | Priority |
|-----------|---------|-----------------|----------|
| EMTL Detection | EMTL\|E-LEVY\|TRANSFER LEVY | emtl | 1 |
| Stamp Duty Detection | STAMP DUTY\|STD\|S/DUTY | stamp_duty | 2 |
| VAT Detection | VAT\|VALUE ADDED TAX | vat | 3 |
| WHT Detection | WHT\|WITHHOLDING | wht | 4 |
| SMS Alert Detection | SMS ALERT\|NOTIFICATION | sms_fee | 5 |

---

## Testing

### Running Tests

```bash
# Run all bank reconciliation tests
pytest tests/test_bank_reconciliation.py -v

# Run specific test
pytest tests/test_bank_reconciliation.py::test_create_bank_account -v

# Run with coverage
pytest tests/test_bank_reconciliation.py --cov=app/services/bank_reconciliation_service
```

### Test Cases

1. **Bank Account Management**
   - Create account with valid NUBAN
   - Create account with API integration
   - Update account balance
   - Deactivate account

2. **Statement Import**
   - Import CSV with standard columns
   - Import CSV with custom column mapping
   - Detect charges during import
   - Handle duplicate transactions

3. **Transaction Matching**
   - Exact match by reference
   - Fuzzy match with date tolerance
   - One-to-many matching
   - Many-to-one matching

4. **Charge Detection**
   - Detect EMTL charges
   - Detect Stamp Duty
   - Detect VAT
   - Auto-create adjustments

5. **Workflow**
   - Create draft reconciliation
   - Submit for review
   - Approve/Reject
   - Complete reconciliation

6. **API Integration**
   - Mono connection
   - Okra connection
   - Transaction sync

---

## Supported Nigerian Banks

### Commercial Banks (23)
- Access Bank
- Citibank Nigeria
- Ecobank Nigeria
- Fidelity Bank
- First Bank of Nigeria
- First City Monument Bank (FCMB)
- Globus Bank
- Guaranty Trust Bank (GTBank)
- Heritage Bank
- Keystone Bank
- Polaris Bank
- Premium Trust Bank
- Providus Bank
- Stanbic IBTC Bank
- Standard Chartered Bank
- Sterling Bank
- SunTrust Bank
- Titan Trust Bank
- Union Bank of Nigeria
- United Bank for Africa (UBA)
- Unity Bank
- Wema Bank
- Zenith Bank

### Merchant Banks (5)
- Coronation Merchant Bank
- FBN Merchant Bank
- FSDH Merchant Bank
- Nova Merchant Bank
- Rand Merchant Bank

### Digital/Mobile Banks (7)
- Kuda Bank
- Moniepoint MFB
- OPay
- PalmPay
- Rubies Bank
- Sparkle MFB
- VFD Microfinance Bank

### Microfinance Banks (21)
- AB Microfinance Bank
- Accion MFB
- Baobab MFB
- CEMCS MFB
- Coronation MFB
- Ekondo MFB
- e-Barcs MFB
- FairMoney MFB
- Fina Trust MFB
- First Multiple MFB
- Hasal MFB
- Infinity MFB
- LAPO MFB
- Mainstreet MFB
- Mutual Trust MFB
- NPF MFB
- Peace MFB
- Renmoney MFB
- Seedvest MFB
- TCF MFB
- Unical MFB

### Development Banks (4)
- Bank of Agriculture (BOA)
- Bank of Industry (BOI)
- Development Bank of Nigeria
- NEXIM Bank

---

## Changelog

### Version 1.0.0 (January 2026)
- Initial release
- Full bank account management
- CSV import with charge detection
- Mono/Okra/Stitch API integration
- 5 matching strategies
- Nigerian charge auto-detection
- Complete workflow management
- Comprehensive frontend

---

## Support

For issues or feature requests, please contact:
- Email: info@tekvwa.org
- GitHub: https://github.com/EfeObus/Tekvwa-Pro-Audit

---

*Last Updated: January 18, 2026*
