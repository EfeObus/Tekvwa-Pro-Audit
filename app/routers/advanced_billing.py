"""
Tekvwa Pro Audit - Advanced Billing Router

API endpoints for Issues #30-36:
- #30: Usage report generation
- #31: Billing cycle alignment
- #32: Subscription pause/resume
- #33: Service credit system
- #34: Discount/referral code system
- #35: Volume discount logic
- #36: Multi-currency support
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, get_current_platform_admin
from app.models.user import User
from app.models.sku import SKUTier
from app.services.advanced_billing_service import (
    AdvancedBillingService,
    CurrencyService,
    BillingCycleService,
    SubscriptionPauseService,
    ServiceCreditService,
    DiscountCodeService,
    VolumeDiscountService,
    UsageReportService,
    Currency,
    CreditType,
    CURRENCY_SYMBOLS,
    CURRENCY_NAMES,
    format_currency,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/billing/advanced", tags=["Advanced Billing"])


# =============================================================================
# SCHEMAS
# =============================================================================

# Issue #31: Billing Cycle Alignment
class AlignBillingCycleRequest(BaseModel):
    anchor_day: Optional[int] = Field(None, ge=1, le=28, description="Day of month for billing (1-28)")
    align_to_calendar: bool = Field(False, description="Align to 1st of month")


# Issue #32: Pause/Resume
class PauseSubscriptionRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)
    pause_days: int = Field(30, ge=1, le=90, description="Days to pause (max 90)")


# Issue #33: Service Credits
class CreateCreditRequest(BaseModel):
    credit_type: str = Field(..., description="sla_breach, goodwill, promotion")
    amount: int = Field(..., ge=1, description="Amount in Naira")
    description: str = Field(..., min_length=5, max_length=500)
    currency: str = Field("NGN", pattern="^(NGN|USD|EUR|GBP)$")
    incident_id: Optional[str] = None
    incident_date: Optional[datetime] = None
    downtime_minutes: Optional[int] = None


class ApproveCreditRequest(BaseModel):
    admin_notes: Optional[str] = None


# Issue #34: Discount Codes
class ValidateDiscountRequest(BaseModel):
    code: str = Field(..., min_length=3, max_length=50)
    tier: str = Field("core", pattern="^(core|professional|enterprise)$")
    billing_cycle: str = Field("monthly", pattern="^(monthly|annual)$")


class ApplyDiscountRequest(BaseModel):
    code: str = Field(..., min_length=3, max_length=50)
    original_amount: int = Field(..., ge=0)
    payment_reference: Optional[str] = None


class CreateDiscountCodeRequest(BaseModel):
    code: str = Field(..., min_length=3, max_length=50)
    name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = None
    discount_type: str = Field(..., pattern="^(percentage|fixed_amount|free_months)$")
    discount_value: float = Field(..., ge=0)
    max_discount_ngn: Optional[int] = None
    applies_to_tiers: Optional[List[str]] = None
    applies_to_billing_cycles: Optional[List[str]] = None
    first_payment_only: bool = True
    max_uses_total: Optional[int] = None
    valid_until: Optional[datetime] = None


# Issue #35: Volume Discounts
class CalculateVolumeDiscountRequest(BaseModel):
    base_price: int = Field(..., ge=0)
    user_count: int = Field(1, ge=1)
    entity_count: int = Field(1, ge=1)
    commitment_months: int = Field(1, ge=1)
    tier: str = Field("core", pattern="^(core|professional|enterprise)$")
    currency: str = Field("NGN", pattern="^(NGN|USD|EUR|GBP)$")


# Issue #36: Multi-Currency
class UpdateExchangeRateRequest(BaseModel):
    from_currency: str = Field(..., pattern="^(NGN|USD|EUR|GBP)$")
    to_currency: str = Field(..., pattern="^(NGN|USD|EUR|GBP)$")
    rate: float = Field(..., gt=0)


class SetPreferredCurrencyRequest(BaseModel):
    currency: str = Field(..., pattern="^(NGN|USD|EUR|GBP)$")


# Issue #30: Usage Reports
class GenerateReportRequest(BaseModel):
    report_type: str = Field("usage_summary", pattern="^(usage_summary|detailed_usage|billing_history)$")
    format: str = Field("csv", pattern="^(csv|pdf|json)$")
    months: int = Field(1, ge=1, le=24)


class ScheduleReportRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    frequency: str = Field(..., pattern="^(daily|weekly|monthly|quarterly)$")
    report_type: str = Field("usage_summary")
    format: str = Field("csv", pattern="^(csv|pdf)$")
    email_recipients: List[str] = Field(default_factory=list)
    day_of_week: Optional[int] = Field(None, ge=0, le=6)
    day_of_month: Optional[int] = Field(None, ge=1, le=28)


# Combined Price Calculation
class CalculatePriceRequest(BaseModel):
    tier: str = Field("core", pattern="^(core|professional|enterprise)$")
    billing_cycle: str = Field("monthly", pattern="^(monthly|annual)$")
    currency: str = Field("NGN", pattern="^(NGN|USD|EUR|GBP)$")
    user_count: int = Field(1, ge=1)
    entity_count: int = Field(1, ge=1)
    commitment_months: int = Field(1, ge=1)
    discount_code: Optional[str] = None
    apply_credits: bool = True


# =============================================================================
# ISSUE #36: MULTI-CURRENCY ENDPOINTS
# =============================================================================

@router.get("/currencies")
async def get_supported_currencies():
    """Get list of supported currencies with symbols and names."""
    return {
        "currencies": [
            {
                "code": c.value,
                "symbol": CURRENCY_SYMBOLS[c.value],
                "name": CURRENCY_NAMES[c.value],
            }
            for c in Currency
        ]
    }


@router.get("/pricing/all-currencies")
async def get_pricing_all_currencies(
    tier: str = Query("core", pattern="^(core|professional|enterprise)$"),
    db: AsyncSession = Depends(get_db),
):
    """Get pricing for a tier in all supported currencies."""
    service = CurrencyService(db)
    tier_enum = SKUTier(tier)
    
    prices = await service.get_all_currency_prices(tier_enum)
    return {"tier": tier, "pricing": prices}


@router.get("/exchange-rates")
async def get_exchange_rates(
    db: AsyncSession = Depends(get_db),
):
    """Get current billing exchange rates."""
    from sqlalchemy import select
    from app.models.sku import ExchangeRate
    
    result = await db.execute(
        select(ExchangeRate)
        .where(ExchangeRate.is_billing_rate == True)
    )
    rates = list(result.scalars().all())
    
    return {
        "rates": [
            {
                "from": r.from_currency,
                "to": r.to_currency,
                "rate": float(r.rate),
                "date": r.rate_date.isoformat(),
            }
            for r in rates
        ]
    }


@router.put("/exchange-rates")
async def update_exchange_rate(
    request: UpdateExchangeRateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_platform_admin),
):
    """Update a billing exchange rate (admin only)."""
    from decimal import Decimal
    
    service = CurrencyService(db)
    rate = await service.update_billing_rate(
        request.from_currency,
        request.to_currency,
        Decimal(str(request.rate)),
    )
    await db.commit()
    
    return {
        "success": True,
        "from": rate.from_currency,
        "to": rate.to_currency,
        "rate": float(rate.rate),
    }


@router.get("/currency/preference")
async def get_preferred_currency(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get preferred billing currency for current organization."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User not in an organization")
    
    from sqlalchemy import select
    from app.models.sku import TenantSKU
    
    result = await db.execute(
        select(TenantSKU)
        .where(TenantSKU.organization_id == current_user.organization_id)
    )
    tenant_sku = result.scalar_one_or_none()
    
    if not tenant_sku:
        return {"currency": "NGN", "source": "default"}
    
    return {
        "currency": tenant_sku.preferred_currency or "NGN",
        "source": "subscription"
    }


@router.put("/currency/preference")
async def set_preferred_currency(
    request: SetPreferredCurrencyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Set preferred billing currency for current organization."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User not in an organization")
    
    from sqlalchemy import select
    from app.models.sku import TenantSKU
    
    result = await db.execute(
        select(TenantSKU)
        .where(TenantSKU.organization_id == current_user.organization_id)
    )
    tenant_sku = result.scalar_one_or_none()
    
    if not tenant_sku:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    tenant_sku.preferred_currency = request.currency
    await db.commit()
    
    return {
        "success": True,
        "currency": request.currency,
        "message": f"Billing currency set to {CURRENCY_NAMES[request.currency]}"
    }


# =============================================================================
# ISSUE #31: BILLING CYCLE ALIGNMENT ENDPOINTS
# =============================================================================

@router.put("/billing-cycle/align")
async def align_billing_cycle(
    request: AlignBillingCycleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Configure billing cycle alignment for subscription."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User not in an organization")
    
    service = BillingCycleService(db)
    result = await service.align_subscription(
        current_user.organization_id,
        request.anchor_day,
        request.align_to_calendar,
    )
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    await db.commit()
    return result


@router.get("/billing-cycle/proration")
async def calculate_proration(
    tier: str = Query("core", pattern="^(core|professional|enterprise)$"),
    billing_cycle: str = Query("monthly", pattern="^(monthly|annual)$"),
    currency: str = Query("NGN", pattern="^(NGN|USD|EUR|GBP)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Calculate proration for starting mid-billing-cycle."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User not in an organization")
    
    from sqlalchemy import select
    from app.models.sku import TenantSKU
    
    result = await db.execute(
        select(TenantSKU)
        .where(TenantSKU.organization_id == current_user.organization_id)
    )
    tenant_sku = result.scalar_one_or_none()
    
    currency_service = CurrencyService(db)
    billing_service = BillingCycleService(db)
    
    # Get price for the tier
    tier_enum = SKUTier(tier)
    full_price = await currency_service.get_pricing_for_currency(tier_enum, currency, billing_cycle)
    
    if not full_price:
        raise HTTPException(status_code=400, detail="Could not determine pricing")
    
    today = date.today()
    
    # Calculate aligned period
    anchor_day = tenant_sku.billing_anchor_day if tenant_sku else None
    align_to_cal = tenant_sku.align_to_calendar_month if tenant_sku else False
    
    period_start, period_end = billing_service.calculate_aligned_period(
        today, anchor_day, align_to_cal, billing_cycle
    )
    
    proration = billing_service.calculate_proration(
        full_price, today, period_end, period_start
    )
    
    proration["currency"] = currency
    proration["symbol"] = CURRENCY_SYMBOLS.get(currency, currency)
    proration["full_price_formatted"] = format_currency(full_price, currency)
    proration["prorated_price_formatted"] = format_currency(proration["prorated_price"], currency)
    
    return proration


# =============================================================================
# ISSUE #32: PAUSE/RESUME ENDPOINTS
# =============================================================================

@router.post("/subscription/pause")
async def pause_subscription(
    request: PauseSubscriptionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pause subscription for up to 90 days."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User not in an organization")
    
    service = SubscriptionPauseService(db)
    
    pause_until = datetime.utcnow() + timedelta(days=request.pause_days)
    
    result = await service.pause_subscription(
        current_user.organization_id,
        request.reason,
        pause_until,
    )
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to pause"))
    
    await db.commit()
    return result


@router.post("/subscription/resume")
async def resume_subscription(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Resume a paused subscription."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User not in an organization")
    
    service = SubscriptionPauseService(db)
    
    result = await service.resume_subscription(current_user.organization_id)
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to resume"))
    
    await db.commit()
    return result


@router.get("/subscription/pause-status")
async def get_pause_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get subscription pause status."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User not in an organization")
    
    service = SubscriptionPauseService(db)
    return await service.get_pause_status(current_user.organization_id)


# =============================================================================
# ISSUE #33: SERVICE CREDITS ENDPOINTS
# =============================================================================

@router.get("/credits")
async def get_credit_balance(
    currency: str = Query("NGN", pattern="^(NGN|USD|EUR|GBP)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get available credit balance for current organization."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User not in an organization")
    
    service = ServiceCreditService(db)
    return await service.get_credit_balance(current_user.organization_id, currency)


@router.post("/credits")
async def create_credit(
    request: CreateCreditRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_platform_admin),
):
    """Create a service credit (admin only)."""
    # Parse organization_id from query or request
    from fastapi import Query as FastAPIQuery
    
    raise HTTPException(
        status_code=400,
        detail="Use /credits/{organization_id} endpoint to create credits"
    )


@router.post("/credits/{organization_id}")
async def create_credit_for_org(
    organization_id: UUID,
    request: CreateCreditRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_platform_admin),
):
    """Create a service credit for an organization (admin only)."""
    from decimal import Decimal
    
    service = ServiceCreditService(db)
    
    if request.credit_type == "sla_breach" and request.incident_id:
        # Get tenant's subscription price for SLA calculation
        from sqlalchemy import select
        from app.models.sku import TenantSKU
        
        result = await db.execute(
            select(TenantSKU)
            .where(TenantSKU.organization_id == organization_id)
        )
        tenant_sku = result.scalar_one_or_none()
        
        if not tenant_sku:
            raise HTTPException(status_code=404, detail="Organization subscription not found")
        
        credit = await service.create_sla_credit(
            organization_id=organization_id,
            incident_id=request.incident_id,
            incident_date=request.incident_date or datetime.utcnow(),
            downtime_minutes=request.downtime_minutes or 0,
            total_minutes=43200,  # Monthly minutes
            monthly_subscription_price=request.amount,
            description=request.description,
            currency=request.currency,
        )
    else:
        credit = await service.create_goodwill_credit(
            organization_id=organization_id,
            amount=request.amount,
            description=request.description,
            currency=request.currency,
            auto_approve=(current_user.role == "platform_admin"),
        )
    
    await db.commit()
    
    return {
        "success": True,
        "credit_id": str(credit.id),
        "amount": credit.amount_ngn,
        "currency": credit.currency,
        "status": credit.status,
    }


@router.put("/credits/{credit_id}/approve")
async def approve_credit(
    credit_id: UUID,
    request: ApproveCreditRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_platform_admin),
):
    """Approve a pending credit (admin only)."""
    service = ServiceCreditService(db)
    
    result = await service.approve_credit(credit_id, current_user.id, request.admin_notes)
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to approve"))
    
    await db.commit()
    return result


# =============================================================================
# ISSUE #34: DISCOUNT CODE ENDPOINTS
# =============================================================================

@router.get("/discount/{code}/validate")
async def validate_discount_code_get(
    code: str,
    tier: str = Query("core", pattern="^(core|professional|enterprise)$"),
    billing_cycle: str = Query("monthly", pattern="^(monthly|annual)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Validate a discount code (GET method for simpler frontend calls)."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User not in an organization")
    
    service = DiscountCodeService(db)
    tier_enum = SKUTier(tier)
    
    return await service.validate_code(
        code,
        current_user.organization_id,
        tier_enum,
        billing_cycle,
    )


@router.post("/discount/validate")
async def validate_discount_code(
    request: ValidateDiscountRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Validate a discount code."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User not in an organization")
    
    service = DiscountCodeService(db)
    tier_enum = SKUTier(request.tier)
    
    return await service.validate_code(
        request.code,
        current_user.organization_id,
        tier_enum,
        request.billing_cycle,
    )


@router.post("/discount/apply")
async def apply_discount_code(
    request: ApplyDiscountRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Apply a discount code to a payment."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User not in an organization")
    
    service = DiscountCodeService(db)
    
    result = await service.apply_code(
        request.code,
        current_user.organization_id,
        current_user.id,
        request.original_amount,
        request.payment_reference,
    )
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to apply code"))
    
    await db.commit()
    return result


@router.get("/discount/my-referral-code")
async def get_my_referral_code(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get or create referral code for current organization."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User not in an organization")
    
    service = DiscountCodeService(db)
    
    code = await service.get_organization_referral_code(current_user.organization_id)
    await db.commit()
    
    if not code:
        raise HTTPException(status_code=500, detail="Failed to generate referral code")
    
    return {
        "code": code.code,
        "discount_percentage": float(code.discount_value),
        "reward_type": code.referrer_reward_type,
        "reward_value": float(code.referrer_reward_value) if code.referrer_reward_value else 0,
        "total_uses": code.current_uses,
    }


@router.post("/discount/codes")
async def create_discount_code(
    request: CreateDiscountCodeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_platform_admin),
):
    """Create a new discount code (admin only)."""
    from decimal import Decimal
    from app.models.sku import DiscountCode
    
    code = DiscountCode(
        code=request.code.upper(),
        name=request.name,
        description=request.description,
        discount_type=request.discount_type,
        discount_value=Decimal(str(request.discount_value)),
        max_discount_ngn=request.max_discount_ngn,
        applies_to_tiers=request.applies_to_tiers,
        applies_to_billing_cycles=request.applies_to_billing_cycles,
        first_payment_only=request.first_payment_only,
        max_uses_total=request.max_uses_total,
        valid_from=datetime.utcnow(),
        valid_until=request.valid_until,
        is_active=True,
        created_by_id=current_user.id,
    )
    
    db.add(code)
    await db.commit()
    
    return {
        "success": True,
        "code": code.code,
        "id": str(code.id),
    }


@router.get("/discount/codes")
async def list_discount_codes(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_platform_admin),
):
    """List all discount codes (admin only)."""
    from sqlalchemy import select
    from app.models.sku import DiscountCode
    
    query = select(DiscountCode)
    if active_only:
        query = query.where(DiscountCode.is_active == True)
    query = query.order_by(DiscountCode.created_at.desc())
    
    result = await db.execute(query)
    codes = list(result.scalars().all())
    
    return {
        "codes": [
            {
                "id": str(c.id),
                "code": c.code,
                "name": c.name,
                "discount_type": c.discount_type,
                "discount_value": float(c.discount_value),
                "current_uses": c.current_uses,
                "max_uses_total": c.max_uses_total,
                "is_active": c.is_active,
                "is_referral_code": c.is_referral_code,
                "valid_until": c.valid_until.isoformat() if c.valid_until else None,
            }
            for c in codes
        ]
    }


# =============================================================================
# ISSUE #35: VOLUME DISCOUNT ENDPOINTS
# =============================================================================

@router.post("/volume-discount/calculate")
async def calculate_volume_discount(
    request: CalculateVolumeDiscountRequest,
    db: AsyncSession = Depends(get_db),
):
    """Calculate volume discounts for given parameters."""
    service = VolumeDiscountService(db)
    tier_enum = SKUTier(request.tier)
    
    result = await service.calculate_volume_discount(
        request.base_price,
        request.user_count,
        request.entity_count,
        request.commitment_months,
        tier_enum,
        request.currency,
    )
    
    result["currency"] = request.currency
    result["symbol"] = CURRENCY_SYMBOLS.get(request.currency, request.currency)
    result["base_price_formatted"] = format_currency(request.base_price, request.currency)
    result["final_price_formatted"] = format_currency(result["final_price"], request.currency)
    
    return result


@router.get("/volume-discount/rules")
async def list_volume_discount_rules(
    db: AsyncSession = Depends(get_db),
):
    """List all active volume discount rules."""
    from sqlalchemy import select
    from app.models.sku import VolumeDiscountRule
    
    today = date.today()
    
    result = await db.execute(
        select(VolumeDiscountRule)
        .where(
            VolumeDiscountRule.is_active == True,
            VolumeDiscountRule.effective_from <= today,
        )
        .order_by(VolumeDiscountRule.priority.desc())
    )
    rules = list(result.scalars().all())
    
    return {
        "rules": [
            {
                "id": str(r.id),
                "name": r.name,
                "description": r.description,
                "rule_type": r.rule_type,
                "min_users": r.min_users,
                "max_users": r.max_users,
                "min_entities": r.min_entities,
                "min_commitment_months": r.min_commitment_months,
                "discount_percentage": float(r.discount_percentage),
                "applies_to_tier": r.applies_to_tier,
                "stackable": r.stackable,
            }
            for r in rules
        ]
    }


# =============================================================================
# ISSUE #30: USAGE REPORT ENDPOINTS
# =============================================================================

@router.post("/reports/generate")
async def generate_usage_report(
    request: GenerateReportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a usage report for download."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User not in an organization")
    
    service = UsageReportService(db)
    
    end_date = date.today()
    start_date = end_date - timedelta(days=request.months * 30)
    
    if request.format == "csv":
        filename, content = await service.generate_usage_report_csv(
            current_user.organization_id,
            start_date,
            end_date,
        )
        
        # Save to history
        await service.save_report_history(
            current_user.organization_id,
            request.report_type,
            request.format,
            start_date,
            end_date,
            generated_by_id=current_user.id,
            file_size=len(content),
        )
        await db.commit()
        
        return StreamingResponse(
            iter([content]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    
    elif request.format == "pdf":
        # Issue #30: PDF export support
        filename, content = await service.generate_usage_report_pdf(
            current_user.organization_id,
            start_date,
            end_date,
        )
        
        # Save to history
        await service.save_report_history(
            current_user.organization_id,
            request.report_type,
            request.format,
            start_date,
            end_date,
            generated_by_id=current_user.id,
            file_size=len(content),
        )
        await db.commit()
        
        return StreamingResponse(
            iter([content]),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    
    elif request.format == "json":
        summary = await service.generate_usage_summary(
            current_user.organization_id,
            request.months,
        )
        
        # Save to history
        await service.save_report_history(
            current_user.organization_id,
            request.report_type,
            request.format,
            start_date,
            end_date,
            generated_by_id=current_user.id,
        )
        await db.commit()
        
        return summary
    
    else:
        raise HTTPException(status_code=400, detail=f"Format {request.format} not supported. Use csv, pdf, or json.")


@router.get("/reports/summary")
async def get_usage_summary(
    months: int = Query(12, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get usage summary with historical data and trends."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User not in an organization")
    
    service = UsageReportService(db)
    return await service.generate_usage_summary(current_user.organization_id, months)


@router.get("/reports/history")
async def get_report_history(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get history of generated reports."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User not in an organization")
    
    service = UsageReportService(db)
    reports = await service.get_report_history(current_user.organization_id, limit)
    
    return {
        "reports": [
            {
                "id": str(r.id),
                "report_type": r.report_type,
                "format": r.format,
                "period_start": r.period_start.isoformat(),
                "period_end": r.period_end.isoformat(),
                "created_at": r.created_at.isoformat(),
                "download_count": r.download_count,
                "file_size_bytes": r.file_size_bytes,
            }
            for r in reports
        ]
    }


@router.post("/reports/schedule")
async def schedule_report(
    request: ScheduleReportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Schedule a recurring usage report."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User not in an organization")
    
    from app.models.sku import ScheduledUsageReport
    
    # Calculate next run time
    now = datetime.utcnow()
    if request.frequency == "daily":
        next_run = now.replace(hour=6, minute=0, second=0, microsecond=0) + timedelta(days=1)
    elif request.frequency == "weekly":
        days_ahead = (request.day_of_week or 0) - now.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        next_run = now.replace(hour=6, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
    elif request.frequency == "monthly":
        day = request.day_of_month or 1
        next_month = now.month + 1 if now.day >= day else now.month
        year = now.year + 1 if next_month > 12 else now.year
        next_month = 1 if next_month > 12 else next_month
        next_run = datetime(year, next_month, min(day, 28), 6, 0, 0)
    else:
        next_run = now + timedelta(days=90)
    
    scheduled = ScheduledUsageReport(
        organization_id=current_user.organization_id,
        created_by_id=current_user.id,
        name=request.name,
        frequency=request.frequency,
        day_of_week=request.day_of_week,
        day_of_month=request.day_of_month,
        report_type=request.report_type,
        format=request.format,
        delivery_method="email" if request.email_recipients else "download",
        email_recipients=request.email_recipients,
        is_active=True,
        next_run_at=next_run,
    )
    
    db.add(scheduled)
    await db.commit()
    
    return {
        "success": True,
        "id": str(scheduled.id),
        "name": scheduled.name,
        "frequency": scheduled.frequency,
        "next_run_at": scheduled.next_run_at.isoformat(),
    }


# =============================================================================
# COMBINED PRICE CALCULATION ENDPOINT
# =============================================================================

@router.post("/calculate-price")
async def calculate_final_price(
    request: CalculatePriceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Calculate the final price including all discounts and credits.
    
    This is the main endpoint for checkout pricing that combines:
    - Base tier pricing
    - Multi-currency support
    - Volume discounts
    - Discount codes
    - Service credits
    """
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User not in an organization")
    
    service = AdvancedBillingService(db)
    tier_enum = SKUTier(request.tier)
    
    result = await service.calculate_final_price(
        organization_id=current_user.organization_id,
        tier=tier_enum,
        billing_cycle=request.billing_cycle,
        currency=request.currency,
        user_count=request.user_count,
        entity_count=request.entity_count,
        commitment_months=request.commitment_months,
        discount_code=request.discount_code,
        apply_credits=request.apply_credits,
    )
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    # Add formatted prices
    result["base_price_formatted"] = format_currency(result["base_price"], request.currency)
    result["final_price_formatted"] = format_currency(result["final_price"], request.currency)
    result["total_savings_formatted"] = format_currency(result["total_savings"], request.currency)
    
    return result
