"""
Regression coverage for Finding 18 (docs/IMPLEMENTATION_ROADMAP.md Phase 2, Section 2.1) as it applies
to app/routers/report_template.py -- 6 endpoints (list_templates, create_template,
set_default_template, get_default_template, clone_template, get_generation_history), all of which take
entity_id as a query parameter rather than a path parameter (this router's prefix is
/api/v1/entities/report-templates, with no {entity_id} in the URL template at all).

clone_template gets extra coverage: its request body's optional target_entity_id was a second,
previously-unvalidated entity_id -- a caller could clone a template directly into another
organization's entity (a cross-tenant WRITE, not just a read), and it wasn't part of the roadmap's
6-endpoint count for this file since it's nested in the request body, not a query/path parameter.
"""
import pytest
from httpx import AsyncClient

# NOTE on list_templates (GET /api/v1/entities/report-templates): there's no HTTP-level test for it
# here. A pre-existing, unrelated routing bug (not Finding 18, not introduced by this migration) makes
# that URL unreachable: entities.py's `GET /{entity_id}` is registered before report_template.py's
# router in main.py, so Starlette's first-match-wins routing sends this exact URL to entities.py's
# get_entity instead, which then 422s trying to parse "report-templates" as a UUID. Documented in
# docs/REMEDIATION_LOG.md as a separate, out-of-scope finding rather than fixed here (reordering
# router registration risks colliding with other entities.py sub-paths and needs its own dedicated
# investigation). Its require_entity_access wiring is still verified -- by the AST structural sweep
# in tests/test_entity_access_isolation.py (report_template.py is in MIGRATED_ROUTER_FILES), which
# inspects the function signature directly rather than going over HTTP.


class TestCreateTemplate:
    async def test_rejects_foreign_entity_before_any_write(
        self, client: AsyncClient, auth_headers: dict, other_entity
    ):
        response = await client.post(
            f"/api/v1/entities/report-templates?entity_id={other_entity.id}",
            headers=auth_headers,
            json={"name": "Should Never Be Created", "report_type": "custom"},
        )
        assert response.status_code == 404, response.text

    async def test_allows_own_entity(self, client: AsyncClient, auth_headers: dict, test_entity):
        response = await client.post(
            f"/api/v1/entities/report-templates?entity_id={test_entity.id}",
            headers=auth_headers,
            json={"name": "Test Template", "report_type": "custom"},
        )
        assert response.status_code == 201, response.text


class TestCloneTemplate:
    async def test_rejects_foreign_source_entity(
        self, client: AsyncClient, auth_headers: dict, other_entity
    ):
        response = await client.post(
            f"/api/v1/entities/report-templates/{other_entity.id}/clone?entity_id={other_entity.id}",
            headers=auth_headers,
            json={"new_name": "Cloned"},
        )
        assert response.status_code == 404, response.text

    async def test_rejects_foreign_target_entity_id_in_body(
        self, client: AsyncClient, auth_headers: dict, test_entity, other_entity, db_session
    ):
        """
        The real bug found while migrating this file: cloning FROM the caller's own (valid) entity
        but TO another organization's entity_id, supplied in the request body, must still be
        rejected -- before this fix, target_entity_id was never validated at all.
        """
        from app.services.report_template_service import ReportTemplateService

        service = ReportTemplateService(db_session)
        template = await service.create_template(
            entity_id=test_entity.id,
            name="Source Template",
            report_type="custom",
        )
        await db_session.commit()

        response = await client.post(
            f"/api/v1/entities/report-templates/{template.id}/clone?entity_id={test_entity.id}",
            headers=auth_headers,
            json={"new_name": "Should Never Be Cloned Cross-Org", "target_entity_id": str(other_entity.id)},
        )
        assert response.status_code == 404, response.text
