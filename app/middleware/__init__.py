"""
Tekvwa Pro Audit - Middleware Package

Security and utility middleware for FastAPI.
"""

from app.middleware.security import (
    GeoFencingMiddleware,
    RateLimitingMiddleware,
    CSRFMiddleware,
    SecurityHeadersMiddleware,
    RequestLoggingMiddleware,
    AccountLockoutMiddleware,
    setup_security_middleware,
)

from app.middleware.sku_middleware import (
    SKUContextMiddleware,
    setup_sku_middleware,
    get_sku_template_context,
    has_feature,
    require_tier,
)

__all__ = [
    # Security middleware
    "GeoFencingMiddleware",
    "RateLimitingMiddleware",
    "CSRFMiddleware",
    "SecurityHeadersMiddleware",
    "RequestLoggingMiddleware",
    "AccountLockoutMiddleware",
    "setup_security_middleware",
    # SKU middleware
    "SKUContextMiddleware",
    "setup_sku_middleware",
    "get_sku_template_context",
    "has_feature",
    "require_tier",
]