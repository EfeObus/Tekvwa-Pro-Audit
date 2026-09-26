"""
Tekvwa Pro Audit - SKU (Stock Keeping Unit) Models

Commercial product tier definitions for:
- Pro Audit Core (SME)
- Pro Audit Professional (Mid-Market)
- Pro Audit Enterprise (Large Organizations)
- Pro Audit Intelligence (Add-on for ML/AI features)

Nigerian Market Pricing (Naira)
"""

import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Dict, Any, List

from sqlalchemy import (
    String, Text, Integer, Boolean, DateTime, Date,
    Numeric, Enum as SQLEnum, ForeignKey, JSON, BigInteger
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

# Import enums from separate file to avoid circular imports
from app.models.sku_enums import (
    SKUTier,
    IntelligenceAddon,
    Feature,
    UsageMetricType,
    BillingCycle,
)

# Re-export for backwards compatibility
__all__ = [
    'SKUTier',
    'IntelligenceAddon', 
    'Feature',
    'UsageMetricType',
    'BillingCycle',
    'SKUPricing',
    'TenantSKU',
    'UsageRecord',
    'UsageEvent',
    'FeatureAccessLog',
    'PaymentTransaction',
    'TIER_LIMITS',
    'INTELLIGENCE_LIMITS',
]

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.organization import Organization


# =============================================================================
# MODELS
# =============================================================================

class SKUPricing(BaseModel):
    """
    Pricing configuration for each SKU tier.
    Prices in Nigerian Naira (₦).
    """
    __tablename__ = "sku_pricing"
    
    sku_tier: Mapped[SKUTier] = mapped_column(
        SQLEnum(SKUTier, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
    )
    
    # Base pricing (Naira)
    base_price_monthly: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="Base monthly price in Naira"
    )
    base_price_annual: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="Annual price in Naira (typically 15% discount)"
    )
    
    # Per-user pricing for additional users
    price_per_user: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Price per additional user in Naira"
    )
    
    # Intelligence add-on pricing
    intelligence_standard_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="Standard Intelligence add-on price in Naira"
    )
    intelligence_advanced_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="Advanced Intelligence add-on price in Naira"
    )
    
    # Effective dates
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Metadata
    currency: Mapped[str] = mapped_column(
        String(3),
        default="NGN",
        comment="ISO currency code"
    )

    # Fixed foreign-currency prices (avoids live FX conversion when configured)
    base_price_monthly_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    base_price_annual_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    base_price_monthly_eur: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    base_price_annual_eur: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    base_price_monthly_gbp: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    base_price_annual_gbp: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)


