# Foreign Exchange (FX) API Documentation

> **Document Version:** 1.1  
> **Last Updated:** January 27, 2026  
> **SKU Requirement:** Professional tier or higher (`Feature.MULTI_CURRENCY`)  
> **API Prefix:** `/api/v1/entities/{entity_id}/fx`

---

## Overview

The Tekvwa Pro Audit Foreign Exchange module provides comprehensive multi-currency support compliant with **IAS 21 - The Effects of Changes in Foreign Exchange Rates**. This module handles:

- Exchange rate management and historical rate storage
- Transaction currency conversion
- Realized FX gains/losses on settlement
- Unrealized FX gains/losses from period-end revaluation
- FX exposure reporting
- Period-end revaluation automation

> **⚠️ SKU Gating:** This module requires **Pro Audit Professional** (₦150,000-400,000/mo) or **Enterprise** (₦1,000,000-5,000,000+/mo) tier. Core tier users will receive a `403 Forbidden` response with upgrade instructions.

## Functional Currency

Each business entity in the system has a designated **functional currency** - the currency of the primary economic environment in which the entity operates. For Nigerian entities, this is typically **NGN (Nigerian Naira)**.

### Supported Currencies
- **NGN** - Nigerian Naira (default functional currency)
- **USD** - United States Dollar
- **EUR** - Euro
- **GBP** - British Pound Sterling

---

## API Endpoints

### Base URL

All FX endpoints are scoped to an entity:
```
/api/v1/entities/{entity_id}/fx/*
```

### Exchange Rates

#### GET /api/v1/entities/{entity_id}/fx/exchange-rates
Retrieve current exchange rates for a given date.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `base_currency` | string | Yes | Base currency code (e.g., "NGN") |
| `date` | string | No | Rate date (YYYY-MM-DD), defaults to today |

**Response:**
```json
{
  "base_currency": "NGN",
  "date": "2026-01-15",
  "rates": {
    "USD": "0.000667",
    "EUR": "0.000615",
    "GBP": "0.000526"
  }
}
```

---

#### POST /api/v1/exchange-rates
Create a new exchange rate entry.

**Request Body:**
```json
{
  "base_currency": "USD",
  "target_currency": "NGN",
  "rate": "1500.00",
  "effective_date": "2026-01-15",
  "rate_type": "spot"
}
```

**Parameters:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `base_currency` | string | Yes | Source currency code |
| `target_currency` | string | Yes | Target currency code |
| `rate` | decimal | Yes | Exchange rate (must be positive) |
| `effective_date` | date | Yes | Date rate becomes effective |
| `rate_type` | string | No | "spot" (default), "closing", "average" |

