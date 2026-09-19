"""
TekVwarho ProAudit - Views Router

Server-side rendered pages using Jinja2 templates.
Authentication is persistent across all pages via HTTP-only cookies.
"""

import uuid
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db, get_async_session
from app.dependencies import get_optional_user
from app.models.user import User
from app.services.dashboard_service import DashboardService
from app.services.auth_service import AuthService
from app.services.feature_flags import FeatureFlagService, Feature
from app.models.sku import TenantSKU, SKUTier
from app.config.sku_config import get_features_for_tier

router = APIRouter()
templates = Jinja2Templates(directory="templates")


async def check_view_feature_access(
    request: Request,
    db: AsyncSession,
    user: User,
    required_feature: Feature,
) -> bool:
    """
    Check if user has access to a feature for view routes.
    Platform staff always have access.
    Returns True if access granted, False otherwise.
    """
    # Platform staff bypass feature checks
    if user.is_platform_staff:
        return True
    
    if not user.organization_id:
        return False
    
    # Get tenant SKU
    result = await db.execute(
        select(TenantSKU).where(
            TenantSKU.organization_id == user.organization_id,
            TenantSKU.is_active == True,
        )
    )
    tenant_sku = result.scalar_one_or_none()
    
    if not tenant_sku:
        # No SKU = default to CORE
        tier = SKUTier.CORE
    else:
        tier = tenant_sku.tier
    
    # Check if feature is enabled for this tier
    enabled_features = get_features_for_tier(tier)
    return required_feature in enabled_features


def get_entity_id_from_session(request: Request) -> Optional[uuid.UUID]:
    """Get the current entity ID from session/cookie."""
    entity_id = request.cookies.get("entity_id")
    if entity_id:
        try:
            return uuid.UUID(entity_id)
        except ValueError:
            return None
    return None


def set_entity_cookie_if_needed(
    response, 
    request: Request, 
    entity_id: Optional[uuid.UUID]
) -> None:
    """
    Set the entity_id cookie if needed (e.g., for platform staff auto-assignment).
    
    This is called after require_auth to persist the auto-assigned entity.
    """
    if entity_id:
        current_cookie = request.cookies.get("entity_id")
        if current_cookie != str(entity_id):
            response.set_cookie(
                key="entity_id",
                value=str(entity_id),
                httponly=True,
                max_age=60 * 60 * 24 * 30,  # 30 days
                samesite="lax"
            )


async def get_user_from_token(request: Request, db: AsyncSession) -> Optional[User]:
    """Get the authenticated user from the access token cookie."""
    token = request.cookies.get("access_token")
    if not token:
        return None
    
    # Remove 'Bearer ' prefix if present
    if token.startswith("Bearer "):
        token = token[7:]
    
    auth_service = AuthService(db)
    try:
        user = await auth_service.get_current_user_from_token(token)
        return user
    except Exception:
        return None


async def require_auth(
    request: Request, 
    db: AsyncSession,
    require_entity: bool = True
) -> Tuple[Optional[User], Optional[uuid.UUID], Optional[RedirectResponse]]:
    """
    Check authentication for protected pages.
    
    For platform staff:
    - They don't need to manually select an entity
    - If they access entity-requiring pages, they get the test entity automatically
    
    Returns:
        Tuple of (user, entity_id, redirect_response)
        If redirect_response is not None, the caller should return it.
    """
    from app.services.staff_management_service import StaffManagementService
    
    user = await get_user_from_token(request, db)
    
    if not user:
        return None, None, RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    entity_id = get_entity_id_from_session(request)
    
    # Platform staff handling
    if user.is_platform_staff:
        if require_entity and not entity_id:
            # Auto-assign the test entity for platform staff
            try:
                service = StaffManagementService(db)
                demo_entity = await service.ensure_staff_has_test_entity_access(user)
                # Return the demo entity ID - caller should set cookie
                return user, demo_entity.id, None
            except Exception as e:
                # If test entity creation fails, continue without entity
                print(f"Could not assign test entity to staff: {e}")
                return user, None, None
        return user, entity_id, None
    
    # Organization users need entity (unless require_entity is False)
    if require_entity and not entity_id:
        return user, None, RedirectResponse(url="/select-entity", status_code=status.HTTP_302_FOUND)
    
    return user, entity_id, None


def get_auth_context(user: Optional[User], entity_id: Optional[uuid.UUID]) -> dict:
    """
    Get common authentication context for templates.
    
    This ensures user info is available across all pages.
    """
    return {
        "user": user,
        "is_authenticated": user is not None,
        "is_platform_staff": user.is_platform_staff if user else False,
        "user_role": user.effective_role if user else None,
        "entity_id": str(entity_id) if entity_id else None,
    }


# ===========================================
# PUBLIC PAGES
# ===========================================

@router.get("/", response_class=HTMLResponse)
async def home(request: Request, db: AsyncSession = Depends(get_async_session)):
    """Home/landing page. Redirect to dashboard if logged in."""
    user = await get_user_from_token(request, db)
    if user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(request, "index.html", {"request": request})


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page."""
    return templates.TemplateResponse(request, "login.html", {"request": request})


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Registration page."""
    return templates.TemplateResponse(request, "register.html", {"request": request})


@router.get("/logout")
async def logout(request: Request):
    """Logout - clear session and redirect to login."""
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("entity_id")
    response.delete_cookie("access_token")
    return response


