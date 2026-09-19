"""
Tekvwa Pro Audit - Advanced Billing Features Service

Implements Issues #30-36:
- #30: Usage report generation
- #31: Billing cycle alignment
- #32: Subscription pause/resume
- #33: Service credit system
- #34: Discount/referral code system
- #35: Volume discount logic
- #36: Multi-currency support
"""

import csv
import io
import logging
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Any, Tuple
from uuid import UUID
from enum import Enum

from sqlalchemy import select, and_, or_, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sku import (
    TenantSKU, SKUTier, SKUPricing, UsageRecord,
    ServiceCredit, DiscountCode, DiscountCodeUsage,
    VolumeDiscountRule, ExchangeRate,
    ScheduledUsageReport, UsageReportHistory,
)

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================

class Currency(str, Enum):
    """Supported currencies."""
    NGN = "NGN"
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"


class CreditType(str, Enum):
    """Service credit types."""
    SLA_BREACH = "sla_breach"
    GOODWILL = "goodwill"
    PROMOTION = "promotion"
    REFERRAL_REWARD = "referral_reward"


class CreditStatus(str, Enum):
    """Service credit statuses."""
    PENDING = "pending"
    APPROVED = "approved"
    APPLIED = "applied"
    EXPIRED = "expired"
    REJECTED = "rejected"


class DiscountType(str, Enum):
    """Discount types."""
    PERCENTAGE = "percentage"
    FIXED_AMOUNT = "fixed_amount"
    FREE_MONTHS = "free_months"


# =============================================================================
# CURRENCY SYMBOLS AND FORMATTING
# =============================================================================

CURRENCY_SYMBOLS = {
    "NGN": "₦",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
}

CURRENCY_NAMES = {
    "NGN": "Nigerian Naira",
    "USD": "US Dollar",
    "EUR": "Euro",
    "GBP": "British Pound",
}


def format_currency(amount: int, currency: str = "NGN") -> str:
    """Format amount with currency symbol."""
    symbol = CURRENCY_SYMBOLS.get(currency, currency)
    return f"{symbol}{amount:,}"


def format_currency_decimal(amount: Decimal, currency: str = "NGN") -> str:
    """Format decimal amount with currency symbol."""
    symbol = CURRENCY_SYMBOLS.get(currency, currency)
    return f"{symbol}{amount:,.2f}"


# =============================================================================
# ISSUE #36: MULTI-CURRENCY SERVICE
# =============================================================================

class CurrencyService:
    """
    Handle multi-currency operations including exchange rates and pricing.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_billing_rate(
        self,
        from_currency: str,
        to_currency: str,
    ) -> Optional[Decimal]:
        """
        Get the billing exchange rate for a currency pair.
        Returns rate where 1 from_currency = rate to_currency.
        """
        if from_currency == to_currency:
            return Decimal("1.0")
        
        result = await self.db.execute(
            select(ExchangeRate)
            .where(
                and_(
                    ExchangeRate.from_currency == from_currency,
                    ExchangeRate.to_currency == to_currency,
                    ExchangeRate.is_billing_rate == True,
                )
            )
        )
        rate = result.scalar_one_or_none()
        
        if rate:
            return rate.rate
        
        # Try reverse rate
        result = await self.db.execute(
            select(ExchangeRate)
            .where(
                and_(
                    ExchangeRate.from_currency == to_currency,
                    ExchangeRate.to_currency == from_currency,
                    ExchangeRate.is_billing_rate == True,
                )
            )
        )
        reverse_rate = result.scalar_one_or_none()
        
        if reverse_rate:
            return Decimal("1.0") / reverse_rate.rate
        
        return None
    
    async def convert_amount(
        self,
        amount: int,
        from_currency: str,
        to_currency: str,
    ) -> Optional[int]:
        """Convert amount from one currency to another."""
        if from_currency == to_currency:
            return amount
        
        rate = await self.get_billing_rate(from_currency, to_currency)
        if rate is None:
            return None
        
        converted = Decimal(amount) * rate
        return int(converted.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    
    async def get_pricing_for_currency(
        self,
        tier: SKUTier,
        currency: str = "NGN",
        billing_cycle: str = "monthly",
    ) -> Optional[int]:
        """
        Get the price for a tier in a specific currency.
        """
        result = await self.db.execute(
            select(SKUPricing)
            .where(
                and_(
                    SKUPricing.sku_tier == tier,
                    SKUPricing.is_active == True,
                )
            )
            .order_by(SKUPricing.effective_from.desc())
        )
        pricing = result.scalar_one_or_none()
        
        if not pricing:
            return None
        
        # Get price based on currency and cycle
        if currency == "NGN":
            if billing_cycle == "annual":
                return int(pricing.base_price_annual)
            return int(pricing.base_price_monthly)
        
        # For other currencies, get the specific column
        currency_suffix = currency.lower()
        monthly_col = f"base_price_monthly_{currency_suffix}"
        annual_col = f"base_price_annual_{currency_suffix}"
        
        if billing_cycle == "annual":
            price = getattr(pricing, annual_col, None)
        else:
            price = getattr(pricing, monthly_col, None)
        
        if price:
            return int(price)
        
        # Fallback: convert from NGN
        ngn_price = int(pricing.base_price_annual if billing_cycle == "annual" else pricing.base_price_monthly)
        return await self.convert_amount(ngn_price, "NGN", currency)
    
    async def get_all_currency_prices(
        self,
        tier: SKUTier,
    ) -> Dict[str, Dict[str, int]]:
        """
        Get pricing for all currencies and billing cycles.
        """
        prices = {}
        for currency in Currency:
            prices[currency.value] = {
                "monthly": await self.get_pricing_for_currency(tier, currency.value, "monthly"),
                "annual": await self.get_pricing_for_currency(tier, currency.value, "annual"),
                "symbol": CURRENCY_SYMBOLS[currency.value],
                "name": CURRENCY_NAMES[currency.value],
            }
        return prices
    
    async def update_billing_rate(
        self,
        from_currency: str,
        to_currency: str,
        rate: Decimal,
        source: str = "manual",
    ) -> ExchangeRate:
        """Update or create a billing exchange rate."""
        result = await self.db.execute(
            select(ExchangeRate)
            .where(
                and_(
                    ExchangeRate.from_currency == from_currency,
                    ExchangeRate.to_currency == to_currency,
                    ExchangeRate.is_billing_rate == True,
                )
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            existing.rate = rate
            existing.rate_date = date.today()
            existing.source = source
            return existing
        
        new_rate = ExchangeRate(
            from_currency=from_currency,
            to_currency=to_currency,
            rate=rate,
            rate_date=date.today(),
            source=source,
            is_billing_rate=True,
        )
        self.db.add(new_rate)
        return new_rate


# =============================================================================
# ISSUE #31: BILLING CYCLE ALIGNMENT SERVICE
# =============================================================================

class BillingCycleService:
    """
    Handle billing cycle alignment and proration.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def calculate_aligned_period(
        self,
        start_date: date,
        billing_anchor_day: Optional[int] = None,
        align_to_calendar_month: bool = False,
        billing_cycle: str = "monthly",
    ) -> Tuple[date, date]:
        """
        Calculate the billing period based on alignment settings.
        
        Args:
            start_date: When subscription started
            billing_anchor_day: Day of month for billing (1-28)
            align_to_calendar_month: If true, align to 1st of month
            billing_cycle: monthly or annual
            
        Returns:
            Tuple of (period_start, period_end)
        """
        if align_to_calendar_month:
            # Align to 1st of month
            period_start = start_date.replace(day=1)
            if billing_cycle == "annual":
                # Also align to January 1st for annual
                period_start = period_start.replace(month=1)
        elif billing_anchor_day:
            # Align to specific day of month
            anchor_day = min(billing_anchor_day, 28)  # Safety check
            period_start = start_date.replace(day=anchor_day)
            if period_start > start_date:
                # Go to previous month
                if period_start.month == 1:
                    period_start = period_start.replace(year=period_start.year - 1, month=12)
                else:
                    period_start = period_start.replace(month=period_start.month - 1)
        else:
            # No alignment - use subscription start date
            period_start = start_date
        
        # Calculate period end
        if billing_cycle == "annual":
            try:
                period_end = period_start.replace(year=period_start.year + 1)
            except ValueError:
                # Handle Feb 29
                period_end = period_start.replace(year=period_start.year + 1, day=28)
        else:
            # Monthly
            if period_start.month == 12:
                period_end = period_start.replace(year=period_start.year + 1, month=1)
            else:
                try:
                    period_end = period_start.replace(month=period_start.month + 1)
                except ValueError:
                    # Handle months with fewer days
                    period_end = period_start.replace(month=period_start.month + 1, day=28)
        
        return period_start, period_end
    
    def calculate_proration(
        self,
        full_price: int,
        start_date: date,
        period_end: date,
        period_start: date,
    ) -> Dict[str, Any]:
        """
        Calculate prorated amount for partial billing period.
        
        Args:
            full_price: Full price for the period
            start_date: When customer starts using service
            period_end: End of billing period
            period_start: Start of billing period
            
        Returns:
            Dict with proration details
        """
        total_days = (period_end - period_start).days
        remaining_days = (period_end - start_date).days
        
        if total_days <= 0:
            return {
                "full_price": full_price,
                "prorated_price": full_price,
                "days_total": 0,
                "days_remaining": 0,
                "proration_percentage": 100.0,
                "is_prorated": False,
            }
        
        proration_percentage = (remaining_days / total_days) * 100
        prorated_price = int((full_price * remaining_days) / total_days)
        
        return {
            "full_price": full_price,
            "prorated_price": prorated_price,
            "days_total": total_days,
            "days_remaining": remaining_days,
            "proration_percentage": round(proration_percentage, 2),
            "is_prorated": remaining_days < total_days,
        }
    
    async def align_subscription(
        self,
        organization_id: UUID,
        anchor_day: Optional[int] = None,
        align_to_calendar: bool = False,
    ) -> Dict[str, Any]:
        """
        Configure billing cycle alignment for a subscription.
        """
        result = await self.db.execute(
            select(TenantSKU)
            .where(TenantSKU.organization_id == organization_id)
        )
        tenant_sku = result.scalar_one_or_none()
        
        if not tenant_sku:
            return {"error": "Subscription not found"}
        
        # Update alignment settings
        tenant_sku.billing_anchor_day = anchor_day
        tenant_sku.align_to_calendar_month = align_to_calendar
        
        # Recalculate period dates
        if tenant_sku.current_period_start:
            new_start, new_end = self.calculate_aligned_period(
                tenant_sku.current_period_start,
                anchor_day,
                align_to_calendar,
                tenant_sku.billing_cycle,
            )
            tenant_sku.current_period_start = new_start
            tenant_sku.current_period_end = new_end
        
        return {
            "success": True,
            "billing_anchor_day": anchor_day,
            "align_to_calendar_month": align_to_calendar,
            "current_period_start": tenant_sku.current_period_start.isoformat() if tenant_sku.current_period_start else None,
            "current_period_end": tenant_sku.current_period_end.isoformat() if tenant_sku.current_period_end else None,
        }


