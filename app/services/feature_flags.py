"""
Tekvwa Pro Audit - Feature Flags Service

Service for checking feature access based on SKU tier.
Implements feature gating for commercial tier enforcement.
"""

import logging
from typing import Dict, List, Optional, Set, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.sku import (
    SKUTier, 
    IntelligenceAddon, 
    Feature, 
    TenantSKU,
    UsageMetricType,
    TIER_LIMITS,
    INTELLIGENCE_LIMITS,
    FeatureAccessLog,
)
from app.models.organization import Organization

logger = logging.getLogger(__name__)


# =============================================================================
# FEATURE TIER MAPPING
# =============================================================================

# Which features are available at each tier
TIER_FEATURES: Dict[SKUTier, Set[Feature]] = {
    SKUTier.CORE: {
        Feature.GL_ENABLED,
        Feature.CHART_OF_ACCOUNTS,
        Feature.JOURNAL_ENTRIES,
        Feature.BASIC_REPORTS,
        Feature.TAX_ENGINE_BASIC,
        Feature.CUSTOMER_MANAGEMENT,
        Feature.VENDOR_MANAGEMENT,
        Feature.BASIC_INVOICING,
        Feature.AUDIT_LOGS_STANDARD,
        Feature.INVENTORY_BASIC,
    },
    SKUTier.PROFESSIONAL: {
        # Includes all CORE features
        Feature.GL_ENABLED,
        Feature.CHART_OF_ACCOUNTS,
        Feature.JOURNAL_ENTRIES,
        Feature.BASIC_REPORTS,
        Feature.TAX_ENGINE_BASIC,
        Feature.CUSTOMER_MANAGEMENT,
        Feature.VENDOR_MANAGEMENT,
        Feature.BASIC_INVOICING,
        Feature.AUDIT_LOGS_STANDARD,
        Feature.INVENTORY_BASIC,
        # PROFESSIONAL features
        Feature.PAYROLL,
        Feature.PAYROLL_ADVANCED,
        Feature.BANK_RECONCILIATION,
        Feature.FIXED_ASSETS,
        Feature.EXPENSE_CLAIMS,
        Feature.E_INVOICING,
        Feature.NRS_COMPLIANCE,
        Feature.ADVANCED_REPORTS,
        Feature.RULE_BASED_ALERTS,
        Feature.MULTI_USER_RBAC,
        Feature.INVENTORY_ADVANCED,
        Feature.DASHBOARD_ADVANCED,
        Feature.MULTI_CURRENCY,        # FX, multi-currency transactions
        Feature.BUDGET_MANAGEMENT,     # Budget creation and tracking
        Feature.BUDGET_VARIANCE,       # Budget vs Actual analysis
    },
    SKUTier.ENTERPRISE: {
        # Includes all PROFESSIONAL features
        Feature.GL_ENABLED,
        Feature.CHART_OF_ACCOUNTS,
        Feature.JOURNAL_ENTRIES,
        Feature.BASIC_REPORTS,
        Feature.TAX_ENGINE_BASIC,
        Feature.CUSTOMER_MANAGEMENT,
        Feature.VENDOR_MANAGEMENT,
        Feature.BASIC_INVOICING,
        Feature.AUDIT_LOGS_STANDARD,
        Feature.INVENTORY_BASIC,
        Feature.PAYROLL,
        Feature.PAYROLL_ADVANCED,
        Feature.BANK_RECONCILIATION,
        Feature.FIXED_ASSETS,
        Feature.EXPENSE_CLAIMS,
        Feature.E_INVOICING,
        Feature.NRS_COMPLIANCE,
        Feature.ADVANCED_REPORTS,
        Feature.RULE_BASED_ALERTS,
        Feature.MULTI_USER_RBAC,
        Feature.INVENTORY_ADVANCED,
        Feature.DASHBOARD_ADVANCED,
        Feature.MULTI_CURRENCY,        # FX, multi-currency transactions
        Feature.BUDGET_MANAGEMENT,     # Budget creation and tracking
        Feature.BUDGET_VARIANCE,       # Budget vs Actual analysis
        # ENTERPRISE features
        Feature.WORM_VAULT,
        Feature.INTERCOMPANY,
        Feature.MULTI_ENTITY,
        Feature.ATTESTATION,
        Feature.DIGITAL_SIGNATURES,
        Feature.SOX_COMPLIANCE,
        Feature.IFRS_COMPLIANCE,
        Feature.FRCN_COMPLIANCE,
        Feature.SEGREGATION_OF_DUTIES,
        Feature.FULL_API_ACCESS,
        Feature.PRIORITY_SUPPORT,
        Feature.AUDIT_VAULT_EXTENDED,
        Feature.CONSOLIDATION,
    },
}

