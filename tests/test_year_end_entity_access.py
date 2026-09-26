"""
Regression coverage for Finding 18 (docs/IMPLEMENTATION_ROADMAP.md Phase 2, Section 2.1) as it
applies to app/routers/year_end.py -- 12 endpoints whose entity_id is an *optional* query parameter,
previously "resolved" by the now-deleted resolve_entity_id() helper: a confirmed fake safety net that
returned a caller-supplied entity_id completely unvalidated, only doing anything on the fallback path
(no entity_id given at all).

Replaced with resolve_and_verify_entity_id(), which calls require_entity_access when entity_id is
provided (can't use Depends() since the parameter is optional) and preserves the old fallback
behavior (pick the caller's own first entity) when it isn't.

reopen_fiscal_year gets its own dedicated test: it previously accepted entity_id but never used it for
anything at all -- its FiscalYear lookup was scoped by fiscal_year_id alone, letting any authenticated
user reopen any organization's closed fiscal year. Fixed by scoping that lookup to the
now-verified entity_id too.

This router carries a router-level require_feature([Feature.ADVANCED_REPORTS]) gate (Professional
tier), so these tests call resolve_and_verify_entity_id and the route handlers directly rather than
over HTTP (which would 403 on the SKU gate before reaching the access check, same as
budget.py/fixed_assets.py/fx.py/forensic_audit.py).
"""
import pytest
from fastapi import HTTPException

from app.routers.year_end import resolve_and_verify_entity_id, reopen_fiscal_year


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


class TestReopenFiscalYear:
    async def test_rejects_foreign_entity_before_touching_any_fiscal_year(
        self, db_session, other_entity, test_user
    ):
        """
        The real bug fixed here: this endpoint used to accept entity_id but never use it at all, so
        any fiscal_year_id (belonging to any organization) could be reopened. Passing a foreign
        entity_id must now be rejected up front, before the (nonexistent, in this test) fiscal_year_id
        is ever looked up.
        """
        import uuid

        with pytest.raises(HTTPException) as exc_info:
            await reopen_fiscal_year(
                fiscal_year_id=uuid.uuid4(),
                reopen_reason="This entity does not belong to the caller's organization",
                entity_id=other_entity.id,
                db=db_session,
                current_user=test_user,
            )
        assert exc_info.value.status_code == 404
