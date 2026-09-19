"""
Tekvwa Pro Audit - Security Middleware

FastAPI middleware for:
1. Geo-Fencing (Nigeria-First)
2. Rate Limiting (SlowAPI)
3. CSRF Protection (HTMX)
4. Content Security Policy
5. Security Headers
6. Request Logging
"""

import time
import logging
from datetime import datetime
from typing import Callable, Dict, Optional
from collections import defaultdict

from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.utils.ndpa_security import (
    get_geo_service,
    rate_limit_config,
    CSRFTokenManager,
    CSPBuilder,
    AccountLockoutManager,
)

logger = logging.getLogger(__name__)


# ============================================================================
# GEO-FENCING MIDDLEWARE
# ============================================================================

class GeoFencingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce Nigeria-first access control.
    
    Features:
    - Block non-Nigerian IPs by default
    - Allow authorized diaspora users
    - Development mode bypass
    - Whitelist for health checks
    """
    
    EXEMPT_PATHS = [
        "/health",
        "/api",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/static",
    ]
    
    def __init__(self, app: FastAPI, enabled: bool = True, development_mode: bool = False):
        super().__init__(app)
        self.enabled = enabled
        self.development_mode = development_mode
        self.geo_service = get_geo_service()
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip if disabled or in development
        if not self.enabled or self.development_mode:
            return await call_next(request)
        
        # Skip exempt paths
        path = request.url.path
        for exempt in self.EXEMPT_PATHS:
            if path.startswith(exempt):
                return await call_next(request)
        
        # Check geolocation
        client_ip = self.geo_service.get_client_ip(request)
        
        # Check if user is authorized diaspora (from session/token)
        is_diaspora = False
        # In production, check user's diaspora_authorized flag from token
        
        allowed, reason, risk_score = await self.geo_service.check_access(
            ip=client_ip,
            is_diaspora_authorized=is_diaspora,
        )
        
        if not allowed:
            logger.warning(f"Geo-blocked access from {client_ip}: {reason}")
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "success": False,
                    "error": {
                        "code": 403,
                        "message": "Access restricted to Nigerian IP addresses. Contact support if you're a Nigerian user abroad.",
                        "type": "geo_restricted",
                    }
                }
            )
        
        # Add geo info to request state
        request.state.client_ip = client_ip
        request.state.geo_risk_score = risk_score
        
        return await call_next(request)


# ============================================================================
# RATE LIMITING MIDDLEWARE
# ============================================================================

class RateLimitingMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using in-memory storage.
    
    Features:
    - Per-IP rate limiting
    - Per-endpoint configuration
    - Graceful degradation in development
    - Redis-compatible for production
    """
    
    def __init__(
        self,
        app: FastAPI,
        enabled: bool = True,
        development_mode: bool = False,
        multiplier: float = 1.0,
    ):
        super().__init__(app)
        self.enabled = enabled
        self.development_mode = development_mode
        self.multiplier = multiplier if not development_mode else 10.0  # 10x in dev
        
        # In-memory storage: {ip: {path: [(timestamp, count)]}}
        self._requests: Dict[str, Dict[str, list]] = defaultdict(lambda: defaultdict(list))
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self.enabled:
            return await call_next(request)
        
        client_ip = getattr(request.state, 'client_ip', request.client.host if request.client else '127.0.0.1')
        path = request.url.path
        
        # Get limit for this path
        requests_limit, window_seconds = rate_limit_config.get_limit(path)
        
        # Apply multiplier
        requests_limit = int(requests_limit * self.multiplier)
        
        # Check rate limit
        is_limited, retry_after = self._check_rate_limit(
            client_ip, path, requests_limit, window_seconds
        )
        
        if is_limited:
            logger.warning(f"Rate limit exceeded for {client_ip} on {path}")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={"Retry-After": str(retry_after)},
                content={
                    "success": False,
                    "error": {
                        "code": 429,
                        "message": f"Too many requests. Please try again in {retry_after} seconds.",
                        "type": "rate_limited",
                        "retry_after": retry_after,
                    }
                }
            )
        
        # Record this request
        self._record_request(client_ip, path)
        
        # Add rate limit headers
        response = await call_next(request)
        remaining = self._get_remaining(client_ip, path, requests_limit, window_seconds)
        response.headers["X-RateLimit-Limit"] = str(requests_limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + window_seconds)
        
        return response
    
    def _check_rate_limit(
        self,
        ip: str,
        path: str,
        limit: int,
        window: int,
    ) -> tuple:
        """Check if request is rate limited."""
        now = time.time()
        cutoff = now - window
        
        # Clean old entries
        self._requests[ip][path] = [
            t for t in self._requests[ip][path] if t > cutoff
        ]
        
        count = len(self._requests[ip][path])
        
        if count >= limit:
            # Calculate retry-after
            oldest = min(self._requests[ip][path]) if self._requests[ip][path] else now
            retry_after = int(oldest + window - now)
            return True, max(1, retry_after)
        
        return False, 0
    
    def _record_request(self, ip: str, path: str):
        """Record a request timestamp."""
        self._requests[ip][path].append(time.time())
    
    def _get_remaining(self, ip: str, path: str, limit: int, window: int) -> int:
        """Get remaining requests in window."""
        now = time.time()
        cutoff = now - window
        
        count = len([t for t in self._requests[ip][path] if t > cutoff])
        return limit - count


