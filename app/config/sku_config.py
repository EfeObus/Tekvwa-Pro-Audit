"""
Tekvwa Pro Audit - SKU Configuration

Central configuration for all SKU-related settings.
Pricing in Nigerian Naira (₦).
"""

from decimal import Decimal
from typing import Dict, Any, Set
from dataclasses import dataclass, field
from enum import Enum


# =============================================================================
# ENUMS (defined here to avoid circular imports)
# These are also exported from app.models.sku for backwards compatibility
# =============================================================================

class SKUTier(str, Enum):
    """
    Commercial SKU tiers for Tekvwa Pro Audit.
    
    Pricing in Nigerian Naira (₦):
    - CORE: ₦25,000 - ₦75,000/month
    - PROFESSIONAL: ₦150,000 - ₦400,000/month
    - ENTERPRISE: ₦1,000,000 - ₦5,000,000+/month
    """
    CORE = "core"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class IntelligenceAddon(str, Enum):
    """Intelligence add-on tiers (requires Professional or Enterprise base)."""
    NONE = "none"
    STANDARD = "standard"
    ADVANCED = "advanced"


class Feature(str, Enum):
    """All features that can be gated by SKU tier."""
    # Core features
    GL_ENABLED = "gl_enabled"
    CHART_OF_ACCOUNTS = "chart_of_accounts"
    JOURNAL_ENTRIES = "journal_entries"
    BASIC_REPORTS = "basic_reports"
    TAX_ENGINE_BASIC = "tax_engine_basic"
    CUSTOMER_MANAGEMENT = "customer_management"
    VENDOR_MANAGEMENT = "vendor_management"
    BASIC_INVOICING = "basic_invoicing"
    AUDIT_LOGS_STANDARD = "audit_logs_standard"
    INVENTORY_BASIC = "inventory_basic"
    # Professional features
    PAYROLL = "payroll"
    PAYROLL_ADVANCED = "payroll_advanced"
    BANK_RECONCILIATION = "bank_reconciliation"
    FIXED_ASSETS = "fixed_assets"
    EXPENSE_CLAIMS = "expense_claims"
    E_INVOICING = "e_invoicing"
    NRS_COMPLIANCE = "nrs_compliance"
    ADVANCED_REPORTS = "advanced_reports"
    RULE_BASED_ALERTS = "rule_based_alerts"
    MULTI_USER_RBAC = "multi_user_rbac"
    INVENTORY_ADVANCED = "inventory_advanced"
    DASHBOARD_ADVANCED = "dashboard_advanced"
    MULTI_CURRENCY = "multi_currency"             # FX, multi-currency transactions
    BUDGET_MANAGEMENT = "budget_management"       # Budget creation and tracking
    BUDGET_VARIANCE = "budget_variance"           # Budget vs Actual analysis
    # Enterprise features
    WORM_VAULT = "worm_vault"
    INTERCOMPANY = "intercompany"
    MULTI_ENTITY = "multi_entity"
    ATTESTATION = "attestation"
    DIGITAL_SIGNATURES = "digital_signatures"
    SOX_COMPLIANCE = "sox_compliance"
    IFRS_COMPLIANCE = "ifrs_compliance"
    FRCN_COMPLIANCE = "frcn_compliance"
    SEGREGATION_OF_DUTIES = "segregation_of_duties"
    FULL_API_ACCESS = "full_api_access"
    PRIORITY_SUPPORT = "priority_support"
    AUDIT_VAULT_EXTENDED = "audit_vault_extended"
    CONSOLIDATION = "consolidation"
    # Intelligence add-on features
    ML_ANOMALY_DETECTION = "ml_anomaly_detection"
    BENFORDS_LAW = "benfords_law"
    ZSCORE_ANALYSIS = "zscore_analysis"
    PREDICTIVE_FORECASTING = "predictive_forecasting"
    NLP_PROCESSING = "nlp_processing"
    OCR_EXTRACTION = "ocr_extraction"
    FRAUD_DETECTION = "fraud_detection"
    CUSTOM_ML_TRAINING = "custom_ml_training"
    BEHAVIORAL_ANALYTICS = "behavioral_analytics"


