# TekVwarho ProAudit - Security & Integration Architecture

## NDPA/NITDA Compliance Implementation

This document details the security features implemented to comply with Nigeria Data Protection Act (2023/2026) and NITDA guidelines.

---

## 1. Data Privacy & Sovereignty

### 1.1 PII Field-Level Encryption (AES-256-GCM)

All Personally Identifiable Information (PII) is encrypted at the field level using AES-256-GCM:

```python
from app.utils.ndpa_security import get_encryption_engine, PIICategory

engine = get_encryption_engine()

# Encrypt BVN
encrypted_bvn = engine.encrypt("22123456789", PIICategory.BVN)
# Result: "bvn:base64_iv:base64_ciphertext:base64_tag"

# Decrypt
plaintext, category = engine.decrypt(encrypted_bvn)
```

**Protected Fields:**
| Category | Fields | Encryption |
|----------|--------|------------|
| High Sensitivity | BVN, NIN, Passport, RSA PIN, Bank Account | AES-256-GCM |
| Medium Sensitivity | TIN, Phone, Email, DOB, Address | AES-256-GCM |
| Low Sensitivity | Full Name, Employee ID | Masking only |

### 1.2 PII Masking for Display

Even authorized users see masked values in the UI:

```python
from app.utils.ndpa_security import PIIMasker

PIIMasker.mask_bvn("22123456789")  # "22*******89"
PIIMasker.mask_phone("08031234567")  # "0803***4567"
PIIMasker.mask_email("john@company.com")  # "j***@company.com"
PIIMasker.mask_account("0123456789")  # "****6789"
```

### 1.3 Local Data Residency

All data is routed through Nigerian IP ranges. The geo-fencing middleware validates:

```python
NIGERIAN_IP_RANGES = [
    "41.58.0.0/15",      # MTN Nigeria
    "41.73.128.0/17",    # Airtel Nigeria
    "41.138.160.0/19",   # Glo Nigeria
    "41.184.0.0/15",     # 9mobile
    "41.203.64.0/18",    # MainOne
    "41.216.160.0/19",   # Rack Centre
    # ... plus AFRINIC general ranges
]
```

### 1.4 Right-to-Erasure Workflow

NDPA-compliant data deletion with statutory retention:

```python
from app.utils.ndpa_security import erasure_service

request = await erasure_service.create_request(
    user_id="user-123",
    email="user@example.com",
    delete_personal_data=True,
)

# Process with statutory retention
await erasure_service.process_request(request, db_session)
```

**What Gets Deleted vs Retained:**
| Data Category | Deletable | Reason |
|---------------|-----------|--------|
| Personal Profile | Yes Yes | User consent |
| Contact Info | Yes Yes | User consent |
| Bank Accounts | Yes Yes | User consent |
| Tax Records (6 years) | No No | NRS Statutory |
| VAT Returns | No No | FIRS Requirement |
| Audit Logs | No No | Compliance |

---

## 2. Network & Infrastructure Security

### 2.1 Geo-Fencing Middleware

```python
# In app/middleware/security.py
class GeoFencingMiddleware:
    """
    Block non-Nigerian IPs by default.
    Allow authorized diaspora users.
    """
    
    async def dispatch(self, request, call_next):
        client_ip = self.geo_service.get_client_ip(request)
        allowed, reason, risk_score = await self.geo_service.check_access(ip=client_ip)
        
        if not allowed:
            return JSONResponse(status_code=403, content={
                "error": "Access restricted to Nigerian IP addresses"
            })
```

### 2.2 Rate Limiting

Per-endpoint rate limits with DDoS protection:

| Endpoint | Limit | Window |
|----------|-------|--------|
| `/api/v1/auth/login` | 5 requests | 60 seconds |
| `/api/v1/auth/register` | 3 requests | 60 seconds |
| `/api/v1/tax-calculators` | 30 requests | 60 seconds |
| `/api/v1/nrs/*` | 10 requests | 60 seconds |
| General API | 100 requests | 60 seconds |

**Development Mode:** Limits are multiplied by 10x for testing.

---

## 3. CSRF Protection

### 3.1 Double-Submit Cookie Pattern

```javascript
// In templates/base.html
document.addEventListener('htmx:configRequest', function(event) {
    event.detail.headers['X-CSRF-Token'] = getCsrfToken();
});
```

