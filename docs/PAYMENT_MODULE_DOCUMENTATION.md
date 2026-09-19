# Tekvwa Pro Audit - Payment Module Documentation

## Overview

The Tekvwa Pro Audit payment module provides a complete billing and subscription management system using **Paystack** as the payment provider. The system is optimized for Nigerian Naira (NGN) transactions and supports multiple payment methods including cards, bank transfers, and USSD.

## Table of Contents

1. [Architecture](#architecture)
2. [Configuration](#configuration)
3. [Payment Flow](#payment-flow)
4. [API Endpoints](#api-endpoints)
5. [Database Models](#database-models)
6. [Security](#security)
7. [Pricing Tiers](#pricing-tiers)
8. [Webhook Handling](#webhook-handling)
9. [Error Handling](#error-handling)
10. [Testing](#testing)
11. [Production Deployment](#production-deployment)

---

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        PAYMENT MODULE ARCHITECTURE                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                           API LAYER                                   │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐ │   │
│  │  │                    app/routers/billing.py                        │ │   │
│  │  │  • GET  /api/v1/billing/pricing                                  │ │   │
│  │  │  • GET  /api/v1/billing/subscription                             │ │   │
│  │  │  • POST /api/v1/billing/checkout                                 │ │   │
│  │  │  • GET  /api/v1/billing/payments                                 │ │   │
│  │  │  • GET  /api/v1/billing/payments/{id}                            │ │   │
│  │  │  • POST /api/v1/billing/webhook/paystack                         │ │   │
│  │  └─────────────────────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│                                    ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         SERVICE LAYER                                 │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐ │   │
│  │  │               app/services/billing_service.py                    │ │   │
│  │  │  ┌─────────────────────┐  ┌───────────────────────────────────┐ │ │   │
│  │  │  │  BillingService     │  │  PaystackProvider                 │ │ │   │
│  │  │  │  • Pricing logic    │  │  • initialize_payment()           │ │ │   │
│  │  │  │  • Payment intents  │  │  • verify_payment()               │ │ │   │
│  │  │  │  • Webhook handling │  │  • create_subscription()          │ │ │   │
│  │  │  │  • SKU upgrades     │  │  • cancel_subscription()          │ │ │   │
│  │  │  └─────────────────────┘  │  • refund_payment()               │ │ │   │
│  │  │                           │  • list_transactions()            │ │ │   │
│  │  │                           └───────────────────────────────────┘ │ │   │
│  │  └─────────────────────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│                                    ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                          DATA LAYER                                   │   │
│  │  ┌───────────────────────┐  ┌─────────────────────────────────────┐  │   │
│  │  │   PaymentTransaction  │  │         TenantSKU                   │  │   │
│  │  │   (payment_transactions)│  │        (tenant_skus)               │  │   │
│  │  │   • reference         │  │   • organization_id                 │  │   │
│  │  │   • status            │  │   • tier (CORE/PRO/ENTERPRISE)      │  │   │
│  │  │   • amount_kobo       │  │   • billing_cycle                   │  │   │
│  │  │   • paystack_response │  │   • is_active                       │  │   │
│  │  └───────────────────────┘  └─────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│                                    ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                      EXTERNAL SERVICES                                │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐ │   │
│  │  │                     Paystack API                                 │ │   │
│  │  │                 https://api.paystack.co                          │ │   │
│  │  │  • POST /transaction/initialize                                  │ │   │
│  │  │  • GET  /transaction/verify/:reference                           │ │   │
│  │  │  • POST /subscription                                            │ │   │
│  │  │  • POST /subscription/disable                                    │ │   │
│  │  │  • POST /refund                                                  │ │   │
│  │  └─────────────────────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### File Structure

```
app/
├── config.py                      # Paystack configuration settings
├── routers/
│   └── billing.py                 # REST API endpoints
├── services/
│   └── billing_service.py         # Business logic & Paystack integration
├── models/
│   └── sku.py                     # PaymentTransaction, TenantSKU models
└── config/
    └── sku_config.py              # Pricing tiers configuration

alembic/versions/
└── 20260122_1920_add_payment_transactions.py  # Database migration

tests/
└── test_paystack_provider.py      # Payment module tests
```

---

## Configuration

### Environment Variables

Add these to your `.env` file:

```bash
# Paystack API Keys
# Get these from https://dashboard.paystack.com/#/settings/developer
PAYSTACK_SECRET_KEY=sk_test_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
PAYSTACK_PUBLIC_KEY=pk_test_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Webhook Secret (for signature verification)
# Generate a random string or get from Paystack dashboard
PAYSTACK_WEBHOOK_SECRET=whsec_your_webhook_secret_here

# API Base URL (optional, defaults to production)
PAYSTACK_BASE_URL=https://api.paystack.co
```

### Configuration Properties

The configuration is loaded in `app/config.py`:

```python
# Paystack settings
paystack_secret_key: str = ""        # Required for API calls
paystack_public_key: str = ""        # For frontend checkout
paystack_webhook_secret: str = ""    # For webhook verification
paystack_base_url: str = "https://api.paystack.co"

@property
def paystack_headers(self) -> Dict[str, str]:
    """Get headers for Paystack API requests."""
    return {
        "Authorization": f"Bearer {self.paystack_secret_key}",
        "Content-Type": "application/json",
    }

@property
def paystack_is_live(self) -> bool:
    """Check if using live Paystack credentials."""
    return self.paystack_secret_key.startswith("sk_live_")
```

---

## Payment Flow

### Complete Payment Lifecycle

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PAYMENT LIFECYCLE                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  STEP 1: INITIATE PAYMENT                                                   │
│  ═══════════════════════════════════════════════════════════════════════   │
│                                                                              │
│  Client                    Server                         Paystack           │
│    │                         │                               │               │
│    │  POST /checkout         │                               │               │
│    │  {tier: "professional"} │                               │               │
│    │─────────────────────────▶                               │               │
│    │                         │                               │               │
│    │                         │  calculate_subscription_price()               │
│    │                         │  generate reference           │               │
│    │                         │                               │               │
│    │                         │  POST /transaction/initialize │               │
│    │                         │─────────────────────────────────▶             │
│    │                         │                               │               │
│    │                         │  {authorization_url, access_code}             │
│    │                         │◀─────────────────────────────────             │
│    │                         │                               │               │
│    │                         │  Save PaymentTransaction      │               │
│    │                         │  (status: "pending")          │               │
│    │                         │                               │               │
│    │  {authorization_url}    │                               │               │
│    │◀─────────────────────────                               │               │
│    │                         │                               │               │
│                                                                              │
│  STEP 2: CUSTOMER PAYMENT                                                   │
│  ═══════════════════════════════════════════════════════════════════════   │
│                                                                              │
│  Client                    Paystack Checkout                                 │
│    │                         │                                               │
│    │  Redirect to checkout   │                                               │
│    │─────────────────────────▶                                               │
│    │                         │                                               │
│    │  Enter card/bank details│                                               │
│    │                         │                                               │
│    │  Payment processed      │                                               │
│    │◀─────────────────────────                                               │
│    │                         │                                               │
│                                                                              │
│  STEP 3: WEBHOOK NOTIFICATION                                               │
│  ═══════════════════════════════════════════════════════════════════════   │
│                                                                              │
│  Paystack                  Server                                            │
│    │                         │                                               │
│    │  POST /webhook/paystack │                                               │
│    │  X-Paystack-Signature   │                                               │
│    │  {event: "charge.success"}                                              │
│    │─────────────────────────▶                                               │
│    │                         │                                               │
│    │                         │  verify_paystack_signature()                  │
│    │                         │  Update PaymentTransaction                    │
│    │                         │  (status: "success")                          │
│    │                         │                                               │
│    │                         │  Upgrade TenantSKU                            │
│    │                         │  (tier: PROFESSIONAL)                         │
│    │                         │                                               │
│    │  HTTP 200 OK            │                                               │
│    │◀─────────────────────────                                               │
│    │                         │                                               │
│                                                                              │
│  STEP 4: CALLBACK (Optional)                                                │
│  ═══════════════════════════════════════════════════════════════════════   │
│                                                                              │
│  Client                    Server                         Paystack           │
│    │                         │                               │               │
│    │  GET /billing/callback  │                               │               │
│    │  ?reference=TVP-xxx     │                               │               │
│    │─────────────────────────▶                               │               │
│    │                         │                               │               │
│    │                         │  GET /transaction/verify/:ref │               │
│    │                         │─────────────────────────────────▶             │
│    │                         │                               │               │
│    │                         │  {status: "success", ...}     │               │
│    │                         │◀─────────────────────────────────             │
│    │                         │                               │               │
│    │  Redirect to dashboard  │                               │               │
│    │◀─────────────────────────                               │               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Code Example: Creating a Payment

```python
from app.services.billing_service import BillingService, BillingCycle
from app.models.sku import SKUTier

# Initialize service
service = BillingService(db_session)

# Create payment intent
intent = await service.create_payment_intent(
    organization_id=org_id,
    tier=SKUTier.PROFESSIONAL,
    billing_cycle=BillingCycle.MONTHLY,
    admin_email="admin@company.com",
    intelligence_addon=None,
    additional_users=0,
    callback_url="https://app.proaudit.com/billing/success"
)

# Response
{
    "id": "uuid-here",
    "reference": "TVP-8f3a2b1c-20260122120000",
    "amount_naira": 150000,
    "amount_formatted": "₦150,000",
    "authorization_url": "https://checkout.paystack.com/abc123def456",
    "status": "pending"
}
```

---

## API Endpoints

### GET /api/v1/billing/pricing

Get pricing information for all tiers.

**Response:**
```json
[
    {
        "tier": "core",
        "name": "Core",
        "tagline": "Essential accounting for small businesses",
        "monthly_amount": 50000,
        "monthly_formatted": "₦50,000",
        "annual_amount": 500000,
        "annual_formatted": "₦500,000",
        "annual_savings": 100000,
        "annual_savings_formatted": "₦100,000",
        "base_users": 3,
        "per_user_amount": 5000,
        "per_user_formatted": "₦5,000"
    },
    // ... professional, enterprise
]
```

### POST /api/v1/billing/checkout

Create a checkout session for payment.

**Request:**
```json
{
    "tier": "professional",
    "billing_cycle": "monthly",
    "intelligence_addon": null,
    "additional_users": 0,
    "callback_url": "https://app.proaudit.com/billing/success"
}
```

**Response:**
```json
{
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "reference": "TVP-8f3a2b1c-20260122120000",
    "amount_naira": 150000,
    "amount_formatted": "₦150,000",
    "currency": "NGN",
    "status": "pending",
    "authorization_url": "https://checkout.paystack.com/abc123",
    "tier": "professional",
    "billing_cycle": "monthly",
    "expires_at": "2026-01-23T12:00:00Z"
}
```

### GET /api/v1/billing/subscription

Get current organization subscription.

**Response:**
```json
{
    "tier": "professional",
    "tier_display": "Professional",
    "intelligence_addon": null,
    "billing_cycle": "monthly",
    "status": "active",
    "is_trial": false,
    "trial_days_remaining": null,
    "current_period_start": "2026-01-01T00:00:00Z",
    "current_period_end": "2026-02-01T00:00:00Z",
    "next_billing_date": "2026-02-01T00:00:00Z",
    "amount_naira": 150000,
    "amount_formatted": "₦150,000"
}
```

### GET /api/v1/billing/payments

Get payment history (paginated).

**Query Parameters:**
- `page` (int, default: 1): Page number
- `per_page` (int, default: 20, max: 100): Items per page
- `status_filter` (string, optional): Filter by status

**Response:**
```json
{
    "payments": [
        {
            "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "reference": "TVP-8f3a2b1c-20260122120000",
            "status": "success",
            "amount_naira": 150000,
            "amount_formatted": "₦150,000",
            "currency": "NGN",
            "tier": "professional",
            "billing_cycle": "monthly",
            "payment_method": "card",
            "card_last4": "4081",
            "card_brand": "visa",
            "gateway_response": "Successful",
            "created_at": "2026-01-22T12:00:00Z",
            "paid_at": "2026-01-22T12:05:00Z"
        }
    ],
    "total": 15,
    "page": 1,
    "per_page": 20,
    "has_more": false
}
```

### GET /api/v1/billing/payments/{payment_id}

Get details for a specific payment.

**Response:**
```json
{
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "reference": "TVP-8f3a2b1c-20260122120000",
    "status": "success",
    "amount_naira": 150000,
    "amount_formatted": "₦150,000",
    "currency": "NGN",
    "tier": "professional",
    "billing_cycle": "monthly",
    "payment_method": "card",
    "card_last4": "4081",
    "card_brand": "visa",
    "gateway_response": "Successful",
    "created_at": "2026-01-22T12:00:00Z",
    "paid_at": "2026-01-22T12:05:00Z"
}
```

### POST /api/v1/billing/webhook/paystack

Receive Paystack webhook events (internal use).

**Headers:**
- `X-Paystack-Signature`: HMAC-SHA512 signature of request body

**Request Body:**
```json
{
    "event": "charge.success",
    "data": {
        "id": 12345678,
        "reference": "TVP-8f3a2b1c-20260122120000",
        "status": "success",
        "amount": 15000000,
        "gateway_response": "Successful",
        "paid_at": "2026-01-22T12:05:00.000Z",
        "channel": "card",
        "fees": 150000,
        "authorization": {
            "card_type": "visa",
            "last4": "4081",
            "bank": "Zenith Bank"
        },
        "customer": {
            "email": "admin@company.com",
            "customer_code": "CUS_abc123"
        },
        "metadata": {
            "organization_id": "uuid-here",
            "tier": "professional",
            "billing_cycle": "monthly"
        }
    }
}
```

---

## Database Models

### PaymentTransaction

Stores all payment attempts and their outcomes.

```python
class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"
    
    # Primary Key
    id: UUID                          # Auto-generated UUID
    
    # Foreign Keys
    organization_id: UUID             # Link to organization
    user_id: UUID                     # User who initiated payment
    
    # Paystack Identifiers
    reference: str                    # Our reference (TVP-xxx-xxx)
    paystack_reference: str           # Paystack's reference
    paystack_access_code: str         # Checkout access code
    authorization_url: str            # Checkout URL
    
    # Transaction Details
    transaction_type: str             # "payment", "subscription", "refund"
    status: str                       # "pending", "success", "failed", etc.
    amount_kobo: int                  # Amount in kobo (100 kobo = ₦1)
    currency: str                     # "NGN"
    paystack_fee_kobo: int            # Paystack fee in kobo
    
    # SKU Context
    tier: SKUTier                     # CORE, PROFESSIONAL, ENTERPRISE
    billing_cycle: str                # "monthly", "annual"
    intelligence_addon: IntelligenceAddon
    additional_users: int
    
    # Payment Method (from Paystack)
    payment_method: str               # "card", "bank_transfer", "ussd"
    card_type: str                    # "visa", "mastercard", "verve"
    card_last4: str                   # Last 4 digits
    bank_name: str                    # Bank name
    
    # Timestamps
    initiated_at: datetime            # When payment started
    completed_at: datetime            # When payment finished
    webhook_received_at: datetime     # When webhook arrived
    
    # Tracking
    gateway_response: str             # Paystack response message
    failure_reason: str               # Error message if failed
    paystack_response: JSON           # Full API response
    custom_metadata: JSON             # Custom metadata
    webhook_event_id: str             # For idempotency
```

### Amount Handling

All monetary amounts are stored in **kobo** (smallest currency unit):

```python
# Properties for easy conversion
@property
def amount_naira(self) -> int:
    """Get amount in Naira (integer)."""
    return self.amount_kobo // 100

@property
def amount_naira_formatted(self) -> str:
    """Get formatted amount in Naira."""
    return f"₦{self.amount_naira:,}"

# Example:
# amount_kobo = 15000000  →  ₦150,000
```

---

## Security

### Webhook Signature Verification

All Paystack webhooks are verified using HMAC-SHA512:

```python
def verify_paystack_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    Verify Paystack webhook signature using HMAC-SHA512.
    Uses constant-time comparison to prevent timing attacks.
    """
    if not signature or not secret:
        return False
    
    expected = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha512
    ).hexdigest()
    
    return hmac.compare_digest(expected, signature)
```

### Security Best Practices

1. **Never expose secret keys** - Only use public key on frontend
2. **Always verify webhooks** - Reject requests with invalid signatures
3. **Use HTTPS** - All API calls must be over TLS
4. **Store minimal card data** - Only last4, never full card numbers
5. **Log without sensitive data** - Mask secret keys in logs
6. **Idempotency** - Store `webhook_event_id` to prevent duplicate processing

### Environment Security

```bash
# .env (NEVER commit to git)
PAYSTACK_SECRET_KEY=sk_live_xxxxx  # Keep this secret!
PAYSTACK_WEBHOOK_SECRET=whsec_xxxxx
```

---

## Pricing Tiers

### Nigerian Naira Pricing Structure

| Tier | Monthly (Min) | Annual (Min) | Base Users | Per User |
|------|---------------|--------------|------------|----------|
| **Core** | ₦25,000 | ₦250,000 | 3 | ₦5,000/mo |
| **Professional** | ₦150,000 | ₦1,500,000 | 10 | ₦10,000/mo |
| **Enterprise** | ₦1,000,000 | Custom | 50+ | Custom |

### Intelligence Add-ons

| Add-on | Monthly | Features |
|--------|---------|----------|
| **Standard** | ₦250,000 | ML anomaly detection, Benford's Law, Z-score |
| **Advanced** | ₦1,000,000 | + Custom ML training, NLP, Predictive analytics |

### Price Calculation

```python
def calculate_subscription_price(
    tier: SKUTier,
    billing_cycle: BillingCycle,
    intelligence_addon: Optional[IntelligenceAddon] = None,
    additional_users: int = 0,
) -> int:
    """
    Calculate total subscription price in Naira.
    
    Annual billing = 10 months (20% discount)
    """
    # Base price
    base = tier_pricing[tier].monthly if monthly else tier_pricing[tier].annual
    
    # Additional users
    user_cost = additional_users * per_user_rate
    if annual:
        user_cost *= 10  # 20% discount
    
    # Intelligence add-on
    addon_cost = intelligence_pricing[addon].monthly if addon else 0
    if annual:
        addon_cost *= 10
    
    return base + user_cost + addon_cost
```

---

## Webhook Handling

### Supported Events

| Event | Description | Action |
|-------|-------------|--------|
| `charge.success` | Payment completed | Update transaction, upgrade SKU |
| `charge.failed` | Payment failed | Mark failed, log reason |
| `subscription.create` | Subscription created | Activate subscription |
| `subscription.disable` | Subscription cancelled | Downgrade or deactivate |
| `invoice.payment_failed` | Recurring payment failed | Send notification, retry |
| `refund.processed` | Refund completed | Update transaction status |

### Webhook Processing

```python
async def process_payment_webhook(event_type: str, payload: dict) -> dict:
    if event_type == "charge.success":
        # 1. Update PaymentTransaction to success
        # 2. Extract metadata (org_id, tier, etc.)
        # 3. Upgrade TenantSKU
        return {"handled": True}
    
    elif event_type == "invoice.payment_failed":
        # 1. Update PaymentTransaction to failed
        # 2. Log failure reason
        # 3. TODO: Send notification
        return {"handled": True}
```

### Webhook URL Configuration

Configure in Paystack Dashboard:
1. Go to Settings → API Keys & Webhooks
2. Add webhook URL: `https://api.proaudit.com/api/v1/billing/webhook/paystack`
3. Copy webhook secret to `.env`

---

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Invalid signature` | Webhook secret mismatch | Verify PAYSTACK_WEBHOOK_SECRET |
| `Payment initialization failed` | Invalid API key | Check PAYSTACK_SECRET_KEY |
| `Request timed out` | Network issues | Retry with exponential backoff |
| `Insufficient funds` | Customer card declined | Notify customer |

### Error Response Format

```python
class PaymentResult:
    success: bool
    reference: str
    status: PaymentStatus    # SUCCESS, FAILED, PENDING, etc.
    amount_naira: int
    message: str            # Human-readable message
    transaction_id: str
    paid_at: datetime
    metadata: dict          # Additional details
```

### Graceful Degradation

When credentials are missing, the system falls back to **stub mode**:

```python
if not self.secret_key:
    self._is_stub = True
    # Returns fake data for testing
```

---

## Testing

### Running Payment Tests

```bash
# Run all payment tests
python -m pytest tests/test_paystack_provider.py -v

# Run specific test class
python -m pytest tests/test_paystack_provider.py::TestWebhookSignatureVerification -v
```

### Test Coverage

| Test Class | Coverage |
|------------|----------|
| `TestWebhookSignatureVerification` | Signature validation |
| `TestPaystackProviderStubMode` | Stub mode functionality |
| `TestPaystackProviderRealMode` | Mocked API calls |
| `TestBillingServicePricing` | Price calculations |
| `TestPaymentTransactionModel` | Model properties |

### Mocking Paystack API

```python
@pytest.mark.asyncio
async def test_initialize_payment_success(paystack_provider, mock_response):
    with patch('httpx.AsyncClient') as MockClient:
        mock_client = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": True, "data": {...}}
        mock_client.request = AsyncMock(return_value=mock_response)
        MockClient.return_value.__aenter__.return_value = mock_client
        
        result = await paystack_provider.initialize_payment(...)
        assert result["status"] is True
```

---

## Production Deployment

### Checklist

- [ ] Replace test keys with live keys
- [ ] Configure webhook URL in Paystack dashboard
- [ ] Set `PAYSTACK_WEBHOOK_SECRET`
- [ ] Enable HTTPS for all endpoints
- [ ] Set up monitoring for failed payments
- [ ] Configure email notifications for payment events
- [ ] Test full payment flow with ₦50 transaction

### Monitoring

Monitor these metrics:
- Payment success rate
- Average payment amount
- Failed payment reasons
- Webhook processing time
- API response times

### Support

- **Paystack Documentation**: https://paystack.com/docs
- **API Reference**: https://paystack.com/docs/api
- **Dashboard**: https://dashboard.paystack.com

---

## Appendix

### Payment Status Codes

| Status | Description |
|--------|-------------|
| `pending` | Payment initiated, awaiting completion |
| `processing` | Payment being processed |
| `success` | Payment completed successfully |
| `failed` | Payment failed |
| `cancelled` | Payment cancelled by user |
| `refunded` | Full refund processed |
| `partially_refunded` | Partial refund processed |
| `disputed` | Chargeback/dispute raised |

### Currency Conversion

```
1 Naira (₦) = 100 Kobo

Examples:
₦50,000    = 5,000,000 kobo
₦150,000   = 15,000,000 kobo
₦1,000,000 = 100,000,000 kobo
```

### Reference Format

```
TVP-{org_id_prefix}-{timestamp}

Example: TVP-8f3a2b1c-20260122120000
         │   │          │
         │   │          └─ YYYYMMDDHHmmss
         │   └─ First 8 chars of org UUID
         └─ Tekvwa Pro Audit prefix
```