class TenantSKU(BaseModel):
    """
    SKU assignment for a tenant (organization).
    Tracks what tier they're on and any custom overrides.
    """
    __tablename__ = "tenant_skus"
    
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    
    # Relationship back to organization
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="tenant_sku",
    )
    
    # Current SKU tier (CORE, PROFESSIONAL, ENTERPRISE)
    tier: Mapped[SKUTier] = mapped_column(
        SQLEnum(SKUTier, values_callable=lambda x: [e.value for e in x]),
        default=SKUTier.CORE,
        nullable=False,
    )
    
    # Intelligence add-on (NONE, STANDARD, ADVANCED)
    intelligence_addon: Mapped[Optional[IntelligenceAddon]] = mapped_column(
        SQLEnum(IntelligenceAddon, values_callable=lambda x: [e.value for e in x]),
        default=IntelligenceAddon.NONE,
        nullable=True,
    )
    
    # Billing cycle (monthly, quarterly, annual)
    billing_cycle: Mapped[str] = mapped_column(
        String(20),
        default="monthly",
        nullable=False,
    )
    
    # Current billing period
    current_period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    current_period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    
    # Trial period
    trial_ends_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the trial period ends (null if not on trial)"
    )
    
    # Feature overrides (JSON: {"feature_name": true/false})
    # Allows enabling/disabling specific features outside normal tier
    feature_overrides: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Override specific features for this tenant"
    )
    
    # Custom limits (JSON: {"metric": limit_value})
    # Allows custom limits outside normal tier limits
    custom_limits: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Custom usage limits for this tenant"
    )
    
    # Pricing overrides (for negotiated enterprise deals) in Naira
    custom_price_naira: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Custom negotiated monthly price in Nigerian Naira"
    )
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    suspended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    suspension_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Cancellation scheduling
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="If True, subscription will be cancelled/downgraded at end of current period"
    )
    cancellation_requested_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When cancellation was requested"
    )
    cancellation_reason: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Reason for cancellation"
    )
    scheduled_downgrade_tier: Mapped[Optional[SKUTier]] = mapped_column(
        SQLEnum(SKUTier, values_callable=lambda x: [e.value for e in x]),
        nullable=True,
        comment="Tier to downgrade to at period end (usually CORE)"
    )
    
    # Audit trail
    upgraded_from: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Previous tier before upgrade"
    )
    upgraded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    upgraded_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True
    )
    
    # Custom limit overrides (for enterprise deals)
    custom_user_limit: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Override default user limit for this tenant"
    )
    custom_entity_limit: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Override default entity limit for this tenant"
    )
    custom_transaction_limit: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Override default transaction limit (-1 for unlimited)"
    )
    
    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # ==========================================================================
    # Issue #31: Billing Cycle Alignment
    # ==========================================================================
    billing_anchor_day: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Day of month for billing (1-28). Null = subscription start date"
    )
    align_to_calendar_month: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="If true, align billing to 1st of month"
    )
    prorated_first_period: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        comment="If true, prorate first billing period"
    )
    
    # ==========================================================================
    # Issue #32: Subscription Pause/Resume
    # ==========================================================================
    paused_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When subscription was paused (null if not paused)"
    )
    pause_reason: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Reason for pausing subscription"
    )
    pause_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When to automatically resume (max 90 days from pause)"
    )
    pause_credits_days: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Days credited when paused (extends subscription)"
    )
    total_paused_days: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Total cumulative days subscription has been paused"
    )
    pause_count_this_year: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Number of times paused this calendar year (max 2 allowed)"
    )
    last_pause_year: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Calendar year of pause count tracking (resets annually)"
    )
    
    # ==========================================================================
    # Issue #36: Multi-Currency Support
    # ==========================================================================
    preferred_currency: Mapped[str] = mapped_column(
        String(3),
        default="NGN",
        comment="Preferred billing currency (NGN, USD, EUR, GBP)"
    )
    locked_exchange_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 6),
        nullable=True,
        comment="Locked exchange rate for this subscription (null = use current)"
    )
    
    @property
    def is_trial(self) -> bool:
        """Check if subscription is currently in trial period."""
        if self.trial_ends_at:
            return self.trial_ends_at > datetime.now()
        return False
    
    @property
    def is_paused(self) -> bool:
        """Check if subscription is currently paused."""
        return self.paused_at is not None and (
            self.pause_until is None or self.pause_until > datetime.now()
        )


class UsageRecord(BaseModel):
    """
    Track usage metrics for billing and limit enforcement.
    Records are created per organization per billing period.
    """
    __tablename__ = "usage_records"
    
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Relationship back to organization
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="usage_records",
    )
    
    # Period - with indexes for date range queries (#42)
    period_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    
    # Usage counts
    transactions_count: Mapped[int] = mapped_column(BigInteger, default=0)
    users_count: Mapped[int] = mapped_column(Integer, default=0)
    entities_count: Mapped[int] = mapped_column(Integer, default=0)
    invoices_count: Mapped[int] = mapped_column(Integer, default=0)
    api_calls_count: Mapped[int] = mapped_column(BigInteger, default=0)
    ocr_pages_count: Mapped[int] = mapped_column(Integer, default=0)
    storage_used_mb: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    ml_inferences_count: Mapped[int] = mapped_column(BigInteger, default=0)
    employees_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Limit breach tracking
    limit_breaches: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Record of any limit breaches this period"
    )
    
    # Billing
    is_billed: Mapped[bool] = mapped_column(Boolean, default=False)
    billed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    invoice_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)


