"""
Tekvwa Pro Audit - Comprehensive Workflow Integration Tests

End-to-end workflow tests covering:
- Invoice to payment with FX
- Multi-entity consolidation flow
- Budget cycle management
- Year-end close to opening
- Report generation workflows
"""

import pytest
from decimal import Decimal
from datetime import date, datetime, timedelta
from uuid import uuid4, UUID
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# MOCK DATA STRUCTURES FOR INTEGRATION TESTS
# =============================================================================

@dataclass
class MockEntity:
    """Mock entity for testing."""
    id: UUID
    name: str
    functional_currency: str
    parent_id: Optional[UUID] = None
    ownership_percentage: Decimal = Decimal("100.00")


@dataclass
class MockAccount:
    """Mock GL account for testing."""
    id: UUID
    code: str
    name: str
    account_type: str  # asset, liability, equity, revenue, expense
    balance: Decimal = Decimal("0.00")


@dataclass
class MockInvoice:
    """Mock invoice for testing."""
    id: UUID
    entity_id: UUID
    invoice_number: str
    currency: str
    amount: Decimal
    functional_amount: Decimal
    exchange_rate: Decimal
    status: str = "draft"
    payments: List[dict] = field(default_factory=list)


@dataclass
class MockJournalEntry:
    """Mock journal entry for testing."""
    id: UUID
    entity_id: UUID
    entry_date: date
    description: str
    lines: List[dict]
    status: str = "posted"


# =============================================================================
# INTEGRATION TEST: INVOICE TO PAYMENT WITH FX
# =============================================================================

class TestInvoiceToPaymentFXWorkflow:
    """Integration test for complete invoice-to-payment with FX."""
    
    def test_complete_invoice_payment_cycle_with_fx(self):
        """Test complete cycle: Invoice creation → Payment → FX gain/loss."""
        # Setup
        entity_id = uuid4()
        functional_currency = "NGN"
        invoice_currency = "USD"
        
        # Step 1: Create USD invoice
        invoice = MockInvoice(
            id=uuid4(),
            entity_id=entity_id,
            invoice_number="INV-001",
            currency=invoice_currency,
            amount=Decimal("1000.00"),  # USD
            functional_amount=Decimal("1500000.00"),  # NGN at 1500 rate
            exchange_rate=Decimal("1500.00"),
            status="draft"
        )
        
        assert invoice.amount == Decimal("1000.00")
        assert invoice.functional_amount == Decimal("1500000.00")
        
        # Step 2: Post invoice
        invoice.status = "posted"
        
        # Create AR journal entry
        ar_entry_lines = [
            {"account": "1200", "debit": invoice.functional_amount, "credit": Decimal("0.00")},
            {"account": "4000", "debit": Decimal("0.00"), "credit": invoice.functional_amount},
        ]
        
        total_debit = sum(l["debit"] for l in ar_entry_lines)
        total_credit = sum(l["credit"] for l in ar_entry_lines)
        
        assert total_debit == total_credit
        assert invoice.status == "posted"
        
        # Step 3: Receive payment with rate change
        payment_date = date(2026, 2, 15)
        payment_rate = Decimal("1520.00")  # Rate changed
        payment_amount_usd = Decimal("1000.00")
        payment_amount_ngn = payment_amount_usd * payment_rate
        
        payment = {
            "id": uuid4(),
            "invoice_id": invoice.id,
            "amount": payment_amount_usd,
            "currency": "USD",
            "functional_amount": payment_amount_ngn,
            "exchange_rate": payment_rate,
            "payment_date": payment_date,
        }
        
        invoice.payments.append(payment)
        
        # Step 4: Calculate FX gain/loss
        original_ngn = invoice.functional_amount
        settlement_ngn = payment_amount_ngn
        fx_difference = settlement_ngn - original_ngn
        
        # Rate increased: USD strengthened, we received more NGN
        assert fx_difference == Decimal("20000.00")  # 1520000 - 1500000
        assert fx_difference > 0  # This is a gain for receivable
        
        # Step 5: Create payment and FX journal entries
        payment_entry_lines = [
            # Cash receipt
            {"account": "1010", "debit": payment_amount_ngn, "credit": Decimal("0.00")},
            # Clear AR at original rate
            {"account": "1200", "debit": Decimal("0.00"), "credit": original_ngn},
            # FX Gain
            {"account": "7100", "debit": Decimal("0.00"), "credit": fx_difference},
        ]
        
        total_debit = sum(l["debit"] for l in payment_entry_lines)
        total_credit = sum(l["credit"] for l in payment_entry_lines)
        
        assert total_debit == total_credit
        
        # Step 6: Mark invoice as paid
        invoice.status = "paid"
        assert invoice.status == "paid"
    
    def test_partial_payment_with_remaining_balance(self):
        """Test partial payment leaves correct remaining balance."""
        entity_id = uuid4()
        
        # Create invoice
        invoice_amount_usd = Decimal("5000.00")
        original_rate = Decimal("1500.00")
        
        invoice = MockInvoice(
            id=uuid4(),
            entity_id=entity_id,
            invoice_number="INV-002",
            currency="USD",
            amount=invoice_amount_usd,
            functional_amount=invoice_amount_usd * original_rate,
            exchange_rate=original_rate,
            status="posted"
        )
        
        # First payment: 2000 USD at rate 1510
        payment1_usd = Decimal("2000.00")
        payment1_rate = Decimal("1510.00")
        payment1_ngn = payment1_usd * payment1_rate
        
        # Calculate proportion of original amount being paid
        proportion_paid = payment1_usd / invoice_amount_usd  # 40%
        original_functional_portion = invoice.functional_amount * proportion_paid
        
        fx_gain_1 = payment1_ngn - original_functional_portion
        
        assert proportion_paid == Decimal("0.4")
        assert original_functional_portion == Decimal("3000000.00")  # 7,500,000 * 0.4
        assert fx_gain_1 == Decimal("20000.00")  # 3,020,000 - 3,000,000
        
        # Remaining balance
        remaining_usd = invoice_amount_usd - payment1_usd
        remaining_ngn = invoice.functional_amount - original_functional_portion
        
        assert remaining_usd == Decimal("3000.00")
        assert remaining_ngn == Decimal("4500000.00")


