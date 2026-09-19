# TekVwarho ProAudit - World-Class Audit System Documentation

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Features](#features)
4. [API Endpoints](#api-endpoints)
5. [Frontend Pages](#frontend-pages)
6. [Integration Guide](#integration-guide)
7. [Configuration](#configuration)
8. [Compliance](#compliance)

---

## Overview

TekVwarho ProAudit implements a **world-class forensic audit system** designed for Nigerian tax compliance and beyond. The system provides enterprise-grade auditing capabilities including:

- **Benford's Law Analysis** - Statistical fraud detection using first/second digit distribution
- **Z-Score Anomaly Detection** - Identify statistical outliers in transaction data
- **NRS Gap Analysis** - FIRS National Revenue Service compliance checking
- **Hash Chain Immutable Ledger** - Blockchain-like transaction integrity
- **WORM Storage** - Write-Once-Read-Many document vault
- **3-Way Matching** - Purchase Order, Goods Receipt, Invoice reconciliation
- **Tax Explainability** - Detailed calculation breakdowns with legal references
- **Compliance Replay Engine** - Recalculate taxes using historical rules

---

## Architecture

### Backend Services

```
app/services/
├── forensic_audit_service.py    # Core forensic audit engine
│   ├── BenfordsLawAnalyzer      # Chi-square statistical analysis
│   ├── ZScoreAnomalyDetector    # Grouped anomaly detection  
│   ├── NRSGapAnalyzer           # FIRS compliance checking
│   ├── ForensicAuditService     # Main orchestrator
│   └── WORMStorageService       # S3 Object Lock integration
├── audit_service.py             # Audit logging and history
├── immutable_ledger.py          # SHA-256 hash chain
└── three_way_matching.py        # PO-GRN-Invoice matching
```

### API Routers

```
app/routers/
├── forensic_audit.py            # /api/v1/entities/{id}/forensic-audit/*
├── audit.py                     # /api/v1/entities/{id}/audit/*
└── advanced_audit.py            # /api/v1/entities/{id}/advanced-audit/*
```

### Frontend Templates

```
templates/
├── audit_dashboard.html         # Main audit dashboard
├── audit_logs.html              # Audit log viewer
├── advanced_audit.html          # Enterprise audit tools
└── worm_storage.html            # WORM vault management
```

### Data Models

```
app/models/
├── audit.py                     # AuditLog model
│   └── AuditLog                 # NTAA 2025 compliant audit trail
└── advanced_accounting.py       # LedgerEntry for hash chain
```

---

## Features

### 1. Benford's Law Analysis

Detects potential fraud by analyzing the distribution of leading digits in transaction amounts.

**How It Works:**
- Natural data follows Benford's distribution (30.1% start with 1, 17.6% with 2, etc.)
- Fraudulent data often deviates from this pattern
- Uses chi-square test to quantify deviation

**Risk Levels:**
- `conforming` - Normal distribution (chi² < 15.51)
- `non_conforming` - Suspicious deviation (chi² ≥ 15.51)
- `critically_non_conforming` - High fraud risk (chi² ≥ 23.21)

**API Endpoint:**
```
POST /api/v1/entities/{entity_id}/forensic-audit/benfords-law
```

**Sample Response:**
```json
{
  "first_digit": {
    "chi_square_statistic": 12.34,
    "p_value": 0.18,
    "conformity_level": "conforming"
  },
  "flagged_transactions": [...],
  "recommendation": "Distribution appears normal..."
}
```

---

### 2. Z-Score Anomaly Detection

Identifies transactions that are statistically unusual compared to their category.

**How It Works:**
- Groups transactions by type
- Calculates mean and standard deviation for each group
- Flags transactions with |z-score| > 3 as anomalies

**Severity Levels:**
- `high` - Z-score > 5 (extreme outlier)
- `medium` - Z-score 4-5 (significant outlier)
- `low` - Z-score 3-4 (minor outlier)

**API Endpoint:**
```
POST /api/v1/entities/{entity_id}/forensic-audit/z-score
```

**Parameters:**
- `group_by` - Field to group transactions (default: "transaction_type")
- `threshold` - Z-score threshold (default: 3)
- `transaction_type` - Filter by transaction type

---

### 3. NRS Gap Analysis

Checks compliance with Nigeria's National Revenue Service (FIRS) requirements.

**Checks Performed:**
- Invoice Reference Number (IRN) validation
- Date format compliance
- Amount accuracy
- Signatory verification
- NRS e-Invoice registration

**Compliance Levels:**
- `compliant` - All checks passed
- `partial` - Some issues found
- `non_compliant` - Critical issues

**API Endpoint:**
```
POST /api/v1/entities/{entity_id}/forensic-audit/nrs-gap-analysis
```

---

### 4. Hash Chain Integrity

Provides blockchain-like immutability for financial records.

**How It Works:**
- Each transaction gets a SHA-256 hash
- Hash includes previous transaction's hash
- Creates unbreakable chain of custody

**Verification:**
```
POST /api/v1/entities/{entity_id}/forensic-audit/integrity/verify
```

**Detailed Verification:**
```
GET /api/v1/entities/{entity_id}/forensic-audit/integrity/verify-detailed
```

---

### 5. WORM Storage (Audit Vault)

Write-Once-Read-Many storage for legally protected documents.

**Features:**
- AWS S3 Object Lock integration
- 7-year default retention
- Immutable document storage
- Hash verification

**Supported Documents:**
- Tax Filings
- NRS-Validated Invoices
- Financial Statements
- Audit Reports
- Bank Statements

**API Endpoints:**
```
GET  /api/v1/entities/{id}/forensic-audit/worm-storage/status
POST /api/v1/entities/{id}/forensic-audit/worm-storage/archive/{doc_type}/{doc_id}
POST /api/v1/entities/{id}/forensic-audit/worm-storage/verify/{doc_type}/{doc_id}
```

---

### 6. Three-Way Matching

Reconciles Purchase Orders, Goods Receipts, and Invoices.

**Match Types:**
- `perfect_match` - All documents align
- `partial_match` - Minor discrepancies
- `no_match` - Major discrepancies

**Tolerances:**
- Quantity: 0.5%
- Price: 1%

**API Endpoint:**
```
POST /api/v1/entities/{entity_id}/forensic-audit/three-way-match
```

---

### 7. Full Forensic Audit

Runs all analyses in a single comprehensive audit.

**API Endpoint:**
```
POST /api/v1/entities/{entity_id}/forensic-audit/full
```

**Response Includes:**
- Benford's Law analysis
- Z-Score anomalies
- NRS compliance status
- Hash chain integrity
- Three-way matching results
- Overall risk assessment
- Recommendations

---

## API Endpoints

### Forensic Audit Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/forensic-audit/overview` | Dashboard overview stats |
| POST | `/forensic-audit/benfords-law` | Run Benford's Law analysis |
| POST | `/forensic-audit/z-score` | Run Z-Score anomaly detection |
| POST | `/forensic-audit/nrs-gap-analysis` | Run NRS compliance check |
| POST | `/forensic-audit/three-way-match` | Run 3-way matching |
| POST | `/forensic-audit/full` | Run full forensic audit |
| POST | `/forensic-audit/integrity/verify` | Verify hash chain |
| GET | `/forensic-audit/integrity/verify-detailed` | Detailed integrity report |
| GET | `/forensic-audit/worm-storage/status` | WORM storage status |
| POST | `/forensic-audit/worm-storage/archive/{type}/{id}` | Archive document |
| POST | `/forensic-audit/worm-storage/verify/{type}/{id}` | Verify document |

### Audit Log Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/audit/logs` | List audit logs with filters |
| GET | `/audit/logs/{log_id}` | Get specific log entry |
| GET | `/audit/history/{resource_type}/{resource_id}` | Entity history |
| GET | `/audit/user-activity/{user_id}` | User activity report |
| GET | `/audit/summary` | Audit summary statistics |
| GET | `/audit/export` | Export audit logs |

### Advanced Audit Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/advanced-audit/explainability/paye` | PAYE calculation breakdown |
| POST | `/advanced-audit/explainability/vat` | VAT calculation breakdown |
| POST | `/advanced-audit/replay/calculate` | Compliance replay |
| POST | `/advanced-audit/replay/compare` | Compare two dates |
| POST | `/advanced-audit/attestation/register` | Register attestor |
| POST | `/advanced-audit/attestation/workflow` | Create workflow |
| GET | `/advanced-audit/attestation/workflows` | List workflows |
| POST | `/advanced-audit/behavioral/analyze` | Behavioral analysis |

---

## Frontend Pages

### Audit Dashboard (`/audit`)
Main dashboard with:
- Quick stats (Integrity, NRS Compliance, Anomalies, 3-Way Match)
- Benford's Law analysis card
- Z-Score anomaly detection card
- NRS Gap Analysis card
- Hash Chain verification card
- Full Forensic Audit runner
- Results modal

### Audit Logs (`/audit-logs`)
Log viewer with:
- Filterable table (action, entity type, dates, search)
- Pagination
- Details modal with full log entry

### Advanced Audit (`/advanced-audit`)
Enterprise tools:
- Tax Explainability Layer (PAYE, VAT, WHT, CIT)
- Compliance Replay Engine
- Regulatory Confidence Scoring
- Third-Party Attestation
- Behavioral Analytics
- Audit-Ready Export

### WORM Storage (`/worm-storage`)
Vault management:
- Storage status and configuration
- Document verification
- Legal protection information
- Supported document types

---

## Integration Guide

### JavaScript API Client

```javascript
// Fetch audit overview
const overview = await fetch(`/api/v1/entities/${entityId}/forensic-audit/overview`, {
    headers: { 'Authorization': `Bearer ${token}` }
}).then(r => r.json());

// Run Benford's Law analysis
const benfords = await fetch(`/api/v1/entities/${entityId}/forensic-audit/benfords-law`, {
    method: 'POST',
    headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({
        start_date: '2026-01-01',
        end_date: '2026-12-31',
        transaction_type: 'sale'
    })
}).then(r => r.json());

// Verify hash chain
const integrity = await fetch(`/api/v1/entities/${entityId}/forensic-audit/integrity/verify`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` }
}).then(r => r.json());
```

### Python Client

```python
import httpx

async with httpx.AsyncClient() as client:
    # Run full forensic audit
    response = await client.post(
        f"http://localhost:8000/api/v1/entities/{entity_id}/forensic-audit/full",
        headers={"Authorization": f"Bearer {token}"},
        json={"start_date": "2026-01-01", "end_date": "2026-12-31"}
    )
    audit_result = response.json()
```

---

## Configuration

### Environment Variables

```bash
# WORM Storage (AWS S3)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
WORM_BUCKET_NAME=proaudit-worm-vault

# Audit Settings
AUDIT_LOG_RETENTION_DAYS=2555  # 7 years
HASH_ALGORITHM=sha256
```

### Database Configuration

The audit system uses PostgreSQL with the following key tables:

- `audit_logs` - Audit trail with NTAA 2025 fields
- `ledger_entries` - Hash chain entries
- `transactions` - Source data for analysis

---

## Compliance

### Nigerian Regulations

- **NTAA 2025** - Nigeria Tax Administration Act 2025
- **FIRS e-Invoice** - Federal Inland Revenue Service electronic invoicing
- **NRS** - National Revenue Service regulations
- **Tax Reform 2026** - Latest Nigerian tax reform requirements

### Retention Requirements

| Document Type | Retention Period |
|--------------|------------------|
| Tax Filings | 7 years |
| Financial Statements | 7 years |
| Invoices | 6 years |
| Audit Reports | 7 years |
| Bank Statements | 6 years |

### International Standards

- **SAF-T** - Standard Audit File for Tax
- **ICAN** - Institute of Chartered Accountants of Nigeria
- **ISO 27001** - Information security management

---

## Security

### Data Protection

- All sensitive data encrypted at rest
- TLS 1.3 for data in transit
- Hash chain prevents tampering
- WORM storage prevents deletion

### Access Control

- Role-Based Access Control (RBAC)
- JWT token authentication
- Audit logging of all access
- Entity-level isolation

### Audit Trail

Every action is logged with:
- User ID and IP address
- Timestamp (UTC)
- Action type
- Resource affected
- Old and new values
- Entity context

---

## Troubleshooting

### Common Issues

1. **Hash chain verification fails**
   - Check for missing ledger entries
   - Verify database integrity
   - Review detailed verification report

2. **WORM storage not configured**
   - Set AWS credentials in environment
   - Ensure S3 bucket has Object Lock enabled
   - Check IAM permissions

3. **Benford's Law shows non-conforming**
   - Review flagged transactions manually
   - Check for legitimate business patterns
   - Consider industry-specific variations

### Support

For technical support, contact:
- Email: info@tekvwa.org
- Documentation: /docs/AUDIT_SYSTEM_DOCUMENTATION.md

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-01-06 | Initial release with full forensic audit |
| 1.0.1 | 2026-01-06 | Added WORM storage integration |
| 1.0.2 | 2026-01-06 | Added advanced audit features |

---
