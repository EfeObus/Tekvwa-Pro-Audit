"""
Tekvwa Pro Audit - FastAPI Application Entry Point

This is the main entry point for the FastAPI application.
"""

import logging
import traceback
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.database import init_db, close_db, async_session_factory
from app.utils.error_handling import (
    AppException,
    setup_exception_handlers,
    ErrorTrackingMiddleware,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def seed_super_admin():
    """
    Seed the hardcoded Super Admin user on startup.
    This ensures there's always a Super Admin account available.
    """
    from app.services.staff_management_service import StaffManagementService
    
    async with async_session_factory() as session:
        service = StaffManagementService(session)
        try:
            super_admin = await service.get_or_create_super_admin()
            logger.info(f"Super Admin ready: {super_admin.email}")
        except Exception as e:
            logger.warning(f"Could not seed Super Admin: {e}")


async def seed_platform_test_entity():
    """
    Seed the platform test organization and entity on startup.
    This provides a demo business for platform staff to use when testing features.
    """
    from app.services.staff_management_service import StaffManagementService
    
    async with async_session_factory() as session:
        service = StaffManagementService(session)
        try:
            demo_entity = await service.get_or_create_platform_test_entity()
            logger.info(f"Platform Test Entity ready: {demo_entity.name}")
        except Exception as e:
            logger.warning(f"Could not seed Test Entity: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info(f"Starting {settings.app_name}...")
    logger.info(f"Environment: {settings.app_env}")
    logger.info(f"Database: {settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}")
    
    # Initialize database (dev only - use migrations in production)
    if settings.is_development:
        await init_db()
        logger.info("Database tables initialized")
    
    # Seed Super Admin
    try:
        await seed_super_admin()
    except Exception as e:
        logger.warning(f"Super Admin seeding skipped: {e}")
    
    # Seed Platform Test Entity for staff testing
    try:
        await seed_platform_test_entity()
    except Exception as e:
        logger.warning(f"Test Entity seeding skipped: {e}")

    yield
    
    # Shutdown
    logger.info(f"Shutting down {settings.app_name}...")
    await close_db()
    logger.info("Database connections closed")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="Nigeria's Premier Tax Compliance & Business Management Platform for the 2026 Tax Reform Era",
    version="0.1.0",
    docs_url="/api/docs" if settings.is_development else None,
    redoc_url="/api/redoc" if settings.is_development else None,
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup Security Middleware (NDPA/NITDA Compliance)
from app.middleware.security import setup_security_middleware
setup_security_middleware(
    app=app,
    development_mode=settings.is_development,
    geo_fencing_enabled=not settings.is_development,  # Disable geo-fencing in dev
    rate_limiting_enabled=True,  # Always enable, but relaxed in dev
    csrf_enabled=True,  # Always enable CSRF
)

# Setup SKU Feature Gating Middleware (Commercial Tiers)
from app.middleware.sku_middleware import setup_sku_middleware
setup_sku_middleware(
    app=app,
    enable_feature_gating=True,  # Set to False to disable tier enforcement
)

# Setup Emergency Mode Middleware (Platform Emergency Controls)
from app.middleware.emergency_mode import create_emergency_middleware
create_emergency_middleware(
    app=app,
    enabled=True,
    development_mode=settings.is_development,
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup Jinja2 templates
templates = Jinja2Templates(directory="templates")


# ===========================================
# HTTP STATUS CODE DESCRIPTIONS
# ===========================================

HTTP_STATUS_DESCRIPTIONS = {
    # 3xx Redirection
    300: ("Multiple Choices", "Multiple options are available for this resource."),
    301: ("Moved Permanently", "This resource has been permanently moved."),
    302: ("Found", "This resource has been temporarily moved."),
    303: ("See Other", "Please see another URI for this resource."),
    304: ("Not Modified", "The resource has not been modified."),
    307: ("Temporary Redirect", "Please follow the redirect."),
    308: ("Permanent Redirect", "This resource has been permanently moved."),
    
    # 4xx Client Errors
    400: ("Bad Request", "The request was invalid or malformed."),
    401: ("Unauthorized", "Authentication is required to access this resource."),
    402: ("Payment Required", "Payment is required to access this feature."),
    403: ("Forbidden", "You don't have permission to access this resource."),
    404: ("Not Found", "The requested resource could not be found."),
    405: ("Method Not Allowed", "This HTTP method is not supported for this endpoint."),
    406: ("Not Acceptable", "The requested content type is not available."),
    408: ("Request Timeout", "The request took too long to complete."),
    409: ("Conflict", "The request conflicts with the current state."),
    410: ("Gone", "This resource is no longer available."),
    411: ("Length Required", "Content-Length header is required."),
    412: ("Precondition Failed", "A precondition for this request was not met."),
    413: ("Payload Too Large", "The request body is too large."),
    414: ("URI Too Long", "The request URI is too long."),
    415: ("Unsupported Media Type", "The content type is not supported."),
    416: ("Range Not Satisfiable", "The requested range cannot be satisfied."),
    418: ("I'm a Teapot", "🫖 The server refuses to brew coffee."),
    422: ("Unprocessable Entity", "The request data could not be processed."),
    423: ("Locked", "The resource is currently locked."),
    424: ("Failed Dependency", "A dependent request failed."),
    429: ("Too Many Requests", "You've exceeded the rate limit. Please slow down."),
    451: ("Unavailable For Legal Reasons", "This content is not available due to legal restrictions."),
    
    # 5xx Server Errors
    500: ("Internal Server Error", "An unexpected error occurred. Our team has been notified."),
    501: ("Not Implemented", "This feature is not yet implemented."),
    502: ("Bad Gateway", "Error communicating with an upstream service."),
    503: ("Service Unavailable", "The service is temporarily unavailable."),
    504: ("Gateway Timeout", "An upstream service took too long to respond."),
    507: ("Insufficient Storage", "Insufficient storage space available."),
}


def _wants_html(request: Request) -> bool:
    """Check if the client prefers HTML over JSON."""
    accept = request.headers.get("accept", "")
    # Check for common browser patterns
    if "text/html" in accept:
        return True
    # API calls typically specify application/json
    if "application/json" in accept:
        return False
    # Check if it's a direct browser navigation
    if request.url.path.startswith("/api/"):
        return False
    # Default to HTML for browser-like requests
    return "Mozilla" in request.headers.get("user-agent", "")


def _generate_error_id() -> str:
    """Generate a unique error ID for support reference."""
    import uuid
    return str(uuid.uuid4())[:8].upper()


async def _render_error_html(
    request: Request,
    status_code: int,
    message: str | None = None,
    error_type: str = "http_error",
    debug_info: dict | None = None,
) -> Any:
    """Render an HTML error page."""
    from fastapi.responses import HTMLResponse
    
    title, default_message = HTTP_STATUS_DESCRIPTIONS.get(
        status_code, ("Error", "An error occurred.")
    )
    
    error_id = _generate_error_id()
    
    # Log the error with reference ID
    logger.error(
        f"Error {status_code} (Ref: {error_id}): {message or default_message}",
        extra={"error_id": error_id, "path": request.url.path}
    )
    
    try:
        return templates.TemplateResponse(
            request, "error.html",
            {
                "request": request,
                "error_code": status_code,
                "error_title": title,
                "error_message": message or default_message,
                "error_id": error_id,
                "debug_info": debug_info if settings.is_development else None,
            },
            status_code=status_code,
        )
    except Exception:
        # Fallback to basic HTML if template fails
        return HTMLResponse(
            content=f"""
            <!DOCTYPE html>
            <html>
            <head><title>{title}</title></head>
            <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                <h1>{status_code} - {title}</h1>
                <p>{message or default_message}</p>
                <p><a href="/">Go Home</a></p>
                <p style="font-size: 12px; color: #666;">Ref: {error_id}</p>
            </body>
            </html>
            """,
            status_code=status_code,
        )


# ===========================================
# GLOBAL ERROR HANDLERS
# ===========================================

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions with HTML or JSON based on Accept header."""
    if _wants_html(request):
        return await _render_error_html(
            request,
            exc.status_code,
            str(exc.detail) if exc.detail else None,
            "http_error",
        )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.status_code,
                "message": str(exc.detail) if exc.detail else HTTP_STATUS_DESCRIPTIONS.get(exc.status_code, ("Error", "An error occurred"))[1],
                "type": "http_error"
            }
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors with detailed field info."""
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"])
        errors.append({
            "field": field,
            "message": error["msg"],
            "type": error["type"]
        })
    
    if _wants_html(request):
        error_details = ", ".join([f"{e['field']}: {e['message']}" for e in errors[:3]])
        if len(errors) > 3:
            error_details += f" (+{len(errors) - 3} more)"
        return await _render_error_html(
            request,
            422,
            f"Validation failed: {error_details}",
            "validation_error",
        )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error": {
                "code": 422,
                "message": "Validation error",
                "type": "validation_error",
                "details": errors
            }
        }
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_handler(request: Request, exc: ValidationError):
    """Handle Pydantic validation errors."""
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"])
        errors.append({
            "field": field,
            "message": error["msg"],
            "type": error["type"]
        })
    
    if _wants_html(request):
        error_details = ", ".join([f"{e['field']}: {e['message']}" for e in errors[:3]])
        return await _render_error_html(
            request,
            422,
            f"Data validation failed: {error_details}",
            "validation_error",
        )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error": {
                "code": 422,
                "message": "Data validation error",
                "type": "validation_error",
                "details": errors
            }
        }
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Handle value errors (business logic errors)."""
    logger.warning(f"ValueError: {exc}")
    
    if _wants_html(request):
        return await _render_error_html(
            request,
            400,
            str(exc),
            "value_error",
        )
    
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "success": False,
            "error": {
                "code": 400,
                "message": str(exc),
                "type": "value_error"
            }
        }
    )


@app.exception_handler(PermissionError)
async def permission_error_handler(request: Request, exc: PermissionError):
    """Handle permission errors."""
    logger.warning(f"PermissionError: {exc}")
    
    if _wants_html(request):
        return await _render_error_html(
            request,
            403,
            str(exc) or "You don't have permission to access this resource.",
            "permission_error",
        )
    
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "success": False,
            "error": {
                "code": 403,
                "message": str(exc) or "Permission denied",
                "type": "permission_error"
            }
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all handler for unhandled exceptions."""
    # Log the full traceback for debugging
    tb = traceback.format_exc()
    logger.error(f"Unhandled exception: {exc}")
    logger.error(tb)
    
    # Return generic error in production, detailed in development
    if settings.is_development:
        message = f"{type(exc).__name__}: {str(exc)}"
        debug_info = {
            "error_type": type(exc).__name__,
            "path": str(request.url.path),
            "method": request.method,
            "traceback": tb,
        }
    else:
        message = "An unexpected error occurred. Please try again later."
        debug_info = None
    
    if _wants_html(request):
        return await _render_error_html(
            request,
            500,
            message,
            "internal_error",
            debug_info,
        )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "code": 500,
                "message": message,
                "type": "internal_error"
            }
        }
    )


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """Handle custom application exceptions with standardized format."""
    logger.error(
        f"AppException: {exc.code.value} - {exc.message}",
        extra={"code": exc.code.value, "path": request.url.path}
    )
    
    if _wants_html(request):
        return await _render_error_html(
            request,
            exc.status_code,
            exc.message,
            exc.code.value,
        )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.to_dict()
        }
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    """Handle SQLAlchemy database errors."""
    from sqlalchemy.exc import IntegrityError, OperationalError, DataError
    
    error_message = "A database error occurred"
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_type = "database_error"
    
    if isinstance(exc, IntegrityError):
        error_str = str(exc.orig).lower() if exc.orig else ""
        if "unique" in error_str or "duplicate" in error_str:
            error_message = "A record with this value already exists"
            status_code = status.HTTP_409_CONFLICT
            error_type = "duplicate_entry"
        elif "foreign key" in error_str:
            error_message = "Referenced record does not exist"
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
            error_type = "foreign_key_violation"
        else:
            error_message = "Data integrity constraint violated"
            error_type = "integrity_error"
    elif isinstance(exc, OperationalError):
        error_message = "Database connection or operation failed. Please try again."
        error_type = "connection_error"
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif isinstance(exc, DataError):
        error_message = "Invalid data format for database field"
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        error_type = "data_error"
    
    logger.error(f"SQLAlchemyError ({error_type}): {str(exc)}", exc_info=True)
    
    if _wants_html(request):
        return await _render_error_html(
            request,
            status_code,
            error_message,
            error_type,
            {"error_type": type(exc).__name__, "path": str(request.url.path), "method": request.method} if settings.is_development else None,
        )
    
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": {
                "code": status_code,
                "message": error_message,
                "type": error_type
            }
        }
    )


