# Advanced Accounting Module Documentation

> **Document Version:** 1.3  
> **Last Updated:** January 27, 2026  
> **SKU Requirement:** Various (Professional to Enterprise)  
> **API Prefix:** `/api/v1/advanced/*`

---

## Overview

The Tekvwa Pro Audit Advanced Accounting Module provides enterprise-grade financial management capabilities specifically designed for Nigerian businesses operating under the 2026 Tax Reform regulations. This module encompasses Zero-Touch Autonomous Accounting, Multi-Entity Consolidation, Tax Intelligence, and comprehensive audit compliance features.

> **SKU Gating Notes:**
> - **Intercompany Transactions:** Enterprise tier (`Feature.INTERCOMPANY`)
> - **Multi-Entity Management:** Enterprise tier (`Feature.MULTI_ENTITY`)
> - **Consolidation:** Enterprise tier (`Feature.CONSOLIDATION`)
> - **WORM Audit Vault:** Enterprise tier (`Feature.WORM_VAULT`)
> - **AI Transaction Labelling:** Intelligence Add-on (`Feature.ML_ANOMALY_DETECTION`)

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [AI Transaction Labelling](#ai-transaction-labelling)
3. [Three-Way Matching System](#three-way-matching-system)
4. [WHT Credit Vault](#wht-credit-vault)
5. [Immutable Ledger](#immutable-ledger)
6. [Approval Workflows](#approval-workflows)
7. [Tax Intelligence Command Center](#tax-intelligence-command-center)
8. [Audit Reporting](#audit-reporting)
9. [Multi-Entity Consolidation](#multi-entity-consolidation)
10. [API Reference](#api-reference)

---

## Architecture Overview

### Module Structure

```
app/
├── models/
│   └── advanced_accounting.py    # 18+ SQLAlchemy models
├── services/
│   ├── ai_labelling.py           # AI/ML transaction categorization
│   ├── immutable_ledger.py       # Blockchain-like audit trail
│   ├── tax_intelligence.py       # ETR optimization & forecasting
│   ├── audit_reporting.py        # 8 comprehensive report types
│   ├── three_way_matching.py     # PO-GRN-Invoice matching
│   ├── approval_workflow.py      # M-of-N approval system
│   └── wht_credit_vault.py       # WHT credit management
└── routers/
    └── advanced_accounting.py    # 50+ API endpoints
```

### Database Models

| Model | Description |
|-------|-------------|
| `AccountingDimension` | Dimensional accounting (Cost Center, Project, Department) |
| `TransactionDimension` | Links transactions to dimensions |
| `PurchaseOrder` | Purchase order header with approval status |
| `PurchaseOrderItem` | Line items for purchase orders |
| `GoodsReceivedNote` | GRN header for receiving goods |
| `GoodsReceivedNoteItem` | Line items for GRN |
| `ThreeWayMatch` | PO-GRN-Invoice matching records |
| `WHTCreditNote` | WHT credit notes with TIN validation |
| `Budget` | Budget headers with periods |
| `BudgetLineItem` | Budget line items by category |
| `ApprovalWorkflow` | Configurable approval workflow definitions |
| `ApprovalWorkflowApprover` | Approvers assigned to workflows |
| `ApprovalRequest` | Individual approval requests |
| `ApprovalDecision` | Decisions made on approval requests |
| `LedgerEntry` | Immutable ledger entries with hash chain |
| `EntityGroup` | Entity groupings for consolidation |
| `EntityGroupMember` | Members of entity groups |
| `IntercompanyTransaction` | Intercompany transactions for elimination |

### Enumerations

```python
class DimensionType(str, Enum):
    COST_CENTER = "cost_center"
    PROJECT = "project"
    DEPARTMENT = "department"
    LOCATION = "location"
    PRODUCT_LINE = "product_line"
    CUSTOMER_SEGMENT = "customer_segment"

class MatchingStatus(str, Enum):
    PENDING = "pending"
    MATCHED = "matched"
    PARTIAL_MATCH = "partial_match"
    DISCREPANCY = "discrepancy"
    REJECTED = "rejected"

class WHTCreditStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    APPLIED = "applied"
    EXPIRED = "expired"
    DISPUTED = "disputed"

class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    CANCELLED = "cancelled"

class BudgetPeriodType(str, Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
```

---

## AI Transaction Labelling

### Overview

The AI Transaction Labelling service provides intelligent, automated categorization of financial transactions using a three-tier prediction system:

1. **Pattern Matching** - Fast, rule-based matching for known vendors
2. **Machine Learning** - TF-IDF + Naive Bayes classifier for learned patterns
3. **OpenAI GPT-4o-mini** - LLM-based prediction for complex cases

### Nigerian Vendor Patterns

The system recognizes common Nigerian vendor patterns:

```python
VENDOR_PATTERNS = {
    "PHCN": {"category": "utilities", "gl_account": "6100"},
    "EKEDC": {"category": "utilities", "gl_account": "6100"},
    "MTN": {"category": "telecommunications", "gl_account": "6200"},
    "GLO": {"category": "telecommunications", "gl_account": "6200"},
    "AIRTEL": {"category": "telecommunications", "gl_account": "6200"},
    "FIRST BANK": {"category": "bank_charges", "gl_account": "6300"},
    "ZENITH": {"category": "bank_charges", "gl_account": "6300"},
    "GTB": {"category": "bank_charges", "gl_account": "6300"},
    "ACCESS": {"category": "bank_charges", "gl_account": "6300"},
    "TOTAL": {"category": "fuel", "gl_account": "6400"},
    "MOBIL": {"category": "fuel", "gl_account": "6400"},
    "OANDO": {"category": "fuel", "gl_account": "6400"},
    "LAWMA": {"category": "waste_management", "gl_account": "6500"},
    "LSWC": {"category": "water", "gl_account": "6100"},
}
```

### GL Account Mapping

```python
GL_ACCOUNTS = {
    "1000": "Cash and Cash Equivalents",
    "1100": "Accounts Receivable",
    "1200": "Inventory",
    "1300": "Prepaid Expenses",
    "1500": "Fixed Assets",
    "2000": "Accounts Payable",
    "2100": "Accrued Liabilities",
    "2200": "VAT Payable",
    "2300": "WHT Payable",
    "2400": "PAYE Payable",
    "3000": "Share Capital",
    "3100": "Retained Earnings",
    "4000": "Sales Revenue",
    "4100": "Service Revenue",
    "5000": "Cost of Goods Sold",
    "6000": "Operating Expenses",
    "6100": "Utilities",
    "6200": "Telecommunications",
    "6300": "Bank Charges",
    "6400": "Fuel and Transportation",
    "6500": "Office Expenses",
    "6600": "Professional Fees",
    "6700": "Rent Expense",
    "6800": "Salaries and Wages",
    "6900": "Depreciation",
}
```

### Usage Example

```python
from app.services.ai_labelling import ai_labelling_service

# Predict category for a transaction
prediction = await ai_labelling_service.predict_category(
    description="MTN Airtime Purchase",
    amount=50000.00,
    vendor_name="MTN Nigeria"
)

# Result:
# TransactionPrediction(
#     category="telecommunications",
#     gl_account="6200",
#     confidence=0.95,
#     source="pattern"
# )
```

### Training the ML Model

```python
# Train from historical transactions
await ai_labelling_service.train_from_historical_data(
    db=session,
    entity_id=entity_uuid
)
```

---

## Three-Way Matching System

### Overview

The Three-Way Matching system ensures procurement integrity by matching:
1. **Purchase Order (PO)** - What was ordered
2. **Goods Received Note (GRN)** - What was received
3. **Vendor Invoice** - What was billed

### Matching Process

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Create    │────►│   Receive   │────►│   Match     │
│   PO        │     │   Goods     │     │   Invoice   │
└─────────────┘     └─────────────┘     └─────────────┘
       │                   │                   │
       ▼                   ▼                   ▼
  PurchaseOrder     GoodsReceivedNote    ThreeWayMatch
```

### Tolerance Configuration

```python
MATCHING_TOLERANCES = {
    "quantity_tolerance_percent": 2.0,   # 2% quantity variance allowed
    "price_tolerance_percent": 1.0,      # 1% price variance allowed
    "amount_tolerance_naira": 100.00,    # ₦100 absolute tolerance
}
```

### Usage Example

```python
from app.services.three_way_matching import three_way_matching_service

# Create Purchase Order
po = await three_way_matching_service.create_purchase_order(
    db=session,
    entity_id=entity_id,
    vendor_id=vendor_id,
    items=[
        {"description": "Office Chairs", "quantity": 10, "unit_price": 25000.00},
        {"description": "Office Desks", "quantity": 5, "unit_price": 45000.00},
    ],
    created_by=user_id
)

# Create GRN when goods arrive
grn = await three_way_matching_service.create_goods_received_note(
    db=session,
    po_id=po.id,
    items=[
        {"po_item_id": po.items[0].id, "quantity_received": 10},
        {"po_item_id": po.items[1].id, "quantity_received": 5},
    ],
    received_by=user_id
)

# Match invoice to PO and GRN
match_result = await three_way_matching_service.match_invoice_to_po_grn(
    db=session,
    invoice_id=invoice_id,
    po_id=po.id,
    grn_id=grn.id
)
```

### Match Statuses

| Status | Description |
|--------|-------------|
| `MATCHED` | All three documents align within tolerance |
| `PARTIAL_MATCH` | Some items match, others have minor discrepancies |
| `DISCREPANCY` | Significant differences requiring review |
| `REJECTED` | Match rejected due to fraud indicators |

---

## WHT Credit Vault

### Overview

The WHT Credit Vault manages Withholding Tax credit notes, ensuring proper tracking, TIN validation, and automated application to tax liabilities.

### 2026 WHT Rates

```python
WHT_RATES = {
    "professional_services": Decimal("0.10"),   # 10%
    "contracts": Decimal("0.05"),               # 5%
    "consultancy": Decimal("0.10"),             # 10%
    "management_fees": Decimal("0.10"),         # 10%
    "technical_services": Decimal("0.10"),      # 10%
    "commission": Decimal("0.10"),              # 10%
    "rent": Decimal("0.10"),                    # 10%
    "dividends": Decimal("0.10"),               # 10%
    "interest": Decimal("0.10"),                # 10%
    "royalties": Decimal("0.10"),               # 10%
    "directors_fees": Decimal("0.10"),          # 10%
    "supply_contracts": Decimal("0.05"),        # 5%
    "construction": Decimal("0.05"),            # 5%
}
```

### TIN Validation

```python
def validate_tin(tin: str) -> bool:
    """
    Validate Nigerian Tax Identification Number.
    Format: XXXXXXXXXX or XX-XXXXXXXX (10 digits)
    """
    cleaned = tin.replace("-", "").replace(" ", "")
    return len(cleaned) == 10 and cleaned.isdigit()
```

### Credit Note Lifecycle

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ PENDING  │────►│ VERIFIED │────►│ APPLIED  │     │ EXPIRED  │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
                       │                                 ▲
                       │         ┌──────────┐            │
                       └────────►│ DISPUTED │────────────┘
                                 └──────────┘
```

### Usage Example

```python
from app.services.wht_credit_vault import wht_credit_vault_service

# Create WHT credit note
credit = await wht_credit_vault_service.create_credit_note(
    db=session,
    entity_id=entity_id,
    certificate_number="WHT/2026/001234",
    issuer_tin="1234567890",
    issuer_name="Nigerian Client Ltd",
    amount=150000.00,
    wht_type="professional_services",
    tax_period=date(2026, 1, 1),
    issued_by=user_id
)

# Verify credit note
verified = await wht_credit_vault_service.verify_credit_note(
    db=session,
    credit_id=credit.id,
    verified_by=user_id
)

# Apply to tax liability
applied = await wht_credit_vault_service.apply_credit_to_liability(
    db=session,
    credit_id=credit.id,
    tax_liability_amount=500000.00
)
```

---

## Immutable Ledger

### Overview

The Immutable Ledger provides blockchain-like audit trail capabilities using SHA-256 hash chains. Each entry is cryptographically linked to the previous entry, making tampering detectable.

### Hash Chain Structure

```
Entry 1          Entry 2          Entry 3
┌─────────┐     ┌─────────┐     ┌─────────┐
│ Data    │     │ Data    │     │ Data    │
│ Hash: A │────►│ Prev: A │────►│ Prev: B │
│         │     │ Hash: B │     │ Hash: C │
└─────────┘     └─────────┘     └─────────┘
```

### Hash Calculation

```python
def calculate_hash(
    sequence_number: int,
    timestamp: datetime,
    entry_type: str,
    entry_data: dict,
    previous_hash: str
) -> str:
    """Calculate SHA-256 hash of ledger entry"""
    content = f"{sequence_number}|{timestamp.isoformat()}|{entry_type}|"
    content += json.dumps(entry_data, sort_keys=True, default=str)
    content += f"|{previous_hash}"
    return hashlib.sha256(content.encode()).hexdigest()
```

### Entry Types

- `TRANSACTION_CREATED`
- `TRANSACTION_MODIFIED`
- `TRANSACTION_DELETED`
- `APPROVAL_GRANTED`
- `APPROVAL_REJECTED`
- `WHT_CREDIT_APPLIED`
- `VAT_FILED`
- `PAYROLL_PROCESSED`

### Usage Example

```python
from app.services.immutable_ledger import immutable_ledger_service

# Create ledger entry
entry = await immutable_ledger_service.create_entry(
    db=session,
    entity_id=entity_id,
    entry_type="TRANSACTION_CREATED",
    reference_type="transaction",
    reference_id=transaction_id,
    entry_data={
        "amount": 500000.00,
        "type": "expense",
        "category": "professional_services"
    },
    created_by=user_id
)

# Verify chain integrity
is_valid, invalid_entries = await immutable_ledger_service.verify_chain_integrity(
    db=session,
    entity_id=entity_id
)

# Generate audit report
report = await immutable_ledger_service.generate_audit_report(
    db=session,
    entity_id=entity_id,
    start_date=date(2026, 1, 1),
    end_date=date(2026, 12, 31)
)
```

---

## Approval Workflows

### Overview

The Approval Workflow system supports configurable M-of-N multi-signature approval processes for sensitive financial operations.

### Workflow Types

| Type | Description | Default M-of-N |
|------|-------------|----------------|
| `bulk_payment` | Bulk vendor payments | 2-of-3 |
| `payroll` | Payroll processing | 2-of-2 |
| `tax_filing` | Tax return submission | 2-of-3 |
| `journal_entry` | Manual journal entries | 1-of-2 |
| `budget_override` | Budget variance approval | 2-of-3 |

### Workflow Configuration

```python
WORKFLOW_CONFIGS = {
    "bulk_payment": {
        "min_approvers": 2,
        "max_approvers": 5,
        "escalation_hours": 24,
        "allow_delegation": True,
    },
    "payroll": {
        "min_approvers": 2,
        "max_approvers": 3,
        "escalation_hours": 48,
        "allow_delegation": False,
    },
}
```

### Approval Process

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Request   │────►│  Approver 1 │────►│  Approver 2 │
│   Created   │     │  Approves   │     │  Approves   │
└─────────────┘     └─────────────┘     └─────────────┘
                                               │
                    ┌─────────────┐            │
                    │  APPROVED   │◄───────────┘
                    │  (M-of-N)   │
                    └─────────────┘
```

### Usage Example

```python
from app.services.approval_workflow import approval_workflow_service

# Create workflow
workflow = await approval_workflow_service.create_workflow(
    db=session,
    entity_id=entity_id,
    workflow_type="bulk_payment",
    name="Vendor Payment Approval",
    required_approvals=2,
    approver_ids=[user1_id, user2_id, user3_id],
    created_by=admin_id
)

# Create approval request
request = await approval_workflow_service.create_approval_request(
    db=session,
    workflow_id=workflow.id,
    reference_type="payment_batch",
    reference_id=batch_id,
    requested_by=user_id,
    request_data={"amount": 5000000.00, "vendor_count": 15}
)

# Approve request
decision = await approval_workflow_service.approve_request(
    db=session,
    request_id=request.id,
    approver_id=user1_id,
    comments="Approved after verification"
)
```

---

## Tax Intelligence Command Center

### Overview

The Tax Intelligence Command Center provides proactive tax optimization, scenario modeling, and cash flow forecasting capabilities.

### 2026 Nigerian Tax Rates

```python
TAX_RATES_2026 = {
    "vat": Decimal("0.075"),          # 7.5%
    "cit_large": Decimal("0.30"),     # 30% (>₦100M turnover)
    "cit_medium": Decimal("0.20"),    # 20% (₦25M-₦100M turnover)
    "cit_small": Decimal("0.00"),     # 0% (<₦25M turnover)
    "dev_levy": Decimal("0.04"),      # 4% Development Levy
    "tet": Decimal("0.025"),          # 2.5% Tertiary Education Tax
    "naseni": Decimal("0.0025"),      # 0.25% NASENI Levy
    "nitda": Decimal("0.01"),         # 1% NITDA Levy (tech companies)
}
```

### Effective Tax Rate Calculation

```python
from app.services.tax_intelligence import tax_intelligence_service

# Calculate ETR
etr_analysis = await tax_intelligence_service.calculate_etr(
    db=session,
    entity_id=entity_id,
    fiscal_year=2026
)

# Result:
# {
#     "gross_revenue": 150000000.00,
#     "total_deductions": 45000000.00,
#     "taxable_income": 105000000.00,
#     "cit": 31500000.00,
#     "dev_levy": 4200000.00,
#     "tet": 2625000.00,
#     "total_tax": 38325000.00,
#     "effective_tax_rate": 0.2555  # 25.55%
# }
```

### Tax Sensitivity Analysis

```python
sensitivity = await tax_intelligence_service.tax_sensitivity_analysis(
    db=session,
    entity_id=entity_id,
    variable="revenue",
    range_percent=20  # +/- 20%
)
```

### Cash Flow Forecasting

```python
forecast = await tax_intelligence_service.forecast_cash_flow(
    db=session,
    entity_id=entity_id,
    months_ahead=12,
    include_tax_obligations=True
)
```

### Scenario Modeling

```python
scenario = await tax_intelligence_service.run_scenario(
    db=session,
    entity_id=entity_id,
    scenario_name="Expansion",
    parameters={
        "revenue_growth": 0.25,
        "expense_increase": 0.15,
        "new_asset_purchases": 50000000.00,
        "new_employees": 20
    }
)
```

---

## Audit Reporting

### Overview

The Audit Reporting service generates 8 comprehensive report types for audit compliance and financial analysis.

### Report Types

| Report | Description | API Endpoint |
|--------|-------------|--------------|
| Audit Trail | Complete transaction history | `/reports/audit-trail` |
| NRS Reconciliation | Nigeria Revenue Service reconciliation | `/reports/nrs-reconciliation` |
| WHT Tracker | WHT credit tracking and utilization | `/reports/wht-tracker` |
| Input VAT Schedule | VAT input summary for claims | `/reports/vat-schedule` |
| Payroll Statutory | PAYE, Pension, NHF, NSITF schedules | `/reports/payroll-statutory` |
| AR/AP Aging | Receivables/Payables aging analysis | `/reports/aging` |
| Budget Variance | Budget vs. actual analysis | `/reports/budget-variance` |
| Dimensional | Multi-dimensional analysis | `/reports/dimensional` |

### Report Generation

```python
from app.services.audit_reporting import audit_reporting_service

# Generate audit trail
audit_trail = await audit_reporting_service.generate_audit_trail(
    db=session,
    entity_id=entity_id,
    start_date=date(2026, 1, 1),
    end_date=date(2026, 12, 31)
)

# Generate AR aging report
aging = await audit_reporting_service.generate_aging_report(
    db=session,
    entity_id=entity_id,
    report_type="receivable",
    as_of_date=date(2026, 6, 30)
)
```

---

## Multi-Entity Consolidation

### Overview

Multi-Entity Consolidation supports group financial reporting with intercompany transaction elimination.

### Entity Group Structure

```
                    ┌─────────────────┐
                    │  Parent Entity  │
                    │  (Holding Co)   │
                    └────────┬────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
    ┌─────▼─────┐     ┌─────▼─────┐     ┌─────▼─────┐
    │ Subsidiary│     │ Subsidiary│     │ Subsidiary│
    │     A     │     │     B     │     │     C     │
    └───────────┘     └───────────┘     └───────────┘
```

### Intercompany Elimination

```python
# Intercompany transactions are automatically identified and eliminated
intercompany = IntercompanyTransaction(
    entity_group_id=group_id,
    from_entity_id=subsidiary_a_id,
    to_entity_id=subsidiary_b_id,
    transaction_type="sale",
    amount=1000000.00,
    elimination_status="pending"
)
```

---

## API Reference

### Base URL

```
/api/v1/advanced
```

### Endpoints

#### Tax Intelligence

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/tax-intelligence/etr` | Calculate Effective Tax Rate |
| GET | `/tax-intelligence/sensitivity` | Tax sensitivity analysis |
| GET | `/tax-intelligence/forecast` | Cash flow forecast |
| POST | `/tax-intelligence/scenario` | Run scenario model |

#### Purchase Orders

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/purchase-orders` | Create purchase order |
| GET | `/purchase-orders` | List purchase orders |
| GET | `/purchase-orders/{po_id}` | Get purchase order details |
| PATCH | `/purchase-orders/{po_id}/approve` | Approve purchase order |

#### Goods Received Notes

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/grn` | Create GRN |
| GET | `/grn` | List GRNs |
| GET | `/grn/{grn_id}` | Get GRN details |

#### Three-Way Matching

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/matching/match` | Match invoice to PO/GRN |
| GET | `/matching/discrepancies` | List matching discrepancies |
| POST | `/matching/resolve/{match_id}` | Resolve discrepancy |

#### WHT Credits

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/wht-credits` | Create WHT credit note |
| GET | `/wht-credits` | List WHT credits |
| PATCH | `/wht-credits/{credit_id}/verify` | Verify credit note |
| POST | `/wht-credits/{credit_id}/apply` | Apply to liability |

#### Approval Workflows

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/workflows` | Create workflow |
| GET | `/workflows` | List workflows |
| POST | `/approvals/request` | Create approval request |
| POST | `/approvals/{request_id}/approve` | Approve request |
| POST | `/approvals/{request_id}/reject` | Reject request |

#### Reports

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/reports/audit-trail` | Audit trail report |
| GET | `/reports/nrs-reconciliation` | NRS reconciliation |
| GET | `/reports/wht-tracker` | WHT tracking report |
| GET | `/reports/vat-schedule` | VAT input schedule |
| GET | `/reports/payroll-statutory` | Payroll statutory report |
| GET | `/reports/aging` | AR/AP aging report |
| GET | `/reports/budget-variance` | Budget variance report |
| GET | `/reports/dimensional` | Dimensional analysis |

#### AI & Ledger

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/ai/predict-category` | AI category prediction |
| POST | `/ai/train` | Train ML model |
| GET | `/ledger/entries` | List ledger entries |
| GET | `/ledger/verify` | Verify chain integrity |
| GET | `/ledger/audit-report` | Generate ledger audit report |

---

## Error Handling

All API endpoints return standardized error responses:

```json
{
    "detail": {
        "code": "VALIDATION_ERROR",
        "message": "Invalid TIN format",
        "field": "issuer_tin",
        "timestamp": "2026-01-06T12:00:00Z"
    }
}
```

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 422 | Input validation failed |
| `NOT_FOUND` | 404 | Resource not found |
| `UNAUTHORIZED` | 401 | Authentication required |
| `FORBIDDEN` | 403 | Permission denied |
| `CONFLICT` | 409 | Resource conflict |
| `RATE_LIMITED` | 429 | Too many requests |
| `INTERNAL_ERROR` | 500 | Internal server error |

---

## Security Considerations

1. **Hash Chain Integrity**: Ledger entries cannot be modified without detection
2. **M-of-N Approvals**: Critical operations require multiple authorizations
3. **TIN Validation**: All tax-related entities validated against FIRS format
4. **Audit Logging**: All operations logged with user attribution
5. **RBAC Integration**: Endpoints protected by role-based access control

---

## Performance Optimization

1. **Async Operations**: All database operations use async SQLAlchemy
2. **Batch Processing**: Bulk operations for high-volume transactions
3. **Caching**: ML model cached after training
4. **Indexing**: Optimized database indexes on frequently queried columns

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-01-06 | Initial release with full feature set |

---

## Support

For technical support or feature requests, contact the Tekvwa development team.
