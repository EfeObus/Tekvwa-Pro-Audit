"""
TekVwarho ProAudit - SKU Context Middleware

Middleware to inject SKU tier context into request state.
This allows templates and API responses to access tier information.

Also includes path-based feature gating - no need to modify individual endpoints.
"""

import logging
from typing import Optional, Set, Dict, List, Callable
from uuid import UUID
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from fastapi import status

from app.database import async_session_factory
from app.models.sku import Feature, SKUTier, IntelligenceAddon

logger = logging.getLogger(__name__)


# =============================================================================
# PATH-BASED FEATURE GATING CONFIGURATION
# =============================================================================

@dataclass
class PathFeatureGate:
    """Configuration for a feature gate on a path pattern."""
    path_prefix: str
    required_features: List[Feature]
    methods: Optional[Set[str]] = None  # None = all methods
    description: str = ""


# Define which paths require which features
# This is the central configuration - no need to modify endpoints
# NOTE: Paths with {entity_id} use contains-based matching for sub-routes
PATH_FEATURE_GATES: List[PathFeatureGate] = [
    # ===========================================
    # PROFESSIONAL TIER FEATURES (₦150,000+/mo)
    # ===========================================
    
    # Payroll
    PathFeatureGate(
        path_prefix="/api/v1/payroll",
        required_features=[Feature.PAYROLL],
        description="Payroll management requires Professional tier",
    ),
    PathFeatureGate(
        path_prefix="/payroll",
        required_features=[Feature.PAYROLL],
        description="Payroll views require Professional tier",
    ),
    
    # Bank Reconciliation - API mounted at /api/v1/entities/{entity_id}/bank-reconciliation
    PathFeatureGate(
        path_prefix="/bank-reconciliation",
        required_features=[Feature.BANK_RECONCILIATION],
        description="Bank reconciliation requires Professional tier",
    ),
    
    # Fixed Assets
    PathFeatureGate(
        path_prefix="/api/v1/fixed-assets",
        required_features=[Feature.FIXED_ASSETS],
        description="Fixed asset management requires Professional tier",
    ),
    PathFeatureGate(
        path_prefix="/fixed-assets",
        required_features=[Feature.FIXED_ASSETS],
        description="Fixed asset views require Professional tier",
    ),
    
    # Expense Claims - API mounted at /api/v1/entities/{entity_id}/expense-claims
    PathFeatureGate(
        path_prefix="/expense-claims",
        required_features=[Feature.EXPENSE_CLAIMS],
        description="Expense claims require Professional tier",
    ),
    
    # NRS / E-Invoicing
    PathFeatureGate(
        path_prefix="/api/v1/nrs",
        required_features=[Feature.NRS_COMPLIANCE],
        description="NRS compliance requires Professional tier",
    ),
    
    # Business Intelligence (Professional feature)
    PathFeatureGate(
        path_prefix="/api/v1/business-intelligence",
        required_features=[Feature.ADVANCED_REPORTS],
        description="Business Intelligence requires Professional tier",
    ),
    PathFeatureGate(
        path_prefix="/business-insights",
        required_features=[Feature.ADVANCED_REPORTS],
        description="Business Insights views require Professional tier",
    ),
    
    # ===========================================
    # ENTERPRISE TIER FEATURES (₦1,000,000+/mo)
    # ===========================================
    
    # WORM Audit Vault
    PathFeatureGate(
        path_prefix="/api/v1/audit/vault",
        required_features=[Feature.WORM_VAULT],
        description="WORM audit vault requires Enterprise tier",
    ),
    PathFeatureGate(
        path_prefix="/worm-storage",
        required_features=[Feature.WORM_VAULT],
        description="WORM storage views require Enterprise tier",
    ),
    
    # Advanced Audit System (Enterprise WORM + SoD features)
    PathFeatureGate(
        path_prefix="/api/audit-system",
        required_features=[Feature.WORM_VAULT],
        description="Advanced audit system requires Enterprise tier",
    ),
    
    # Advanced Audit - mounted at /api/v1/entities/{entity_id}/advanced-audit
    PathFeatureGate(
        path_prefix="/advanced-audit",
        required_features=[Feature.WORM_VAULT],
        description="Advanced audit requires Enterprise tier",
    ),
    
    # Intercompany - router uses /api/v1/advanced prefix
    PathFeatureGate(
        path_prefix="/api/v1/intercompany",
        required_features=[Feature.INTERCOMPANY],
        description="Intercompany transactions require Enterprise tier",
    ),
    PathFeatureGate(
        path_prefix="/api/v1/advanced/intercompany",
        required_features=[Feature.INTERCOMPANY],
        description="Intercompany transactions require Enterprise tier",
    ),
    
    # Consolidation
    PathFeatureGate(
        path_prefix="/api/v1/consolidation",
        required_features=[Feature.CONSOLIDATION],
        description="Financial consolidation requires Enterprise tier",
    ),
    
    # Segregation of Duties
    PathFeatureGate(
        path_prefix="/api/v1/sod",
        required_features=[Feature.SEGREGATION_OF_DUTIES],
        description="Segregation of Duties requires Enterprise tier",
    ),
    
    # Attestation & Digital Signatures
    PathFeatureGate(
        path_prefix="/attestation",
        required_features=[Feature.ATTESTATION],
        description="Attestation & signatures require Enterprise tier",
    ),
    
    # ===========================================
    # INTELLIGENCE ADD-ON FEATURES (₦250,000+/mo)
    # ===========================================
    
    # ML/AI
    PathFeatureGate(
        path_prefix="/api/v1/ml",
        required_features=[Feature.ML_ANOMALY_DETECTION],
        description="ML features require Intelligence add-on",
    ),
    
    # Forensic Audit - mounted at /api/v1/entities/{entity_id}/forensic-audit
    PathFeatureGate(
        path_prefix="/forensic-audit",
        required_features=[Feature.BENFORDS_LAW],
        description="Forensic audit requires Intelligence add-on",
    ),
    PathFeatureGate(
        path_prefix="/api/v1/audit/benfords",
        required_features=[Feature.BENFORDS_LAW],
        description="Benford's Law analysis requires Intelligence add-on",
    ),
    PathFeatureGate(
        path_prefix="/api/v1/audit/zscore",
        required_features=[Feature.ZSCORE_ANALYSIS],
        description="Z-Score analysis requires Intelligence add-on",
    ),
    
    # OCR
    PathFeatureGate(
        path_prefix="/api/v1/ocr",
        required_features=[Feature.OCR_EXTRACTION],
        description="OCR extraction requires Intelligence add-on",
    ),
    
    # Forecasting
    PathFeatureGate(
        path_prefix="/api/v1/forecast",
        required_features=[Feature.PREDICTIVE_FORECASTING],
        description="Forecasting requires Intelligence add-on",
    ),
]