# ===========================================
# API ROUTES
# ===========================================

@app.get("/api")
async def api_info():
    """API information endpoint."""
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "status": "running",
        "environment": settings.app_env,
        "api_docs": "/api/docs" if settings.is_development else "disabled",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "database": "connected",
    }


@app.get("/api/v1")
async def api_root():
    """API v1 root endpoint."""
    return {
        "message": f"Welcome to {settings.app_name} API v1",
        "endpoints": {
            "auth": "/api/v1/auth",
            "staff": "/api/v1/staff",
            "entities": "/api/v1/entities",
            "transactions": "/api/v1/entities/{entity_id}/transactions",
            "invoices": "/api/v1/entities/{entity_id}/invoices",
            "vendors": "/api/v1/entities/{entity_id}/vendors",
            "reports": "/api/v1/entities/{entity_id}/reports",
        }
    }


# ===========================================
# INCLUDE ROUTERS
# ===========================================

from app.routers import (
    auth, entities, categories, vendors, customers, 
    transactions, invoices, tax, inventory, receipts,
    reports, audit, views, tax_2026, staff, organization_users,
    fixed_assets, sales, dashboard, payroll, payroll_views,
    # New routers added
    notifications, self_assessment, organization_settings,
    bulk_operations, exports, search_analytics,
    # 2026 Tax Reform Advanced Features
    advanced_accounting,
    # Business Intelligence (BIK, NIBSS, Growth Radar, Inventory)
    business_intelligence,
    # World-Class Forensic Audit (Benford's Law, Z-Score, NRS Gap, WORM)
    forensic_audit,
    # Enterprise Advanced Audit (Explainability, Replay, Confidence, Attestation, Export, Behavioral)
    advanced_audit,
    # Advanced Audit System (Immutable Evidence, Reproducible Runs, Human-Readable Findings)
    audit_system,
    # Advanced Payroll (Compliance, Impact Preview, Exceptions, Decision Logs, YTD, CTC)
    payroll_advanced,
    # NRS Integration (Invoice Reporting, TIN Validation, Disputes)
    nrs,
    # Bank Reconciliation
    bank_reconciliation,
    # Expense Claims
    expense_claims,
    # Machine Learning & AI (OCR, Forecasting, NLP, Neural Networks)
    ml_ai,
    # Chart of Accounts & General Ledger (Core Accounting Engine)
    accounting,
    # Evidence Collection (Document Upload, Screenshots, Transaction Snapshots, Confirmations)
    evidence_routes,
    # SKU Management (Platform Admin)
    admin_sku,
    # Billing (Subscription Management, Payments, Upgrades)
    billing,
    # Advanced Billing (Usage Reports, Pause/Resume, Credits, Discounts, Volume, Multi-Currency)
    advanced_billing,
    # Super Admin Dashboard APIs
    legal_holds,
    risk_signals,
    ml_jobs,
    upsell,
    support_tickets,
    admin_tenants,
    admin_emergency,
    admin_user_search,
    admin_platform_staff,
    admin_verification,
    admin_audit_logs,
    admin_health,
    # New Admin Routers (Settings, Security, API Keys, Automation)
    admin_settings,
    admin_security,
    admin_api_keys,
    admin_automation,
)

