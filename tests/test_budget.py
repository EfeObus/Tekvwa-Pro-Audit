"""
Tekvwa Pro Audit - Budget Unit Tests

Comprehensive tests for budget functionality:
- Budget creation and periods
- Variance analysis (actual vs budget)
- Budget forecasting
- Approval workflow
- Version/revision tracking
"""

import pytest
from decimal import Decimal
from datetime import date, datetime
from uuid import uuid4, UUID
from typing import Dict, List, Any

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# TESTS FOR BUDGET CREATION AND STRUCTURE
# =============================================================================

class TestBudgetCreation:
    """Tests for budget creation and structure."""
    
    def test_annual_budget_total(self):
        """Test annual budget calculates correctly from monthly amounts."""
        monthly_amounts = {
            "jan": Decimal("100000.00"),
            "feb": Decimal("110000.00"),
            "mar": Decimal("120000.00"),
            "apr": Decimal("115000.00"),
            "may": Decimal("125000.00"),
            "jun": Decimal("130000.00"),
            "jul": Decimal("135000.00"),
            "aug": Decimal("140000.00"),
            "sep": Decimal("145000.00"),
            "oct": Decimal("150000.00"),
            "nov": Decimal("155000.00"),
            "dec": Decimal("160000.00"),
        }
        
        annual_total = sum(monthly_amounts.values())
        
        assert annual_total == Decimal("1585000.00")
    
    def test_quarterly_budget_aggregation(self):
        """Test quarterly totals from monthly amounts."""
        monthly = [
            Decimal("100000"), Decimal("110000"), Decimal("120000"),  # Q1
            Decimal("115000"), Decimal("125000"), Decimal("130000"),  # Q2
            Decimal("135000"), Decimal("140000"), Decimal("145000"),  # Q3
            Decimal("150000"), Decimal("155000"), Decimal("160000"),  # Q4
        ]
        
        q1 = sum(monthly[0:3])
        q2 = sum(monthly[3:6])
        q3 = sum(monthly[6:9])
        q4 = sum(monthly[9:12])
        
        assert q1 == Decimal("330000")
        assert q2 == Decimal("370000")
        assert q3 == Decimal("420000")
        assert q4 == Decimal("465000")
    
    def test_budget_line_item_allocation(self):
        """Test budget allocation across line items."""
        line_items = [
            {"account": "4000", "description": "Sales Revenue", "amount": Decimal("5000000.00")},
            {"account": "5000", "description": "Cost of Sales", "amount": Decimal("3000000.00")},
            {"account": "6100", "description": "Salaries", "amount": Decimal("1200000.00")},
            {"account": "6200", "description": "Rent", "amount": Decimal("360000.00")},
            {"account": "6300", "description": "Utilities", "amount": Decimal("120000.00")},
        ]
        
        total_revenue = sum(li["amount"] for li in line_items if li["account"].startswith("4"))
        total_costs = sum(li["amount"] for li in line_items if li["account"].startswith("5"))
        total_expenses = sum(li["amount"] for li in line_items if li["account"].startswith("6"))
        
        gross_profit = total_revenue - total_costs
        net_income = gross_profit - total_expenses
        
        assert total_revenue == Decimal("5000000.00")
        assert total_costs == Decimal("3000000.00")
        assert gross_profit == Decimal("2000000.00")
        assert net_income == Decimal("320000.00")