# ===========================================
# PROTECTED PAGES (require authentication)
# ===========================================

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Unified dashboard page.
    Routes to appropriate dashboard based on user type:
    - Super Admin: Comprehensive super admin dashboard with Nigerian flag theme
    - Platform Staff: Staff dashboard with platform metrics
    - Organization Users: Business dashboard with financial metrics
    """
    from app.models.user import PlatformRole
    
    # Use consistent authentication
    user, entity_id, redirect = await require_auth(request, db, require_entity=False)
    if redirect:
        return redirect
    
    # Get dashboard data
    dashboard_service = DashboardService(db)
    
    try:
        if user.is_platform_staff:
            # Platform staff - use staff dashboard
            dashboard_data = await dashboard_service.get_dashboard(user)
            
            # Super Admin gets the comprehensive green-white-green dashboard
            if user.platform_role == PlatformRole.SUPER_ADMIN:
                return templates.TemplateResponse(request, "super_admin_dashboard.html", {
                    "request": request,
                    "dashboard": dashboard_data,
                    **get_auth_context(user, None),
                })
            
            # Other platform staff get the standard staff dashboard
            return templates.TemplateResponse(request, "staff_dashboard.html", {
                "request": request,
                "dashboard": dashboard_data,
                **get_auth_context(user, None),
            })
        else:
            # Organization user - use business dashboard
            # If no entity selected, redirect to entity selection
            if not entity_id:
                # Check if user has any entities
                if user.entity_access and len(user.entity_access) > 0:
                    return RedirectResponse(url="/select-entity", status_code=status.HTTP_302_FOUND)
            
            dashboard_data = await dashboard_service.get_dashboard(user, entity_id)
            
            # Use enhanced dashboard template
            return templates.TemplateResponse(request, "dashboard_v2.html", {
                "request": request,
                "dashboard": dashboard_data,
                "entity_id": str(entity_id) if entity_id else None,
                **get_auth_context(user, entity_id),
            })
    except PermissionError as e:
        return RedirectResponse(url="/login?error=permission", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        # Log the exception for debugging
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        logger.error(f"Dashboard error for {user.email}: {type(e).__name__}: {e}")
        logger.debug(traceback.format_exc())
        
        # Fallback to basic dashboard
        if not entity_id and not user.is_platform_staff:
            return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
        
        return templates.TemplateResponse(request, "dashboard_v2.html", {
            "request": request,
            "error": str(e),
            "entity_id": str(entity_id) if entity_id else None,
            **get_auth_context(user, entity_id),
        })


@router.get("/transactions", response_class=HTMLResponse)
async def transactions_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Transactions list page."""
    user, entity_id, redirect = await require_auth(request, db, require_entity=True)
    if redirect:
        return redirect
    
    response = templates.TemplateResponse(request, "transactions.html", {
        "request": request,
        **get_auth_context(user, entity_id),
    })
    set_entity_cookie_if_needed(response, request, entity_id)
    return response


@router.get("/transactions/new", response_class=HTMLResponse)
async def new_transaction_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """New transaction page - redirects to transactions with modal open."""
    return RedirectResponse(url="/transactions#new", status_code=status.HTTP_302_FOUND)


@router.get("/invoices", response_class=HTMLResponse)
async def invoices_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Invoices list page."""
    user, entity_id, redirect = await require_auth(request, db, require_entity=True)
    if redirect:
        return redirect
    
    response = templates.TemplateResponse(request, "invoices.html", {
        "request": request,
        **get_auth_context(user, entity_id),
    })
    set_entity_cookie_if_needed(response, request, entity_id)
    return response


@router.get("/invoices/new", response_class=HTMLResponse)
async def new_invoice_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """New invoice page - redirects to invoices with modal open."""
    return RedirectResponse(url="/invoices#new", status_code=status.HTTP_302_FOUND)


@router.get("/sales", response_class=HTMLResponse)
async def sales_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Sales recording page - POS-style sales management."""
    user, entity_id, redirect = await require_auth(request, db, require_entity=True)
    if redirect:
        return redirect
    
    response = templates.TemplateResponse(request, "sales.html", {
        "request": request,
        **get_auth_context(user, entity_id),
    })
    set_entity_cookie_if_needed(response, request, entity_id)
    return response


@router.get("/receipts/upload", response_class=HTMLResponse)
async def receipt_upload_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receipt upload/scan page."""
    user, entity_id, redirect = await require_auth(request, db, require_entity=True)
    if redirect:
        return redirect
    
    response = templates.TemplateResponse(request, "receipts.html", {
        "request": request,
        **get_auth_context(user, entity_id),
    })
    set_entity_cookie_if_needed(response, request, entity_id)
    return response


@router.get("/reports", response_class=HTMLResponse)
async def reports_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Reports page."""
    user, entity_id, redirect = await require_auth(request, db, require_entity=True)
    if redirect:
        return redirect
    
    response = templates.TemplateResponse(request, "reports.html", {
        "request": request,
        **get_auth_context(user, entity_id),
    })
    set_entity_cookie_if_needed(response, request, entity_id)
    return response


@router.get("/vendors", response_class=HTMLResponse)
async def vendors_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Vendors list page."""
    user, entity_id, redirect = await require_auth(request, db, require_entity=True)
    if redirect:
        return redirect
    
    response = templates.TemplateResponse(request, "vendors.html", {
        "request": request,
        **get_auth_context(user, entity_id),
    })
    set_entity_cookie_if_needed(response, request, entity_id)
    return response


@router.get("/customers", response_class=HTMLResponse)
async def customers_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Customers list page."""
    user, entity_id, redirect = await require_auth(request, db, require_entity=True)
    if redirect:
        return redirect
    
    response = templates.TemplateResponse(request, "customers.html", {
        "request": request,
        **get_auth_context(user, entity_id),
    })
    set_entity_cookie_if_needed(response, request, entity_id)
    return response


@router.get("/inventory", response_class=HTMLResponse)
async def inventory_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Inventory management page."""
    user, entity_id, redirect = await require_auth(request, db, require_entity=True)
    if redirect:
        return redirect
    
    response = templates.TemplateResponse(request, "inventory.html", {
        "request": request,
        **get_auth_context(user, entity_id),
    })
    set_entity_cookie_if_needed(response, request, entity_id)
    return response


@router.get("/accounting", response_class=HTMLResponse)
async def accounting_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Chart of Accounts & General Ledger management page."""
    user, entity_id, redirect = await require_auth(request, db, require_entity=True)
    if redirect:
        return redirect
    
    response = templates.TemplateResponse(request, "accounting.html", {
        "request": request,
        **get_auth_context(user, entity_id),
    })
    set_entity_cookie_if_needed(response, request, entity_id)
    return response