# =============================================================================
# ISSUE #32: SUBSCRIPTION PAUSE/RESUME SERVICE
# =============================================================================

class SubscriptionPauseService:
    """
    Handle subscription pause and resume operations.
    """
    
    MAX_PAUSE_DAYS = 90  # Maximum pause duration
    MAX_ANNUAL_PAUSE_DAYS = 180  # Maximum annual pause allowance
    MAX_PAUSES_PER_YEAR = 2  # Maximum number of pauses allowed per year (Issue #32)
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def _get_pause_count_for_year(self, tenant_sku: TenantSKU, year: int) -> int:
        """Get the pause count for a specific year, resetting if needed."""
        if tenant_sku.last_pause_year != year:
            # Reset count for new year
            return 0
        return tenant_sku.pause_count_this_year or 0
    
    async def pause_subscription(
        self,
        organization_id: UUID,
        reason: str,
        pause_until: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Pause a subscription.
        
        Args:
            organization_id: Organization to pause
            reason: Reason for pausing
            pause_until: When to auto-resume (max 90 days)
            
        Returns:
            Result dictionary
        """
        result = await self.db.execute(
            select(TenantSKU)
            .where(TenantSKU.organization_id == organization_id)
        )
        tenant_sku = result.scalar_one_or_none()
        
        if not tenant_sku:
            return {"success": False, "error": "Subscription not found"}
        
        if not tenant_sku.is_active:
            return {"success": False, "error": "Subscription is not active"}
        
        if tenant_sku.paused_at:
            return {"success": False, "error": "Subscription is already paused"}
        
        if tenant_sku.is_trial:
            return {"success": False, "error": "Cannot pause trial subscriptions"}
        
        # Validate pause_until
        now = datetime.utcnow()
        current_year = now.year
        max_pause_date = now + timedelta(days=self.MAX_PAUSE_DAYS)
        
        if pause_until:
            if pause_until > max_pause_date:
                pause_until = max_pause_date
            if pause_until <= now:
                return {"success": False, "error": "Resume date must be in the future"}
        else:
            # Default to 30 days
            pause_until = now + timedelta(days=30)
        
        # Check annual pause limit (days)
        if tenant_sku.total_paused_days >= self.MAX_ANNUAL_PAUSE_DAYS:
            return {
                "success": False,
                "error": f"Annual pause limit of {self.MAX_ANNUAL_PAUSE_DAYS} days exceeded"
            }
        
        # Issue #32: Check pause count limit (2 per year)
        pause_count = self._get_pause_count_for_year(tenant_sku, current_year)
        if pause_count >= self.MAX_PAUSES_PER_YEAR:
            return {
                "success": False,
                "error": f"Maximum {self.MAX_PAUSES_PER_YEAR} pauses per year allowed. You have used all your pauses for {current_year}.",
                "pauses_used": pause_count,
                "pauses_allowed": self.MAX_PAUSES_PER_YEAR,
            }
        
        # Pause the subscription
        tenant_sku.paused_at = now
        tenant_sku.pause_reason = reason
        tenant_sku.pause_until = pause_until
        
        # Update pause count tracking
        if tenant_sku.last_pause_year != current_year:
            # Reset count for new year
            tenant_sku.pause_count_this_year = 1
            tenant_sku.last_pause_year = current_year
        else:
            tenant_sku.pause_count_this_year = (tenant_sku.pause_count_this_year or 0) + 1
        
        # Calculate days being paused
        pause_days = (pause_until - now).days
        pauses_remaining = self.MAX_PAUSES_PER_YEAR - tenant_sku.pause_count_this_year
        
        return {
            "success": True,
            "paused_at": now.isoformat(),
            "pause_until": pause_until.isoformat(),
            "pause_reason": reason,
            "pause_days": pause_days,
            "pauses_used_this_year": tenant_sku.pause_count_this_year,
            "pauses_remaining_this_year": pauses_remaining,
            "message": f"Subscription paused until {pause_until.strftime('%B %d, %Y')}. You have {pauses_remaining} pause(s) remaining this year."
        }
    
    async def resume_subscription(
        self,
        organization_id: UUID,
    ) -> Dict[str, Any]:
        """
        Resume a paused subscription.
        
        Returns:
            Result dictionary with extended period info
        """
        result = await self.db.execute(
            select(TenantSKU)
            .where(TenantSKU.organization_id == organization_id)
        )
        tenant_sku = result.scalar_one_or_none()
        
        if not tenant_sku:
            return {"success": False, "error": "Subscription not found"}
        
        if not tenant_sku.paused_at:
            return {"success": False, "error": "Subscription is not paused"}
        
        now = datetime.utcnow()
        
        # Calculate pause duration
        pause_duration = (now - tenant_sku.paused_at).days
        
        # Update total paused days
        tenant_sku.total_paused_days += pause_duration
        
        # Credit days to extend subscription period
        tenant_sku.pause_credits_days += pause_duration
        
        # Extend current period end by pause duration
        if tenant_sku.current_period_end:
            new_period_end = tenant_sku.current_period_end + timedelta(days=pause_duration)
            tenant_sku.current_period_end = new_period_end
        
        # Clear pause status
        paused_at = tenant_sku.paused_at
        tenant_sku.paused_at = None
        tenant_sku.pause_reason = None
        tenant_sku.pause_until = None
        
        return {
            "success": True,
            "resumed_at": now.isoformat(),
            "was_paused_at": paused_at.isoformat(),
            "pause_duration_days": pause_duration,
            "days_credited": pause_duration,
            "new_period_end": tenant_sku.current_period_end.isoformat() if tenant_sku.current_period_end else None,
            "message": f"Subscription resumed. {pause_duration} days credited to your billing period."
        }
    
    async def get_pause_status(
        self,
        organization_id: UUID,
    ) -> Dict[str, Any]:
        """Get the pause status for a subscription."""
        result = await self.db.execute(
            select(TenantSKU)
            .where(TenantSKU.organization_id == organization_id)
        )
        tenant_sku = result.scalar_one_or_none()
        
        if not tenant_sku:
            return {"error": "Subscription not found"}
        
        remaining_annual_pause = self.MAX_ANNUAL_PAUSE_DAYS - tenant_sku.total_paused_days
        current_year = datetime.utcnow().year
        pause_count = self._get_pause_count_for_year(tenant_sku, current_year)
        pauses_remaining = max(0, self.MAX_PAUSES_PER_YEAR - pause_count)
        
        return {
            "is_paused": tenant_sku.paused_at is not None,
            "paused_at": tenant_sku.paused_at.isoformat() if tenant_sku.paused_at else None,
            "pause_until": tenant_sku.pause_until.isoformat() if tenant_sku.pause_until else None,
            "pause_reason": tenant_sku.pause_reason,
            "total_paused_days_this_year": tenant_sku.total_paused_days,
            "remaining_pause_days": max(0, remaining_annual_pause),
            "max_pause_days": self.MAX_PAUSE_DAYS,
            "max_annual_pause_days": self.MAX_ANNUAL_PAUSE_DAYS,
            # Issue #32: Pause count tracking
            "pauses_used_this_year": pause_count,
            "pauses_remaining_this_year": pauses_remaining,
            "max_pauses_per_year": self.MAX_PAUSES_PER_YEAR,
            "current_year": current_year,
            "can_pause": (
                tenant_sku.paused_at is None and
                remaining_annual_pause > 0 and
                pauses_remaining > 0 and  # Also check pause count
                tenant_sku.is_active and
                not tenant_sku.is_trial
            ),
        }


# =============================================================================
# ISSUE #33: SERVICE CREDIT SERVICE
# =============================================================================

class ServiceCreditService:
    """
    Handle service credits for SLA breaches and goodwill gestures.
    """
    
    # SLA credit percentages based on availability
    SLA_CREDIT_TIERS = {
        (99.0, 99.5): Decimal("10.0"),   # 10% credit
        (95.0, 99.0): Decimal("25.0"),   # 25% credit
        (90.0, 95.0): Decimal("50.0"),   # 50% credit
        (0.0, 90.0): Decimal("100.0"),   # 100% credit
    }
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def calculate_sla_credit(
        self,
        availability_percentage: Decimal,
        monthly_subscription_price: int,
    ) -> int:
        """
        Calculate SLA credit based on availability.
        
        Args:
            availability_percentage: Actual availability (0-100)
            monthly_subscription_price: Monthly price in smallest currency unit
            
        Returns:
            Credit amount
        """
        credit_percentage = Decimal("0.0")
        
        for (lower, upper), percentage in self.SLA_CREDIT_TIERS.items():
            if lower <= float(availability_percentage) < upper:
                credit_percentage = percentage
                break
        
        if credit_percentage == 0:
            return 0
        
        credit_amount = int((Decimal(monthly_subscription_price) * credit_percentage) / Decimal("100.0"))
        return credit_amount
    
    async def create_sla_credit(
        self,
        organization_id: UUID,
        incident_id: str,
        incident_date: datetime,
        downtime_minutes: int,
        total_minutes: int,
        monthly_subscription_price: int,
        description: str,
        currency: str = "NGN",
    ) -> ServiceCredit:
        """
        Create a service credit for an SLA breach.
        """
        # Calculate availability
        availability = ((total_minutes - downtime_minutes) / total_minutes) * 100
        availability_decimal = Decimal(str(availability))
        
        # Calculate credit amount
        credit_amount = self.calculate_sla_credit(availability_decimal, monthly_subscription_price)
        
        # Create credit
        credit = ServiceCredit(
            organization_id=organization_id,
            credit_type=CreditType.SLA_BREACH.value,
            amount_ngn=credit_amount if currency == "NGN" else 0,
            amount_usd=Decimal(credit_amount) if currency == "USD" else None,
            currency=currency,
            description=description,
            incident_id=incident_id,
            incident_date=incident_date,
            downtime_minutes=downtime_minutes,
            availability_percentage=availability_decimal,
            status=CreditStatus.PENDING.value,
            expires_at=datetime.utcnow() + timedelta(days=365),  # 12 month expiry
        )
        
        self.db.add(credit)
        return credit
    
    async def create_goodwill_credit(
        self,
        organization_id: UUID,
        amount: int,
        description: str,
        currency: str = "NGN",
        auto_approve: bool = False,
    ) -> ServiceCredit:
        """Create a goodwill credit for a customer."""
        credit = ServiceCredit(
            organization_id=organization_id,
            credit_type=CreditType.GOODWILL.value,
            amount_ngn=amount if currency == "NGN" else 0,
            amount_usd=Decimal(amount) if currency == "USD" else None,
            currency=currency,
            description=description,
            status=CreditStatus.APPROVED.value if auto_approve else CreditStatus.PENDING.value,
            approved_at=datetime.utcnow() if auto_approve else None,
            expires_at=datetime.utcnow() + timedelta(days=365),
        )
        
        self.db.add(credit)
        return credit
    
    async def create_referral_reward_credit(
        self,
        organization_id: UUID,
        amount: int,
        referred_org_name: str,
        currency: str = "NGN",
    ) -> ServiceCredit:
        """Create a referral reward credit."""
        credit = ServiceCredit(
            organization_id=organization_id,
            credit_type=CreditType.REFERRAL_REWARD.value,
            amount_ngn=amount if currency == "NGN" else 0,
            amount_usd=Decimal(amount) if currency == "USD" else None,
            currency=currency,
            description=f"Referral reward for referring {referred_org_name}",
            status=CreditStatus.APPROVED.value,
            approved_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=365),
        )
        
        self.db.add(credit)
        return credit
    
    async def approve_credit(
        self,
        credit_id: UUID,
        approved_by_id: UUID,
        admin_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Approve a pending credit."""
        result = await self.db.execute(
            select(ServiceCredit)
            .where(ServiceCredit.id == credit_id)
        )
        credit = result.scalar_one_or_none()
        
        if not credit:
            return {"success": False, "error": "Credit not found"}
        
        if credit.status != CreditStatus.PENDING.value:
            return {"success": False, "error": f"Credit is {credit.status}, not pending"}
        
        credit.status = CreditStatus.APPROVED.value
        credit.approved_by_id = approved_by_id
        credit.approved_at = datetime.utcnow()
        if admin_notes:
            credit.admin_notes = admin_notes
        
        return {
            "success": True,
            "credit_id": str(credit_id),
            "status": "approved",
            "amount": credit.amount_ngn,
            "currency": credit.currency,
        }
    
    async def get_available_credits(
        self,
        organization_id: UUID,
    ) -> List[ServiceCredit]:
        """Get all available (unused, unexpired) credits for an organization."""
        now = datetime.utcnow()
        
        result = await self.db.execute(
            select(ServiceCredit)
            .where(
                and_(
                    ServiceCredit.organization_id == organization_id,
                    ServiceCredit.status == CreditStatus.APPROVED.value,
                    ServiceCredit.applied_at == None,
                    or_(
                        ServiceCredit.expires_at == None,
                        ServiceCredit.expires_at > now,
                    ),
                )
            )
            .order_by(ServiceCredit.expires_at.asc())  # Use oldest first
        )
        
        return list(result.scalars().all())
    
    async def get_credit_balance(
        self,
        organization_id: UUID,
        currency: str = "NGN",
    ) -> Dict[str, Any]:
        """Get total available credit balance for an organization."""
        credits = await self.get_available_credits(organization_id)
        
        total_ngn = sum(c.amount_ngn for c in credits if c.currency == "NGN")
        total_usd = sum(c.amount_usd or Decimal("0") for c in credits if c.currency == "USD")
        
        return {
            "total_ngn": total_ngn,
            "total_usd": float(total_usd),
            "total_credits": len(credits),
            "credits": [
                {
                    "id": str(c.id),
                    "type": c.credit_type,
                    "amount": c.amount_ngn if c.currency == "NGN" else float(c.amount_usd or 0),
                    "currency": c.currency,
                    "description": c.description,
                    "expires_at": c.expires_at.isoformat() if c.expires_at else None,
                }
                for c in credits
            ],
        }
    
    async def apply_credits_to_payment(
        self,
        organization_id: UUID,
        payment_amount: int,
        invoice_id: str,
        currency: str = "NGN",
    ) -> Dict[str, Any]:
        """
        Apply available credits to a payment.
        
        Returns:
            Dict with remaining amount and credits applied
        """
        credits = await self.get_available_credits(organization_id)
        
        remaining_amount = payment_amount
        credits_applied = []
        total_credit_used = 0
        
        for credit in credits:
            if remaining_amount <= 0:
                break
            
            if credit.currency != currency:
                continue  # Skip credits in different currency
            
            available = credit.amount_ngn if currency == "NGN" else int(credit.amount_usd or 0)
            
            if available <= 0:
                continue
            
            amount_to_use = min(available, remaining_amount)
            
            # Mark credit as applied (partially or fully)
            credit.status = CreditStatus.APPLIED.value
            credit.applied_to_invoice_id = invoice_id
            credit.applied_at = datetime.utcnow()
            credit.amount_applied_ngn = amount_to_use
            
            remaining_amount -= amount_to_use
            total_credit_used += amount_to_use
            
            credits_applied.append({
                "credit_id": str(credit.id),
                "amount_used": amount_to_use,
                "type": credit.credit_type,
            })
        
        return {
            "original_amount": payment_amount,
            "credit_used": total_credit_used,
            "remaining_amount": remaining_amount,
            "credits_applied": credits_applied,
            "fully_covered": remaining_amount <= 0,
        }


# =============================================================================
# ISSUE #34: DISCOUNT CODE SERVICE
# =============================================================================

class DiscountCodeService:
    """
    Handle discount and referral code operations.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def validate_code(
        self,
        code: str,
        organization_id: UUID,
        tier: SKUTier,
        billing_cycle: str = "monthly",
    ) -> Dict[str, Any]:
        """
        Validate a discount code and return discount details.
        """
        # Find the code (case-insensitive)
        result = await self.db.execute(
            select(DiscountCode)
            .where(func.upper(DiscountCode.code) == code.upper())
        )
        discount = result.scalar_one_or_none()
        
        if not discount:
            return {"valid": False, "error": "Invalid discount code"}
        
        # Check if code is valid
        if not discount.is_valid:
            if not discount.is_active:
                return {"valid": False, "error": "This discount code is no longer active"}
            if discount.valid_from > datetime.utcnow():
                return {"valid": False, "error": "This discount code is not yet valid"}
            if discount.valid_until and discount.valid_until < datetime.utcnow():
                return {"valid": False, "error": "This discount code has expired"}
            if discount.max_uses_total and discount.current_uses >= discount.max_uses_total:
                return {"valid": False, "error": "This discount code has reached its usage limit"}
        
        # Check tier applicability
        if discount.applies_to_tiers:
            if tier.value not in discount.applies_to_tiers:
                return {"valid": False, "error": f"This code is not valid for the {tier.value} tier"}
        
        # Check billing cycle applicability
        if discount.applies_to_billing_cycles:
            if billing_cycle not in discount.applies_to_billing_cycles:
                return {"valid": False, "error": f"This code is not valid for {billing_cycle} billing"}
        
        # Check if organization already used this code
        usage_result = await self.db.execute(
            select(func.count(DiscountCodeUsage.id))
            .where(
                and_(
                    DiscountCodeUsage.discount_code_id == discount.id,
                    DiscountCodeUsage.organization_id == organization_id,
                )
            )
        )
        org_usage = usage_result.scalar() or 0
        
        if org_usage >= discount.max_uses_per_org:
            return {"valid": False, "error": "You have already used this discount code"}
        
        return {
            "valid": True,
            "code": discount.code,
            "name": discount.name,
            "description": discount.description,
            "discount_type": discount.discount_type,
            "discount_value": float(discount.discount_value),
            "max_discount_ngn": discount.max_discount_ngn,
            "first_payment_only": discount.first_payment_only,
            "is_referral_code": discount.is_referral_code,
        }
    
    def calculate_discount(
        self,
        original_amount: int,
        discount_type: str,
        discount_value: Decimal,
        max_discount: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Calculate the discount amount.
        """
        if discount_type == DiscountType.PERCENTAGE.value:
            discount_amount = int((Decimal(original_amount) * discount_value) / Decimal("100"))
            if max_discount and discount_amount > max_discount:
                discount_amount = max_discount
        elif discount_type == DiscountType.FIXED_AMOUNT.value:
            discount_amount = int(discount_value)
        else:
            # Free months handled differently
            discount_amount = 0
        
        final_amount = max(0, original_amount - discount_amount)
        
        return {
            "original_amount": original_amount,
            "discount_amount": discount_amount,
            "final_amount": final_amount,
            "savings_percentage": round((discount_amount / original_amount) * 100, 2) if original_amount > 0 else 0,
        }
    
    async def apply_code(
        self,
        code: str,
        organization_id: UUID,
        user_id: Optional[UUID],
        original_amount: int,
        payment_reference: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Apply a discount code and record the usage.
        """
        result = await self.db.execute(
            select(DiscountCode)
            .where(func.upper(DiscountCode.code) == code.upper())
        )
        discount = result.scalar_one_or_none()
        
        if not discount:
            return {"success": False, "error": "Invalid discount code"}
        
        # Calculate discount
        calc = self.calculate_discount(
            original_amount,
            discount.discount_type,
            discount.discount_value,
            discount.max_discount_ngn,
        )
        
        # Record usage
        usage = DiscountCodeUsage(
            discount_code_id=discount.id,
            organization_id=organization_id,
            user_id=user_id,
            payment_reference=payment_reference,
            original_amount_ngn=original_amount,
            discount_amount_ngn=calc["discount_amount"],
            final_amount_ngn=calc["final_amount"],
        )
        self.db.add(usage)
        
        # Increment usage count
        discount.current_uses += 1
        
        # Handle referral rewards
        referrer_credit = None
        if discount.is_referral_code and discount.referrer_organization_id:
            # Create credit for referrer
            credit_service = ServiceCreditService(self.db)
            referrer_credit = await credit_service.create_referral_reward_credit(
                organization_id=discount.referrer_organization_id,
                amount=int(discount.referrer_reward_value or 0),
                referred_org_name="New Customer",  # Would fetch org name in real impl
            )
            usage.referrer_reward_issued = True
            usage.referrer_credit_id = referrer_credit.id
        
        return {
            "success": True,
            "original_amount": original_amount,
            "discount_amount": calc["discount_amount"],
            "final_amount": calc["final_amount"],
            "code": discount.code,
            "referrer_rewarded": referrer_credit is not None,
        }
    
    async def create_referral_code(
        self,
        organization_id: UUID,
        reward_type: str = "credit",
        reward_value: int = 10000,  # ₦10,000 default
        discount_percentage: int = 10,  # 10% for referred
    ) -> DiscountCode:
        """
        Create a referral code for an organization.
        """
        # Generate unique code
        from app.models.organization import Organization
        
        result = await self.db.execute(
            select(Organization)
            .where(Organization.id == organization_id)
        )
        org = result.scalar_one_or_none()
        
        # Generate code from org name
        base_code = "".join(c for c in (org.name if org else "REF")[:8].upper() if c.isalnum())
        code = f"{base_code}{datetime.utcnow().strftime('%m%d')}"
        
        referral = DiscountCode(
            code=code,
            name=f"Referral from {org.name if org else 'Customer'}",
            description=f"Get {discount_percentage}% off your first payment",
            discount_type=DiscountType.PERCENTAGE.value,
            discount_value=Decimal(discount_percentage),
            first_payment_only=True,
            valid_from=datetime.utcnow(),
            is_referral_code=True,
            referrer_organization_id=organization_id,
            referrer_reward_type=reward_type,
            referrer_reward_value=Decimal(reward_value),
            is_active=True,
        )
        
        self.db.add(referral)
        return referral
    
    async def get_organization_referral_code(
        self,
        organization_id: UUID,
    ) -> Optional[DiscountCode]:
        """Get or create the referral code for an organization."""
        result = await self.db.execute(
            select(DiscountCode)
            .where(
                and_(
                    DiscountCode.referrer_organization_id == organization_id,
                    DiscountCode.is_referral_code == True,
                    DiscountCode.is_active == True,
                )
            )
        )
        code = result.scalar_one_or_none()
        
        if code:
            return code
        
        # Create one if it doesn't exist
        return await self.create_referral_code(organization_id)


# =============================================================================
# ISSUE #35: VOLUME DISCOUNT SERVICE
# =============================================================================

class VolumeDiscountService:
    """
    Handle volume-based and commitment-based discounts.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_applicable_rules(
        self,
        user_count: int,
        entity_count: int,
        commitment_months: int,
        tier: SKUTier,
        currency: str = "NGN",
    ) -> List[VolumeDiscountRule]:
        """
        Get all applicable volume discount rules for given parameters.
        """
        today = date.today()
        
        result = await self.db.execute(
            select(VolumeDiscountRule)
            .where(
                and_(
                    VolumeDiscountRule.is_active == True,
                    VolumeDiscountRule.effective_from <= today,
                    or_(
                        VolumeDiscountRule.effective_until == None,
                        VolumeDiscountRule.effective_until >= today,
                    ),
                    or_(
                        VolumeDiscountRule.applies_to_tier == None,
                        VolumeDiscountRule.applies_to_tier == tier.value,
                    ),
                    or_(
                        VolumeDiscountRule.applies_to_currency == None,
                        VolumeDiscountRule.applies_to_currency == currency,
                    ),
                )
            )
            .order_by(VolumeDiscountRule.priority.desc())
        )
        
        all_rules = list(result.scalars().all())
        applicable = []
        
        for rule in all_rules:
            # Check if rule applies based on thresholds
            if rule.rule_type == "user_count":
                if rule.min_users and user_count < rule.min_users:
                    continue
                if rule.max_users and user_count > rule.max_users:
                    continue
            elif rule.rule_type == "entity_count":
                if rule.min_entities and entity_count < rule.min_entities:
                    continue
                if rule.max_entities and entity_count > rule.max_entities:
                    continue
            elif rule.rule_type == "commitment_months":
                if rule.min_commitment_months and commitment_months < rule.min_commitment_months:
                    continue
            
            applicable.append(rule)
        
        return applicable
    
    async def calculate_volume_discount(
        self,
        base_price: int,
        user_count: int,
        entity_count: int,
        commitment_months: int,
        tier: SKUTier,
        currency: str = "NGN",
    ) -> Dict[str, Any]:
        """
        Calculate the total volume discount for a subscription.
        """
        rules = await self.get_applicable_rules(
            user_count, entity_count, commitment_months, tier, currency
        )
        
        if not rules:
            return {
                "base_price": base_price,
                "discount_amount": 0,
                "final_price": base_price,
                "discount_percentage": Decimal("0.0"),
                "applied_rules": [],
            }
        
        # Find best non-stackable discount
        best_non_stackable = None
        best_non_stackable_discount = Decimal("0.0")
        
        stackable_discounts = []
        
        for rule in rules:
            if rule.stackable:
                stackable_discounts.append(rule)
            else:
                if rule.discount_percentage > best_non_stackable_discount:
                    best_non_stackable = rule
                    best_non_stackable_discount = rule.discount_percentage
        
        # Calculate total discount percentage
        total_discount_pct = best_non_stackable_discount
        applied_rules = []
        
        if best_non_stackable:
            applied_rules.append({
                "name": best_non_stackable.name,
                "percentage": float(best_non_stackable.discount_percentage),
                "type": best_non_stackable.rule_type,
            })
        
        for rule in stackable_discounts:
            total_discount_pct += rule.discount_percentage
            applied_rules.append({
                "name": rule.name,
                "percentage": float(rule.discount_percentage),
                "type": rule.rule_type,
                "stackable": True,
            })
        
        # Cap at 50% discount
        total_discount_pct = min(total_discount_pct, Decimal("50.0"))
        
        discount_amount = int((Decimal(base_price) * total_discount_pct) / Decimal("100.0"))
        final_price = base_price - discount_amount
        
        return {
            "base_price": base_price,
            "discount_amount": discount_amount,
            "final_price": final_price,
            "discount_percentage": float(total_discount_pct),
            "applied_rules": applied_rules,
        }


# =============================================================================
# ISSUE #30: USAGE REPORT SERVICE
# =============================================================================

class UsageReportService:
    """
    Handle usage report generation and delivery.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def generate_usage_report_csv(
        self,
        organization_id: UUID,
        start_date: date,
        end_date: date,
    ) -> Tuple[str, bytes]:
        """
        Generate a CSV usage report.
        
        Returns:
            Tuple of (filename, csv_content)
        """
        result = await self.db.execute(
            select(UsageRecord)
            .where(
                and_(
                    UsageRecord.organization_id == organization_id,
                    UsageRecord.period_start >= start_date,
                    UsageRecord.period_end <= end_date,
                )
            )
            .order_by(UsageRecord.period_start.asc())
        )
        records = list(result.scalars().all())
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            "Period Start", "Period End",
            "Transactions", "Users", "Entities", "Invoices",
            "API Calls", "OCR Pages", "Storage (MB)", "ML Inferences",
            "Employees", "Is Billed"
        ])
        
        # Data rows
        for record in records:
            writer.writerow([
                record.period_start.isoformat(),
                record.period_end.isoformat(),
                record.transactions_count,
                record.users_count,
                record.entities_count,
                record.invoices_count,
                record.api_calls_count,
                record.ocr_pages_count,
                float(record.storage_used_mb),
                record.ml_inferences_count,
                record.employees_count,
                "Yes" if record.is_billed else "No",
            ])
        
        # Summary row
        writer.writerow([])
        writer.writerow(["SUMMARY"])
        writer.writerow([
            f"{start_date} to {end_date}", "",
            sum(r.transactions_count for r in records),
            max(r.users_count for r in records) if records else 0,
            max(r.entities_count for r in records) if records else 0,
            sum(r.invoices_count for r in records),
            sum(r.api_calls_count for r in records),
            sum(r.ocr_pages_count for r in records),
            float(max(r.storage_used_mb for r in records)) if records else 0,
            sum(r.ml_inferences_count for r in records),
            max(r.employees_count for r in records) if records else 0,
            "",
        ])
        
        csv_content = output.getvalue().encode('utf-8')
        filename = f"usage_report_{organization_id}_{start_date}_{end_date}.csv"
        
        return filename, csv_content
    
    async def generate_usage_report_pdf(
        self,
        organization_id: UUID,
        start_date: date,
        end_date: date,
    ) -> Tuple[str, bytes]:
        """
        Generate a PDF usage report using HTML to PDF conversion.
        
        Returns:
            Tuple of (filename, pdf_content)
        """
        # Fetch usage records
        result = await self.db.execute(
            select(UsageRecord)
            .where(
                and_(
                    UsageRecord.organization_id == organization_id,
                    UsageRecord.period_start >= start_date,
                    UsageRecord.period_end <= end_date,
                )
            )
            .order_by(UsageRecord.period_start.asc())
        )
        records = list(result.scalars().all())
        
        # Get organization name
        from app.models import Organization
        org_result = await self.db.execute(
            select(Organization).where(Organization.id == organization_id)
        )
        org = org_result.scalar_one_or_none()
        org_name = org.name if org else "Unknown Organization"
        
        # Calculate summary
        summary = {
            "total_transactions": sum(r.transactions_count for r in records),
            "total_invoices": sum(r.invoices_count for r in records),
            "total_api_calls": sum(r.api_calls_count for r in records),
            "total_ocr_pages": sum(r.ocr_pages_count for r in records),
            "peak_users": max(r.users_count for r in records) if records else 0,
            "peak_storage_mb": float(max(r.storage_used_mb for r in records)) if records else 0,
            "total_periods": len(records),
        }
        
        # Generate HTML content
        html_content = self._generate_report_html(
            organization_name=org_name,
            organization_id=str(organization_id),
            start_date=start_date,
            end_date=end_date,
            records=records,
            summary=summary,
        )
        
        # Convert HTML to PDF using weasyprint or fallback to HTML bytes
        try:
            from weasyprint import HTML
            pdf_bytes = HTML(string=html_content).write_pdf()
        except ImportError:
            # If weasyprint is not installed, return HTML as base64-encoded PDF placeholder
            # In production, you'd want to ensure weasyprint is installed
            pdf_bytes = self._create_simple_pdf(
                organization_name=org_name,
                start_date=start_date,
                end_date=end_date,
                records=records,
                summary=summary,
            )
        
        filename = f"usage_report_{organization_id}_{start_date}_{end_date}.pdf"
        return filename, pdf_bytes
    
    def _generate_report_html(
        self,
        organization_name: str,
        organization_id: str,
        start_date: date,
        end_date: date,
        records: List,
        summary: Dict,
    ) -> str:
        """Generate HTML content for the PDF report."""
        rows_html = ""
        for r in records:
            rows_html += f"""
            <tr>
                <td>{r.period_start.strftime('%Y-%m-%d')}</td>
                <td>{r.period_end.strftime('%Y-%m-%d')}</td>
                <td>{r.transactions_count:,}</td>
                <td>{r.users_count:,}</td>
                <td>{r.invoices_count:,}</td>
                <td>{r.api_calls_count:,}</td>
                <td>{r.ocr_pages_count:,}</td>
                <td>{float(r.storage_used_mb):.2f}</td>
            </tr>
            """
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Usage Report - {organization_name}</title>
            <style>
                body {{
                    font-family: 'Helvetica Neue', Arial, sans-serif;
                    margin: 40px;
                    color: #333;
                }}
                .header {{
                    text-align: center;
                    margin-bottom: 40px;
                    border-bottom: 2px solid #2563eb;
                    padding-bottom: 20px;
                }}
                .logo {{
                    font-size: 24px;
                    font-weight: bold;
                    color: #2563eb;
                }}
                h1 {{
                    color: #1f2937;
                    margin: 10px 0;
                }}
                .meta {{
                    color: #6b7280;
                    font-size: 14px;
                }}
                .summary {{
                    display: flex;
                    flex-wrap: wrap;
                    gap: 20px;
                    margin: 30px 0;
                }}
                .summary-card {{
                    background: #f3f4f6;
                    padding: 20px;
                    border-radius: 8px;
                    min-width: 150px;
                    text-align: center;
                }}
                .summary-card .value {{
                    font-size: 24px;
                    font-weight: bold;
                    color: #2563eb;
                }}
                .summary-card .label {{
                    font-size: 12px;
                    color: #6b7280;
                    margin-top: 5px;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 30px;
                }}
                th, td {{
                    border: 1px solid #e5e7eb;
                    padding: 12px 8px;
                    text-align: left;
                }}
                th {{
                    background: #2563eb;
                    color: white;
                    font-weight: 600;
                }}
                tr:nth-child(even) {{
                    background: #f9fafb;
                }}
                .footer {{
                    margin-top: 40px;
                    padding-top: 20px;
                    border-top: 1px solid #e5e7eb;
                    font-size: 12px;
                    color: #6b7280;
                    text-align: center;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <div class="logo">Tekvwa Pro Audit</div>
                <h1>Usage Report</h1>
                <div class="meta">
                    <p><strong>{organization_name}</strong></p>
                    <p>Period: {start_date.strftime('%B %d, %Y')} - {end_date.strftime('%B %d, %Y')}</p>
                    <p>Generated: {datetime.utcnow().strftime('%B %d, %Y at %H:%M UTC')}</p>
                </div>
            </div>
            
            <h2>Summary</h2>
            <div class="summary">
                <div class="summary-card">
                    <div class="value">{summary['total_transactions']:,}</div>
                    <div class="label">Total Transactions</div>
                </div>
                <div class="summary-card">
                    <div class="value">{summary['total_invoices']:,}</div>
                    <div class="label">Total Invoices</div>
                </div>
                <div class="summary-card">
                    <div class="value">{summary['peak_users']:,}</div>
                    <div class="label">Peak Users</div>
                </div>
                <div class="summary-card">
                    <div class="value">{summary['total_api_calls']:,}</div>
                    <div class="label">API Calls</div>
                </div>
                <div class="summary-card">
                    <div class="value">{summary['total_ocr_pages']:,}</div>
                    <div class="label">OCR Pages</div>
                </div>
                <div class="summary-card">
                    <div class="value">{summary['peak_storage_mb']:.1f} MB</div>
                    <div class="label">Peak Storage</div>
                </div>
            </div>
            
            <h2>Detailed Usage by Period</h2>
            <table>
                <thead>
                    <tr>
                        <th>Period Start</th>
                        <th>Period End</th>
                        <th>Transactions</th>
                        <th>Users</th>
                        <th>Invoices</th>
                        <th>API Calls</th>
                        <th>OCR Pages</th>
                        <th>Storage (MB)</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html if rows_html else '<tr><td colspan="8" style="text-align:center;">No usage records found</td></tr>'}
                </tbody>
            </table>
            
            <div class="footer">
                <p>This report was automatically generated by Tekvwa Pro Audit.</p>
                <p>Organization ID: {organization_id}</p>
            </div>
        </body>
        </html>
        """
    
    def _create_simple_pdf(
        self,
        organization_name: str,
        start_date: date,
        end_date: date,
        records: List,
        summary: Dict,
    ) -> bytes:
        """
        Create a simple PDF without external dependencies.
        Uses reportlab if available, otherwise creates minimal PDF.
        """
        try:
            from reportlab.lib.pagesizes import letter, A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib import colors
            
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            styles = getSampleStyleSheet()
            elements = []
            
            # Title
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=18,
                spaceAfter=20,
                alignment=1,  # Center
            )
            elements.append(Paragraph("Tekvwa Pro Audit - Usage Report", title_style))
            elements.append(Paragraph(f"<b>{organization_name}</b>", styles['Normal']))
            elements.append(Paragraph(f"Period: {start_date} to {end_date}", styles['Normal']))
            elements.append(Spacer(1, 20))
            
            # Summary section
            elements.append(Paragraph("<b>Summary</b>", styles['Heading2']))
            summary_data = [
                ["Metric", "Value"],
                ["Total Transactions", f"{summary['total_transactions']:,}"],
                ["Total Invoices", f"{summary['total_invoices']:,}"],
                ["Peak Users", f"{summary['peak_users']:,}"],
                ["Total API Calls", f"{summary['total_api_calls']:,}"],
                ["Peak Storage", f"{summary['peak_storage_mb']:.1f} MB"],
            ]
            summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
            summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563eb')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f9fafb')),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e5e7eb')),
            ]))
            elements.append(summary_table)
            elements.append(Spacer(1, 20))
            
            # Detailed records
            if records:
                elements.append(Paragraph("<b>Detailed Usage</b>", styles['Heading2']))
                detail_data = [["Start", "End", "Txns", "Users", "Invoices", "API", "Storage"]]
                for r in records[:20]:  # Limit to 20 rows for PDF
                    detail_data.append([
                        r.period_start.strftime('%Y-%m-%d'),
                        r.period_end.strftime('%Y-%m-%d'),
                        f"{r.transactions_count:,}",
                        f"{r.users_count:,}",
                        f"{r.invoices_count:,}",
                        f"{r.api_calls_count:,}",
                        f"{float(r.storage_used_mb):.1f}",
                    ])
                
                detail_table = Table(detail_data, colWidths=[1*inch, 1*inch, 0.7*inch, 0.7*inch, 0.8*inch, 0.7*inch, 0.8*inch])
                detail_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563eb')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),
                ]))
                elements.append(detail_table)
            
            doc.build(elements)
            return buffer.getvalue()
            
        except ImportError:
            # Absolute fallback: create minimal valid PDF
            # This is a very basic PDF structure
            pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]