# Paths exempt from feature checks
EXEMPT_PREFIXES: List[str] = [
    "/static/",
    "/api/docs",
    "/api/redoc",
    "/openapi.json",
    "/health",
    "/favicon.ico",
    "/login",
    "/logout",
    "/register",
    "/api/v1/auth/",
    "/api/v1/billing/",  # Allow billing endpoints during suspension
    "/checkout",
    "/pricing",
    "/payment-success",
    "/payment-failed",
    "/",
]

# Paths that require active subscription (not suspended)
SUBSCRIPTION_REQUIRED_PREFIXES: List[str] = [
    "/api/v1/",
    "/dashboard",
    "/transactions",
    "/invoices",
    "/sales",
    "/reports",
    "/audit",
    "/payroll",
    "/accounting",
    "/inventory",
    "/customers",
    "/vendors",
    "/fixed-assets",
    "/bank-reconciliation",
    "/expense-claims",
    "/tax-2026",
    "/business-insights",
    "/receipts",
    "/settings",  # Settings allowed except billing
]

# Paths exempt from subscription status check
SUBSCRIPTION_EXEMPT_PREFIXES: List[str] = [
    "/static/",
    "/api/docs",
    "/api/redoc",
    "/openapi.json",
    "/health",
    "/favicon.ico",
    "/login",
    "/logout",
    "/register",
    "/api/v1/auth/",
    "/api/v1/billing/",  # Always allow billing operations
    "/checkout",
    "/pricing",
    "/payment-success",
    "/payment-failed",
    "/select-entity",
    "/",
]


class SKUContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware that injects SKU context into request state.
    
    After this middleware runs, request.state will have:
    - sku_tier: The organization's SKU tier (or None if not authenticated)
    - sku_intelligence: Intelligence add-on level
    - sku_features: Set of enabled feature names
    - sku_loaded: Boolean indicating if SKU was loaded
    
    Usage in routes:
        @router.get("/dashboard")
        async def dashboard(request: Request):
            tier = request.state.sku_tier
            features = request.state.sku_features
            
            if "payroll" in features:
                # Show payroll widget
    
    Usage in templates:
        {% if 'payroll' in request.state.sku_features %}
            <a href="/payroll">Payroll</a>
        {% endif %}
    """
    
    async def dispatch(
        self, 
        request: Request, 
        call_next: RequestResponseEndpoint
    ) -> Response:
        # Initialize default SKU state
        request.state.sku_tier = None
        request.state.sku_intelligence = None
        request.state.sku_features = set()
        request.state.sku_loaded = False
        request.state.sku_is_trial = False
        
        # Skip SKU loading for static files and health checks
        if self._should_skip(request.url.path):
            return await call_next(request)
        
        try:
            # Try to get organization ID from various sources
            org_id = await self._get_organization_id(request)
            
            if org_id:
                await self._load_sku_context(request, org_id)
        except Exception as e:
            # Don't fail the request if SKU loading fails
            logger.warning(f"Failed to load SKU context: {e}")
        
        return await call_next(request)
    
    def _should_skip(self, path: str) -> bool:
        """Check if path should skip SKU loading."""
        skip_prefixes = [
            "/static/",
            "/api/docs",
            "/api/redoc",
            "/openapi.json",
            "/health",
            "/favicon.ico",
        ]
        return any(path.startswith(prefix) for prefix in skip_prefixes)
    
    async def _get_organization_id(self, request: Request) -> Optional[UUID]:
        """
        Try to get organization ID from the request context.
        
        Checks:
        1. Previously loaded user in request state
        2. JWT token from header or cookie
        """
        # Check if user was already loaded by auth middleware
        if hasattr(request.state, 'user') and request.state.user:
            user = request.state.user
            if hasattr(user, 'organization_id') and user.organization_id:
                return user.organization_id
        
        # Try to extract from JWT token
        token = self._extract_token(request)
        if token:
            from app.utils.security import verify_access_token
            payload = verify_access_token(token)
            if payload:
                org_id_str = payload.get("org_id") or payload.get("organization_id")
                if org_id_str:
                    try:
                        return UUID(org_id_str)
                    except ValueError:
                        pass
                
                # If org_id not in token, look up user
                user_id_str = payload.get("sub")
                if user_id_str:
                    return await self._lookup_user_org(user_id_str)
        
        return None
    
    def _extract_token(self, request: Request) -> Optional[str]:
        """Extract JWT token from request."""
        # Try Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:]
        
        # Try cookie
        token = request.cookies.get("access_token")
        if token:
            if token.startswith("Bearer "):
                return token[7:]
            return token
        
        return None
    
    async def _lookup_user_org(self, user_id_str: str) -> Optional[UUID]:
        """Look up user's organization ID from database."""
        try:
            from sqlalchemy import select
            from app.models.user import User
            
            user_id = UUID(user_id_str)
            
            async with async_session_factory() as db:
                result = await db.execute(
                    select(User.organization_id).where(User.id == user_id)
                )
                org_id = result.scalar_one_or_none()
                return org_id
        except Exception as e:
            logger.debug(f"Failed to lookup user organization: {e}")
            return None
    
    async def _load_sku_context(self, request: Request, org_id: UUID) -> None:
        """Load SKU context for an organization."""
        from app.services.feature_flags import FeatureFlagService
        
        async with async_session_factory() as db:
            service = FeatureFlagService(db)
            
            # Get tenant SKU
            tenant_sku = await service.get_tenant_sku(org_id)
            
            if tenant_sku:
                request.state.sku_tier = tenant_sku.tier.value
                request.state.sku_intelligence = tenant_sku.intelligence_addon.value
                request.state.sku_is_trial = tenant_sku.is_trial
            else:
                # Default to CORE tier
                request.state.sku_tier = SKUTier.CORE.value
                request.state.sku_intelligence = IntelligenceAddon.NONE.value
                request.state.sku_is_trial = False
            
            # Get enabled features
            features = await service.get_enabled_features(org_id)
            request.state.sku_features = {f.value for f in features}
            
            request.state.sku_loaded = True
            request.state.sku_org_id = org_id
            
            # Load subscription status for grace period/suspension checking
            await self._load_subscription_status(request, org_id, db)
            
            # Record API call metering for /api/ paths
            if request.url.path.startswith("/api/v1/"):
                await self._record_api_call(request, org_id, db)
    
    async def _load_subscription_status(
        self,
        request: Request,
        org_id: UUID,
        db,
    ) -> None:
        """Load subscription status for access control."""
        try:
            from app.services.billing_service import BillingService
            
            billing_service = BillingService(db)
            access_info = await billing_service.check_subscription_access(org_id)
            
            # Store subscription status in request state
            request.state.subscription_status = access_info.get("status", "unknown")
            request.state.subscription_has_access = access_info.get("has_access", True)
            request.state.subscription_message = access_info.get("message", "")
            request.state.subscription_days_remaining = access_info.get("days_remaining", 0)
            request.state.subscription_grace_period_remaining = access_info.get("grace_period_remaining", 0)
            
        except Exception as e:
            # Default to allowing access if check fails
            logger.warning(f"Failed to load subscription status: {e}")
            request.state.subscription_status = "unknown"
            request.state.subscription_has_access = True
            request.state.subscription_message = ""
            request.state.subscription_days_remaining = 0
            request.state.subscription_grace_period_remaining = 0
    
    async def _record_api_call(
        self, 
        request: Request, 
        org_id: UUID, 
        db
    ) -> None:
        """Record API call usage for metering."""
        try:
            from app.services.metering_service import MeteringService
            
            # Get user_id if available
            user_id = None
            if hasattr(request.state, 'user') and request.state.user:
                user_id = request.state.user.id
            
            metering_service = MeteringService(db)
            await metering_service.record_api_call(
                organization_id=org_id,
                user_id=user_id,
                endpoint=request.url.path,
            )
            await db.commit()
        except Exception as e:
            # Don't fail the request if metering fails
            logger.warning(f"Failed to record API call: {e}")