# View Routes (HTML pages)
app.include_router(views.router, tags=["Views"])

# Authentication
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])

# Platform Staff Management (RBAC)
app.include_router(staff.router, prefix="/api/v1", tags=["Staff Management"])

# Organization User Management
app.include_router(organization_users.router, prefix="/api/v1", tags=["Organization Users"])

# Business Entities
app.include_router(entities.router, prefix="/api/v1/entities", tags=["Business Entities"])

# Entity Sub-resources (nested under entities)
app.include_router(categories.router, prefix="/api/v1/entities", tags=["Categories"])
app.include_router(vendors.router, prefix="/api/v1/entities", tags=["Vendors"])
app.include_router(customers.router, prefix="/api/v1/entities", tags=["Customers"])
app.include_router(transactions.router, prefix="/api/v1/entities", tags=["Transactions"])
app.include_router(invoices.router, prefix="/api/v1/entities", tags=["Invoices"])
app.include_router(inventory.router, prefix="/api/v1/entities", tags=["Inventory"])
app.include_router(receipts.router, prefix="/api/v1/entities", tags=["Receipts & Files"])
app.include_router(reports.router, prefix="/api/v1/entities", tags=["Reports & Dashboard"])
app.include_router(audit.router, prefix="/api/v1/entities", tags=["Audit Trail"])
app.include_router(sales.router, prefix="/api/v1/entities", tags=["Sales Recording"])