class TestVarianceAnalysis:
    """Tests for budget vs actual variance analysis."""
    
    def test_favorable_revenue_variance(self):
        """Test favorable variance when actual revenue exceeds budget."""
        budget_revenue = Decimal("500000.00")
        actual_revenue = Decimal("550000.00")
        
        variance = actual_revenue - budget_revenue
        variance_pct = (variance / budget_revenue) * 100
        
        assert variance == Decimal("50000.00")
        assert variance > 0  # Favorable for revenue
        assert round(variance_pct, 2) == Decimal("10.00")
    
    def test_unfavorable_revenue_variance(self):
        """Test unfavorable variance when actual revenue below budget."""
        budget_revenue = Decimal("500000.00")
        actual_revenue = Decimal("450000.00")
        
        variance = actual_revenue - budget_revenue
        variance_pct = (variance / budget_revenue) * 100
        
        assert variance == Decimal("-50000.00")
        assert variance < 0  # Unfavorable for revenue
        assert round(variance_pct, 2) == Decimal("-10.00")
    
    def test_favorable_expense_variance(self):
        """Test favorable variance when actual expenses below budget."""
        budget_expense = Decimal("300000.00")
        actual_expense = Decimal("270000.00")
        
        # For expenses, under budget is favorable
        variance = budget_expense - actual_expense  # Reverse for expenses
        variance_pct = (variance / budget_expense) * 100
        
        assert variance == Decimal("30000.00")
        assert variance > 0  # Favorable (saved money)
        assert round(variance_pct, 2) == Decimal("10.00")
    
    def test_unfavorable_expense_variance(self):
        """Test unfavorable variance when actual expenses exceed budget."""
        budget_expense = Decimal("300000.00")
        actual_expense = Decimal("330000.00")
        
        variance = budget_expense - actual_expense
        variance_pct = (variance / budget_expense) * 100
        
        assert variance == Decimal("-30000.00")
        assert variance < 0  # Unfavorable (overspent)
        assert round(variance_pct, 2) == Decimal("-10.00")
    
    def test_ytd_variance_calculation(self):
        """Test year-to-date variance calculation."""
        # Monthly data through June
        monthly_budgets = [Decimal("100000")] * 6  # 100K/month
        monthly_actuals = [
            Decimal("95000"), Decimal("105000"), Decimal("98000"),
            Decimal("102000"), Decimal("110000"), Decimal("108000"),
        ]
        
        ytd_budget = sum(monthly_budgets)
        ytd_actual = sum(monthly_actuals)
        ytd_variance = ytd_actual - ytd_budget
        
        assert ytd_budget == Decimal("600000")
        assert ytd_actual == Decimal("618000")
        assert ytd_variance == Decimal("18000")  # Over budget by 18K
    
    def test_variance_percentage_with_zero_budget(self):
        """Test variance percentage when budget is zero."""
        budget = Decimal("0.00")
        actual = Decimal("10000.00")
        
        # Can't divide by zero, should handle gracefully
        if budget == 0:
            variance_pct = Decimal("100.00") if actual > 0 else Decimal("0.00")
        else:
            variance_pct = (actual - budget) / budget * 100
        
        assert variance_pct == Decimal("100.00")


class TestBudgetForecasting:
    """Tests for budget forecasting functionality."""
    
    def test_linear_forecast_from_ytd(self):
        """Test linear projection based on YTD run rate."""
        # 6 months of actual data
        ytd_actual = Decimal("3000000.00")  # 3M in 6 months
        months_completed = 6
        months_remaining = 6
        total_months = 12
        
        monthly_run_rate = ytd_actual / months_completed
        forecast_remaining = monthly_run_rate * months_remaining
        annual_forecast = ytd_actual + forecast_remaining
        
        assert monthly_run_rate == Decimal("500000.00")
        assert forecast_remaining == Decimal("3000000.00")
        assert annual_forecast == Decimal("6000000.00")
    
    def test_forecast_with_seasonality(self):
        """Test forecast with seasonal adjustment factors."""
        base_monthly = Decimal("100000.00")
        seasonal_factors = {
            "jan": Decimal("0.80"), "feb": Decimal("0.85"), "mar": Decimal("0.90"),
            "apr": Decimal("0.95"), "may": Decimal("1.00"), "jun": Decimal("1.05"),
            "jul": Decimal("1.10"), "aug": Decimal("1.15"), "sep": Decimal("1.10"),
            "oct": Decimal("1.05"), "nov": Decimal("0.95"), "dec": Decimal("1.10"),
        }
        
        adjusted_forecast = {
            month: base_monthly * factor
            for month, factor in seasonal_factors.items()
        }
        
        annual_total = sum(adjusted_forecast.values())
        
        assert adjusted_forecast["jan"] == Decimal("80000.00")
        assert adjusted_forecast["aug"] == Decimal("115000.00")
        assert annual_total == Decimal("1200000.00")
    
    def test_forecast_variance_from_budget(self):
        """Test forecast to budget variance."""
        annual_budget = Decimal("6000000.00")
        forecast_annual = Decimal("6300000.00")
        
        forecast_variance = forecast_annual - annual_budget
        forecast_variance_pct = (forecast_variance / annual_budget) * 100
        
        assert forecast_variance == Decimal("300000.00")
        assert round(forecast_variance_pct, 2) == Decimal("5.00")
    
    def test_rolling_forecast_update(self):
        """Test rolling forecast update with new actuals."""
        # Original forecast: 500K/month
        original_monthly_forecast = Decimal("500000.00")
        
        # Actual for January came in at 520K
        actual_jan = Decimal("520000.00")
        variance_jan = actual_jan - original_monthly_forecast
        
        # Adjust remaining months proportionally
        adjustment_factor = actual_jan / original_monthly_forecast
        
        updated_monthly_forecast = original_monthly_forecast * adjustment_factor
        
        assert adjustment_factor == Decimal("1.04")
        assert updated_monthly_forecast == Decimal("520000.00")


