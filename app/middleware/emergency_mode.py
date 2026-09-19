"""
Tekvwa Pro Audit - Emergency Mode Middleware

FastAPI middleware for enforcing emergency platform controls:
1. Read-only mode (blocks write operations)
2. Maintenance mode (blocks all non-admin access)
3. Login lockdown (blocks all logins except Super Admin)
4. Feature kill switches (blocks disabled features)

Integrates with PlatformStatus model and EmergencyControlService.
"""

import logging
import re
from datetime import datetime
from typing import Callable, Optional, Set, Dict, Any

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse, HTMLResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


# ============================================================================
# EMERGENCY MODE MIDDLEWARE
# ============================================================================

class EmergencyModeMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce platform emergency controls.
    
    Features:
    - Read-only mode: Blocks all POST/PUT/PATCH/DELETE requests (except Super Admin)
    - Maintenance mode: Blocks all non-admin access, shows maintenance page
    - Login lockdown: Blocks all login attempts except Super Admin
    - Feature kill switches: Blocks access to specific disabled features
    
    The middleware checks PlatformStatus from a cached state (updated periodically)
    to avoid database queries on every request.
    """
    
    # Paths always exempt from emergency controls (health checks, static files)
    ALWAYS_EXEMPT_PATHS = [
        "/health",
        "/api/v1/health",
        "/static",
        "/favicon.ico",
        "/docs",
        "/openapi.json",
        "/redoc",
    ]
    
    # Admin paths that bypass emergency controls
    ADMIN_EXEMPT_PATHS = [
        "/api/v1/admin",
        "/admin",
        "/super-admin",
    ]
    
    # Paths for authentication (selectively controlled by login lockdown)
    AUTH_PATHS = [
        "/api/v1/auth/login",
        "/api/v1/auth/token",
        "/auth/login",
        "/login",
    ]
    
    # HTTP methods considered "write" operations
    WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
    
    # Feature path mappings for kill switches
    FEATURE_PATHS: Dict[str, list] = {
        "payments": ["/api/v1/payments", "/payments"],
        "invoicing": ["/api/v1/invoices", "/invoicing"],
        "payroll": ["/api/v1/payroll", "/payroll"],
        "bank_reconciliation": ["/api/v1/bank-reconciliation", "/bank-reconciliation"],
        "expense_claims": ["/api/v1/expense-claims", "/expense-claims"],
        "tax_filing": ["/api/v1/tax", "/tax"],
        "audit_reports": ["/api/v1/audit-reports", "/audit-reports"],
        "user_registration": ["/api/v1/auth/register", "/register"],
        "api_access": ["/api/v1"],
        "exports": ["/api/v1/export", "/export"],
        "file_uploads": ["/api/v1/upload", "/upload"],
        "integrations": ["/api/v1/integrations", "/integrations"],
        "ml_inference": ["/api/v1/ml", "/ml", "/api/v1/anomaly"],
        "notifications": ["/api/v1/notifications", "/notifications"],
    }
    
    def __init__(
        self,
        app,
        enabled: bool = True,
        development_mode: bool = False,
    ):
        super().__init__(app)
        self.enabled = enabled
        self.development_mode = development_mode
        
        # Cached platform status (updated by background task or service)
        self._platform_status = {
            "is_read_only": False,
            "is_maintenance_mode": False,
            "is_login_locked": False,
            "disabled_features": [],
            "maintenance_message": None,
            "read_only_message": None,
            "last_updated": datetime.utcnow(),
        }
    
    def update_status(
        self,
        is_read_only: bool = None,
        is_maintenance_mode: bool = None,
        is_login_locked: bool = None,
        disabled_features: list = None,
        maintenance_message: str = None,
        read_only_message: str = None,
    ):
        """
        Update cached platform status.
        
        Called by EmergencyControlService or background task
        when platform status changes.
        """
        if is_read_only is not None:
            self._platform_status["is_read_only"] = is_read_only
        if is_maintenance_mode is not None:
            self._platform_status["is_maintenance_mode"] = is_maintenance_mode
        if is_login_locked is not None:
            self._platform_status["is_login_locked"] = is_login_locked
        if disabled_features is not None:
            self._platform_status["disabled_features"] = disabled_features
        if maintenance_message is not None:
            self._platform_status["maintenance_message"] = maintenance_message
        if read_only_message is not None:
            self._platform_status["read_only_message"] = read_only_message
        
        self._platform_status["last_updated"] = datetime.utcnow()
        
        logger.info(f"Platform status updated: {self._platform_status}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current cached platform status."""
        return self._platform_status.copy()
    
    def _is_super_admin_request(self, request: Request) -> bool:
        """
        Check if request is from a Super Admin.
        
        In production, this should check:
        1. JWT token claims for is_super_admin=True
        2. Session data for super admin role
        
        For middleware, we use a lightweight check based on
        a custom header or cookie that's set after auth verification.
        """
        # Check for super admin indicator in request state (set by auth middleware)
        if hasattr(request.state, "is_super_admin") and request.state.is_super_admin:
            return True
        
        # Check for super admin header (set by previous middleware)
        if request.headers.get("X-Super-Admin-Verified") == "true":
            return True
        
        # Check for super admin cookie (alternative verification)
        if request.cookies.get("sa_verified") == "true":
            return True
        
        return False
    
    def _is_exempt_path(self, path: str) -> bool:
        """Check if path is always exempt from emergency controls."""
        for exempt in self.ALWAYS_EXEMPT_PATHS:
            if path.startswith(exempt):
                return True
        return False
    
    def _is_admin_path(self, path: str) -> bool:
        """Check if path is an admin path (exempt for admins)."""
        for admin_path in self.ADMIN_EXEMPT_PATHS:
            if path.startswith(admin_path):
                return True
        return False
    
    def _is_auth_path(self, path: str) -> bool:
        """Check if path is an authentication path."""
        for auth_path in self.AUTH_PATHS:
            if path.startswith(auth_path):
                return True
        return False
    
    def _get_feature_for_path(self, path: str) -> Optional[str]:
        """Get the feature key for a given path."""
        for feature, paths in self.FEATURE_PATHS.items():
            for feature_path in paths:
                if path.startswith(feature_path):
                    return feature
        return None
    
    def _maintenance_response(self, request: Request) -> Response:
        """Generate maintenance mode response."""
        message = self._platform_status.get("maintenance_message") or \
            "The platform is currently undergoing maintenance. Please try again later."
        
        # Return JSON for API requests
        if request.url.path.startswith("/api/"):
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "success": False,
                    "error": {
                        "code": 503,
                        "message": message,
                        "type": "maintenance_mode",
                    }
                }
            )
        
        # Return HTML for web requests
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Tekvwa Pro Audit - Maintenance</title>
            <style>
                body {{ font-family: 'Segoe UI', sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: linear-gradient(135deg, #1e3a5f 0%, #0d1b2a 100%); color: white; }}
                .container {{ text-align: center; padding: 40px; }}
                .icon {{ font-size: 80px; margin-bottom: 20px; }}
                h1 {{ margin: 0 0 20px 0; font-weight: 300; }}
                p {{ color: #a0aec0; max-width: 400px; margin: 0 auto; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="icon" style="font-size: 80px;">&#x1F527;</div>
                <h1>Under Maintenance</h1>
                <p>{message}</p>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(
            content=html_content,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    
    def _read_only_response(self, request: Request) -> Response:
        """Generate read-only mode response."""
        message = self._platform_status.get("read_only_message") or \
            "The platform is currently in read-only mode. Write operations are temporarily disabled."
        
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "success": False,
                "error": {
                    "code": 403,
                    "message": message,
                    "type": "read_only_mode",
                }
            }
        )
    
    def _login_locked_response(self, request: Request) -> Response:
        """Generate login lockdown response."""
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "success": False,
                "error": {
                    "code": 503,
                    "message": "Login is temporarily disabled. Please try again later.",
                    "type": "login_lockdown",
                }
            }
        )
    
    def _feature_disabled_response(self, request: Request, feature: str) -> Response:
        """Generate feature disabled response."""
        feature_display = feature.replace("_", " ").title()
        
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "success": False,
                "error": {
                    "code": 503,
                    "message": f"The {feature_display} feature is currently disabled.",
                    "type": "feature_disabled",
                    "feature": feature,
                }
            }
        )
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request through emergency controls."""
        
        # Skip if disabled or in development mode
        if not self.enabled or self.development_mode:
            return await call_next(request)
        
        path = request.url.path
        method = request.method
        
        # Always exempt paths (health checks, static files)
        if self._is_exempt_path(path):
            return await call_next(request)
        
        # Check if Super Admin - they bypass most controls
        is_super_admin = self._is_super_admin_request(request)
        
        # Admin paths are exempt for Super Admins
        if is_super_admin and self._is_admin_path(path):
            return await call_next(request)
        
        # === MAINTENANCE MODE ===
        if self._platform_status["is_maintenance_mode"]:
            # Only Super Admins can access during maintenance
            if not is_super_admin:
                logger.warning(f"Blocked request during maintenance: {method} {path}")
                return self._maintenance_response(request)
        
        # === LOGIN LOCKDOWN ===
        if self._platform_status["is_login_locked"]:
            if self._is_auth_path(path) and not is_super_admin:
                logger.warning(f"Blocked login attempt during lockdown: {path}")
                return self._login_locked_response(request)
        
        # === READ-ONLY MODE ===
        if self._platform_status["is_read_only"]:
            if method in self.WRITE_METHODS:
                # Super Admins can still write
                if not is_super_admin:
                    # Check if it's a safe read-only exempt path
                    # (e.g., login should still work for reading)
                    if not self._is_auth_path(path):
                        logger.warning(f"Blocked write operation in read-only mode: {method} {path}")
                        return self._read_only_response(request)
        
        # === FEATURE KILL SWITCHES ===
        disabled_features = self._platform_status.get("disabled_features", [])
        if disabled_features:
            feature = self._get_feature_for_path(path)
            if feature and feature in disabled_features:
                # Super Admins can still access disabled features
                if not is_super_admin:
                    logger.warning(f"Blocked access to disabled feature '{feature}': {path}")
                    return self._feature_disabled_response(request, feature)
        
        # All checks passed, continue to route handler
        return await call_next(request)


# ============================================================================
# MIDDLEWARE FACTORY
# ============================================================================

# Global reference to middleware instance (for status updates)
_emergency_middleware_instance: Optional[EmergencyModeMiddleware] = None


def get_emergency_middleware() -> Optional[EmergencyModeMiddleware]:
    """Get the global emergency middleware instance."""
    return _emergency_middleware_instance


def create_emergency_middleware(
    app,
    enabled: bool = True,
    development_mode: bool = False,
) -> EmergencyModeMiddleware:
    """Create and register the emergency mode middleware."""
    global _emergency_middleware_instance
    
    middleware = EmergencyModeMiddleware(
        app,
        enabled=enabled,
        development_mode=development_mode,
    )
    _emergency_middleware_instance = middleware
    
    logger.info(f"Emergency Mode Middleware initialized (enabled={enabled}, dev={development_mode})")
    
    return middleware


def update_emergency_status(
    is_read_only: bool = None,
    is_maintenance_mode: bool = None,
    is_login_locked: bool = None,
    disabled_features: list = None,
    maintenance_message: str = None,
    read_only_message: str = None,
):
    """
    Update the emergency middleware status.
    
    This function should be called by the EmergencyControlService
    whenever platform status changes.
    """
    middleware = get_emergency_middleware()
    if middleware:
        middleware.update_status(
            is_read_only=is_read_only,
            is_maintenance_mode=is_maintenance_mode,
            is_login_locked=is_login_locked,
            disabled_features=disabled_features,
            maintenance_message=maintenance_message,
            read_only_message=read_only_message,
        )
    else:
        logger.warning("Emergency middleware not initialized, status update ignored")
