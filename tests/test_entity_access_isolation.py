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
import uuid as uuid_module
from pathlib import Path as FilePath

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import require_entity_access, require_group_access
from app.models.advanced_accounting import EntityGroup
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
    "budget.py",
    "consolidation.py",
    "fixed_assets.py",
    "forensic_audit.py",
    "fx.py",
    "report_template.py",
    # ml_ai.py is NOT added here: 3 of its 4 in-scope endpoints (forecast_cash_flow, predict_growth,
    # detect_anomalies) take entity_id nested inside a POST request body, not as a function parameter
    # this AST sweep can see -- adding it would silently skip verifying them (no entity_id param means
    # nothing gets flagged), not genuinely prove they're fixed. See tests/test_ml_ai_entity_access.py
    # for that file's real coverage, and docs/REMEDIATION_LOG.md's Phase 2 entry for the full writeup.
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
        with pytest.raises(HTTPException) as exc_info:
            await require_entity_access(
                entity_id=uuid_module.uuid4(),
                current_user=test_user,
                db=db_session,
            )
        assert exc_info.value.status_code == 404


class TestRequireGroupAccess:
    """
    Direct unit tests for `require_group_access` (app/dependencies.py), the group_id-keyed
    counterpart to `require_entity_access` discovered while migrating `consolidation.py`:
    `ConsolidationService.get_entity_group` looked up `EntityGroup` by `group_id` alone, with no
    `organization_id` check at all, across every one of that router's group-scoped endpoints -- a
    same-root-cause cross-tenant IDOR gap the original audit's per-file endpoint count for this file
    (3) did not capture, since it only counted the `entity_id`-based endpoints. See
    docs/REMEDIATION_LOG.md's Phase 2 entry for `consolidation.py` for the full discovery writeup.

    Router-level HTTP tests aren't practical here (consolidation.py's router requires the
    Enterprise-tier `Feature.CONSOLIDATION` gate, which the default test fixtures don't have, so any
    request 403s before reaching `require_group_access`) -- these call the dependency directly instead,
    same pattern as `TestRequireEntityAccess` above.
    """

    async def test_rejects_foreign_organizations_group(
        self,
        db_session: AsyncSession,
        other_organization: Organization,
        other_entity: BusinessEntity,
        test_user: User,
    ):
        foreign_group = EntityGroup(
            id=uuid_module.uuid4(),
            organization_id=other_organization.id,
            name="Other Org Group",
            parent_entity_id=other_entity.id,
        )
        db_session.add(foreign_group)
        await db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await require_group_access(
                group_id=foreign_group.id,
                current_user=test_user,
                db=db_session,
            )
        assert exc_info.value.status_code == 404

    async def test_allows_own_organizations_group(
        self,
        db_session: AsyncSession,
        test_organization: Organization,
        test_entity: BusinessEntity,
        test_user: User,
    ):
        own_group = EntityGroup(
            id=uuid_module.uuid4(),
            organization_id=test_organization.id,
            name="Own Org Group",
            parent_entity_id=test_entity.id,
        )
        db_session.add(own_group)
        await db_session.commit()

        result = await require_group_access(
            group_id=own_group.id,
            current_user=test_user,
            db=db_session,
        )
        assert result.id == own_group.id

    async def test_rejects_nonexistent_group(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await require_group_access(
                group_id=uuid_module.uuid4(),
                current_user=test_user,
                db=db_session,
            )
        assert exc_info.value.status_code == 404


class TestEntityAccessDependencyWiring:
    """AST-based structural check: every entity-scoped endpoint in a migrated file must use
    Depends(require_entity_access) (or the group_id-keyed Depends(require_group_access), for
    consolidation.py's group-scoped endpoints), not just a raw entity_id/group_id parameter."""

    # Dependencies that are an acceptable substitute for a direct Depends(require_entity_access) on
    # an `entity_id` parameter: get_current_entity_id derives entity_id from the user's own
    # cookie/accessible-entity list, so it can never resolve to a foreign organization's entity --
    # see consolidation.py's create_entity_group/list_entity_groups.
    SAFE_ENTITY_ID_DEPENDENCIES = ("require_entity_access", "get_current_entity_id")

    def _calls_require_entity_access_in_body(self, node) -> bool:
        """Fallback for params like consolidation.py's get_translation_history, where entity_id is an
        *optional* filter -- Depends(require_entity_access) can't be used (it would make the param
        mandatory), so the check is inlined in the function body instead."""
        for child in ast.walk(node):
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "require_entity_access"
            ):
                return True
        return False

    def _find_unmigrated_functions(self, filename: str) -> list[str]:
        """A function is unmigrated if it takes an `entity_id` and/or `group_id` parameter at all
        (whether given an explicit `Path(...)`/`Query(...)` default, or left as a bare path parameter
        resolved implicitly from the route template) and isn't provably guarded: via a
        Depends(require_entity_access) / Depends(require_group_access) / Depends(get_current_entity_id)
        default, or (entity_id only) an inline require_entity_access(...) call in the body."""
        source = (ROUTERS_DIR / filename).read_text()
        tree = ast.parse(source, filename=filename)
        unmigrated = []

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            # Only route handlers are in scope -- plain helper functions (e.g. consolidation.py's
            # get_organization_id_from_entity) may legitimately take an already-validated entity_id
            # with no Depends() of their own, since the caller did the access check.
            is_route_handler = any(
                isinstance(dec, ast.Call) and "router" in ast.dump(dec.func)
                for dec in node.decorator_list
            )
            if not is_route_handler:
                continue

            all_args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            has_entity_id_param = any(arg.arg == "entity_id" for arg in all_args)
            has_group_id_param = any(arg.arg == "group_id" for arg in all_args)

            all_defaults = [*node.args.defaults, *node.args.kw_defaults]
            default_srcs = [ast.dump(d) for d in all_defaults if d is not None]

            has_entity_access = any(
                any(dep in s for dep in self.SAFE_ENTITY_ID_DEPENDENCIES) for s in default_srcs
            ) or (has_entity_id_param and self._calls_require_entity_access_in_body(node))
            has_group_access = any("require_group_access" in s for s in default_srcs)

            if has_entity_id_param and not has_entity_access:
                unmigrated.append(node.name)
            elif has_group_id_param and not has_group_access:
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
