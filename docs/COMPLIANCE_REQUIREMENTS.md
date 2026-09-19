# Tekvwa Pro Audit - Nigeria 2026 Tax Compliance Requirements

**Document Version:** 2.1  
**Date:** January 6, 2026  
**Status:** Production - Fully Implemented  
**Disclaimer:** This document is for planning purposes. Consult with licensed tax professionals and NRS for official guidance.

---

## Implementation Status

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| CIT Calculation | Yes Complete | `app/services/tax_calculators/cit.py` |
| VAT Calculation | Yes Complete | `app/services/tax_calculators/vat.py` |
| PAYE Calculation | Yes Complete | `app/services/tax_calculators/paye.py` |
| WHT Calculation | Yes Complete | `app/services/tax_calculators/wht.py` |
| E-Invoicing (NRS) | Yes Complete | `app/services/nrs_service.py` |
| Development Levy | Yes Complete | `app/services/development_levy_service.py` |
| Capital Gains Tax | Yes Complete | `app/routers/tax_2026.py` |
| VAT Recovery | Yes Complete | `app/services/vat_recovery_service.py` |
| PIT Reliefs | Yes Complete | `app/services/pit_relief_service.py` |
| Buyer Review (72h) | Yes Complete | `app/services/buyer_review_service.py` |
| B2C Realtime Reporting | Yes Complete | `app/services/b2c_reporting_service.py` |
| NDPA Data Protection | Yes Complete | `app/utils/ndpa_security.py` |

---

## Executive Summary

This document outlines the key compliance requirements from Nigeria's 2026 Tax Reform that Tekvwa Pro Audit must implement. The reforms represent significant changes to Corporate Income Tax, Value Added Tax, Personal Income Tax (PAYE), Withholding Tax, and introduce mandatory e-invoicing.

---

## Table of Contents

