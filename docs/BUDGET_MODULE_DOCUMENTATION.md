# Budget Module Documentation

> **Document Version:** 1.2  
> **Last Updated:** January 27, 2026  
> **SKU Requirement:** Professional tier or higher (`Feature.BUDGET_MANAGEMENT`)  
> **API Prefix:** `/api/v1/entities/{entity_id}/budgets`

---

## Overview

The Tekvwa Pro Audit Budget Module provides comprehensive budgeting capabilities including budget creation, multi-level approval workflows, variance analysis, and rolling forecasts. It supports annual, quarterly, and monthly budgeting with flexible allocation methods.

> **⚠️ SKU Gating:** This module requires **Pro Audit Professional** (₦150,000-400,000/mo) or **Enterprise** (₦1,000,000-5,000,000+/mo) tier. Core tier users will receive a `403 Forbidden` response with upgrade instructions.

### Key Features

- **Budget Creation:** Annual, quarterly, and monthly budgets with flexible periods
- **Approval Workflows:** M-of-N approval with sequential/parallel modes
- **Variance Analysis:** Budget vs Actual with favorable/unfavorable tracking
- **Rolling Forecasts:** Hybrid forecasting combining actuals with projections
- **Version Control:** Budget revisions with full audit trail
- **Dimension Support:** Department, project, and cost center budgeting

---

## Table of Contents

