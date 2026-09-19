"""
Tekvwa Pro Audit - Configuration Package

Application configuration modules.
"""

# Re-export settings from the old config.py module
# This allows both `from app.config import settings` and 
# `from app.config.sku_config import ...` to work
import sys
import os

# Import settings from the config.py file (not this package)
# We need to be careful about the import order to avoid circular imports
_config_module_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.py')
if os.path.exists(_config_module_path):
    import importlib.util
    _spec = importlib.util.spec_from_file_location("app_config_settings", _config_module_path)
    _settings_module = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_settings_module)
    settings = _settings_module.settings
    Settings = _settings_module.Settings
    get_settings = _settings_module.get_settings
else:
    # Fallback - this shouldn't happen
    settings = None
    Settings = None
    get_settings = None

from app.config.sku_config import (
    TIER_PRICING,
    INTELLIGENCE_PRICING,
    TIER_LIMITS_CONFIG,
    INTELLIGENCE_LIMITS_CONFIG,
    FEATURE_DESCRIPTIONS,
    get_tier_pricing,
    get_tier_limits,
    get_intelligence_pricing,
    get_intelligence_limits,
    get_features_for_tier,
    get_intelligence_features,
    calculate_monthly_price,
    format_naira,
)

__all__ = [
    # Settings
    "settings",
    "Settings",
    "get_settings",
    # SKU Config
    "TIER_PRICING",
    "INTELLIGENCE_PRICING",
    "TIER_LIMITS_CONFIG",
    "INTELLIGENCE_LIMITS_CONFIG",
    "FEATURE_DESCRIPTIONS",
    "get_tier_pricing",
    "get_tier_limits",
    "get_intelligence_pricing",
    "get_intelligence_limits",
    "get_features_for_tier",
    "get_intelligence_features",
    "calculate_monthly_price",
    "format_naira",
]