# =============================================================================
# INTEGRATION TEST: MULTI-ENTITY CONSOLIDATION
# =============================================================================

class TestMultiEntityConsolidationWorkflow:
    """Integration test for consolidation workflow."""
    
    def test_parent_subsidiary_consolidation_flow(self):
        """Test complete parent-subsidiary consolidation."""
        # Setup entities
        parent = MockEntity(
            id=uuid4(),
            name="Parent Corp",
            functional_currency="NGN"
        )
        
        subsidiary = MockEntity(
            id=uuid4(),
            name="US Subsidiary",
            functional_currency="USD",
            parent_id=parent.id,
            ownership_percentage=Decimal("80.00")
        )
        
        # Subsidiary trial balance (USD)
        subsidiary_tb = [
            {"account": "1000", "name": "Cash", "debit": Decimal("100000.00"), "credit": Decimal("0.00")},
            {"account": "1200", "name": "AR", "debit": Decimal("50000.00"), "credit": Decimal("0.00")},
            {"account": "2000", "name": "AP", "debit": Decimal("0.00"), "credit": Decimal("30000.00")},
            {"account": "3000", "name": "Equity", "debit": Decimal("0.00"), "credit": Decimal("70000.00")},
            {"account": "3200", "name": "RE", "debit": Decimal("0.00"), "credit": Decimal("30000.00")},
            {"account": "4000", "name": "Revenue", "debit": Decimal("0.00"), "credit": Decimal("80000.00")},
            {"account": "5000", "name": "Expenses", "debit": Decimal("60000.00"), "credit": Decimal("0.00")},
        ]
        
        # Verify balanced
        total_debit = sum(tb["debit"] for tb in subsidiary_tb)
        total_credit = sum(tb["credit"] for tb in subsidiary_tb)
        assert total_debit == total_credit == Decimal("210000.00")
        
        # Translation rates
        closing_rate = Decimal("1500.00")
        average_rate = Decimal("1480.00")
        historical_rate = Decimal("1400.00")  # For equity
        
        # Translate to NGN
        translated_tb = []
        for line in subsidiary_tb:
            account_type = "monetary" if line["account"] in ["1000", "1200", "2000"] else \
                          "equity" if line["account"] in ["3000", "3200"] else \
                          "income"
            
            if account_type == "monetary":
                rate = closing_rate
            elif account_type == "equity":
                rate = historical_rate
            else:  # income statement
                rate = average_rate
            
            translated_tb.append({
                **line,
                "debit_ngn": line["debit"] * rate,
                "credit_ngn": line["credit"] * rate,
                "rate_used": rate,
            })
        
        # Calculate CTA (balancing figure)
        total_debit_ngn = sum(tb["debit_ngn"] for tb in translated_tb)
        total_credit_ngn = sum(tb["credit_ngn"] for tb in translated_tb)
        cta = total_credit_ngn - total_debit_ngn
        
        # Apply minority interest (20%)
        nci_percentage = Decimal("1.00") - subsidiary.ownership_percentage / 100
        
        # Net income = Revenue - Expenses
        net_income_usd = Decimal("80000.00") - Decimal("60000.00")
        net_income_ngn = net_income_usd * average_rate
        nci_share = net_income_ngn * nci_percentage
        
        assert net_income_usd == Decimal("20000.00")
        assert net_income_ngn == Decimal("29600000.00")
        assert nci_share == Decimal("5920000.00")  # 20% of net income
    
    def test_intercompany_elimination_entries(self):
        """Test intercompany elimination entry generation."""
        parent_id = uuid4()
        subsidiary_id = uuid4()
        
        # Intercompany receivable/payable
        ic_balance = Decimal("50000000.00")  # 50M NGN
        
        # Parent has receivable from subsidiary
        parent_tb = [
            {"account": "1250", "name": "IC Receivable", "entity": parent_id, 
             "debit": ic_balance, "credit": Decimal("0.00")},
        ]
        
        # Subsidiary has payable to parent
        subsidiary_tb = [
            {"account": "2100", "name": "IC Payable", "entity": subsidiary_id,
             "debit": Decimal("0.00"), "credit": ic_balance},
        ]
        
        # Generate elimination entry
        elimination_entry = {
            "description": "Eliminate intercompany receivable/payable",
            "lines": [
                {"account": "2100", "debit": ic_balance, "credit": Decimal("0.00")},  # Dr IC Payable
                {"account": "1250", "debit": Decimal("0.00"), "credit": ic_balance},  # Cr IC Receivable
            ]
        }
        
        total_debit = sum(l["debit"] for l in elimination_entry["lines"])
        total_credit = sum(l["credit"] for l in elimination_entry["lines"])
        
        assert total_debit == total_credit == ic_balance