# Intelligence add-on features
INTELLIGENCE_FEATURES: Dict[IntelligenceAddon, Set[Feature]] = {
    IntelligenceAddon.NONE: set(),
    IntelligenceAddon.STANDARD: {
        Feature.ML_ANOMALY_DETECTION,
        Feature.BENFORDS_LAW,
        Feature.ZSCORE_ANALYSIS,
        Feature.PREDICTIVE_FORECASTING,
        Feature.OCR_EXTRACTION,
        Feature.FRAUD_DETECTION,
    },
    IntelligenceAddon.ADVANCED: {
        Feature.ML_ANOMALY_DETECTION,
        Feature.BENFORDS_LAW,
        Feature.ZSCORE_ANALYSIS,
        Feature.PREDICTIVE_FORECASTING,
        Feature.NLP_PROCESSING,
        Feature.OCR_EXTRACTION,
        Feature.FRAUD_DETECTION,
        Feature.CUSTOM_ML_TRAINING,
        Feature.BEHAVIORAL_ANALYTICS,
    },
}


class FeatureAccessDenied(Exception):
    """Raised when a feature is not available for the tenant's SKU tier."""
    
    def __init__(
        self, 
        feature: Feature, 
        current_tier: SKUTier,
        required_tier: Optional[SKUTier] = None,
        requires_addon: bool = False,
    ):
        self.feature = feature
        self.current_tier = current_tier
        self.required_tier = required_tier
        self.requires_addon = requires_addon
        
        if requires_addon:
            message = (
                f"Feature '{feature.value}' requires Pro Audit Intelligence add-on. "
                f"Contact sales to enable ML/AI features."
            )
        elif required_tier:
            message = (
                f"Feature '{feature.value}' requires Pro Audit {required_tier.value.title()} tier. "
                f"Current tier: {current_tier.value.title()}. Upgrade to access this feature."
            )
        else:
            message = f"Feature '{feature.value}' is not available on your current plan."
        
        super().__init__(message)


class UsageLimitExceeded(Exception):
    """Raised when a usage limit has been exceeded."""
    
    def __init__(
        self,
        metric: UsageMetricType,
        current_usage: int,
        limit: int,
        tier: SKUTier,
    ):
        self.metric = metric
        self.current_usage = current_usage
        self.limit = limit
        self.tier = tier
        
        message = (
            f"Usage limit exceeded for {metric.value}: {current_usage}/{limit}. "
            f"Upgrade your plan or contact support to increase limits."
        )
        super().__init__(message)