class UsageEvent(BaseModel):
    """
    Individual usage events for real-time metering.
    Aggregated into UsageRecord periodically.
    """
    __tablename__ = "usage_events"
    
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    
    metric_type: Mapped[UsageMetricType] = mapped_column(
        SQLEnum(UsageMetricType),
        nullable=False,
        index=True,
    )
    
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    
    # For tracking specific resources
    resource_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Event metadata (named event_metadata to avoid conflict with SQLAlchemy's metadata)
    event_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Timestamp is inherited from BaseModel (created_at)


class FeatureAccessLog(BaseModel):
    """
    Log feature access attempts for auditing and analytics.
    Tracks both successful access and denials.
    """
    __tablename__ = "feature_access_logs"
    
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    
    feature: Mapped[Feature] = mapped_column(
        SQLEnum(Feature),
        nullable=False,
        index=True,
    )
    
    was_granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    
    # If denied, why?
    denial_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Request context
    endpoint: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)


class PaymentTransaction(BaseModel):
    """
    Record of all payment transactions processed through Paystack.
    
    Stores payment intents, completions, refunds, and subscription events.
    Essential for:
    - Financial reconciliation
    - Audit trail
    - Subscription management
    - Refund processing
    """
    __tablename__ = "payment_transactions"
    
    # Organization context
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # User who initiated payment (if known)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    tenant_sku_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant_skus.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Paystack references
    reference: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment="Tekvwa payment reference (TVP-XXXXX)"
    )
    paystack_reference: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Paystack transaction reference"
    )
    paystack_access_code: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Paystack checkout access code"
    )
    authorization_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Paystack checkout URL"
    )
    
    # Transaction type
    transaction_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="subscription",
        comment="subscription, one_time, refund, etc."
    )
    
    # Status tracking
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        index=True,
        comment="pending, success, failed, refunded, cancelled"
    )
    
    # Amount details (stored in kobo for Paystack compatibility)
    amount_kobo: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="Amount in kobo (100 kobo = 1 Naira)"
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="NGN",
    )
    
    # Fee tracking
    fee_kobo: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Paystack transaction fee in kobo"
    )
    
    # SKU context - using String to match VARCHAR columns in database
    # (PostgreSQL ENUMs were converted to VARCHAR for flexibility)
    tier: Mapped[Optional[SKUTier]] = mapped_column(
        String(50),
        nullable=True,
        comment="SKU tier: core, professional, enterprise"
    )
    billing_cycle: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="monthly, annual"
    )
    intelligence_addon: Mapped[Optional[IntelligenceAddon]] = mapped_column(
        String(50),
        nullable=True,
        comment="Intelligence addon: standard, advanced"
    )
    additional_users: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    
    # Payment method details (from Paystack response)
    payment_method: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="card, bank_transfer, ussd, etc."
    )
    channel: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Paystack payment channel"
    )
    card_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="visa, mastercard, verve, etc."
    )
    card_last4: Mapped[Optional[str]] = mapped_column(
        String(4),
        nullable=True,
    )
    card_exp_month: Mapped[Optional[str]] = mapped_column(
        String(2),
        nullable=True,
    )
    card_exp_year: Mapped[Optional[str]] = mapped_column(
        String(4),
        nullable=True,
    )
    card_bank: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    card_brand: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    customer_email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    customer_code: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    callback_url: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Timestamps - with indexes for date range queries (#43)
    paid_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="When payment was confirmed successful",
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When payment was verified with the provider",
    )
    failed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When payment failed",
    )
    
    # Webhook tracking
    webhook_received_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    webhook_event_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Paystack webhook event ID for idempotency"
    )
    
    # Error tracking
    error_code: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    retry_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    gateway_response: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Raw gateway response message"
    )

    # Full response storage (for debugging/audit)
    paystack_response: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Full Paystack API response"
    )

    # Custom metadata
    custom_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Custom metadata for the transaction"
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)

    # Refund tracking
    refunded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When refund was processed"
    )
    refund_amount_kobo: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Refund amount in kobo"
    )
    refund_reference: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Paystack refund/transfer reference"
    )
    refund_reason: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Reason for refund"
    )
    
    # Paystack invoice tracking (for subscription billing)
    paystack_invoice_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Paystack invoice ID for subscription payments"
    )
    paystack_invoice_status: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Paystack invoice status (pending, paid, failed)"
    )
    
    @property
    def amount_naira(self) -> int:
        """Get amount in Naira (integer)."""
        return self.amount_kobo // 100
    
    @property
    def amount_naira_formatted(self) -> str:
        """Get formatted amount in Naira."""
        return f"₦{self.amount_naira:,}"
    
    @property
    def fee_naira(self) -> Optional[int]:
        """Get Paystack fee in Naira."""
        if self.fee_kobo:
            return self.fee_kobo // 100
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "reference": self.reference,
            "paystack_reference": self.paystack_reference,
            "status": self.status,
            "amount_naira": self.amount_naira,
            "amount_formatted": self.amount_naira_formatted,
            "currency": self.currency,
            "tier": self.tier.value if self.tier else None,
            "billing_cycle": self.billing_cycle,
            "payment_method": self.payment_method,
            "card_last4": self.card_last4,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "failed_at": self.failed_at.isoformat() if self.failed_at else None,
            "failure_reason": self.error_message,
        }