# =============================================================================
# INTEGRATION TEST: BUDGET CYCLE
# =============================================================================

class TestBudgetCycleWorkflow:
    """Integration test for complete budget cycle."""
    
    def test_annual_budget_cycle(self):
        """Test complete annual budget cycle."""
        entity_id = uuid4()
        fiscal_year = 2027
        
        # Step 1: Create budget
        budget = {
            "id": uuid4(),
            "entity_id": entity_id,
            "fiscal_year": fiscal_year,
            "name": "FY2027 Operating Budget",
            "status": "draft",
            "version": 1,
            "line_items": [
                {"account": "4000", "name": "Sales Revenue", 
                 "annual_amount": Decimal("12000000.00"),
                 "monthly_amounts": [Decimal("1000000.00")] * 12},
                {"account": "5000", "name": "Cost of Sales",
                 "annual_amount": Decimal("7200000.00"),
                 "monthly_amounts": [Decimal("600000.00")] * 12},
            ]
        }
        
        assert budget["status"] == "draft"
        
        # Step 2: Submit for approval
        budget["status"] = "submitted"
        budget["submitted_at"] = datetime.now()
        budget["submitted_by"] = "budget_owner"
        
        assert budget["status"] == "submitted"
        
        # Step 3: Review and approve
        approvals = []
        required_approvals = 2
        
        approvals.append({"approver": "manager", "approved_at": datetime.now()})
        assert len(approvals) < required_approvals
        
        approvals.append({"approver": "cfo", "approved_at": datetime.now()})
        assert len(approvals) >= required_approvals
        
        budget["status"] = "approved"
        budget["approved_at"] = datetime.now()
        
        # Step 4: Record actuals and compare
        actuals = {
            "jan": {
                "4000": Decimal("980000.00"),   # Under budget
                "5000": Decimal("620000.00"),   # Over budget
            }
        }
        
        revenue_variance = actuals["jan"]["4000"] - budget["line_items"][0]["monthly_amounts"][0]
        cos_variance = actuals["jan"]["5000"] - budget["line_items"][1]["monthly_amounts"][0]
        
        assert revenue_variance == Decimal("-20000.00")  # Unfavorable
        assert cos_variance == Decimal("20000.00")  # Unfavorable (over budget)
        
        # Step 5: Generate forecast
        months_completed = 1
        ytd_revenue = actuals["jan"]["4000"]
        monthly_run_rate = ytd_revenue / months_completed
        forecast_revenue = monthly_run_rate * 12
        
        budget_revenue = budget["line_items"][0]["annual_amount"]
        forecast_variance = forecast_revenue - budget_revenue
        
        assert forecast_revenue == Decimal("11760000.00")
        assert forecast_variance == Decimal("-240000.00")  # Projected shortfall
    
    def test_budget_revision_workflow(self):
        """Test mid-year budget revision."""
        # Original budget
        original_budget = {
            "id": uuid4(),
            "version": 1,
            "is_current": True,
            "annual_revenue": Decimal("12000000.00"),
        }
        
        # Create revision
        revised_budget = {
            "id": uuid4(),
            "parent_id": original_budget["id"],
            "version": 2,
            "is_current": True,
            "annual_revenue": Decimal("11500000.00"),  # Reduced forecast
            "revision_reason": "Q2 market conditions",
        }
        
        # Mark original as not current
        original_budget["is_current"] = False
        
        assert revised_budget["version"] == 2
        assert revised_budget["parent_id"] == original_budget["id"]
        assert original_budget["is_current"] is False
        assert revised_budget["is_current"] is True