# ============================================================================
# CSRF PROTECTION MIDDLEWARE
# ============================================================================

class CSRFMiddleware(BaseHTTPMiddleware):
    """
    CSRF protection middleware for HTMX.
    
    Features:
    - Double-submit cookie pattern
    - Session-bound tokens
    - SameSite=Strict cookies
    - HTMX header integration
    """
    
    SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
    EXEMPT_PATHS = [
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/health",
        "/api",
        "/select-entity",  # Entity selection just sets a cookie
    ]
    
    def __init__(
        self,
        app: FastAPI,
        enabled: bool = True,
        development_mode: bool = False,
    ):
        super().__init__(app)
        self.enabled = enabled
        self.development_mode = development_mode
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip if disabled
        if not self.enabled:
            return await call_next(request)
        
        # Skip safe methods
        if request.method in self.SAFE_METHODS:
            response = await call_next(request)
            return self._set_csrf_cookie(response, request)
        
        # Skip exempt paths
        path = request.url.path
        for exempt in self.EXEMPT_PATHS:
            if path.startswith(exempt):
                response = await call_next(request)
                return self._set_csrf_cookie(response, request)
        
        # Skip API-only requests (Bearer token auth)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return await call_next(request)
        
        # Validate CSRF token
        cookie_token = request.cookies.get(CSRFTokenManager.COOKIE_NAME)
        header_token = request.headers.get(CSRFTokenManager.TOKEN_HEADER)
        
        # Also check form data for traditional forms
        if not header_token:
            # For form submissions, token might be in body
            # This is handled by the specific endpoint
            pass
        
        if not self.development_mode:
            if not CSRFTokenManager.validate_double_submit(cookie_token, header_token):
                logger.warning(f"CSRF validation failed for {path}")
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "success": False,
                        "error": {
                            "code": 403,
                            "message": "CSRF token validation failed. Please refresh and try again.",
                            "type": "csrf_error",
                        }
                    }
                )
        
        response = await call_next(request)
        return self._set_csrf_cookie(response, request)
    
    def _set_csrf_cookie(self, response: Response, request: Request) -> Response:
        """Set CSRF cookie if not present."""
        if CSRFTokenManager.COOKIE_NAME not in request.cookies:
            token = CSRFTokenManager.generate_token()
            response.set_cookie(
                key=CSRFTokenManager.COOKIE_NAME,
                value=token,
                httponly=False,  # JavaScript needs to read it
                samesite="strict",
                secure=not self.development_mode,
                max_age=86400,  # 24 hours
            )
        return response