class UsageMetricType(str, Enum):
    """Types of usage metrics tracked for billing and limits."""
    TRANSACTIONS = "transactions"
    USERS = "users"
    ENTITIES = "entities"
    INVOICES = "invoices"
    API_CALLS = "api_calls"
    OCR_PAGES = "ocr_pages"
    STORAGE_MB = "storage_mb"
    ML_INFERENCES = "ml_inferences"
    EMPLOYEES = "employees"


# =============================================================================
# PRICING CONFIGURATION (Nigerian Naira)
# =============================================================================

@dataclass
class TierPricing:
    """Pricing configuration for a SKU tier."""
    tier: SKUTier
    
    # Base pricing
    monthly_min: Decimal
    monthly_max: Decimal
    annual_min: Decimal  # Typically 15% discount (10 months)
    annual_max: Decimal
    
    # Per-user pricing (for additional users beyond base)
    base_users_included: int
    price_per_additional_user: Decimal
    
    # Description
    name: str
    tagline: str
    target_market: str


# Tier Pricing (Naira)
TIER_PRICING: Dict[SKUTier, TierPricing] = {
    SKUTier.CORE: TierPricing(
        tier=SKUTier.CORE,
        monthly_min=Decimal("25000"),
        monthly_max=Decimal("75000"),
        annual_min=Decimal("255000"),   # ₦25,000 × 10.2 months
        annual_max=Decimal("765000"),   # ₦75,000 × 10.2 months
        base_users_included=5,
        price_per_additional_user=Decimal("5000"),
        name="Pro Audit Core",
        tagline="Essential accounting for Nigerian SMEs",
        target_market="Small businesses, sole practitioners, startups, POS operators",
    ),
    SKUTier.PROFESSIONAL: TierPricing(
        tier=SKUTier.PROFESSIONAL,
        monthly_min=Decimal("150000"),
        monthly_max=Decimal("400000"),
        annual_min=Decimal("1530000"),
        annual_max=Decimal("4080000"),
        base_users_included=10,
        price_per_additional_user=Decimal("10000"),
        name="Pro Audit Professional",
        tagline="Full-featured solution for growing businesses",
        target_market="Growing SMEs, accounting firms, manufacturing, retail chains",
    ),
    SKUTier.ENTERPRISE: TierPricing(
        tier=SKUTier.ENTERPRISE,
        monthly_min=Decimal("1000000"),
        monthly_max=Decimal("5000000"),
        annual_min=Decimal("10200000"),
        annual_max=Decimal("51000000"),
        base_users_included=50,
        price_per_additional_user=Decimal("15000"),
        name="Pro Audit Enterprise",
        tagline="Compliance-ready platform for large organizations",
        target_market="Multinationals, banks, oil & gas, NSE-listed companies, government",
    ),
}


@dataclass
class IntelligencePricing:
    """Pricing for Intelligence add-on."""
    addon: IntelligenceAddon
    monthly_min: Decimal
    monthly_max: Decimal
    name: str
    description: str
    requires_tier: SKUTier  # Minimum base tier required


INTELLIGENCE_PRICING: Dict[IntelligenceAddon, IntelligencePricing] = {
    IntelligenceAddon.NONE: IntelligencePricing(
        addon=IntelligenceAddon.NONE,
        monthly_min=Decimal("0"),
        monthly_max=Decimal("0"),
        name="No Intelligence Add-on",
        description="Base tier features only",
        requires_tier=SKUTier.CORE,
    ),
    IntelligenceAddon.STANDARD: IntelligencePricing(
        addon=IntelligenceAddon.STANDARD,
        monthly_min=Decimal("250000"),
        monthly_max=Decimal("500000"),
        name="Pro Audit Intelligence Standard",
        description="ML anomaly detection, Benford's Law, Z-Score, OCR, Forecasting",
        requires_tier=SKUTier.PROFESSIONAL,
    ),
    IntelligenceAddon.ADVANCED: IntelligencePricing(
        addon=IntelligenceAddon.ADVANCED,
        monthly_min=Decimal("500000"),
        monthly_max=Decimal("1000000"),
        name="Pro Audit Intelligence Advanced",
        description="Full ML suite including NLP, custom model training, behavioral analytics",
        requires_tier=SKUTier.PROFESSIONAL,
    ),
}


