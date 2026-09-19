"""
Tekvwa Pro Audit - Billing Router

API endpoints for billing, subscription management, and payments.
Uses Paystack as the primary payment provider for Nigerian Naira.
"""

import logging
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Path, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field, EmailStr

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.organization import Organization
from app.models.sku import SKUTier, IntelligenceAddon, PaymentTransaction
from app.services.billing_service import (
    BillingService,
    BillingCycle,
    PaymentStatus,
)
from app.services.invoice_pdf_service import InvoicePDFService
from app.services.dunning_service import DunningService, DunningLevel
from app.services.billing_email_service import BillingEmailService
from app.config.sku_config import TIER_PRICING, INTELLIGENCE_PRICING, TIER_LIMITS_CONFIG
from sqlalchemy import select, desc, func


logger = logging.getLogger(__name__)


def _format_limit(value: int, suffix: str = "") -> str:
    """Format a limit value for display. -1 means unlimited."""
    if value == -1:
        return "Unlimited"
    elif value == 0:
        return "No access"
    elif suffix:
        return f"{value:,} {suffix}"
    else:
        return f"{value:,}"


def _get_tier_limits_response(tier: SKUTier) -> "TierLimitsResponse":
    """Build TierLimitsResponse from TIER_LIMITS_CONFIG (Issue #53)."""
    limits = TIER_LIMITS_CONFIG.get(tier, TIER_LIMITS_CONFIG[SKUTier.CORE])
    
    # Format storage in human-readable format
    storage_gb = limits.storage_limit_mb / 1000
    storage_display = f"{int(storage_gb)} GB" if storage_gb >= 1 else f"{limits.storage_limit_mb} MB"
    
    # Format retention
    if limits.audit_log_retention_days >= 365:
        years = limits.audit_log_retention_days / 365
        retention_display = f"{years:.0f} year{'s' if years > 1 else ''}"
    else:
        retention_display = f"{limits.audit_log_retention_days} days"
    
    # Import here to avoid circular import at module level
    from app.routers.billing import TierLimitsResponse
    
    return TierLimitsResponse(
        max_users=limits.max_users,
        max_users_display=_format_limit(limits.max_users, "users"),
        max_entities=limits.max_entities,
        max_entities_display=_format_limit(limits.max_entities, "entities"),
        max_transactions_monthly=limits.max_transactions_monthly,
        max_transactions_display=_format_limit(limits.max_transactions_monthly, "/month"),
        max_invoices_monthly=limits.max_invoices_monthly,
        max_invoices_display=_format_limit(limits.max_invoices_monthly, "/month"),
        max_employees=limits.max_employees,
        max_employees_display=_format_limit(limits.max_employees, "employees"),
        api_calls_per_hour=limits.api_calls_per_hour,
        api_calls_display=_format_limit(limits.api_calls_per_hour, "/hour") + (" (read-only)" if limits.api_read_only and limits.api_calls_per_hour > 0 else ""),
        api_read_only=limits.api_read_only,
        storage_limit_mb=limits.storage_limit_mb,
        storage_limit_display=storage_display,
        audit_log_retention_days=limits.audit_log_retention_days,
        audit_retention_display=retention_display,
    )

router = APIRouter(prefix="/api/v1/billing", tags=["Billing"])


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class CreatePaymentIntentRequest(BaseModel):
    """Request to create a payment intent."""
    tier: SKUTier = Field(..., description="Target SKU tier")
    billing_cycle: str = Field("monthly", description="monthly or annual")
    intelligence_addon: Optional[IntelligenceAddon] = Field(None, description="Intelligence add-on")
    additional_users: int = Field(0, ge=0, description="Additional users beyond base")
    callback_url: Optional[str] = Field(None, description="Custom callback URL")
    is_upgrade: bool = Field(False, description="If true, calculates prorated amount for mid-cycle upgrade")
    # Billing feature #34: Discount codes
    discount_code: Optional[str] = Field(None, description="Discount/promo code to apply")
    # Billing feature #36: Multi-currency checkout
    currency: Optional[str] = Field("NGN", description="Currency for payment (NGN, USD, EUR, GBP)")


class PaymentIntentResponse(BaseModel):
    """Response for payment intent creation."""
    id: str
    reference: str
    amount_naira: int
    amount_formatted: str
    currency: str
    status: str
    authorization_url: Optional[str]
    tier: str
    billing_cycle: str
    expires_at: str


class PricingTierResponse(BaseModel):
    """Pricing information for a tier."""
    tier: str
    name: str
    tagline: str
    monthly_amount: int
    monthly_formatted: str
    annual_amount: int
    annual_formatted: str
    annual_savings: int
    annual_savings_formatted: str
    base_users: int
    per_user_amount: int
    per_user_formatted: str


class TierLimitsResponse(BaseModel):
    """Usage limits for the current tier (Issue #53)."""
    max_users: int = Field(..., description="Maximum users allowed (-1 = unlimited)")
    max_users_display: str = Field(..., description="Human-readable max users")
    max_entities: int = Field(..., description="Maximum entities allowed (-1 = unlimited)")
    max_entities_display: str = Field(..., description="Human-readable max entities")
    max_transactions_monthly: int = Field(..., description="Max transactions per month")
    max_transactions_display: str = Field(..., description="Human-readable max transactions")
    max_invoices_monthly: int = Field(..., description="Max invoices per month (-1 = unlimited)")
    max_invoices_display: str = Field(..., description="Human-readable max invoices")
    max_employees: int = Field(..., description="Max payroll employees (-1 = unlimited)")
    max_employees_display: str = Field(..., description="Human-readable max employees")
    api_calls_per_hour: int = Field(..., description="API rate limit per hour (0 = no access)")
    api_calls_display: str = Field(..., description="Human-readable API limit")
    api_read_only: bool = Field(..., description="If True, API access is read-only")
    storage_limit_mb: int = Field(..., description="Storage limit in MB")
    storage_limit_display: str = Field(..., description="Human-readable storage limit (e.g., '5 GB')")
    audit_log_retention_days: int = Field(..., description="Audit log retention in days")
    audit_retention_display: str = Field(..., description="Human-readable retention (e.g., '90 days')")


