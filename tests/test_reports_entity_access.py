"""
Regression coverage for Finding 18 (docs/IMPLEMENTATION_ROADMAP.md Phase 2, Section 2.1) as it applies
to app/routers/reports.py -- 22 endpoints (the roadmap's own count was 21, excluding
subscribe_to_compliance_alerts as low-risk since its underlying service call is an unimplemented stub
that reads/persists nothing; fixed it anyway here since the check is harmless and pre-emptively covers
it once the stub is implemented for real).

This router has no SKU feature gate (unlike budget.py/fixed_assets.py/fx.py/forensic_audit.py/
ml_ai.py), so HTTP-level testing is practical here. Exercises a representative read endpoint
(get_dashboard_metrics) and the previously-unprotected stub endpoint
(subscribe_to_compliance_alerts) -- proving the fix, not repeating the full 22-endpoint AST-covered
sweep as HTTP round trips too.
"""
import pytest
from httpx import AsyncClient


class TestDashboardMetrics:
    async def test_rejects_foreign_entity(self, client: AsyncClient, auth_headers: dict, other_entity):
        response = await client.get(
            f"/api/v1/entities/{other_entity.id}/reports/dashboard",
            headers=auth_headers,
        )
        assert response.status_code == 404, response.text

    async def test_allows_own_entity(self, client: AsyncClient, auth_headers: dict, test_entity):
        response = await client.get(
            f"/api/v1/entities/{test_entity.id}/reports/dashboard",
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text


class TestSubscribeToComplianceAlerts:
    async def test_rejects_foreign_entity(self, client: AsyncClient, auth_headers: dict, other_entity):
        response = await client.post(
            f"/api/v1/entities/{other_entity.id}/reports/compliance-health/subscribe",
            headers=auth_headers,
        )
        assert response.status_code == 404, response.text