class TestBudgetApproval:
    """Tests for budget approval workflow."""
    
    def test_approval_status_progression(self):
        """Test budget status progression through approval."""
        statuses = ["draft", "submitted", "under_review", "approved"]
        
        current_status = "draft"
        
        # Submit for approval
        if current_status == "draft":
            current_status = "submitted"
        
        assert current_status == "submitted"
        
        # Under review
        current_status = "under_review"
        assert current_status == "under_review"
        
        # Final approval
        current_status = "approved"
        assert current_status == "approved"
    
    def test_multi_approver_workflow(self):
        """Test M-of-N approval workflow."""
        required_approvals = 3
        approvers = ["manager1", "manager2", "director", "cfo"]
        current_approvals = ["manager1", "director"]
        
        approval_count = len(current_approvals)
        is_fully_approved = approval_count >= required_approvals
        
        assert approval_count == 2
        assert is_fully_approved is False
        
        # Add one more approval
        current_approvals.append("cfo")
        approval_count = len(current_approvals)
        is_fully_approved = approval_count >= required_approvals
        
        assert approval_count == 3
        assert is_fully_approved is True
    
    def test_rejection_handling(self):
        """Test budget rejection and return to draft."""
        status = "submitted"
        rejection_reason = "Revenue projections too optimistic"
        
        # Reject budget
        status = "rejected"
        
        # Must return to draft for revision
        if status == "rejected":
            status = "draft"
        
        assert status == "draft"
    
    def test_approval_with_conditions(self):
        """Test conditional approval."""
        conditions = [
            "Reduce travel budget by 10%",
            "Add contingency line item",
        ]
        
        is_conditional = len(conditions) > 0
        status = "conditionally_approved"
        
        assert is_conditional is True
        assert status == "conditionally_approved"


class TestBudgetVersioning:
    """Tests for budget version and revision tracking."""
    
    def test_version_increment(self):
        """Test version number incrementing on revision."""
        versions = [
            {"version": 1, "status": "approved", "is_current": False},
            {"version": 2, "status": "approved", "is_current": False},
            {"version": 3, "status": "approved", "is_current": True},
        ]
        
        current_version = next(v for v in versions if v["is_current"])
        
        assert current_version["version"] == 3
    
    def test_revision_creates_new_version(self):
        """Test that creating revision creates new version."""
        original_budget_id = uuid4()
        original_version = 1
        
        # Create revision
        revision_id = uuid4()
        revision_version = original_version + 1
        parent_id = original_budget_id
        
        assert revision_version == 2
        assert parent_id == original_budget_id
        assert revision_id != original_budget_id
    
    def test_version_history_chain(self):
        """Test version history maintains chain."""
        # Version 1 (original)
        v1 = {"id": uuid4(), "version": 1, "parent_id": None}
        
        # Version 2 (revision of v1)
        v2 = {"id": uuid4(), "version": 2, "parent_id": v1["id"]}
        
        # Version 3 (revision of v2)
        v3 = {"id": uuid4(), "version": 3, "parent_id": v2["id"]}
        
        # Can trace back to original
        def trace_history(version):
            history = [version]
            current = version
            while current["parent_id"]:
                parent = next((v for v in [v1, v2, v3] if v["id"] == current["parent_id"]), None)
                if parent:
                    history.append(parent)
                    current = parent
                else:
                    break
            return history
        
        history = trace_history(v3)
        
        assert len(history) == 3
        assert history[0]["version"] == 3
        assert history[-1]["version"] == 1


