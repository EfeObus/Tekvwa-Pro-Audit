"""
Regression coverage for Finding 18 (docs/IMPLEMENTATION_ROADMAP.md Phase 2, Section 2.1) --
the cross-tenant IDOR audit finding, and its fix, the centralized `require_entity_access`
dependency in `app/dependencies.py`.

Two layers of test, matching the roadmap's own stated verification method:

1. A direct test of `require_entity_access` itself: an Org A user requesting Org B's entity_id
   must be rejected (404) regardless of role (OWNER doesn't bypass cross-organization checks,
   only same-organization role checks); an Org A user requesting their own entity succeeds.

2. A structural, AST-based test ("a route with a raw entity_id param and no
   require_entity_access dependency is, by definition, unfixed" -- the roadmap's own words) that
   scans a specific list of router files this phase has migrated and asserts every function
   taking `entity_id: uuid.UUID = Path(...)` also has `Depends(require_entity_access)` in its
   signature. This is cheap to run against all 164 endpoints as they're migrated file by file,
   without needing a hand-written request-based test per endpoint -- add each file to
   `MIGRATED_ROUTER_FILES` below as it's completed.
"""
import ast
from pathlib import Path as FilePath

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import require_entity_access
from app.models.entity import BusinessEntity
from app.models.organization import Organization
from app.models.user import User

ROUTERS_DIR = FilePath(__file__).resolve().parent.parent / "app" / "routers"

# Files fully migrated to Depends(require_entity_access) so far. Add to this list as each of
# Phase 2 Section 2.1's 17 files is completed -- every file here is asserted to have zero
# remaining unmigrated entity-scoped endpoints.
MIGRATED_ROUTER_FILES = [
    "accounting.py",
    "audit.py",
]


class TestRequireEntityAccess:
    async def test_rejects_foreign_organizations_entity(
        self,
        db_session: AsyncSession,
        test_organization: Organization,
        test_user: User,
        other_entity: BusinessEntity,
    ):
        """Org A's (OWNER-role) user must be rejected for Org B's entity_id."""
        with pytest.raises(HTTPException) as exc_info:
            await require_entity_access(
                entity_id=other_entity.id,
                current_user=test_user,
                db=db_session,
            )
        assert exc_info.value.status_code == 404

    async def test_allows_own_organizations_entity(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_entity: BusinessEntity,
    ):
        result = await require_entity_access(
            entity_id=test_entity.id,
            current_user=test_user,
            db=db_session,
        )
        assert result.id == test_entity.id

    async def test_rejects_nonexistent_entity(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        import uuid as uuid_module

        with pytest.raises(HTTPException) as exc_info:
            await require_entity_access(
                entity_id=uuid_module.uuid4(),
                current_user=test_user,
                db=db_session,
            )
        assert exc_info.value.status_code == 404


class TestEntityAccessDependencyWiring:
    """AST-based structural check: every entity-scoped endpoint in a migrated file must use
    Depends(require_entity_access), not just a raw entity_id path parameter."""

    def _find_unmigrated_functions(self, filename: str) -> list[str]:
        """A function is unmigrated if it takes an `entity_id` parameter at all (whether given an
        explicit `Path(...)` default, as in accounting.py, or left as a bare path parameter resolved
        implicitly from the route template, as in audit.py) and none of its parameter defaults wire in
        `Depends(require_entity_access)`."""
        source = (ROUTERS_DIR / filename).read_text()
        tree = ast.parse(source, filename=filename)
        unmigrated = []

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            all_args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            has_entity_id_param = any(arg.arg == "entity_id" for arg in all_args)

            all_defaults = [*node.args.defaults, *node.args.kw_defaults]
            has_require_entity_access = any(
                default is not None and "require_entity_access" in ast.dump(default)
                for default in all_defaults
            )

            if has_entity_id_param and not has_require_entity_access:
                unmigrated.append(node.name)

        return unmigrated

    def test_all_migrated_files_have_no_unmigrated_endpoints(self):
        failures = {}
        for filename in MIGRATED_ROUTER_FILES:
            unmigrated = self._find_unmigrated_functions(filename)
            if unmigrated:
                failures[filename] = unmigrated

        assert not failures, (
            f"Found entity-scoped endpoints with a raw entity_id path param but no "
            f"Depends(require_entity_access): {failures}"
        )


class TestAccountingRouterEndToEnd:
    """
    Real HTTP-level proof for accounting.py, the first Phase 2 Section 2.1 file migrated: proves
    the shared `entity_id` path parameter is correctly threaded into `require_entity_access` by
    FastAPI's own dependency resolution, not just present in the function signature (which the
    AST check above already confirms).
    """

    async def test_read_endpoint_rejects_foreign_entity(
        self,
        client: AsyncClient,
        auth_headers: dict,
        other_entity: BusinessEntity,
    ):
        response = await client.get(
            f"/api/v1/entities/{other_entity.id}/accounting/chart-of-accounts",
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_read_endpoint_allows_own_entity(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_entity: BusinessEntity,
    ):
        response = await client.get(
            f"/api/v1/entities/{test_entity.id}/accounting/chart-of-accounts",
            headers=auth_headers,
        )
        assert response.status_code == 200

    async def test_write_endpoint_rejects_foreign_entity_before_any_write(
        self,
        client: AsyncClient,
        auth_headers: dict,
        other_entity: BusinessEntity,
    ):
        """The access check must reject before create_account() ever runs -- not after."""
        response = await client.post(
            f"/api/v1/entities/{other_entity.id}/accounting/chart-of-accounts",
            headers=auth_headers,
            json={
                "account_code": "9999",
                "account_name": "Should Never Be Created",
                "account_type": "asset",
                "normal_balance": "debit",
            },
        )
        assert response.status_code == 404

    async def test_write_endpoint_allows_own_entity(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_entity: BusinessEntity,
    ):
        response = await client.post(
            f"/api/v1/entities/{test_entity.id}/accounting/chart-of-accounts",
            headers=auth_headers,
            json={
                "account_code": "1999",
                "account_name": "Test Account",
                "account_type": "asset",
                "normal_balance": "debit",
            },
        )
        assert response.status_code == 201


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
