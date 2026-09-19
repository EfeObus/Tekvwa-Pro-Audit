# Tekvwa Pro Audit - Use Cases Document

**Document Version:** 1.0  
**Date:** January 3, 2026  
**Status:** Requirements Gathering  

---

## Table of Contents

1. [Actor Definitions](#1-actor-definitions)
2. [Use Case Overview](#2-use-case-overview)
3. [Core Operations Use Cases](#3-core-operations-use-cases)
4. [Tax Compliance Use Cases](#4-tax-compliance-use-cases)
5. [Advanced Financial Pipeline Use Cases](#5-advanced-financial-pipeline-use-cases)
6. [Administrative Use Cases](#6-administrative-use-cases)
7. [Integration Use Cases](#7-integration-use-cases)
8. [User Journey Maps](#8-user-journey-maps)

---

## 1. Actor Definitions

### 1.1 Primary Actors

| Actor | Description | Key Goals |
|-------|-------------|-----------|
| **Business Owner** | SME owner managing day-to-day operations and overall compliance | Ensure business profitability while staying compliant |
| **Accountant** | Internal or external accountant handling financial records | Accurate bookkeeping and timely reporting |
| **Auditor** | Tax consultant or external auditor (read-only access) | Review financial records for compliance verification |
| **Payroll Manager** | HR/Admin staff handling employee salaries | Process payroll with correct tax deductions |
| **Inventory Manager** | Staff managing stock and warehouse operations | Maintain optimal stock levels and accurate records |

### 1.2 Secondary Actors

| Actor | Description |
|-------|-------------|
| **NRS System** | Nigeria Revenue Service e-invoicing portal |
| **Bank System** | Commercial bank for statement synchronization |
| **TaxPro Max** | NRS self-assessment portal for form uploads |
| **TIN Verification Service** | External service for vendor TIN validation |

---

## 2. Use Case Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Tekvwa Pro Audit System                        │
├─────────────────────────┬─────────────────────────┬────────────────────┤
│    CORE OPERATIONS      │    TAX COMPLIANCE       │    FINANCIAL       │
│    ─────────────────    │    ─────────────────    │    PIPELINE        │
│                         │                         │    ─────────────── │
│  UC-01: Manage Stock    │  UC-10: Create Invoice  │  UC-20: Sync Bank  │
│  UC-02: Record Expense  │  UC-11: Submit E-Invoice│  UC-21: Reconcile  │
│  UC-03: Record Income   │  UC-12: Track VAT       │  UC-22: Depreciate │
│  UC-04: Manage Vendors  │  UC-13: Calculate PAYE  │  UC-23: Self-Assess│
│  UC-05: View Reports    │  UC-14: Apply WHT       │  UC-24: Export Audit│
│  UC-06: Manage Accounts │  UC-15: Determine CIT   │                    │
│  UC-07: OCR Receipt     │  UC-16: Track Dev Levy  │                    │
│  UC-08: Stock Write-off │                         │                    │
│  UC-09: Verify TIN      │                         │                    │
└─────────────────────────┴─────────────────────────┴────────────────────┘
```

---

## 3. Core Operations Use Cases

### UC-01: Manage Inventory Stock

**Use Case ID:** UC-01  
**Name:** Manage Inventory Stock  
**Primary Actor:** Inventory Manager / Business Owner  
**Priority:** High  
**Frequency:** Daily  

#### Description
User can add, update, view, and track inventory items with real-time stock levels and automated low-stock alerts.

#### Preconditions
- User is authenticated and has inventory management permission
- At least one business entity is set up

#### Main Flow
1. User navigates to Inventory module
2. System displays current inventory list with stock levels
3. User selects action (Add Item / Update Item / View History)
4. **[Add Item]** User enters: SKU, Name, Category, Unit Cost, Quantity, Reorder Level
5. System validates input and saves item
6. System updates real-time stock count
7. System checks if stock is below reorder level
8. **[If below threshold]** System triggers low-stock alert

#### Alternative Flows
- **A1: Bulk Import** - User uploads CSV file with inventory data
- **A2: Barcode Scan** - User scans barcode to retrieve/add item

#### Postconditions
- Inventory record is updated
- Stock levels are reflected in dashboard
- Low-stock alerts are sent if applicable

#### Business Rules
- BR-01: Reorder level must be ≥ 0
- BR-02: Stock quantity cannot be negative
- BR-03: SKU must be unique within business entity

---

### UC-02: Record Business Expense

**Use Case ID:** UC-02  
**Name:** Record Business Expense  
**Primary Actor:** Accountant / Business Owner  
**Priority:** High  
**Frequency:** Daily  

#### Description
User records business expenses with automatic categorization and WREN (Wholly, Reasonably, Exclusively, Necessarily) tax deductibility flagging.

#### Preconditions
- User is authenticated with expense recording permission
- Expense categories are configured

#### Main Flow
1. User navigates to Expenses module
2. User clicks "Add Expense"
3. User enters: Date, Amount, Vendor, Category, Description
4. System auto-suggests category based on vendor history
5. System evaluates WREN criteria based on category and description
6. System displays WREN flag status (Tax Deductible / Not Deductible / Review Required)
7. User confirms or overrides WREN status
8. System saves expense with WREN classification
9. System updates expense totals and tax deduction projections

#### Alternative Flows
- **A1: OCR Receipt Scan** (See UC-07)
- **A2: Recurring Expense** - User sets expense to repeat monthly/annually

#### Postconditions
- Expense is recorded with WREN classification
- Financial summaries are updated
- Tax deduction projections are recalculated

#### WREN Classification Logic
| Category | Auto-WREN | Reason |
|----------|-----------|--------|
| Office Supplies | Yes | Wholly business-related |
| Fuel/Transport | Review | May include personal use |
| Entertainment | Review | Must be client-related |
| Personal Expenses | No | Not exclusively for business |
| Equipment Repair | Yes | Necessarily incurred |

---

### UC-03: Record Business Income

**Use Case ID:** UC-03  
**Name:** Record Business Income  
**Primary Actor:** Accountant / Business Owner  
**Priority:** High  
**Frequency:** Daily  

#### Description
User records income transactions with source categorization and VAT treatment identification.

#### Preconditions
- User is authenticated with income recording permission
- Income categories are configured

#### Main Flow
1. User navigates to Income module
2. User clicks "Add Income"
3. User enters: Date, Amount, Source/Customer, Category, Description
4. System prompts for VAT treatment (Standard/Exempt/Zero-rated)
5. User selects VAT treatment
6. System calculates VAT component if applicable
7. System saves income record
8. **[If B2B and VAT applicable]** System prompts to create invoice (See UC-10)

#### Postconditions
- Income is recorded
- VAT is calculated and tracked
- Financial summaries are updated

---

### UC-04: Manage Vendor Relationships

**Use Case ID:** UC-04  
**Name:** Manage Vendor Relationships  
**Primary Actor:** Accountant / Procurement  
**Priority:** Medium  
**Frequency:** Weekly  

#### Description
User manages vendor profiles including TIN verification and VAT compliance status tracking.

#### Preconditions
- User is authenticated with vendor management permission

#### Main Flow
1. User navigates to Supply Chain > Vendors
2. User clicks "Add Vendor"
3. User enters: Name, TIN, Address, Contact, Bank Details
4. User clicks "Verify TIN"
5. System calls TIN Verification Service API
6. System displays verification result (Valid/Invalid/Not Found)
7. System auto-populates registered business name from TIN database
8. User selects VAT compliance status (VAT Registered / Non-VAT Registered)
9. System saves vendor profile
10. System flags vendor for VAT input claims eligibility

#### Alternative Flows
- **A1: TIN Verification Fails** - System marks vendor as "Unverified" and notifies user

#### Postconditions
- Vendor is added to supplier database
- TIN verification status is recorded
- VAT compliance status affects input VAT tracking

---

### UC-05: Generate Financial Reports

**Use Case ID:** UC-05  
**Name:** Generate Financial Reports  
**Primary Actor:** Business Owner / Accountant / Auditor  
**Priority:** High  
**Frequency:** Monthly/Annually  

#### Description
User generates audit-ready financial reports including Trial Balance, Profit & Loss, and Fixed Asset Register.

#### Preconditions
- Financial transactions have been recorded
- User has report generation permission

#### Main Flow
1. User navigates to Reports module
2. System displays report types: Trial Balance, P&L, Balance Sheet, Fixed Asset Register, Cash Flow
3. User selects report type
4. User selects date range (Month/Quarter/Year/Custom)
5. User selects business entity (if multi-entity)
6. User clicks "Generate Report"
7. System compiles data and generates report
8. System displays report preview
9. User clicks "Export as PDF" or "Export as Excel"
10. System generates downloadable file

#### Report Specifications

| Report | Contents | Compliance Notes |
|--------|----------|------------------|
| Trial Balance | All account balances, debit/credit columns | NRS audit requirement |
| P&L Statement | Revenue, COGS, Expenses, Net Income | WREN-compliant expense breakdown |
| Balance Sheet | Assets, Liabilities, Equity | Fixed asset register linkage |
| Fixed Asset Register | Assets, depreciation, net book value | Capital Gains Tax ready |
| Cash Flow | Operating, Investing, Financing activities | Bank reconciliation linked |

---

### UC-06: Manage Multiple Business Entities

**Use Case ID:** UC-06  
**Name:** Manage Multiple Business Entities  
**Primary Actor:** Business Owner  
**Priority:** Medium  
**Frequency:** Setup/Occasional  

#### Description
User sets up and switches between multiple business entities with separate ledgers.

#### Main Flow
1. User navigates to Settings > Business Entities
2. User clicks "Add New Entity"
3. User enters: Business Name, TIN, Registration Number, Address, Industry
4. User configures fiscal year start date
5. User configures chart of accounts (default or custom)
6. System creates separate ledger for new entity
7. User can switch between entities via entity selector dropdown
8. System ensures data isolation between entities

#### Business Rules
- BR-01: Each entity has isolated financial data
- BR-02: Users can be granted access to specific entities
- BR-03: Consolidated reports can span multiple entities (upgrade feature)

---

### UC-07: Scan Receipt with OCR

**Use Case ID:** UC-07  
**Name:** Scan Receipt with OCR  
**Primary Actor:** Business Owner / Accountant  
**Priority:** High  
**Frequency:** Daily  

#### Description
User scans or uploads a receipt image, and the system extracts transaction details using OCR.

#### Main Flow
1. User navigates to Expenses > Scan Receipt
2. User takes photo or uploads receipt image
3. System processes image through OCR engine
4. System extracts: Date, Amount, Vendor Name, Item Details
5. System displays extracted data for user review
6. User confirms or corrects extracted fields
7. System auto-categorizes expense based on vendor/items
8. System evaluates WREN compliance
9. User saves expense record

#### Postconditions
- Expense is recorded with receipt image attached
- OCR extraction confidence score is logged
- WREN classification is applied

---

### UC-08: Write Off Damaged/Expired Stock

**Use Case ID:** UC-08  
**Name:** Stock-to-Tax Write-Off  
**Primary Actor:** Inventory Manager / Accountant  
**Priority:** Medium  
**Frequency:** As needed  

#### Description
User records damaged or expired goods for tax deduction purposes (Stock-to-Tax link).

#### Main Flow
1. User navigates to Inventory > Write-Offs
2. User selects stock items to write off
3. User enters: Quantity, Reason (Expired/Damaged/Obsolete), Supporting Notes
4. User uploads supporting documentation (photos, inspection reports)
5. System calculates write-off value (based on cost or market value)
6. System creates journal entry: Debit Loss Account, Credit Inventory
7. System flags transaction as "Tax Write-Off Eligible"
8. System updates inventory levels
9. Write-off appears in End of Year report for tax deduction

#### Business Rules
- BR-01: Write-offs must have documented justification
- BR-02: Write-off value cannot exceed original cost
- BR-03: Write-offs are reviewed during annual audit preparation

---

### UC-09: Verify Vendor TIN

**Use Case ID:** UC-09  
**Name:** Verify Vendor TIN  
**Primary Actor:** Accountant  
**Priority:** High  
**Frequency:** Per vendor onboarding  

#### Description
System verifies vendor's Tax Identification Number against NRS/FIRS database.

#### Main Flow
1. User enters vendor TIN
2. User clicks "Verify TIN"
3. System sends verification request to TIN Verification API
4. System receives response with: Validity, Registered Name, Registration Date, VAT Status
5. System displays verification result
6. **[If valid]** System auto-populates vendor details
7. **[If invalid]** System warns user and requires acknowledgment before proceeding

---

## 4. Tax Compliance Use Cases

### UC-10: Create Sales Invoice

**Use Case ID:** UC-10  
**Name:** Create Sales Invoice  
**Primary Actor:** Business Owner / Accountant  
**Priority:** Critical  
**Frequency:** Per transaction  

#### Description
User creates a sales invoice with all required NRS e-invoicing fields.

#### Main Flow
1. User navigates to Invoicing > Create Invoice
2. User enters customer details (Name, TIN, Address)
3. User adds line items: Description, Quantity, Unit Price
4. System calculates subtotal
5. System applies VAT calculation (7.5% standard rate)
6. System calculates total
7. User reviews invoice preview
8. User clicks "Save as Draft" or "Finalize"
9. **[If Finalize]** System proceeds to UC-11 (Submit E-Invoice)

#### Invoice Fields Required by NRS
| Field | Description | Validation |
|-------|-------------|------------|
| Seller TIN | Business TIN | Verified against TIN database |
| Buyer TIN | Customer TIN (for B2B) | Required for B2B transactions |
| Invoice Date | Date of issue | Cannot be future date |
| Invoice Number | Unique sequential number | Auto-generated |
| Line Items | Description, Qty, Price | At least one item required |
| VAT Amount | Calculated VAT | Auto-calculated |
| Total Amount | Grand total | Sum of subtotal + VAT |

---

### UC-11: Submit E-Invoice to NRS

**Use Case ID:** UC-11  
**Name:** Submit E-Invoice to NRS Portal  
**Primary Actor:** System (Automated)  
**Priority:** Critical  
**Frequency:** Per finalized invoice  

#### Description
System submits invoice to NRS e-invoicing portal and receives Invoice Reference Number (IRN) and QR Code.

#### Preconditions
- Invoice is finalized
- NRS API credentials are configured
- Internet connectivity is available

#### Main Flow
1. System prepares invoice data in NRS-compliant format (JSON/XML)
2. System signs invoice with digital certificate
3. System sends invoice to NRS E-Invoicing API
4. System receives response
5. **[If Success]** System stores: IRN, QR Code, Submission Timestamp
6. System updates invoice status to "NRS Submitted"
7. System embeds QR code into invoice PDF
8. Invoice is ready for delivery to customer

#### Alternative Flows
- **A1: NRS API Unavailable** - System queues invoice for retry (max 24 hours)
- **A2: Validation Error** - System displays NRS error message, user must correct and resubmit

#### E-Invoice Status Flow
```
Draft → Finalized → Submitted → IRN Received → Delivered
                  ↓
            Validation Error → Corrected → Resubmitted
```

---

### UC-12: Track Input VAT for Recovery

**Use Case ID:** UC-12  
**Name:** Track Input VAT for Recovery  
**Primary Actor:** Accountant  
**Priority:** High  
**Frequency:** Ongoing  

#### Description
System tracks VAT paid on purchases (services and fixed assets) as credits to offset against VAT collected.

#### Main Flow
1. User records purchase/expense with VAT
2. System identifies if VAT is recoverable based on:
   - Vendor is VAT-registered (verified TIN)
   - Purchase is for business use
   - Purchase category is eligible (services, fixed assets)
3. System adds VAT amount to Input VAT Register
4. System displays running Input VAT balance
5. At filing period, system calculates: Net VAT = Output VAT - Input VAT
6. System generates Input VAT recovery report

#### Input VAT Eligibility (2026 Reform)
| Purchase Type | Recoverable | Notes |
|---------------|-------------|-------|
| Raw Materials | Yes | Always recoverable |
| Services | Yes | New in 2026 reform |
| Fixed Assets | Yes | New in 2026 reform |
| Entertainment | No | Excluded |
| Personal Items | No | Not business-related |

---

### UC-13: Calculate PAYE for Employees

**Use Case ID:** UC-13  
**Name:** Calculate Progressive PAYE Tax  
**Primary Actor:** Payroll Manager  
**Priority:** High  
**Frequency:** Monthly  

#### Description
System calculates employee income tax using 2026 progressive tax bands.

#### Main Flow
1. User navigates to Payroll module
2. User enters/imports employee salary details
3. For each employee, system calculates:
   - Gross Annual Salary
   - Tax-Free Threshold (₦800,000)
   - Applicable tax bands
   - Monthly PAYE deduction
4. System generates payroll summary
5. User approves payroll
6. System generates PAYE remittance report for NRS

#### 2026 PAYE Tax Bands
| Annual Income Band | Tax Rate |
|--------------------|----------|
| First ₦800,000 | 0% (Tax-Free) |
| ₦800,001 - ₦2,400,000 | 15% |
| ₦2,400,001 - ₦4,800,000 | 20% |
| ₦4,800,001 - ₦7,200,000 | 25% |
| Above ₦7,200,000 | 30% |

#### Calculation Example
**Annual Salary: ₦3,600,000**

| Band | Calculation | Tax |
|------|-------------|-----|
| 0% | ₦800,000 × 0% | ₦0 |
| 15% | ₦1,600,000 × 15% | ₦240,000 |
| 20% | ₦1,200,000 × 20% | ₦240,000 |
| **Total Annual PAYE** | | **₦480,000** |
| **Monthly PAYE** | ÷ 12 | **₦40,000** |

---

### UC-14: Apply Withholding Tax

**Use Case ID:** UC-14  
**Name:** Apply Withholding Tax (WHT)  
**Primary Actor:** Accountant  
**Priority:** High  
**Frequency:** Per applicable transaction  

#### Description
System calculates and records Withholding Tax on qualifying payments.

#### Main Flow
1. User creates payment to vendor
2. System checks if WHT applies based on:
   - Payment type (consultancy, rent, contracts, etc.)
   - Transaction amount
   - Vendor type
3. **[If transaction < ₦2M and vendor is small business]** System exempts from WHT
4. **[If WHT applies]** System calculates WHT based on rate schedule
5. System displays: Gross Amount, WHT Deduction, Net Payment
6. User confirms payment
7. System generates WHT credit note for vendor
8. System adds WHT to remittance schedule

#### WHT Rates (2026)
| Payment Type | Rate | Exemption |
|--------------|------|-----------|
| Rent | 10% | < ₦2M (small business) |
| Dividends | 10% | < ₦2M (small business) |
| Contracts | 5% | < ₦2M (small business) |
| Consultancy | 10% | < ₦2M (small business) |
| Director Fees | 10% | None |

---

### UC-15: Determine Corporate Income Tax Rate

**Use Case ID:** UC-15  
**Name:** Determine CIT Rate and Calculate Liability  
**Primary Actor:** System (Automated)  
**Priority:** Critical  
**Frequency:** Annually  

#### Description
System determines applicable CIT rate based on company turnover and calculates tax liability.

#### Main Flow
1. System retrieves annual turnover from income records
2. System determines CIT bracket:
   - ₦0 - ₦50M: 0% CIT (Small Company)
   - ₦50M - ₦100M: 0% CIT (Transitional - verify current thresholds)
   - Above ₦100M: 30% CIT (Large Company)
3. System calculates assessable profit
4. System applies applicable CIT rate
5. **[If Large Company]** System calculates 4% Development Levy (See UC-16)
6. System generates CIT computation schedule
7. System pre-fills self-assessment form

---

### UC-16: Track Development Levy

**Use Case ID:** UC-16  
**Name:** Track and Calculate Development Levy  
**Primary Actor:** System (Automated)  
**Priority:** Medium  
**Frequency:** Annually  

#### Description
System tracks and calculates the 4% Development Levy for companies exceeding the small business threshold.

#### Main Flow
1. System monitors accumulated profit throughout the year
2. At year-end, system checks if Development Levy applies
3. **[If assessable profit > threshold]** System calculates: Levy = Assessable Profit × 4%
4. System adds Development Levy to total tax liability
5. System includes in End of Year report

---

## 5. Advanced Financial Pipeline Use Cases

### UC-20: Sync Bank Statements

**Use Case ID:** UC-20  
**Name:** Automated Bank Statement Sync  
**Primary Actor:** Accountant  
**Priority:** High  
**Frequency:** Daily (Automated)  

#### Description
System connects to bank APIs to import transactions for reconciliation.

#### Main Flow
1. User configures bank connection (one-time setup)
2. User authenticates with bank using secure token
3. System schedules daily statement imports
4. System imports transactions: Date, Description, Amount, Reference
5. System attempts auto-matching with existing records
6. System displays matched and unmatched transactions
7. User reviews and categorizes unmatched transactions

---

### UC-21: Reconcile Transactions

**Use Case ID:** UC-21  
**Name:** Bank Reconciliation  
**Primary Actor:** Accountant  
**Priority:** High  
**Frequency:** Weekly/Monthly  

#### Description
User reconciles bank statement transactions with internal ledger entries.

#### Main Flow
1. User navigates to Banking > Reconciliation
2. System displays bank transactions alongside ledger entries
3. System highlights auto-matched transactions
4. User reviews matches and confirms
5. For unmatched items, user:
   - Links to existing transaction
   - Creates new transaction
   - Marks as "No Match" with explanation
6. System calculates reconciliation status
7. User finalizes reconciliation
8. System generates reconciliation report

---

### UC-22: Track Asset Depreciation

**Use Case ID:** UC-22  
**Name:** Asset Depreciation Management  
**Primary Actor:** Accountant  
**Priority:** Medium  
**Frequency:** Monthly  

#### Description
System tracks fixed assets and calculates depreciation for accounting and tax purposes.

#### Main Flow
1. User registers fixed asset: Name, Cost, Acquisition Date, Category, Expected Life
2. System assigns depreciation method (Straight-Line / Reducing Balance)
3. System calculates annual and monthly depreciation
4. System generates monthly journal entries automatically
5. System updates Fixed Asset Register
6. At year-end, system calculates:
   - Total depreciation expense (P&L impact)
   - Net Book Value (Balance Sheet)
   - Capital Allowances (Tax computation)
7. On asset disposal, system calculates Capital Gains Tax (30% rate merged with income)

---

### UC-23: Prepare Self-Assessment

**Use Case ID:** UC-23  
**Name:** Pre-Fill NRS Self-Assessment  
**Primary Actor:** Accountant / Business Owner  
**Priority:** High  
**Frequency:** Annually  

#### Description
System generates pre-filled self-assessment data compatible with TaxPro Max upload.

#### Main Flow
1. User navigates to Tax > Self-Assessment
2. User selects tax year
3. System compiles data from all modules:
   - Total Revenue
   - Allowable Expenses (WREN-compliant)
   - Fixed Asset Depreciation
   - Input VAT Credits
   - WHT Credits
4. System calculates:
   - Assessable Profit
   - CIT Liability
   - Development Levy (if applicable)
5. System generates self-assessment form in TaxPro Max format
6. User reviews and adjusts if needed
7. User exports file for TaxPro Max upload

---

### UC-24: Export Audit-Ready Package

**Use Case ID:** UC-24  
**Name:** Generate End-of-Year Audit Package  
**Primary Actor:** Business Owner / Auditor  
**Priority:** High  
**Frequency:** Annually  

#### Description
User generates a comprehensive audit package with all required financials in one click.

#### Main Flow
1. User navigates to Reports > Annual Audit Package
2. User selects fiscal year
3. System generates:
   - Trial Balance
   - Profit & Loss Statement
   - Balance Sheet
   - Cash Flow Statement
   - Fixed Asset Register
   - Tax Computation Schedule
   - VAT Summary
   - PAYE Summary
   - E-Invoice Ledger (with IRNs)
4. System compiles into single PDF or ZIP file
5. User downloads audit package
6. Package includes "Data Integrity Certificate" with checksums

---

## 6. Administrative Use Cases

### UC-30: User Role Management

**Use Case ID:** UC-30  
**Name:** Manage User Roles and Permissions  
**Primary Actor:** Business Owner / Admin  
**Priority:** High  
**Frequency:** As needed  

#### Description
Admin configures user access levels based on role.

#### Role Definitions
| Role | Permissions |
|------|-------------|
| **Owner** | Full access to all features and settings |
| **Accountant** | Create/edit transactions, reports; No settings access |
| **Auditor** | Read-only access to all financial data |
| **Payroll** | Access only to payroll module |
| **Inventory** | Access only to inventory module |
| **Viewer** | Read-only access to dashboard and reports |

---

### UC-31: Configure Tax Settings

**Use Case ID:** UC-31  
**Name:** Configure Tax Parameters  
**Primary Actor:** Business Owner / Accountant  
**Priority:** High  
**Frequency:** Setup / Annual Review  

#### Description
User configures business-specific tax settings.

#### Configuration Options
- Fiscal year start date
- VAT registration status (Yes/No)
- CIT category (Small/Medium/Large)
- WHT agent status
- State of operation (for PAYE)
- NRS API credentials

---

## 7. Integration Use Cases

### UC-40: NRS E-Invoicing Integration

**Use Case ID:** UC-40  
**Name:** Configure NRS API Connection  
**Primary Actor:** Admin  
**Priority:** Critical  
**Frequency:** One-time setup  

#### Description
System is configured to communicate with NRS e-invoicing portal.

#### Setup Flow
1. User obtains NRS API credentials from NRS portal
2. User enters: API Key, Secret, Environment (Sandbox/Production)
3. System tests connection
4. System retrieves and stores NRS certificate
5. System is ready for e-invoice submissions

---

### UC-41: Bank Integration Setup

**Use Case ID:** UC-41  
**Name:** Configure Bank Connection  
**Primary Actor:** Admin / Accountant  
**Priority:** High  
**Frequency:** One-time per bank  

#### Supported Banks (Planned)
- GTBank
- Access Bank
- UBA
- First Bank
- Zenith Bank

---

## 8. User Journey Maps

### Journey 1: New Business Onboarding

```
DAY 1                    WEEK 1                    MONTH 1
─────────────────────────────────────────────────────────────
Sign Up                  Configure Settings        First Compliance
   │                          │                         │
   ├── Create Account         ├── Add Bank Account      ├── Generate Invoice
   ├── Verify Email           ├── Set Up Inventory      ├── Submit to NRS
   ├── Enter Business Info    ├── Add Vendors (TIN)     ├── Record First VAT
   ├── Upload TIN Cert        ├── Configure Payroll     ├── Run First Payroll
   └── Choose Plan            └── Import Opening Balances└── Review Dashboard
```

### Journey 2: Monthly Compliance Cycle

```
WEEK 1-2 (Transactions)    WEEK 3 (Reconciliation)    WEEK 4 (Filing)
───────────────────────────────────────────────────────────────────────
Record Income               Bank Sync                   VAT Filing Prep
Record Expenses             Match Transactions          PAYE Remittance
Issue Invoices              Resolve Discrepancies       WHT Remittance
Submit E-Invoices           Update Inventory            Generate Reports
OCR Receipt Scans           Asset Depreciation          Manager Review
```

### Journey 3: End of Year

```
MONTH 12                   MONTH 1 (New Year)         FILING DEADLINE
──────────────────────────────────────────────────────────────────────
Close Books                Generate Reports            Self-Assessment
   │                           │                           │
   ├── Final Reconciliation    ├── Trial Balance           ├── Pre-fill Forms
   ├── Depreciation Close      ├── P&L Statement           ├── Review with Auditor
   ├── Stock Take              ├── Balance Sheet           ├── Upload to TaxPro Max
   ├── VAT Reconciliation      ├── Fixed Asset Register    ├── Payment Processing
   └── CIT Calculation         └── Audit Package           └── Archive Year
```

---

## Appendix A: Use Case Traceability Matrix

| Use Case | Feature Requirement | Priority | Status |
|----------|---------------------|----------|--------|
| UC-01 | Inventory Management | High | Planned |
| UC-02 | Expense Tracking | High | Planned |
| UC-03 | Income Tracking | High | Planned |
| UC-07 | OCR Receipt Scanning | High | Planned |
| UC-10, UC-11 | NRS E-Invoicing | Critical | Planned |
| UC-12 | Input VAT Recovery | High | Planned |
| UC-13 | Progressive PAYE | High | Planned |
| UC-14 | WHT Manager | High | Planned |
| UC-15, UC-16 | CIT & Dev Levy | Critical | Planned |
| UC-20, UC-21 | Banking Sync | High | Planned |
| UC-22 | Asset Depreciation | Medium | Planned |
| UC-23 | Self-Assessment | High | Planned |
| UC-24 | Audit Reports | High | Planned |

---

*Document maintained by Tekvwa Pro Audit Product Team*
