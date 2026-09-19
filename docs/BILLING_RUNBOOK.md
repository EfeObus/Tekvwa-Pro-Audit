# Tekvwa Pro Audit - Billing Incident Response Runbook

> **Document Version:** 1.0  
> **Effective Date:** January 24, 2026  
> **Owner:** Operations Team  
> **Classification:** Internal Operations

---

## Table of Contents

1. [Overview](#overview)
2. [Incident Classification](#incident-classification)
3. [Escalation Matrix](#escalation-matrix)
4. [Common Incidents](#common-incidents)
   - [Payment Failures](#payment-failures)
   - [Webhook Failures](#webhook-failures)
   - [Subscription Issues](#subscription-issues)
   - [Refund Processing](#refund-processing)
   - [Dunning/Collection Issues](#dunningcollection-issues)
5. [Recovery Procedures](#recovery-procedures)
6. [Monitoring & Alerts](#monitoring--alerts)
7. [Post-Incident Review](#post-incident-review)

---

## Overview

This runbook provides step-by-step procedures for responding to billing-related incidents in Tekvwa Pro Audit. The billing system uses **Paystack** as the payment provider and handles subscription management, payment processing, and usage metering.

### Key Components

| Component | Description | Location |
|-----------|-------------|----------|
| Billing API | REST endpoints for billing operations | `app/routers/billing.py` |
| Advanced Billing | Multi-currency, discounts, credits | `app/routers/advanced_billing.py` |
| Billing Service | Core billing business logic | `app/services/billing_service.py` |
| Dunning Service | Failed payment recovery | `app/services/dunning_service.py` |
| Metering Service | Usage tracking and limits | `app/services/metering_service.py` |
| Paystack Webhooks | Payment event processing | `POST /api/v1/billing/webhook/paystack` |

---

## Incident Classification

### Severity Levels

| Severity | Definition | Response Time | Examples |
|----------|------------|---------------|----------|
| **P1 - Critical** | Complete billing system outage | 15 minutes | Paystack integration down, all payments failing |
| **P2 - High** | Major degradation affecting many users | 1 hour | Webhook processing delayed, subscription activations failing |
| **P3 - Medium** | Limited impact, workaround available | 4 hours | Single customer payment issue, invoice generation error |
| **P4 - Low** | Minor issue, no immediate business impact | 24 hours | Reporting discrepancy, non-critical feature bug |

---

## Escalation Matrix

| Severity | First Responder | Escalation (30 min) | Final Escalation |
|----------|-----------------|---------------------|------------------|
| P1 | On-call Engineer | Engineering Lead + Product | CTO + CEO |
| P2 | On-call Engineer | Engineering Lead | Product Manager |
| P3 | Support Engineer | Engineering Team | Engineering Lead |
| P4 | Support Engineer | Engineering Team | - |

### Contact Information

| Role | Primary Contact | Backup |
|------|-----------------|--------|
| On-call Engineer | PagerDuty rotation | #engineering-oncall Slack |
| Engineering Lead | Direct page | Email + Slack |
| Product Manager | Slack DM | Email |
| Paystack Support | support@paystack.com | Dashboard chat |

---

## Common Incidents

### Payment Failures

#### Symptoms
- Customer unable to complete checkout
- Payment transaction stuck in "pending" status
- Error messages on checkout page

#### Diagnostic Steps

1. **Check Paystack Dashboard**
   ```
   https://dashboard.paystack.com/transactions
   ```
   - Look for the transaction by reference
   - Check if Paystack received the request
   - Review any error messages from Paystack

2. **Check Application Logs**
   ```bash
   # Search for payment errors
   grep -i "payment\|paystack\|billing" /var/log/tekvwa/app.log | tail -100
   
   # Check for specific transaction
   grep "TXN_REFERENCE" /var/log/tekvwa/app.log
   ```

3. **Verify Paystack API Status**
   - Check https://status.paystack.com
   - Test API connectivity:
   ```bash
   curl -X GET https://api.paystack.co/transaction/verify/test \
     -H "Authorization: Bearer $PAYSTACK_SECRET_KEY"
   ```

4. **Database Check**
   ```sql
   -- Check payment transaction status
   SELECT id, reference, status, gateway_response, created_at, updated_at
   FROM payment_transactions
   WHERE reference = 'TXN_REFERENCE'
   ORDER BY created_at DESC;
   
   -- Check for stuck pending transactions
   SELECT COUNT(*), status
   FROM payment_transactions
   WHERE created_at > NOW() - INTERVAL '1 hour'
   GROUP BY status;
   ```

#### Resolution Steps

**For declined cards:**
1. Inform customer to try a different payment method
2. Check if card type is supported (Verve, Mastercard, Visa)
3. Suggest bank transfer for large amounts

**For API errors:**
1. Check Paystack API key validity
2. Verify webhook secret is correct
3. Restart billing service if needed:
   ```bash
   sudo systemctl restart tekvwa-api
   ```

**For stuck transactions:**
1. Manually verify with Paystack:
   ```bash
   curl -X GET "https://api.paystack.co/transaction/verify/REFERENCE" \
     -H "Authorization: Bearer $PAYSTACK_SECRET_KEY"
   ```
2. Update transaction status in database if confirmed:
   ```sql
   UPDATE payment_transactions
   SET status = 'success', paid_at = NOW(), updated_at = NOW()
   WHERE reference = 'REFERENCE' AND status = 'pending';
   ```

---

### Webhook Failures

#### Symptoms
- Payments complete on Paystack but subscriptions not activated
- Customer charged but no invoice generated
- Webhook endpoint returning errors

#### Diagnostic Steps

1. **Check Webhook Logs**
   ```bash
   grep "webhook\|paystack" /var/log/tekvwa/app.log | tail -200
   ```

2. **Verify Webhook Configuration**
   - Go to Paystack Dashboard → Settings → API Keys & Webhooks
   - Confirm webhook URL: `https://api.proaudit.com/api/v1/billing/webhook/paystack`
   - Check webhook secret matches environment variable

3. **Test Webhook Endpoint**
   ```bash
   curl -X POST https://api.proaudit.com/api/v1/billing/webhook/paystack \
     -H "Content-Type: application/json" \
     -H "X-Paystack-Signature: test" \
     -d '{"event": "test"}'
   ```

4. **Check Failed Webhooks in Paystack**
   - Dashboard → Logs → Webhooks
   - Filter by failed status
   - Review error responses

#### Resolution Steps

**For signature validation failures:**
1. Verify `PAYSTACK_WEBHOOK_SECRET` in environment
2. Check for whitespace in secret value
3. Regenerate secret if compromised:
   ```bash
   # Update .env with new secret
   PAYSTACK_WEBHOOK_SECRET=new_secret_from_paystack
   
   # Restart service
   sudo systemctl restart tekvwa-api
   ```

**For processing errors:**
1. Check database connectivity
2. Review error in application logs
3. Manually process webhook if needed:
   ```python
   # In Django shell or script
   from app.services.billing_service import BillingService
   
   # Process specific transaction
   await service.process_successful_payment(
       reference="TXN_REFERENCE",
       paystack_data={"status": "success", ...}
   )
   ```

**For missed webhooks:**
1. Retrieve transaction from Paystack:
   ```bash
   curl -X GET "https://api.paystack.co/transaction/verify/REFERENCE" \
     -H "Authorization: Bearer $PAYSTACK_SECRET_KEY"
   ```
2. Manually update subscription status
3. Send confirmation email to customer

---

### Subscription Issues

#### Symptoms
- Customer cannot access features after payment
- Trial not converting to paid
- Subscription showing wrong tier

#### Diagnostic Steps

1. **Check TenantSKU Record**
   ```sql
   SELECT ts.*, o.name as org_name
   FROM tenant_skus ts
   JOIN organizations o ON o.id = ts.organization_id
   WHERE ts.organization_id = 'ORG_UUID';
   ```

2. **Review Payment History**
   ```sql
   SELECT * FROM payment_transactions
   WHERE organization_id = 'ORG_UUID'
   ORDER BY created_at DESC
   LIMIT 10;
   ```

3. **Check Subscription Events**
   ```bash
   grep "ORG_UUID\|subscription" /var/log/tekvwa/app.log | tail -50
   ```

#### Resolution Steps

**For activation failures:**
```sql
-- Manually activate subscription
UPDATE tenant_skus
SET 
    tier = 'professional',
    billing_cycle = 'monthly',
    current_period_start = CURRENT_DATE,
    current_period_end = CURRENT_DATE + INTERVAL '1 month',
    is_active = true,
    updated_at = NOW()
WHERE organization_id = 'ORG_UUID';
```

**For trial conversion:**
```sql
-- Convert trial to paid
UPDATE tenant_skus
SET 
    trial_ends_at = NULL,
    current_period_start = CURRENT_DATE,
    current_period_end = CURRENT_DATE + INTERVAL '1 month',
    updated_at = NOW()
WHERE organization_id = 'ORG_UUID';
```

---

### Refund Processing

#### Symptoms
- Customer requesting refund
- Partial refund needed for downgrade
- Chargeback notification

#### Diagnostic Steps

1. **Verify Original Transaction**
   ```sql
   SELECT * FROM payment_transactions
   WHERE id = 'PAYMENT_UUID' OR reference = 'REFERENCE';
   ```

2. **Check Refund Eligibility**
   - Payment must be within 30 days
   - No prior refund on transaction
   - Customer subscription active

#### Resolution Steps

**Process Refund via Paystack:**
```bash
# Full refund
curl -X POST "https://api.paystack.co/refund" \
  -H "Authorization: Bearer $PAYSTACK_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "transaction": "PAYSTACK_TXN_ID",
    "amount": 15000000
  }'

# Partial refund
curl -X POST "https://api.paystack.co/refund" \
  -H "Authorization: Bearer $PAYSTACK_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "transaction": "PAYSTACK_TXN_ID",
    "amount": 5000000
  }'
```

**Update Database:**
```sql
UPDATE payment_transactions
SET 
    status = 'refunded',
    refund_reference = 'REFUND_REF',
    refund_amount_kobo = 15000000,
    refunded_at = NOW(),
    updated_at = NOW()
WHERE id = 'PAYMENT_UUID';
```

**Adjust Subscription:**
```sql
-- Downgrade or cancel subscription
UPDATE tenant_skus
SET 
    tier = 'core',
    cancel_at_period_end = true,
    cancellation_reason = 'Customer requested refund',
    updated_at = NOW()
WHERE organization_id = 'ORG_UUID';
```

---

### Dunning/Collection Issues

#### Symptoms
- Recurring payment failed
- Customer in dunning process
- Subscription about to be suspended

#### Diagnostic Steps

1. **Check Dunning Status**
   ```sql
   SELECT * FROM dunning_records
   WHERE organization_id = 'ORG_UUID'
   ORDER BY created_at DESC;
   ```

2. **Review Failed Payment Attempts**
   ```sql
   SELECT * FROM payment_transactions
   WHERE organization_id = 'ORG_UUID'
   AND status = 'failed'
   ORDER BY created_at DESC;
   ```

#### Resolution Steps

**Retry Payment:**
```python
from app.services.dunning_service import DunningService

service = DunningService(db)
await service.retry_payment(organization_id)
```

**Manual Payment Link:**
```python
from app.services.billing_service import BillingService

service = BillingService(db)
intent = await service.create_payment_intent(
    organization_id=org_id,
    tier=current_tier,
    billing_cycle=current_cycle,
    admin_email=admin_email,
)
# Send intent.authorization_url to customer
```

**Grace Period Extension:**
```sql
UPDATE tenant_skus
SET 
    current_period_end = current_period_end + INTERVAL '7 days',
    updated_at = NOW()
WHERE organization_id = 'ORG_UUID';
```

---

## Recovery Procedures

### Full Billing System Recovery

If the entire billing system is down:

1. **Acknowledge Incident**
   - Create incident in #incidents Slack channel
   - Page on-call engineer

2. **Assess Scope**
   ```bash
   # Check service health
   curl https://api.proaudit.com/health
   
   # Check database connectivity
   psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT 1"
   
   # Check Redis
   redis-cli ping
   ```

3. **Failover Steps**
   ```bash
   # If primary database is down
   # Promote read replica
   aws rds promote-read-replica --db-instance-identifier tekvwa-replica
   
   # Update connection string
   export DATABASE_URL=postgresql://user:pass@replica:5432/tekvwa
   
   # Restart services
   sudo systemctl restart tekvwa-api
   sudo systemctl restart tekvwa-celery
   ```

4. **Enable Maintenance Mode** (if needed)
   ```bash
   # Toggle maintenance mode
   redis-cli SET maintenance_mode "true"
   redis-cli SET maintenance_message "Billing system maintenance in progress"
   ```

5. **Customer Communication**
   - Post status update to status.proaudit.com
   - Send email to affected customers
   - Update social media if prolonged

---

## Monitoring & Alerts

### Key Metrics to Monitor

| Metric | Warning Threshold | Critical Threshold |
|--------|-------------------|-------------------|
| Payment success rate | < 95% | < 90% |
| Webhook processing time | > 5s | > 15s |
| Failed webhook rate | > 5% | > 10% |
| Dunning conversion rate | < 50% | < 30% |
| API response time (billing) | > 500ms | > 2s |

### Alert Configuration

```yaml
# Prometheus alert rules
groups:
  - name: billing
    rules:
      - alert: PaymentSuccessRateLow
        expr: |
          sum(rate(payment_transactions_total{status="success"}[5m])) 
          / sum(rate(payment_transactions_total[5m])) < 0.9
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: Payment success rate below 90%
          
      - alert: WebhookProcessingDelayed
        expr: |
          histogram_quantile(0.95, rate(webhook_processing_seconds_bucket[5m])) > 15
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: Webhook processing time exceeds 15s
```

### Dashboard Links

- Grafana Billing Dashboard: `https://grafana.proaudit.com/d/billing`
- Paystack Dashboard: `https://dashboard.paystack.com`
- Application Logs: `https://logs.proaudit.com/billing`

---

## Post-Incident Review

### Required Documentation

After any P1 or P2 incident, complete the following:

1. **Incident Timeline**
   - When was the incident detected?
   - When was it acknowledged?
   - When was it resolved?

2. **Root Cause Analysis**
   - What caused the incident?
   - Why wasn't it caught earlier?
   - What systems were affected?

3. **Customer Impact**
   - How many customers affected?
   - Revenue impact estimate
   - Customer complaints received

4. **Action Items**
   - Immediate fixes applied
   - Long-term preventive measures
   - Monitoring improvements

### Template

```markdown
## Incident Report: [TITLE]

**Date:** YYYY-MM-DD
**Severity:** P1/P2/P3/P4
**Duration:** X hours Y minutes
**Impact:** Z customers affected, ₦X potential revenue impact

### Timeline
- HH:MM - Incident detected by [source]
- HH:MM - On-call engineer paged
- HH:MM - Root cause identified
- HH:MM - Fix deployed
- HH:MM - Monitoring confirms resolution

### Root Cause
[Description of root cause]

### Resolution
[Steps taken to resolve]

### Action Items
- [ ] [Action item 1] - Owner - Due date
- [ ] [Action item 2] - Owner - Due date

### Lessons Learned
[Key takeaways]
```

---

## Appendix

### Useful Commands

```bash
# View recent billing errors
journalctl -u tekvwa-api | grep -i "billing\|payment" | tail -50

# Check Celery task queue
celery -A app.celery_app inspect active

# Force retry failed webhooks
python -m app.scripts.retry_failed_webhooks --hours 24

# Generate billing reconciliation report
python -m app.scripts.billing_reconciliation --date 2026-01-24
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `PAYSTACK_SECRET_KEY` | Paystack API secret key |
| `PAYSTACK_PUBLIC_KEY` | Paystack public key for frontend |
| `PAYSTACK_WEBHOOK_SECRET` | Webhook signature validation |
| `PAYSTACK_SANDBOX_MODE` | True for test, False for production |
| `PAYSTACK_BASE_URL` | API base URL |
| `PAYSTACK_TIMEOUT_SECONDS` | API timeout |
| `PAYSTACK_MAX_RETRIES` | Max retry attempts |

---

*Last Updated: January 24, 2026*