class FeatureFlagService:
    """
    Service for checking feature access based on organization's SKU tier.
    
    Usage:
        service = FeatureFlagService(db)
        
        # Check if feature is available
        if await service.has_feature(org_id, Feature.PAYROLL):
            # Feature is available
            
        # Or use require_feature to raise exception if not available
        await service.require_feature(org_id, Feature.PAYROLL)
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self._cache: Dict[UUID, TenantSKU] = {}
    
    async def get_tenant_sku(self, organization_id: UUID) -> Optional[TenantSKU]:
        """
        Get the TenantSKU for an organization.
        Returns None if no SKU is configured (defaults to CORE).
        """
        # Check cache first
        if organization_id in self._cache:
            return self._cache[organization_id]
        
        result = await self.db.execute(
            select(TenantSKU)
            .where(TenantSKU.organization_id == organization_id)
            .where(TenantSKU.is_active == True)
        )
        tenant_sku = result.scalar_one_or_none()
        
        if tenant_sku:
            self._cache[organization_id] = tenant_sku
        
        return tenant_sku
    
    async def get_effective_tier(self, organization_id: UUID) -> SKUTier:
        """
        Get the effective SKU tier for an organization.
        Defaults to CORE if not configured.
        """
        tenant_sku = await self.get_tenant_sku(organization_id)
        if tenant_sku:
            return tenant_sku.tier
        return SKUTier.CORE
    
    async def get_intelligence_addon(self, organization_id: UUID) -> IntelligenceAddon:
        """Get the Intelligence add-on level for an organization."""
        tenant_sku = await self.get_tenant_sku(organization_id)
        if tenant_sku:
            return tenant_sku.intelligence_addon
        return IntelligenceAddon.NONE
    
    async def get_enabled_features(self, organization_id: UUID) -> Set[Feature]:
        """
        Get all enabled features for an organization.
        Combines tier features, intelligence addon features, and any overrides.
        """
        tenant_sku = await self.get_tenant_sku(organization_id)
        
        # Start with base tier features
        tier = tenant_sku.tier if tenant_sku else SKUTier.CORE
        features = TIER_FEATURES.get(tier, set()).copy()
        
        # Add intelligence addon features
        intel_addon = tenant_sku.intelligence_addon if tenant_sku else IntelligenceAddon.NONE
        features.update(INTELLIGENCE_FEATURES.get(intel_addon, set()))
        
        # Apply feature overrides
        if tenant_sku and tenant_sku.feature_overrides:
            for feature_name, enabled in tenant_sku.feature_overrides.items():
                try:
                    feature = Feature(feature_name)
                    if enabled:
                        features.add(feature)
                    else:
                        features.discard(feature)
                except ValueError:
                    logger.warning(f"Unknown feature in overrides: {feature_name}")
        
        return features
    
    async def has_feature(
        self, 
        organization_id: UUID, 
        feature: Feature,
        log_access: bool = False,
        user_id: Optional[UUID] = None,
        request_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Check if an organization has access to a specific feature.
        
        Args:
            organization_id: The organization to check
            feature: The feature to check access for
            log_access: Whether to log this access attempt
            user_id: User making the request (for logging)
            request_context: Additional request context (endpoint, IP, etc.)
        
        Returns:
            True if feature is available, False otherwise
        """
        enabled_features = await self.get_enabled_features(organization_id)
        has_access = feature in enabled_features
        
        if log_access and user_id:
            await self._log_feature_access(
                organization_id=organization_id,
                user_id=user_id,
                feature=feature,
                was_granted=has_access,
                request_context=request_context,
            )
        
        return has_access
    
    async def require_feature(
        self,
        organization_id: UUID,
        feature: Feature,
        user_id: Optional[UUID] = None,
        request_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Require that an organization has access to a feature.
        Raises FeatureAccessDenied if not available.
        
        Args:
            organization_id: The organization to check
            feature: The feature required
            user_id: User making the request (for logging)
            request_context: Additional request context
        
        Raises:
            FeatureAccessDenied: If feature is not available
        """
        has_access = await self.has_feature(
            organization_id=organization_id,
            feature=feature,
            log_access=True,
            user_id=user_id,
            request_context=request_context,
        )
        
        if not has_access:
            tenant_sku = await self.get_tenant_sku(organization_id)
            current_tier = tenant_sku.tier if tenant_sku else SKUTier.CORE
            
            # Determine what's needed to access this feature
            required_tier = self._get_required_tier(feature)
            requires_addon = self._requires_intelligence_addon(feature)
            
            # Log denial reason
            if user_id:
                reason = "requires_intelligence_addon" if requires_addon else f"requires_{required_tier.value}"
                await self._log_feature_access(
                    organization_id=organization_id,
                    user_id=user_id,
                    feature=feature,
                    was_granted=False,
                    denial_reason=reason,
                    request_context=request_context,
                )
            
            raise FeatureAccessDenied(
                feature=feature,
                current_tier=current_tier,
                required_tier=required_tier,
                requires_addon=requires_addon,
            )
    
    async def get_limit(
        self, 
        organization_id: UUID, 
        metric: UsageMetricType
    ) -> int:
        """
        Get the usage limit for a specific metric.
        Returns -1 for unlimited.
        """
        tenant_sku = await self.get_tenant_sku(organization_id)
        tier = tenant_sku.tier if tenant_sku else SKUTier.CORE
        intel_addon = tenant_sku.intelligence_addon if tenant_sku else IntelligenceAddon.NONE
        
        # Check for custom limit override
        if tenant_sku and tenant_sku.custom_limits:
            custom_limit = tenant_sku.custom_limits.get(metric.value)
            if custom_limit is not None:
                return int(custom_limit)
        
        # Get base tier limit
        tier_limit = TIER_LIMITS.get(tier, {}).get(metric, 0)
        
        # Add intelligence addon limits for relevant metrics
        if metric in [UsageMetricType.OCR_PAGES, UsageMetricType.ML_INFERENCES]:
            intel_limit = INTELLIGENCE_LIMITS.get(intel_addon, {}).get(metric, 0)
            return intel_limit  # Intelligence limits override base for these metrics
        
        return tier_limit
    
    async def check_limit(
        self,
        organization_id: UUID,
        metric: UsageMetricType,
        current_usage: int,
    ) -> bool:
        """
        Check if current usage is within limits.
        
        Returns:
            True if within limits, False if exceeded
        """
        limit = await self.get_limit(organization_id, metric)
        
        # -1 means unlimited
        if limit == -1:
            return True
        
        return current_usage < limit
    
    async def require_within_limit(
        self,
        organization_id: UUID,
        metric: UsageMetricType,
        current_usage: int,
    ) -> None:
        """
        Require that usage is within limits.
        Raises UsageLimitExceeded if exceeded.
        """
        limit = await self.get_limit(organization_id, metric)
        
        if limit != -1 and current_usage >= limit:
            tenant_sku = await self.get_tenant_sku(organization_id)
            tier = tenant_sku.tier if tenant_sku else SKUTier.CORE
            
            raise UsageLimitExceeded(
                metric=metric,
                current_usage=current_usage,
                limit=limit,
                tier=tier,
            )
    
    def _get_required_tier(self, feature: Feature) -> Optional[SKUTier]:
        """Determine the minimum tier required for a feature."""
        # Check each tier from lowest to highest
        for tier in [SKUTier.CORE, SKUTier.PROFESSIONAL, SKUTier.ENTERPRISE]:
            if feature in TIER_FEATURES.get(tier, set()):
                return tier
        return None
    
    def _requires_intelligence_addon(self, feature: Feature) -> bool:
        """Check if a feature requires the Intelligence add-on."""
        for addon_level in [IntelligenceAddon.STANDARD, IntelligenceAddon.ADVANCED]:
            if feature in INTELLIGENCE_FEATURES.get(addon_level, set()):
                return True
        return False
    
    async def _log_feature_access(
        self,
        organization_id: UUID,
        user_id: UUID,
        feature: Feature,
        was_granted: bool,
        denial_reason: Optional[str] = None,
        request_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log a feature access attempt."""
        try:
            log = FeatureAccessLog(
                organization_id=organization_id,
                user_id=user_id,
                feature=feature,
                was_granted=was_granted,
                denial_reason=denial_reason,
                endpoint=request_context.get("endpoint") if request_context else None,
                ip_address=request_context.get("ip_address") if request_context else None,
                user_agent=request_context.get("user_agent") if request_context else None,
            )
            self.db.add(log)
            await self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to log feature access: {e}")
    
    async def get_upgrade_recommendation(
        self, 
        organization_id: UUID,
        denied_feature: Feature,
    ) -> Dict[str, Any]:
        """
        Get upgrade recommendation when a feature is denied.
        Useful for showing users what they need to upgrade to.
        """
        tenant_sku = await self.get_tenant_sku(organization_id)
        current_tier = tenant_sku.tier if tenant_sku else SKUTier.CORE
        current_intel = tenant_sku.intelligence_addon if tenant_sku else IntelligenceAddon.NONE
        
        required_tier = self._get_required_tier(denied_feature)
        requires_intel = self._requires_intelligence_addon(denied_feature)
        
        recommendation = {
            "current_tier": current_tier.value,
            "current_intelligence": current_intel.value,
            "denied_feature": denied_feature.value,
            "recommendation": None,
            "estimated_price_naira": None,
        }
        
        if requires_intel and current_intel == IntelligenceAddon.NONE:
            recommendation["recommendation"] = "Add Pro Audit Intelligence"
            recommendation["requires_intelligence"] = True
            recommendation["estimated_price_naira"] = "₦250,000 - ₦1,000,000/month"
        elif required_tier and self._tier_rank(required_tier) > self._tier_rank(current_tier):
            recommendation["recommendation"] = f"Upgrade to Pro Audit {required_tier.value.title()}"
            recommendation["required_tier"] = required_tier.value
            if required_tier == SKUTier.PROFESSIONAL:
                recommendation["estimated_price_naira"] = "₦150,000 - ₦400,000/month"
            elif required_tier == SKUTier.ENTERPRISE:
                recommendation["estimated_price_naira"] = "₦1,000,000 - ₦5,000,000+/month"
        
        return recommendation
    
    def _tier_rank(self, tier: SKUTier) -> int:
        """Get numeric rank of tier for comparison."""
        ranks = {
            SKUTier.CORE: 1,
            SKUTier.PROFESSIONAL: 2,
            SKUTier.ENTERPRISE: 3,
        }
        return ranks.get(tier, 0)
    
    def clear_cache(self, organization_id: Optional[UUID] = None) -> None:
        """Clear the SKU cache for an organization or all organizations."""
        if organization_id:
            self._cache.pop(organization_id, None)
        else:
            self._cache.clear()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_tier_features(tier: SKUTier) -> Set[Feature]:
    """Get all features available for a tier."""
    return TIER_FEATURES.get(tier, set()).copy()


def get_intelligence_features(addon: IntelligenceAddon) -> Set[Feature]:
    """Get all features available for an intelligence addon level."""
    return INTELLIGENCE_FEATURES.get(addon, set()).copy()


def feature_requires_tier(feature: Feature) -> Optional[SKUTier]:
    """Get the minimum tier required for a feature."""
    for tier in [SKUTier.CORE, SKUTier.PROFESSIONAL, SKUTier.ENTERPRISE]:
        if feature in TIER_FEATURES.get(tier, set()):
            return tier
    return None


def feature_requires_intelligence(feature: Feature) -> bool:
    """Check if a feature requires Intelligence add-on."""
    for addon in [IntelligenceAddon.STANDARD, IntelligenceAddon.ADVANCED]:
        if feature in INTELLIGENCE_FEATURES.get(addon, set()):
            return True
    return False