@router.get("/budgets", response_class=HTMLResponse)
async def budgets_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Budget Management page - Create and track budgets with variance analysis."""
    user, entity_id, redirect = await require_auth(request, db, require_entity=True)
    if redirect:
        return redirect
    
    # SKU Feature Gate: BUDGET_MANAGEMENT required (Professional+ tier)
    has_access = await check_view_feature_access(request, db, user, Feature.BUDGET_MANAGEMENT)
    if not has_access:
        return templates.TemplateResponse(request, "feature_locked.html", {
            "request": request,
            **get_auth_context(user, entity_id),
            "feature_name": "Budget Management",
            "required_tier": "Professional",
        }, status_code=403)
    
    response = templates.TemplateResponse(request, "budget_management.html", {
        "request": request,
        **get_auth_context(user, entity_id),
    })
    set_entity_cookie_if_needed(response, request, entity_id)
    return response


@router.get("/fx", response_class=HTMLResponse)
async def fx_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """FX Management page - Exchange rates, FX gains/losses, and revaluation."""
    user, entity_id, redirect = await require_auth(request, db, require_entity=True)
    if redirect:
        return redirect
    
    # SKU Feature Gate: MULTI_CURRENCY required (Professional+ tier)
    has_access = await check_view_feature_access(request, db, user, Feature.MULTI_CURRENCY)
    if not has_access:
        return templates.TemplateResponse(request, "feature_locked.html", {
            "request": request,
            **get_auth_context(user, entity_id),
            "feature_name": "FX Management",
            "required_tier": "Professional",
        }, status_code=403)
    
    response = templates.TemplateResponse(request, "fx_management.html", {
        "request": request,
        **get_auth_context(user, entity_id),
    })
    set_entity_cookie_if_needed(response, request, entity_id)
    return response


@router.get("/year-end", response_class=HTMLResponse)
async def year_end_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Year-End Closing page - Period closing and opening balances."""
    user, entity_id, redirect = await require_auth(request, db, require_entity=True)
    if redirect:
        return redirect
    
    # SKU Feature Gate: ADVANCED_REPORTS required (Professional+ tier)
    has_access = await check_view_feature_access(request, db, user, Feature.ADVANCED_REPORTS)
    if not has_access:
        return templates.TemplateResponse(request, "feature_locked.html", {
            "request": request,
            **get_auth_context(user, entity_id),
            "feature_name": "Year-End Closing",
            "required_tier": "Professional",
        }, status_code=403)
    
    response = templates.TemplateResponse(request, "year_end.html", {
        "request": request,
        **get_auth_context(user, entity_id),
    })
    set_entity_cookie_if_needed(response, request, entity_id)
    return response


@router.get("/consolidation", response_class=HTMLResponse)
async def consolidation_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Consolidation page - Group financial statements and intercompany eliminations."""
    user, entity_id, redirect = await require_auth(request, db, require_entity=True)
    if redirect:
        return redirect
    
    # SKU Feature Gate: CONSOLIDATION required (Enterprise tier)
    has_access = await check_view_feature_access(request, db, user, Feature.CONSOLIDATION)
    if not has_access:
        return templates.TemplateResponse(request, "feature_locked.html", {
            "request": request,
            **get_auth_context(user, entity_id),
            "feature_name": "Consolidation",
            "required_tier": "Enterprise",
        }, status_code=403)
    
    response = templates.TemplateResponse(request, "consolidation.html", {
        "request": request,
        **get_auth_context(user, entity_id),
    })
    set_entity_cookie_if_needed(response, request, entity_id)
    return response


@router.get("/fixed-assets", response_class=HTMLResponse)
async def fixed_assets_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Fixed Asset Register management page."""
    user, entity_id, redirect = await require_auth(request, db, require_entity=True)
    if redirect:
        return redirect
    
    # SKU Feature Gate: FIXED_ASSETS required (Professional+ tier)
    has_access = await check_view_feature_access(request, db, user, Feature.FIXED_ASSETS)
    if not has_access:
        return templates.TemplateResponse(request, "feature_locked.html", {
            "request": request,
            **get_auth_context(user, entity_id),
            "feature_name": "Fixed Assets",
            "required_tier": "Professional",
        }, status_code=403)
    
    response = templates.TemplateResponse(request, "fixed_assets.html", {
        "request": request,
        **get_auth_context(user, entity_id),
    })
    set_entity_cookie_if_needed(response, request, entity_id)
    return response


@router.get("/bank-reconciliation", response_class=HTMLResponse)
async def bank_reconciliation_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Bank Reconciliation page - Match transactions with bank statements."""
    user, entity_id, redirect = await require_auth(request, db, require_entity=True)
    if redirect:
        return redirect
    
    # SKU Feature Gate: BANK_RECONCILIATION required (Professional+ tier)
    has_access = await check_view_feature_access(request, db, user, Feature.BANK_RECONCILIATION)
    if not has_access:
        return templates.TemplateResponse(request, "feature_locked.html", {
            "request": request,
            **get_auth_context(user, entity_id),
            "feature_name": "Bank Reconciliation",
            "required_tier": "Professional",
        }, status_code=403)
    
    response = templates.TemplateResponse(request, "bank_reconciliation.html", {
        "request": request,
        **get_auth_context(user, entity_id),
    })
    set_entity_cookie_if_needed(response, request, entity_id)
    return response


@router.get("/expense-claims", response_class=HTMLResponse)
async def expense_claims_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Expense Claims page - Submit and manage expense reimbursements."""
    user, entity_id, redirect = await require_auth(request, db, require_entity=True)
    if redirect:
        return redirect
    
    # SKU Feature Gate: EXPENSE_CLAIMS required (Professional+ tier)
    has_access = await check_view_feature_access(request, db, user, Feature.EXPENSE_CLAIMS)
    if not has_access:
        return templates.TemplateResponse(request, "feature_locked.html", {
            "request": request,
            **get_auth_context(user, entity_id),
            "feature_name": "Expense Claims",
            "required_tier": "Professional",
        }, status_code=403)
    
    response = templates.TemplateResponse(request, "expense_claims.html", {
        "request": request,
        **get_auth_context(user, entity_id),
    })
    set_entity_cookie_if_needed(response, request, entity_id)
    return response


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Settings page."""
    user, entity_id, redirect = await require_auth(request, db)
    if redirect:
        return redirect
    
    return templates.TemplateResponse(request, "settings.html", {
        "request": request,
        **get_auth_context(user, entity_id),
    })


# ===========================================
# ADMIN / STAFF MANAGEMENT PAGES
# ===========================================

@router.get("/admin/verifications", response_class=HTMLResponse)
async def admin_verifications_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Organization verifications page (Admin and Super Admin only)."""
    from app.models.user import PlatformRole
    
    user, entity_id, redirect = await require_auth(request, db, require_entity=False)
    if redirect:
        return redirect
    
    # Only platform staff with Admin or Super Admin role can verify organizations
    if not user.is_platform_staff:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    if user.platform_role not in [PlatformRole.SUPER_ADMIN, PlatformRole.ADMIN]:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    return templates.TemplateResponse(request, "admin_verifications.html", {
        "request": request,
        **get_auth_context(user, entity_id),
    })


