# Tekvwa Pro Audit - Payroll System Documentation

## Overview

Tekvwa Pro Audit includes a comprehensive payroll management system built specifically for Nigerian businesses. The system handles all statutory deductions, compliance requirements, and provides complete employee compensation management.

---

## Table of Contents

1. [Nigerian Statutory Compliance](#1-nigerian-statutory-compliance)
2. [Core Data Models](#2-core-data-models)
3. [Payroll Processing Workflow](#3-payroll-processing-workflow)
4. [API Endpoints](#4-api-endpoints)
5. [Salary Calculations](#5-salary-calculations)
6. [Statutory Deductions](#6-statutory-deductions)
7. [Reports & Exports](#7-reports--exports)
8. [Leave & Loan Management](#8-leave--loan-management)
9. [Configuration Options](#9-configuration-options)

---

## 1. Nigerian Statutory Compliance

The payroll system is fully compliant with Nigerian employment and tax regulations:

### 1.1 PAYE (Pay As You Earn)
- **Description**: Personal Income Tax deducted at source
- **Tax Bands (2026 Reform)**:
  | Annual Income | Rate |
  |--------------|------|
  | First ₦300,000 | 7% |
  | Next ₦300,000 | 11% |
  | Next ₦500,000 | 15% |
  | Next ₦500,000 | 19% |
  | Next ₦1,600,000 | 21% |
  | Above ₦3,200,000 | 24% |

- **Consolidated Relief Allowance (CRA)**: Higher of ₦200,000 or 1% of gross income, plus 20% of gross income

### 1.2 Pension (Contributory Pension Scheme)
- **Employee Contribution**: 8% of (Basic + Housing + Transport)
- **Employer Contribution**: 10% of (Basic + Housing + Transport)
- **Regulated by**: PenCom (National Pension Commission)
- **Minimum Contribution**: ₦70,000 minimum wage as base

### 1.3 NHF (National Housing Fund)
- **Rate**: 2.5% of Basic Salary
- **Contribution**: Employee only
- **Purpose**: Home ownership fund

### 1.4 NSITF (Nigeria Social Insurance Trust Fund)
- **Rate**: 1% of monthly payroll
- **Contribution**: Employer only
- **Purpose**: Employee compensation insurance

### 1.5 ITF (Industrial Training Fund)
- **Rate**: 1% of annual payroll
- **Contribution**: Employer only
- **Applicability**: Companies with 5+ employees OR ₦50M+ annual turnover

---

## 2. Core Data Models

### 2.1 Employee Model

```python
# Key Fields
- employee_id        # Internal staff number
- first_name, middle_name, last_name
- email, phone_number
- date_of_birth, gender, marital_status

# Nigerian Identification
- nin               # National Identification Number
- bvn               # Bank Verification Number
- tin               # Tax Identification Number (PAYE)
- tax_state         # State for PAYE remittance

# Pension Details
- pension_pin       # RSA PIN
- pfa               # Pension Fund Administrator
- is_pension_exempt # Exemption flag

# NHF
- nhf_number
- is_nhf_exempt

# Employment Details
- employment_type   # FULL_TIME, PART_TIME, CONTRACT, INTERN, PROBATION, CONSULTANT
- employment_status # ACTIVE, INACTIVE, TERMINATED, RESIGNED, RETIRED, SUSPENDED, ON_LEAVE
- department, job_title, job_grade
- hire_date, confirmation_date, termination_date

# Salary Components
- basic_salary      # Monthly basic
- housing_allowance # Monthly housing
- transport_allowance # Monthly transport
- other_allowances  # JSON for additional allowances

# 2026 Tax Reform
- annual_rent_paid      # For Rent Relief calculation
- has_life_insurance
- monthly_insurance_premium
```

### 2.2 Payroll Run Model

Represents a pay period processing batch:

```python
- payroll_code      # Unique code (e.g., PAY-2026-01-001)
- name              # Descriptive name
- frequency         # WEEKLY, BI_WEEKLY, MONTHLY
- period_start, period_end
- payment_date
- status            # DRAFT, PENDING_APPROVAL, APPROVED, PROCESSING, COMPLETED, PAID, CANCELLED

# Totals
- total_employees
- total_gross_pay
- total_deductions
- total_net_pay
- total_employer_contributions

# Statutory Totals
- total_paye
- total_pension_employee
- total_pension_employer
- total_nhf
- total_nsitf
- total_itf
```

### 2.3 Payslip Model

Individual employee payslip:

```python
- payslip_number
- days_in_period, days_worked, days_absent

# Earnings
- basic_salary
- housing_allowance
- transport_allowance
- other_earnings
- gross_pay

# Deductions
- paye_tax
- pension_employee
- nhf
- other_deductions
- total_deductions

# Net
- net_pay

# Employer Contributions (not deducted)
- pension_employer
- nsitf
- itf

# Tax Details
- consolidated_relief
- taxable_income
- tax_calculation  # JSON with band breakdown

# Payment
- bank_name, account_number, account_name
- is_paid, paid_at
```

### 2.4 Supporting Models

| Model | Purpose |
|-------|---------|
| `EmployeeBankAccount` | Employee bank details for salary payments |
| `PayslipItem` | Line items (earnings/deductions) on payslip |
| `StatutoryRemittance` | Track PAYE, Pension, NHF payments |
| `EmployeeLoan` | Loans and salary advances |
| `LoanRepayment` | Loan repayment records |
| `EmployeeLeave` | Leave requests and approvals |
| `PayrollSettings` | Entity-level configuration |

---

## 3. Payroll Processing Workflow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   DRAFT     │────▶│  PENDING    │────▶│  APPROVED   │────▶│ PROCESSING  │
│             │     │  APPROVAL   │     │             │     │             │
└─────────────┘     └─────────────┘     └─────────────┘     └──────┬──────┘
                                                                    │
                                                                    ▼
                                        ┌─────────────┐     ┌─────────────┐
                                        │    PAID     │◀────│  COMPLETED  │
                                        │             │     │             │
                                        └─────────────┘     └─────────────┘
```

### 3.1 Step-by-Step Process

1. **Create Payroll Run** (`POST /api/payroll/runs`)
   - Specify pay period (start/end dates)
   - Select employees (or include all active)
   - System generates payslips automatically

2. **Review Draft**
   - View generated payslips
   - Make adjustments if needed
   - Check calculations

3. **Submit for Approval** (`PATCH /api/payroll/runs/{id}`)
   - Change status to `pending_approval`

4. **Approve Payroll** (`POST /api/payroll/runs/{id}/approve`)
   - Authorized user approves
   - Records approval timestamp

5. **Process Payroll** (`POST /api/payroll/runs/{id}/process`)
   - Finalizes calculations
   - Creates statutory remittance records
   - Status → `completed`

6. **Mark as Paid** (`POST /api/payroll/runs/{id}/mark-paid`)
   - After bank transfers complete
   - Updates all payslips

---

## 4. API Endpoints

### 4.1 Employee Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/payroll/employees` | Create new employee |
| `GET` | `/api/payroll/employees` | List employees (paginated) |
| `GET` | `/api/payroll/employees/{id}` | Get employee details |
| `PATCH` | `/api/payroll/employees/{id}` | Update employee |
| `DELETE` | `/api/payroll/employees/{id}` | Deactivate employee |
| `GET` | `/api/payroll/employees/departments` | List departments |
| `POST` | `/api/payroll/employees/{id}/bank-accounts` | Add bank account |

### 4.2 Payroll Processing

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/payroll/runs` | Create payroll run |
| `GET` | `/api/payroll/runs` | List payroll runs |
| `GET` | `/api/payroll/runs/{id}` | Get payroll details |
| `PATCH` | `/api/payroll/runs/{id}` | Update payroll run |
| `DELETE` | `/api/payroll/runs/{id}` | Cancel payroll |
| `POST` | `/api/payroll/runs/{id}/approve` | Approve payroll |
| `POST` | `/api/payroll/runs/{id}/process` | Process payroll |
| `POST` | `/api/payroll/runs/{id}/mark-paid` | Mark as paid |

### 4.3 Payslips

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/payroll/runs/{id}/payslips` | List payslips in run |
| `GET` | `/api/payroll/payslips/{id}` | Get payslip details |
| `GET` | `/api/payroll/employees/{id}/payslips` | Employee payslip history |
| `GET` | `/api/payroll/payslips/{id}/pdf` | Download payslip PDF |

### 4.4 Calculations

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/payroll/calculate-salary` | Calculate salary breakdown |
| `GET` | `/api/payroll/runs/{id}/bank-schedule` | Generate bank payment file |

### 4.5 Statutory Remittances

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/payroll/remittances` | List remittances |
| `GET` | `/api/payroll/remittances/{id}` | Get remittance details |
| `POST` | `/api/payroll/remittances/{id}/mark-paid` | Record payment |

### 4.6 Dashboard & Reports

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/payroll/dashboard` | Payroll dashboard stats |
| `GET` | `/api/payroll/reports/annual-summary` | Annual summary |
| `GET` | `/api/payroll/reports/tax-summary` | Tax summary report |

---

## 5. Salary Calculations

### 5.1 Gross Salary

```
Monthly Gross = Basic Salary + Housing Allowance + Transport Allowance + Other Allowances
Annual Gross = Monthly Gross × 12
```

### 5.2 Pensionable Earnings

Per PenCom regulations:
```
Pensionable Earnings = Basic + Housing + Transport
```

### 5.3 PAYE Calculation

```
1. Calculate Annual Gross Income
2. Calculate Reliefs:
   - CRA = max(₦200,000, 1% of Gross) + 20% of Gross
   - Pension Relief (8% of pensionable × 12)
   - NHF Relief (2.5% of basic × 12)
   - Other reliefs (rent, life insurance)

3. Taxable Income = Annual Gross - Total Reliefs

4. Apply Tax Bands (cumulative)

5. Monthly PAYE = Annual PAYE ÷ 12
```

### 5.4 Example Calculation

**Employee Salary**:
- Basic: ₦500,000/month
- Housing: ₦250,000/month
- Transport: ₦100,000/month

```
Annual Gross = ₦850,000 × 12 = ₦10,200,000

CRA = max(₦200,000, ₦102,000) + ₦2,040,000 = ₦2,240,000
Pension Relief = ₦850,000 × 8% × 12 = ₦816,000
NHF Relief = ₦500,000 × 2.5% × 12 = ₦150,000
Total Reliefs = ₦3,206,000

Taxable Income = ₦10,200,000 - ₦3,206,000 = ₦6,994,000

Tax Calculation:
- ₦300,000 × 7% = ₦21,000
- ₦300,000 × 11% = ₦33,000
- ₦500,000 × 15% = ₦75,000
- ₦500,000 × 19% = ₦95,000
- ₦1,600,000 × 21% = ₦336,000
- ₦3,794,000 × 24% = ₦910,560

Annual PAYE = ₦1,470,560
Monthly PAYE = ₦122,547
```

---

## 6. Statutory Deductions

### 6.1 Monthly Employee Deductions

| Deduction | Rate | Base | Typical Amount |
|-----------|------|------|----------------|
| PAYE Tax | Progressive | Taxable Income | Varies |
| Pension | 8% | Basic + Housing + Transport | ₦68,000 |
| NHF | 2.5% | Basic Salary | ₦12,500 |

### 6.2 Employer Contributions (Not Deducted from Employee)

| Contribution | Rate | Base |
|--------------|------|------|
| Pension | 10% | Basic + Housing + Transport |
| NSITF | 1% | Total Monthly Payroll |
| ITF | 1% ÷ 12 | Annual Payroll |

### 6.3 Remittance Due Dates

| Type | Due Date |
|------|----------|
| PAYE | 10th of following month |
| Pension | 7th of following month |
| NHF | 10th of following month |
| NSITF | 15th of following month |
| ITF | Quarterly/Annually |

---

## 7. Reports & Exports

### 7.1 Available Reports

1. **Payslip PDF** - Individual employee payslips
2. **Bank Schedule** - Payment file for bulk transfers
3. **Statutory Remittance Report** - Monthly obligations
4. **Annual Tax Summary** - Yearly PAYE summary (Form H1)
5. **Pension Schedule** - PFA contribution file
6. **Department Payroll Summary** - Breakdown by department
7. **Variance Report** - Month-over-month changes

### 7.2 Bank Schedule Format

```json
{
  "payroll_code": "PAY-2026-01-001",
  "payment_date": "2026-01-25",
  "total_amount": 15000000.00,
  "total_employees": 50,
  "items": [
    {
      "employee_id": "EMP001",
      "employee_name": "John Doe",
      "bank_name": "gtbank",
      "account_number": "0123456789",
      "account_name": "JOHN DOE",
      "amount": 300000.00,
      "narration": "Salary - January 2026 Payroll"
    }
  ]
}
```

---

## 8. Leave & Loan Management

### 8.1 Leave Types

| Type | Paid | Typical Days |
|------|------|--------------|
| Annual | Yes | 21 days |
| Sick | Yes | 12 days |
| Maternity | Yes | 12-16 weeks |
| Paternity | Yes | 10 days |
| Compassionate | Yes | 3-5 days |
| Study | Yes | Varies |
| Unpaid | No | As approved |

### 8.2 Leave Workflow

```
Employee Request → Pending → Approved/Rejected → Balance Updated
```

### 8.3 Loan Types

- Salary Advance
- Staff Loan
- Cooperative Loan
- Equipment Loan
- Educational Loan
- Emergency Loan

### 8.4 Loan Features

- Automatic payroll deduction
- Interest calculation
- Repayment tracking
- Balance management

---

## 9. Configuration Options

### 9.1 Entity-Level Settings (`PayrollSettings`)

```python
# Company Information
- company_name
- company_address
- company_logo_path

# Tax Settings
- tax_state            # Where PAYE is remitted
- tax_office
- employer_tin

# Pension Settings
- pfa_name             # Default PFA
- pension_employee_rate # Default 8%
- pension_employer_rate # Default 10%

# Other Statutory
- nhf_rate             # Default 2.5%
- nsitf_rate           # Default 1%
- itf_rate             # Default 1%
- itf_applicable       # Based on employee count

# Payment Settings
- default_payment_day  # e.g., 25th
- prorate_new_employees

# Workflow
- require_approval     # Payroll approval workflow
- auto_lock_after_days # Lock for audit

# Payslip
- payslip_template
- email_payslips       # Auto-send to employees
```

### 9.2 Supported Banks

All major Nigerian banks are supported:
- Access Bank, GTBank, Zenith Bank, UBA, First Bank
- Stanbic IBTC, Standard Chartered, FCMB, Fidelity
- Digital banks: Kuda, OPay, PalmPay, Moniepoint

### 9.3 Supported PFAs

All PenCom-licensed Pension Fund Administrators:
- AIICO Pension, ARM Pension, Leadway Pensure
- Stanbic IBTC Pension, Premium Pension, PAL Pensions
- And 13+ others

---

## Database Tables

| Table | Purpose |
|-------|---------|
| `employees` | Employee records |
| `employee_bank_accounts` | Bank details |
| `payroll_runs` | Pay period batches |
| `payslips` | Individual payslips |
| `payslip_items` | Line items |
| `statutory_remittances` | Tax/pension tracking |
| `employee_loans` | Loan records |
| `loan_repayments` | Repayment history |
| `employee_leaves` | Leave requests |
| `payroll_settings` | Entity configuration |

---

## Security Considerations

1. **Access Control**: Role-based permissions for payroll operations
2. **Audit Trail**: All changes are logged with user and timestamp
3. **Data Encryption**: Sensitive fields (BVN, TIN) are encrypted at rest
4. **Approval Workflow**: Multi-level approval for payroll processing
5. **Read-Only Mode**: Completed payrolls are locked for audit compliance

---

## Integration Points

1. **Accounting Module**: Journal entries for payroll expenses
2. **Tax Module**: PAYE calculations and returns
3. **Audit System**: Payroll audit trail and evidence
4. **Notification System**: Payslip emails and reminders
5. **Banking APIs**: Bulk payment processing (future)

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | Jan 2026 | Initial payroll system |
| 1.1.0 | Jan 2026 | 2026 Tax Reform updates |
| 1.2.0 | Jan 2026 | Leave & Loan management |

---

*Last Updated: January 7, 2026*
*Tekvwa Pro Audit - Nigeria's Premier Tax Compliance Platform*
