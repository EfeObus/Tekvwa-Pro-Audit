"""
Tekvwa Pro Audit - SKU Enums

Re-exports SKU enums from app.config.sku_config for use in models.
The enums are defined in sku_config to avoid circular imports.

Nigerian Market Pricing (Naira):
- CORE: ₦25,000 - ₦75,000/month
- PROFESSIONAL: ₦150,000 - ₦400,000/month
- ENTERPRISE: ₦1,000,000 - ₦5,000,000+/month
- Intelligence Add-on: ₦250,000 - ₦1,000,000/month
"""

from enum import Enum


# These need to be defined here as well (not imported from config) to avoid
# circular imports. The config module uses these and is imported before models.

class SKUTier(str, Enum):
    """
    Commercial SKU tiers for Tekvwa Pro Audit.
    
    Pricing in Nigerian Naira (₦):
    - CORE: ₦25,000 - ₦75,000/month
    - PROFESSIONAL: ₦150,000 - ₦400,000/month
    - ENTERPRISE: ₦1,000,000 - ₦5,000,000+/month
    """
    CORE = "core"                    # Basic accounting for SMEs
    PROFESSIONAL = "professional"    # Full features for growing businesses
    ENTERPRISE = "enterprise"        # Multi-entity, compliance, WORM vault


class IntelligenceAddon(str, Enum):
    """
    Intelligence add-on tiers (requires Professional or Enterprise base).
    
    Pricing: ₦250,000 - ₦1,000,000/month
    """
    NONE = "none"           # No ML/AI features
    STANDARD = "standard"   # Basic ML features (₦250,000-500,000/mo)
    ADVANCED = "advanced"   # Full ML + custom training (₦500,000-1,000,000/mo)


class Feature(str, Enum):
    """
    All features that can be gated by SKU tier.
    Feature flags for controlling access to functionality.
    """
    # ===========================================
    # CORE TIER FEATURES (₦25,000-75,000/mo)
    # ===========================================
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
    
    # ===========================================
    # PROFESSIONAL TIER FEATURES (₦150,000-400,000/mo)
    # ===========================================
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
    MULTI_CURRENCY = "multi_currency"           # FX, multi-currency transactions
    BUDGET_MANAGEMENT = "budget_management"     # Budget creation and tracking
    BUDGET_VARIANCE = "budget_variance"         # Budget vs Actual analysis
    
    # ===========================================
    # ENTERPRISE TIER FEATURES (₦1,000,000-5,000,000+/mo)
    # ===========================================
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
    
    # ===========================================
    # INTELLIGENCE ADD-ON FEATURES (₦250,000-1,000,000/mo)
    # ===========================================
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
    EMPLOYEES = "employees"  # For payroll


class BillingCycle(str, Enum):
    """Billing cycle options."""
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