@router.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Platform settings page (Super Admin only)."""
    from app.models.user import PlatformRole
    
    user, entity_id, redirect = await require_auth(request, db, require_entity=False)
    if redirect:
        return redirect
    
    # Only Super Admin can access platform settings
    if not user.is_platform_staff:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    if user.platform_role != PlatformRole.SUPER_ADMIN:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    return templates.TemplateResponse(request, "admin_settings.html", {
        "request": request,
        **get_auth_context(user, entity_id),
    })


@router.get("/admin/api-keys", response_class=HTMLResponse)
async def admin_api_keys_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Platform API keys management page (Super Admin only)."""
    from app.models.user import PlatformRole
    
    user, entity_id, redirect = await require_auth(request, db, require_entity=False)
    if redirect:
        return redirect
    
    # Only Super Admin can manage API keys
    if not user.is_platform_staff:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    if user.platform_role != PlatformRole.SUPER_ADMIN:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    return templates.TemplateResponse(request, "admin_api_keys.html", {
        "request": request,
        **get_auth_context(user, entity_id),
    })


@router.get("/admin/security", response_class=HTMLResponse)
async def admin_security_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Security audit page (Super Admin only)."""
    from app.models.user import PlatformRole
    
    user, entity_id, redirect = await require_auth(request, db, require_entity=False)
    if redirect:
        return redirect
    
    # Only Super Admin can access security audit
    if not user.is_platform_staff:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    if user.platform_role != PlatformRole.SUPER_ADMIN:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    return templates.TemplateResponse(request, "admin_security.html", {
        "request": request,
        **get_auth_context(user, entity_id),
    })


@router.get("/admin/automation", response_class=HTMLResponse)
async def admin_automation_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Workflow automation page (Super Admin only)."""
    from app.models.user import PlatformRole
    
    user, entity_id, redirect = await require_auth(request, db, require_entity=False)
    if redirect:
        return redirect
    
    # Only Super Admin can access automation
    if not user.is_platform_staff:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    if user.platform_role != PlatformRole.SUPER_ADMIN:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    return templates.TemplateResponse(request, "admin_automation.html", {
        "request": request,
        **get_auth_context(user, entity_id),
    })


@router.get("/admin/tenants", response_class=HTMLResponse)
async def admin_tenants_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Tenant management page (Super Admin only)."""
    from app.models.user import PlatformRole
    
    user, entity_id, redirect = await require_auth(request, db, require_entity=False)
    if redirect:
        return redirect
    
    if not user.is_platform_staff or user.platform_role not in [PlatformRole.SUPER_ADMIN, PlatformRole.ADMIN]:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    dashboard_service = DashboardService(db)
    dashboard_data = await dashboard_service.get_super_admin_dashboard(user) if user.platform_role == PlatformRole.SUPER_ADMIN else {}
    
    return templates.TemplateResponse(request, "admin_tenants.html", {
        "request": request,
        "dashboard": dashboard_data,
        **get_auth_context(user, entity_id),
    })


@router.get("/admin/support", response_class=HTMLResponse)
async def admin_support_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Support tickets management page."""
    from app.models.user import PlatformRole
    
    user, entity_id, redirect = await require_auth(request, db, require_entity=False)
    if redirect:
        return redirect
    
    if not user.is_platform_staff:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    dashboard_service = DashboardService(db)
    dashboard_data = await dashboard_service.get_super_admin_dashboard(user) if user.platform_role == PlatformRole.SUPER_ADMIN else {}
    
    return templates.TemplateResponse(request, "admin_support.html", {
        "request": request,
        "dashboard": dashboard_data,
        **get_auth_context(user, entity_id),
    })


@router.get("/admin/ml-jobs", response_class=HTMLResponse)
async def admin_ml_jobs_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """ML Jobs management page (Super Admin only)."""
    from app.models.user import PlatformRole
    
    user, entity_id, redirect = await require_auth(request, db, require_entity=False)
    if redirect:
        return redirect
    
    if not user.is_platform_staff or user.platform_role != PlatformRole.SUPER_ADMIN:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    dashboard_service = DashboardService(db)
    dashboard_data = await dashboard_service.get_super_admin_dashboard(user)
    
    return templates.TemplateResponse(request, "admin_ml_jobs.html", {
        "request": request,
        "dashboard": dashboard_data,
        **get_auth_context(user, entity_id),
    })


@router.get("/admin/legal-holds", response_class=HTMLResponse)
async def admin_legal_holds_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Legal Holds management page (Super Admin only)."""
    from app.models.user import PlatformRole
    
    user, entity_id, redirect = await require_auth(request, db, require_entity=False)
    if redirect:
        return redirect
    
    if not user.is_platform_staff or user.platform_role != PlatformRole.SUPER_ADMIN:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    dashboard_service = DashboardService(db)
    dashboard_data = await dashboard_service.get_super_admin_dashboard(user)
    
    return templates.TemplateResponse(request, "admin_legal_holds.html", {
        "request": request,
        "dashboard": dashboard_data,
        **get_auth_context(user, entity_id),
    })


@router.get("/admin/risk-signals", response_class=HTMLResponse)
async def admin_risk_signals_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Risk Signals management page (Super Admin only)."""
    from app.models.user import PlatformRole
    
    user, entity_id, redirect = await require_auth(request, db, require_entity=False)
    if redirect:
        return redirect
    
    if not user.is_platform_staff or user.platform_role != PlatformRole.SUPER_ADMIN:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    dashboard_service = DashboardService(db)
    dashboard_data = await dashboard_service.get_super_admin_dashboard(user)
    
    return templates.TemplateResponse(request, "admin_risk_signals.html", {
        "request": request,
        "dashboard": dashboard_data,
        **get_auth_context(user, entity_id),
    })


