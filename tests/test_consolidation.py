"""
Tekvwa Pro Audit - Consolidation Unit Tests

Comprehensive tests for multi-entity consolidation:
- IAS 21 currency translation (closing/average/historical rates)
- Cumulative Translation Adjustment (CTA) tracking
- Intercompany elimination
- Minority interest calculations
- Consolidated trial balance aggregation
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
# TESTS FOR IAS 21 CURRENCY TRANSLATION
# =============================================================================

class TestCurrencyTranslationRates:
    """Tests for applying correct translation rates per IAS 21."""
    
    def test_assets_at_closing_rate(self):
        """IAS 21.39(a): Assets translated at closing rate."""
        # USD subsidiary asset value
        asset_usd = Decimal("100000.00")
        closing_rate = Decimal("1550.00")  # NGN/USD
        
        translated_ngn = asset_usd * closing_rate
        
        assert translated_ngn == Decimal("155000000.00")
    
    def test_liabilities_at_closing_rate(self):
        """IAS 21.39(a): Liabilities translated at closing rate."""
        liability_usd = Decimal("50000.00")
        closing_rate = Decimal("1550.00")
        
        translated_ngn = liability_usd * closing_rate
        
        assert translated_ngn == Decimal("77500000.00")
    
    def test_revenue_at_average_rate(self):
        """IAS 21.39(b): Income/expenses at transaction date or average rate."""
        revenue_usd = Decimal("200000.00")
        average_rate = Decimal("1520.00")  # Average for the period
        
        translated_ngn = revenue_usd * average_rate
        
        assert translated_ngn == Decimal("304000000.00")
    
    def test_expenses_at_average_rate(self):
        """IAS 21.39(b): Expenses translated at average rate."""
        expenses_usd = Decimal("150000.00")
        average_rate = Decimal("1520.00")
        
        translated_ngn = expenses_usd * average_rate
        
        assert translated_ngn == Decimal("228000000.00")
    
    def test_equity_capital_at_historical_rate(self):
        """IAS 21.39(c): Equity at historical rates."""
        share_capital_usd = Decimal("500000.00")
        historical_rate = Decimal("1200.00")  # Rate when invested
        
        translated_ngn = share_capital_usd * historical_rate
        
        assert translated_ngn == Decimal("600000000.00")
    
    def test_retained_earnings_at_historical_rate(self):
        """Opening retained earnings at historical rate."""
        retained_earnings_usd = Decimal("100000.00")
        historical_rate = Decimal("1350.00")  # Rate at start of period
        
        translated_ngn = retained_earnings_usd * historical_rate
        
        assert translated_ngn == Decimal("135000000.00")


class TestCTACalculation:
    """Tests for Cumulative Translation Adjustment calculations."""
    
    def test_cta_from_rate_difference(self):
        """Test CTA arising from different rates on assets vs income."""
        # Simplified example:
        # Net assets: 100,000 USD
        # - At closing rate (1550): 155,000,000 NGN
        # - If all at average rate (1520): 152,000,000 NGN
        # CTA = 3,000,000 NGN
        
        net_assets_usd = Decimal("100000.00")
        closing_rate = Decimal("1550.00")
        average_rate = Decimal("1520.00")
        
        closing_translation = net_assets_usd * closing_rate
        average_translation = net_assets_usd * average_rate
        
        cta = closing_translation - average_translation
        
        assert cta == Decimal("3000000.00")
    
    def test_cta_calculation_comprehensive(self):
        """Comprehensive CTA calculation per IAS 21."""
        # Subsidiary in USD
        # Assets at closing rate
        assets_usd = Decimal("500000.00")
        closing_rate = Decimal("1550.00")
        assets_ngn = assets_usd * closing_rate  # 775,000,000
        
        # Liabilities at closing rate
        liabilities_usd = Decimal("200000.00")
        liabilities_ngn = liabilities_usd * closing_rate  # 310,000,000
        
        # Net assets at closing rate
        net_assets_ngn = assets_ngn - liabilities_ngn  # 465,000,000
        
        # Share capital at historical rate
        share_capital_usd = Decimal("200000.00")
        historical_rate = Decimal("1200.00")
        share_capital_ngn = share_capital_usd * historical_rate  # 240,000,000
        
        # Revenue at average rate
        revenue_usd = Decimal("300000.00")
        average_rate = Decimal("1480.00")
        revenue_ngn = revenue_usd * average_rate  # 444,000,000
        
        # Expenses at average rate
        expenses_usd = Decimal("200000.00")
        expenses_ngn = expenses_usd * average_rate  # 296,000,000
        
        # Net income
        net_income_ngn = revenue_ngn - expenses_ngn  # 148,000,000
        
        # Total equity (excluding CTA)
        equity_before_cta = share_capital_ngn + net_income_ngn  # 388,000,000
        
        # CTA = Net assets at closing - Equity before CTA
        cta = net_assets_ngn - equity_before_cta  # 77,000,000
        
        assert cta == Decimal("77000000.00")
    
    def test_cta_gain_when_functional_currency_strengthens(self):
        """CTA gain when parent's currency strengthens."""
        # If NGN strengthens relative to USD:
        # More NGN per USD -> higher translated values
        prior_rate = Decimal("1500.00")
        current_rate = Decimal("1550.00")  # NGN weakened (more NGN per USD)
        
        net_assets_usd = Decimal("100000.00")
        
        prior_translation = net_assets_usd * prior_rate
        current_translation = net_assets_usd * current_rate
        
        # Translation gain (more NGN value)
        cta_movement = current_translation - prior_translation
        
        assert cta_movement == Decimal("5000000.00")
        assert cta_movement > 0  # Positive = gain in OCI
    
    def test_cta_loss_when_functional_currency_weakens(self):
        """CTA loss when parent's currency weakens."""
        prior_rate = Decimal("1550.00")
        current_rate = Decimal("1500.00")  # NGN strengthened (less NGN per USD)
        
        net_assets_usd = Decimal("100000.00")
        
        prior_translation = net_assets_usd * prior_rate
        current_translation = net_assets_usd * current_rate
        
        cta_movement = current_translation - prior_translation
        
        assert cta_movement == Decimal("-5000000.00")
        assert cta_movement < 0  # Negative = loss in OCI


