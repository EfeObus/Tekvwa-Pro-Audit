"""
Regression coverage for Finding 18 (docs/IMPLEMENTATION_ROADMAP.md Phase 2, Section 2.1) as it
applies to app/routers/report_export.py -- 8 endpoints whose entity_id is an *optional* query
parameter, previously "resolved" by the now-deleted resolve_entity_id() helper: a confirmed fake
safety net that returned a caller-supplied entity_id completely unvalidated, only doing anything on
the fallback path (no entity_id given at all). Identical bug and fix to year_end.py's.

Replaced with resolve_and_verify_entity_id(), which calls require_entity_access when entity_id is
provided (can't use Depends() since the parameter is optional) and preserves the old fallback
behavior (pick the caller's own first entity) when it isn't.

Also fixes a second, unrelated, pre-existing bug found while writing test_rejects_foreign_entity
below: this file's endpoints all wrapped their bodies in `except ValueError / except Exception`, with
no `except HTTPException: raise` guard -- Python's exception matching is first-match, so `except
Exception` (a superclass of everything, including HTTPException) caught the 404 raised by
require_entity_access and re-wrapped it as a 500 with the original message stuffed into the detail
string. Access was still correctly denied either way (no data leaked), but the status code was wrong.
Confirmed live: the first version of this test failed with exactly that 500-wrapping-a-404 response
before the guard was added to all 8 endpoints (same fix applied to year_end.py, which had the
identical pattern on 9 of its 12 endpoints).

This router has no SKU feature gate, so HTTP-level testing is practical for the representative
export_balance_sheet_get endpoint (JSON export bodies for the POST variants would need real
accounting data to render without erroring, so the direct helper-function tests are the primary
coverage here).
"""
import pytest
from fastapi import HTTPException
from httpx import AsyncClient

from app.routers.report_export import resolve_and_verify_entity_id


class TestResolveAndVerifyEntityId:
    async def test_rejects_foreign_entity(self, db_session, other_entity, test_user):
        with pytest.raises(HTTPException) as exc_info:
            await resolve_and_verify_entity_id(db_session, other_entity.id, test_user)
        assert exc_info.value.status_code == 404

    async def test_allows_own_entity(self, db_session, test_entity, test_user):
        result = await resolve_and_verify_entity_id(db_session, test_entity.id, test_user)
        assert result == test_entity.id

    async def test_falls_back_to_first_org_entity_when_omitted(self, db_session, test_entity, test_user):
        result = await resolve_and_verify_entity_id(db_session, None, test_user)
        assert result == test_entity.id


class TestExportBalanceSheetHttp:
    async def test_rejects_foreign_entity(self, client: AsyncClient, auth_headers: dict, other_entity):
        response = await client.get(
            f"/api/v1/reports/export/balance-sheet?as_of_date=2026-01-01&entity_id={other_entity.id}",
            headers=auth_headers,
        )
        assert response.status_code == 404, response.text