# ============================================================================
# SECURITY HEADERS MIDDLEWARE
# ============================================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add security headers to all responses.
    
    Headers:
    - Content-Security-Policy
    - X-Content-Type-Options
    - X-Frame-Options
    - X-XSS-Protection
    - Strict-Transport-Security
    - Referrer-Policy
    - Permissions-Policy
    """
    
    def __init__(
        self,
        app: FastAPI,
        csp_policy: Optional[str] = None,
        development_mode: bool = False,
    ):
        super().__init__(app)
        self.development_mode = development_mode
        
        # Build CSP
        csp = CSPBuilder()
        csp.add_nrs_integration()
        csp.add_nibss_integration()
        csp.add_htmx_support()
        csp.add_tailwind_support()
        csp.add_alpinejs_support()
        self.csp_policy = csp_policy or csp.build()
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # Skip for static files
        if request.url.path.startswith("/static"):
            return response
        
        # Content Security Policy
        response.headers["Content-Security-Policy"] = self.csp_policy
        
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        
        # XSS Protection (legacy, but still useful)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # HSTS (only in production)
        if not self.development_mode:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Referrer Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Permissions Policy
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(self), payment=(self)"
        )
        
        return response


# ============================================================================
# REQUEST LOGGING MIDDLEWARE
# ============================================================================

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Log all requests for security monitoring.
    
    Logs:
    - Request method and path
    - Client IP and user agent
    - Response status and timing
    - Security-relevant headers
    """
    
    SENSITIVE_PATHS = [
        "/api/v1/auth",
        "/api/v1/payroll",
        "/api/v1/tax",
    ]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        
        # Get request details
        client_ip = getattr(request.state, 'client_ip', request.client.host if request.client else 'unknown')
        user_agent = request.headers.get("User-Agent", "unknown")
        path = request.url.path
        method = request.method
        
        # Process request
        response = await call_next(request)
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Log request
        log_level = logging.WARNING if response.status_code >= 400 else logging.INFO
        
        is_sensitive = any(path.startswith(p) for p in self.SENSITIVE_PATHS)
        
        if is_sensitive or response.status_code >= 400:
            logger.log(
                log_level,
                f"{method} {path} - {response.status_code} - {duration:.3f}s - {client_ip}",
                extra={
                    "method": method,
                    "path": path,
                    "status": response.status_code,
                    "duration": duration,
                    "client_ip": client_ip,
                    "user_agent": user_agent[:100],
                }
            )
        
        # Add timing header
        response.headers["X-Response-Time"] = f"{duration:.3f}s"
        
        return response


# ============================================================================
# ACCOUNT LOCKOUT MIDDLEWARE
# ============================================================================

class AccountLockoutMiddleware(BaseHTTPMiddleware):
    """
    Check account lockout before processing auth requests.
    """
    
    AUTH_PATHS = [
        "/api/v1/auth/login",
    ]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        
        # Only check for auth paths
        if path not in self.AUTH_PATHS:
            return await call_next(request)
        
        # Get identifier (IP for now, could be email from body)
        client_ip = getattr(request.state, 'client_ip', request.client.host if request.client else '127.0.0.1')
        
        # Check lockout
        is_locked, seconds_remaining = AccountLockoutManager.is_locked_out(client_ip)
        
        if is_locked:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={"Retry-After": str(seconds_remaining)},
                content={
                    "success": False,
                    "error": {
                        "code": 429,
                        "message": f"Account temporarily locked. Try again in {seconds_remaining} seconds.",
                        "type": "account_locked",
                        "retry_after": seconds_remaining,
                    }
                }
            )
        
        return await call_next(request)


# ============================================================================
# SETUP FUNCTION
# ============================================================================

def setup_security_middleware(
    app: FastAPI,
    development_mode: bool = False,
    geo_fencing_enabled: bool = True,
    rate_limiting_enabled: bool = True,
    csrf_enabled: bool = True,
):
    """
    Setup all security middleware for the application.
    
    Args:
        app: FastAPI application instance
        development_mode: If True, relaxes some security checks
        geo_fencing_enabled: Enable geo-fencing (Nigeria-first)
        rate_limiting_enabled: Enable rate limiting
        csrf_enabled: Enable CSRF protection
    """
    # Order matters! Later middleware wraps earlier ones
    
    # 1. Request logging (outermost - logs everything)
    app.add_middleware(RequestLoggingMiddleware)
    
    # 2. Security headers
    app.add_middleware(
        SecurityHeadersMiddleware,
        development_mode=development_mode,
    )
    
    # 3. CSRF protection
    if csrf_enabled:
        app.add_middleware(
            CSRFMiddleware,
            enabled=True,
            development_mode=development_mode,
        )
    
    # 4. Account lockout
    app.add_middleware(AccountLockoutMiddleware)
    
    # 5. Rate limiting
    if rate_limiting_enabled:
        app.add_middleware(
            RateLimitingMiddleware,
            enabled=True,
            development_mode=development_mode,
        )
    
    # 6. Geo-fencing (innermost for API - first check)
    if geo_fencing_enabled:
        app.add_middleware(
            GeoFencingMiddleware,
            enabled=True,
            development_mode=development_mode,
        )
    
    logger.info(
        f"Security middleware configured: "
        f"geo_fencing={geo_fencing_enabled}, "
        f"rate_limiting={rate_limiting_enabled}, "
        f"csrf={csrf_enabled}, "
        f"development_mode={development_mode}"
    )