```html
<body hx-headers='{"X-CSRF-Token": "{{ csrf_token }}"}'>
```

### 3.2 SameSite=Strict Cookies

```python
response.set_cookie(
    key="csrf_token",
    value=token,
    httponly=False,  # JS needs to read it
    samesite="strict",
    secure=not development_mode,
    max_age=86400,
)
```

---

## 4. XSS Protection

### 4.1 Content Security Policy

```
Content-Security-Policy: 
    default-src 'self'; 
    script-src 'self' https://unpkg.com; 
    style-src 'self' 'unsafe-inline'; 
    img-src 'self' data: https:; 
    connect-src 'self' https://nrs.gov.ng https://api.nrs.gov.ng https://nibss-plc.com.ng;
    frame-ancestors 'none';
    form-action 'self';
```

### 4.2 Security Headers

All responses include:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Strict-Transport-Security: max-age=31536000` (production)
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=(self)`

---

## 5. SQL Injection & IDOR Protection

### 5.1 ORM Enforcement

All queries use SQLAlchemy 2.0 ORM with parameterized queries:

```python
# CORRECT - Parameterized
result = await db.execute(
    select(Invoice)
    .where(Invoice.id == invoice_id)
    .where(Invoice.entity_id == current_entity_id)  # IDOR protection
)

# NEVER - String interpolation
# query = f"SELECT * FROM invoices WHERE id = {invoice_id}"
```

### 5.2 Entity-Based Access Control

Every service method requires `entity_id`:

```python
class TransactionService:
    async def get_transaction(
        self,
        transaction_id: UUID,
        entity_id: UUID,  # MANDATORY
    ) -> Transaction:
        return await db.execute(
            select(Transaction)
            .where(Transaction.id == transaction_id)
            .where(Transaction.entity_id == entity_id)
        )
```

### 5.3 UUIDs Over Integers

All public-facing IDs use UUID:

```python
class Transaction(Base):
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,  # UUIDv4 - unguessable
    )
```

---

## 6. Brute Force Protection

### 6.1 Account Lockout

```python
from app.utils.ndpa_security import AccountLockoutManager

# Check lockout
is_locked, seconds = AccountLockoutManager.is_locked_out(email)

# Record failed attempt
remaining, lockout = AccountLockoutManager.record_failed_attempt(email)

# Clear on success
AccountLockoutManager.clear_attempts(email)
```

**Lockout Schedule:**
| Attempt # | Lockout Duration |
|-----------|------------------|
| 5 | 1 minute |
| 10 | 5 minutes |
| 15 | 15 minutes |
| 20 | 1 hour |
| 25+ | 24 hours |

### 6.2 Email Alerts

On lockout, an email is sent to the user warning of potential unauthorized access.

---

## 7. Advanced Accounting Integration

### 7.1 How Advanced Features Connect to Initial System

The advanced accounting module builds on top of the initial accounting system:

```
┌─────────────────────────────────────────────────────────────────┐
│                    INITIAL ACCOUNTING SYSTEM                     │
├─────────────────────────────────────────────────────────────────┤
│  Transaction Service  │  Invoice Service  │  Vendor Service     │
│  Customer Service     │  Category Service │  Tax Service        │
│  Inventory Service    │  Report Service   │  Dashboard Service  │
└───────────┬───────────┴────────┬──────────┴────────┬────────────┘
            │                    │                    │
            ▼                    ▼                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ADVANCED ACCOUNTING MODULE                    │
├─────────────────────────────────────────────────────────────────┤
│  AI Labelling         │  3-Way Matching    │  WHT Vault         │
│  Tax Intelligence     │  Approval Workflow │  Immutable Ledger  │
│  Entity Consolidation │  Dimensional Acct  │  Audit Reports     │
└─────────────────────────────────────────────────────────────────┘
            │                    │                    │
            ▼                    ▼                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                 BUSINESS INTELLIGENCE MODULE                     │
├─────────────────────────────────────────────────────────────────┤
│  BIK Automator        │  NIBSS Pension     │  Growth Radar      │
│  Inventory Write-off  │  Multi-Location    │  Tax Threshold     │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 Data Flow Integration

**Transactions → AI Labelling:**
```python
# TransactionService creates transaction
transaction = await transaction_service.create_transaction(...)