class TestIntercompanyElimination:
    """Tests for intercompany transaction elimination."""
    
    def test_eliminate_intercompany_receivables_payables(self):
        """Test elimination of intercompany receivables and payables."""
        # Parent has receivable from subsidiary: 10,000,000 NGN
        # Subsidiary has payable to parent: 10,000,000 NGN
        
        parent_receivable = Decimal("10000000.00")
        sub_payable = Decimal("10000000.00")
        
        # After elimination
        consolidated_receivable = parent_receivable - parent_receivable
        consolidated_payable = sub_payable - sub_payable
        
        assert consolidated_receivable == Decimal("0.00")
        assert consolidated_payable == Decimal("0.00")
    
    def test_eliminate_intercompany_sales_purchases(self):
        """Test elimination of intercompany sales and cost of sales."""
        # Parent sold goods to subsidiary: 50,000,000 NGN
        # This creates:
        # - Parent revenue: 50,000,000
        # - Subsidiary cost of sales: 50,000,000
        
        parent_revenue = Decimal("50000000.00")
        sub_cogs = Decimal("50000000.00")
        
        # After elimination
        consolidated_revenue = parent_revenue - parent_revenue
        consolidated_cogs = sub_cogs - sub_cogs
        
        assert consolidated_revenue == Decimal("0.00")
        assert consolidated_cogs == Decimal("0.00")
    
    def test_eliminate_unrealized_profit_in_inventory(self):
        """Test elimination of unrealized profit in ending inventory."""
        # Parent sold to subsidiary at 30% markup
        # Subsidiary still holds inventory at cost of 13,000,000
        # Original cost to parent: 10,000,000
        # Markup: 3,000,000 (unrealized profit)
        
        inventory_at_cost_to_sub = Decimal("13000000.00")
        original_cost_to_parent = Decimal("10000000.00")
        unrealized_profit = inventory_at_cost_to_sub - original_cost_to_parent
        
        # Elimination entry reduces inventory and retained earnings
        consolidated_inventory = inventory_at_cost_to_sub - unrealized_profit
        
        assert unrealized_profit == Decimal("3000000.00")
        assert consolidated_inventory == original_cost_to_parent
    
    def test_eliminate_intercompany_dividends(self):
        """Test elimination of intercompany dividends."""
        # Subsidiary declared dividend: 5,000,000
        # Parent's share (80%): 4,000,000
        # Parent recorded as dividend income
        
        sub_dividend_declared = Decimal("5000000.00")
        parent_ownership = Decimal("0.80")
        parent_dividend_income = sub_dividend_declared * parent_ownership
        
        # Elimination:
        # DR: Dividend income (parent) 4,000,000
        # CR: Dividend declared (sub) 4,000,000
        
        consolidated_dividend_income = parent_dividend_income - parent_dividend_income
        
        assert consolidated_dividend_income == Decimal("0.00")
    
    def test_eliminate_intercompany_loan(self):
        """Test elimination of intercompany loans and interest."""
        # Parent loaned to subsidiary: 100,000,000 NGN
        # Interest rate: 10%
        # Interest expense/income: 10,000,000
        
        loan_amount = Decimal("100000000.00")
        interest_rate = Decimal("0.10")
        interest = loan_amount * interest_rate
        
        # Parent: Loan receivable + Interest income
        # Subsidiary: Loan payable + Interest expense
        
        # After elimination
        consolidated_loan_receivable = loan_amount - loan_amount
        consolidated_loan_payable = loan_amount - loan_amount
        consolidated_interest_income = interest - interest
        consolidated_interest_expense = interest - interest
        
        assert consolidated_loan_receivable == Decimal("0.00")
        assert consolidated_loan_payable == Decimal("0.00")
        assert consolidated_interest_income == Decimal("0.00")
        assert consolidated_interest_expense == Decimal("0.00")