# Tax Management
app.include_router(tax.router, prefix="/api/v1/tax", tags=["Tax Management"])

# 2026 Tax Reform APIs
app.include_router(tax_2026.router, prefix="/api/v1/tax-2026", tags=["2026 Tax Reform"])

# Fixed Asset Register (2026)
app.include_router(fixed_assets.router, tags=["Fixed Assets"])

# World-Class Dashboards (NTAA 2025)
app.include_router(dashboard.router, tags=["Dashboard"])

# Notifications
app.include_router(notifications.router, prefix="/api/v1", tags=["Notifications"])

# Self-Assessment & Tax Returns
app.include_router(self_assessment.router, tags=["Self-Assessment"])

# Organization Settings
app.include_router(organization_settings.router, tags=["Organization Settings"])

# Bulk Operations (Import/Export)
app.include_router(bulk_operations.router, tags=["Bulk Operations"])

# Export & Download
app.include_router(exports.router, tags=["Export & Download"])

# Search & Analytics
app.include_router(search_analytics.router, tags=["Search & Analytics"])

# Payroll System (Nigerian Compliance)
app.include_router(payroll.router, prefix="/api/v1/payroll", tags=["Payroll"])

# Payroll HTML Views
app.include_router(payroll_views.router, tags=["Payroll Views"])