# =============================================================================
# TIER LIMITS CONFIGURATION (Default limits per tier)
# =============================================================================

# These are the default limits - can be overridden per tenant in TenantSKU.custom_limits
TIER_LIMITS = {
    SKUTier.CORE: {
        UsageMetricType.USERS: 5,
        UsageMetricType.ENTITIES: 1,
        UsageMetricType.TRANSACTIONS: 10_000,  # per month
        UsageMetricType.INVOICES: 100,  # per month
        UsageMetricType.API_CALLS: 0,  # No API access
        UsageMetricType.OCR_PAGES: 0,  # No OCR
        UsageMetricType.STORAGE_MB: 5_000,  # 5 GB
        UsageMetricType.ML_INFERENCES: 0,  # No ML
        UsageMetricType.EMPLOYEES: 10,  # Basic payroll limit
    },
    SKUTier.PROFESSIONAL: {
        UsageMetricType.USERS: 25,
        UsageMetricType.ENTITIES: 1,
        UsageMetricType.TRANSACTIONS: 100_000,  # per month
        UsageMetricType.INVOICES: 1_000,  # per month
        UsageMetricType.API_CALLS: 1_000,  # per hour (read-only)
        UsageMetricType.OCR_PAGES: 0,  # Requires Intelligence add-on
        UsageMetricType.STORAGE_MB: 50_000,  # 50 GB
        UsageMetricType.ML_INFERENCES: 0,  # Requires Intelligence add-on
        UsageMetricType.EMPLOYEES: 500,
    },
    SKUTier.ENTERPRISE: {
        UsageMetricType.USERS: -1,  # Unlimited
        UsageMetricType.ENTITIES: -1,  # Unlimited
        UsageMetricType.TRANSACTIONS: 1_000_000,  # per month (soft limit)
        UsageMetricType.INVOICES: -1,  # Unlimited
        UsageMetricType.API_CALLS: 10_000,  # per hour
        UsageMetricType.OCR_PAGES: 0,  # Requires Intelligence add-on
        UsageMetricType.STORAGE_MB: 500_000,  # 500 GB
        UsageMetricType.ML_INFERENCES: 0,  # Requires Intelligence add-on
        UsageMetricType.EMPLOYEES: -1,  # Unlimited
    },
}

# Intelligence add-on limits (added to base tier limits)
INTELLIGENCE_LIMITS = {
    IntelligenceAddon.NONE: {
        UsageMetricType.OCR_PAGES: 0,
        UsageMetricType.ML_INFERENCES: 0,
    },
    IntelligenceAddon.STANDARD: {
        UsageMetricType.OCR_PAGES: 1_000,  # per month
        UsageMetricType.ML_INFERENCES: 10_000,  # per day
    },
    IntelligenceAddon.ADVANCED: {
        UsageMetricType.OCR_PAGES: 5_000,  # per month
        UsageMetricType.ML_INFERENCES: 50_000,  # per day
    },
}