class TestMinorityInterest:
    """Tests for minority (non-controlling) interest calculations."""
    
    def test_calculate_minority_interest_at_acquisition(self):
        """Test NCI calculation at acquisition date."""
        # Parent acquires 80% of subsidiary
        # Subsidiary net assets: 100,000,000 NGN
        # NCI: 20%
        
        sub_net_assets = Decimal("100000000.00")
        parent_ownership = Decimal("0.80")
        nci_percentage = Decimal("1.00") - parent_ownership
        
        nci_share = sub_net_assets * nci_percentage
        
        assert nci_share == Decimal("20000000.00")
    
    def test_calculate_minority_interest_in_profit(self):
        """Test NCI share of subsidiary profit."""
        # Subsidiary net profit: 25,000,000 NGN
        # NCI: 20%
        
        sub_net_profit = Decimal("25000000.00")
        nci_percentage = Decimal("0.20")
        
        nci_share_of_profit = sub_net_profit * nci_percentage
        
        assert nci_share_of_profit == Decimal("5000000.00")
    
    def test_calculate_minority_interest_in_loss(self):
        """Test NCI share of subsidiary loss."""
        # Subsidiary net loss: 10,000,000 NGN
        # NCI: 20%
        
        sub_net_loss = Decimal("-10000000.00")
        nci_percentage = Decimal("0.20")
        
        nci_share_of_loss = sub_net_loss * nci_percentage
        
        assert nci_share_of_loss == Decimal("-2000000.00")
    
    def test_minority_interest_year_end_balance(self):
        """Test NCI balance at year end."""
        # Opening NCI: 20,000,000 NGN
        # + NCI share of profit: 5,000,000
        # - NCI share of dividends: 1,000,000
        # = Closing NCI: 24,000,000
        
        opening_nci = Decimal("20000000.00")
        nci_profit_share = Decimal("5000000.00")
        nci_dividend_share = Decimal("1000000.00")
        
        closing_nci = opening_nci + nci_profit_share - nci_dividend_share
        
        assert closing_nci == Decimal("24000000.00")
    
    def test_minority_interest_with_multiple_subsidiaries(self):
        """Test NCI calculation across multiple subsidiaries."""
        subsidiaries = [
            {"net_assets": Decimal("100000000.00"), "nci_pct": Decimal("0.20")},
            {"net_assets": Decimal("50000000.00"), "nci_pct": Decimal("0.30")},
            {"net_assets": Decimal("75000000.00"), "nci_pct": Decimal("0.15")},
        ]
        
        total_nci = sum(
            sub["net_assets"] * sub["nci_pct"]
            for sub in subsidiaries
        )
        
        # 20,000,000 + 15,000,000 + 11,250,000 = 46,250,000
        assert total_nci == Decimal("46250000.00")


