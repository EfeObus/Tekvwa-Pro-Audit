"""
Regression coverage for Finding 18 (docs/IMPLEMENTATION_ROADMAP.md Phase 2, Section 2.1) as it applies
to app/routers/ml_ai.py.

The AST structural sweep in tests/test_entity_access_isolation.py can't verify 3 of this file's 4
in-scope endpoints: forecast_cash_flow, predict_growth, and detect_anomalies all take their entity_id
nested inside a POST request body (CashFlowForecastRequest.entity_id, etc.), not as a direct function
parameter the sweep's AST walk can see -- only get_ml_dashboard's bare `entity_id: UUID` path param is
sweep-visible. These tests call the four route handler functions directly (bypassing the router's
Intelligence-add-on feature gate, which would otherwise 403 an HTTP-level test before the access check
ever runs, same issue as budget.py/fixed_assets.py/fx.py), proving each one's require_entity_access
call actually rejects a foreign organization's entity_id.

Also covers a fourth vulnerability discovered while fixing the two the roadmap named
(forecast_cash_flow, predict_growth, "remove their misleading # Verify entity access comments"):
detect_anomalies had no access check at all, not even the misleading db.get() existence check --
not counted in the roadmap's "3 total" for this file, fixed here as a same-root-cause extension.

get_ml_dashboard is different again: its access control is Depends(require_entity_access) on a bare
entity_id path param, so rejection happens inside FastAPI's own dependency resolution, before this
function's body ever runs -- already proven correct by TestRequireEntityAccess (the dependency itself)
and the AST sweep (confirms it's wired into this function's signature). The test here instead guards a
real regression this file's edit introduced and this test suite caught: removing the old inline
`entity = await db.get(...)` check without keeping something named `entity` broke the dashboard's own
later use of `entity.name` with a NameError on every single call, foreign entity or not.
"""
import pytest
from fastapi import HTTPException

from app.routers.ml_ai import (
    forecast_cash_flow,
    predict_growth,
    detect_anomalies,
    get_ml_dashboard,
    CashFlowForecastRequest,
    GrowthPredictionRequest,
    AnomalyDetectionRequest,
)


class TestMlAiEntityAccess:
    async def test_forecast_cash_flow_rejects_foreign_entity(self, db_session, other_entity, test_user):
        with pytest.raises(HTTPException) as exc_info:
            await forecast_cash_flow(
                request=CashFlowForecastRequest(entity_id=other_entity.id),
                db=db_session,
                current_user=test_user,
            )
        assert exc_info.value.status_code == 404

    async def test_forecast_cash_flow_allows_own_entity(self, db_session, test_entity, test_user):
        result = await forecast_cash_flow(
            request=CashFlowForecastRequest(entity_id=test_entity.id),
            db=db_session,
            current_user=test_user,
        )
        assert result is not None

    async def test_predict_growth_rejects_foreign_entity(self, db_session, other_entity, test_user):
        with pytest.raises(HTTPException) as exc_info:
            await predict_growth(
                request=GrowthPredictionRequest(entity_id=other_entity.id),
                db=db_session,
                current_user=test_user,
            )
        assert exc_info.value.status_code == 404

    async def test_predict_growth_allows_own_entity(self, db_session, test_entity, test_user):
        result = await predict_growth(
            request=GrowthPredictionRequest(entity_id=test_entity.id),
            db=db_session,
            current_user=test_user,
        )
        assert result is not None

    async def test_detect_anomalies_rejects_foreign_entity(self, db_session, other_entity, test_user):
        with pytest.raises(HTTPException) as exc_info:
            await detect_anomalies(
                request=AnomalyDetectionRequest(entity_id=other_entity.id),
                db=db_session,
                current_user=test_user,
            )
        assert exc_info.value.status_code == 404

    async def test_get_ml_dashboard_runs_with_resolved_entity(self, db_session, test_entity, test_user):
        """
        get_ml_dashboard's access control is via Depends(require_entity_access) (a bare entity_id path
        param, unlike the three body-based endpoints above), so rejection itself happens inside
        FastAPI's own dependency resolution before this function body ever runs -- already proven by
        TestRequireEntityAccess (the dependency itself) and the AST sweep (confirms it's wired in).
        This test instead guards a regression caught while writing this file: removing the old
        misleading `entity = await db.get(...)` check without replacing the `entity` variable broke
        the dashboard's own use of `entity.name` further down with a NameError on every call.
        """
        result = await get_ml_dashboard(
            entity_id=test_entity.id,
            db=db_session,
            current_user=test_user,
            entity=test_entity,
        )
        assert result is not None