# =============================================================================
# INTEGRATION TEST: YEAR-END TO OPENING
# =============================================================================

class TestYearEndToOpeningWorkflow:
    """Integration test for year-end to new year opening."""
    
    def test_complete_year_end_workflow(self):
        """Test complete year-end close and new year opening."""
        entity_id = uuid4()
        closing_year = 2026
        
        # Step 1: Pre-close trial balance
        trial_balance = [
            # Assets
            {"account": "1000", "name": "Cash", "type": "asset",
             "debit": Decimal("500000.00"), "credit": Decimal("0.00")},
            {"account": "1200", "name": "AR", "type": "asset",
             "debit": Decimal("300000.00"), "credit": Decimal("0.00")},
            # Liabilities
            {"account": "2000", "name": "AP", "type": "liability",
             "debit": Decimal("0.00"), "credit": Decimal("200000.00")},
            # Equity
            {"account": "3100", "name": "Capital", "type": "equity",
             "debit": Decimal("0.00"), "credit": Decimal("400000.00")},
            {"account": "3200", "name": "Retained Earnings", "type": "equity",
             "debit": Decimal("0.00"), "credit": Decimal("100000.00")},
            # Revenue
            {"account": "4000", "name": "Sales", "type": "revenue",
             "debit": Decimal("0.00"), "credit": Decimal("500000.00")},
            # Expenses
            {"account": "5000", "name": "Cost of Sales", "type": "expense",
             "debit": Decimal("300000.00"), "credit": Decimal("0.00")},
            {"account": "6000", "name": "Operating Expenses", "type": "expense",
             "debit": Decimal("100000.00"), "credit": Decimal("0.00")},
        ]
        
        # Verify balanced
        total_debit = sum(tb["debit"] for tb in trial_balance)
        total_credit = sum(tb["credit"] for tb in trial_balance)
        assert total_debit == total_credit
        
        # Step 2: Calculate net income
        total_revenue = sum(tb["credit"] for tb in trial_balance if tb["type"] == "revenue")
        total_expenses = sum(tb["debit"] for tb in trial_balance if tb["type"] == "expense")
        net_income = total_revenue - total_expenses
        
        assert net_income == Decimal("100000.00")
        
        # Step 3: Generate closing entries
        closing_entries = []
        
        # Close revenue accounts
        for tb in trial_balance:
            if tb["type"] == "revenue" and tb["credit"] > 0:
                closing_entries.append({
                    "description": f"Close {tb['name']}",
                    "lines": [
                        {"account": tb["account"], "debit": tb["credit"], "credit": Decimal("0.00")},
                        {"account": "5999", "debit": Decimal("0.00"), "credit": tb["credit"]},
                    ]
                })
        
        # Close expense accounts
        for tb in trial_balance:
            if tb["type"] == "expense" and tb["debit"] > 0:
                closing_entries.append({
                    "description": f"Close {tb['name']}",
                    "lines": [
                        {"account": "5999", "debit": tb["debit"], "credit": Decimal("0.00")},
                        {"account": tb["account"], "debit": Decimal("0.00"), "credit": tb["debit"]},
                    ]
                })
        
        # Close income summary to retained earnings
        closing_entries.append({
            "description": "Close Income Summary to Retained Earnings",
            "lines": [
                {"account": "5999", "debit": net_income, "credit": Decimal("0.00")},
                {"account": "3200", "debit": Decimal("0.00"), "credit": net_income},
            ]
        })
        
        # Verify each closing entry is balanced
        for entry in closing_entries:
            entry_debit = sum(l["debit"] for l in entry["lines"])
            entry_credit = sum(l["credit"] for l in entry["lines"])
            assert entry_debit == entry_credit
        
        # Step 4: Generate opening balances for new year
        opening_balances = []
        new_re_balance = Decimal("100000.00") + net_income  # Old RE + net income
        
        for tb in trial_balance:
            if tb["type"] in ["asset", "liability", "equity"]:
                if tb["account"] == "3200":  # Retained earnings
                    opening_balances.append({
                        "account": tb["account"],
                        "name": tb["name"],
                        "debit": Decimal("0.00"),
                        "credit": new_re_balance,
                    })
                else:
                    opening_balances.append({
                        "account": tb["account"],
                        "name": tb["name"],
                        "debit": tb["debit"],
                        "credit": tb["credit"],
                    })
        
        # Verify opening balances are balanced
        opening_debit = sum(ob["debit"] for ob in opening_balances)
        opening_credit = sum(ob["credit"] for ob in opening_balances)
        
        assert opening_debit == opening_credit
        
        # New retained earnings includes net income
        new_re = next(ob for ob in opening_balances if ob["account"] == "3200")
        assert new_re["credit"] == Decimal("200000.00")