# =============================================================================
# USAGE LIMITS CONFIGURATION
# =============================================================================

@dataclass
class TierLimits:
    """Usage limits for a SKU tier."""
    tier: SKUTier
    
    # User and entity limits
    max_users: int  # -1 = unlimited
    max_entities: int  # -1 = unlimited
    
    # Transaction limits (per month)
    max_transactions_monthly: int
    max_invoices_monthly: int
    
    # API limits (per hour)
    api_calls_per_hour: int  # 0 = no API access
    api_read_only: bool  # True = read-only API access
    
    # Storage (MB)
    storage_limit_mb: int
    
    # Payroll
    max_employees: int
    
    # Audit log retention (days)
    audit_log_retention_days: int


TIER_LIMITS_CONFIG: Dict[SKUTier, TierLimits] = {
    SKUTier.CORE: TierLimits(
        tier=SKUTier.CORE,
        max_users=5,
        max_entities=1,
        max_transactions_monthly=10_000,
        max_invoices_monthly=100,
        api_calls_per_hour=0,
        api_read_only=True,
        storage_limit_mb=5_000,  # 5 GB
        max_employees=10,
        audit_log_retention_days=90,
    ),
    SKUTier.PROFESSIONAL: TierLimits(
        tier=SKUTier.PROFESSIONAL,
        max_users=25,
        max_entities=1,
        max_transactions_monthly=100_000,
        max_invoices_monthly=1_000,
        api_calls_per_hour=1_000,
        api_read_only=True,
        storage_limit_mb=50_000,  # 50 GB
        max_employees=500,
        audit_log_retention_days=365,
    ),
    SKUTier.ENTERPRISE: TierLimits(
        tier=SKUTier.ENTERPRISE,
        max_users=-1,  # Unlimited
        max_entities=-1,  # Unlimited
        max_transactions_monthly=1_000_000,
        max_invoices_monthly=-1,  # Unlimited
        api_calls_per_hour=10_000,
        api_read_only=False,
        storage_limit_mb=500_000,  # 500 GB
        max_employees=-1,  # Unlimited
        audit_log_retention_days=2555,  # 7 years (NTAA compliance)
    ),
}


@dataclass
class IntelligenceLimits:
    """Usage limits for Intelligence add-on features."""
    addon: IntelligenceAddon
    
    # OCR limits (per month)
    ocr_pages_monthly: int
    
    # ML inference limits (per day)
    ml_inferences_daily: int
    
    # Benford/Z-Score analysis limits (max records per run)
    max_analysis_records: int
    
    # Custom training
    custom_models_allowed: int


INTELLIGENCE_LIMITS_CONFIG: Dict[IntelligenceAddon, IntelligenceLimits] = {
    IntelligenceAddon.NONE: IntelligenceLimits(
        addon=IntelligenceAddon.NONE,
        ocr_pages_monthly=0,
        ml_inferences_daily=0,
        max_analysis_records=0,
        custom_models_allowed=0,
    ),
    IntelligenceAddon.STANDARD: IntelligenceLimits(
        addon=IntelligenceAddon.STANDARD,
        ocr_pages_monthly=1_000,
        ml_inferences_daily=10_000,
        max_analysis_records=100_000,
        custom_models_allowed=0,
    ),
    IntelligenceAddon.ADVANCED: IntelligenceLimits(
        addon=IntelligenceAddon.ADVANCED,
        ocr_pages_monthly=5_000,
        ml_inferences_daily=50_000,
        max_analysis_records=500_000,
        custom_models_allowed=5,
    ),
}