1. [Budget Structure](#budget-structure)
2. [Budget Creation](#budget-creation)
3. [Approval Workflow](#approval-workflow)
4. [Variance Analysis](#variance-analysis)
5. [Budget Forecasting](#budget-forecasting)
6. [Budget Reports](#budget-reports)
7. [API Reference](#api-reference)
8. [Best Practices](#best-practices)

---

## Budget Structure

### Hierarchy

```
Budget
├── Budget Period (Annual 2026)
│   ├── Budget Line Items
│   │   ├── Revenue - Sales (Q1, Q2, Q3, Q4)
│   │   ├── Revenue - Services (Q1, Q2, Q3, Q4)
│   │   ├── Expense - Salaries (Q1, Q2, Q3, Q4)
│   │   └── Expense - Rent (Q1, Q2, Q3, Q4)
│   └── Budget Versions
│       ├── v1 - Original
│       ├── v2 - Q1 Revision
│       └── v3 - Mid-year Update
```

### Budget Status Lifecycle

```
DRAFT → SUBMITTED → PENDING_APPROVAL → APPROVED → ACTIVE
                  ↓
              REJECTED → DRAFT (revision)
```

### Budget Periods

| Period Type | Duration | Description |
|-------------|----------|-------------|
| Annual | 12 months | Full fiscal year budget |
| Quarterly | 3 months | Rolling quarterly budget |
| Monthly | 1 month | Detailed monthly budget |

---

## Budget Creation

### Create Annual Budget

```json
POST /api/v1/budgets
{
  "name": "FY2026 Operating Budget",
  "description": "Annual operating budget for fiscal year 2026",
  "fiscal_year": 2026,
  "period_type": "annual",
  "start_date": "2026-01-01",
  "end_date": "2026-12-31",
  "currency": "NGN"
}
```

### Response

```json
{
  "id": "budget-uuid",
  "name": "FY2026 Operating Budget",
  "fiscal_year": 2026,
  "period_type": "annual",
  "status": "draft",
  "version": 1,
  "created_at": "2026-01-10T10:00:00Z"
}
```

### Add Budget Line Items

```json
POST /api/v1/budgets/{budget_id}/line-items
{
  "account_id": "4000-sales-revenue",
  "account_code": "4000",
  "account_name": "Sales Revenue",
  "category": "revenue",
  "annual_amount": "500000000.00",
  "allocation_method": "seasonal",
  "quarterly_amounts": {
    "Q1": "100000000.00",
    "Q2": "125000000.00",
    "Q3": "125000000.00",
    "Q4": "150000000.00"
  }
}
```

### Allocation Methods

| Method | Description | Use Case |
|--------|-------------|----------|
| **even** | Equal distribution across periods | Fixed costs (rent, subscriptions) |
| **seasonal** | Custom amounts per period | Revenue with seasonal patterns |
| **front_loaded** | Higher in earlier periods | Project-based spending |
| **back_loaded** | Higher in later periods | Year-end initiatives |
| **percentage** | Custom percentage per period | Complex allocations |

### Bulk Import Line Items

```json
POST /api/v1/budgets/{budget_id}/line-items/bulk
{
  "line_items": [
    {
      "account_code": "4000",
      "account_name": "Sales Revenue",
      "category": "revenue",
      "annual_amount": "500000000.00",
      "allocation_method": "seasonal",
      "quarterly_amounts": {
        "Q1": "100000000.00",
        "Q2": "125000000.00",
        "Q3": "125000000.00",
        "Q4": "150000000.00"
      }
    },
    {
      "account_code": "5000",
      "account_name": "Cost of Goods Sold",
      "category": "expense",
      "annual_amount": "300000000.00",
      "allocation_method": "percentage",
      "percentage_allocation": [20, 25, 25, 30]
    },
    {
      "account_code": "6000",
      "account_name": "Salaries Expense",
      "category": "expense",
      "annual_amount": "120000000.00",
      "allocation_method": "even"
    }
  ]
}
```

---

## Approval Workflow

### Workflow Stages

```
┌─────────────┐    ┌───────────────┐    ┌───────────────┐    ┌──────────┐
│   DRAFT     │───▶│   SUBMITTED   │───▶│   PENDING     │───▶│ APPROVED │
│             │    │               │    │   APPROVAL    │    │          │
└─────────────┘    └───────────────┘    └───────────────┘    └──────────┘
                                                │
                                                ▼
                                        ┌───────────────┐
                                        │   REJECTED    │
                                        │ (with notes)  │
                                        └───────────────┘
```

### Submit Budget for Approval

```json
POST /api/v1/budgets/{budget_id}/submit
{
  "submitted_by": "user-uuid",
  "notes": "FY2026 budget ready for management review"
}
```

### Configure Approvers

```json
POST /api/v1/budgets/{budget_id}/approvers
{
  "approvers": [
    {
      "user_id": "dept-manager-uuid",
      "level": 1,
      "required": true,
      "description": "Department Manager"
    },
    {
      "user_id": "finance-director-uuid",
      "level": 2,
      "required": true,
      "description": "Finance Director"
    },
    {
      "user_id": "cfo-uuid",
      "level": 3,
      "required": true,
      "description": "CFO Final Approval"
    }
  ],
  "approval_mode": "sequential"
}
```

### Approval Modes

| Mode | Description |
|------|-------------|
| **sequential** | Approvers must approve in order (Level 1 → 2 → 3) |
| **parallel** | All approvers can approve simultaneously |
| **any** | Any single approver can approve |

### Approve/Reject Budget

```json
POST /api/v1/budgets/{budget_id}/approve
{
  "approved_by": "cfo-uuid",
  "decision": "approved",
  "notes": "Approved as submitted"
}
```

```json
POST /api/v1/budgets/{budget_id}/approve
{
  "approved_by": "finance-director-uuid",
  "decision": "rejected",
  "notes": "Marketing budget needs reduction by 15%",
  "rejection_details": {
    "line_items_flagged": ["6200", "6210"],
    "requested_changes": "Reduce conference and travel budget"
  }
}
```

---

## Variance Analysis

Variance analysis compares actual results to budgeted amounts, identifying favorable and unfavorable variances.

### Variance Types

| Variance | Formula | Favorable When |
|----------|---------|----------------|
| **Revenue** | Actual - Budget | Actual > Budget |
| **Expense** | Budget - Actual | Actual < Budget |
| **Percentage** | (Variance / Budget) × 100 | Depends on type |

### Get Variance Report

```json
GET /api/v1/budgets/{budget_id}/variance
{
  "period": "Q1",
  "as_of_date": "2026-03-31"
}
```

### Response

```json
{
  "budget_id": "budget-uuid",
  "budget_name": "FY2026 Operating Budget",
  "period": "Q1",
  "as_of_date": "2026-03-31",
  "variances": [
    {
      "account_code": "4000",
      "account_name": "Sales Revenue",
      "category": "revenue",
      "budget_amount": "100000000.00",
      "actual_amount": "108000000.00",
      "variance_amount": "8000000.00",
      "variance_percentage": "8.00",
      "variance_type": "favorable",
      "status": "on_track"
    },
    {
      "account_code": "6000",
      "account_name": "Salaries Expense",
      "category": "expense",
      "budget_amount": "30000000.00",
      "actual_amount": "32000000.00",
      "variance_amount": "-2000000.00",
      "variance_percentage": "-6.67",
      "variance_type": "unfavorable",
      "status": "over_budget"
    }
  ],
  "summary": {
    "total_budget_revenue": "100000000.00",
    "total_actual_revenue": "108000000.00",
    "revenue_variance": "8000000.00",
    "total_budget_expense": "80000000.00",
    "total_actual_expense": "84500000.00",
    "expense_variance": "-4500000.00",
    "net_variance": "3500000.00"
  }
}
```

### YTD Variance

```json
GET /api/v1/budgets/{budget_id}/variance/ytd
{
  "as_of_date": "2026-06-30"
}
```

### Response

```json
{
  "ytd_budget": "250000000.00",
  "ytd_actual": "262000000.00",
  "ytd_variance": "12000000.00",
  "ytd_variance_percentage": "4.80",
  "periods_included": ["Q1", "Q2"],
  "monthly_trend": [
    {"month": "January", "budget": "40000000.00", "actual": "42000000.00"},
    {"month": "February", "budget": "42000000.00", "actual": "44000000.00"},
    {"month": "March", "budget": "43000000.00", "actual": "45000000.00"},
    {"month": "April", "budget": "42000000.00", "actual": "43000000.00"},
    {"month": "May", "budget": "41000000.00", "actual": "44000000.00"},
    {"month": "June", "budget": "42000000.00", "actual": "44000000.00"}
  ]
}
```

### Variance Alerts

Configure thresholds for automatic alerts:

```json
POST /api/v1/budgets/{budget_id}/alerts
{
  "thresholds": [
    {
      "variance_type": "unfavorable",
      "threshold_percentage": 10,
      "alert_level": "warning",
      "notify": ["finance-director-uuid"]
    },
    {
      "variance_type": "unfavorable",
      "threshold_percentage": 20,
      "alert_level": "critical",
      "notify": ["finance-director-uuid", "cfo-uuid"]
    }
  ]
}
```

---

## Budget Forecasting

Rolling forecasts combine actuals with projections to estimate year-end results.

### Forecast Methods

| Method | Description |
|--------|-------------|
| **linear** | Project based on current run rate |
| **seasonal** | Apply historical seasonal patterns |
| **trend** | Apply growth/decline trends |
| **hybrid** | Actuals + remaining budget |

### Generate Forecast

```json
POST /api/v1/budgets/{budget_id}/forecast
{
  "as_of_date": "2026-06-30",
  "method": "hybrid",
  "projection_periods": ["Q3", "Q4"]
}
```

### Response

```json
{
  "budget_id": "budget-uuid",
  "forecast_date": "2026-06-30",
  "method": "hybrid",
  "forecast_items": [
    {
      "account_code": "4000",
      "account_name": "Sales Revenue",
      "ytd_actual": "225000000.00",
      "original_annual_budget": "500000000.00",
      "remaining_budget": "275000000.00",
      "projected_q3": "140000000.00",
      "projected_q4": "165000000.00",
      "forecast_annual": "530000000.00",
      "variance_to_budget": "30000000.00",
      "variance_percentage": "6.00"
    }
  ],
  "summary": {
    "original_budget_net_income": "80000000.00",
    "forecast_net_income": "92000000.00",
    "improvement": "12000000.00"
  }
}
```

### Rolling Forecast Update

```json
POST /api/v1/budgets/{budget_id}/forecast/update
{
  "period": "Q3",
  "adjustments": [
    {
      "account_code": "4000",
      "adjusted_amount": "145000000.00",
      "reason": "New customer contract signed"
    },
    {
      "account_code": "6200",
      "adjusted_amount": "12000000.00",
      "reason": "Deferred marketing campaign to Q4"
    }
  ],
  "updated_by": "finance-manager-uuid"
}
```

---

## Budget Reports

### Available Reports

| Report | Description |
|--------|-------------|
| Budget Summary | High-level budget overview |
| Variance Report | Detailed actual vs budget |
| Forecast Report | Year-end projections |
| Approval History | Budget approval audit trail |
| Version Comparison | Compare budget versions |

### Generate Budget Summary Report

```json
POST /api/v1/reports/budget-summary
{
  "budget_id": "budget-uuid",
  "format": "pdf",
  "include_charts": true
}
```

### Budget vs Actual Report (Excel)

```json
POST /api/v1/reports/budget-variance
{
  "budget_id": "budget-uuid",
  "format": "xlsx",
  "period_start": "2026-01-01",
  "period_end": "2026-06-30",
  "grouping": "department"
}
```

---

## API Reference

### Budget Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/budgets` | Create new budget |
| GET | `/budgets` | List all budgets |
| GET | `/budgets/{id}` | Get budget details |
| PUT | `/budgets/{id}` | Update budget |
| DELETE | `/budgets/{id}` | Delete draft budget |

### Budget Line Item Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/budgets/{id}/line-items` | Add line item |
| GET | `/budgets/{id}/line-items` | List line items |
| PUT | `/budgets/{id}/line-items/{item_id}` | Update line item |
| DELETE | `/budgets/{id}/line-items/{item_id}` | Delete line item |
| POST | `/budgets/{id}/line-items/bulk` | Bulk import |

### Approval Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/budgets/{id}/submit` | Submit for approval |
| POST | `/budgets/{id}/approve` | Approve/reject |
| GET | `/budgets/{id}/approval-history` | Get approval history |

### Analysis Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/budgets/{id}/variance` | Get variance report |
| GET | `/budgets/{id}/variance/ytd` | Get YTD variance |
| POST | `/budgets/{id}/forecast` | Generate forecast |
| POST | `/budgets/{id}/forecast/update` | Update forecast |

---

## Best Practices

### 1. Start with Historical Data

Use prior year actuals as a baseline:
```json
POST /api/v1/budgets/{budget_id}/import-baseline
{
  "source": "prior_year_actual",
  "year": 2025,
  "adjustment_percentage": 5
}
```

### 2. Use Realistic Assumptions

Document assumptions for each budget line:
```json
{
  "account_code": "4000",
  "annual_amount": "500000000.00",
  "assumptions": [
    "5% price increase effective Q2",
    "New product launch contributing 15% of revenue",
    "No significant customer churn expected"
  ]
}
```

### 3. Regular Variance Reviews

- **Weekly**: Review critical expense categories
- **Monthly**: Full variance analysis with management
- **Quarterly**: Forecast update and budget revision if needed

### 4. Version Control

Create new versions for significant changes:
```json
POST /api/v1/budgets/{budget_id}/new-version
{
  "version_name": "Q2 Revision",
  "reason": "Updated revenue projections based on Q1 results",
  "changes_summary": "Revenue increased 10%, Marketing reduced 5%"
}
```

### 5. Threshold Monitoring

Set up appropriate variance thresholds:

| Category | Warning | Critical |
|----------|---------|----------|
| Revenue | -5% | -10% |
| COGS | +5% | +10% |
| OpEx | +10% | +20% |
| CapEx | +15% | +25% |

---

## Budget Checklist

### Budget Creation
- [ ] Define fiscal year and periods
- [ ] Import or create line items
- [ ] Set allocation methods
- [ ] Document assumptions
- [ ] Review and validate totals

### Approval Process
- [ ] Configure approval workflow
- [ ] Submit for review
- [ ] Address feedback/rejections
- [ ] Obtain all required approvals
- [ ] Activate budget

### Ongoing Management
- [ ] Monthly variance analysis
- [ ] Quarterly forecast updates
- [ ] Document significant variances
- [ ] Communicate with stakeholders
- [ ] Prepare revision if needed

---

## Troubleshooting

### Issue: Budget Won't Submit

**Causes:**
1. Missing required line items
2. Unbalanced revenue/expense totals
3. Invalid allocation amounts

**Solution:**
```json
GET /api/v1/budgets/{budget_id}/validate
```
Returns validation errors to address.

### Issue: Variance Calculation Incorrect

**Causes:**
1. Actual amounts not yet posted to GL
2. Account mapping mismatch
3. Period dates misaligned

**Solution:**
1. Verify GL entries are posted
2. Check budget line item account codes match GL
3. Confirm period dates align with accounting periods

### Issue: Forecast Not Reflecting Actuals

**Causes:**
1. Forecast method doesn't consider recent actuals
2. YTD actuals haven't been updated

**Solution:**
```json
POST /api/v1/budgets/{budget_id}/forecast/refresh
{
  "include_latest_actuals": true,
  "as_of_date": "2026-06-30"
}
```