class TestConsolidatedTrialBalance:
    """Tests for consolidated trial balance aggregation."""
    
    def test_aggregate_same_account_codes(self):
        """Test aggregation of same account across entities."""
        # Cash accounts from different entities
        parent_cash = Decimal("50000000.00")
        sub1_cash = Decimal("25000000.00")
        sub2_cash = Decimal("15000000.00")
        
        consolidated_cash = parent_cash + sub1_cash + sub2_cash
        
        assert consolidated_cash == Decimal("90000000.00")
    
    def test_translated_amounts_in_aggregation(self):
        """Test that foreign sub amounts are translated before aggregation."""
        # Parent cash (NGN): 50,000,000
        # Subsidiary cash (USD): 50,000 * 1550 = 77,500,000
        
        parent_cash_ngn = Decimal("50000000.00")
        sub_cash_usd = Decimal("50000.00")
        closing_rate = Decimal("1550.00")
        
        sub_cash_ngn = sub_cash_usd * closing_rate
        consolidated_cash = parent_cash_ngn + sub_cash_ngn
        
        assert consolidated_cash == Decimal("127500000.00")
    
    def test_debit_credit_balance_after_consolidation(self):
        """Test that consolidated TB remains balanced."""
        # Simplified example
        debits = {
            "cash": Decimal("100000000.00"),
            "receivables": Decimal("50000000.00"),
            "inventory": Decimal("75000000.00"),
            "fixed_assets": Decimal("200000000.00"),
        }
        
        credits = {
            "payables": Decimal("40000000.00"),
            "loans": Decimal("100000000.00"),
            "share_capital": Decimal("200000000.00"),
            "retained_earnings": Decimal("50000000.00"),
            "revenue": Decimal("150000000.00"),
            "nci": Decimal("20000000.00"),
        }
        
        # Add back expenses (debit)
        debits["expenses"] = Decimal("135000000.00")
        
        total_debits = sum(debits.values())
        total_credits = sum(credits.values())
        
        assert total_debits == total_credits
    
    def test_goodwill_calculation(self):
        """Test goodwill calculation on acquisition."""
        # Purchase consideration: 120,000,000 NGN
        # Net assets acquired: 100,000,000 NGN
        # Parent ownership: 80%
        # Fair value of net assets to parent: 80,000,000
        # Goodwill: 120,000,000 - 80,000,000 = 40,000,000
        
        purchase_price = Decimal("120000000.00")
        net_assets = Decimal("100000000.00")
        ownership_pct = Decimal("0.80")
        
        parent_share_of_net_assets = net_assets * ownership_pct
        goodwill = purchase_price - parent_share_of_net_assets
        
        assert goodwill == Decimal("40000000.00")
    
    def test_negative_goodwill_bargain_purchase(self):
        """Test bargain purchase (negative goodwill)."""
        # Purchase consideration: 70,000,000 NGN
        # Net assets acquired: 100,000,000 NGN
        # Parent ownership: 80%
        # Fair value to parent: 80,000,000
        # Bargain gain: 80,000,000 - 70,000,000 = 10,000,000
        
        purchase_price = Decimal("70000000.00")
        net_assets = Decimal("100000000.00")
        ownership_pct = Decimal("0.80")
        
        parent_share_of_net_assets = net_assets * ownership_pct
        bargain_purchase_gain = parent_share_of_net_assets - purchase_price
        
        assert bargain_purchase_gain == Decimal("10000000.00")
        assert bargain_purchase_gain > 0  # Recognized in P&L


class TestCTARecycling:
    """Tests for CTA recycling on disposal of foreign operation."""
    
    def test_recycle_cta_on_full_disposal(self):
        """Test reclassification of CTA to P&L on 100% disposal."""
        # Accumulated CTA in OCI: 15,000,000 NGN gain
        # On disposal, recycle to P&L
        
        accumulated_cta = Decimal("15000000.00")
        disposal_percentage = Decimal("1.00")  # 100%
        
        recycled_to_pl = accumulated_cta * disposal_percentage
        remaining_cta = accumulated_cta - recycled_to_pl
        
        assert recycled_to_pl == Decimal("15000000.00")
        assert remaining_cta == Decimal("0.00")
    
    def test_recycle_cta_on_partial_disposal(self):
        """Test proportional reclassification on partial disposal."""
        # Accumulated CTA: 15,000,000 NGN
        # Sell 40% of subsidiary
        
        accumulated_cta = Decimal("15000000.00")
        disposal_percentage = Decimal("0.40")
        
        recycled_to_pl = accumulated_cta * disposal_percentage
        remaining_cta = accumulated_cta - recycled_to_pl
        
        assert recycled_to_pl == Decimal("6000000.00")
        assert remaining_cta == Decimal("9000000.00")
    
    def test_cta_loss_recycling(self):
        """Test recycling of CTA loss to P&L."""
        # Accumulated CTA: -8,000,000 NGN (loss)
        accumulated_cta = Decimal("-8000000.00")
        
        # On full disposal
        recycled_to_pl = accumulated_cta
        
        # Loss is recognized in P&L (reduces profit)
        assert recycled_to_pl == Decimal("-8000000.00")


class TestConsolidationValidation:
    """Tests for consolidation process validation."""
    
    def test_validate_same_reporting_date(self):
        """Subsidiaries should have same reporting date as parent."""
        parent_year_end = date(2025, 12, 31)
        sub_year_end = date(2025, 12, 31)
        
        same_date = parent_year_end == sub_year_end
        
        assert same_date is True
    
    def test_validate_consistent_accounting_policies(self):
        """Test that accounting policies are consistent."""
        # In practice, this requires adjustments if different
        parent_depreciation_method = "straight_line"
        sub_depreciation_method = "straight_line"
        
        policies_consistent = parent_depreciation_method == sub_depreciation_method
        
        assert policies_consistent is True
    
    def test_validate_control_exists(self):
        """Test that parent has control (>50% or other indicators)."""
        ownership_percentages = [
            Decimal("0.80"),  # 80% - control exists
            Decimal("0.51"),  # 51% - control exists
            Decimal("0.50"),  # 50% - may need other factors
            Decimal("0.40"),  # 40% - no automatic control
        ]
        
        for pct in ownership_percentages:
            has_control = pct > Decimal("0.50")
            
            if pct == Decimal("0.80") or pct == Decimal("0.51"):
                assert has_control is True
            else:
                assert has_control is False