class TestBudgetPeriods:
    """Tests for budget period calculations."""
    
    def test_monthly_period_dates(self):
        """Test monthly period date calculations."""
        fiscal_year = 2026
        
        periods = []
        for month in range(1, 13):
            if month == 12:
                end_date = date(fiscal_year, 12, 31)
            else:
                end_date = date(fiscal_year, month + 1, 1) - timedelta(days=1)
            
            periods.append({
                "month": month,
                "start_date": date(fiscal_year, month, 1),
                "end_date": end_date,
            })
        
        # January
        assert periods[0]["start_date"] == date(2026, 1, 1)
        assert periods[0]["end_date"] == date(2026, 1, 31)
        
        # February (non-leap year)
        assert periods[1]["start_date"] == date(2026, 2, 1)
        assert periods[1]["end_date"] == date(2026, 2, 28)
        
        # December
        assert periods[11]["start_date"] == date(2026, 12, 1)
        assert periods[11]["end_date"] == date(2026, 12, 31)
    
    def test_quarterly_period_dates(self):
        """Test quarterly period date calculations."""
        fiscal_year = 2026
        
        quarters = [
            {"q": 1, "start": date(2026, 1, 1), "end": date(2026, 3, 31)},
            {"q": 2, "start": date(2026, 4, 1), "end": date(2026, 6, 30)},
            {"q": 3, "start": date(2026, 7, 1), "end": date(2026, 9, 30)},
            {"q": 4, "start": date(2026, 10, 1), "end": date(2026, 12, 31)},
        ]
        
        assert quarters[0]["end"] == date(2026, 3, 31)
        assert quarters[1]["start"] == date(2026, 4, 1)
        assert quarters[3]["end"] == date(2026, 12, 31)
    
    def test_period_status_determination(self):
        """Test period status based on current date."""
        current_date = date(2026, 6, 15)
        
        periods = [
            {"month": 1, "end": date(2026, 1, 31)},  # Closed
            {"month": 5, "end": date(2026, 5, 31)},  # Closed
            {"month": 6, "end": date(2026, 6, 30)},  # Current
            {"month": 7, "end": date(2026, 7, 31)},  # Future
        ]
        
        statuses = []
        for p in periods:
            if p["end"] < current_date:
                status = "closed"
            elif p["end"].month == current_date.month and p["end"].year == current_date.year:
                status = "current"
            else:
                status = "future"
            statuses.append(status)
        
        assert statuses == ["closed", "closed", "current", "future"]


class TestBudgetAllocation:
    """Tests for budget allocation methods."""
    
    def test_even_monthly_allocation(self):
        """Test even distribution across months."""
        annual_amount = Decimal("1200000.00")
        months = 12
        
        monthly_allocation = annual_amount / months
        allocations = [monthly_allocation] * months
        
        assert monthly_allocation == Decimal("100000.00")
        assert sum(allocations) == annual_amount
    
    def test_front_loaded_allocation(self):
        """Test front-loaded budget allocation."""
        annual_amount = Decimal("1200000.00")
        
        # 60% in first half, 40% in second half
        first_half = annual_amount * Decimal("0.60")
        second_half = annual_amount * Decimal("0.40")
        
        monthly_h1 = first_half / 6
        monthly_h2 = second_half / 6
        
        assert first_half == Decimal("720000.00")
        assert second_half == Decimal("480000.00")
        assert monthly_h1 == Decimal("120000.00")
        assert monthly_h2 == Decimal("80000.00")
    
    def test_percentage_allocation_to_departments(self):
        """Test budget allocation by department percentage."""
        total_budget = Decimal("10000000.00")
        
        allocations = {
            "Sales": Decimal("0.30"),
            "Marketing": Decimal("0.15"),
            "Operations": Decimal("0.25"),
            "Admin": Decimal("0.10"),
            "IT": Decimal("0.12"),
            "HR": Decimal("0.08"),
        }
        
        department_budgets = {
            dept: total_budget * pct
            for dept, pct in allocations.items()
        }
        
        assert department_budgets["Sales"] == Decimal("3000000.00")
        assert department_budgets["Marketing"] == Decimal("1500000.00")
        assert sum(department_budgets.values()) == total_budget