class SubscriptionResponse(BaseModel):
    """Current subscription information."""
    tier: str
    tier_display: str
    intelligence_addon: Optional[str]
    billing_cycle: str
    status: str
    is_trial: bool
    trial_days_remaining: Optional[int]
    current_period_start: Optional[str]
    current_period_end: Optional[str]
    next_billing_date: Optional[str]
    amount_naira: int
    amount_formatted: str
    # Cancellation/downgrade fields
    cancel_at_period_end: bool = False
    cancellation_requested_at: Optional[str] = None
    cancellation_reason: Optional[str] = None
    scheduled_downgrade_tier: Optional[str] = None
    # Issue #53: Tier limits included in response
    tier_limits: Optional[TierLimitsResponse] = Field(None, description="Usage limits for this tier")


class WebhookPayload(BaseModel):
    """Paystack webhook payload."""
    event: str
    data: dict


class PaymentTransactionResponse(BaseModel):
    """Response for a payment transaction."""
    id: str
    reference: str
    status: str
    amount_naira: int
    amount_formatted: str
    currency: str
    tier: Optional[str]
    billing_cycle: Optional[str]
    payment_method: Optional[str]
    card_last4: Optional[str]
    card_brand: Optional[str]
    gateway_response: Optional[str]
    created_at: str
    paid_at: Optional[str]
    
    class Config:
        from_attributes = True


class PaymentHistoryResponse(BaseModel):
    """Response for payment history."""
    payments: List[PaymentTransactionResponse]
    total: int
    page: int
    per_page: int
    has_more: bool


class SubscriptionAccessResponse(BaseModel):
    """Response for subscription access check."""
    has_access: bool
    status: str
    tier: Optional[str]
    message: str
    days_remaining: int
    grace_period_remaining: int
    is_trial: bool


class DunningStatusResponse(BaseModel):
    """Response for dunning status."""
    organization_id: str
    level: str
    amount_naira: int
    amount_formatted: str
    first_failure_at: Optional[str]
    last_retry_at: Optional[str]
    retry_count: int
    next_retry_at: Optional[str]
    days_until_suspension: int
    notes: Optional[str]
    is_in_dunning: bool


# Request models for new endpoints
class ValidateDowngradeRequest(BaseModel):
    """Request to validate a downgrade."""
    target_tier: SKUTier = Field(..., description="Target tier to downgrade to")


class RequestDowngradeRequest(BaseModel):
    """Request to schedule a downgrade."""
    target_tier: SKUTier = Field(..., description="Target tier to downgrade to")
    force: bool = Field(False, description="Force downgrade even if limits exceeded")


class CalculateProrationRequest(BaseModel):
    """Request to calculate upgrade proration."""
    target_tier: SKUTier = Field(..., description="Target tier to upgrade to")
    target_intelligence: Optional[IntelligenceAddon] = Field(None, description="Target intelligence addon")


class ConvertTrialRequest(BaseModel):
    """Request to convert trial to paid."""
    tier: Optional[SKUTier] = Field(None, description="Target tier (defaults to current)")
    billing_cycle: Optional[str] = Field("monthly", description="Billing cycle")


class CancelSubscriptionRequest(BaseModel):
    """Request to cancel subscription."""
    reason: Optional[str] = Field(None, max_length=500, description="Cancellation reason")
    immediate: bool = Field(False, description="If true, cancel immediately; if false, cancel at period end")


# =============================================================================
# PRICING ENDPOINTS
# =============================================================================

@router.get(
    "/pricing",
    response_model=List[PricingTierResponse],
    summary="Get all tier pricing",
)
async def get_pricing():
    """
    Get pricing information for all tiers.
    
    Returns pricing in Nigerian Naira (₦) with monthly and annual options.
    """
    pricing_list = []
    
    for tier in [SKUTier.CORE, SKUTier.PROFESSIONAL, SKUTier.ENTERPRISE]:
        pricing = TIER_PRICING.get(tier)
        if not pricing:
            continue
        
        monthly = int(pricing.monthly_min)
        annual = int(pricing.annual_min)
        savings = (monthly * 12) - annual
        
        pricing_list.append(PricingTierResponse(
            tier=tier.value,
            name=pricing.name,
            tagline=pricing.tagline,
            monthly_amount=monthly,
            monthly_formatted=f"₦{monthly:,}",
            annual_amount=annual,
            annual_formatted=f"₦{annual:,}",
            annual_savings=savings,
            annual_savings_formatted=f"₦{savings:,}",
            base_users=pricing.base_users_included,
            per_user_amount=int(pricing.price_per_additional_user),
            per_user_formatted=f"₦{int(pricing.price_per_additional_user):,}",
        ))
    
    return pricing_list


@router.get(
    "/pricing/{tier}",
    response_model=PricingTierResponse,
    summary="Get pricing for specific tier",
)
async def get_tier_pricing(
    tier: SKUTier = Path(..., description="SKU tier"),
):
    """Get pricing information for a specific tier."""
    pricing = TIER_PRICING.get(tier)
    if not pricing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pricing not found for tier: {tier.value}",
        )
    
    monthly = int(pricing.monthly_min)
    annual = int(pricing.annual_min)
    savings = (monthly * 12) - annual
    
    return PricingTierResponse(
        tier=tier.value,
        name=pricing.name,
        tagline=pricing.tagline,
        monthly_amount=monthly,
        monthly_formatted=f"₦{monthly:,}",
        annual_amount=annual,
        annual_formatted=f"₦{annual:,}",
        annual_savings=savings,
        annual_savings_formatted=f"₦{savings:,}",
        base_users=pricing.base_users_included,
        per_user_amount=int(pricing.price_per_additional_user),
        per_user_formatted=f"₦{int(pricing.price_per_additional_user):,}",
    )