**Response (201 Created):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "base_currency": "USD",
  "target_currency": "NGN",
  "rate": "1500.00",
  "effective_date": "2026-01-15",
  "rate_type": "spot",
  "created_at": "2026-01-15T10:30:00Z"
}
```

---

#### GET /api/v1/exchange-rates/historical
Retrieve historical exchange rates for a date range.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `base_currency` | string | Yes | Base currency code |
| `target_currency` | string | Yes | Target currency code |
| `start_date` | date | Yes | Start of date range |
| `end_date` | date | Yes | End of date range |

**Response:**
```json
{
  "base_currency": "USD",
  "target_currency": "NGN",
  "start_date": "2026-01-01",
  "end_date": "2026-01-31",
  "rates": [
    {"date": "2026-01-01", "rate": "1480.00"},
    {"date": "2026-01-15", "rate": "1500.00"},
    {"date": "2026-01-31", "rate": "1520.00"}
  ]
}
```

---

### Currency Conversion

#### POST /api/v1/fx/convert
Convert an amount between currencies.

**Request Body:**
```json
{
  "amount": "1000.00",
  "from_currency": "USD",
  "to_currency": "NGN",
  "rate_date": "2026-01-15"
}
```

**Response:**
```json
{
  "original_amount": "1000.00",
  "from_currency": "USD",
  "converted_amount": "1500000.00",
  "to_currency": "NGN",
  "exchange_rate": "1500.00",
  "rate_date": "2026-01-15"
}
```

---

### FX Gains/Losses

#### POST /api/v1/fx/realized-gain-loss
Calculate realized FX gain/loss on payment settlement.

**Request Body:**
```json
{
  "invoice_id": "550e8400-e29b-41d4-a716-446655440000",
  "payment_amount": "1000.00",
  "payment_currency": "USD",
  "payment_date": "2026-02-15",
  "payment_rate": "1520.00"
}
```

**Response:**
```json
{
  "invoice_id": "550e8400-e29b-41d4-a716-446655440000",
  "original_functional_amount": "1500000.00",
  "settlement_functional_amount": "1520000.00",
  "fx_gain_loss": "20000.00",
  "is_gain": true,
  "journal_entry": {
    "id": "660e8400-e29b-41d4-a716-446655440001",
    "lines": [
      {"account": "1010", "debit": "1520000.00", "credit": "0.00"},
      {"account": "1200", "debit": "0.00", "credit": "1500000.00"},
      {"account": "7100", "debit": "0.00", "credit": "20000.00"}
    ]
  }
}
```

**FX Gain/Loss Determination:**
- **Receivables (AR):** Rate increase = Gain, Rate decrease = Loss
- **Payables (AP):** Rate increase = Loss, Rate decrease = Gain

---

#### POST /api/v1/fx/revaluation
Perform period-end FX revaluation for monetary items.

**Request Body:**
```json
{
  "entity_id": "550e8400-e29b-41d4-a716-446655440000",
  "revaluation_date": "2026-01-31",
  "closing_rates": {
    "USD": "1520.00",
    "EUR": "1650.00",
    "GBP": "1920.00"
  },
  "item_types": ["receivables", "payables"]
}
```

**Response:**
```json
{
  "entity_id": "550e8400-e29b-41d4-a716-446655440000",
  "revaluation_date": "2026-01-31",
  "items_revalued": 15,
  "total_unrealized_gain": "250000.00",
  "total_unrealized_loss": "75000.00",
  "net_unrealized": "175000.00",
  "journal_entry_id": "770e8400-e29b-41d4-a716-446655440002"
}
```

---

## Accounting Treatment

### Realized FX Gains/Losses
When a foreign currency transaction is settled, any difference between the original recorded amount (at transaction date rate) and the settlement amount (at payment date rate) is recorded as:

- **FX Gain Account (7100):** Credit for gains
- **FX Loss Account (7200):** Debit for losses

### Unrealized FX Gains/Losses
At period-end, monetary items (receivables, payables, foreign currency cash) are revalued using the closing rate:

- **Unrealized FX Gain Account (7110):** Credit for gains
- **Unrealized FX Loss Account (7210):** Debit for losses

These unrealized amounts may be reversed at the start of the next period (optional).

---

## GL Account Structure

| Account Code | Account Name | Type |
|--------------|--------------|------|
| 7100 | Realized FX Gain | Income |
| 7110 | Unrealized FX Gain | Income |
| 7200 | Realized FX Loss | Expense |
| 7210 | Unrealized FX Loss | Expense |

---

## IAS 21 Compliance

The FX module implements the following IAS 21 requirements:

### Initial Recognition (IAS 21.21)
Foreign currency transactions are initially recorded in the functional currency using the **spot exchange rate** at the date of the transaction.

### Subsequent Measurement (IAS 21.23)
At each reporting date:
- **Monetary items** (cash, receivables, payables) are translated using the **closing rate**
- **Non-monetary items** at historical cost remain at the **historical rate**
- **Non-monetary items** at fair value use the rate at the fair value measurement date

### Recognition of Exchange Differences (IAS 21.28)
Exchange differences arising on settlement or translation are recognized in **profit or loss**, except for:
- Net investment in a foreign operation (recognized in OCI)
- Cash flow hedges (recognized in OCI)

---

## Error Codes

| Code | Description |
|------|-------------|
| `FX001` | Invalid currency code |
| `FX002` | Exchange rate not found for date |
| `FX003` | Rate must be positive |
| `FX004` | Same currency conversion not allowed |
| `FX005` | Future date rate not available |

---

## Examples

### Example 1: Record a USD Invoice

1. **Create invoice** for 1,000 USD when rate is 1,500 NGN/USD:
   - Invoice recorded at 1,500,000 NGN
   
2. **Journal Entry:**
   ```
   Dr. Accounts Receivable (1200)    1,500,000 NGN
       Cr. Sales Revenue (4000)               1,500,000 NGN
   ```

### Example 2: Receive Payment with Rate Change

1. **Receive payment** of 1,000 USD when rate is 1,520 NGN/USD:
   - Cash received: 1,520,000 NGN
   - Original AR: 1,500,000 NGN
   - FX Gain: 20,000 NGN

2. **Journal Entry:**
   ```
   Dr. Cash (1010)                   1,520,000 NGN
       Cr. Accounts Receivable (1200)        1,500,000 NGN
       Cr. FX Gain (7100)                       20,000 NGN
   ```

### Example 3: Period-End Revaluation

1. **Open AR balance** of 5,000 USD at book rate 1,500 = 7,500,000 NGN
2. **Closing rate** is 1,480 NGN/USD
3. **Revalued amount:** 5,000 × 1,480 = 7,400,000 NGN
4. **Unrealized loss:** 100,000 NGN

5. **Journal Entry:**
   ```
   Dr. Unrealized FX Loss (7210)       100,000 NGN
       Cr. Accounts Receivable (1200)         100,000 NGN
   ```

---

## Rate Type Usage

| Rate Type | When Used |
|-----------|-----------|
| **Spot Rate** | Transaction date recording |
| **Closing Rate** | Period-end revaluation of monetary items |
| **Average Rate** | Income/expense translation in consolidation |
| **Historical Rate** | Non-monetary items, equity items in consolidation |

---

## Best Practices

1. **Daily Rate Updates:** Import exchange rates daily from a reliable source
2. **Rate Source Documentation:** Record the source of each rate for audit trail
3. **Consistent Methodology:** Apply the same rate determination methodology consistently
4. **Timely Revaluation:** Perform FX revaluation at each month-end close
5. **Segregate FX Impacts:** Use separate GL accounts for realized vs unrealized FX effects
