# Tekvwa Pro Audit - Service Level Agreement (SLA)

**Effective Date:** January 1, 2026  
**Last Updated:** January 3, 2026  
**Version:** 1.0  
**Applies To:** All Paid Subscription Plans  

---

## 1. Overview

This Service Level Agreement ("SLA") defines the service commitments Tekvwa IT Solutions LTD provides to subscribers of Tekvwa Pro Audit. This SLA is incorporated into and forms part of your subscription agreement.

---

## 2. Definitions

| Term | Definition |
|------|------------|
| **Availability** | The percentage of time the Service is operational |
| **Downtime** | Period when the Service is unavailable |
| **Scheduled Maintenance** | Planned maintenance communicated in advance |
| **Incident** | Any event causing service degradation |
| **Resolution Time** | Time from incident report to resolution |
| **Response Time** | Time from support request to first response |
| **Service Credit** | Compensation for SLA breaches |

---

## 3. Service Availability

### 3.1 Availability Commitment

| Plan | Availability Target | Monthly Downtime Allowance |
|------|--------------------|-----------------------------|
| **Starter** | 99.0% | 7 hours 18 minutes |
| **Professional** | 99.5% | 3 hours 39 minutes |
| **Business** | 99.9% | 43 minutes |
| **Enterprise** | 99.9% | 43 minutes |

### 3.2 Availability Calculation

```
Availability % = ((Total Minutes - Downtime Minutes) / Total Minutes) × 100

Monthly Total Minutes = 43,200 (30 days)
```

### 3.3 Excluded from Downtime Calculation

The following are NOT counted as downtime:

- Scheduled maintenance (with 48-hour notice)
- Emergency maintenance (critical security patches)
- Third-party service outages (NRS, banks, cloud providers)
- Issues caused by user actions or configurations
- Force majeure events
- Connectivity issues on user's network

---

## 4. Scheduled Maintenance

### 4.1 Maintenance Windows

| Type | Preferred Window | Notice Required |
|------|------------------|-----------------|
| **Regular Maintenance** | Sundays 00:00-06:00 WAT | 48 hours |
| **Major Updates** | Saturdays 22:00-Sunday 06:00 WAT | 7 days |
| **Emergency Patches** | As needed | Best effort |

### 4.2 Maintenance Notifications

You will be notified via:
- Email to account owner
- In-app banner announcement
- Status page update (status.proaudit.com)

---

## 5. Support Response Times

### 5.1 Support Tiers

| Priority | Description | Examples |
|----------|-------------|----------|
| **Critical (P1)** | Service completely unavailable | Login fails, e-invoices not submitting |
| **High (P2)** | Major feature impaired | Reports not generating, OCR failing |
| **Medium (P3)** | Feature partially impaired | Slow performance, minor bugs |
| **Low (P4)** | General questions, enhancements | How-to questions, feature requests |

### 5.2 Response Time Commitments

| Priority | Starter | Professional | Business | Enterprise |
|----------|---------|--------------|----------|------------|
| **Critical** | 24 hours | 4 hours | 1 hour | 15 minutes |
| **High** | 48 hours | 8 hours | 4 hours | 1 hour |
| **Medium** | 5 days | 3 days | 1 day | 8 hours |
| **Low** | 10 days | 5 days | 3 days | 1 day |

### 5.3 Resolution Time Targets

| Priority | Target Resolution Time |
|----------|------------------------|
| **Critical** | 4 hours (Business/Enterprise) |
| **High** | 24 hours |
| **Medium** | 3-5 business days |
| **Low** | Best effort |

---

## 6. Support Channels

### 6.1 Available Channels by Plan

| Channel | Starter | Professional | Business | Enterprise |
|---------|---------|--------------|----------|------------|
| **Help Center/Docs** | | | | |
| **Email Support** | | | | |
| **Live Chat** |  | | | |
| **Phone Support** |  |  | | |
| **Dedicated Manager** |  |  |  | |
| **WhatsApp Business** |  |  | | |

### 6.2 Support Hours

| Plan | Hours | Days |
|------|-------|------|
| **Starter** | 9:00-17:00 WAT | Mon-Fri |
| **Professional** | 8:00-20:00 WAT | Mon-Sat |
| **Business** | 24/7 | All days |
| **Enterprise** | 24/7 | All days |

---

## 7. Performance Standards

### 7.1 Page Load Times

| Page Type | Target | Maximum |
|-----------|--------|---------|
| **Dashboard** | < 2 seconds | 5 seconds |
| **Transaction List** | < 3 seconds | 7 seconds |
| **Report Generation** | < 5 seconds | 15 seconds |
| **PDF Download** | < 3 seconds | 10 seconds |

### 7.2 API Response Times