# AILabellingService categorizes it
prediction = await ai_service.predict_category(
    description=transaction.description,
    amount=transaction.amount,
    vendor_name=transaction.vendor.name if transaction.vendor else None,
)
transaction.category_id = prediction.category_id
```

**Invoices → 3-Way Matching:**
```python
# InvoiceService creates invoice
invoice = await invoice_service.create_invoice(...)

# ThreeWayMatchingService matches to PO/GRN
match_result = await matching_service.match_invoice(
    invoice_id=invoice.id,
    po_id=related_po.id,
    grn_id=related_grn.id,
)
```

**Vendors → WHT Credit Vault:**
```python
# VendorService tracks payments
payment = await vendor_service.record_payment(...)

# WHTCreditNoteService tracks withholding
if payment.wht_amount > 0:
    credit_note = await wht_service.receive_credit_note(
        issuer_tin=vendor.tin,
        wht_amount=payment.wht_amount,
    )
```

### 7.3 Shared Database Models

The advanced accounting module uses relationships to existing models:

```python
class ThreeWayMatch(Base):
    invoice_id = Column(UUID, ForeignKey("invoices.id"))  # Existing
    po_id = Column(UUID, ForeignKey("purchase_orders.id"))
    grn_id = Column(UUID, ForeignKey("goods_received_notes.id"))
    
    invoice = relationship("Invoice", back_populates="matches")

class WHTCreditNote(Base):
    vendor_id = Column(UUID, ForeignKey("vendors.id"))  # Existing
    vendor = relationship("Vendor", back_populates="wht_credit_notes")

class ApprovalRequest(Base):
    transaction_id = Column(UUID, ForeignKey("transactions.id"))  # Existing
    transaction = relationship("Transaction")
```

### 7.4 Service Dependencies

```python
# Advanced services use initial services
class TaxIntelligenceService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.transaction_service = TransactionService(db)
        self.invoice_service = InvoiceService(db)
        self.payroll_service = PayrollService(db)
    
    async def calculate_etr(self, entity_id: UUID, period: date):
        # Uses transaction_service for income/expenses
        income = await self.transaction_service.get_total_income(entity_id, period)
        expenses = await self.transaction_service.get_total_expenses(entity_id, period)
        
        # Uses payroll_service for PAYE calculations
        paye = await self.payroll_service.get_paye_liability(entity_id, period)