def setup_sku_middleware(app, enable_feature_gating: bool = True, enable_subscription_enforcement: bool = True) -> None:
    """
    Add SKU middleware to the FastAPI app.
    
    Args:
        app: FastAPI application
        enable_feature_gating: Whether to enable path-based feature gating
        enable_subscription_enforcement: Whether to enforce subscription status
    """
    # Context middleware first (provides data for feature gating)
    app.add_middleware(SKUContextMiddleware)
    
    # Feature gating middleware
    if enable_feature_gating:
        app.add_middleware(FeatureGateMiddleware)
        logger.info("SKU feature gating middleware enabled")
    
    # Subscription enforcement middleware
    if enable_subscription_enforcement:
        app.add_middleware(SubscriptionEnforcementMiddleware)
        logger.info("Subscription enforcement middleware enabled")
    
    logger.info("SKU context middleware enabled")


class SubscriptionEnforcementMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces subscription status and blocks suspended accounts.
    
    This middleware checks if the organization has a valid subscription and
    blocks access to protected routes if the account is suspended.
    
    Allowed statuses for access:
    - active: Normal active subscription
    - trial: In trial period
    - grace_period: Payment overdue but within grace period
    - trial_expired: Trial ended but within grace period
    
    Blocked statuses:
    - suspended: Account suspended due to non-payment
    - cancelled: Subscription cancelled
    """
    
    async def dispatch(
        self, 
        request: Request, 
        call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path
        
        # Check if path is exempt from subscription check
        if self._is_exempt(path):
            return await call_next(request)
        
        # Check if path requires subscription
        if not self._requires_subscription(path):
            return await call_next(request)
        
        # Check subscription status
        subscription_status = getattr(request.state, 'subscription_status', None)
        has_access = getattr(request.state, 'subscription_has_access', True)
        
        # If status not loaded, allow access (unauthenticated requests)
        if subscription_status is None:
            return await call_next(request)
        
        # Check if account is suspended
        if subscription_status == "suspended" or not has_access:
            message = getattr(request.state, 'subscription_message', 
                            'Your account has been suspended due to non-payment.')
            
            # For API requests, return JSON error
            if path.startswith("/api/"):
                return JSONResponse(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    content={
                        "error": "subscription_suspended",
                        "message": message,
                        "status": subscription_status,
                        "upgrade_url": "/checkout",
                        "billing_url": "/api/v1/billing/subscription-access",
                    },
                )
            
            # For page requests, redirect to a suspended page or checkout
            from starlette.responses import RedirectResponse
            return RedirectResponse(
                url=f"/checkout?status=suspended&message={message}",
                status_code=status.HTTP_302_FOUND,
            )
        
        # For grace period, add warning headers
        if subscription_status == "grace_period":
            grace_remaining = getattr(request.state, 'subscription_grace_period_remaining', 0)
            response = await call_next(request)
            response.headers["X-Subscription-Warning"] = "grace_period"
            response.headers["X-Grace-Period-Remaining"] = str(grace_remaining)
            return response
        
        return await call_next(request)
    
    def _is_exempt(self, path: str) -> bool:
        """Check if path is exempt from subscription check."""
        if path == "/":
            return True
        
        for prefix in SUBSCRIPTION_EXEMPT_PREFIXES:
            if path.startswith(prefix):
                return True
        
        return False
    
    def _requires_subscription(self, path: str) -> bool:
        """Check if path requires an active subscription."""
        for prefix in SUBSCRIPTION_REQUIRED_PREFIXES:
            if path.startswith(prefix):
                return True
        return False


class FeatureGateMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces SKU feature gating based on URL paths.
    
    This middleware intercepts requests and checks if the user's organization
    has access to the required features for the requested path.
    
    Benefits:
    - No need to modify individual endpoints
    - Centralized feature gating configuration
    - Easy to add/remove feature gates
    - Consistent error responses
    """
    
    async def dispatch(
        self, 
        request: Request, 
        call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path
        method = request.method
        
        # Check if path is exempt
        if self._is_exempt(path):
            return await call_next(request)
        
        # Find applicable feature gates
        gates = self._find_applicable_gates(path, method)
        
        # No gates = allow access
        if not gates:
            return await call_next(request)
        
        # Check if SKU context was loaded
        sku_features = getattr(request.state, 'sku_features', set())
        sku_loaded = getattr(request.state, 'sku_loaded', False)
        
        # If SKU not loaded (unauthenticated), let endpoint handle auth
        if not sku_loaded:
            return await call_next(request)
        
        # Check each gate's required features
        for gate in gates:
            for feature in gate.required_features:
                if feature.value not in sku_features:
                    # Feature not available
                    tier = getattr(request.state, 'sku_tier', 'core')
                    
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={
                            "error": "feature_not_available",
                            "message": gate.description,
                            "feature": feature.value,
                            "path": path,
                            "current_tier": tier,
                            "upgrade_required": True,
                            "contact": "Contact info@tekvwa.org to upgrade your plan",
                        },
                    )
        
        return await call_next(request)
    
    def _is_exempt(self, path: str) -> bool:
        """Check if path is exempt from feature checks."""
        # Exact match for root
        if path == "/":
            return True
        
        for prefix in EXEMPT_PREFIXES:
            if path.startswith(prefix):
                return True
        
        return False
    
    def _find_applicable_gates(self, path: str, method: str) -> List[PathFeatureGate]:
        """Find all feature gates that apply to a path.
        
        Uses both prefix matching (for /api/v1/payroll, etc.) and 
        contains matching (for paths like /api/v1/entities/{entity_id}/bank-reconciliation).
        """
        applicable = []
        
        for gate in PATH_FEATURE_GATES:
            # Use contains matching to handle entity-prefixed routes
            # e.g., /api/v1/entities/123/bank-reconciliation should match /bank-reconciliation
            if path.startswith(gate.path_prefix) or gate.path_prefix in path:
                # Check method restriction
                if gate.methods is None or method.upper() in gate.methods:
                    applicable.append(gate)
        
        return applicable