# Advanced Payroll (Compliance Status, Impact Preview, Exceptions, Decision Logs, YTD, CTC, What-If)
app.include_router(payroll_advanced.router, prefix="/api/v1/payroll/advanced", tags=["Advanced Payroll"])

# 2026 Tax Reform Advanced Features (3-Way Matching, WHT Vault, Approvals, AI)
app.include_router(advanced_accounting.router, tags=["Advanced Accounting"])

# Business Intelligence (BIK Automator, NIBSS Pension, Growth Radar, Inventory Management)
app.include_router(business_intelligence.router, tags=["Business Intelligence"])

# World-Class Forensic Audit (Benford's Law, Z-Score Anomaly, NRS Gap, WORM Storage)
app.include_router(forensic_audit.router, prefix="/api/v1/entities", tags=["Forensic Audit"])

# Enterprise Advanced Audit (Explainability, Replay, Confidence, Attestation, Export, Behavioral Analytics)
app.include_router(advanced_audit.router, prefix="/api/v1/entities", tags=["Advanced Audit"])

# Advanced Audit System (Immutable Evidence, Reproducible Runs, Auditor Read-Only, Human-Readable Findings)
app.include_router(audit_system.router, tags=["Audit System"])

# NRS Integration (Invoice Reporting System - 2026 Compliance)
app.include_router(nrs.router, prefix="/api/v1", tags=["NRS Integration"])

# Bank Reconciliation
app.include_router(bank_reconciliation.router, prefix="/api/v1/entities", tags=["Bank Reconciliation"])

# Expense Claims
app.include_router(expense_claims.router, prefix="/api/v1/entities", tags=["Expense Claims"])

# Machine Learning & AI (OCR, Cash Flow Forecasting, Growth Prediction, NLP, Neural Networks)
app.include_router(ml_ai.router, prefix="/api/v1/ml", tags=["Machine Learning & AI"])

# Chart of Accounts & General Ledger (Core Accounting Engine)
app.include_router(accounting.router, tags=["Accounting"])

# Foreign Exchange (FX) - Multi-Currency Operations
from app.routers import fx as fx_router
app.include_router(fx_router.router, tags=["Foreign Exchange"])

# Multi-Entity Consolidation - Group Financial Statements
from app.routers import consolidation as consolidation_router
app.include_router(consolidation_router.router, tags=["Consolidation"])

# Advanced Accounting - Entity Groups, Consolidated Views (Frontend Compatibility)
from app.routers import advanced as advanced_router
app.include_router(advanced_router.router, tags=["Advanced Accounting"])