# =============================================================================
# INTERCOMPANY TRANSACTION PERSISTENCE (Finding 50, docs/FINDING_50_SCOPE.md)
#
# Every test above in this file is pure arithmetic with no database involved, so none of them
# would have caught this: IntercompanyTransaction's model declared from_entity_id/to_entity_id/
# transaction_date/currency/from_transaction_id/to_transaction_id/elimination_date/notes, but the
# live migrated table had none of them (source_entity_id/target_entity_id/etc. instead, and no
# transaction_date/currency at all) until alembic/versions/20260919_2120_backfill_intercompany_
# transactions_.py. POST /intercompany crashed on every call before that fix. This is a permanent
# regression test for the actual persistence path, not just the migration's own manual verification.
# =============================================================================

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.advanced_accounting import IntercompanyTransaction, EntityGroup
from app.models.entity import BusinessEntity


class TestIntercompanyTransactionPersistence:
    """Regression coverage for Finding 50's IntercompanyTransaction column drift."""

    @pytest_asyncio.fixture
    async def second_entity(self, db_session: AsyncSession, test_organization) -> BusinessEntity:
        """A second business entity in the same org, for the inter-company pair."""
        from app.models.entity import BusinessType
        entity = BusinessEntity(
            name="Second Test Business Ltd",
            organization_id=test_organization.id,
            business_type=BusinessType.LIMITED_COMPANY,
            tin="87654321-0001",
            rc_number="RC654321",
            is_vat_registered=True,
        )
        db_session.add(entity)
        await db_session.commit()
        await db_session.refresh(entity)
        return entity

    async def test_create_and_fetch_intercompany_transaction(
        self, db_session: AsyncSession, test_organization, test_entity: BusinessEntity, second_entity: BusinessEntity,
    ):
        """The exact scenario POST /intercompany performs: construct with the model's own field
        names, flush, then read every field back unchanged."""
        group = EntityGroup(
            organization_id=test_organization.id,
            name="Test Consolidation Group",
            parent_entity_id=test_entity.id,
        )
        db_session.add(group)
        await db_session.commit()
        await db_session.refresh(group)

        ic = IntercompanyTransaction(
            group_id=group.id,
            from_entity_id=test_entity.id,
            to_entity_id=second_entity.id,
            transaction_date=date.today(),
            transaction_type="management_fee",
            amount=Decimal("100000.00"),
            currency="NGN",
            notes="Q1 management fee allocation",
            is_eliminated=False,
        )
        db_session.add(ic)
        await db_session.commit()
        await db_session.refresh(ic)

        assert ic.id is not None
        assert ic.from_entity_id == test_entity.id
        assert ic.to_entity_id == second_entity.id
        assert ic.transaction_date == date.today()
        assert ic.currency == "NGN"
        assert ic.notes == "Q1 management fee allocation"
        assert ic.updated_at is not None


# =============================================================================
# IMMUTABLE LEDGER PERSISTENCE (Finding 50, docs/FINDING_50_SCOPE.md)
#
# The opposite direction from IntercompanyTransaction above: here the model and its only real
# caller (ImmutableLedgerService.create_entry) already agreed with each other on a coherent
# hash-chained ledger design, but the live table implemented a completely different, generic
# audit-log shape instead (resource_type/resource_id/action/data_snapshot/user_id/ip_address, none
# of which anything in the codebase ever used) - so every call to create_entry() crashed before
# this fix, not because the code was wrong, but because the database was never migrated to match
# what the code (and model) always expected.
# =============================================================================

from app.services.immutable_ledger import ImmutableLedgerService


class TestLedgerEntryPersistence:
    """Regression coverage for Finding 50's LedgerEntry column drift."""

    async def test_create_entry_and_verify_hash_chain(
        self, db_session: AsyncSession, test_entity, test_user,
    ):
        service = ImmutableLedgerService()

        entry1 = await service.create_entry(
            db=db_session,
            entity_id=test_entity.id,
            entry_type="transaction",
            source_type="invoice",
            source_id=uuid4(),
            account_code="4000",
            debit_amount=Decimal("50000.00"),
            credit_amount=Decimal("0.00"),
            entry_date=date.today(),
            description="First ledger entry",
            reference="INV-001",
            created_by_id=test_user.id,
        )
        assert entry1.id is not None
        assert entry1.sequence_number == 1
        assert entry1.balance == Decimal("50000.00")
        assert entry1.entry_hash is not None
        assert entry1.previous_hash is None

        entry2 = await service.create_entry(
            db=db_session,
            entity_id=test_entity.id,
            entry_type="transaction",
            source_type="payment",
            source_id=uuid4(),
            account_code="4000",
            debit_amount=Decimal("0.00"),
            credit_amount=Decimal("20000.00"),
            entry_date=date.today(),
            description="Second ledger entry",
            reference="PAY-001",
            created_by_id=test_user.id,
        )
        assert entry2.sequence_number == 2
        assert entry2.balance == Decimal("30000.00")
        assert entry2.previous_hash == entry1.entry_hash