# =============================================================================
# INTEGRATION TEST: REPORT GENERATION WORKFLOW
# =============================================================================

class TestReportGenerationWorkflow:
    """Integration test for report generation workflow."""
    
    def test_financial_statement_generation_flow(self):
        """Test complete financial statement generation."""
        entity_id = uuid4()
        report_date = date(2026, 12, 31)
        
        # Step 1: Get trial balance data
        trial_balance = [
            {"account": "1000", "name": "Cash", "type": "asset", "balance": Decimal("500000.00")},
            {"account": "1200", "name": "AR", "type": "asset", "balance": Decimal("300000.00")},
            {"account": "1500", "name": "Inventory", "type": "asset", "balance": Decimal("400000.00")},
            {"account": "1700", "name": "Fixed Assets", "type": "asset", "balance": Decimal("1000000.00")},
            {"account": "2000", "name": "AP", "type": "liability", "balance": Decimal("-200000.00")},
            {"account": "2500", "name": "Long-term Debt", "type": "liability", "balance": Decimal("-500000.00")},
            {"account": "3100", "name": "Capital", "type": "equity", "balance": Decimal("-1000000.00")},
            {"account": "3200", "name": "RE", "type": "equity", "balance": Decimal("-500000.00")},
        ]
        
        # Step 2: Build balance sheet
        balance_sheet = {
            "report_date": report_date,
            "assets": {
                "current": [],
                "non_current": [],
                "total": Decimal("0.00"),
            },
            "liabilities": {
                "current": [],
                "non_current": [],
                "total": Decimal("0.00"),
            },
            "equity": {
                "items": [],
                "total": Decimal("0.00"),
            },
        }
        
        # Classify accounts
        for tb in trial_balance:
            if tb["type"] == "asset":
                if tb["account"] in ["1000", "1200", "1500"]:
                    balance_sheet["assets"]["current"].append(tb)
                else:
                    balance_sheet["assets"]["non_current"].append(tb)
            elif tb["type"] == "liability":
                if tb["account"] == "2000":
                    balance_sheet["liabilities"]["current"].append(tb)
                else:
                    balance_sheet["liabilities"]["non_current"].append(tb)
            elif tb["type"] == "equity":
                balance_sheet["equity"]["items"].append(tb)
        
        # Calculate totals
        balance_sheet["assets"]["total"] = sum(
            tb["balance"] for tb in 
            balance_sheet["assets"]["current"] + balance_sheet["assets"]["non_current"]
        )
        balance_sheet["liabilities"]["total"] = abs(sum(
            tb["balance"] for tb in 
            balance_sheet["liabilities"]["current"] + balance_sheet["liabilities"]["non_current"]
        ))
        balance_sheet["equity"]["total"] = abs(sum(
            tb["balance"] for tb in balance_sheet["equity"]["items"]
        ))
        
        # Verify accounting equation
        total_assets = balance_sheet["assets"]["total"]
        total_liab_equity = balance_sheet["liabilities"]["total"] + balance_sheet["equity"]["total"]
        
        assert total_assets == Decimal("2200000.00")
        assert total_liab_equity == Decimal("2200000.00")
        assert total_assets == total_liab_equity
        
        # Step 3: Apply report template formatting
        template = {
            "show_subtotals": True,
            "decimal_places": 2,
            "thousand_separator": ",",
            "negative_format": "parentheses",
        }
        
        def format_amount(amount: Decimal, template: dict) -> str:
            if amount < 0 and template["negative_format"] == "parentheses":
                return f"({abs(amount):,.{template['decimal_places']}f})"
            return f"{amount:,.{template['decimal_places']}f}"
        
        formatted_total = format_amount(total_assets, template)
        assert formatted_total == "2,200,000.00"
    
    def test_scheduled_report_execution(self):
        """Test scheduled report execution workflow."""
        # Schedule setup
        schedule = {
            "id": uuid4(),
            "report_type": "balance_sheet",
            "entity_id": uuid4(),
            "frequency": "monthly",
            "day_of_month": 5,
            "recipients": ["cfo@company.com", "controller@company.com"],
            "formats": ["pdf", "xlsx"],
            "is_active": True,
            "last_run": None,
        }
        
        # Check if schedule should run
        today = date(2026, 3, 5)
        should_run = (
            schedule["is_active"] and 
            today.day == schedule["day_of_month"]
        )
        
        assert should_run is True
        
        # Execute report generation
        generation_log = {
            "id": uuid4(),
            "schedule_id": schedule["id"],
            "started_at": datetime.now(),
            "report_date": date(2026, 2, 28),  # End of previous month
            "formats_generated": [],
            "recipients_notified": [],
            "status": "running",
        }
        
        # Generate each format
        for fmt in schedule["formats"]:
            generation_log["formats_generated"].append({
                "format": fmt,
                "file_path": f"/reports/{generation_log['id']}.{fmt}",
                "size_bytes": 15000 if fmt == "pdf" else 25000,
            })
        
        # Notify recipients
        for recipient in schedule["recipients"]:
            generation_log["recipients_notified"].append({
                "email": recipient,
                "sent_at": datetime.now(),
                "status": "sent",
            })
        
        # Complete
        generation_log["status"] = "completed"
        generation_log["completed_at"] = datetime.now()
        schedule["last_run"] = datetime.now()
        
        assert generation_log["status"] == "completed"
        assert len(generation_log["formats_generated"]) == 2
        assert len(generation_log["recipients_notified"]) == 2