# =============================================================================
# TEMPLATE HELPERS
# =============================================================================

def get_sku_template_context(request: Request) -> dict:
    """
    Get SKU context for template rendering.
    
    Returns a dictionary suitable for passing to Jinja2 templates.
    
    Usage:
        @router.get("/dashboard")
        async def dashboard(request: Request):
            return templates.TemplateResponse(
                request,
                "dashboard.html",
                {
                    **get_sku_template_context(request),
                }
            )
    """
    return {
        "sku_tier": getattr(request.state, 'sku_tier', None),
        "sku_intelligence": getattr(request.state, 'sku_intelligence', None),
        "sku_features": getattr(request.state, 'sku_features', set()),
        "sku_is_trial": getattr(request.state, 'sku_is_trial', False),
        "has_feature": lambda f: f in getattr(request.state, 'sku_features', set()),
        # Subscription status
        "subscription_status": getattr(request.state, 'subscription_status', None),
        "subscription_has_access": getattr(request.state, 'subscription_has_access', True),
        "subscription_message": getattr(request.state, 'subscription_message', ''),
        "subscription_days_remaining": getattr(request.state, 'subscription_days_remaining', 0),
        "subscription_grace_period_remaining": getattr(request.state, 'subscription_grace_period_remaining', 0),
    }


def has_feature(request: Request, feature: str) -> bool:
    """
    Check if a feature is available in the current request context.
    
    Usage in routes:
        if has_feature(request, "payroll"):
            # Include payroll data
    """
    features = getattr(request.state, 'sku_features', set())
    return feature in features


def require_tier(request: Request, min_tier: str) -> bool:
    """
    Check if current tier meets minimum requirement.
    
    Args:
        request: The request object
        min_tier: Minimum tier required ("core", "professional", "enterprise")
    
    Returns:
        True if current tier meets or exceeds requirement
    """
    tier_order = {
        "core": 1,
        "professional": 2,
        "enterprise": 3,
    }
    
    current_tier = getattr(request.state, 'sku_tier', 'core')
    current_rank = tier_order.get(current_tier, 0)
    required_rank = tier_order.get(min_tier, 0)
    
    return current_rank >= required_rank
