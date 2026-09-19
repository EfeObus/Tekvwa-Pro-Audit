# Super Admin Dashboard Documentation

## Overview

The Super Admin Dashboard is the comprehensive command center for platform administrators of TekVwarho ProAudit. It provides full visibility and control over the multi-tenant SaaS accounting and audit platform, featuring a distinctive Nigerian flag-inspired green-white-green color scheme.

---

## Table of Contents

1. [Design Philosophy](#design-philosophy)
2. [Technical Architecture](#technical-architecture)
3. [Dashboard Sections](#dashboard-sections)
4. [Color Scheme & Branding](#color-scheme--branding)
5. [Navigation Structure](#navigation-structure)
6. [Data Sources & API Endpoints](#data-sources--api-endpoints)
7. [Feature Flags & SKU Tiers](#feature-flags--sku-tiers)
8. [Security Considerations](#security-considerations)
9. [File Structure](#file-structure)
10. [Future Enhancements](#future-enhancements)

---

## Design Philosophy

The Super Admin Dashboard follows these core principles:

### 1. **Nigerian Pride Theme**
- Primary color: Nigerian Green (`#008751`)
- Clean white backgrounds for readability
- Green accents throughout the interface
- Professional yet distinctly Nigerian aesthetic

### 2. **Information Hierarchy**
- Most critical metrics visible immediately (KPIs at top)
- Drill-down capability for detailed analysis
- Contextual actions near relevant data
- Clear visual separation between sections

### 3. **Actionable Insights**
- Every metric leads to actionable items
- Quick action buttons for common tasks
- Alert badges for items requiring attention
- Status indicators for system health

### 4. **Modern SaaS Standards**
- Responsive design (mobile to desktop)
- Dark mode ready infrastructure
- Real-time data updates via HTMX
- Alpine.js for reactive state management

---

## Technical Architecture

### Frontend Stack

| Technology | Purpose |
|------------|---------|
| **Tailwind CSS** | Utility-first CSS framework via CDN |
| **Alpine.js** | Lightweight reactivity for UI state |
| **HTMX** | Dynamic content loading without full page reloads |
| **Jinja2** | Server-side templating |

### Backend Integration

| Component | File | Purpose |
|-----------|------|---------|
| Route | `app/routers/views.py` | Dashboard routing logic |
| Service | `app/services/dashboard_service.py` | Data aggregation |
| Template | `templates/super_admin_dashboard.html` | Main layout |
| Partials | `templates/partials/super_admin/*.html` | Section components |

### Data Flow

```
User Request → views.py → DashboardService → Database
                    ↓
              Jinja2 Template → HTML Response
                    ↓
              Alpine.js State Management
                    ↓
              HTMX Partial Updates
```

---

## Dashboard Sections

### 1. Executive Overview (`overview.html`)
**Purpose**: High-level platform health and KPIs at a glance

**Key Metrics**:
- Total Tenants (Organizations)
- Monthly Recurring Revenue (MRR)
- Annual Recurring Revenue (ARR)
- Average Revenue Per User (ARPU)
- Churn Rate (monthly)
- System Health Score

**Quick Actions**:
- Add New Tenant
- View All Tenants
- Generate Reports
- System Settings

---

### 2. Tenant Management (`tenants.html`)
**Purpose**: Complete visibility and control over all tenants

**Features**:
- Tenant search and filtering
- Tenant statistics cards
- Detailed tenant table with:
  - Organization name
  - Subscription tier (Core/Professional/Enterprise)
  - Status (Active/Trial/Grace/Suspended)
  - MRR contribution
  - User count
  - Last activity
- Quick actions: View, Edit, Impersonate, Suspend

**Filters**:
- By subscription tier
- By status
- By date range
- By revenue range

---

### 3. Subscription & Billing (`subscriptions.html`)
**Purpose**: Revenue tracking and billing management

**Metrics**:
- Active Subscriptions
- MRR by tier
- Pending payments
- Failed payments (24h)

**Tier Breakdown**:
| Tier | Price/Month | Features |
|------|-------------|----------|
| Core | ₦15,000 | Basic accounting, 3 users |
| Professional | ₦50,000 | Full features, 10 users |
| Enterprise | ₦150,000 | Unlimited, priority support |
| Intelligence Add-on | ₦25,000 | ML/AI features |

**Payment Providers**:
- Paystack integration status
- NRS (NASME Reporting Standards) compliance

---

### 4. Feature Flags Panel (`feature_flags.html`)
**Purpose**: SKU-based feature gating management

**Feature Categories**:

#### Core Tier Features
- Basic Accounting
- Invoice Management
- Basic Reports
- Customer Management
- Vendor Management

#### Professional Tier Features
- Advanced Accounting
- Bank Reconciliation
- Payroll Processing
- Fixed Asset Management
- Multi-entity Support

#### Enterprise Tier Features
- White-labeling
- Custom Integrations
- API Access
- Priority Support
- Dedicated Account Manager

#### Intelligence Add-on
- Benford's Law Analysis
- Anomaly Detection
- Predictive Analytics
- Risk Scoring
- Journal Entry Clustering

**Per-Tenant Overrides**: Ability to enable/disable specific features for individual tenants regardless of their subscription tier.

---

### 5. Audit Logs (`audit_logs.html`)
**Purpose**: Platform-wide audit trail

**Logged Events**:
- User authentication (login/logout/failed)
- Data modifications (CRUD operations)
- Configuration changes
- Subscription changes
- Feature flag changes
- Security events

**Features**:
- Real-time log streaming
- Advanced filtering
- Export capabilities
- Retention policy display
- Immutability guarantee

---

### 6. Compliance Section (`compliance.html`)
**Purpose**: Nigerian regulatory compliance tracking

**Compliance Frameworks**:

| Framework | Description |
|-----------|-------------|
| **FIRS** | Federal Inland Revenue Service tax compliance |
| **NRS** | NASME Reporting Standards for invoicing |
| **CAMA** | Companies and Allied Matters Act compliance |

**Metrics**:
- Compliance rate by framework
- Upcoming deadlines
- Outstanding filings
- Alert notifications

---

### 7. Legal Holds (`legal_holds.html`)
**Purpose**: Legal and regulatory data retention management

**Features**:
- Active legal holds list
- Affected data categories
- Hold duration tracking
- Export restrictions
- Audit trail of hold actions

**Legal Hold Types**:
- Litigation holds
- Regulatory investigation holds
- Audit preservation holds
- Tax investigation holds

---

### 8. ML Jobs (`ml_jobs.html`)
**Purpose**: Machine learning pipeline management

**Job Types**:
- Anomaly Detection Training
- Risk Score Calculation
- Benford's Law Analysis
- Journal Entry Clustering
- Trend Forecasting

**Metrics**:
- Active jobs count
- Queue depth
- Worker pool status
- Success/failure rates

---

### 9. ML Models (`models.html`)
**Purpose**: ML model lifecycle management

**Model Cards**:
Each model displays:
- Model name and version
- Last training date
- Performance metrics (precision, recall, F1)
- Status (Active/Training/Deprecated)
- Retraining schedule

**Available Models**:
1. Anomaly Detection Model
2. Risk Scoring Model
3. Benford's Law Analyzer
4. Journal Entry Clusterer

---

### 10. Risk Signals (`risk_signals.html`)
**Purpose**: Platform-wide risk monitoring

**Signal Categories**:
- Financial anomalies
- Unusual user behavior
- Compliance deviations
- System security alerts

**Severity Levels**:
- 🔴 Critical: Immediate action required
- 🟠 High: Action within 24 hours
- 🟡 Medium: Review within week
- 🟢 Low: Monitor

---

### 11. Revenue Analytics (`revenue.html`)
**Purpose**: Financial health of the platform

**Key Metrics**:
- ARR (Annual Recurring Revenue)
- MRR (Monthly Recurring Revenue)
- NRR (Net Revenue Retention)
- LTV (Lifetime Value)
- CAC (Customer Acquisition Cost)

**Revenue Breakdown**:
- By subscription tier
- By geography (Nigerian states)
- By industry vertical
- By acquisition channel

**MRR Movement**:
- New business
- Expansion (upgrades)
- Contraction (downgrades)
- Churn (cancellations)

---

### 12. Upsell Opportunities (`upsell.html`)
**Purpose**: Revenue growth opportunity identification

**Upgrade Pipelines**:
1. Core → Professional candidates
2. Professional → Enterprise candidates
3. Intelligence add-on candidates

**Signals for Upsell**:
- High feature utilization
- Approaching user limits
- Transaction volume growth
- Support ticket patterns

---

### 13. Infrastructure (`infrastructure.html`)
**Purpose**: Platform health monitoring

**Monitored Services**:
- API Gateway
- Database (PostgreSQL)
- Redis Cache
- Celery Workers
- Email Service
- File Storage
- NRS Gateway
- Paystack Integration

**Resource Monitoring**:
- CPU utilization
- Memory usage
- Disk space
- Network I/O
- Database connections

**Queue Status**:
- Default queue
- ML jobs queue
- Email queue
- Reports queue
- Backup queue

---

### 14. Support Queue (`support.html`)
**Purpose**: Customer support management

**Ticket Prioritization**:
| Priority | SLA Response Time |
|----------|-------------------|
| Critical | 1 hour |
| High | 4 hours |
| Medium | 24 hours |
| Low | 48 hours |

**Ticket Categories**:
- Billing issues
- Technical problems
- Feature requests
- Account management
- Compliance questions

**Metrics**:
- Open tickets
- Average response time
- Resolution rate
- Customer satisfaction (CSAT)

---

### 15. Staff Management (`staff_management.html`)
**Purpose**: Platform team administration

**Platform Roles**:
| Role | Permissions |
|------|-------------|
| Super Admin | Full platform access |
| Platform Admin | Tenant + feature management |
| Support Lead | Support + limited admin |
| Support Agent | Support queue only |
| Finance Admin | Billing + revenue access |

**Features**:
- Staff directory
- Role assignment
- Permission matrix
- Activity tracking
- Session management

---

### 16. Security Dashboard (`security.html`)
**Purpose**: Platform security monitoring

**Security Metrics**:
- Security score (A+ to F)
- Failed login attempts
- Active sessions
- 2FA adoption rate

**Security Features**:
- IP blocklist management
- Session monitoring
- Security alerts
- Compliance checklist
- Vulnerability status

---

### 17. Global Settings (`settings.html`)
**Purpose**: Platform-wide configuration

**Configurable Options**:
- Platform name and branding
- Default currency (NGN)
- Default timezone (WAT)
- Trial period duration
- Grace period duration
- Pricing tiers
- Feature toggles
- Backup configuration
- Maintenance mode

---

## Color Scheme & Branding

### CSS Custom Properties

```css
:root {
    /* Nigerian Flag Green */
    --ng-green: #008751;
    --ng-green-dark: #006741;
    --ng-green-light: #00a865;
    --ng-green-pale: #e6f5ef;
    
    /* White */
    --ng-white: #ffffff;
    
    /* Supporting Colors */
    --gray-50: #f9fafb;
    --gray-100: #f3f4f6;
    --gray-200: #e5e7eb;
    --gray-500: #6b7280;
    --gray-700: #374151;
    --gray-900: #111827;
}
```

### Component Styling

```css
/* Primary Button */
.btn-primary {
    background: linear-gradient(135deg, var(--ng-green) 0%, var(--ng-green-dark) 100%);
    color: white;
    border: none;
    box-shadow: 0 2px 4px rgba(0, 135, 81, 0.3);
}

/* Metric Card */
.metric-card {
    background: white;
    border-radius: 16px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

/* Highlighted Card (Green Gradient) */
.metric-card.highlight {
    background: linear-gradient(135deg, var(--ng-green) 0%, var(--ng-green-dark) 100%);
    color: white;
}
```

---

## Navigation Structure

### Sidebar Navigation (17 Sections)

```
📊 Overview          (Executive dashboard)
👥 Tenants           (Tenant management)
💳 Subscriptions     (Billing & payments)
🚀 Features          (Feature flags)
📋 Audit Logs        (Platform audit trail)
✅ Compliance        (Regulatory compliance)
⚖️ Legal Holds       (Data preservation)
🤖 ML Jobs           (Machine learning pipeline)
📈 Models            (ML model management)
⚠️ Risk Signals      (Risk monitoring)
💰 Revenue           (Revenue analytics)
📈 Upsell            (Growth opportunities)
🖥️ Infrastructure    (System health)
🎫 Support           (Support queue)
👔 Staff             (Team management)
🔐 Security          (Security monitoring)
⚙️ Settings          (Global configuration)
```

### Alpine.js State Management

```javascript
function superAdminDashboard() {
    return {
        activeSection: 'overview',
        sidebarOpen: true,
        
        setSection(section) {
            this.activeSection = section;
            // Optionally update URL hash
            window.location.hash = section;
        },
        
        init() {
            // Load section from URL hash
            const hash = window.location.hash.slice(1);
            if (hash) this.activeSection = hash;
        }
    }
}
```

---

## Data Sources & API Endpoints

### Dashboard Data API

**Endpoint**: `GET /api/v1/dashboard`

**Response Structure**:
```json
{
    "dashboard_type": "super_admin",
    "user": {
        "id": "uuid",
        "email": "info@tekvwa.org",
        "role": "SUPER_ADMIN"
    },
    "overview": {
        "total_organizations": 42,
        "total_users": 1250,
        "total_staff": 12,
        "pending_verifications": 3
    },
    "financial_metrics": {
        "mrr": 3250000,
        "arr": 39000000,
        "arpu": 77380,
        "churn_rate": 2.1
    },
    "platform_health": {
        "api": {"status": "healthy", "uptime": "99.97%"},
        "database": {"status": "healthy", "connections": 45},
        "workers": {"status": "healthy", "active": 4}
    },
    "quick_actions": [
        {"label": "Add Tenant", "url": "/admin/tenants/new", "icon": "building"},
        {"label": "View Reports", "url": "/reports", "icon": "chart-bar"}
    ],
    "recent_activity": [
        {"action": "login", "user": "admin@tenant1.com", "timestamp": "2025-01-25T10:30:00Z"}
    ]
}
```

### Supplementary Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v1/admin/tenants` | List all tenants |
| `GET /api/v1/admin/subscriptions` | Subscription data |
| `GET /api/v1/admin/audit-logs` | Audit log entries |
| `GET /api/v1/admin/ml/jobs` | ML job status |
| `GET /api/v1/admin/revenue/metrics` | Revenue analytics |
| `GET /api/v1/admin/support/tickets` | Support queue |
| `GET /api/v1/admin/security/alerts` | Security events |

---

## Feature Flags & SKU Tiers

### Tier Feature Matrix

| Feature | Core | Professional | Enterprise |
|---------|:----:|:------------:|:----------:|
| Basic Accounting | ✅ | ✅ | ✅ |
| Invoice Management | ✅ | ✅ | ✅ |
| Customer/Vendor | ✅ | ✅ | ✅ |
| Basic Reports | ✅ | ✅ | ✅ |
| User Limit | 3 | 10 | Unlimited |
| Bank Reconciliation | ❌ | ✅ | ✅ |
| Payroll | ❌ | ✅ | ✅ |
| Fixed Assets | ❌ | ✅ | ✅ |
| Multi-Entity | ❌ | ✅ | ✅ |
| Advanced Reports | ❌ | ✅ | ✅ |
| API Access | ❌ | ❌ | ✅ |
| White-labeling | ❌ | ❌ | ✅ |
| Custom Integrations | ❌ | ❌ | ✅ |
| Priority Support | ❌ | ❌ | ✅ |
| Dedicated AM | ❌ | ❌ | ✅ |

### Intelligence Add-on Features

Available with any tier for additional ₦25,000/month:

| Feature | Description |
|---------|-------------|
| Anomaly Detection | ML-powered unusual transaction detection |
| Benford's Law | Statistical analysis for fraud detection |
| Risk Scoring | Automated risk assessment |
| Predictive Analytics | Cash flow forecasting |
| Journal Clustering | Pattern recognition in entries |

---

## Security Considerations

### Access Control

1. **Authentication**: Required for all dashboard access
2. **Authorization**: Super Admin platform role required
3. **Session Management**: Secure session with timeout
4. **Audit Trail**: All actions logged

### Data Protection

1. **Encryption**: TLS 1.3 in transit, AES-256 at rest
2. **Input Validation**: All user inputs sanitized
3. **CSRF Protection**: Token-based protection
4. **Rate Limiting**: API request limits enforced

### Sensitive Operations

Operations requiring additional confirmation:
- Tenant suspension
- Feature flag changes
- Staff permission changes
- Bulk data operations
- System setting modifications

---

## File Structure

```
templates/
├── super_admin_dashboard.html          # Main dashboard layout
└── partials/
    └── super_admin/
        ├── overview.html               # Executive overview
        ├── tenants.html                # Tenant management
        ├── subscriptions.html          # Billing & subscriptions
        ├── feature_flags.html          # Feature flags panel
        ├── audit_logs.html             # Audit log viewer
        ├── compliance.html             # Compliance tracking
        ├── legal_holds.html            # Legal holds management
        ├── ml_jobs.html                # ML pipeline jobs
        ├── models.html                 # ML model management
        ├── risk_signals.html           # Risk monitoring
        ├── revenue.html                # Revenue analytics
        ├── upsell.html                 # Upsell opportunities
        ├── infrastructure.html         # Infrastructure health
        ├── support.html                # Support queue
        ├── staff_management.html       # Staff administration
        ├── security.html               # Security dashboard
        └── settings.html               # Global settings

app/
├── routers/
│   └── views.py                        # Dashboard routing (line 178-220)
└── services/
    └── dashboard_service.py            # Dashboard data service
```

---

## Future Enhancements

### Planned Features

1. **Real-time Notifications**
   - WebSocket integration for live updates
   - Browser push notifications
   - In-app notification center

2. **Advanced Analytics**
   - Cohort analysis
   - Customer lifetime value modeling
   - Churn prediction

3. **Automation Rules**
   - Auto-suspend on payment failure
   - Auto-upgrade on usage threshold
   - Scheduled report generation

4. **Enhanced Security**
   - Hardware key support (FIDO2)
   - Biometric authentication
   - Geo-fencing

5. **Customization**
   - Dashboard widget arrangement
   - Custom report builder
   - Saved filter presets

### API Expansion

Future API endpoints:
- `POST /api/v1/admin/tenants/{id}/suspend`
- `POST /api/v1/admin/tenants/{id}/impersonate`
- `POST /api/v1/admin/features/{id}/toggle`
- `GET /api/v1/admin/analytics/cohorts`
- `GET /api/v1/admin/predictions/churn`

---

## Changelog

### Version 1.0.0 (January 25, 2025)

- ✅ Initial Super Admin Dashboard release
- ✅ Nigerian flag green-white-green theme
- ✅ 17 comprehensive sections
- ✅ Tailwind CSS styling (fixed Bootstrap mismatch)
- ✅ Alpine.js state management
- ✅ Responsive design
- ✅ Full documentation

### Bug Fixes

- Fixed `AttributeError: 'AuditLog' object has no attribute 'resource_type'` in `dashboard_service.py`
- Fixed CSS framework mismatch (Bootstrap classes with Tailwind CSS base)

---

## Support

For issues or questions regarding the Super Admin Dashboard:

- **Technical Issues**: Create a GitHub issue
- **Feature Requests**: Submit via internal ticket system
- **Documentation Updates**: PR to this document

---

*Documentation last updated: January 25, 2025*
*TekVwarho ProAudit - Building Nigeria's Financial Future* 🇳🇬