| Endpoint Type | Target | Maximum |
|---------------|--------|---------|
| **Read Operations** | < 200ms | 1 second |
| **Write Operations** | < 500ms | 2 seconds |
| **Report Generation** | < 5 seconds | 30 seconds |
| **E-Invoice Submission** | < 3 seconds | 10 seconds* |

*Excludes NRS processing time

---

## 8. Service Credits

### 8.1 Credit Calculation

If we fail to meet availability commitments:

| Availability | Credit (% of Monthly Fee) |
|--------------|---------------------------|
| 99.0% - 99.5% | 10% |
| 95.0% - 99.0% | 25% |
| 90.0% - 95.0% | 50% |
| < 90.0% | 100% |

### 8.2 Credit Limits

- Maximum credit: 100% of one month's subscription fee
- Credits are applied to future invoices (not cash refunds)
- Credits expire after 12 months if unused

### 8.3 Credit Request Process

1. Submit request within 30 days of incident
2. Include date, time, and description of outage
3. We will verify against our monitoring data
4. Credit applied within 45 days if approved

**Request Email:** info@tekvwa.org

### 8.4 Exclusions from Credits

Credits are NOT provided for:

- Issues caused by user actions
- Third-party service failures
- Scheduled maintenance
- Beta/preview features
- Free tier accounts

---

## 9. Data Protection

### 9.1 Backup Schedule

| Data Type | Backup Frequency | Retention |
|-----------|------------------|-----------|
| **User Data** | Every 6 hours | 30 days |
| **Transactions** | Real-time replication | 30 days |
| **Documents** | Daily | 30 days |
| **Audit Logs** | Real-time | 6 years |

### 9.2 Recovery Time Objectives

| Scenario | RTO | RPO |
|----------|-----|-----|
| **Minor Outage** | 1 hour | 0 (no data loss) |
| **Major Outage** | 4 hours | 6 hours |
| **Disaster Recovery** | 24 hours | 24 hours |

---

## 10. Security Standards

### 10.1 Security Commitments

| Measure | Standard |
|---------|----------|
| **Encryption at Rest** | AES-256 |
| **Encryption in Transit** | TLS 1.3 |
| **Authentication** | MFA available |
| **Penetration Testing** | Annual by third party |
| **Vulnerability Scanning** | Weekly |
| **Security Patches** | Critical within 24 hours |

### 10.2 Incident Response

| Severity | Response Time | Notification |
|----------|---------------|--------------|
| **Critical (Data Breach)** | Immediate | Within 72 hours (NDPA) |
| **High** | 4 hours | Within 24 hours |
| **Medium** | 24 hours | Within 72 hours |
| **Low** | Best effort | In monthly report |

---

## 11. Escalation Procedure

### 11.1 Escalation Path

| Level | Contact | Timeframe |
|-------|---------|-----------|
| **Level 1** | Support Team | Initial contact |
| **Level 2** | Support Manager | After 24 hours |
| **Level 3** | Technical Director | After 48 hours |
| **Level 4** | Executive Team | After 72 hours |

### 11.2 Enterprise Escalation

Enterprise customers have direct access to:
- Named Account Manager
- Technical Account Manager
- Executive Sponsor

---

## 12. Reporting

### 12.1 Status Page

Real-time service status: **status.proaudit.com**

Includes:
- Current system status
- Incident history
- Scheduled maintenance
- Historical uptime

### 12.2 Monthly Reports (Business/Enterprise)

Monthly reports include:
- Availability metrics
- Incident summary
- Response time statistics
- Recommendations

---

## 13. Third-Party Dependencies

### 13.1 External Services

| Service | Provider | Our Responsibility |
|---------|----------|-------------------|
| **NRS E-Invoicing** | Nigeria Revenue Service | API integration |
| **TIN Verification** | NRS/FIRS | Pass-through queries |
| **Bank APIs** | Various banks | Integration maintenance |
| **Cloud Infrastructure** | AWS/Azure | Provider selection |

### 13.2 Third-Party SLA Pass-Through

We do not control third-party uptime. If a third-party outage causes Tekvwa outage:
- We will communicate transparently
- We will work with the provider for resolution
- Service credits may apply at our discretion

---

## 14. Changes to This SLA

We may update this SLA with:
- 30 days' notice for material changes
- Immediate effect for improvements
- Grandfathering for reduced commitments during current term

---

## 15. Contact Information

**Technical Support:** info@tekvwa.org  
**SLA Inquiries:** info@tekvwa.org  
**Status Page:** status.proaudit.com  
**Emergency (Enterprise):** +234 90 6577 9323  

---

**© 2026 Tekvwa IT Solutions LTD. All Rights Reserved.**