1. [2026 Tax Reform Overview](#1-2026-tax-reform-overview)
2. [Corporate Income Tax (CIT)](#2-corporate-income-tax-cit)
3. [Value Added Tax (VAT)](#3-value-added-tax-vat)
4. [Personal Income Tax - PAYE](#4-personal-income-tax---paye)
5. [Withholding Tax (WHT)](#5-withholding-tax-wht)
6. [E-Invoicing Mandate](#6-e-invoicing-mandate)
7. [Development Levy](#7-development-levy)
8. [Capital Gains Tax](#8-capital-gains-tax)
9. [Record Keeping Requirements](#9-record-keeping-requirements)
10. [Compliance Calendar](#10-compliance-calendar)
11. [Implementation Checklist](#11-implementation-checklist)

---

## 1. 2026 Tax Reform Overview

### 1.1 Key Changes Summary

| Area | Pre-2026 | 2026 Reform | Impact on App |
|------|----------|-------------|---------------|
| **CIT Small Business** | 0% for < ₦25M | 0% for ≤ ₦50M-₦100M | Update threshold logic |
| **VAT Input Recovery** | Limited to goods | Extended to services + fixed assets | Track all eligible inputs |
| **PAYE Tax-Free Threshold** | ₦300,000 | ₦800,000 | Update tax band calculator |
| **E-Invoicing** | Optional | Mandatory for B2B | Core feature requirement |
| **WHT Small Business** | No exemption | Exempt for < ₦2M transactions | Add exemption logic |
| **Development Levy** | 2% Education Tax | 4% Development Levy | Update calculation |
| **CGT** | 10% separate | 30% merged with income | Integrate with asset register |

### 1.2 Relevant Legislation

- **Nigeria Tax Act, 2025** (Act No. 7, Official Gazette No. 117, June 26, 2025)
  - Commencement: January 1, 2026
  - Consolidates: Capital Gains Tax Act, Companies Income Tax Act, Personal 
    Income Tax Act, Stamp Duties Act, Value Added Tax Act
- **Nigeria Tax Administration Act, 2025**
- **NRS E-Invoicing Regulations 2026**
- **PAYE Regulations (pursuant to Nigeria Tax Act, 2025)

### 1.3 Regulatory Bodies

| Body | Responsibility |
|------|----------------|
| **Nigeria Revenue Service (NRS)** | Primary tax authority (reformed from FIRS) |
| **State Internal Revenue Services** | PAYE collection and administration |
| **NRS E-Invoice Portal** | E-invoicing validation and IRN generation |
| **TaxPro Max** | Self-assessment filing portal |

---

## 2. Corporate Income Tax (CIT) - Section 56, Nigeria Tax Act 2025

### 2.1 CIT Rate Structure (Section 56)

```
┌─────────────────────────────────────────────────────────────────┐
│     CORPORATE INCOME TAX RATES - Section 56, Nigeria Tax Act    │
├──────────────────────────────┬──────────────────────────────────┤
│  Company Classification      │  CIT Rate                        │
├──────────────────────────────┼──────────────────────────────────┤
│  Small Company               │  0%                              │
│  (Turnover ≤ ₦50,000,000)    │                                  │
├──────────────────────────────┼──────────────────────────────────┤
│  Other Companies             │  30%                             │
│  (Turnover > ₦50,000,000)    │                                  │
└──────────────────────────────┴──────────────────────────────────┘

Note: Section 57 introduces a 15% minimum effective tax rate for 
MNE constituents and companies with turnover ≥ ₦20 billion.
```

### 2.2 Implementation Requirements

| Requirement | Description | App Feature |
|-------------|-------------|-------------|
| **Turnover Tracking** | Accurately track annual gross income | Income module totals |
| **Bracket Determination** | Auto-classify company size at year-end | CIT calculator |
| **Assessable Profit Calculation** | Revenue - Allowable Deductions | Report generator |
| **Tax-Free Status Notification** | Alert when qualifying for 0% | Dashboard notification |
| **CIT Computation Schedule** | Standard format for filing | Report export |

### 2.3 Allowable Deductions

For expenses to be deductible (WREN principle):

| Criterion | Description | Validation |
|-----------|-------------|------------|
| **Wholly** | Fully for business purposes | 100% business use |
| **Reasonably** | Reasonable in amount | Industry benchmarks |
| **Exclusively** | Only for business operations | No personal element |
| **Necessarily** | Required for income generation | Business justification |

### 2.4 App Implementation

```typescript
// CIT Calculation Logic (Conceptual)

function determineCITBracket(annualTurnover: number): CITBracket {
  if (annualTurnover <= 50_000_000) {
    return { rate: 0, category: 'SMALL_COMPANY', threshold: 50_000_000 };
  } else if (annualTurnover <= 100_000_000) {
    return { rate: 0, category: 'TRANSITIONAL', threshold: 100_000_000 };
  } else {
    return { rate: 0.30, category: 'LARGE_COMPANY', threshold: null };
  }
}

function calculateCIT(assessableProfit: number, turnover: number): CITResult {
  const bracket = determineCITBracket(turnover);
  const citLiability = assessableProfit * bracket.rate;
  
  return {
    bracket: bracket.category,
    rate: bracket.rate,
    assessableProfit,
    citLiability,
    developmentLevy: bracket.rate > 0 ? assessableProfit * 0.04 : 0
  };
}
```

---

## 3. Value Added Tax (VAT) - Chapter 6, Nigeria Tax Act 2025

### 3.1 VAT Rate (Section 148)

| Rate | Application |
|------|-------------|
| **7.5%** | Standard rate for taxable supplies (Section 148) |
| **0%** | Zero-rated supplies (exports, certain essentials) |
| **Exempt** | Medical, educational, basic food items (Part IV, Chapter Eight) |

### 3.2 Input VAT Recovery (NEW in 2026)

**Key Change:** VAT paid on SERVICES and FIXED ASSETS is now recoverable.

| Input Category | Pre-2026 | 2026 | App Tracking |
|----------------|----------|------|--------------|
| Raw Materials | Recoverable | Recoverable | Track as Input VAT |
| Services | Not Recoverable | Recoverable | **NEW: Track as Input VAT** |
| Fixed Assets | Not Recoverable | Recoverable | **NEW: Track as Input VAT** |
| Entertainment | Not Recoverable | Not Recoverable | Exclude from recovery |
| Motor Vehicles | Not Recoverable | Verify | Check regulations |

### 3.3 VAT Calculation Logic

```typescript
// VAT Recovery Calculation

interface VATSummary {
  outputVAT: number;        // VAT collected on sales
  inputVAT: number;         // VAT paid on purchases (eligible)
  netVATLiability: number;  // Amount due to NRS
  vatCredit: number;        // Carry-forward if negative
}

function calculateVATLiability(
  sales: Transaction[],
  purchases: Transaction[]
): VATSummary {
  // Output VAT from sales
  const outputVAT = sales
    .filter(s => s.vatTreatment === 'STANDARD')
    .reduce((sum, s) => sum + s.vatAmount, 0);
  
  // Input VAT from eligible purchases
  const inputVAT = purchases
    .filter(p => p.inputVatRecoverable === true)
    .reduce((sum, p) => sum + p.vatAmount, 0);
  
  const netVAT = outputVAT - inputVAT;
  
  return {
    outputVAT,
    inputVAT,
    netVATLiability: netVAT > 0 ? netVAT : 0,
    vatCredit: netVAT < 0 ? Math.abs(netVAT) : 0
  };
}
```

### 3.4 VAT Filing Requirements

| Requirement | Deadline | App Feature |
|-------------|----------|-------------|
| Monthly VAT Return | 21st of following month | VAT summary report |
| VAT Remittance | 21st of following month | Payment reminder |
| E-Invoice IRN | At point of invoice | Automatic submission |
| VAT Invoice Format | NRS-compliant fields | Invoice template |

### 3.5 VAT Invoice Requirements

All VAT invoices must include:

- [ ] Business name and TIN
- [ ] Customer name and TIN (for B2B)
- [ ] Invoice date and unique number
- [ ] Description of goods/services
- [ ] Unit price and quantity
- [ ] VAT amount (separate line)
- [ ] Total amount
- [ ] **NRS Invoice Reference Number (IRN)** - NEW
- [ ] **QR Code** - NEW

---

## 4. Personal Income Tax - PAYE

### 4.1 2026 PAYE Tax Bands (Nigeria Tax Act 2025, Fourth Schedule)

```
┌─────────────────────────────────────────────────────────────────┐
│     INDIVIDUAL INCOME TAX RATES - Section 58, Fourth Schedule   │
├──────────────────────────────┬──────────────────────────────────┤
│  Annual Taxable Income       │  Tax Rate                        │
├──────────────────────────────┼──────────────────────────────────┤
│  First ₦800,000              │  0% (Tax-Free)                   │
├──────────────────────────────┼──────────────────────────────────┤
│  Next ₦2,200,000             │  15%                             │
│  (₦800,001 - ₦3,000,000)     │                                  │
├──────────────────────────────┼──────────────────────────────────┤
│  Next ₦9,000,000             │  18%                             │
│  (₦3,000,001 - ₦12,000,000)  │                                  │
├──────────────────────────────┼──────────────────────────────────┤
│  Next ₦13,000,000            │  21%                             │
│  (₦12,000,001 - ₦25,000,000) │                                  │
├──────────────────────────────┼──────────────────────────────────┤
│  Next ₦25,000,000            │  23%                             │
│  (₦25,000,001 - ₦50,000,000) │                                  │
├──────────────────────────────┼──────────────────────────────────┤
│  Above ₦50,000,000           │  25%                             │
└──────────────────────────────┴──────────────────────────────────┘

Note: These rates apply after relief allowances and exemptions have been 
granted in accordance with Section 30(1) of the Nigeria Tax Act, 2025.
```

### 4.2 PAYE Calculation Example (Using Official Bands)

**Employee Annual Gross Salary: ₦15,000,000**
(After Section 30 relief allowances and exemptions)

| Band | Taxable Amount | Rate | Tax |
|------|----------------|------|-----|
| Tax-Free | ₦800,000 | 0% | ₦0 |
| Band 1 | ₦2,200,000 | 15% | ₦330,000 |
| Band 2 | ₦9,000,000 | 18% | ₦1,620,000 |
| Band 3 | ₦3,000,000 | 21% | ₦630,000 |
| **Total Annual PAYE** | ₦15,000,000 | | **₦2,580,000** |
| **Monthly PAYE** | | | **₦215,000** |

### 4.3 PAYE Calculation Logic (Nigeria Tax Act 2025 Compliant)

```python
# PAYE Tax Calculator - Section 58, Fourth Schedule

PAYE_BANDS_2026 = [
    {"min": 0, "max": 800_000, "rate": 0.00},
    {"min": 800_001, "max": 3_000_000, "rate": 0.15},
    {"min": 3_000_001, "max": 12_000_000, "rate": 0.18},
    {"min": 12_000_001, "max": 25_000_000, "rate": 0.21},
    {"min": 25_000_001, "max": 50_000_000, "rate": 0.23},
    {"min": 50_000_001, "max": float("inf"), "rate": 0.25},
]

def calculate_paye(annual_taxable_income: float) -> dict:
    """
    Calculate PAYE based on Nigeria Tax Act 2025, Section 58
    Note: Taxable income is after Section 30 relief allowances
    """
    remaining_income = annual_taxable_income
    total_tax = 0.0
    breakdown = []

    for band in PAYE_BANDS_2026:
        if remaining_income <= 0:
            break

        band_width = band["max"] - band["min"] + 1
        taxable_in_band = min(remaining_income, band_width)
        tax_for_band = taxable_in_band * band["rate"]

        breakdown.append({
            "band": f"₦{band['min']:,} - ₦{band['max']:,}",
            "taxable_amount": taxable_in_band,
            "rate": band["rate"],
            "tax": tax_for_band,
        })

        total_tax += tax_for_band
        remaining_income -= taxable_in_band

    return {
        "annual_taxable_income": annual_taxable_income,
        "annual_tax": total_tax,
        "monthly_tax": total_tax / 12,
        "effective_rate": total_tax / annual_taxable_income if annual_taxable_income > 0 else 0,
        "breakdown": breakdown,
    }
```

### 4.4 PAYE Remittance Requirements

| Requirement | Deadline | App Feature |
|-------------|----------|-------------|
| Monthly PAYE Deduction | Payroll processing date | Auto-calculate |
| PAYE Remittance to SIRS | 10th of following month | Payment reminder |
| Annual PAYE Reconciliation | January 31st | Summary report |
| Employee Tax Deduction Cards | Annual | PDF generation |

---

## 5. Withholding Tax (WHT)

### 5.1 WHT Rates

| Payment Type | Rate | Notes |
|--------------|------|-------|
| Dividends | 10% | Except to companies (0%) |
| Interest | 10% | Banks withheld at source |
| Royalties | 10% | Intellectual property |
| Rent | 10% | Property rentals |
| Commission | 10% | Agency fees |
| Consultancy/Professional | 10% | Services |
| Construction/Contracts | 5% | Building, supply contracts |
| Directors Fees | 10% | Board compensation |

### 5.2 Small Business WHT Exemption (NEW in 2026)

**Key Change:** Transactions under ₦2,000,000 with small businesses are exempt from WHT.

```typescript
// WHT Exemption Logic

function isWHTExempt(transaction: Transaction): boolean {
  // Exemption criteria:
  // 1. Transaction amount < ₦2,000,000
  // 2. Vendor is classified as small business
  
  if (transaction.amount < 2_000_000) {
    if (transaction.vendor.businessSize === 'SMALL') {
      return true; // Exempt from WHT
    }
  }
  return false; // WHT applies
}

function calculateWHT(transaction: Transaction): WHTResult {
  if (isWHTExempt(transaction)) {
    return { 
      whtAmount: 0, 
      netPayment: transaction.amount,
      exempt: true,
      reason: 'Small business transaction < ₦2M'
    };
  }
  
  const rate = getWHTRate(transaction.paymentType);
  const whtAmount = transaction.amount * rate;
  
  return {
    whtAmount,
    netPayment: transaction.amount - whtAmount,
    exempt: false,
    rate
  };
}
```

### 5.3 WHT Credit Notes

When WHT is deducted, the payer must issue a WHT credit note containing:

- [ ] Name and TIN of payer
- [ ] Name and TIN of payee
- [ ] Nature of payment
- [ ] Gross amount
- [ ] WHT rate applied
- [ ] WHT amount deducted
- [ ] Net amount paid
- [ ] Date of transaction

---

## 6. E-Invoicing Mandate

### 6.1 E-Invoicing Overview

**Effective Date:** Mandatory for B2B transactions from 2026

**Purpose:**
- Real-time transaction visibility for NRS
- Reduce tax evasion
- Simplify VAT reconciliation
- Standardize invoice formats

### 6.2 E-Invoice Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                    E-INVOICING WORKFLOW                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. CREATE INVOICE                                              │
│     └─► Business creates invoice in Tekvwa                   │
│                                                                 │
│  2. VALIDATE & SIGN                                             │
│     └─► System validates all required fields                    │
│     └─► Digital signature applied                               │
│                                                                 │
│  3. SUBMIT TO NRS                                               │
│     └─► Invoice payload sent to NRS E-Invoice Portal            │
│     └─► Real-time validation by NRS                             │
│                                                                 │
│  4. RECEIVE IRN                                                 │
│     └─► NRS returns Invoice Reference Number (IRN)              │
│     └─► QR Code data provided                                   │
│                                                                 │
│  5. FINALIZE & DISTRIBUTE                                       │
│     └─► IRN and QR embedded in invoice                          │
│     └─► PDF generated for customer                              │
│     └─► Invoice is now legally valid                            │
│                                                                 │
│  6. ARCHIVAL                                                    │
│     └─► Invoice stored with NRS acknowledgment                  │
│     └─► Available for audit retrieval                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 6.3 E-Invoice Data Requirements

| Field | Required | Format | Validation |
|-------|----------|--------|------------|
| Seller TIN | Yes | 12345678-0001 | TIN verification |
| Seller Name | Yes | String | Match TIN registration |
| Seller Address | Yes | String | - |
| Buyer TIN | Yes (B2B) | 12345678-0001 | TIN verification |
| Buyer Name | Yes | String | - |
| Buyer Address | Yes | String | - |
| Invoice Number | Yes | String | Unique per seller |
| Invoice Date | Yes | YYYY-MM-DD | Cannot be future |
| Invoice Time | Yes | HH:MM:SS | Local time |
| Line Items | Yes (min 1) | Array | See below |
| Subtotal | Yes | Decimal | Sum of line items |
| VAT Amount | Yes | Decimal | 7.5% of taxable |
| Total Amount | Yes | Decimal | Subtotal + VAT |
| Currency | Yes | NGN | Only Naira |

**Line Item Fields:**
- Description
- Quantity
- Unit of Measure
- Unit Price
- Total Price
- HSN/SAC Code (if applicable)
- VAT Treatment (Standard/Zero/Exempt)

### 6.4 NRS API Integration

```typescript
// NRS E-Invoice Submission (Conceptual)

interface NRSInvoicePayload {
  version: '1.0';
  sellerDetails: {
    tin: string;
    name: string;
    address: string;
  };
  buyerDetails: {
    tin: string;
    name: string;
    address: string;
  };
  invoiceDetails: {
    invoiceNumber: string;
    invoiceDate: string;
    invoiceTime: string;
    currency: 'NGN';
  };
  lineItems: LineItem[];
  totals: {
    subtotal: number;
    vatAmount: number;
    totalAmount: number;
  };
  signature: string; // Digital signature
}

interface NRSResponse {
  success: boolean;
  irn?: string;           // Invoice Reference Number
  qrCodeData?: string;    // Data for QR code generation
  timestamp?: string;
  errors?: ValidationError[];
}

async function submitToNRS(payload: NRSInvoicePayload): Promise<NRSResponse> {
  const signedPayload = await signPayload(payload);
  
  const response = await fetch(NRS_EINVOICE_API, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${NRS_API_TOKEN}`,
      'X-Seller-TIN': payload.sellerDetails.tin
    },
    body: JSON.stringify(signedPayload)
  });
  
  return response.json();
}
```

### 6.5 E-Invoice Error Handling

| Error Code | Description | Resolution |
|------------|-------------|------------|
| E001 | Invalid Seller TIN | Verify TIN registration |
| E002 | Invalid Buyer TIN | Request correct TIN from customer |
| E003 | Duplicate Invoice Number | Generate new unique number |
| E004 | Invalid VAT Calculation | Recalculate VAT amount |
| E005 | Missing Required Field | Complete all mandatory fields |
| E006 | Invalid Date Format | Use YYYY-MM-DD format |
| E007 | Signature Validation Failed | Re-sign payload |
| E500 | NRS System Error | Retry with exponential backoff |

### 6.6 Offline Handling

When NRS is unavailable:

1. Save invoice as "Pending NRS Submission"
2. Queue for automatic retry (max 24 hours)
3. Notify user of pending status
4. Mark as "Failed" if 24-hour deadline exceeded
5. Require manual intervention for failed invoices

---

## 7. Development Levy (Section 59 of Nigeria Tax Act 2025)

### 7.1 Development Levy Overview

**Rate:** 4% of Assessable Profit (Section 59(1))

**Applicability:** All companies chargeable to tax under Chapters Two and Three, 
EXCEPT small companies and non-resident companies.

**Revenue Distribution (Section 59(3)):**
- Tertiary Education Trust Fund: 50%
- Nigerian Education Loan: 15%
- National Information Technology Development Fund: 8%
- National Agency for Science and Engineering Infrastructure: 8%
- National Board for Technological Incubation: 4%
- Defence and Security Infrastructure Fund: 10%
- National Cybersecurity Fund: 5%

```python
# Development Levy Calculation - Section 59, Nigeria Tax Act 2025

def calculate_development_levy(
    assessable_profit: float,
    company_size: str,
    is_resident: bool
) -> dict:
    """
    Calculate Development Levy per Section 59 of Nigeria Tax Act 2025.
    
    Exemptions:
    - Small companies (turnover ≤ ₦50M)
    - Non-resident companies
    """
    
    # Check exemptions
    if company_size == "SMALL":
        return {
            "levy_amount": 0,
            "exempt": True,
            "reason": "Small company exemption under Section 59(1)"
        }
    
    if not is_resident:
        return {
            "levy_amount": 0,
            "exempt": True,
            "reason": "Non-resident company exemption under Section 59(1)"
        }
    
    # Apply 4% Development Levy
    levy_amount = assessable_profit * 0.04
    
    return {
        "levy_amount": levy_amount,
        "exempt": False,
        "rate": 0.04,
        "legal_basis": "Section 59(1), Nigeria Tax Act 2025"
    }
```

---

## 8. Capital Gains Tax

### 8.1 CGT Changes (2026)

**Key Change:** Capital Gains Tax rate increased to 30% and merged with general income tax reporting.

| Asset Type | Pre-2026 Rate | 2026 Rate | Reporting |
|------------|---------------|-----------|-----------|
| Fixed Assets | 10% | 30% | Include in CIT computation |
| Securities | 10% | 30% | Include in CIT computation |
| Real Estate | 10% | 30% | Include in CIT computation |

### 8.2 Integration with Asset Register

```typescript
// CGT on Asset Disposal

function calculateCGT(asset: FixedAsset, salePrice: number): CGTResult {
  const costBasis = asset.acquisitionCost;
  const accumulatedDepreciation = calculateAccumulatedDepreciation(asset);
  const netBookValue = costBasis - accumulatedDepreciation;
  
  const capitalGain = salePrice - netBookValue;
  
  if (capitalGain > 0) {
    return {
      capitalGain,
      cgtLiability: capitalGain * 0.30, // 30% CGT
      netBookValue,
      salePrice
    };
  }
  
  return {
    capitalGain: 0,
    cgtLiability: 0,
    capitalLoss: Math.abs(capitalGain),
    netBookValue,
    salePrice
  };
}
```

---

## 9. Record Keeping Requirements

### 9.1 Mandatory Records

| Record Type | Retention Period | Format |
|-------------|------------------|--------|
| Invoices (Sales & Purchases) | 6 years | Digital + E-Invoice IRN |
| Bank Statements | 6 years | Digital |
| Employee Records | 6 years after employment | Digital |
| Fixed Asset Register | Life of asset + 6 years | Digital |
| VAT Returns | 6 years | Digital |
| Contracts | 6 years after completion | Digital |

### 9.2 App Compliance Features

| Requirement | App Feature |
|-------------|-------------|
| Immutable Records | Audit trail with no delete capability |
| Data Backup | Automated daily backups |
| Export Capability | CSV, PDF, Excel exports |
| Search & Retrieval | Full-text search on all records |
| Access Logs | Who accessed what and when |

---

## 10. Compliance Calendar

### 10.1 Monthly Obligations

| Day | Obligation | Responsible Party |
|-----|------------|-------------------|
| 10th | PAYE Remittance to SIRS | Employer |
| 14th | WHT Remittance (Contracts) | Withholding Agent |
| 21st | VAT Return & Payment | VAT-registered business |
| 21st | WHT Remittance (Others) | Withholding Agent |

### 10.2 Annual Obligations

| Deadline | Obligation | Applicable To |
|----------|------------|---------------|
| January 31 | Annual PAYE Reconciliation | All employers |
| March 31 | CIT Self-Assessment (First quarter) | All companies |
| June 30 | CIT Final Filing (if fiscal = calendar) | All companies |
| Ongoing | E-Invoice submission | All B2B transactions |

### 10.3 App Notification Schedule

```typescript
// Compliance Reminder Logic

const REMINDERS = [
  { days: 7, type: 'warning', message: 'VAT filing due in 7 days' },
  { days: 3, type: 'urgent', message: 'VAT filing due in 3 days' },
  { days: 1, type: 'critical', message: 'VAT filing due TOMORROW' },
  { days: 0, type: 'overdue', message: 'VAT filing is OVERDUE' },
];
```

---

## 11. Implementation Checklist

### 11.1 CIT Module

- [ ] Implement turnover tracking (accumulated annual)
- [ ] Build CIT bracket determination logic
- [ ] Create assessable profit calculation
- [ ] Generate CIT computation schedule report
- [ ] Add 0% bracket notification for qualifying businesses

### 11.2 VAT Module

- [ ] Track Output VAT on sales
- [ ] Track Input VAT on eligible purchases
- [ ] Identify service and fixed asset VAT as recoverable
- [ ] Calculate net VAT liability
- [ ] Generate VAT return data

### 11.3 PAYE Module

- [ ] Implement 2026 tax band calculator
- [ ] Calculate monthly PAYE deductions
- [ ] Generate PAYE remittance schedule
- [ ] Create employee tax deduction cards
- [ ] Annual PAYE reconciliation report

### 11.4 WHT Module

- [ ] Implement WHT rate lookup by payment type
- [ ] Build small business exemption logic (< ₦2M)
- [ ] Calculate WHT on applicable transactions
- [ ] Generate WHT credit notes
- [ ] Track WHT for remittance

### 11.5 E-Invoicing Module

- [ ] Build NRS-compliant invoice payload generator
- [ ] Implement digital signature mechanism
- [ ] Integrate with NRS E-Invoice API
- [ ] Handle IRN and QR code storage
- [ ] Implement retry logic for failed submissions
- [ ] Create offline queue mechanism
- [ ] Embed QR code in PDF invoices

### 11.6 Development Levy Module

- [ ] Calculate 4% on assessable profit
- [ ] Apply only to companies with CIT liability
- [ ] Include in CIT computation schedule

### 11.7 CGT Module

- [ ] Track fixed asset disposals
- [ ] Calculate capital gains/losses
- [ ] Apply 30% CGT rate
- [ ] Merge with general income reporting

---

## Appendix A: Glossary

| Term | Definition |
|------|------------|
| **NRS** | Nigeria Revenue Service (reformed tax authority) |
| **IRN** | Invoice Reference Number (issued by NRS) |
| **TIN** | Tax Identification Number |
| **SIRS** | State Internal Revenue Service |
| **PAYE** | Pay As You Earn (employee income tax) |
| **WHT** | Withholding Tax |
| **CIT** | Corporate Income Tax |
| **VAT** | Value Added Tax |
| **WREN** | Wholly, Reasonably, Exclusively, Necessarily (expense deductibility test) |
| **TaxPro Max** | NRS self-assessment filing portal |

---

## Appendix B: Regulatory References

- Nigeria Revenue Service: [Placeholder for official NRS website]
- Federal Ministry of Finance: [Placeholder]
- Companies Income Tax Act: [Legal reference]
- Value Added Tax Act: [Legal reference]
- Personal Income Tax Act: [Legal reference]

---

## Appendix C: Verification Required

The following items require verification against final 2026 legislation:

1. [ ] Exact CIT threshold for transitional bracket (₦50M-₦100M range)
2. [ ] PAYE band amounts and rates
3. [ ] WHT small business exemption exact threshold
4. [ ] E-invoicing go-live date and phase-in periods
5. [ ] Development Levy rate and applicability
6. [ ] CGT rate and merger with income tax
7. [ ] NRS API specifications and certification process

---
*Consult licensed tax professionals for authoritative guidance*