@router.get("/admin/emergency-controls", response_class=HTMLResponse)
async def admin_emergency_controls_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Emergency Controls page (Super Admin only) - Kill switches, maintenance mode, feature toggles."""
    from app.models.user import PlatformRole
    from app.services.emergency_control_service import EmergencyControlService
    from app.models.emergency_control import FeatureKey
    
    user, entity_id, redirect = await require_auth(request, db, require_entity=False)
    if redirect:
        return redirect
    
    if not user.is_platform_staff or user.platform_role != PlatformRole.SUPER_ADMIN:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    # Get emergency control data
    emergency_service = EmergencyControlService(db)
    
    # Get platform status
    platform_status = await emergency_service.get_platform_status()
    
    # Get stats
    stats = await emergency_service.get_emergency_stats()
    
    # Get active controls
    active_controls = await emergency_service.get_active_emergency_controls()
    
    # Get recent history
    recent_controls = await emergency_service.get_emergency_control_history(limit=20)
    
    # Build available features list for display
    available_features = [
        {
            "key": FeatureKey.TRANSACTIONS.value,
            "name": "Transactions",
            "description": "All transaction recording"
        },
        {
            "key": FeatureKey.INVOICING.value,
            "name": "Invoicing",
            "description": "Invoice creation and management"
        },
        {
            "key": FeatureKey.PAYMENTS.value,
            "name": "Payments",
            "description": "Payment processing"
        },
        {
            "key": FeatureKey.REPORTS.value,
            "name": "Reports",
            "description": "Financial reporting"
        },
        {
            "key": FeatureKey.TAX_FILING.value,
            "name": "Tax Filing",
            "description": "Tax submission to FIRS"
        },
        {
            "key": FeatureKey.NRS_SUBMISSION.value,
            "name": "NRS Submission",
            "description": "NRS invoice submission"
        },
        {
            "key": FeatureKey.PAYROLL.value,
            "name": "Payroll",
            "description": "Payroll processing"
        },
        {
            "key": FeatureKey.BULK_OPERATIONS.value,
            "name": "Bulk Operations",
            "description": "Bulk imports/exports"
        },
        {
            "key": FeatureKey.API_ACCESS.value,
            "name": "API Access",
            "description": "External API access"
        },
        {
            "key": FeatureKey.USER_SIGNUP.value,
            "name": "User Signup",
            "description": "New user registration"
        },
        {
            "key": FeatureKey.ML_PROCESSING.value,
            "name": "ML Processing",
            "description": "Machine learning jobs"
        },
        {
            "key": FeatureKey.AUDIT_LOGS.value,
            "name": "Audit Logs",
            "description": "Audit log recording"
        },
    ]
    
    # Get suspended tenants count from active controls
    suspended_tenants_count = len([
        c for c in active_controls 
        if c.action_type.value == "TENANT_EMERGENCY_SUSPEND"
    ])
    
    # Get list of suspended tenants for display (simplified)
    suspended_tenants = []
    for control in active_controls:
        if control.action_type.value == "TENANT_EMERGENCY_SUSPEND" and control.target_id:
            suspended_tenants.append({
                "id": str(control.target_id),
                "name": f"Tenant {str(control.target_id)[:8]}...",  # Placeholder
                "suspended_at": control.started_at.strftime("%Y-%m-%d %H:%M") if control.started_at else "Unknown",
                "reason": control.reason or "No reason provided"
            })
    
    # Format recent controls for template
    recent_controls_formatted = []
    for control in recent_controls:
        recent_controls_formatted.append({
            "action_type": control.action_type.value,
            "target_type": control.target_type or "Platform",
            "target_id": str(control.target_id) if control.target_id else None,
            "reason": control.reason or "No reason provided",
            "is_active": control.is_active,
            "started_at": control.started_at.strftime("%Y-%m-%d %H:%M") if control.started_at else "Unknown",
            "ended_at": control.ended_at.strftime("%Y-%m-%d %H:%M") if control.ended_at else None,
        })
    
    return templates.TemplateResponse(request, "admin_emergency_controls.html", {
        "request": request,
        "platform_status": platform_status,
        "active_controls_count": stats.get("active_emergency_controls", 0),
        "suspended_tenants_count": suspended_tenants_count,
        "suspended_tenants": suspended_tenants,
        "available_features": available_features,
        "recent_controls": recent_controls_formatted,
        **get_auth_context(user, entity_id),
    })


@router.get("/admin/staff/onboard", response_class=HTMLResponse)
async def staff_onboard_page(
    request: Request,
    role: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Staff onboarding page (Super Admin and Admin only)."""
    from app.models.user import PlatformRole
    
    user, entity_id, redirect = await require_auth(request, db, require_entity=False)
    if redirect:
        return redirect
    
    # Only platform staff with Admin or Super Admin role can onboard
    if not user.is_platform_staff:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    if user.platform_role not in [PlatformRole.SUPER_ADMIN, PlatformRole.ADMIN]:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    return templates.TemplateResponse(request, "staff_onboard.html", {
        "request": request,
        "preset_role": role,  # Pre-select role if passed in URL
        **get_auth_context(user, entity_id),
    })


@router.get("/admin/users/search", response_class=HTMLResponse)
async def admin_user_search_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """User search page (Super Admin and Admin only)."""
    from app.models.user import PlatformRole, UserRole
    from app.services.admin_user_search_service import AdminUserSearchService
    
    user, entity_id, redirect = await require_auth(request, db, require_entity=False)
    if redirect:
        return redirect
    
    if not user.is_platform_staff:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    if user.platform_role not in [PlatformRole.SUPER_ADMIN, PlatformRole.ADMIN]:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    # Fetch user stats
    try:
        service = AdminUserSearchService(db)
        stats = await service.get_user_stats()
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching user stats: {e}")
        stats = {
            "total_users": 0,
            "active_users": 0,
            "verified_users": 0,
            "platform_staff": 0,
            "organization_users": 0,
            "recent_signups_7d": 0
        }
    
    # Role options for dropdowns
    platform_roles = [role.value for role in PlatformRole]
    org_roles = [role.value for role in UserRole]
    
    return templates.TemplateResponse(request, "admin_user_search.html", {
        "request": request,
        "stats": stats,
        "platform_roles": platform_roles,
        "org_roles": org_roles,
        **get_auth_context(user, entity_id),
    })