```

---

## 8. Frontend-Backend Route Mapping

### 8.1 HTML Page Routes (views.py)

| Frontend URL | Template | Backend API |
|--------------|----------|-------------|
| `/` | `index.html` | - |
| `/login` | `login.html` | `POST /api/v1/auth/login` |
| `/register` | `register.html` | `POST /api/v1/auth/register` |
| `/dashboard` | `dashboard.html` | `GET /api/v1/auth/dashboard` |
| `/transactions` | `transactions.html` | `GET /api/v1/entities/{id}/transactions` |
| `/invoices` | `invoices.html` | `GET /api/v1/entities/{id}/invoices` |
| `/vendors` | `vendors.html` | `GET /api/v1/entities/{id}/vendors` |
| `/customers` | `customers.html` | `GET /api/v1/entities/{id}/customers` |
| `/inventory` | `inventory.html` | `GET /api/v1/entities/{id}/inventory` |
| `/tax-2026` | `tax_2026.html` | `GET /api/v1/tax-2026/*` |
| `/reports` | `reports.html` | `GET /api/v1/entities/{id}/reports/*` |
| `/settings` | `settings.html` | `PATCH /api/v1/auth/me` |

### 8.2 API Endpoint Categories

| Category | Prefix | Routes |
|----------|--------|--------|
| Authentication | `/api/v1/auth` | 20+ |
| Entities | `/api/v1/entities` | 10+ |
| Transactions | `/api/v1/entities/{id}/transactions` | 15+ |
| Invoices | `/api/v1/entities/{id}/invoices` | 20+ |
| Tax 2026 | `/api/v1/tax-2026` | 25+ |
| Advanced Accounting | `/api/v1/advanced` | 50+ |
| Business Intelligence | `/api/v1/business-intelligence` | 15+ |
| Payroll | `/api/v1/payroll` | 30+ |

---

## 9. Testing

### 9.1 Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html

# Run specific test file
pytest tests/test_auth_service.py -v
```

### 9.2 Security Tests

```bash
# Test rate limiting
pytest tests/test_security.py::test_rate_limiting -v

# Test geo-fencing
pytest tests/test_security.py::test_geo_fencing -v

# Test CSRF protection
pytest tests/test_security.py::test_csrf_protection -v
```

---

## 10. Super Admin Security Controls (Platform Management)

The Super Admin Dashboard provides platform-level security controls for TekVwarho staff. All actions are logged to the global audit log.

### 10.1 Emergency Controls (Kill Switches)

Platform-wide emergency controls for incident response:

```python
# Emergency platform read-only mode
POST /admin/emergency/platform/read-only
{
    "enabled": true,
    "reason": "Security incident investigation"
}

# Emergency tenant suspension
POST /admin/emergency/tenant/{tenant_id}/suspend
{
    "reason": "Fraudulent activity detected",
    "notify_admin": true
}

# Feature kill switch
POST /admin/emergency/feature/{feature_name}/disable
{
    "reason": "Vulnerability discovered in NRS integration"
}
```

### 10.2 Platform Staff Authentication

```python
# Staff roles with hierarchical permissions
PLATFORM_STAFF_ROLES = {
    "Super Admin": ["*"],  # Full platform access
    "IT Developer": ["health.read", "audit.read", "tenants.read"],
    "CSR": ["users.search", "users.read", "tenants.read"],
    "Support Manager": ["users.*", "verifications.*", "tenants.read"]
}

# JWT claims for platform staff
{
    "sub": "staff_uuid",
    "is_platform_staff": true,
    "platform_role": "Super Admin",
    "permissions": ["*"]
}
```

### 10.3 Global Audit Log

All Super Admin actions are logged with full details:

```python
# Audit log entry structure
{
    "id": "uuid",
    "actor_id": "staff_uuid",
    "actor_email": "info@tekvwa.org",
    "action": "emergency.tenant.suspend",
    "target_type": "organization",
    "target_id": "tenant_uuid",
    "details": {"reason": "...", "notify_admin": true},
    "ip_address": "41.58.x.x",
    "user_agent": "...",
    "timestamp": "2026-01-27T12:00:00Z"
}
```

### 10.4 Implemented Admin Endpoints

| Category | Endpoints | Status |
|----------|-----------|--------|
| Emergency Controls | 6 | ✅ Implemented |
| User Search | 4 | ✅ Implemented |
| Staff Management | 4 | ✅ Implemented |
| Verification | 4 | ✅ Implemented |
| Audit Logs | 4 | ✅ Implemented |
| Health Metrics | 6 | ✅ Implemented |
| Tenant Management | 3 | ✅ Implemented |
| **Total** | **31** | **100% Passing** |

---

## 11. Environment Configuration

Add to `.env`:

```bash
# PII Encryption Key (generate with: openssl rand -base64 32)
PII_ENCRYPTION_KEY=your-base64-encoded-32-byte-key

# Security Settings
GEO_FENCING_ENABLED=true
RATE_LIMITING_ENABLED=true
CSRF_ENABLED=true

# Development Mode (relaxes security for testing)
APP_ENV=development
```

---

## Summary

TekVwarho ProAudit implements world-class security features:

| Feature | Implementation | Compliance |
|---------|----------------|------------|
| PII Encryption | AES-256-GCM | NDPA 2023 |
| Data Masking | Field-level | NDPA 2023 |
| Geo-Fencing | Nigerian IPs | NITDA |
| Rate Limiting | Per-endpoint | Best Practice |
| CSRF Protection | Double-submit | OWASP |
| XSS Protection | CSP Headers | OWASP |
| SQL Injection | ORM + Parameterized | OWASP |
| IDOR Protection | Entity-based access | OWASP |
| Brute Force | Account lockout | Best Practice |
| Right-to-Erasure | Statutory retention | NDPA 2023 |
| Super Admin Controls | Emergency kill switches | Platform Security |
| Global Audit Logging | All admin actions logged | Compliance |
| Platform Health Monitoring | Real-time metrics | Operational |

---

*Last Updated: January 27, 2026*