# Budget Management - Budget vs Actual, Variance Analysis
from app.routers import budget as budget_router
app.include_router(budget_router.router, tags=["Budget Management"])

# Year-End Closing - Automated Year-End Closing, Period Locking, Opening Balances
from app.routers import year_end as year_end_router
app.include_router(year_end_router.router, tags=["Year-End Closing"])

# Financial Report Export - PDF, Excel, CSV for Balance Sheet, Income Statement, Trial Balance, GL
from app.routers import report_export as report_export_router
app.include_router(report_export_router.router, tags=["Report Export"])

# Report Templates - Customizable report templates per tenant
from app.routers import report_template as report_template_router
app.include_router(report_template_router.router, prefix="/api/v1/entities", tags=["Report Templates"])

# WebSocket - Real-time notifications
from app.routers import websocket as websocket_router
app.include_router(websocket_router.router, tags=["WebSocket"])

# Evidence Collection (Document Upload, Screenshots, Transaction Snapshots, Confirmations)
app.include_router(evidence_routes.router, tags=["Evidence Collection"])

# SKU Management - Platform Admin (Tier Management, Pricing, Usage Analytics)
app.include_router(admin_sku.router, prefix="/api/v1", tags=["SKU Management"])

# Billing - Subscription Management, Payments, Upgrades (Paystack Integration)
app.include_router(billing.router, tags=["Billing"])

# Advanced Billing - Issues #30-36 (Usage Reports, Pause/Resume, Credits, Discounts, Volume, Multi-Currency)
app.include_router(advanced_billing.router, tags=["Advanced Billing"])

# ===========================================
# SUPER ADMIN DASHBOARD APIs
# ===========================================

# Legal Holds (Compliance & Data Preservation)
app.include_router(legal_holds.router, prefix="/api/v1", tags=["Legal Holds"])

# Risk Signals (Platform Monitoring & Early Warning)
app.include_router(risk_signals.router, prefix="/api/v1", tags=["Risk Signals"])

# ML Jobs & Models (Platform ML Operations)
app.include_router(ml_jobs.router, prefix="/api/v1", tags=["ML Jobs"])

# Upsell Opportunities (Revenue Expansion)
app.include_router(upsell.router, prefix="/api/v1", tags=["Upsell"])

# Support Tickets (Customer Service)
app.include_router(support_tickets.router, prefix="/api/v1", tags=["Support Tickets"])

# Admin Tenants (Tenant Management for Platform Admins)
app.include_router(admin_tenants.router, prefix="/api/v1", tags=["Admin - Tenants"])

# Emergency Controls (Kill Switches, Maintenance Mode, Feature Toggles)
app.include_router(admin_emergency.router, prefix="/api/v1", tags=["Admin - Emergency Controls"])

# Admin User Search (Cross-Tenant User Discovery)
app.include_router(admin_user_search.router, prefix="/api/v1", tags=["Admin - User Search"])

# Admin Platform Staff Management (Internal Tekvwa Staff)
app.include_router(admin_platform_staff.router, prefix="/api/v1", tags=["Admin - Platform Staff"])

# Admin Organization Verification (CAC/TIN Document Review)
app.include_router(admin_verification.router, prefix="/api/v1", tags=["Admin - Verification"])

# Admin Global Audit Log Viewer (Cross-Tenant Audit Trail)
app.include_router(admin_audit_logs.router, prefix="/api/v1", tags=["Admin - Audit Logs"])

# Admin Platform Health Metrics (System Monitoring Dashboard)
app.include_router(admin_health.router, prefix="/api/v1", tags=["Admin - Platform Health"])

# Admin Platform Settings (General, Trial, NRS, Billing, Security, Notifications)
app.include_router(admin_settings.router, prefix="/api/v1", tags=["Admin - Settings"])

# Admin Security Audit Center (Alerts, Sessions, IP Whitelist, Policies)
app.include_router(admin_security.router, prefix="/api/v1", tags=["Admin - Security"])

# Admin API Keys Management (Generate, Revoke, Track Usage)
app.include_router(admin_api_keys.router, prefix="/api/v1", tags=["Admin - API Keys"])

# Admin Workflow Automation (Rules, Triggers, Actions)
app.include_router(admin_automation.router, prefix="/api/v1", tags=["Admin - Automation"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=5120,
        reload=settings.is_development,
    )