# =============================================================================
# INTEGRATION TEST: AUDIT TRAIL
# =============================================================================

class TestAuditTrailWorkflow:
    """Integration test for audit trail integrity."""
    
    def test_transaction_audit_trail(self):
        """Test complete audit trail for a transaction."""
        # Create invoice with full audit trail
        invoice_id = uuid4()
        
        audit_log = []
        
        # Creation
        audit_log.append({
            "action": "create",
            "entity_type": "invoice",
            "entity_id": invoice_id,
            "user_id": uuid4(),
            "timestamp": datetime(2026, 1, 15, 10, 0, 0),
            "changes": {"status": [None, "draft"], "amount": [None, "1000000.00"]},
        })
        
        # Edit
        audit_log.append({
            "action": "update",
            "entity_type": "invoice",
            "entity_id": invoice_id,
            "user_id": uuid4(),
            "timestamp": datetime(2026, 1, 15, 11, 0, 0),
            "changes": {"amount": ["1000000.00", "1100000.00"]},
        })
        
        # Approval
        audit_log.append({
            "action": "approve",
            "entity_type": "invoice",
            "entity_id": invoice_id,
            "user_id": uuid4(),
            "timestamp": datetime(2026, 1, 15, 14, 0, 0),
            "changes": {"status": ["draft", "approved"]},
        })
        
        # Post
        audit_log.append({
            "action": "post",
            "entity_type": "invoice",
            "entity_id": invoice_id,
            "user_id": uuid4(),
            "timestamp": datetime(2026, 1, 15, 14, 30, 0),
            "changes": {"status": ["approved", "posted"]},
        })
        
        # Verify audit trail integrity
        assert len(audit_log) == 4
        assert all(log["entity_id"] == invoice_id for log in audit_log)
        
        # Verify chronological order
        timestamps = [log["timestamp"] for log in audit_log]
        assert timestamps == sorted(timestamps)
        
        # Can reconstruct final state from audit trail
        final_status = None
        final_amount = None
        
        for log in audit_log:
            if "status" in log["changes"]:
                final_status = log["changes"]["status"][1]
            if "amount" in log["changes"]:
                final_amount = log["changes"]["amount"][1]
        
        assert final_status == "posted"
        assert final_amount == "1100000.00"


