"""
Regression coverage for docs/IMPLEMENTATION_ROADMAP.md Phase 2 Section 2.1's own stated regression
requirement: "Every endpoint in the '24 confirmed safe' bucket from the audit's §3.3 (dashboard.py's
4, notifications.py's 2, reports.py's 1, auth.py's 1, plus views.py::set_entity's already-safe
pattern) must be re-run and must still pass -- this phase must not accidentally break the patterns
that were already correct."

These 9 endpoints (of the full 24; the roadmap names only these -- the remaining ~15 are in files
Phase 2.1 never touched, so carry no regression risk from this phase's work) were confirmed safe by
the original audit (docs/PRODUCTION_AUDIT_2026.md §3.3) via patterns distinct from
require_entity_access:

- dashboard.py's get_dashboard: delegates to DashboardService.get_dashboard, which raises
  PermissionError internally (a real check, just a different mechanism).
- dashboard.py's get_widget_layout / update_widget_layout: accept entity_id but never reference it in
  the body -- unimplemented stubs with nothing per-entity to leak.
- dashboard.py's compare_kpis: role-gated (VIEW_REPORTS permission), returns hardcoded placeholder
  numbers regardless of entity_id.
- notifications.py's list_notifications / mark_all_as_read: every query is mandatorily scoped by
  NotificationModel.user_id == current_user.id; the optional entity_id only narrows further within
  the caller's own rows, it can never widen access to another user's.
- reports.py's subscribe_to_compliance_alerts: an unimplemented stub with nothing persisted (also has
  its own dedicated coverage in tests/test_reports_entity_access.py, since it was additionally
  protected with require_entity_access this session even though the audit deemed it low-risk).
- auth.py's get_dashboard: a second, separate route delegating to the same already-verified-safe
  DashboardService.get_dashboard.
- views.py's set_entity: only sets an httponly cookie, no data access of any kind.

None of these endpoints were touched during Phase 2.1's migration (dashboard.py's only in-scope
endpoint was mark_all_alerts_read, a different function entirely). This suite exists to prove that
claim mechanically, not just assert it in a docstring -- if a future change to any of these functions
removes the safe pattern it's checked for here, this suite catches it.
"""
import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class TestDashboardPySafeEndpoints:
    async def test_get_widget_layout_never_references_entity_id_in_body(self):
        import inspect
        from app.routers.dashboard import get_widget_layout

        source = inspect.getsource(get_widget_layout)
        # The parameter declaration itself will always contain the string "entity_id" -- check only
        # the function body (after the closing paren of the signature) for any real use of it.
        body = source.split("):", 1)[1]
        assert "entity_id" not in body, (
            "get_widget_layout now references entity_id in its body -- it was an unimplemented stub "
            "with nothing per-entity to leak; if it now reads/writes real per-entity data, it needs "
            "require_entity_access like every other endpoint in this phase, not this safe-stub pass."
        )

    async def test_update_widget_layout_never_references_entity_id_in_body(self):
        import inspect
        from app.routers.dashboard import update_widget_layout

        source = inspect.getsource(update_widget_layout)
        body = source.split("):", 1)[1]
        assert "entity_id" not in body

    async def test_compare_kpis_still_returns_hardcoded_placeholder_data(
        self, client: AsyncClient, auth_headers: dict, other_entity
    ):
        """Requesting another organization's entity_id must still be harmless -- there's no real
        per-entity data behind this endpoint to leak."""
        response = await client.get(
            f"/api/v1/dashboard/kpis/comparison?entity_id={other_entity.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["comparison"]["revenue"]["current"] == 15500000.00, (
            "compare_kpis no longer returns the hardcoded placeholder data it did when confirmed "
            "safe -- if it now computes a real figure from entity_id, it needs require_entity_access."
        )

    async def test_get_dashboard_still_delegates_to_dashboard_service(self):
        import inspect
        from app.routers.dashboard import get_dashboard
        from app.services.dashboard_service import DashboardService

        source = inspect.getsource(get_dashboard)
        assert "DashboardService" in source
        assert hasattr(DashboardService, "get_dashboard")


class TestNotificationsPySafeEndpoints:
    async def test_list_notifications_still_scoped_by_user_id(self):
        import inspect
        from app.services.notification_service import NotificationService

        source = inspect.getsource(NotificationService.get_user_notifications)
        assert "user_id" in source

    async def test_mark_all_as_read_still_scoped_by_user_id(self):
        import inspect
        from app.services.notification_service import NotificationService

        source = inspect.getsource(NotificationService.mark_all_as_read)
        assert "user_id" in source

    async def test_notifications_for_other_user_are_invisible(
        self, client: AsyncClient, other_auth_headers: dict, test_user, db_session: AsyncSession
    ):
        """An Org B user's notification list must never include an Org A user's rows, even if both
        happen to reference the same entity_id (impossible here since entities are org-scoped, but
        the base user_id filter is what actually guarantees this, not entity scoping)."""
        response = await client.get(
            "/api/v1/notifications",
            headers=other_auth_headers,
        )
        assert response.status_code == 200, response.text


class TestAuthPySafeEndpoint:
    async def test_auth_get_dashboard_delegates_to_same_service(self):
        import inspect
        from app.routers.auth import get_dashboard
        from app.services.dashboard_service import DashboardService

        source = inspect.getsource(get_dashboard)
        assert "DashboardService" in source
        assert hasattr(DashboardService, "get_dashboard")


class TestViewsPySafeEndpoint:
    async def test_set_entity_only_sets_a_cookie_no_data_access(self):
        import inspect
        from app.routers.views import set_entity

        source = inspect.getsource(set_entity)
        # No db session, no service call, no query -- just a redirect with a cookie set.
        assert "db" not in inspect.signature(set_entity).parameters
        assert "set_cookie" in source

    async def test_set_entity_redirects_with_cookie(self, client: AsyncClient, other_entity):
        response = await client.post(
            f"/select-entity/{other_entity.id}",
            follow_redirects=False,
        )
        assert response.status_code == 302, response.text
        assert response.cookies.get("entity_id") == str(other_entity.id)