# =============================================================================
# ISSUE #33: SERVICE CREDITS MODEL
# =============================================================================

class ServiceCredit(BaseModel):
    """
    Service credits for SLA breaches, goodwill gestures, or promotions.
    Credits can be applied to future invoices.
    """
    __tablename__ = "service_credits"
    
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Credit details
    credit_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="sla_breach, goodwill, promotion, referral_reward"
    )
    amount_ngn: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Credit amount in Naira"
    )
    amount_usd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Credit amount in USD (for multi-currency)"
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="NGN",
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    
    # SLA breach details (if applicable)
    incident_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Reference to incident/outage"
    )
    incident_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    downtime_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    availability_percentage: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),
        nullable=True
    )
    
    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        comment="pending, approved, applied, expired, rejected"
    )
    approved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    # Application
    applied_to_invoice_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Invoice where credit was applied"
    )
    applied_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    amount_applied_ngn: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Actual amount applied"
    )
    
    # Expiry
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Credit expires after 12 months"
    )
    
    # Notes
    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    @property
    def is_expired(self) -> bool:
        """Check if credit has expired."""
        if self.expires_at:
            return self.expires_at < datetime.now()
        return False
    
    @property
    def is_available(self) -> bool:
        """Check if credit is available for use."""
        return (
            self.status == "approved" and
            not self.is_expired and
            self.applied_at is None
        )


# =============================================================================
# ISSUE #34: DISCOUNT CODES MODEL
# =============================================================================

class DiscountCode(BaseModel):
    """
    Discount and referral codes for billing.
    """
    __tablename__ = "discount_codes"
    
    # Code details
    code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
        comment="Unique discount code (e.g., WELCOME20)"
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Display name for the discount"
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Discount type and value
    discount_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="percentage, fixed_amount, free_months"
    )
    discount_value: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="Percentage (0-100), amount in Naira, or months"
    )
    max_discount_ngn: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Cap on discount amount (for percentage discounts)"
    )
    
    # Applicability
    applies_to_tiers: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
        comment='Null = all tiers, or ["core", "professional"]'
    )
    applies_to_billing_cycles: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
        comment='Null = all, or ["monthly", "annual"]'
    )
    min_subscription_months: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Minimum commitment for discount"
    )
    first_payment_only: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )
    
    # Usage limits
    max_uses_total: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Null = unlimited"
    )
    max_uses_per_org: Mapped[int] = mapped_column(
        Integer,
        default=1,
    )
    current_uses: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    
    # Validity period
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )
    valid_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Null = never expires"
    )
    
    # Referral link (if this is a referral code)
    is_referral_code: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )
    referrer_organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Org that owns this referral code"
    )
    referrer_reward_type: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="credit, percentage, free_months"
    )
    referrer_reward_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2),
        nullable=True
    )
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True
    )
    
    @property
    def is_valid(self) -> bool:
        """Check if discount code is currently valid."""
        now = datetime.now()
        if not self.is_active:
            return False
        if self.valid_from > now:
            return False
        if self.valid_until and self.valid_until < now:
            return False
        if self.max_uses_total and self.current_uses >= self.max_uses_total:
            return False
        return True
    
    @property
    def remaining_uses(self) -> Optional[int]:
        """Get remaining uses (None if unlimited)."""
        if self.max_uses_total is None:
            return None
        return max(0, self.max_uses_total - self.current_uses)


class DiscountCodeUsage(BaseModel):
    """
    Track usage of discount codes.
    """
    __tablename__ = "discount_code_usages"
    
    discount_code_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discount_codes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True
    )
    
    # Usage details
    payment_reference: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )
    original_amount_ngn: Mapped[int] = mapped_column(Integer, nullable=False)
    discount_amount_ngn: Mapped[int] = mapped_column(Integer, nullable=False)
    final_amount_ngn: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Referrer reward (if applicable)
    referrer_reward_issued: Mapped[bool] = mapped_column(
        Boolean,
        default=False
    )
    referrer_credit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True
    )