@router.get(
    "/calculate-price",
    summary="Calculate subscription price",
)
async def calculate_price(
    tier: SKUTier = Query(..., description="Target tier"),
    billing_cycle: str = Query("monthly", description="monthly or annual"),
    intelligence_addon: Optional[IntelligenceAddon] = Query(None),
    additional_users: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    Calculate total subscription price based on options.
    
    Useful for showing price before checkout.
    """
    service = BillingService(db)
    
    cycle = BillingCycle.ANNUAL if billing_cycle == "annual" else BillingCycle.MONTHLY
    
    amount = service.calculate_subscription_price(
        tier=tier,
        billing_cycle=cycle,
        intelligence_addon=intelligence_addon,
        additional_users=additional_users,
    )
    
    return {
        "tier": tier.value,
        "billing_cycle": billing_cycle,
        "intelligence_addon": intelligence_addon.value if intelligence_addon else None,
        "additional_users": additional_users,
        "amount_naira": amount,
        "amount_formatted": f"₦{amount:,}",
        "currency": "NGN",
    }


# =============================================================================
# SUBSCRIPTION ENDPOINTS
# =============================================================================

@router.get(
    "/subscription",
    response_model=SubscriptionResponse,
    summary="Get current subscription",
)
async def get_current_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the current user's organization subscription.
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not belong to an organization",
        )
    
    service = BillingService(db)
    info = await service.get_subscription_info(current_user.organization_id)
    
    if not info:
        # No TenantSKU record - fallback to organization's subscription_tier
        # instead of hardcoding "Core" (Issue #53 fix)
        result = await db.execute(
            select(Organization).where(Organization.id == current_user.organization_id)
        )
        org = result.scalar_one_or_none()
        
        # Determine fallback tier from organization table
        fallback_tier = SKUTier.CORE
        if org and org.subscription_tier:
            tier_str = str(org.subscription_tier).upper()
            if tier_str == "ENTERPRISE":
                fallback_tier = SKUTier.ENTERPRISE
            elif tier_str == "PROFESSIONAL":
                fallback_tier = SKUTier.PROFESSIONAL
        
        tier_display = {
            SKUTier.CORE: "Core",
            SKUTier.PROFESSIONAL: "Professional",
            SKUTier.ENTERPRISE: "Enterprise",
        }.get(fallback_tier, "Core")
        
        # Get pricing for the tier
        tier_pricing = TIER_PRICING.get(fallback_tier, TIER_PRICING[SKUTier.CORE])
        
        return SubscriptionResponse(
            tier=fallback_tier.value,
            tier_display=tier_display,
            intelligence_addon=None,
            billing_cycle="monthly",
            status="active" if fallback_tier != SKUTier.CORE else "trial",
            is_trial=fallback_tier == SKUTier.CORE,
            trial_days_remaining=14 if fallback_tier == SKUTier.CORE else None,
            current_period_start=None,
            current_period_end=None,
            next_billing_date=None,
            amount_naira=tier_pricing.get("monthly", 50000),
            amount_formatted=f"₦{tier_pricing.get('monthly', 50000):,}",
            tier_limits=_get_tier_limits_response(fallback_tier),
        )
    
    # Calculate trial days remaining
    trial_days = None
    if info.trial_ends_at:
        delta = info.trial_ends_at - datetime.utcnow()
        trial_days = max(0, delta.days)
    
    tier_display = {
        SKUTier.CORE: "Core",
        SKUTier.PROFESSIONAL: "Professional",
        SKUTier.ENTERPRISE: "Enterprise",
    }.get(info.tier, "Core")
    
    return SubscriptionResponse(
        tier=info.tier.value,
        tier_display=tier_display,
        intelligence_addon=info.intelligence_addon.value if info.intelligence_addon else None,
        billing_cycle=info.billing_cycle.value,
        status=info.status,
        is_trial=info.is_trial,
        trial_days_remaining=trial_days,
        current_period_start=info.current_period_start.isoformat() if info.current_period_start else None,
        current_period_end=info.current_period_end.isoformat() if info.current_period_end else None,
        next_billing_date=info.next_billing_date.isoformat() if info.next_billing_date else None,
        amount_naira=info.amount_naira,
        amount_formatted=f"₦{info.amount_naira:,}",
        cancel_at_period_end=info.cancel_at_period_end or False,
        cancellation_requested_at=info.cancellation_requested_at.isoformat() if info.cancellation_requested_at else None,
        cancellation_reason=info.cancellation_reason,
        scheduled_downgrade_tier=info.scheduled_downgrade_tier.value if info.scheduled_downgrade_tier else None,
        tier_limits=_get_tier_limits_response(info.tier),  # Issue #53: Include tier limits
    )


# =============================================================================
# USAGE VS LIMITS ENDPOINT (Issue #54)
# =============================================================================

class UsageMetricDetail(BaseModel):
    """Detail for a single usage metric."""
    metric: str = Field(..., description="Metric name")
    metric_display: str = Field(..., description="Human-readable metric name")
    current: int = Field(..., description="Current usage value")
    current_display: str = Field(..., description="Formatted current usage")
    limit: int = Field(..., description="Limit for this metric (-1 = unlimited)")
    limit_display: str = Field(..., description="Formatted limit")
    percentage: float = Field(..., description="Percentage of limit used (0-100+)")
    status: str = Field(..., description="Status: ok, warning, critical, exceeded")
    remaining: int = Field(..., description="Remaining until limit (-1 if unlimited)")
    remaining_display: str = Field(..., description="Formatted remaining")


class UsageVsLimitsResponse(BaseModel):
    """Response for current usage vs tier limits (Issue #54)."""
    organization_id: str
    tier: str
    tier_display: str
    billing_period_start: Optional[str]
    billing_period_end: Optional[str]
    metrics: List[UsageMetricDetail]
    overall_status: str = Field(..., description="Highest severity status across all metrics")
    alerts: List[str] = Field(default_factory=list, description="Active usage warnings")


@router.get(
    "/subscription/usage",
    response_model=UsageVsLimitsResponse,
    summary="Get current usage vs tier limits",
    description="Returns current usage compared to tier limits for all metered resources. "
                "Frontend can use this to display usage meters and warnings.",
)
async def get_usage_vs_limits(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current usage compared to tier limits (Issue #54).
    
    Returns usage data for all metered metrics including:
    - Transactions (monthly)
    - Users
    - Entities
    - Invoices (monthly)
    - Employees
    - API calls (hourly)
    - Storage
    
    Each metric includes current usage, limit, percentage, and status.
    Status values: ok (<80%), warning (80-99%), critical (100-119%), exceeded (120%+)
    """
    from app.services.metering_service import MeteringService
    from app.models.sku import TenantSKU
    
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not belong to an organization",
        )
    
    # Get tenant SKU info
    result = await db.execute(
        select(TenantSKU).where(TenantSKU.organization_id == current_user.organization_id)
    )
    tenant_sku = result.scalar_one_or_none()
    
    # Default to Core tier if no SKU assigned
    tier = tenant_sku.tier if tenant_sku else SKUTier.CORE
    limits = TIER_LIMITS_CONFIG.get(tier, TIER_LIMITS_CONFIG[SKUTier.CORE])
    
    tier_display = {
        SKUTier.CORE: "Core",
        SKUTier.PROFESSIONAL: "Professional", 
        SKUTier.ENTERPRISE: "Enterprise",
    }.get(tier, "Core")
    
    # Get current usage from metering service
    metering = MeteringService(db)
    usage_summary = await metering.get_usage_summary(current_user.organization_id)
    
    # Build metrics list
    metrics = []
    alerts = []
    highest_status = "ok"
    
    def calc_status(current: int, limit: int) -> tuple[str, float]:
        """Calculate status and percentage."""
        if limit == -1:  # Unlimited
            return "ok", 0.0
        if limit == 0:
            return "exceeded" if current > 0 else "ok", 100.0 if current > 0 else 0.0
        pct = (current / limit) * 100
        if pct >= 120:
            return "exceeded", pct
        elif pct >= 100:
            return "critical", pct
        elif pct >= 80:
            return "warning", pct
        return "ok", pct
    
    def update_highest(status: str):
        nonlocal highest_status
        priority = {"ok": 0, "warning": 1, "critical": 2, "exceeded": 3}
        if priority.get(status, 0) > priority.get(highest_status, 0):
            highest_status = status
    
    # Transactions
    txn_current = usage_summary.get("transactions", 0)
    txn_status, txn_pct = calc_status(txn_current, limits.max_transactions_monthly)
    update_highest(txn_status)
    if txn_status in ("warning", "critical", "exceeded"):
        alerts.append(f"Transaction usage is at {txn_pct:.0f}% of monthly limit")
    metrics.append(UsageMetricDetail(
        metric="transactions",
        metric_display="Transactions (monthly)",
        current=txn_current,
        current_display=f"{txn_current:,}",
        limit=limits.max_transactions_monthly,
        limit_display=_format_limit(limits.max_transactions_monthly),
        percentage=round(txn_pct, 1),
        status=txn_status,
        remaining=max(0, limits.max_transactions_monthly - txn_current) if limits.max_transactions_monthly != -1 else -1,
        remaining_display=_format_limit(max(0, limits.max_transactions_monthly - txn_current)) if limits.max_transactions_monthly != -1 else "Unlimited",
    ))
    
    # Users
    user_current = usage_summary.get("users", 1)
    user_status, user_pct = calc_status(user_current, limits.max_users)
    update_highest(user_status)
    if user_status in ("warning", "critical", "exceeded"):
        alerts.append(f"User count is at {user_pct:.0f}% of limit")
    metrics.append(UsageMetricDetail(
        metric="users",
        metric_display="Users",
        current=user_current,
        current_display=f"{user_current:,}",
        limit=limits.max_users,
        limit_display=_format_limit(limits.max_users),
        percentage=round(user_pct, 1),
        status=user_status,
        remaining=max(0, limits.max_users - user_current) if limits.max_users != -1 else -1,
        remaining_display=_format_limit(max(0, limits.max_users - user_current)) if limits.max_users != -1 else "Unlimited",
    ))
    
    # Entities
    entity_current = usage_summary.get("entities", 1)
    entity_status, entity_pct = calc_status(entity_current, limits.max_entities)
    update_highest(entity_status)
    if entity_status in ("warning", "critical", "exceeded"):
        alerts.append(f"Entity count is at {entity_pct:.0f}% of limit")
    metrics.append(UsageMetricDetail(
        metric="entities",
        metric_display="Entities/Companies",
        current=entity_current,
        current_display=f"{entity_current:,}",
        limit=limits.max_entities,
        limit_display=_format_limit(limits.max_entities),
        percentage=round(entity_pct, 1),
        status=entity_status,
        remaining=max(0, limits.max_entities - entity_current) if limits.max_entities != -1 else -1,
        remaining_display=_format_limit(max(0, limits.max_entities - entity_current)) if limits.max_entities != -1 else "Unlimited",
    ))
    
    # Invoices
    inv_current = usage_summary.get("invoices", 0)
    inv_status, inv_pct = calc_status(inv_current, limits.max_invoices_monthly)
    update_highest(inv_status)
    if inv_status in ("warning", "critical", "exceeded"):
        alerts.append(f"Invoice usage is at {inv_pct:.0f}% of monthly limit")
    metrics.append(UsageMetricDetail(
        metric="invoices",
        metric_display="Invoices (monthly)",
        current=inv_current,
        current_display=f"{inv_current:,}",
        limit=limits.max_invoices_monthly,
        limit_display=_format_limit(limits.max_invoices_monthly),
        percentage=round(inv_pct, 1),
        status=inv_status,
        remaining=max(0, limits.max_invoices_monthly - inv_current) if limits.max_invoices_monthly != -1 else -1,
        remaining_display=_format_limit(max(0, limits.max_invoices_monthly - inv_current)) if limits.max_invoices_monthly != -1 else "Unlimited",
    ))
    
    # Employees
    emp_current = usage_summary.get("employees", 0)
    emp_status, emp_pct = calc_status(emp_current, limits.max_employees)
    update_highest(emp_status)
    if emp_status in ("warning", "critical", "exceeded"):
        alerts.append(f"Employee count is at {emp_pct:.0f}% of limit")
    metrics.append(UsageMetricDetail(
        metric="employees",
        metric_display="Payroll Employees",
        current=emp_current,
        current_display=f"{emp_current:,}",
        limit=limits.max_employees,
        limit_display=_format_limit(limits.max_employees),
        percentage=round(emp_pct, 1),
        status=emp_status,
        remaining=max(0, limits.max_employees - emp_current) if limits.max_employees != -1 else -1,
        remaining_display=_format_limit(max(0, limits.max_employees - emp_current)) if limits.max_employees != -1 else "Unlimited",
    ))
    
    # Storage
    storage_current = usage_summary.get("storage_mb", 0)
    storage_status, storage_pct = calc_status(storage_current, limits.storage_limit_mb)
    update_highest(storage_status)
    if storage_status in ("warning", "critical", "exceeded"):
        alerts.append(f"Storage usage is at {storage_pct:.0f}% of limit")
    storage_gb = storage_current / 1000
    storage_display = f"{storage_gb:.1f} GB" if storage_gb >= 1 else f"{storage_current} MB"
    limit_gb = limits.storage_limit_mb / 1000
    limit_display = f"{int(limit_gb)} GB" if limit_gb >= 1 else f"{limits.storage_limit_mb} MB"
    metrics.append(UsageMetricDetail(
        metric="storage",
        metric_display="Storage",
        current=storage_current,
        current_display=storage_display,
        limit=limits.storage_limit_mb,
        limit_display=limit_display,
        percentage=round(storage_pct, 1),
        status=storage_status,
        remaining=max(0, limits.storage_limit_mb - storage_current),
        remaining_display=f"{max(0, limits.storage_limit_mb - storage_current) / 1000:.1f} GB",
    ))
    
    # API calls (current hour)
    api_current = usage_summary.get("api_calls_hour", 0)
    api_status, api_pct = calc_status(api_current, limits.api_calls_per_hour)
    update_highest(api_status)
    if api_status in ("warning", "critical", "exceeded"):
        alerts.append(f"API calls are at {api_pct:.0f}% of hourly limit")
    metrics.append(UsageMetricDetail(
        metric="api_calls",
        metric_display="API Calls (hourly)",
        current=api_current,
        current_display=f"{api_current:,}",
        limit=limits.api_calls_per_hour,
        limit_display=_format_limit(limits.api_calls_per_hour) + (" (read-only)" if limits.api_read_only and limits.api_calls_per_hour > 0 else ""),
        percentage=round(api_pct, 1),
        status=api_status,
        remaining=max(0, limits.api_calls_per_hour - api_current) if limits.api_calls_per_hour > 0 else 0,
        remaining_display=_format_limit(max(0, limits.api_calls_per_hour - api_current)) if limits.api_calls_per_hour > 0 else "No access",
    ))
    
    return UsageVsLimitsResponse(
        organization_id=str(current_user.organization_id),
        tier=tier.value,
        tier_display=tier_display,
        billing_period_start=tenant_sku.current_period_start.isoformat() if tenant_sku and tenant_sku.current_period_start else None,
        billing_period_end=tenant_sku.current_period_end.isoformat() if tenant_sku and tenant_sku.current_period_end else None,
        metrics=metrics,
        overall_status=highest_status,
        alerts=alerts,
    )


# =============================================================================
# PAYMENT HISTORY ENDPOINT
# =============================================================================

@router.get(
    "/payments",
    response_model=PaymentHistoryResponse,
    summary="Get payment history",
)
async def get_payment_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    status_filter: Optional[str] = Query(None, description="Filter by status"),
):
    """
    Get payment transaction history for the current user's organization.
    
    Returns a paginated list of payment transactions with details
    including amounts, status, payment method, and timestamps.
    
    Filter options:
    - status_filter: pending, processing, success, failed, cancelled, refunded
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not belong to an organization",
        )
    
    # Build query
    query = select(PaymentTransaction).where(
        PaymentTransaction.organization_id == current_user.organization_id
    )
    
    # Apply status filter if provided
    if status_filter:
        query = query.where(PaymentTransaction.status == status_filter)
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Apply ordering and pagination
    query = query.order_by(desc(PaymentTransaction.created_at))
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)
    
    # Execute query
    result = await db.execute(query)
    transactions = result.scalars().all()
    
    # Format response
    payments = []
    for tx in transactions:
        payments.append(PaymentTransactionResponse(
            id=str(tx.id),
            reference=tx.reference,
            status=tx.status,
            amount_naira=tx.amount_kobo // 100,
            amount_formatted=f"₦{tx.amount_kobo // 100:,}",
            currency=tx.currency or "NGN",
            tier=tx.tier,
            billing_cycle=tx.billing_cycle,
            payment_method=tx.payment_method or tx.channel,
            card_last4=tx.card_last4,
            card_brand=tx.card_brand,
            gateway_response=tx.gateway_response,
            created_at=tx.created_at.isoformat() if tx.created_at else None,
            paid_at=tx.paid_at.isoformat() if tx.paid_at else None,
        ))
    
    return PaymentHistoryResponse(
        payments=payments,
        total=total,
        page=page,
        per_page=per_page,
        has_more=(offset + len(transactions)) < total,
    )


@router.get(
    "/payments/{payment_id}",
    response_model=PaymentTransactionResponse,
    summary="Get payment details",
)
async def get_payment_detail(
    payment_id: UUID = Path(..., description="Payment transaction ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get details for a specific payment transaction.
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not belong to an organization",
        )
    
    # Get payment transaction
    result = await db.execute(
        select(PaymentTransaction).where(
            PaymentTransaction.id == payment_id,
            PaymentTransaction.organization_id == current_user.organization_id,
        )
    )
    tx = result.scalar_one_or_none()
    
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment transaction not found",
        )
    
    return PaymentTransactionResponse(
        id=str(tx.id),
        reference=tx.reference,
        status=tx.status,
        amount_naira=tx.amount_kobo // 100,
        amount_formatted=f"₦{tx.amount_kobo // 100:,}",
        currency=tx.currency or "NGN",
        tier=tx.tier,
        billing_cycle=tx.billing_cycle,
        payment_method=tx.payment_method or tx.channel,
        card_last4=tx.card_last4,
        card_brand=tx.card_brand,
        gateway_response=tx.gateway_response,
        created_at=tx.created_at.isoformat() if tx.created_at else None,
        paid_at=tx.paid_at.isoformat() if tx.paid_at else None,
    )


# =============================================================================
# PAYMENT ENDPOINTS
# =============================================================================

@router.post(
    "/checkout",
    response_model=PaymentIntentResponse,
    summary="Create checkout session",
)
async def create_checkout_session(
    request: CreatePaymentIntentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a payment intent and get Paystack checkout URL.
    
    The user should be redirected to the authorization_url to complete payment.
    After payment, Paystack will redirect to the callback_url.
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not belong to an organization",
        )
    
    if not current_user.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User email is required for payment",
        )
    
    service = BillingService(db)
    
    try:
        cycle = BillingCycle.ANNUAL if request.billing_cycle == "annual" else BillingCycle.MONTHLY
        
        # Calculate discount if code provided (#34)
        discount_percent = 0
        if request.discount_code:
            from app.services.advanced_billing_service import AdvancedBillingService
            advanced_service = AdvancedBillingService(db)
            discount_result = await advanced_service.discount_service.validate_discount_code(
                code=request.discount_code,
                tier=request.tier,
                billing_cycle=cycle,
            )
            if discount_result.get("valid"):
                discount_percent = discount_result.get("discount_percent", 0)
        
        intent = await service.create_payment_intent(
            organization_id=current_user.organization_id,
            tier=request.tier,
            billing_cycle=cycle,
            admin_email=current_user.email,
            intelligence_addon=request.intelligence_addon,
            additional_users=request.additional_users,
            callback_url=request.callback_url,
            is_upgrade=request.is_upgrade,
            apply_proration=request.is_upgrade,  # Apply proration for upgrades
            discount_percent=discount_percent,  # Apply discount (#34)
            currency=request.currency or "NGN",  # Multi-currency (#36)
        )
        
        return PaymentIntentResponse(
            id=intent.id,
            reference=intent.reference,
            amount_naira=intent.amount_naira,
            amount_formatted=f"₦{intent.amount_naira:,}",
            currency=intent.currency,
            status=intent.status.value,
            authorization_url=intent.authorization_url,
            tier=intent.tier.value,
            billing_cycle=intent.billing_cycle.value,
            expires_at=intent.expires_at.isoformat(),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/verify/{reference}",
    summary="Verify payment",
)
async def verify_payment(
    reference: str = Path(..., description="Payment reference"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Verify a payment after returning from Paystack checkout.
    
    This should be called after the customer completes payment
    and is redirected back to the application.
    """
    service = BillingService(db)
    
    result = await service.verify_and_process_payment(reference)
    
    return {
        "success": result.success,
        "reference": result.reference,
        "status": result.status.value,
        "message": result.message,
        "amount_naira": result.amount_naira,
        "amount_formatted": f"₦{result.amount_naira:,}",
        "paid_at": result.paid_at.isoformat() if result.paid_at else None,
    }


@router.post(
    "/cancel",
    summary="Cancel subscription",
)
async def cancel_subscription(
    request_body: Optional[CancelSubscriptionRequest] = None,
    reason: Optional[str] = Query(None, max_length=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Cancel the current subscription.
    
    If immediate=True, cancels immediately (no refund).
    If immediate=False (default), cancels at end of current billing period.
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not belong to an organization",
        )
    
    # Get reason and immediate flag from body or query param
    cancel_reason = reason
    immediate = False
    if request_body:
        cancel_reason = request_body.reason or reason
        immediate = request_body.immediate
    
    service = BillingService(db)
    
    result = await service.cancel_subscription(
        organization_id=current_user.organization_id,
        reason=cancel_reason,
        immediate=immediate,
    )
    
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("message", "Failed to cancel subscription"),
        )
    
    await db.commit()
    
    return result


# =============================================================================
# SUBSCRIPTION MANAGEMENT ENDPOINTS
# =============================================================================

@router.post(
    "/validate-downgrade",
    summary="Validate downgrade eligibility",
)
async def validate_downgrade(
    request_body: ValidateDowngradeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Validate if the organization can downgrade to a target tier.
    
    Checks current usage against target tier limits and returns:
    - Whether downgrade is possible
    - Which limits would be exceeded
    - Recommendations for reducing usage
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not belong to an organization",
        )
    
    service = BillingService(db)
    
    result = await service.validate_downgrade(
        organization_id=current_user.organization_id,
        target_tier=request_body.target_tier,
    )
    
    return result


@router.post(
    "/request-downgrade",
    summary="Request subscription downgrade",
)
async def request_downgrade(
    request_body: RequestDowngradeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Request a downgrade to a lower tier.
    
    The downgrade will take effect at the end of the current billing period.
    If force=True, schedules the downgrade even if current usage exceeds
    target tier limits (a warning will be included in the response).
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not belong to an organization",
        )
    
    service = BillingService(db)
    
    result = await service.request_downgrade(
        organization_id=current_user.organization_id,
        target_tier=request_body.target_tier,
        force=request_body.force,
    )
    
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("message", "Failed to schedule downgrade"),
        )
    
    await db.commit()
    
    return result


@router.post(
    "/reactivate",
    summary="Reactivate cancelled subscription",
)
async def reactivate_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Reactivate a subscription that was scheduled for cancellation.
    
    This can only be done before the current billing period ends.
    Cancels any pending cancellation or downgrade.
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not belong to an organization",
        )
    
    service = BillingService(db)
    
    result = await service.reactivate_subscription(
        organization_id=current_user.organization_id,
    )
    
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("message", "Failed to reactivate subscription"),
        )
    
    await db.commit()
    
    return result


@router.post(
    "/calculate-proration",
    summary="Calculate upgrade proration",
)
async def calculate_proration(
    request_body: CalculateProrationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Calculate the prorated cost for upgrading to a higher tier.
    
    Returns breakdown of:
    - Current subscription value
    - New subscription value
    - Prorated amount to pay now
    - Full amount for next billing cycle
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not belong to an organization",
        )
    
    service = BillingService(db)
    
    result = await service.calculate_upgrade_proration(
        organization_id=current_user.organization_id,
        new_tier=request_body.target_tier,
        new_intelligence=request_body.target_intelligence,
    )
    
    if result.get("error"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error"),
        )
    
    return result


@router.get(
    "/validate-trial-conversion",
    summary="Validate trial to paid conversion",
)
async def validate_trial_conversion(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Validate that the organization can convert from trial to paid.
    
    Checks:
    - Organization has an active trial
    - Trial hasn't expired
    - Valid payment method on file
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not belong to an organization",
        )
    
    service = BillingService(db)
    
    result = await service.validate_trial_to_paid_conversion(
        organization_id=current_user.organization_id,
    )
    
    return result


@router.post(
    "/convert-trial",
    summary="Convert trial to paid subscription",
)
async def convert_trial_to_paid(
    request_body: Optional[ConvertTrialRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Convert a trial subscription to a paid subscription.
    
    Charges the saved payment method and starts the paid subscription.
    Optionally specify a different tier or billing cycle.
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not belong to an organization",
        )
    
    service = BillingService(db)
    
    # Parse optional parameters
    tier = None
    billing_cycle = None
    if request_body:
        tier = request_body.tier
        if request_body.billing_cycle:
            billing_cycle = BillingCycle.ANNUAL if request_body.billing_cycle == "annual" else BillingCycle.MONTHLY
    
    result = await service.convert_trial_to_paid(
        organization_id=current_user.organization_id,
        tier=tier,
        billing_cycle=billing_cycle,
    )
    
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("message", "Failed to convert trial"),
        )
    
    await db.commit()
    
    return result


# =============================================================================
# WEBHOOK ENDPOINT
# =============================================================================

import hmac
import hashlib


def verify_paystack_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    Verify Paystack webhook signature using HMAC-SHA512.
    
    Paystack signs all webhook requests with your secret key.
    The signature is sent in the X-Paystack-Signature header.
    
    Args:
        payload: Raw request body bytes
        signature: X-Paystack-Signature header value
        secret: Paystack webhook secret key
        
    Returns:
        True if signature is valid, False otherwise
    """
    if not signature or not secret:
        return False
    
    # Calculate expected signature
    expected = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha512
    ).hexdigest()
    
    # Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(expected, signature)


@router.post(
    "/webhook/paystack",
    summary="Paystack webhook handler",
    include_in_schema=False,  # Hide from OpenAPI docs
)
async def paystack_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Handle Paystack webhook events.
    
    This endpoint receives payment notifications from Paystack.
    It should be configured in the Paystack dashboard.
    
    Security:
    - Verifies X-Paystack-Signature using HMAC-SHA512
    - Uses constant-time comparison to prevent timing attacks
    - Returns 400 for invalid signatures
    
    Supported events:
    - charge.success: Payment completed
    - charge.failed: Payment failed
    - subscription.create: New subscription
    - subscription.disable: Subscription cancelled
    - invoice.create: New invoice generated (subscription billing)
    - invoice.update: Invoice status changed
    - invoice.payment_failed: Invoice payment failed
    - transfer.success: Refund/payout completed
    - transfer.failed: Refund/payout failed
    - refund.processed: Refund completed
    """
    from app.config import settings
    
    # Get raw body for signature verification
    body = await request.body()
    signature = request.headers.get("X-Paystack-Signature", "")
    
    # Verify signature if webhook secret is configured
    webhook_secret = settings.paystack_webhook_secret
    if webhook_secret:
        if not verify_paystack_signature(body, signature, webhook_secret):
            logger.warning(f"Paystack webhook signature verification failed")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid webhook signature"
            )
        logger.debug("Paystack webhook signature verified successfully")
    else:
        # Log warning in production if no secret configured
        if settings.paystack_secret_key and settings.paystack_secret_key.startswith("sk_live_"):
            logger.warning(
                "SECURITY WARNING: Paystack webhook secret not configured. "
                "Set PAYSTACK_WEBHOOK_SECRET in .env for production!"
            )
    
    try:
        # Parse JSON payload
        payload = await request.json() if not body else __import__('json').loads(body)
        event_type = payload.get("event")
        
        if not event_type:
            logger.debug("Paystack webhook received with no event type")
            return {"status": "ignored", "reason": "No event type"}
        
        # Log event (without sensitive data)
        event_data = payload.get("data", {})
        logger.info(
            f"Paystack webhook received: event={event_type}, "
            f"reference={event_data.get('reference', 'N/A')}"
        )
        
        service = BillingService(db)
        result = await service.process_payment_webhook(event_type, payload)
        
        if result.get("handled"):
            await db.commit()
            logger.info(f"Paystack webhook processed successfully: {event_type}")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook processing error: {e}", exc_info=True)
        # Return 200 to acknowledge receipt (prevents retries for parsing errors)
        return {"status": "error", "message": str(e)}


# =============================================================================
# SUBSCRIPTION ACCESS ENDPOINT
# =============================================================================

@router.get(
    "/subscription-access",
    response_model=SubscriptionAccessResponse,
    summary="Check subscription access status",
)
async def check_subscription_access(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Check if the current organization has valid subscription access.
    
    Returns access status including:
    - has_access: Whether the organization can access the application
    - status: Current subscription status (active, trial, grace_period, suspended, etc.)
    - tier: Current subscription tier
    - message: Human-readable status message
    - days_remaining: Days until subscription expires or trial ends
    - grace_period_remaining: Days remaining in grace period (if applicable)
    - is_trial: Whether currently in trial period
    
    This endpoint is used by the frontend to display subscription status
    banners and handle access restrictions.
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not belong to an organization",
        )
    
    service = BillingService(db)
    access_info = await service.check_subscription_access(current_user.organization_id)
    
    return SubscriptionAccessResponse(
        has_access=access_info.get("has_access", False),
        status=access_info.get("status", "unknown"),
        tier=access_info.get("tier"),
        message=access_info.get("message", ""),
        days_remaining=access_info.get("days_remaining", 0),
        grace_period_remaining=access_info.get("grace_period_remaining", 0),
        is_trial=access_info.get("is_trial", False),
    )


# =============================================================================
# DUNNING STATUS ENDPOINT
# =============================================================================

@router.get(
    "/dunning-status",
    response_model=DunningStatusResponse,
    summary="Get dunning/payment failure status",
)
async def get_dunning_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the current dunning status for the organization.
    
    Dunning is the process of handling failed payments with escalating
    notifications and retry attempts.
    
    Returns:
    - is_in_dunning: Whether the organization has any failed payments
    - level: Current dunning level (initial, warning, urgent, final, suspended)
    - amount_naira: Amount that failed to process
    - retry_count: Number of payment retry attempts
    - days_until_suspension: Days remaining before account suspension
    
    If the organization is not in dunning, is_in_dunning will be False
    and other fields will have default/empty values.
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not belong to an organization",
        )
    
    dunning_service = DunningService(db)
    dunning_record = await dunning_service.get_dunning_status(current_user.organization_id)
    
    if not dunning_record:
        return DunningStatusResponse(
            organization_id=str(current_user.organization_id),
            level="none",
            amount_naira=0,
            amount_formatted="₦0",
            first_failure_at=None,
            last_retry_at=None,
            retry_count=0,
            next_retry_at=None,
            days_until_suspension=0,
            notes=None,
            is_in_dunning=False,
        )
    
    return DunningStatusResponse(
        organization_id=str(dunning_record.organization_id),
        level=dunning_record.level.value,
        amount_naira=dunning_record.amount_naira,
        amount_formatted=f"₦{dunning_record.amount_naira:,}",
        first_failure_at=dunning_record.first_failure_at.isoformat() if dunning_record.first_failure_at else None,
        last_retry_at=dunning_record.last_retry_at.isoformat() if dunning_record.last_retry_at else None,
        retry_count=dunning_record.retry_count,
        next_retry_at=dunning_record.next_retry_at.isoformat() if dunning_record.next_retry_at else None,
        days_until_suspension=dunning_record.days_until_suspension,
        notes=dunning_record.notes,
        is_in_dunning=True,
    )


# =============================================================================
# USER-FACING USAGE ENDPOINT
# =============================================================================

class UsageMetricResponse(BaseModel):
    """Response model for a single usage metric."""
    metric: str
    display_name: str
    current: int
    limit: int | str  # Can be "unlimited"
    percentage: float
    status: str  # ok, warning, critical, exceeded


class MyUsageResponse(BaseModel):
    """Response for current user's organization usage."""
    tier: str
    tier_display: str
    period_start: str
    period_end: str
    metrics: List[UsageMetricResponse]
    has_warnings: bool
    has_critical: bool


METRIC_DISPLAY_NAMES = {
    "transactions": "Monthly Transactions",
    "users": "Active Users",
    "entities": "Business Entities",
    "invoices": "Monthly Invoices",
    "api_calls": "API Calls (per hour)",
    "ocr_pages": "OCR Pages",
    "storage_mb": "Storage (MB)",
    "ml_inferences": "ML Inferences",
    "employees": "Employees",
}


@router.get(
    "/my-usage",
    response_model=MyUsageResponse,
    summary="Get current usage for my organization",
)
async def get_my_usage(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current usage metrics for the logged-in user's organization.
    
    Returns usage against tier limits with status indicators:
    - ok: Usage below 75% of limit
    - warning: Usage between 75-90% of limit
    - critical: Usage between 90-100% of limit
    - exceeded: Usage at or above 100% of limit
    
    This endpoint is for regular users, not admin-only.
    """
    from app.services.metering_service import MeteringService
    from app.models.sku import TenantSKU
    
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not belong to an organization",
        )
    
    # Get metering service and usage summary
    metering_service = MeteringService(db)
    usage_summary = await metering_service.get_usage_summary(current_user.organization_id)
    
    # Get tenant SKU for tier display name
    sku_result = await db.execute(
        select(TenantSKU).where(TenantSKU.organization_id == current_user.organization_id)
    )
    tenant_sku = sku_result.scalar_one_or_none()
    
    tier_display = "Core"
    if tenant_sku:
        tier_display = tenant_sku.tier.value.title()
    
    # Format period dates
    period = usage_summary.get("period", [])
    period_start = str(period[0]) if period else ""
    period_end = str(period[1]) if len(period) > 1 else ""
    
    # Build metrics list
    metrics = []
    has_warnings = False
    has_critical = False
    
    for metric_name, metric_data in usage_summary.get("metrics", {}).items():
        metric_status = metric_data.get("status", "ok")
        if metric_status == "warning":
            has_warnings = True
        elif metric_status in ("critical", "exceeded"):
            has_critical = True
        
        metrics.append(UsageMetricResponse(
            metric=metric_name,
            display_name=METRIC_DISPLAY_NAMES.get(metric_name, metric_name.replace("_", " ").title()),
            current=metric_data.get("current", 0),
            limit=metric_data.get("limit", "unlimited"),
            percentage=metric_data.get("percentage", 0),
            status=metric_status,
        ))
    
    return MyUsageResponse(
        tier=usage_summary.get("tier", "core"),
        tier_display=tier_display,
        period_start=period_start,
        period_end=period_end,
        metrics=metrics,
        has_warnings=has_warnings,
        has_critical=has_critical,
    )


# =============================================================================
# INVOICE PDF ENDPOINT
# =============================================================================

@router.get(
    "/invoice/{payment_id}/pdf",
    summary="Download invoice PDF",
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "PDF invoice file",
        }
    },
)
async def download_invoice_pdf(
    payment_id: UUID = Path(..., description="Payment transaction ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Download a PDF invoice for a specific payment transaction.
    
    The invoice includes:
    - Company and customer details
    - Line items with subscription details
    - VAT breakdown (7.5% Nigerian standard)
    - Payment reference and status
    - Bank details for wire transfers (if unpaid)
    
    Returns a PDF file that can be saved or printed.
    """
    import io
    
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not belong to an organization",
        )
    
    # Get the payment transaction
    result = await db.execute(
        select(PaymentTransaction).where(
            PaymentTransaction.id == payment_id,
            PaymentTransaction.organization_id == current_user.organization_id,
        )
    )
    transaction = result.scalar_one_or_none()
    
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment transaction not found",
        )
    
    # Generate PDF invoice
    pdf_service = InvoicePDFService(db)
    
    try:
        pdf_bytes = await pdf_service.generate_subscription_invoice(
            organization_id=current_user.organization_id,
            tier=transaction.tier or "professional",
            billing_cycle=transaction.billing_cycle or "monthly",
            amount_naira=transaction.amount_kobo // 100,
            payment_reference=transaction.reference,
            paid_at=transaction.paid_at,
        )
        
        # Create filename
        invoice_date = transaction.created_at.strftime("%Y%m%d") if transaction.created_at else "invoice"
        filename = f"Tekvwa_Invoice_{invoice_date}_{transaction.reference[:8].upper()}.pdf"
        
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(pdf_bytes)),
            },
        )
    except Exception as e:
        logger.error(f"Failed to generate invoice PDF: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate invoice PDF",
        )