@router.get("/admin/platform-staff", response_class=HTMLResponse)
async def admin_platform_staff_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Platform staff management page (Super Admin and Admin only)."""
    from app.models.user import PlatformRole
    from app.services.platform_staff_service import PlatformStaffService
    
    user, entity_id, redirect = await require_auth(request, db, require_entity=False)
    if redirect:
        return redirect
    
    if not user.is_platform_staff:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    if user.platform_role not in [PlatformRole.SUPER_ADMIN, PlatformRole.ADMIN]:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    # Fetch actual data from database
    service = PlatformStaffService(db)
    
    try:
        # Get staff list
        staff_data = await service.list_platform_staff(page=1, page_size=50)
        staff_list = staff_data.get("staff", [])
        pagination = staff_data.get("pagination", {})
        
        # Get stats
        stats = await service.get_staff_stats()
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching platform staff data: {e}")
        staff_list = []
        pagination = {"page": 1, "page_size": 20, "total_count": 0, "total_pages": 0}
        stats = {"total_staff": 0, "active_staff": 0, "inactive_staff": 0, "staff_by_role": {}}
    
    return templates.TemplateResponse(request, "admin_platform_staff.html", {
        "request": request,
        "staff": staff_list,
        "stats": stats,
        "pagination": pagination,
        **get_auth_context(user, entity_id),
    })


# ===========================================
# ENTITY SELECTION
# ===========================================

@router.get("/select-entity", response_class=HTMLResponse)
async def select_entity_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Entity selection page."""
    # Check authentication but don't require entity
    user, _, redirect = await require_auth(request, db, require_entity=False)
    if redirect:
        return redirect
    
    return templates.TemplateResponse(request, "select_entity.html", {
        "request": request,
        **get_auth_context(user, None),
    })


@router.post("/select-entity/{entity_id}")
async def set_entity(
    entity_id: uuid.UUID,
    request: Request,
):
    """Set the current entity in session."""
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="entity_id",
        value=str(entity_id),
        httponly=True,
        max_age=60 * 60 * 24 * 30,  # 30 days
        samesite="lax",
    )
    return response


# ===========================================
# LEGAL & POLICY PAGES
# ===========================================

@router.get("/terms", response_class=HTMLResponse)
async def terms_page(request: Request):
    """Terms and Conditions page."""
    return templates.TemplateResponse(request, "legal/terms.html", {"request": request})


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    """Privacy Policy page."""
    return templates.TemplateResponse(request, "legal/privacy.html", {"request": request})


@router.get("/cookies", response_class=HTMLResponse)
async def cookies_page(request: Request):
    """Cookie Policy page."""
    return templates.TemplateResponse(request, "legal/cookies.html", {"request": request})


@router.get("/faq", response_class=HTMLResponse)
async def faq_page(request: Request):
    """FAQ page."""
    return templates.TemplateResponse(request, "legal/faq.html", {"request": request})


@router.get("/security", response_class=HTMLResponse)
async def security_page(request: Request):
    """Security Policy page."""
    return templates.TemplateResponse(request, "legal/security.html", {"request": request})


# ===========================================
# 2026 TAX REFORM
# ===========================================

@router.get("/tax-2026", response_class=HTMLResponse)
async def tax_2026_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """2026 Tax Reform compliance page."""
    # Require entity selection - redirect to select-entity if not selected
    user, entity_id, redirect = await require_auth(request, db, require_entity=True)
    if redirect:
        return redirect
    
    response = templates.TemplateResponse(request, "tax_2026.html", {
        "request": request,
        **get_auth_context(user, entity_id),
    })
    set_entity_cookie_if_needed(response, request, entity_id)
    return response


# ===========================================
# PASSWORD RESET
# ===========================================

@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    """Forgot password page."""
    return templates.TemplateResponse(request, "forgot_password.html", {"request": request})


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, token: str = None):
    """Reset password page."""
    return templates.TemplateResponse(request, "reset_password.html", {"request": request, "token": token})


# ===========================================
# EMAIL VERIFICATION
# ===========================================

@router.get("/verify-email", response_class=HTMLResponse)
async def verify_email_page(request: Request, token: str = None):
    """Email verification page."""
    return templates.TemplateResponse(request, "verify_email.html", {"request": request, "token": token})


# ===========================================
# WORLD-CLASS AUDIT PAGES
# ===========================================