/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length 200 >>
stream
BT
/F1 16 Tf
50 750 Td
(Tekvwa Pro Audit - Usage Report) Tj
0 -30 Td
/F1 12 Tf
(Organization: """ + organization_name.encode() + b""") Tj
0 -20 Td
(Period: """ + str(start_date).encode() + b""" to """ + str(end_date).encode() + b""") Tj
0 -20 Td
(Total Transactions: """ + str(summary['total_transactions']).encode() + b""") Tj
0 -20 Td
(PDF export requires reportlab or weasyprint library.) Tj
ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000268 00000 n 
0000000520 00000 n 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
599
%%EOF"""
            return pdf_content
    
    async def generate_usage_summary(
        self,
        organization_id: UUID,
        months: int = 12,
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive usage summary.
        """
        from app.services.metering_service import MeteringService
        
        metering = MeteringService(self.db)
        
        # Get current usage
        current_usage = await metering.get_usage_summary(organization_id)
        
        # Get historical usage
        history = await metering.get_usage_history(organization_id, months)
        
        # Calculate trends
        if len(history) >= 2:
            latest = history[0]
            previous = history[1]
            
            trends = {
                "transactions": self._calc_trend(latest.transactions_count, previous.transactions_count),
                "users": self._calc_trend(latest.users_count, previous.users_count),
                "storage": self._calc_trend(float(latest.storage_used_mb), float(previous.storage_used_mb)),
            }
        else:
            trends = {"transactions": 0, "users": 0, "storage": 0}
        
        # Calculate totals for period
        totals = {
            "total_transactions": sum(r.transactions_count for r in history),
            "total_invoices": sum(r.invoices_count for r in history),
            "total_api_calls": sum(r.api_calls_count for r in history),
            "peak_users": max(r.users_count for r in history) if history else 0,
            "peak_storage_mb": float(max(r.storage_used_mb for r in history)) if history else 0,
        }
        
        return {
            "organization_id": str(organization_id),
            "generated_at": datetime.utcnow().isoformat(),
            "period_months": months,
            "current": current_usage,
            "totals": totals,
            "trends": trends,
            "history": [
                {
                    "period_start": r.period_start.isoformat(),
                    "period_end": r.period_end.isoformat(),
                    "transactions": r.transactions_count,
                    "users": r.users_count,
                    "entities": r.entities_count,
                    "invoices": r.invoices_count,
                    "storage_mb": float(r.storage_used_mb),
                }
                for r in history
            ],
        }
    
    def _calc_trend(self, current: float, previous: float) -> float:
        """Calculate percentage change between two values."""
        if previous == 0:
            return 100.0 if current > 0 else 0.0
        return round(((current - previous) / previous) * 100, 2)
    
    async def save_report_history(
        self,
        organization_id: UUID,
        report_type: str,
        format: str,
        period_start: date,
        period_end: date,
        file_path: Optional[str] = None,
        file_size: Optional[int] = None,
        generated_by_id: Optional[UUID] = None,
    ) -> UsageReportHistory:
        """Save a record of a generated report."""
        report = UsageReportHistory(
            organization_id=organization_id,
            report_type=report_type,
            format=format,
            period_start=period_start,
            period_end=period_end,
            file_path=file_path,
            file_size_bytes=file_size,
            generated_by_id=generated_by_id,
            expires_at=datetime.utcnow() + timedelta(days=90),
        )
        self.db.add(report)
        return report
    
    async def get_report_history(
        self,
        organization_id: UUID,
        limit: int = 20,
    ) -> List[UsageReportHistory]:
        """Get recent report history for an organization."""
        result = await self.db.execute(
            select(UsageReportHistory)
            .where(UsageReportHistory.organization_id == organization_id)
            .order_by(UsageReportHistory.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


# =============================================================================
# COMBINED ADVANCED BILLING SERVICE
# =============================================================================

class AdvancedBillingService:
    """
    Combined service providing access to all advanced billing features.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.currency = CurrencyService(db)
        self.billing_cycle = BillingCycleService(db)
        self.pause = SubscriptionPauseService(db)
        self.credits = ServiceCreditService(db)
        self.discounts = DiscountCodeService(db)
        self.volume = VolumeDiscountService(db)
        self.reports = UsageReportService(db)
    
    async def calculate_final_price(
        self,
        organization_id: UUID,
        tier: SKUTier,
        billing_cycle: str,
        currency: str = "NGN",
        user_count: int = 1,
        entity_count: int = 1,
        commitment_months: int = 1,
        discount_code: Optional[str] = None,
        apply_credits: bool = True,
    ) -> Dict[str, Any]:
        """
        Calculate the final price including all discounts and credits.
        """
        # Get base price
        base_price = await self.currency.get_pricing_for_currency(tier, currency, billing_cycle)
        
        if base_price is None:
            return {"error": "Could not determine pricing"}
        
        result = {
            "base_price": base_price,
            "currency": currency,
            "symbol": CURRENCY_SYMBOLS.get(currency, currency),
            "tier": tier.value,
            "billing_cycle": billing_cycle,
            "adjustments": [],
        }
        
        current_price = base_price
        
        # Apply volume discounts
        volume_result = await self.volume.calculate_volume_discount(
            current_price, user_count, entity_count, commitment_months, tier, currency
        )
        if volume_result["discount_amount"] > 0:
            result["adjustments"].append({
                "type": "volume_discount",
                "amount": -volume_result["discount_amount"],
                "description": f"{volume_result['discount_percentage']}% volume discount",
                "rules": volume_result["applied_rules"],
            })
            current_price = volume_result["final_price"]
        
        # Apply discount code
        if discount_code:
            validation = await self.discounts.validate_code(
                discount_code, organization_id, tier, billing_cycle
            )
            if validation["valid"]:
                calc = self.discounts.calculate_discount(
                    current_price,
                    validation["discount_type"],
                    Decimal(str(validation["discount_value"])),
                    validation.get("max_discount_ngn"),
                )
                result["adjustments"].append({
                    "type": "discount_code",
                    "code": discount_code,
                    "amount": -calc["discount_amount"],
                    "description": validation["name"],
                })
                current_price = calc["final_amount"]
        
        # Apply service credits
        if apply_credits:
            credit_balance = await self.credits.get_credit_balance(organization_id, currency)
            available_credit = credit_balance["total_ngn"] if currency == "NGN" else int(credit_balance["total_usd"])
            
            if available_credit > 0:
                credit_to_use = min(available_credit, current_price)
                result["adjustments"].append({
                    "type": "service_credit",
                    "amount": -credit_to_use,
                    "description": f"Service credits ({credit_balance['total_credits']} available)",
                    "remaining_credit": available_credit - credit_to_use,
                })
                current_price -= credit_to_use
        
        result["final_price"] = max(0, current_price)
        result["total_savings"] = base_price - result["final_price"]
        result["savings_percentage"] = round((result["total_savings"] / base_price) * 100, 2) if base_price > 0 else 0
        
        return result
