# Consolidation Module Documentation

## Overview

The Tekvwa Pro Audit Consolidation module provides comprehensive group accounting capabilities for multi-entity organizations. It supports parent-subsidiary relationships, currency translation for foreign operations, intercompany eliminations, and non-controlling interest calculations, all compliant with **IFRS 10 - Consolidated Financial Statements** and **IAS 21 - The Effects of Changes in Foreign Exchange Rates**.

---

## Table of Contents

1. [Entity Hierarchy Setup](#entity-hierarchy-setup)
2. [Currency Translation](#currency-translation)
3. [Intercompany Eliminations](#intercompany-eliminations)
4. [Non-Controlling Interests (NCI)](#non-controlling-interests)
5. [Consolidated Financial Statements](#consolidated-financial-statements)
6. [API Reference](#api-reference)
7. [Best Practices](#best-practices)

---

## Entity Hierarchy Setup

### Creating the Parent Entity

```json
POST /api/v1/entities
{
  "name": "Parent Corp Nigeria",
  "business_type": "limited_company",
  "functional_currency": "NGN",
  "presentation_currency": "NGN",
  "is_parent": true
}
```

### Adding Subsidiaries

```json
POST /api/v1/entities
{
  "name": "US Subsidiary Inc",
  "business_type": "limited_company",
  "functional_currency": "USD",
  "parent_id": "parent-entity-uuid",
  "ownership_percentage": "80.00",
  "acquisition_date": "2024-01-01",
  "consolidation_method": "full"
}
```

### Consolidation Methods

| Method | Ownership | Description |
|--------|-----------|-------------|
| **Full Consolidation** | >50% | Line-by-line aggregation with NCI |
| **Equity Method** | 20-50% | Single line investment + share of profit |
| **Proportionate** | Joint Ventures | Pro-rata line items (rare under IFRS) |
| **Cost Method** | <20% | Investment at cost |

### Entity Hierarchy Response

```json
GET /api/v1/entities/{parent_id}/hierarchy

{
  "id": "parent-uuid",
  "name": "Parent Corp Nigeria",
  "functional_currency": "NGN",
  "subsidiaries": [
    {
      "id": "sub-us-uuid",
      "name": "US Subsidiary Inc",
      "functional_currency": "USD",
      "ownership_percentage": "80.00",
      "consolidation_method": "full",
      "acquisition_date": "2024-01-01"
    },
    {
      "id": "sub-uk-uuid",
      "name": "UK Subsidiary Ltd",
      "functional_currency": "GBP",
      "ownership_percentage": "100.00",
      "consolidation_method": "full",
      "acquisition_date": "2023-07-01"
    }
  ],
  "total_subsidiaries": 2
}
```

---

## Currency Translation

Foreign subsidiaries' financial statements must be translated to the parent's presentation currency. This follows IAS 21 requirements.

### Translation Rates

| Item Category | Rate to Use |
|---------------|-------------|
| Assets & Liabilities | **Closing rate** (at reporting date) |
| Revenue & Expenses | **Average rate** (for the period) |
| Equity (Share Capital) | **Historical rate** (at acquisition) |
| Retained Earnings | Cumulative translation |
| Dividends | Rate at declaration date |

### Translation API

```json
POST /api/v1/consolidation/translate
{
  "subsidiary_id": "sub-us-uuid",
  "as_of_date": "2026-12-31",
  "rates": {
    "closing_rate": "1520.00",
    "average_rate": "1500.00",
    "historical_rate": "1400.00"
  }
}
```

### Response

```json
{
  "subsidiary_id": "sub-us-uuid",
  "original_currency": "USD",
  "presentation_currency": "NGN",
  "translated_trial_balance": [
    {
      "account_code": "1000",
      "account_name": "Cash",
      "original_amount": "100000.00",
      "rate_used": "1520.00",
      "translated_amount": "152000000.00"
    }
  ],
  "cumulative_translation_adjustment": "5000000.00"
}
```

### Cumulative Translation Adjustment (CTA)

The CTA arises because:
- Balance sheet items are translated at closing rate
- Equity items are translated at historical/opening rates
- Income statement items are translated at average rate

The CTA is the balancing figure that keeps the translated trial balance in balance. It is recorded in **Other Comprehensive Income (OCI)**.

#### CTA Calculation Example:

| Component | USD | Rate | NGN |
|-----------|-----|------|-----|
| Assets | 200,000 | Closing 1,520 | 304,000,000 |
| Liabilities | (80,000) | Closing 1,520 | (121,600,000) |
| **Net Assets** | **120,000** | | **182,400,000** |
| Share Capital | (50,000) | Historical 1,400 | (70,000,000) |
| Opening RE | (50,000) | Opening 1,450 | (72,500,000) |
| Net Income | (20,000) | Average 1,500 | (30,000,000) |
| **Total Equity (calc)** | **(120,000)** | | **(172,500,000)** |
| **CTA (balancing)** | | | **(9,900,000)** |

---

## Intercompany Eliminations

Intercompany transactions and balances must be eliminated in consolidation to prevent double-counting.

### Types of Eliminations

1. **Intercompany Receivables/Payables**
2. **Intercompany Sales/Purchases**
3. **Intercompany Inventory Profit**
4. **Intercompany Dividends**
5. **Intercompany Loans and Interest**

### Identifying Intercompany Balances

```json
GET /api/v1/consolidation/intercompany
{
  "parent_entity_id": "parent-uuid",
  "as_of_date": "2026-12-31"
}
```

### Response

```json
{
  "intercompany_items": [
    {
      "from_entity": "Parent Corp Nigeria",
      "to_entity": "US Subsidiary Inc",
      "type": "receivable",
      "amount": "50000000.00",
      "currency": "NGN"
    },
    {
      "from_entity": "US Subsidiary Inc",
      "to_entity": "Parent Corp Nigeria",
      "type": "payable",
      "amount": "50000000.00",
      "currency": "NGN"
    }
  ],
  "suggested_eliminations": [
    {
      "description": "Eliminate IC receivable/payable",
      "debit_account": "2100",
      "debit_amount": "50000000.00",
      "credit_account": "1250",
      "credit_amount": "50000000.00"
    }
  ]
}
```

### Elimination Entry Generation

```json
POST /api/v1/consolidation/eliminations
{
  "parent_entity_id": "parent-uuid",
  "consolidation_date": "2026-12-31",
  "elimination_types": [
    "receivables_payables",
    "sales_purchases",
    "inventory_profit",
    "dividends"
  ]
}
```

### Elimination Accounts

| Elimination Type | Debit | Credit |
|------------------|-------|--------|
| IC Receivable/Payable | IC Payable (2100) | IC Receivable (1250) |
| IC Sales/COGS | IC Sales (4500) | IC COGS (5500) |
| IC Inventory Profit | Cost of Sales (5000) | Inventory (1500) |
| IC Dividend | Dividend Income (4600) | Dividend Declared (3300) |

---

## Non-Controlling Interests

When ownership is less than 100%, the portion not owned by the parent is the **Non-Controlling Interest (NCI)**.

### NCI Calculation

```
NCI % = 100% - Parent Ownership %
NCI in Net Assets = Subsidiary Net Assets × NCI %
NCI in Profit/Loss = Subsidiary Net Income × NCI %
```

### NCI API

```json
GET /api/v1/consolidation/nci
{
  "subsidiary_id": "sub-us-uuid",
  "as_of_date": "2026-12-31"
}
```

### Response

```json
{
  "subsidiary_id": "sub-us-uuid",
  "subsidiary_name": "US Subsidiary Inc",
  "ownership_percentage": "80.00",
  "nci_percentage": "20.00",
  "subsidiary_net_assets": "150000000.00",
  "nci_in_net_assets": "30000000.00",
  "subsidiary_net_income": "25000000.00",
  "nci_in_profit_loss": "5000000.00",
  "nci_balance_sheet_account": "3500",
  "nci_income_statement_account": "8500"
}
```

### NCI Presentation

**Balance Sheet:**
```
Equity
  Share Capital               100,000,000
  Retained Earnings            75,000,000
  Other Reserves               10,000,000
  Equity Attributable to Owners of Parent   185,000,000
  Non-Controlling Interests    30,000,000
  Total Equity                215,000,000
```

**Income Statement:**
```
Profit for the Year           25,000,000
Attributable to:
  Owners of Parent            20,000,000
  Non-Controlling Interests    5,000,000
                              25,000,000
```

---

## Consolidated Financial Statements

### Generate Consolidated Trial Balance

```json
POST /api/v1/consolidation/trial-balance
{
  "parent_entity_id": "parent-uuid",
  "as_of_date": "2026-12-31",
  "include_eliminations": true,
  "include_nci": true
}
```

### Response

```json
{
  "as_of_date": "2026-12-31",
  "presentation_currency": "NGN",
  "consolidated_accounts": [
    {
      "account_code": "1000",
      "account_name": "Cash and Cash Equivalents",
      "parent_amount": "100000000.00",
      "subsidiary_amounts": {
        "US Subsidiary": "152000000.00",
        "UK Subsidiary": "76000000.00"
      },
      "eliminations": "0.00",
      "consolidated_amount": "328000000.00"
    },
    {
      "account_code": "1250",
      "account_name": "Intercompany Receivable",
      "parent_amount": "50000000.00",
      "subsidiary_amounts": {},
      "eliminations": "-50000000.00",
      "consolidated_amount": "0.00"
    }
  ],
  "total_debits": "500000000.00",
  "total_credits": "500000000.00",
  "cta_balance": "9900000.00",
  "nci_balance": "30000000.00"
}
```

### Generate Consolidated Balance Sheet

```json
GET /api/v1/consolidation/balance-sheet
{
  "parent_entity_id": "parent-uuid",
  "as_of_date": "2026-12-31",
  "comparative": true
}
```

### Generate Consolidated Income Statement

```json
GET /api/v1/consolidation/income-statement
{
  "parent_entity_id": "parent-uuid",
  "period_start": "2026-01-01",
  "period_end": "2026-12-31",
  "comparative": true
}
```

---

## API Reference

### Endpoints Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/entities/{id}/hierarchy` | Get entity hierarchy |
| POST | `/consolidation/translate` | Translate subsidiary balances |
| GET | `/consolidation/intercompany` | Get intercompany balances |
| POST | `/consolidation/eliminations` | Generate elimination entries |
| GET | `/consolidation/nci` | Calculate NCI |
| POST | `/consolidation/trial-balance` | Generate consolidated TB |
| GET | `/consolidation/balance-sheet` | Generate consolidated BS |
| GET | `/consolidation/income-statement` | Generate consolidated P&L |

---

## Best Practices

### 1. Consistent Reporting Dates
Ensure all subsidiaries report as of the same date. If reporting dates differ by more than 3 months, adjustments are required per IFRS 10.

### 2. Uniform Accounting Policies
Apply consistent accounting policies across all group entities. Document any differences and make consolidation adjustments.

### 3. Regular Intercompany Reconciliation
Reconcile intercompany balances monthly:
- Ensure matching amounts in both entities
- Investigate and resolve differences before period-end

### 4. Rate Documentation
Document the source and calculation of all exchange rates used:
- Closing rate source (e.g., CBN, Reuters)
- Average rate methodology (simple average, weighted)
- Historical rate records for equity items

### 5. CTA Monitoring
Monitor the CTA balance for significant movements. Large CTA changes may indicate:
- Significant currency movements
- Errors in translation
- Changes in subsidiary net asset composition

### 6. NCI Tracking
Maintain detailed NCI schedules showing:
- Opening NCI balance
- Share of comprehensive income
- Dividends to NCI
- Changes in ownership
- Closing NCI balance

---

## Consolidation Checklist

### Pre-Consolidation
- [ ] All subsidiary trial balances finalized
- [ ] Intercompany balances reconciled
- [ ] Exchange rates documented
- [ ] Accounting policies aligned

### During Consolidation
- [ ] Translate foreign subsidiaries
- [ ] Calculate and record CTA
- [ ] Generate elimination entries
- [ ] Calculate NCI amounts
- [ ] Verify consolidated TB balances

### Post-Consolidation
- [ ] Review consolidated statements
- [ ] Analyze CTA movements
- [ ] Document significant judgments
- [ ] Prepare NCI disclosure
- [ ] Archive working papers

---

## Troubleshooting

### Issue: Consolidated Trial Balance Doesn't Balance

**Causes:**
1. Translation CTA not properly calculated
2. Elimination entries unbalanced
3. NCI not included in equity

**Solution:**
1. Verify CTA calculation
2. Check each elimination entry balances
3. Ensure NCI is posted to both Balance Sheet and P&L

### Issue: Intercompany Differences

**Causes:**
1. Timing differences (one entity recorded, other didn't)
2. FX rate differences between entities
3. Duplicate/missing transactions

**Solution:**
1. Reconcile as of cut-off date
2. Use agreed-upon exchange rates
3. Review transaction details