@router.get("/audit", response_class=HTMLResponse)
async def audit_unified_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Unified Audit Center - Comprehensive audit tools.
    
    Provides access to:
    - Audit Dashboard with integrity verification
    - Audit Logs with filtering and export
    - Forensic Analysis (Benford's Law, Z-Score Anomalies)
    - Audit Runs management
    - Findings and Evidence tracking
    - Tax Explainability (PAYE, VAT)
    - Audit Vault with NTAA 2025 compliance
    - Payroll Decisions audit trail
    """
    user, entity_id, redirect = await require_auth(request, db, require_entity=True)
    if redirect:
        return redirect
    
    response = templates.TemplateResponse(request, "audit_unified.html", {
        "request": request,
        **get_auth_context(user, entity_id),
    })
    set_entity_cookie_if_needed(response, request, entity_id)
    return response


@router.get("/audit-dashboard", response_class=HTMLResponse)
async def audit_dashboard_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Legacy audit dashboard - redirects to unified audit."""
    return RedirectResponse(url="/audit", status_code=status.HTTP_302_FOUND)


@router.get("/audit-old", response_class=HTMLResponse)
async def audit_old_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Legacy Audit Dashboard for backwards compatibility.
    """
    user, entity_id, redirect = await require_auth(request, db, require_entity=True)
    if redirect:
        return redirect
    
    response = templates.TemplateResponse(request, "audit_dashboard.html", {
        "request": request,
        **get_auth_context(user, entity_id),
    })
    set_entity_cookie_if_needed(response, request, entity_id)
    return response


@router.get("/audit-logs", response_class=HTMLResponse)
async def audit_logs_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Redirect to unified audit page - Logs tab."""
    return RedirectResponse(url="/audit?tab=logs", status_code=302)


@router.get("/forensic-audit", response_class=HTMLResponse)
async def forensic_audit_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Redirect to unified audit page - Forensic tab."""
    return RedirectResponse(url="/audit?tab=forensic", status_code=302)


@router.get("/advanced-audit", response_class=HTMLResponse)
async def advanced_audit_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Redirect to unified audit page - Advanced tab."""
    return RedirectResponse(url="/audit?tab=advanced", status_code=302)


@router.get("/worm-storage", response_class=HTMLResponse)
async def worm_storage_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Redirect to unified audit page - WORM Storage tab."""
    return RedirectResponse(url="/audit?tab=worm", status_code=302)


# ===========================================
# MACHINE LEARNING & AI PAGES
# ===========================================

@router.get("/business-insights", response_class=HTMLResponse)
async def business_insights_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Business Insights Dashboard.
    
    AI-powered analytics providing:
    - Cash Flow Forecasting (ARIMA, Holt-Winters, LSTM)
    - Growth Prediction (Linear, Polynomial, Neural Network)
    - NLP Analysis (Sentiment, Entities, Keywords, Classification)
    - OCR Document Processing (Azure, Tesseract, Internal)
    - Custom Model Training (Neural Networks, LSTM)
    """
    user, entity_id, redirect = await require_auth(request, db, require_entity=True)
    if redirect:
        return redirect
    
    # SKU Feature Gate: ADVANCED_REPORTS required (Professional+ tier)
    has_access = await check_view_feature_access(request, db, user, Feature.ADVANCED_REPORTS)
    if not has_access:
        return templates.TemplateResponse(request, "feature_locked.html", {
            "request": request,
            **get_auth_context(user, entity_id),
            "feature_name": "Business Insights",
            "required_tier": "Professional",
        }, status_code=403)
    
    response = templates.TemplateResponse(request, "business_insights.html", {
        "request": request,
        **get_auth_context(user, entity_id),
    })
    set_entity_cookie_if_needed(response, request, entity_id)
    return response


# ===========================================
# FEATURE GATE - UPGRADE PROMPTS
# ===========================================

@router.get("/feature-unavailable", response_class=HTMLResponse)
async def feature_unavailable_page(
    request: Request,
    feature: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Display upgrade prompt when a feature is not available.
    
    This page is shown when:
    - User tries to access a feature not in their SKU tier
    - Feature check fails at API or UI level
    
    Query params:
        feature: The feature that was denied (e.g., 'payroll', 'bank_reconciliation')
    """
    from app.utils.sku_context import get_sku_context, get_feature_upgrade_prompt
    
    user, entity_id, redirect = await require_auth(request, db, require_entity=False)
    if redirect:
        return redirect
    
    # Get SKU context for the user's organization
    sku = None
    if user and user.organization_id:
        sku = await get_sku_context(db, user.organization_id)
    
    # Get feature-specific upgrade prompt info
    feature_info = get_feature_upgrade_prompt(feature) if feature else {}
    
    response = templates.TemplateResponse(request, "feature_unavailable.html", {
        "request": request,
        "sku": sku,
        "feature": feature,
        "feature_title": feature_info.get("title", "Feature Unavailable"),
        "feature_description": feature_info.get("description", "This feature requires a higher tier plan."),
        "feature_icon": feature_info.get("icon", "⭐"),
        "required_tier": feature_info.get("required_tier", "professional"),
        **get_auth_context(user, entity_id),
    })
    return response


@router.get("/pricing", response_class=HTMLResponse)
async def pricing_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Pricing page showing all SKU tiers.
    
    Displays:
    - Core, Professional, Enterprise tier pricing (in Naira)
    - Intelligence add-on pricing
    - Feature comparison matrix
    """
    from app.utils.sku_context import get_sku_context
    from app.config.sku_config import TIER_PRICING, INTELLIGENCE_PRICING
    
    user = await get_user_from_token(request, db)
    entity_id = get_entity_id_from_session(request)
    
    # Get SKU context if user is logged in
    sku = None
    if user and user.organization_id:
        sku = await get_sku_context(db, user.organization_id)
    
    return templates.TemplateResponse(request, "pricing.html", {
        "request": request,
        "sku": sku,
        "tier_pricing": TIER_PRICING,
        "intelligence_pricing": INTELLIGENCE_PRICING,
        **get_auth_context(user, entity_id),
    })


@router.get("/checkout", response_class=HTMLResponse)
async def checkout_page(
    request: Request,
    tier: str = None,
    billing_cycle: str = "monthly",
    db: AsyncSession = Depends(get_db),
):
    """
    Checkout page for subscription upgrades.
    
    Requires authentication. Allows users to:
    - Select tier and billing cycle
    - Add intelligence add-on
    - Add additional users
    - Proceed to Paystack payment
    """
    from app.utils.sku_context import get_sku_context
    
    user, entity_id, redirect = await require_auth(request, db, require_entity=False)
    if redirect:
        return redirect
    
    # Get current SKU context
    sku = None
    if user and user.organization_id:
        sku = await get_sku_context(db, user.organization_id)
    
    return templates.TemplateResponse(request, "checkout.html", {
        "request": request,
        "sku": sku,
        "tier": tier or (sku.tier.value if sku else "professional"),
        "billing_cycle": billing_cycle,
        **get_auth_context(user, entity_id),
    })


@router.get("/payment-success", response_class=HTMLResponse)
async def payment_success_page(
    request: Request,
    reference: str = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Payment success page.
    
    Shown after successful Paystack payment verification.
    Displays order confirmation and next steps.
    """
    from datetime import datetime
    from app.utils.sku_context import get_sku_context
    from app.services.billing_service import BillingService
    
    user, entity_id, redirect = await require_auth(request, db, require_entity=False)
    if redirect:
        return redirect
    
    # Get current SKU context (should be updated after payment)
    sku = None
    tier_name = "Professional"
    amount = None
    
    if user and user.organization_id:
        sku = await get_sku_context(db, user.organization_id)
        if sku:
            tier_name = sku.tier_display_name
    
    # Verify payment if reference provided
    if reference:
        try:
            billing_service = BillingService(db)
            result = await billing_service.verify_and_process_payment(reference)
            if result.success and result.amount:
                amount = result.amount
        except Exception:
            pass  # Don't fail the success page if verification has issues
    
    return templates.TemplateResponse(request, "payment_success.html", {
        "request": request,
        "sku": sku,
        "tier_name": tier_name,
        "reference": reference,
        "amount": amount,
        "now": datetime.now,
        **get_auth_context(user, entity_id),
    })


@router.get("/payment-failed", response_class=HTMLResponse)
async def payment_failed_page(
    request: Request,
    tier: str = None,
    error: str = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Payment failed page.
    
    Shown when payment is cancelled or fails.
    Provides options to retry or contact support.
    """
    user, entity_id, redirect = await require_auth(request, db, require_entity=False)
    if redirect:
        return redirect
    
    return templates.TemplateResponse(request, "payment_failed.html", {
        "request": request,
        "tier": tier,
        "error_message": error,
        **get_auth_context(user, entity_id),
    })


# ===========================================
# HTMX PARTIAL ENDPOINTS (for dashboard refresh)
# ===========================================

@router.get("/api/v1/partials/legal-holds-table", response_class=HTMLResponse)
async def legal_holds_table_partial(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    HTMX partial endpoint for legal holds table.
    Returns just the table HTML for HTMX refresh.
    """
    from app.models.user import PlatformRole
    
    user, entity_id, redirect = await require_auth(request, db, require_entity=False)
    if redirect or not user.is_platform_staff or user.platform_role != PlatformRole.SUPER_ADMIN:
        return HTMLResponse(status_code=403, content="<tr><td colspan='7'>Access Denied</td></tr>")
    
    dashboard_service = DashboardService(db)
    dashboard_data = await dashboard_service.get_super_admin_dashboard()
    
    return templates.TemplateResponse(request, "partials/super_admin/legal_holds.html", {
        "request": request,
        "dashboard": dashboard_data,
    })


@router.get("/api/v1/partials/risk-signals-table", response_class=HTMLResponse)
async def risk_signals_table_partial(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    HTMX partial endpoint for risk signals table.
    Returns just the table HTML for HTMX refresh.
    """
    from app.models.user import PlatformRole
    
    user, entity_id, redirect = await require_auth(request, db, require_entity=False)
    if redirect or not user.is_platform_staff or user.platform_role != PlatformRole.SUPER_ADMIN:
        return HTMLResponse(status_code=403, content="<tr><td colspan='8'>Access Denied</td></tr>")
    
    dashboard_service = DashboardService(db)
    dashboard_data = await dashboard_service.get_super_admin_dashboard()
    
    return templates.TemplateResponse(request, "partials/super_admin/risk_signals.html", {
        "request": request,
        "dashboard": dashboard_data,
    })


@router.get("/api/v1/partials/ml-jobs-table", response_class=HTMLResponse)
async def ml_jobs_table_partial(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    HTMX partial endpoint for ML jobs table.
    Returns just the table HTML for HTMX refresh.
    """
    from app.models.user import PlatformRole
    
    user, entity_id, redirect = await require_auth(request, db, require_entity=False)
    if redirect or not user.is_platform_staff or user.platform_role != PlatformRole.SUPER_ADMIN:
        return HTMLResponse(status_code=403, content="<tr><td colspan='7'>Access Denied</td></tr>")
    
    dashboard_service = DashboardService(db)
    dashboard_data = await dashboard_service.get_super_admin_dashboard()
    
    return templates.TemplateResponse(request, "partials/super_admin/ml_jobs.html", {
        "request": request,
        "dashboard": dashboard_data,
    })


@router.get("/api/v1/partials/ml-models-grid", response_class=HTMLResponse)
async def ml_models_grid_partial(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    HTMX partial endpoint for ML models grid.
    Returns just the grid HTML for HTMX refresh.
    """
    from app.models.user import PlatformRole
    
    user, entity_id, redirect = await require_auth(request, db, require_entity=False)
    if redirect or not user.is_platform_staff or user.platform_role != PlatformRole.SUPER_ADMIN:
        return HTMLResponse(status_code=403, content="<div>Access Denied</div>")
    
    dashboard_service = DashboardService(db)
    dashboard_data = await dashboard_service.get_super_admin_dashboard()
    
    return templates.TemplateResponse(request, "partials/super_admin/models.html", {
        "request": request,
        "dashboard": dashboard_data,
    })


@router.get("/api/v1/partials/upsell-table", response_class=HTMLResponse)
async def upsell_table_partial(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    HTMX partial endpoint for upsell opportunities table.
    Returns just the table HTML for HTMX refresh.
    """
    from app.models.user import PlatformRole
    
    user, entity_id, redirect = await require_auth(request, db, require_entity=False)
    if redirect or not user.is_platform_staff or user.platform_role != PlatformRole.SUPER_ADMIN:
        return HTMLResponse(status_code=403, content="<tr><td colspan='8'>Access Denied</td></tr>")
    
    dashboard_service = DashboardService(db)
    dashboard_data = await dashboard_service.get_super_admin_dashboard()
    
    return templates.TemplateResponse(request, "partials/super_admin/upsell.html", {
        "request": request,
        "dashboard": dashboard_data,
    })


@router.get("/api/v1/partials/support-tickets-table", response_class=HTMLResponse)
async def support_tickets_table_partial(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    HTMX partial endpoint for support tickets table.
    Returns just the table HTML for HTMX refresh.
    """
    from app.models.user import PlatformRole
    
    user, entity_id, redirect = await require_auth(request, db, require_entity=False)
    if redirect or not user.is_platform_staff or user.platform_role != PlatformRole.SUPER_ADMIN:
        return HTMLResponse(status_code=403, content="<tr><td colspan='8'>Access Denied</td></tr>")
    
    dashboard_service = DashboardService(db)
    dashboard_data = await dashboard_service.get_super_admin_dashboard()
    
    return templates.TemplateResponse(request, "partials/super_admin/support.html", {
        "request": request,
        "dashboard": dashboard_data,
    })