# =============================================================================
# APPROVAL WORKFLOW PERSISTENCE (Finding 50, docs/FINDING_50_SCOPE.md)
#
# Everything above in this file uses MockEntity/MockAccount dataclasses with no real database
# involved, so none of it would have caught this: ApprovalWorkflow's model declared trigger_type/
# trigger_condition/total_approvers/approval_timeout_hours/priority/required_approvals, none of
# which existed on the live table (workflow_type/threshold_amount/escalation_hours/
# required_approvers instead) -- and ApprovalWorkflowService.create_workflow
# (app/services/approval_workflow.py) already constructed both ApprovalWorkflow and
# ApprovalWorkflowApprover using the *real* (DB-matching) field names, meaning every single call to
# create_workflow() raised a TypeError before this fix, not a subtler bug. This is a permanent
# regression test against the real persistence path, using the actual service class.
# =============================================================================

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.approval_workflow import ApprovalWorkflowService
from app.models.advanced_accounting import ApprovalWorkflow, ApprovalWorkflowApprover


class TestApprovalWorkflowPersistence:
    """Regression coverage for Finding 50's ApprovalWorkflow/ApprovalWorkflowApprover column drift."""

    async def test_create_workflow_with_approvers(
        self, db_session: AsyncSession, test_entity, test_user,
    ):
        service = ApprovalWorkflowService()
        workflow = await service.create_workflow(
            db=db_session,
            entity_id=test_entity.id,
            workflow_type="budget",
            name="Budget Approval",
            approvers=[
                {"user_id": test_user.id, "role": "approver", "order": 1, "is_required": True},
            ],
            created_by=test_user.id,
        )

        assert workflow.id is not None
        assert workflow.workflow_type == "budget"
        assert workflow.required_approvers == 1

        result = await db_session.execute(
            select(ApprovalWorkflow)
            .options(selectinload(ApprovalWorkflow.approvers))
            .where(ApprovalWorkflow.id == workflow.id)
        )
        reloaded = result.scalar_one()
        assert len(reloaded.approvers) == 1

        approver = reloaded.approvers[0]
        assert approver.user_id == test_user.id
        assert approver.role == "approver"
        assert approver.approval_order == 1
        assert approver.is_required is True
        assert approver.created_at is not None


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
