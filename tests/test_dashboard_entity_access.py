"""
Regression coverage for Finding 18 (docs/IMPLEMENTATION_ROADMAP.md Phase 2, Section 2.1) as it applies
to app/routers/dashboard.py::mark_all_alerts_read -- the only one of this file's ~21 endpoints in
scope for this section (the other 20 already use a different, confirmed-safe pattern,
DashboardService._get_entity_if_accessible, and are deliberately left untouched).

mark_all_alerts_read's entity_id is an *optional* filter (unlike accounting.py/audit.py/budget.py's
required entity_id path params), so it can't take Depends(require_entity_access) directly -- that
would make the parameter mandatory. The fix is an inline require_entity_access(...) call, only when
entity_id is actually provided. These tests prove that inline check behaves the same as the Depends()
form elsewhere: rejects a foreign organization's entity_id, allows the caller's own, and -- the part
unique to the optional-parameter case -- still works with no entity_id at all.
"""
import pytest
from httpx import AsyncClient


async def test_mark_all_alerts_read_rejects_foreign_entity(client: AsyncClient, auth_headers: dict, other_entity):
    response = await client.post(
        f"/api/v1/dashboard/alerts/read-all?entity_id={other_entity.id}",
        headers=auth_headers,
    )
    assert response.status_code == 404, response.text


async def test_mark_all_alerts_read_allows_own_entity(client: AsyncClient, auth_headers: dict, test_entity):
    response = await client.post(
        f"/api/v1/dashboard/alerts/read-all?entity_id={test_entity.id}",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text


async def test_mark_all_alerts_read_allows_no_entity_filter(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/v1/dashboard/alerts/read-all",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
