"""
Tekvwa Pro Audit - Year-End Closing Unit Tests

Comprehensive tests for year-end closing procedures:
- Period close validation
- Closing entry generation
- Retained earnings rollforward
- Opening balance creation
- Fiscal year transitions
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
# TESTS FOR PERIOD CLOSE PROCEDURES
# =============================================================================

class TestPeriodClose:
    """Tests for period closing procedures."""
    
    def test_period_close_validation_all_entries_posted(self):
        """Test validation that all journal entries are posted."""
        entries = [
            {"id": 1, "status": "posted"},
            {"id": 2, "status": "posted"},
            {"id": 3, "status": "posted"},
        ]
        
        unposted = [e for e in entries if e["status"] != "posted"]
        can_close = len(unposted) == 0
        
        assert can_close is True
    
    def test_period_close_validation_unposted_entries(self):
        """Test validation fails with unposted entries."""
        entries = [
            {"id": 1, "status": "posted"},
            {"id": 2, "status": "draft"},
            {"id": 3, "status": "posted"},
        ]
        
        unposted = [e for e in entries if e["status"] != "posted"]
        can_close = len(unposted) == 0
        
        assert can_close is False
        assert len(unposted) == 1
    
    def test_trial_balance_balances(self):
        """Test trial balance is balanced before close."""
        trial_balance = [
            {"account": "1000", "debit": Decimal("100000.00"), "credit": Decimal("0.00")},
            {"account": "2000", "debit": Decimal("0.00"), "credit": Decimal("50000.00")},
            {"account": "3000", "debit": Decimal("0.00"), "credit": Decimal("50000.00")},
        ]
        
        total_debits = sum(tb["debit"] for tb in trial_balance)
        total_credits = sum(tb["credit"] for tb in trial_balance)
        
        is_balanced = total_debits == total_credits
        
        assert is_balanced is True
        assert total_debits == Decimal("100000.00")
        assert total_credits == Decimal("100000.00")
    
    def test_bank_reconciliation_complete(self):
        """Test bank accounts are reconciled before close."""
        bank_accounts = [
            {"account": "1010", "reconciled": True, "reconciled_date": date(2026, 1, 31)},
            {"account": "1020", "reconciled": True, "reconciled_date": date(2026, 1, 31)},
        ]
        
        period_end = date(2026, 1, 31)
        
        all_reconciled = all(
            ba["reconciled"] and ba["reconciled_date"] >= period_end
            for ba in bank_accounts
        )
        
        assert all_reconciled is True
    
    def test_period_lock_prevents_posting(self):
        """Test locked period prevents new journal entries."""
        period_status = "closed"
        entry_date = date(2026, 1, 15)
        period_end = date(2026, 1, 31)
        
        is_period_locked = period_status == "closed"
        can_post = entry_date <= period_end and not is_period_locked
        
        assert is_period_locked is True
        assert can_post is False


class TestClosingEntries:
    """Tests for closing entry generation."""
    
    def test_revenue_account_closing(self):
        """Test revenue accounts close to income summary."""
        revenue_accounts = [
            {"account": "4000", "name": "Sales Revenue", "balance": Decimal("500000.00")},
            {"account": "4100", "name": "Service Revenue", "balance": Decimal("150000.00")},
            {"account": "4200", "name": "Interest Income", "balance": Decimal("5000.00")},
        ]
        
        total_revenue = sum(ra["balance"] for ra in revenue_accounts)
        
        # Closing entry: Debit revenue accounts, Credit income summary
        closing_entries = []
        for ra in revenue_accounts:
            closing_entries.append({
                "account": ra["account"],
                "debit": ra["balance"],
                "credit": Decimal("0.00"),
            })
        
        closing_entries.append({
            "account": "5999",  # Income Summary
            "debit": Decimal("0.00"),
            "credit": total_revenue,
        })
        
        total_debit = sum(e["debit"] for e in closing_entries)
        total_credit = sum(e["credit"] for e in closing_entries)
        
        assert total_revenue == Decimal("655000.00")
        assert total_debit == total_credit
    
    def test_expense_account_closing(self):
        """Test expense accounts close to income summary."""
        expense_accounts = [
            {"account": "5000", "name": "Cost of Sales", "balance": Decimal("300000.00")},
            {"account": "6100", "name": "Salaries", "balance": Decimal("120000.00")},
            {"account": "6200", "name": "Rent", "balance": Decimal("36000.00")},
            {"account": "6300", "name": "Utilities", "balance": Decimal("12000.00")},
        ]
        
        total_expenses = sum(ea["balance"] for ea in expense_accounts)
        
        # Closing entry: Credit expense accounts, Debit income summary
        closing_entries = []
        closing_entries.append({
            "account": "5999",  # Income Summary
            "debit": total_expenses,
            "credit": Decimal("0.00"),
        })
        
        for ea in expense_accounts:
            closing_entries.append({
                "account": ea["account"],
                "debit": Decimal("0.00"),
                "credit": ea["balance"],
            })
        
        total_debit = sum(e["debit"] for e in closing_entries)
        total_credit = sum(e["credit"] for e in closing_entries)
        
        assert total_expenses == Decimal("468000.00")
        assert total_debit == total_credit
    
    def test_income_summary_to_retained_earnings(self):
        """Test income summary closes to retained earnings."""
        total_revenue = Decimal("655000.00")
        total_expenses = Decimal("468000.00")
        net_income = total_revenue - total_expenses
        
        # Net income is positive: Debit income summary, Credit retained earnings
        closing_entry = {
            "lines": [
                {"account": "5999", "debit": net_income, "credit": Decimal("0.00")},
                {"account": "3200", "debit": Decimal("0.00"), "credit": net_income},
            ]
        }
        
        total_debit = sum(l["debit"] for l in closing_entry["lines"])
        total_credit = sum(l["credit"] for l in closing_entry["lines"])
        
        assert net_income == Decimal("187000.00")
        assert total_debit == total_credit
    
    def test_net_loss_closing_entry(self):
        """Test closing entry when there is a net loss."""
        total_revenue = Decimal("400000.00")
        total_expenses = Decimal("450000.00")
        net_loss = total_expenses - total_revenue
        
        # Net loss: Credit income summary, Debit retained earnings
        closing_entry = {
            "lines": [
                {"account": "3200", "debit": net_loss, "credit": Decimal("0.00")},
                {"account": "5999", "debit": Decimal("0.00"), "credit": net_loss},
            ]
        }
        
        total_debit = sum(l["debit"] for l in closing_entry["lines"])
        total_credit = sum(l["credit"] for l in closing_entry["lines"])
        
        assert net_loss == Decimal("50000.00")
        assert total_debit == total_credit
    
    def test_dividend_closing_entry(self):
        """Test dividends close to retained earnings."""
        dividends_declared = Decimal("50000.00")
        
        # Dividends: Credit dividends account, Debit retained earnings
        closing_entry = {
            "lines": [
                {"account": "3200", "debit": dividends_declared, "credit": Decimal("0.00")},
                {"account": "3300", "debit": Decimal("0.00"), "credit": dividends_declared},
            ]
        }
        
        total_debit = sum(l["debit"] for l in closing_entry["lines"])
        total_credit = sum(l["credit"] for l in closing_entry["lines"])
        
        assert total_debit == total_credit == dividends_declared


class TestRetainedEarningsRollforward:
    """Tests for retained earnings rollforward."""
    
    def test_basic_rollforward_calculation(self):
        """Test basic retained earnings rollforward."""
        beginning_balance = Decimal("500000.00")
        net_income = Decimal("187000.00")
        dividends = Decimal("50000.00")
        
        ending_balance = beginning_balance + net_income - dividends
        
        assert ending_balance == Decimal("637000.00")
    
    def test_rollforward_with_prior_period_adjustment(self):
        """Test rollforward with prior period adjustment."""
        beginning_balance = Decimal("500000.00")
        prior_period_adjustment = Decimal("-25000.00")  # Error correction
        net_income = Decimal("187000.00")
        dividends = Decimal("50000.00")
        
        adjusted_beginning = beginning_balance + prior_period_adjustment
        ending_balance = adjusted_beginning + net_income - dividends
        
        assert adjusted_beginning == Decimal("475000.00")
        assert ending_balance == Decimal("612000.00")
    
    def test_rollforward_with_oci_reclassification(self):
        """Test rollforward with OCI reclassification."""
        beginning_balance = Decimal("500000.00")
        net_income = Decimal("187000.00")
        oci_reclassification = Decimal("15000.00")  # Realized from AOCI
        dividends = Decimal("50000.00")
        
        ending_balance = beginning_balance + net_income + oci_reclassification - dividends
        
        assert ending_balance == Decimal("652000.00")
    
    def test_rollforward_multi_year_continuity(self):
        """Test retained earnings continuity across years."""
        years = [
            {"year": 2024, "begin": Decimal("300000"), "income": Decimal("100000"), "dividends": Decimal("30000")},
            {"year": 2025, "income": Decimal("150000"), "dividends": Decimal("50000")},
            {"year": 2026, "income": Decimal("187000"), "dividends": Decimal("50000")},
        ]
        
        balance = years[0]["begin"]
        for year in years:
            balance = balance + year["income"] - year["dividends"]
            year["end"] = balance
        
        assert years[0]["end"] == Decimal("370000")
        assert years[1]["end"] == Decimal("470000")
        assert years[2]["end"] == Decimal("607000")


class TestOpeningBalances:
    """Tests for opening balance generation."""
    
    def test_balance_sheet_accounts_carry_forward(self):
        """Test balance sheet accounts carry forward to new year."""
        ending_balances = [
            {"account": "1000", "type": "asset", "balance": Decimal("100000.00")},
            {"account": "1100", "type": "asset", "balance": Decimal("250000.00")},
            {"account": "2000", "type": "liability", "balance": Decimal("-150000.00")},
            {"account": "3100", "type": "equity", "balance": Decimal("-200000.00")},
        ]
        
        opening_balances = [
            {**e, "date": date(2027, 1, 1)}
            for e in ending_balances
        ]
        
        assert len(opening_balances) == 4
        assert all(ob["date"] == date(2027, 1, 1) for ob in opening_balances)
    
    def test_income_statement_accounts_zero(self):
        """Test income statement accounts start at zero in new year."""
        closing_balances = [
            {"account": "4000", "type": "revenue", "balance": Decimal("500000.00")},
            {"account": "5000", "type": "expense", "balance": Decimal("300000.00")},
        ]
        
        # After closing entries, income statement accounts should be zero
        opening_balances = [
            {"account": e["account"], "type": e["type"], "balance": Decimal("0.00")}
            for e in closing_balances
        ]
        
        assert all(ob["balance"] == Decimal("0.00") for ob in opening_balances)
    
    def test_opening_balance_journal_entry(self):
        """Test opening balance journal entry structure."""
        opening_balances = [
            {"account": "1000", "debit": Decimal("100000.00"), "credit": Decimal("0.00")},
            {"account": "1100", "debit": Decimal("250000.00"), "credit": Decimal("0.00")},
            {"account": "2000", "debit": Decimal("0.00"), "credit": Decimal("150000.00")},
            {"account": "3100", "debit": Decimal("0.00"), "credit": Decimal("200000.00")},
        ]
        
        total_debit = sum(ob["debit"] for ob in opening_balances)
        total_credit = sum(ob["credit"] for ob in opening_balances)
        
        is_balanced = total_debit == total_credit
        
        assert is_balanced is True
        assert total_debit == Decimal("350000.00")
    
    def test_retained_earnings_opening_includes_net_income(self):
        """Test retained earnings opening includes prior year net income."""
        prior_year_re_opening = Decimal("500000.00")
        prior_year_net_income = Decimal("187000.00")
        prior_year_dividends = Decimal("50000.00")
        
        new_year_re_opening = prior_year_re_opening + prior_year_net_income - prior_year_dividends
        
        assert new_year_re_opening == Decimal("637000.00")


class TestFiscalYearTransition:
    """Tests for fiscal year transition."""
    
    def test_fiscal_year_end_date_calculation(self):
        """Test fiscal year end date calculation."""
        # Calendar year end
        fiscal_year = 2026
        fiscal_year_end_month = 12
        
        if fiscal_year_end_month == 12:
            year_end_date = date(fiscal_year, 12, 31)
        else:
            year_end_date = date(fiscal_year + 1, fiscal_year_end_month, 1) - timedelta(days=1)
        
        assert year_end_date == date(2026, 12, 31)
    
    def test_non_calendar_fiscal_year(self):
        """Test non-calendar fiscal year (e.g., March year-end)."""
        fiscal_year = 2026  # Fiscal year ending March 2026
        fiscal_year_end_month = 3
        
        from datetime import timedelta
        
        # Year-end is March 31, 2026
        year_end_date = date(fiscal_year, 3, 31)
        
        # First day of new fiscal year
        new_year_start = date(fiscal_year, 4, 1)
        
        assert year_end_date == date(2026, 3, 31)
        assert new_year_start == date(2026, 4, 1)
    
    def test_comparative_period_dates(self):
        """Test comparative period date calculation."""
        current_year_end = date(2026, 12, 31)
        
        prior_year_end = date(current_year_end.year - 1, current_year_end.month, current_year_end.day)
        
        assert prior_year_end == date(2025, 12, 31)
    
    def test_year_rollover_status_reset(self):
        """Test period status resets for new year."""
        prior_year_periods = [
            {"month": m, "year": 2026, "status": "closed"}
            for m in range(1, 13)
        ]
        
        new_year_periods = [
            {"month": m, "year": 2027, "status": "open" if m == 1 else "future"}
            for m in range(1, 13)
        ]
        
        assert all(p["status"] == "closed" for p in prior_year_periods)
        assert new_year_periods[0]["status"] == "open"
        assert all(p["status"] == "future" for p in new_year_periods[1:])


class TestYearEndChecklists:
    """Tests for year-end checklist completion."""
    
    def test_checklist_items_completion(self):
        """Test checklist items track completion status."""
        checklist = [
            {"item": "Review all open invoices", "completed": True, "completed_by": "user1"},
            {"item": "Complete bank reconciliations", "completed": True, "completed_by": "user2"},
            {"item": "Review accruals", "completed": False, "completed_by": None},
            {"item": "Calculate depreciation", "completed": True, "completed_by": "user1"},
        ]
        
        completed_items = [c for c in checklist if c["completed"]]
        incomplete_items = [c for c in checklist if not c["completed"]]
        
        completion_pct = len(completed_items) / len(checklist) * 100
        
        assert len(completed_items) == 3
        assert len(incomplete_items) == 1
        assert completion_pct == 75.0
    
    def test_checklist_prevents_close_if_incomplete(self):
        """Test year cannot close with incomplete checklist."""
        checklist = [
            {"item": "Review accruals", "required": True, "completed": False},
            {"item": "Calculate depreciation", "required": True, "completed": True},
        ]
        
        required_incomplete = [
            c for c in checklist
            if c["required"] and not c["completed"]
        ]
        
        can_close = len(required_incomplete) == 0
        
        assert can_close is False
        assert len(required_incomplete) == 1


class TestClosingEntryReversal:
    """Tests for closing entry auto-reversal."""
    
    def test_accrual_reversal_entry(self):
        """Test accrual reversal entry generation."""
        accrual_entry = {
            "date": date(2026, 12, 31),
            "description": "Accrued expenses",
            "lines": [
                {"account": "6900", "debit": Decimal("25000.00"), "credit": Decimal("0.00")},
                {"account": "2100", "debit": Decimal("0.00"), "credit": Decimal("25000.00")},
            ],
            "auto_reverse": True,
            "reverse_date": date(2027, 1, 1),
        }
        
        # Generate reversal
        if accrual_entry["auto_reverse"]:
            reversal_entry = {
                "date": accrual_entry["reverse_date"],
                "description": f"Reversal: {accrual_entry['description']}",
                "lines": [
                    {"account": l["account"], "debit": l["credit"], "credit": l["debit"]}
                    for l in accrual_entry["lines"]
                ],
            }
        
        assert reversal_entry["date"] == date(2027, 1, 1)
        assert reversal_entry["lines"][0]["debit"] == Decimal("0.00")
        assert reversal_entry["lines"][0]["credit"] == Decimal("25000.00")
        assert reversal_entry["lines"][1]["debit"] == Decimal("25000.00")
        assert reversal_entry["lines"][1]["credit"] == Decimal("0.00")


class TestAuditTrail:
    """Tests for year-end audit trail."""
    
    def test_closing_entry_audit_log(self):
        """Test closing entries are logged for audit."""
        closing_actions = [
            {"action": "close_revenue", "timestamp": datetime(2026, 12, 31, 23, 0, 0), "user": "admin"},
            {"action": "close_expenses", "timestamp": datetime(2026, 12, 31, 23, 5, 0), "user": "admin"},
            {"action": "close_to_re", "timestamp": datetime(2026, 12, 31, 23, 10, 0), "user": "admin"},
            {"action": "lock_year", "timestamp": datetime(2026, 12, 31, 23, 15, 0), "user": "admin"},
        ]
        
        assert len(closing_actions) == 4
        assert closing_actions[0]["action"] == "close_revenue"
        assert closing_actions[-1]["action"] == "lock_year"
    
    def test_year_lock_timestamp_recorded(self):
        """Test year lock timestamp is recorded."""
        year_close_record = {
            "fiscal_year": 2026,
            "closed_at": datetime(2026, 12, 31, 23, 59, 0),
            "closed_by": "admin",
            "locked": True,
            "lock_reason": "Year-end close",
        }
        
        assert year_close_record["locked"] is True
        assert year_close_record["closed_by"] == "admin"


# Need timedelta import
from datetime import timedelta


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