class TestBudgetThresholds:
    """Tests for budget threshold and alerts."""
    
    def test_variance_threshold_alert(self):
        """Test variance threshold triggering alert."""
        budget = Decimal("100000.00")
        actual = Decimal("115000.00")
        threshold_pct = Decimal("10.00")
        
        variance = actual - budget
        variance_pct = (variance / budget) * 100
        
        alert_triggered = abs(variance_pct) > threshold_pct
        
        assert variance_pct == Decimal("15.00")
        assert alert_triggered is True
    
    def test_budget_utilization_percentage(self):
        """Test budget utilization calculation."""
        budget = Decimal("500000.00")
        spent = Decimal("375000.00")
        
        utilization_pct = (spent / budget) * 100
        remaining = budget - spent
        remaining_pct = (remaining / budget) * 100
        
        assert utilization_pct == Decimal("75.00")
        assert remaining == Decimal("125000.00")
        assert remaining_pct == Decimal("25.00")
    
    def test_over_budget_flag(self):
        """Test over budget detection."""
        line_items = [
            {"name": "Salaries", "budget": Decimal("500000"), "actual": Decimal("510000")},
            {"name": "Travel", "budget": Decimal("50000"), "actual": Decimal("45000")},
            {"name": "Software", "budget": Decimal("30000"), "actual": Decimal("35000")},
        ]
        
        over_budget_items = [
            li for li in line_items
            if li["actual"] > li["budget"]
        ]
        
        assert len(over_budget_items) == 2
        assert over_budget_items[0]["name"] == "Salaries"
        assert over_budget_items[1]["name"] == "Software"


# Need to import timedelta
from datetime import timedelta


# =============================================================================
# BUDGET PERSISTENCE (Finding 50, docs/FINDING_50_SCOPE.md)
#
# Every test above in this file is pure arithmetic with no database involved, so none of them
# would have caught this: budget_service.py and app/routers/budget.py consistently construct/read
# Budget using description/total_revenue_budget/total_expense_budget/total_capex_budget, none of
# which existed on the live table (which had notes/total_revenue/total_expense instead, and no
# capex concept at all) until this session's migration. create_budget() and every variance
# calculation would have crashed or silently operated on the wrong (nonexistent) attributes.
# =============================================================================

from sqlalchemy.ext.asyncio import AsyncSession
from app.services.budget_service import BudgetService


class TestBudgetPersistence:
    """Regression coverage for Finding 50's Budget column drift."""

    async def test_create_budget_and_update_totals(
        self, db_session: AsyncSession, test_entity, test_user,
    ):
        service = BudgetService(db_session)
        budget = await service.create_budget(
            entity_id=test_entity.id,
            name="FY2026 Operating Budget",
            fiscal_year=2026,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            created_by_id=test_user.id,
            description="Annual operating budget",
        )

        assert budget.id is not None
        assert budget.description == "Annual operating budget"
        assert budget.total_revenue_budget == Decimal("0.00")
        assert budget.total_expense_budget == Decimal("0.00")
        assert budget.total_capex_budget == Decimal("0.00")

        budget.total_revenue_budget = Decimal("5000000.00")
        budget.total_expense_budget = Decimal("3000000.00")
        budget.total_capex_budget = Decimal("500000.00")
        await db_session.commit()
        await db_session.refresh(budget)

        assert budget.total_revenue_budget == Decimal("5000000.00")
        assert budget.total_capex_budget == Decimal("500000.00")


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
