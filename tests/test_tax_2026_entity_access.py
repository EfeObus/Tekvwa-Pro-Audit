"""
Regression coverage for tax_2026.py, touched for two reasons this session:

1. Finding 18 (docs/IMPLEMENTATION_ROADMAP.md Phase 2, Section 2.1): 4 endpoints
   (generate_cit_self_assessment, generate_vat_self_assessment, generate_annual_returns,
   export_for_taxpro_max) had no access check at all -- unlike the ~35 other endpoints in this file,
   which all call a file-local verify_entity_access() helper. Fixed with Depends(require_entity_access),
   same as every other migrated file.

2. Two severe, unrelated, pre-existing bugs found and fixed while investigating this file (not Finding
   18, documented in full in docs/REMEDIATION_LOG.md):
   - The file-local verify_entity_access() called EntityService.get_entity_by_id(entity_id) with only
     one argument, but that method requires a second `user` argument -- every one of the ~35 endpoints
     using it crashed with a TypeError on every single call, regardless of entity ownership.
   - main.py double-mounted this router's prefix (both the router's own internal
     prefix="/api/v1/tax-2026" AND main.py's include_router(..., prefix="/api/v1/tax-2026")), so every
     endpoint in this file was actually reachable only at
     /api/v1/tax-2026/api/v1/tax-2026/{entity_id}/... -- not the documented/expected URL.

Not added to tests/test_entity_access_isolation.py's MIGRATED_ROUTER_FILES: that sweep would need to
treat this file's local verify_entity_access() as a safe alternative to Depends(require_entity_access),
but the *shared* app.dependencies.verify_entity_access (a different function, used in 10 other files) is
a documented, still-open, "additive not restrictive" bug -- teaching the sweep to accept any
verify_entity_access() call as safe would incorrectly certify those other 10 files too. Verified here
instead, scoped to this file only.
"""
import ast
from pathlib import Path as FilePath

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.routers.tax_2026 import verify_entity_access as local_verify_entity_access
from app.models.user import User

ROUTER_PATH = FilePath(__file__).resolve().parent.parent / "app" / "routers" / "tax_2026.py"
NEWLY_PROTECTED_FUNCTIONS = [
    "generate_cit_self_assessment",
    "generate_vat_self_assessment",
    "generate_annual_returns",
    "export_for_taxpro_max",
]


class TestLocalVerifyEntityAccessCrashFix:
    """The ~35 other endpoints in this file all depend on this local helper working at all."""

    async def _reload_with_entity_access(self, db_session, user):
        result = await db_session.execute(
            select(User).options(selectinload(User.entity_access)).where(User.id == user.id)
        )
        return result.scalar_one()

    async def test_allows_own_entity_without_crashing(self, db_session, test_entity, test_user):
        user = await self._reload_with_entity_access(db_session, test_user)
        result = await local_verify_entity_access(
            entity_id=test_entity.id, current_user=user, db=db_session
        )
        assert result.id == test_entity.id

    async def test_rejects_foreign_entity(self, db_session, other_entity, test_user):
        user = await self._reload_with_entity_access(db_session, test_user)
        with pytest.raises(HTTPException) as exc_info:
            await local_verify_entity_access(
                entity_id=other_entity.id, current_user=user, db=db_session
            )
        assert exc_info.value.status_code in (403, 404)


class TestSelfAssessmentEndpointsWired:
    """Scoped AST check for just the 4 newly-fixed functions -- not added to the shared
    MIGRATED_ROUTER_FILES sweep for the reason in this module's docstring."""

    def test_all_four_have_require_entity_access(self):
        source = ROUTER_PATH.read_text()
        tree = ast.parse(source, filename="tax_2026.py")

        found = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in NEWLY_PROTECTED_FUNCTIONS:
                defaults = [*node.args.defaults, *node.args.kw_defaults]
                found[node.name] = any(
                    d is not None and "require_entity_access" in ast.dump(d) for d in defaults
                )

        missing = [name for name in NEWLY_PROTECTED_FUNCTIONS if not found.get(name)]
        assert not missing, f"Missing Depends(require_entity_access): {missing}"
        assert set(found) == set(NEWLY_PROTECTED_FUNCTIONS)


class TestRouterMountFix:
    async def test_no_doubled_prefix_in_openapi_schema(self, client: AsyncClient):
        response = await client.get("/openapi.json")
        schema = response.json()
        doubled = [p for p in schema.get("paths", {}).keys() if p.count("tax-2026") > 1]
        assert not doubled, f"Still double-prefixed: {doubled}"