# =============================================================================
# THREE-WAY MATCH PERSISTENCE (Finding 50, docs/FINDING_50_SCOPE.md)
#
# ThreeWayMatch's model previously declared grn_amount/quantity_variance/price_variance/
# tolerances/overrides/payment-authorization fields that ThreeWayMatchingService never used and
# that don't exist on the live table, while missing grn_quantity/discrepancies/resolution_notes,
# which the service always did use. Separately, MatchingStatus's member set didn't match either
# the live enum type or what the service/forensic_audit.py actually reference -- not a casing
# issue, the member set itself was wrong (AttributeError on every real usage). Both are fixed
# together here since resolve_discrepancy can't be tested at all without a working enum.
# =============================================================================

from app.services.three_way_matching import ThreeWayMatchingService
from app.models.advanced_accounting import ThreeWayMatch, MatchingStatus, PurchaseOrder


class TestThreeWayMatchPersistence:
    """Regression coverage for Finding 50's ThreeWayMatch column and enum drift."""

    async def test_create_and_resolve_discrepancy(
        self, db_session: AsyncSession, test_entity, test_vendor, test_user, test_invoice,
    ):
        po = PurchaseOrder(
            entity_id=test_entity.id,
            vendor_id=test_vendor.id,
            po_number="PO-TEST-0001",
            subtotal=Decimal("100000.00"),
            total_amount=Decimal("100000.00"),
            created_by_id=test_user.id,
        )
        db_session.add(po)
        await db_session.commit()
        await db_session.refresh(po)

        match = ThreeWayMatch(
            entity_id=test_entity.id,
            purchase_order_id=po.id,
            invoice_id=test_invoice.id,
            status=MatchingStatus.DISCREPANCY,
            po_amount=Decimal("100000.00"),
            grn_quantity=Decimal("10.0000"),
            invoice_amount=Decimal("105000.00"),
            discrepancies=[{"type": "price_mismatch", "severity": "medium"}],
        )
        db_session.add(match)
        await db_session.commit()
        await db_session.refresh(match)

        assert match.status == MatchingStatus.DISCREPANCY
        assert match.discrepancies[0]["type"] == "price_mismatch"
        assert match.updated_at is not None

        service = ThreeWayMatchingService()
        resolved = await service.resolve_discrepancy(
            db=db_session,
            match_id=match.id,
            resolution="accept",
            resolved_by=test_user.id,
            notes="Approved despite variance",
        )

        assert resolved.status == MatchingStatus.MATCHED
        assert resolved.resolved_by_id == test_user.id
        assert resolved.resolution_notes == "Approved despite variance"
        assert resolved.matched_at is not None


# =============================================================================
# WHT CREDIT NOTE PERSISTENCE (Finding 50, docs/FINDING_50_SCOPE.md)
#
# WHTCreditNote's model previously declared expiry_date/matched_transaction_id/matched_by_id/
# applied_amount/applied_to_period/document_url/document_verified/notes -- none of which exist on
# the live table or have any other reference anywhere in the codebase -- while missing
# expires_at/applied_tax_reference/received_at/created_by_id, which WHTCreditVaultService always
# used. Needed zero migration; the database was already correct.
# =============================================================================

from app.services.wht_credit_vault import WHTCreditVaultService


class TestWHTCreditNotePersistence:
    """Regression coverage for Finding 50's WHTCreditNote column drift."""

    async def test_record_credit_note(
        self, db_session: AsyncSession, test_entity, test_user,
    ):
        service = WHTCreditVaultService()
        credit_note = await service.record_credit_note(
            db=db_session,
            entity_id=test_entity.id,
            credit_note_data={
                "credit_note_number": "WHT-TEST-0001",
                "issue_date": date.today(),
                "issuer_name": "Test Client Ltd",
                "issuer_tin": "12345678-0001",
                "gross_amount": Decimal("500000.00"),
                "wht_type": "professional_fees",
                "description": "Consulting services WHT credit",
            },
            created_by=test_user.id,
        )

        assert credit_note.id is not None
        assert credit_note.description == "Consulting services WHT credit"
        assert credit_note.expires_at is not None
        assert credit_note.created_by_id == test_user.id
        assert credit_note.wht_amount > Decimal("0")