# =============================================================================
# ISSUE #35: VOLUME DISCOUNT RULES MODEL
# =============================================================================

class VolumeDiscountRule(BaseModel):
    """
    Dynamic volume-based discount rules.
    """
    __tablename__ = "volume_discount_rules"
    
    # Rule identification
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Rule type
    rule_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="user_count, entity_count, commitment_months, combined"
    )
    
    # Thresholds
    min_users: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Minimum users for this discount"
    )
    max_users: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Maximum users (null = unlimited)"
    )
    min_entities: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_entities: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    min_commitment_months: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="12, 24, 36 month commitments"
    )
    
    # Discount
    discount_percentage: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        comment="Percentage off base price"
    )
    
    # Applicability
    applies_to_tier: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Null = all tiers"
    )
    applies_to_currency: Mapped[Optional[str]] = mapped_column(
        String(3),
        nullable=True,
        comment="Null = all currencies"
    )
    
    # Priority (higher = applied first)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    stackable: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Can combine with other volume discounts"
    )
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    
    @property
    def is_effective(self) -> bool:
        """Check if rule is currently effective."""
        today = date.today()
        if not self.is_active:
            return False
        if self.effective_from > today:
            return False
        if self.effective_until and self.effective_until < today:
            return False
        return True


# =============================================================================
# ISSUE #36: EXCHANGE RATES MODEL
# =============================================================================

class ExchangeRate(BaseModel):
    """
    Exchange rates for multi-currency billing.
    """
    __tablename__ = "exchange_rates"
    
    from_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        comment="Source currency (e.g., USD)"
    )
    to_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        comment="Target currency (e.g., NGN)"
    )
    rate: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        comment="1 from_currency = rate to_currency"
    )
    rate_date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="CBN, manual, api"
    )
    is_billing_rate: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Rate used for billing (more stable)"
    )


# =============================================================================
# ISSUE #30: SCHEDULED USAGE REPORTS MODEL
# =============================================================================

class ScheduledUsageReport(BaseModel):
    """
    Scheduled usage report configuration.
    """
    __tablename__ = "scheduled_usage_reports"
    
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True
    )
    
    # Schedule
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    frequency: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="daily, weekly, monthly, quarterly"
    )
    day_of_week: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="0-6 for weekly reports"
    )
    day_of_month: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="1-28 for monthly reports"
    )
    
    # Report configuration
    report_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="usage_summary, detailed_usage, billing_history"
    )
    format: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="csv, pdf, excel"
    )
    include_charts: Mapped[bool] = mapped_column(Boolean, default=True)
    date_range_months: Mapped[int] = mapped_column(Integer, default=1)
    
    # Delivery
    delivery_method: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="email, download, both"
    )
    email_recipients: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True
    )
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    next_run_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class UsageReportHistory(BaseModel):
    """
    History of generated usage reports.
    """
    __tablename__ = "usage_report_history"
    
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scheduled_report_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Null if ad-hoc report"
    )
    generated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True
    )
    
    # Report details
    report_type: Mapped[str] = mapped_column(String(30), nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    
    # File
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Delivery status
    email_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    email_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    email_recipients: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True
    )
    
    # Expiry (auto-delete after 90 days)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )


# Update __all__ to include new models
__all__ = [
    'SKUTier',
    'IntelligenceAddon', 
    'Feature',
    'UsageMetricType',
    'BillingCycle',
    'SKUPricing',
    'TenantSKU',
    'UsageRecord',
    'UsageEvent',
    'FeatureAccessLog',
    'PaymentTransaction',
    'ServiceCredit',
    'DiscountCode',
    'DiscountCodeUsage',
    'VolumeDiscountRule',
    'ExchangeRate',
    'ScheduledUsageReport',
    'UsageReportHistory',
    'TIER_LIMITS',
    'INTELLIGENCE_LIMITS',
]
