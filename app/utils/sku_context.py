"""
Tekvwa Pro Audit - SKU Context for Templates

Provides SKU tier and feature context to Jinja2 templates for UI-level feature gating.
"""

from typing import Dict, Any, Set, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sku import TenantSKU, SKUTier, IntelligenceAddon
from app.models.sku_enums import Feature
from app.config.sku_config import (
    TIER_PRICING,
    INTELLIGENCE_PRICING,
    format_naira,
)


class SKUContext:
    """
    SKU context for template rendering.
    
    Provides helpers for feature gating in Jinja2 templates.
    
    Usage in templates:
        {% if sku.has_feature('payroll') %}
            <a href="/payroll">Payroll</a>
        {% else %}
            <a href="/upgrade?feature=payroll" class="text-gray-400">
                Payroll <span class="badge">Upgrade</span>
            </a>
        {% endif %}
    """
    
    def __init__(
        self,
        tier: SKUTier = SKUTier.CORE,
        intelligence_addon: IntelligenceAddon = IntelligenceAddon.NONE,
        is_trial: bool = False,
        trial_days_remaining: Optional[int] = None,
        enabled_features: Optional[Set[str]] = None,
        feature_overrides: Optional[Dict[str, bool]] = None,
    ):
        self.tier = tier
        self.intelligence_addon = intelligence_addon
        self.is_trial = is_trial
        self.trial_days_remaining = trial_days_remaining
        self._enabled_features = enabled_features or set()
        self._feature_overrides = feature_overrides or {}
        
    @property
    def tier_name(self) -> str:
        """Human-readable tier name."""
        return {
            SKUTier.CORE: "Core",
            SKUTier.PROFESSIONAL: "Professional",
            SKUTier.ENTERPRISE: "Enterprise",
        }.get(self.tier, "Core")
    
    @property
    def tier_badge_class(self) -> str:
        """CSS class for tier badge."""
        return {
            SKUTier.CORE: "bg-gray-100 text-gray-800",
            SKUTier.PROFESSIONAL: "bg-blue-100 text-blue-800",
            SKUTier.ENTERPRISE: "bg-purple-100 text-purple-800",
        }.get(self.tier, "bg-gray-100 text-gray-800")
    
    @property
    def has_intelligence(self) -> bool:
        """Check if Intelligence add-on is active."""
        return self.intelligence_addon != IntelligenceAddon.NONE
    
    @property
    def intelligence_level(self) -> str:
        """Human-readable intelligence level."""
        return {
            IntelligenceAddon.NONE: "None",
            IntelligenceAddon.STANDARD: "Standard",
            IntelligenceAddon.ADVANCED: "Advanced",
        }.get(self.intelligence_addon, "None")
    
    def has_feature(self, feature: str) -> bool:
        """
        Check if a feature is available.
        
        Args:
            feature: Feature name (e.g., 'payroll', 'bank_reconciliation')
            
        Returns:
            True if feature is available
        """
        # Check overrides first
        if feature in self._feature_overrides:
            return self._feature_overrides[feature]
        
        # Check enabled features
        return feature in self._enabled_features
    
    def feature_tier(self, feature: str) -> Optional[str]:
        """
        Get the minimum tier required for a feature.
        
        Args:
            feature: Feature name
            
        Returns:
            Tier name or None if feature is an intelligence add-on feature
        """
        from app.services.feature_flags import TIER_FEATURES
        
        for tier, features in TIER_FEATURES.items():
            if feature in [f.value for f in features]:
                return tier.value
        return None
    
    def upgrade_url(self, feature: str) -> str:
        """
        Get the upgrade URL for a feature.
        
        Args:
            feature: Feature name
            
        Returns:
            URL to upgrade page with feature context
        """
        return f"/upgrade?feature={feature}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for template context."""
        return {
            "tier": self.tier.value,
            "tier_name": self.tier_name,
            "tier_badge_class": self.tier_badge_class,
            "intelligence_addon": self.intelligence_addon.value,
            "intelligence_level": self.intelligence_level,
            "has_intelligence": self.has_intelligence,
            "is_trial": self.is_trial,
            "trial_days_remaining": self.trial_days_remaining,
            "enabled_features": list(self._enabled_features),
        }