# =============================================================================
# RESEND INVOICE EMAIL ENDPOINT
# =============================================================================

@router.post(
    "/invoice/{payment_id}/resend",
    summary="Resend invoice email",
)
async def resend_invoice_email(
    payment_id: UUID = Path(..., description="Payment transaction ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Resend the invoice email for a specific payment transaction.
    
    This will send a copy of the invoice to the organization's
    billing contact email.
    """
    from app.models.organization import Organization
    from app.models.sku import TenantSKU
    
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not belong to an organization",
        )
    
    # Get the payment transaction
    result = await db.execute(
        select(PaymentTransaction).where(
            PaymentTransaction.id == payment_id,
            PaymentTransaction.organization_id == current_user.organization_id,
        )
    )
    transaction = result.scalar_one_or_none()
    
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment transaction not found",
        )
    
    # Get organization name
    org_result = await db.execute(
        select(Organization).where(Organization.id == current_user.organization_id)
    )
    org = org_result.scalar_one_or_none()
    organization_name = org.name if org else "Customer"
    
    # Get next billing date from TenantSKU
    sku_result = await db.execute(
        select(TenantSKU).where(TenantSKU.organization_id == current_user.organization_id)
    )
    tenant_sku = sku_result.scalar_one_or_none()
    next_billing_date = tenant_sku.current_period_end if tenant_sku else None
    
    # Send invoice email using correct method signature
    email_service = BillingEmailService(db)
    
    try:
        await email_service.send_payment_success(
            email=current_user.email,
            organization_name=organization_name,
            tier=transaction.tier or "professional",
            amount_naira=transaction.amount_kobo // 100,
            reference=transaction.reference,
            payment_date=transaction.paid_at or transaction.created_at,
            next_billing_date=next_billing_date,
        )
        
        return {"message": "Invoice email sent successfully", "sent_to": current_user.email}
    except Exception as e:
        logger.error(f"Failed to send invoice email: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send invoice email",
        )

