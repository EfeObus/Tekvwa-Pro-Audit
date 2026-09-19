# TekVwarho ProAudit - Data Retention Policy

> **Document Version:** 1.0  
> **Effective Date:** January 24, 2026  
> **Classification:** Internal Operations  
> **Compliance:** NDPR, FIRS, FRCN

---

## Overview

This document describes the data retention policy for TekVwarho ProAudit billing and usage data. The policy ensures compliance with Nigerian data protection regulations (NDPR), tax authority requirements (FIRS), and accounting standards (FRCN) while managing database storage efficiently.

---

## Retention Periods

| Data Type | Retention Period | Reason | Action After Retention |
|-----------|------------------|--------|------------------------|
| `usage_records` | 2 years (730 days) | Billing disputes, usage analysis | Hard delete |
| `usage_events` | 90 days | Operational monitoring | Hard delete |
| `feature_access_logs` | 1 year (365 days) | Security audit, access analysis | Hard delete |
| `payment_transactions` | 7 years (2555 days) | FIRS tax compliance, FRCN | Archive (soft delete) |
| `audit_logs` | Tier-dependent (90 days - 7 years) | Compliance, SKU tier feature | Per tier configuration |

---

## Data Types

### Usage Records (`usage_records`)

**Description:** Monthly billing period summaries per organization, including transaction counts, user counts, API calls, and storage usage.

**Retention:** 2 years (730 days)

**Justification:**
- Sufficient for billing dispute resolution (typically within 1 year)
- Enables year-over-year usage trend analysis
- Complies with general commercial record-keeping

**Cleanup:**
- Records older than `period_end + 730 days` are deleted
- Deletion is batched (1000 records at a time) to avoid database lock contention
- Runs daily at 3 AM during off-peak hours

### Usage Events (`usage_events`)

**Description:** Granular, real-time usage events recording individual API calls, transactions, and feature accesses.

**Retention:** 90 days

**Justification:**
- High volume data (potentially millions of records per month)
- Primarily used for real-time metering and debugging
- Aggregated into `usage_records` before deletion

**Cleanup:**
- Events older than 90 days are permanently deleted
- Larger batch size (5000 records) due to higher volume

### Feature Access Logs (`feature_access_logs`)

**Description:** Records of feature access attempts, including granted and denied access based on SKU tier.

**Retention:** 1 year (365 days)

**Justification:**
- Security audit requirements
- Feature adoption analytics
- Access pattern analysis for product development

**Cleanup:**
- Logs older than 365 days are permanently deleted

### Payment Transactions (`payment_transactions`)

**Description:** Complete payment records including Paystack references, amounts, card details (masked), and transaction metadata.

**Retention:** 7 years (2555 days)

**Justification:**
- **FIRS Requirement:** Nigerian tax law requires retention of financial records for 6 years
- **FRCN Standards:** Accounting records must be kept for 6 years minimum
- **Additional buffer:** 7 years provides safety margin for audits

**Cleanup:**
- Records are **archived** (soft delete), not permanently deleted
- Archived records set `is_archived=true` and `archived_at` timestamp
- Archived records can be retrieved for audits if needed
- Physical deletion requires explicit data destruction request

---

## Configuration

### Environment Variables

```bash
# Data retention periods (days)
USAGE_RECORDS_RETENTION_DAYS=730
USAGE_EVENTS_RETENTION_DAYS=90
PAYMENT_TRANSACTIONS_RETENTION_DAYS=2555
FEATURE_ACCESS_LOGS_RETENTION_DAYS=365

# Enable/disable automatic cleanup
ENABLE_DATA_RETENTION_CLEANUP=True
```

### Disabling Cleanup

To disable automatic cleanup (e.g., for investigation purposes):

```bash
ENABLE_DATA_RETENTION_CLEANUP=False
```

**Warning:** Disabling cleanup will cause unbounded database growth.

---

## Cleanup Task

### Schedule

The cleanup task (`cleanup_expired_usage_data`) runs daily at 3:00 AM (configurable via Celery beat schedule).

### Celery Configuration

```python
# In celery_app.py or scheduled_tasks.py
app.conf.beat_schedule = {
    'cleanup-expired-usage-data': {
        'task': 'app.tasks.scheduled_tasks.cleanup_expired_usage_data',
        'schedule': crontab(hour=3, minute=0),  # 3 AM daily
    },
}
```

### Manual Execution

To run cleanup manually:

```bash
# Via management command
python -m app.scripts.run_cleanup

# Or in Python shell
from app.tasks.scheduled_tasks import cleanup_expired_usage_data
from app.database import async_session_factory

async with async_session_factory() as db:
    result = await cleanup_expired_usage_data(db)
    print(result)
```

---

## Monitoring

### Metrics

Monitor the following metrics to ensure cleanup is working:

| Metric | Alert Threshold | Description |
|--------|-----------------|-------------|
| `usage_records_count` | > 5M records | Total records in table |
| `usage_events_count` | > 50M records | Total events in table |
| `cleanup_duration_seconds` | > 300s | Cleanup task duration |
| `cleanup_errors` | > 0 | Any errors during cleanup |

### Alerts

Set up alerts for:

1. **Cleanup task failures** - Task not completing successfully
2. **Table size growth** - Tables growing despite cleanup (indicates misconfiguration)
3. **Long-running cleanup** - Performance degradation

### Grafana Dashboard Query Examples

```sql
-- Usage records age distribution
SELECT 
    DATE_TRUNC('month', period_end) as month,
    COUNT(*) as record_count
FROM usage_records
GROUP BY month
ORDER BY month DESC
LIMIT 24;

-- Estimate cleanup impact
SELECT 
    COUNT(*) as records_to_delete,
    pg_size_pretty(SUM(pg_column_size(t.*))) as space_to_reclaim
FROM usage_records t
WHERE period_end < CURRENT_DATE - INTERVAL '730 days';
```

---

## Compliance Notes

### NDPR (Nigeria Data Protection Regulation)

- Personal data should not be kept longer than necessary
- This policy aligns with data minimization principles
- Usage data is aggregate and does not contain PII
- Payment data is retained for legal compliance

### FIRS (Federal Inland Revenue Service)

- Financial records must be retained for 6 years
- Payment transactions are archived for 7 years
- All archived records remain available for tax audits

### FRCN (Financial Reporting Council of Nigeria)

- Companies must retain accounting records for 6 years minimum
- This policy exceeds minimum requirements with 7-year payment retention

---

## Data Destruction

### Request Process

To permanently destroy archived data:

1. Submit formal request to Compliance team
2. Provide justification and legal approval
3. Ensure no pending audits or legal holds
4. Execute destruction with dual authorization
5. Document destruction in audit log

### Destruction Script

```sql
-- WARNING: This permanently deletes data
-- Requires DBA and Compliance approval

-- Delete archived payment transactions older than 10 years
DELETE FROM payment_transactions
WHERE is_archived = true
AND archived_at < CURRENT_DATE - INTERVAL '10 years';

-- Log destruction
INSERT INTO data_destruction_log (
    table_name, 
    records_deleted, 
    reason, 
    authorized_by, 
    executed_at
) VALUES (
    'payment_transactions',
    (SELECT changes()),
    'Data destruction request #XXX',
    'info@tekvwa.org',
    NOW()
);
```

---

## Changelog

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-24 | System | Initial policy |

---

*This document is subject to annual review and updates as regulations change.*