# =============================================================================
# FEATURE MAPPING CONFIGURATION
# =============================================================================

# Features available at each tier (cumulative - higher tiers include lower tier features)
CORE_FEATURES: Set[Feature] = {
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
}

PROFESSIONAL_FEATURES: Set[Feature] = CORE_FEATURES | {
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
}

ENTERPRISE_FEATURES: Set[Feature] = PROFESSIONAL_FEATURES | {
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
}

INTELLIGENCE_STANDARD_FEATURES: Set[Feature] = {
    Feature.ML_ANOMALY_DETECTION,
    Feature.BENFORDS_LAW,
    Feature.ZSCORE_ANALYSIS,
    Feature.PREDICTIVE_FORECASTING,
    Feature.OCR_EXTRACTION,
    Feature.FRAUD_DETECTION,
}

INTELLIGENCE_ADVANCED_FEATURES: Set[Feature] = INTELLIGENCE_STANDARD_FEATURES | {
    Feature.NLP_PROCESSING,
    Feature.CUSTOM_ML_TRAINING,
    Feature.BEHAVIORAL_ANALYTICS,
}


# =============================================================================
# FEATURE DESCRIPTIONS (For UI display)
# =============================================================================

FEATURE_DESCRIPTIONS: Dict[Feature, Dict[str, str]] = {
    # Core Features
    Feature.GL_ENABLED: {
        "name": "General Ledger",
        "description": "Full double-entry accounting with Nigerian chart of accounts templates",
        "icon": "book-open",
    },
    Feature.CHART_OF_ACCOUNTS: {
        "name": "Chart of Accounts",
        "description": "Customizable account structure with FRCN-compliant categories",
        "icon": "list",
    },
    Feature.JOURNAL_ENTRIES: {
        "name": "Journal Entries",
        "description": "Create, approve, and reverse journal entries",
        "icon": "edit",
    },
    Feature.BASIC_REPORTS: {
        "name": "Financial Reports",
        "description": "Trial Balance, Income Statement, Balance Sheet, Cash Flow",
        "icon": "file-text",
    },
    Feature.TAX_ENGINE_BASIC: {
        "name": "Tax Calculations",
        "description": "VAT, WHT calculations for Nigerian compliance",
        "icon": "calculator",
    },
    Feature.CUSTOMER_MANAGEMENT: {
        "name": "Customer Management",
        "description": "Customer records, aging reports, transaction history",
        "icon": "users",
    },
    Feature.VENDOR_MANAGEMENT: {
        "name": "Vendor Management",
        "description": "Vendor records, payment tracking, aging",
        "icon": "truck",
    },
    Feature.BASIC_INVOICING: {
        "name": "Invoicing",
        "description": "Create and send professional invoices",
        "icon": "file-invoice",
    },
    Feature.AUDIT_LOGS_STANDARD: {
        "name": "Audit Logs",
        "description": "Track user activities and changes",
        "icon": "shield",
    },
    Feature.INVENTORY_BASIC: {
        "name": "Basic Inventory",
        "description": "Stock tracking, reorder alerts",
        "icon": "package",
    },
    
    # Professional Features
    Feature.PAYROLL: {
        "name": "Payroll",
        "description": "Full Nigerian payroll with PAYE, Pension, NHF, NSITF",
        "icon": "credit-card",
    },
    Feature.PAYROLL_ADVANCED: {
        "name": "Advanced Payroll",
        "description": "Loans, multiple pay frequencies, bank file generation",
        "icon": "credit-card",
    },
    Feature.BANK_RECONCILIATION: {
        "name": "Bank Reconciliation",
        "description": "Auto-matching, Nigerian bank charge detection",
        "icon": "git-merge",
    },
    Feature.FIXED_ASSETS: {
        "name": "Fixed Assets",
        "description": "Asset register, depreciation, disposal tracking",
        "icon": "home",
    },
    Feature.EXPENSE_CLAIMS: {
        "name": "Expense Claims",
        "description": "Employee expense submission and approval",
        "icon": "receipt",
    },
    Feature.E_INVOICING: {
        "name": "E-Invoicing",
        "description": "Electronic invoice submission to FIRS",
        "icon": "send",
    },
    Feature.NRS_COMPLIANCE: {
        "name": "NRS Compliance",
        "description": "Nigerian Revenue Service integration",
        "icon": "check-circle",
    },
    Feature.ADVANCED_REPORTS: {
        "name": "Advanced Reports",
        "description": "Custom report builder, scheduled reports",
        "icon": "bar-chart",
    },
    Feature.RULE_BASED_ALERTS: {
        "name": "Alerts",
        "description": "Threshold alerts, duplicate detection",
        "icon": "bell",
    },
    Feature.MULTI_USER_RBAC: {
        "name": "Role-Based Access",
        "description": "Custom roles, department permissions",
        "icon": "lock",
    },
    
    # Enterprise Features
    Feature.WORM_VAULT: {
        "name": "WORM Audit Vault",
        "description": "Immutable storage for regulatory compliance",
        "icon": "database",
    },
    Feature.INTERCOMPANY: {
        "name": "Intercompany",
        "description": "Inter-entity transactions and eliminations",
        "icon": "git-branch",
    },
    Feature.MULTI_ENTITY: {
        "name": "Multi-Entity",
        "description": "Manage multiple business entities",
        "icon": "layers",
    },
    Feature.ATTESTATION: {
        "name": "Attestation",
        "description": "Document attestation workflows",
        "icon": "award",
    },
    Feature.DIGITAL_SIGNATURES: {
        "name": "Digital Signatures",
        "description": "Legally binding electronic signatures",
        "icon": "pen-tool",
    },
    Feature.SOX_COMPLIANCE: {
        "name": "SOX Compliance",
        "description": "Sarbanes-Oxley reporting support",
        "icon": "shield",
    },
    Feature.IFRS_COMPLIANCE: {
        "name": "IFRS Compliance",
        "description": "International Financial Reporting Standards",
        "icon": "globe",
    },
    Feature.FRCN_COMPLIANCE: {
        "name": "FRCN Compliance",
        "description": "Financial Reporting Council of Nigeria standards",
        "icon": "flag",
    },
    Feature.SEGREGATION_OF_DUTIES: {
        "name": "Segregation of Duties",
        "description": "SoD conflict detection and enforcement",
        "icon": "users",
    },
    Feature.FULL_API_ACCESS: {
        "name": "Full API Access",
        "description": "Read/write REST API for integrations",
        "icon": "code",
    },
    Feature.CONSOLIDATION: {
        "name": "Consolidation",
        "description": "Multi-entity financial consolidation",
        "icon": "git-merge",
    },
    
    # Intelligence Features
    Feature.ML_ANOMALY_DETECTION: {
        "name": "ML Anomaly Detection",
        "description": "AI-powered unusual transaction detection",
        "icon": "cpu",
    },
    Feature.BENFORDS_LAW: {
        "name": "Benford's Law Analysis",
        "description": "Statistical fraud detection",
        "icon": "trending-up",
    },
    Feature.ZSCORE_ANALYSIS: {
        "name": "Z-Score Analysis",
        "description": "Statistical outlier identification",
        "icon": "activity",
    },
    Feature.PREDICTIVE_FORECASTING: {
        "name": "Forecasting",
        "description": "ML-based revenue and expense predictions",
        "icon": "trending-up",
    },
    Feature.NLP_PROCESSING: {
        "name": "NLP Processing",
        "description": "Natural language document analysis",
        "icon": "message-square",
    },
    Feature.OCR_EXTRACTION: {
        "name": "OCR",
        "description": "Automatic invoice data extraction",
        "icon": "camera",
    },
    Feature.FRAUD_DETECTION: {
        "name": "Fraud Detection",
        "description": "Pattern-based fraud identification",
        "icon": "alert-triangle",
    },
    Feature.CUSTOM_ML_TRAINING: {
        "name": "Custom ML Models",
        "description": "Train models on your organization's data",
        "icon": "cpu",
    },
    Feature.BEHAVIORAL_ANALYTICS: {
        "name": "Behavioral Analytics",
        "description": "User behavior pattern analysis",
        "icon": "eye",
    },
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_tier_pricing(tier: SKUTier) -> TierPricing:
    """Get pricing configuration for a tier."""
    return TIER_PRICING[tier]


def get_tier_limits(tier: SKUTier) -> TierLimits:
    """Get usage limits for a tier."""
    return TIER_LIMITS_CONFIG[tier]


def get_intelligence_pricing(addon: IntelligenceAddon) -> IntelligencePricing:
    """Get pricing for intelligence add-on."""
    return INTELLIGENCE_PRICING[addon]


def get_intelligence_limits(addon: IntelligenceAddon) -> IntelligenceLimits:
    """Get limits for intelligence add-on."""
    return INTELLIGENCE_LIMITS_CONFIG[addon]


def get_features_for_tier(tier: SKUTier) -> Set[Feature]:
    """Get all features available for a tier."""
    mapping = {
        SKUTier.CORE: CORE_FEATURES,
        SKUTier.PROFESSIONAL: PROFESSIONAL_FEATURES,
        SKUTier.ENTERPRISE: ENTERPRISE_FEATURES,
    }
    return mapping.get(tier, set())


def get_intelligence_features(addon: IntelligenceAddon) -> Set[Feature]:
    """Get features for intelligence add-on level."""
    mapping = {
        IntelligenceAddon.NONE: set(),
        IntelligenceAddon.STANDARD: INTELLIGENCE_STANDARD_FEATURES,
        IntelligenceAddon.ADVANCED: INTELLIGENCE_ADVANCED_FEATURES,
    }
    return mapping.get(addon, set())


def calculate_monthly_price(
    tier: SKUTier,
    user_count: int,
    intelligence: IntelligenceAddon = IntelligenceAddon.NONE,
) -> Decimal:
    """
    Calculate estimated monthly price based on tier and users.
    Returns minimum of range + per-user pricing for additional users.
    """
    tier_pricing = get_tier_pricing(tier)
    intel_pricing = get_intelligence_pricing(intelligence)
    
    # Base price
    base = tier_pricing.monthly_min
    
    # Additional users
    additional_users = max(0, user_count - tier_pricing.base_users_included)
    user_cost = additional_users * tier_pricing.price_per_additional_user
    
    # Intelligence add-on
    intel_cost = intel_pricing.monthly_min
    
    return base + user_cost + intel_cost


def format_naira(amount: Decimal) -> str:
    """Format amount as Nigerian Naira."""
    return f"₦{amount:,.2f}"


def get_tier_display_name(tier: SKUTier) -> str:
    """
    Get display name for a SKU tier.
    
    Args:
        tier: The SKU tier enum value
        
    Returns:
        Human-readable display name (e.g., "Professional")
    """
    return {
        SKUTier.CORE: "Core",
        SKUTier.PROFESSIONAL: "Professional",
        SKUTier.ENTERPRISE: "Enterprise",
    }.get(tier, "Core")


def get_tier_badge_class(tier: SKUTier) -> str:
    """
    Get CSS class for tier badge styling.
    
    Args:
        tier: The SKU tier enum value
        
    Returns:
        Tailwind CSS classes for badge
    """
    return {
        SKUTier.CORE: "bg-gray-100 text-gray-800",
        SKUTier.PROFESSIONAL: "bg-blue-100 text-blue-800",
        SKUTier.ENTERPRISE: "bg-purple-100 text-purple-800",
    }.get(tier, "bg-gray-100 text-gray-800")


def get_tier_description(tier: SKUTier) -> str:
    """
    Get description/tagline for a SKU tier.
    
    Args:
        tier: The SKU tier enum value
        
    Returns:
        Short description of tier
    """
    pricing = TIER_PRICING.get(tier)
    if pricing:
        return pricing.tagline
    return "Essential accounting features"