# =============================================================================
# ACCOUNT BALANCE PERSISTENCE (Finding 50, docs/FINDING_50_SCOPE.md)
#
# AccountBalance's model declares entity_id/ytd_debit/ytd_credit/last_updated, and
# app/utils/query_optimization.py, accounting_service.py, and year_end_closing_service.py all
# already query/update using exactly these names -- none of which existed on the live table
# (which had no entity_id, no ytd_debit/ytd_credit, and last_calculated_at instead) until this
# session's migration. Every one of those real call sites would have crashed or silently failed
# to filter/update the intended rows before this fix.
# =============================================================================

from sqlalchemy import select
from app.models.accounting import AccountBalance, ChartOfAccounts, FiscalPeriod, FiscalYear, AccountType, NormalBalance, FiscalPeriodStatus


class TestAccountBalancePersistence:
    """Regression coverage for Finding 50's AccountBalance column drift."""

    async def test_create_and_query_by_entity(
        self, db_session: AsyncSession, test_entity,
    ):
        fiscal_year = FiscalYear(
            entity_id=test_entity.id,
            year_name="FY2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        db_session.add(fiscal_year)
        await db_session.flush()

        fiscal_period = FiscalPeriod(
            entity_id=test_entity.id,
            fiscal_year_id=fiscal_year.id,
            period_name="January 2026",
            period_number=1,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            status=FiscalPeriodStatus.OPEN,
        )
        db_session.add(fiscal_period)
        await db_session.flush()

        account = ChartOfAccounts(
            entity_id=test_entity.id,
            account_code="1000",
            account_name="Cash",
            account_type=AccountType.ASSET,
            normal_balance=NormalBalance.DEBIT,
        )
        db_session.add(account)
        await db_session.flush()
        # Finding 50: allow_manual_entries already existed on the live table, unused anywhere in
        # the codebase, but was never declared on the model until this fix.
        assert account.allow_manual_entries is True

        balance = AccountBalance(
            entity_id=test_entity.id,
            account_id=account.id,
            fiscal_period_id=fiscal_period.id,
            opening_balance=Decimal("100000.00"),
            period_debit=Decimal("50000.00"),
            period_credit=Decimal("20000.00"),
            closing_balance=Decimal("130000.00"),
            ytd_debit=Decimal("50000.00"),
            ytd_credit=Decimal("20000.00"),
        )
        db_session.add(balance)
        await db_session.commit()
        await db_session.refresh(balance)

        assert balance.entity_id == test_entity.id
        assert balance.ytd_debit == Decimal("50000.00")
        assert balance.last_updated is not None

        result = await db_session.execute(
            select(AccountBalance).where(AccountBalance.entity_id == test_entity.id)
        )
        assert result.scalar_one().id == balance.id


# =============================================================================
# RECURRING JOURNAL ENTRY PERSISTENCE (Finding 50, docs/FINDING_50_SCOPE.md)
#
# Unlike every other table fixed under this finding, RecurringJournalEntry is genuinely dead in
# current usage -- imported by accounting_service.py but never constructed, queried, or read
# anywhere. With no real call site to determine intent from, the model was fixed to match the
# live table exactly (not the reverse) since the database is the real, currently-deployed state.
# This is a direct ORM round-trip, not a service-level test, since there's no service to exercise.
# =============================================================================

from app.models.accounting import RecurringJournalEntry


class TestRecurringJournalEntryPersistence:
    """Regression coverage for Finding 50's RecurringJournalEntry column drift."""

    async def test_create_and_fetch(self, db_session: AsyncSession, test_entity, test_user):
        entry = RecurringJournalEntry(
            entity_id=test_entity.id,
            name="Monthly Depreciation",
            description="Auto-generated monthly depreciation entry",
            frequency="monthly",
            start_date=date.today(),
            template_data={"lines": [{"account": "6100", "debit": "10000.00"}]},
            created_by_id=test_user.id,
        )
        db_session.add(entry)
        await db_session.commit()
        await db_session.refresh(entry)

        assert entry.id is not None
        assert entry.template_data["lines"][0]["account"] == "6100"
        assert entry.run_count == 0
        assert entry.auto_post is False

        result = await db_session.execute(
            select(RecurringJournalEntry).where(RecurringJournalEntry.entity_id == test_entity.id)
        )
        assert result.scalar_one().id == entry.id


# =============================================================================
# GL INTEGRATION LOG PERSISTENCE (Finding 50, docs/FINDING_50_SCOPE.md)
#
# gl_integration_logs was missing both created_at and updated_at at the DB level entirely.
# journal_entry_id's nullable/ondelete also didn't match the live column (model said NOT NULL +
# CASCADE, live column is nullable + SET NULL) -- a pure metadata correction, not a behavior
# change, since gl_event_service.py/accounting_service.py always provide a value in practice.
# =============================================================================

from app.models.accounting import GLIntegrationLog


class TestGLIntegrationLogPersistence:
    """Regression coverage for Finding 50's GLIntegrationLog column drift."""

    async def test_create_and_fetch(self, db_session: AsyncSession, test_entity, test_user):
        log = GLIntegrationLog(
            entity_id=test_entity.id,
            source_module="invoicing",
            source_document_type="invoice",
            source_document_id=uuid4(),
            posted_by_id=test_user.id,
        )
        db_session.add(log)
        await db_session.commit()
        await db_session.refresh(log)

        assert log.id is not None
        assert log.journal_entry_id is None  # nullable, matching the live column
        assert log.created_at is not None
        assert log.updated_at is not None
        assert log.is_reversed is False


# =============================================================================
# JOURNAL ENTRY PERSISTENCE (Finding 50, docs/FINDING_50_SCOPE.md)
#
# JournalEntry's model declared attachments (JSONB), which never existed on the live table and had
# zero references anywhere in the codebase, while missing is_recurring/recurring_entry_id, both of
# which already existed on the live table. Neither pair is currently used by any real call site;
# fixed to match the live table exactly since it's the real, deployed state.
# =============================================================================

from app.models.accounting import JournalEntry, JournalEntryType, JournalEntryStatus


class TestJournalEntryPersistence:
    """Regression coverage for Finding 50's JournalEntry column drift."""

    async def test_create_and_fetch(self, db_session: AsyncSession, test_entity, test_user):
        entry = JournalEntry(
            entity_id=test_entity.id,
            entry_number="JE-TEST-0001",
            entry_date=date.today(),
            description="Test journal entry",
            entry_type=JournalEntryType.MANUAL,
            total_debit=Decimal("50000.00"),
            total_credit=Decimal("50000.00"),
            status=JournalEntryStatus.DRAFT,
            created_by_id=test_user.id,
        )
        db_session.add(entry)
        await db_session.commit()
        await db_session.refresh(entry)

        assert entry.id is not None
        assert entry.is_recurring is False
        assert entry.recurring_entry_id is None


# =============================================================================
# JOURNAL ENTRY LINE PERSISTENCE (Finding 50, docs/FINDING_50_SCOPE.md)
#
# department_id/project_id/bank_transaction_id previously declared ForeignKey()s that were never
# actually created on the live table -- confirmed zero references anywhere in the codebase for all
# three, so the ForeignKey()s were removed rather than creating real constraints for currently-
# unused columns. cost_center_id added (already existed on the live table, also unused, also no
# FK). Separately, updated_at was missing at the DB level entirely -- migration adds it.
#
# Not fixed here, flagged instead: the model's __table_args__ declares a uq_je_line_number unique
# constraint (journal_entry_id, line_number) that doesn't exist on the live table either. Unlike
# everything else fixed in this session, adding it would be a genuinely *new* constraint, not
# catching up to something already enforced in the database -- and this environment can't verify
# production has no existing duplicate (journal_entry_id, line_number) pairs. Left as an explicit
# follow-up verification task rather than risking a migration failure on unverified data.
# =============================================================================

from app.models.accounting import JournalEntryLine


class TestJournalEntryLinePersistence:
    """Regression coverage for Finding 50's JournalEntryLine column drift."""

    async def test_create_and_fetch(self, db_session: AsyncSession, test_entity, test_user):
        entry = JournalEntry(
            entity_id=test_entity.id,
            entry_number="JE-TEST-0002",
            entry_date=date.today(),
            description="Test entry for line",
            entry_type=JournalEntryType.MANUAL,
            total_debit=Decimal("10000.00"),
            total_credit=Decimal("10000.00"),
            status=JournalEntryStatus.DRAFT,
            created_by_id=test_user.id,
        )
        db_session.add(entry)
        await db_session.flush()

        account = ChartOfAccounts(
            entity_id=test_entity.id,
            account_code="2000",
            account_name="Accounts Payable",
            account_type=AccountType.LIABILITY,
            normal_balance=NormalBalance.CREDIT,
        )
        db_session.add(account)
        await db_session.flush()

        line = JournalEntryLine(
            journal_entry_id=entry.id,
            account_id=account.id,
            line_number=1,
            debit_amount=Decimal("10000.00"),
            credit_amount=Decimal("0.00"),
        )
        db_session.add(line)
        await db_session.commit()
        await db_session.refresh(line)

        assert line.id is not None
        assert line.department_id is None
        assert line.cost_center_id is None
        assert line.updated_at is not None


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
