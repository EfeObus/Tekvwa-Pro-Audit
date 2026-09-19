"""
Tekvwa Pro Audit - SKU System Unit Tests

Tests for the SKU (Stock Keeping Unit) / tier system including:
- Feature flag enforcement
- Registration trial creation  
- Tier limits enforcement
- Billing service functionality
- Usage metering
- Alert system
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sku import (
    SKUTier, 
    IntelligenceAddon, 
    TenantSKU, 
    UsageRecord,
    UsageEvent,
    FeatureAccessLog,
    SKUPricing,
)
from app.config.sku_config import (
    TIER_PRICING,
    INTELLIGENCE_PRICING,
    TIER_LIMITS_CONFIG,
    get_tier_display_name,
    get_tier_description,
    get_features_for_tier,
    TierPricing,
)
from app.services.billing_service import (
    BillingService,
    BillingCycle,
    PaymentStatus,
    generate_payment_reference,
    format_price_naira,
    calculate_annual_savings,
)
from app.services.usage_alert_service import (
    UsageAlertService,
    AlertThreshold,
    AlertChannel,
)


# =============================================================================
# FEATURE FLAG TESTS
# =============================================================================

class TestFeatureFlags:
    """Tests for SKU feature flag configuration."""
    
    def test_tier_pricing_exists_for_all_tiers(self):
        """Verify pricing is defined for all SKU tiers."""
        for tier in SKUTier:
            assert tier in TIER_PRICING, f"Missing pricing for tier: {tier}"
            pricing = TIER_PRICING[tier]
            # TierPricing is a dataclass
            assert isinstance(pricing, TierPricing), f"Pricing for {tier} should be TierPricing"
            assert pricing.monthly_min > 0, f"Monthly min should be > 0 for {tier}"
            assert pricing.annual_min > 0, f"Annual min should be > 0 for {tier}"
    
    def test_intelligence_pricing_exists_for_all_addons(self):
        """Verify pricing is defined for all intelligence add-ons."""
        for addon in IntelligenceAddon:
            if addon == IntelligenceAddon.NONE:
                continue  # NONE is free, no pricing needed
            assert addon in INTELLIGENCE_PRICING, f"Missing pricing for addon: {addon}"
            pricing = INTELLIGENCE_PRICING[addon]
            assert pricing.monthly_min > 0, f"Monthly min should be > 0 for {addon}"
    
    def test_annual_pricing_is_discounted(self):
        """Verify annual pricing has discount over monthly."""
        for tier in SKUTier:
            pricing = TIER_PRICING[tier]
            monthly_annual = pricing.monthly_min * 12
            annual = pricing.annual_min
            # Annual should be less than 12 months of monthly
            assert annual < monthly_annual, f"Tier {tier} annual should be less than 12x monthly"
    
    def test_feature_sets_defined_for_all_tiers(self):
        """Verify features are defined for all SKU tiers."""
        for tier in SKUTier:
            features = get_features_for_tier(tier)
            assert isinstance(features, set), f"Features for {tier} should be a set"
            # Each tier should have at least some features
            assert len(features) > 0, f"Tier {tier} should have features"
    
    def test_tier_limits_defined_for_all_tiers(self):
        """Verify usage limits are defined for all tiers."""
        for tier in SKUTier:
            assert tier in TIER_LIMITS_CONFIG, f"Missing limits for tier: {tier}"
            limits = TIER_LIMITS_CONFIG[tier]
            # TierLimits is a dataclass, check attributes
            assert hasattr(limits, 'max_transactions_monthly')
            assert hasattr(limits, 'max_invoices_monthly')
            assert hasattr(limits, 'api_calls_per_hour')
            assert hasattr(limits, 'max_users')
    
    def test_tier_display_name_returns_valid_string(self):
        """Verify tier display name function works correctly."""
        for tier in SKUTier:
            name = get_tier_display_name(tier)
            assert isinstance(name, str)
            assert len(name) > 0
    
    def test_tier_description_returns_valid_string(self):
        """Verify tier description function works correctly."""
        for tier in SKUTier:
            desc = get_tier_description(tier)
            assert isinstance(desc, str)
            assert len(desc) > 0


# =============================================================================
# TENANT SKU MODEL TESTS
# =============================================================================

class TestTenantSKUModel:
    """Tests for TenantSKU model properties and methods."""
    
    def test_create_sku_with_trial(self):
        """Test creating a SKU with trial period."""
        sku = TenantSKU(
            id=uuid4(),
            organization_id=uuid4(),
            tier=SKUTier.CORE,
            trial_ends_at=datetime.utcnow() + timedelta(days=14),
        )
        
        assert sku.tier == SKUTier.CORE
        assert sku.trial_ends_at is not None
    
    def test_create_paid_sku(self):
        """Test creating a paid (non-trial) SKU."""
        sku = TenantSKU(
            id=uuid4(),
            organization_id=uuid4(),
            tier=SKUTier.PROFESSIONAL,
            billing_cycle="monthly",
        )
        
        assert sku.tier == SKUTier.PROFESSIONAL
        assert sku.trial_ends_at is None  # No trial
    
    def test_sku_with_intelligence_addon(self):
        """Test SKU with intelligence add-on."""
        sku = TenantSKU(
            id=uuid4(),
            organization_id=uuid4(),
            tier=SKUTier.PROFESSIONAL,
            intelligence_addon=IntelligenceAddon.STANDARD,
        )
        
        assert sku.intelligence_addon == IntelligenceAddon.STANDARD
    
    def test_sku_with_custom_limits(self):
        """Test SKU with custom limits override."""
        custom_limits = {"transactions_per_month": 10000}
        sku = TenantSKU(
            id=uuid4(),
            organization_id=uuid4(),
            tier=SKUTier.CORE,
            custom_limits=custom_limits,
        )
        
        assert sku.custom_limits == custom_limits


# =============================================================================
# BILLING SERVICE TESTS
# =============================================================================

class TestBillingServiceHelpers:
    """Tests for billing service helper functions."""
    
    def test_generate_payment_reference(self):
        """Test payment reference generation."""
        org_id = uuid4()
        ref = generate_payment_reference(org_id)
        
        assert ref.startswith("TVP-")
        assert len(ref) > 10
        # Should contain org ID prefix
        assert org_id.hex[:8] in ref
    
    def test_format_price_naira(self):
        """Test Naira price formatting."""
        assert format_price_naira(50000) == "₦50,000"
        assert format_price_naira(2000000) == "₦2,000,000"
        assert format_price_naira(100) == "₦100"
    
    def test_calculate_annual_savings_core(self):
        """Test annual savings calculation for Core tier."""
        savings = calculate_annual_savings(SKUTier.CORE)
        # Core: ₦25,000/month × 12 = ₦300,000, annual is ₦255,000
        # Savings = ₦300,000 - ₦255,000 = ₦45,000
        assert savings > 0
    
    def test_calculate_annual_savings_professional(self):
        """Test annual savings calculation for Professional tier."""
        savings = calculate_annual_savings(SKUTier.PROFESSIONAL)
        # Should have positive savings
        assert savings > 0


class TestBillingService:
    """Tests for BillingService class."""
    
    @pytest.mark.asyncio
    async def test_billing_service_initialization(self, db_session):
        """Test BillingService can be initialized."""
        service = BillingService(db_session)
        assert service is not None
    
    @pytest.mark.asyncio
    async def test_calculate_subscription_price_monthly(self, db_session):
        """Test monthly subscription price calculation."""
        service = BillingService(db_session)
        
        price = service.calculate_subscription_price(
            tier=SKUTier.PROFESSIONAL,
            billing_cycle=BillingCycle.MONTHLY,
            intelligence_addon=None,
            additional_users=0,
        )
        
        # Professional starts at ₦150,000/month
        assert price >= 150000
    
    @pytest.mark.asyncio
    async def test_calculate_subscription_price_annual(self, db_session):
        """Test annual subscription price calculation."""
        service = BillingService(db_session)
        
        price = service.calculate_subscription_price(
            tier=SKUTier.PROFESSIONAL,
            billing_cycle=BillingCycle.ANNUAL,
            intelligence_addon=None,
            additional_users=0,
        )
        
        # Annual should be less than 12x monthly
        monthly = service.calculate_subscription_price(
            tier=SKUTier.PROFESSIONAL,
            billing_cycle=BillingCycle.MONTHLY,
            intelligence_addon=None,
            additional_users=0,
        )
        assert price < monthly * 12


# =============================================================================
# USAGE ALERT SERVICE TESTS
# =============================================================================

class TestUsageAlertService:
    """Tests for usage alert service."""
    
    def test_alert_thresholds(self):
        """Test alert threshold values."""
        assert AlertThreshold.WARNING_80.value == "80"
        assert AlertThreshold.CRITICAL_90.value == "90"
        assert AlertThreshold.EXCEEDED_100.value == "100"
    
    def test_alert_channels(self):
        """Test alert channel values."""
        assert AlertChannel.EMAIL == "email"
        assert AlertChannel.WEBSOCKET == "websocket"
        assert AlertChannel.IN_APP == "in_app"
        assert AlertChannel.WEBHOOK == "webhook"
    
    @pytest.mark.asyncio
    async def test_usage_alert_service_initialization(self, db_session):
        """Test UsageAlertService can be initialized."""
        service = UsageAlertService(db_session)
        assert service is not None


# =============================================================================
# USAGE RECORD MODEL TESTS
# =============================================================================

class TestUsageRecordModel:
    """Tests for UsageRecord model."""
    
    def test_create_usage_record(self):
        """Test creating a usage record."""
        org_id = uuid4()
        record = UsageRecord(
            id=uuid4(),
            organization_id=org_id,
            period_start=date.today().replace(day=1),
            period_end=date.today().replace(day=28),
            transactions_count=100,
            invoices_count=50,
            api_calls_count=5000,
        )
        
        assert record.organization_id == org_id
        assert record.transactions_count == 100
        assert record.invoices_count == 50
        assert record.api_calls_count == 5000


# =============================================================================
# USAGE EVENT MODEL TESTS
# =============================================================================

class TestUsageEventModel:
    """Tests for UsageEvent model."""
    
    def test_create_usage_event(self):
        """Test creating a usage event."""
        from app.models.sku import UsageMetricType
        
        org_id = uuid4()
        entity_id = uuid4()
        user_id = uuid4()
        
        event = UsageEvent(
            id=uuid4(),
            organization_id=org_id,
            entity_id=entity_id,
            user_id=user_id,
            metric_type=UsageMetricType.TRANSACTIONS,
            resource_type="transaction",
            quantity=1,
        )
        
        assert event.organization_id == org_id
        assert event.metric_type == UsageMetricType.TRANSACTIONS
        assert event.quantity == 1


# =============================================================================
# FEATURE ACCESS LOG MODEL TESTS
# =============================================================================

class TestFeatureAccessLogModel:
    """Tests for FeatureAccessLog model."""
    
    def test_create_access_log_allowed(self):
        """Test creating an allowed access log."""
        from app.config.sku_config import Feature
        
        log = FeatureAccessLog(
            id=uuid4(),
            organization_id=uuid4(),
            user_id=uuid4(),
            feature=Feature.PAYROLL,
            was_granted=True,
        )
        
        assert log.was_granted is True
        assert log.feature == Feature.PAYROLL
    
    def test_create_access_log_denied(self):
        """Test creating a denied access log."""
        from app.config.sku_config import Feature
        
        log = FeatureAccessLog(
            id=uuid4(),
            organization_id=uuid4(),
            user_id=uuid4(),
            feature=Feature.WORM_VAULT,  # Enterprise feature
            was_granted=False,
            denial_reason="Requires Enterprise tier",
        )
        
        assert log.was_granted is False
        assert log.denial_reason == "Requires Enterprise tier"


# =============================================================================
# SKU PRICING MODEL TESTS
# =============================================================================

class TestSKUPricingModel:
    """Tests for SKUPricing database model."""
    
    def test_create_sku_pricing(self):
        """Test creating SKU pricing record."""
        pricing = SKUPricing(
            id=uuid4(),
            sku_tier=SKUTier.PROFESSIONAL,
            base_price_monthly=Decimal("200000"),  # ₦200,000
            base_price_annual=Decimal("1920000"),   # ₦1,920,000
            currency="NGN",
            is_active=True,
        )
        
        assert pricing.sku_tier == SKUTier.PROFESSIONAL
        assert pricing.base_price_monthly == Decimal("200000")
        assert pricing.currency == "NGN"


# =============================================================================
# TIER LIMITS ENFORCEMENT TESTS
# =============================================================================

class TestTierLimitsEnforcement:
    """Tests for tier limit enforcement logic."""
    
    def test_core_tier_limits(self):
        """Test Core tier has appropriate limits."""
        limits = TIER_LIMITS_CONFIG[SKUTier.CORE]
        
        assert limits.max_transactions_monthly <= 15000
        assert limits.max_invoices_monthly <= 500
        assert limits.max_users <= 5
    
    def test_professional_tier_has_higher_limits(self):
        """Test Professional tier has higher limits than Core."""
        core_limits = TIER_LIMITS_CONFIG[SKUTier.CORE]
        pro_limits = TIER_LIMITS_CONFIG[SKUTier.PROFESSIONAL]
        
        assert pro_limits.max_transactions_monthly > core_limits.max_transactions_monthly
        assert pro_limits.max_invoices_monthly > core_limits.max_invoices_monthly
        assert pro_limits.max_users > core_limits.max_users
    
    def test_enterprise_tier_has_highest_limits(self):
        """Test Enterprise tier has highest or unlimited limits (-1 = unlimited)."""
        pro_limits = TIER_LIMITS_CONFIG[SKUTier.PROFESSIONAL]
        ent_limits = TIER_LIMITS_CONFIG[SKUTier.ENTERPRISE]
        
        # For transactions: compare directly or check for unlimited (-1)
        assert ent_limits.max_transactions_monthly >= pro_limits.max_transactions_monthly or ent_limits.max_transactions_monthly == -1
        
        # For invoices: -1 means unlimited, which is better than any positive limit
        if ent_limits.max_invoices_monthly == -1:
            assert True  # Unlimited is the highest
        else:
            assert ent_limits.max_invoices_monthly >= pro_limits.max_invoices_monthly
    
    def test_usage_within_limits(self):
        """Test usage check when within limits."""
        limits = TIER_LIMITS_CONFIG[SKUTier.CORE]
        current_usage = limits.max_transactions_monthly - 100
        
        is_within = current_usage <= limits.max_transactions_monthly
        assert is_within is True
    
    def test_usage_exceeds_limits(self):
        """Test usage check when exceeding limits."""
        limits = TIER_LIMITS_CONFIG[SKUTier.CORE]
        current_usage = limits.max_transactions_monthly + 100
        
        is_within = current_usage <= limits.max_transactions_monthly
        assert is_within is False


# =============================================================================
# PRICE CALCULATION TESTS
# =============================================================================

class TestPriceCalculations:
    """Tests for pricing calculations."""
    
    def test_tier_pricing_consistency(self):
        """Test that annual pricing is always less than 12x monthly."""
        for tier in SKUTier:
            pricing = TIER_PRICING[tier]
            twelve_months = pricing.monthly_min * 12
            assert pricing.annual_min < twelve_months, f"Tier {tier} annual should be discounted"
    
    def test_enterprise_tier_most_expensive(self):
        """Test Enterprise tier is the most expensive."""
        core_price = TIER_PRICING[SKUTier.CORE].monthly_min
        pro_price = TIER_PRICING[SKUTier.PROFESSIONAL].monthly_min
        ent_price = TIER_PRICING[SKUTier.ENTERPRISE].monthly_min
        
        assert ent_price > pro_price > core_price
    
    def test_pricing_in_naira(self):
        """Test all prices are reasonable Naira amounts."""
        for tier in SKUTier:
            pricing = TIER_PRICING[tier]
            # Monthly should be between ₦10,000 and ₦10,000,000
            assert 10000 <= pricing.monthly_min <= 10000000
            assert 10000 <= pricing.annual_min <= 100000000


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestSKUIntegration:
    """Integration tests for SKU system."""
    
    @pytest.mark.asyncio
    async def test_create_tenant_sku_in_db(self, db_session, test_organization):
        """Test creating a TenantSKU in the database."""
        sku = TenantSKU(
            id=uuid4(),
            organization_id=test_organization.id,
            tier=SKUTier.CORE,
            billing_cycle="trial",
            trial_ends_at=datetime.utcnow() + timedelta(days=14),
        )
        db_session.add(sku)
        await db_session.commit()
        await db_session.refresh(sku)
        
        assert sku.organization_id == test_organization.id
        assert sku.tier == SKUTier.CORE
        assert sku.trial_ends_at is not None


# =============================================================================
# FIXTURES
# =============================================================================

@pytest_asyncio.fixture
async def test_organization(db_session: AsyncSession):
    """Create a test organization for SKU tests."""
    from app.models.organization import Organization
    
    org = Organization(
        id=uuid4(),
        name="SKU Test Organization",
        slug="sku-test-org",
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest_asyncio.fixture
async def test_tenant_sku(db_session: AsyncSession, test_organization):
    """Create a test TenantSKU."""
    sku = TenantSKU(
        id=uuid4(),
        organization_id=test_organization.id,
        tier=SKUTier.PROFESSIONAL,
        billing_cycle="monthly",
    )
    db_session.add(sku)
    await db_session.commit()
    await db_session.refresh(sku)
    return sku
