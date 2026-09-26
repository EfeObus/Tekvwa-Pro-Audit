"""
Regression coverage for Finding 18 (docs/IMPLEMENTATION_ROADMAP.md Phase 2, Section 2.1) as it
applies to app/routers/entities.py::restore_entity -- the final endpoint in Phase 2.1's 17-file,
164-endpoint list.

Two bugs fixed together here:
1. The roadmap's actual ask -- "add an organization-match check, not just a role check": the
   endpoint looked up the entity via a raw, org-unscoped `select(Entity)...` query, so any
   organization's OWNER could restore any OTHER organization's soft-deleted entity by guessing its
   entity_id.
2. A crash found while fixing #1: that same query imported `from app.models.entity import Entity`,
   but no such class exists in that module (only BusinessEntity) -- this endpoint raised ImportError
   on every single call, regardless of entity ownership.

Both fixed with Depends(require_entity_access), same as every other migrated endpoint --
EntityService.get_entity_by_id doesn't filter by is_active, so a soft-deleted entity in the caller's
own organization still resolves correctly.
"""
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import UserRole


class TestRestoreEntity:
    async def test_rejects_foreign_entity_before_touching_role_check(
        self, client: AsyncClient, auth_headers: dict, other_entity
    ):
        """Rejection must happen at the organization boundary, before the OWNER-role check even runs."""
        response = await client.post(
            f"/api/v1/entities/{other_entity.id}/restore",
            headers=auth_headers,
        )
        assert response.status_code == 404, response.text

    async def test_restores_own_soft_deleted_entity(
        self, client: AsyncClient, auth_headers: dict, test_entity, db_session: AsyncSession, test_user
    ):
        test_user.role = UserRole.OWNER
        test_entity.is_active = False
        await db_session.commit()

        response = await client.post(
            f"/api/v1/entities/{test_entity.id}/restore",
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text

    async def test_rejects_nonexistent_entity(self, client: AsyncClient, auth_headers: dict):
        response = await client.post(
            f"/api/v1/entities/{uuid4()}/restore",
            headers=auth_headers,
        )
        assert response.status_code == 404, response.text