async def get_sku_context(
    db: AsyncSession,
    organization_id: UUID,
) -> SKUContext:
    """
    Get SKU context for an organization.
    
    Args:
        db: Database session
        organization_id: Organization UUID
        
    Returns:
        SKUContext with tier and feature information
    """
    from app.services.feature_flags import FeatureFlagService
    from datetime import datetime
    
    service = FeatureFlagService(db)
    tenant_sku = await service.get_tenant_sku(organization_id)
    
    if not tenant_sku:
        # Default to Core tier trial
        return SKUContext(
            tier=SKUTier.CORE,
            intelligence_addon=IntelligenceAddon.NONE,
            is_trial=True,
            trial_days_remaining=14,
            enabled_features=_get_tier_features(SKUTier.CORE),
        )
    
    # Get enabled features
    enabled_features_enums = await service.get_enabled_features(organization_id)
    enabled_features = {f.value for f in enabled_features_enums}
    
    # Calculate trial days remaining
    trial_days_remaining = None
    if tenant_sku.trial_ends_at:
        days = (tenant_sku.trial_ends_at - datetime.utcnow()).days
        trial_days_remaining = max(0, days)
    
    return SKUContext(
        tier=tenant_sku.tier,
        intelligence_addon=tenant_sku.intelligence_addon or IntelligenceAddon.NONE,
        is_trial=tenant_sku.trial_ends_at is not None and trial_days_remaining is not None and trial_days_remaining > 0,
        trial_days_remaining=trial_days_remaining,
        enabled_features=enabled_features,
        feature_overrides=tenant_sku.feature_overrides or {},
    )


def _get_tier_features(tier: SKUTier) -> Set[str]:
    """Get all features available for a tier."""
    from app.services.feature_flags import TIER_FEATURES
    
    features = set()
    
    # Add features from this tier and below
    tier_order = [SKUTier.CORE, SKUTier.PROFESSIONAL, SKUTier.ENTERPRISE]
    tier_index = tier_order.index(tier)
    
    for i in range(tier_index + 1):
        t = tier_order[i]
        if t in TIER_FEATURES:
            features.update(f.value for f in TIER_FEATURES[t])
    
    return features


# =============================================================================
# FEATURE DESCRIPTIONS FOR UPGRADE PROMPTS
# =============================================================================

FEATURE_UPGRADE_PROMPTS: Dict[str, Dict[str, str]] = {
    "payroll": {
        "title": "Payroll Management",
        "description": "Process employee salaries, generate payslips, and handle statutory deductions.",
        "required_tier": "professional",
        "icon": "",
    },
    "payroll_advanced": {
        "title": "Advanced Payroll",
        "description": "Multi-company payroll, custom salary components, and advanced reporting.",
        "required_tier": "professional",
        "icon": "",
    },
    "bank_reconciliation": {
        "title": "Bank Reconciliation",
        "description": "Automatically match bank statements with transactions.",
        "required_tier": "professional",
        "icon": "",
    },
    "fixed_assets": {
        "title": "Fixed Asset Management",
        "description": "Track and depreciate fixed assets according to Nigerian tax rules.",
        "required_tier": "professional",
        "icon": "",
    },
    "expense_claims": {
        "title": "Expense Claims",
        "description": "Employee expense submission and approval workflows.",
        "required_tier": "professional",
        "icon": "",
    },
    "worm_vault": {
        "title": "Compliance Vault",
        "description": "Immutable audit trail meeting regulatory compliance requirements.",
        "required_tier": "enterprise",
        "icon": "",
    },
    "multi_entity": {
        "title": "Multi-Entity",
        "description": "Manage multiple companies with consolidated reporting.",
        "required_tier": "enterprise",
        "icon": "",
    },
    "intercompany": {
        "title": "Intercompany Transactions",
        "description": "Handle transactions between related entities with automatic elimination.",
        "required_tier": "enterprise",
        "icon": "",
    },
    "ml_anomaly_detection": {
        "title": "AI Anomaly Detection",
        "description": "Machine learning powered detection of unusual transactions.",
        "required_tier": "intelligence",
        "icon": "",
    },
    "benfords_law": {
        "title": "Benford's Law Analysis",
        "description": "Statistical analysis to detect potential fraud patterns.",
        "required_tier": "intelligence",
        "icon": "",
    },
    "ocr_extraction": {
        "title": "OCR Document Extraction",
        "description": "Automatically extract data from invoices and receipts.",
        "required_tier": "intelligence",
        "icon": "",
    },
}


def get_feature_upgrade_prompt(feature: str) -> Dict[str, str]:
    """Get upgrade prompt information for a feature."""
    return FEATURE_UPGRADE_PROMPTS.get(feature, {
        "title": feature.replace("_", " ").title(),
        "description": "This feature requires a higher tier plan.",
        "required_tier": "professional",
        "icon": "⭐",
    })
