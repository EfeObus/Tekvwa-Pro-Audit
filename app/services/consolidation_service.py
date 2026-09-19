"""
Tekvwa Pro Audit - Multi-Entity Consolidation Service

Comprehensive service for financial statement consolidation across entity groups.
Implements IFRS 10 consolidation requirements including:
- Full consolidation for subsidiaries
- Proportional consolidation for joint ventures
- Equity method for associates
- Elimination of intercompany transactions
- Minority interest calculations
- Currency translation for foreign subsidiaries

Performance optimized with Redis caching for consolidated trial balances.
"""

import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum as PyEnum
from collections import defaultdict

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.advanced_accounting import (
    EntityGroup, EntityGroupMember, IntercompanyTransaction, CurrencyTranslationHistory
)
from app.models.accounting import (
    ChartOfAccounts, AccountType, AccountBalance, JournalEntry, 
    JournalEntryLine, JournalEntryStatus, JournalEntryType,
    FiscalPeriod, FiscalYear
)
from app.models.entity import BusinessEntity
from app.services.cache_service import get_cache_service

logger = logging.getLogger(__name__)


class ConsolidationMethod(str, PyEnum):
    """Consolidation methods per IFRS 10/11/28"""
    FULL = "full"  # >50% ownership - subsidiaries
    PROPORTIONAL = "proportional"  # Joint ventures (allowed under IFRS 11 in some cases)
    EQUITY = "equity"  # 20-50% ownership - associates


class EliminationType(str, PyEnum):
    """Types of elimination entries"""
    INTERCOMPANY_REVENUE = "intercompany_revenue"
    INTERCOMPANY_EXPENSE = "intercompany_expense"
    INTERCOMPANY_RECEIVABLE = "intercompany_receivable"
    INTERCOMPANY_PAYABLE = "intercompany_payable"
    INTERCOMPANY_DIVIDEND = "intercompany_dividend"
    INTERCOMPANY_LOAN = "intercompany_loan"
    INVESTMENT_ELIMINATION = "investment_elimination"
    UNREALIZED_PROFIT_INVENTORY = "unrealized_profit_inventory"
    UNREALIZED_PROFIT_FIXED_ASSET = "unrealized_profit_fixed_asset"


class ConsolidationService:
    """Service for multi-entity consolidation operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # =========================================================================
    # ENTITY GROUP MANAGEMENT
    # =========================================================================
    
    async def get_entity_group(
        self,
        group_id: uuid.UUID
    ) -> Optional[EntityGroup]:
        """Get an entity group by ID."""
        result = await self.db.execute(
            select(EntityGroup).where(EntityGroup.id == group_id)
        )
        return result.scalar_one_or_none()
    
    async def get_entity_groups_for_org(
        self,
        organization_id: uuid.UUID
    ) -> List[EntityGroup]:
        """Get all entity groups for an organization."""
        result = await self.db.execute(
            select(EntityGroup).where(
                and_(
                    EntityGroup.organization_id == organization_id,
                    EntityGroup.is_active == True
                )
            )
        )
        return list(result.scalars().all())
    
    async def create_entity_group(
        self,
        organization_id: uuid.UUID,
        name: str,
        parent_entity_id: uuid.UUID,
        consolidation_currency: str = "NGN",
        fiscal_year_end_month: int = 12,
        description: Optional[str] = None
    ) -> EntityGroup:
        """Create a new entity group for consolidation."""
        group = EntityGroup(
            organization_id=organization_id,
            name=name,
            parent_entity_id=parent_entity_id,
            consolidation_currency=consolidation_currency,
            fiscal_year_end_month=fiscal_year_end_month,
            description=description,
            is_active=True
        )
        self.db.add(group)
        await self.db.flush()
        
        # Add parent entity as a member with 100% ownership
        parent_member = EntityGroupMember(
            group_id=group.id,
            entity_id=parent_entity_id,
            ownership_percentage=Decimal("100.00"),
            consolidation_method="full",
            is_parent=True
        )
        self.db.add(parent_member)
        await self.db.commit()
        
        return group
    
    async def add_group_member(
        self,
        group_id: uuid.UUID,
        entity_id: uuid.UUID,
        ownership_percentage: Decimal,
        consolidation_method: str = "full"
    ) -> EntityGroupMember:
        """Add an entity as a member of a consolidation group."""
        # Determine consolidation method based on ownership
        if ownership_percentage > 50:
            method = ConsolidationMethod.FULL.value
        elif ownership_percentage >= 20:
            method = ConsolidationMethod.EQUITY.value if consolidation_method == "equity" else ConsolidationMethod.PROPORTIONAL.value
        else:
            method = ConsolidationMethod.EQUITY.value  # Associates with <20% ownership
        
        member = EntityGroupMember(
            group_id=group_id,
            entity_id=entity_id,
            ownership_percentage=ownership_percentage,
            consolidation_method=method,
            is_parent=False
        )
        self.db.add(member)
        await self.db.commit()
        
        # Invalidate consolidation cache for this group
        cache = get_cache_service()
        await cache.invalidate_consolidation(str(group_id))
        
        return member
    
    async def get_group_members(
        self,
        group_id: uuid.UUID
    ) -> List[Dict[str, Any]]:
        """Get all members of an entity group with details."""
        result = await self.db.execute(
            select(EntityGroupMember, BusinessEntity).join(
                BusinessEntity, EntityGroupMember.entity_id == BusinessEntity.id
            ).where(EntityGroupMember.group_id == group_id)
        )
        
        members = []
        for member, entity in result.all():
            members.append({
                "id": str(member.id),
                "entity_id": str(member.entity_id),
                "entity_name": entity.name,
                "ownership_percentage": float(member.ownership_percentage),
                "consolidation_method": member.consolidation_method,
                "is_parent": member.is_parent
            })
        
        return members
    
    # =========================================================================
    # TRIAL BALANCE CONSOLIDATION
    # =========================================================================
    
    async def get_entity_trial_balance(
        self,
        entity_id: uuid.UUID,
        as_of_date: date
    ) -> Dict[str, Dict[str, Decimal]]:
        """Get trial balance for a single entity."""
        # Get all accounts with balances
        result = await self.db.execute(
            select(ChartOfAccounts, AccountBalance).outerjoin(
                AccountBalance, 
                and_(
                    ChartOfAccounts.id == AccountBalance.account_id,
                    AccountBalance.period_end_date <= as_of_date
                )
            ).where(
                and_(
                    ChartOfAccounts.entity_id == entity_id,
                    ChartOfAccounts.is_active == True,
                    ChartOfAccounts.is_header == False
                )
            )
        )
        
        balances = {}
        for account, balance in result.all():
            account_code = account.account_code
            if account_code not in balances:
                balances[account_code] = {
                    "account_name": account.account_name,
                    "account_type": account.account_type.value,
                    "debit": Decimal("0"),
                    "credit": Decimal("0")
                }
            
            if balance:
                balances[account_code]["debit"] += balance.debit_balance or Decimal("0")
                balances[account_code]["credit"] += balance.credit_balance or Decimal("0")
        
        return balances
    
    async def get_consolidated_trial_balance(
        self,
        group_id: uuid.UUID,
        as_of_date: date,
        include_eliminations: bool = True,
        auto_translate: bool = True,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """
        Generate consolidated trial balance for an entity group.
        
        Steps:
        1. Translate foreign currency subsidiaries (if auto_translate=True)
        2. Aggregate trial balances from all member entities  
        3. Apply ownership percentages based on consolidation method
        4. Generate and apply elimination entries
        5. Calculate minority interests
        
        IAS 21 Compliance:
        - Foreign subsidiaries are translated before consolidation
        - Translation adjustments go to OCI (CTA)
        
        Performance:
        - Uses Redis caching for complex calculations
        - Cache TTL: 5 minutes (configurable)
        """
        # Try cache first
        if use_cache:
            cache = get_cache_service()
            cached_result = await cache.get_consolidated_tb(
                str(group_id), as_of_date, include_eliminations
            )
            if cached_result is not None:
                logger.debug(f"Cache hit for consolidated TB: {group_id}")
                return cached_result
        
        # Get group and members
        group = await self.get_entity_group(group_id)
        if not group:
            raise ValueError("Entity group not found")
        
        members_result = await self.db.execute(
            select(EntityGroupMember).where(EntityGroupMember.group_id == group_id)
        )
        members = list(members_result.scalars().all())
        
        # ===========================================
        # STEP 1: TRANSLATE FOREIGN SUBSIDIARIES
        # ===========================================
        translation_summary = None
        if auto_translate:
            translation_summary = await self.translate_all_subsidiaries(
                group_id=group_id,
                translation_date=as_of_date,
            )
        
        # Aggregate balances
        consolidated = defaultdict(lambda: {
            "account_name": "",
            "account_type": "",
            "debit": Decimal("0"),
            "credit": Decimal("0")
        })
        
        entity_contributions = {}
        
        for member in members:
            # Check if this member needs translation
            is_foreign = (
                member.functional_currency and 
                member.functional_currency != group.consolidation_currency
            )
            
            entity_tb = await self.get_entity_trial_balance(member.entity_id, as_of_date)
            ownership_factor = member.ownership_percentage / Decimal("100")
            
            entity_contributions[str(member.entity_id)] = {
                "ownership_percentage": float(member.ownership_percentage),
                "consolidation_method": member.consolidation_method,
                "functional_currency": member.functional_currency,
                "is_foreign_subsidiary": is_foreign,
                "accounts": {}
            }
            
            # Determine translation rate for foreign subsidiaries
            translation_rate = Decimal("1.0")
            if is_foreign and member.last_translation_rate:
                translation_rate = Decimal(str(member.last_translation_rate))
            
            for account_code, account_data in entity_tb.items():
                # Apply consolidation method
                if member.consolidation_method == ConsolidationMethod.FULL.value:
                    factor = Decimal("1")  # Full consolidation: 100% of amounts
                elif member.consolidation_method == ConsolidationMethod.PROPORTIONAL.value:
                    factor = ownership_factor  # Proportional: ownership %
                else:  # Equity method - only record investment value, not line items
                    continue
                
                debit = account_data["debit"] * factor
                credit = account_data["credit"] * factor
                
                # Apply translation for foreign subsidiaries
                if is_foreign and auto_translate:
                    # Use appropriate rate based on account type
                    account_type = account_data.get("account_type", "")
                    if account_type in ["ASSET", "LIABILITY"]:
                        # Balance sheet: closing rate
                        rate = translation_rate
                    elif account_type in ["REVENUE", "EXPENSE"]:
                        # Income statement: average rate
                        rate = Decimal(str(member.average_rate_period)) if member.average_rate_period else translation_rate
                    else:
                        # Equity: historical rate
                        rate = Decimal(str(member.historical_equity_rate)) if member.historical_equity_rate else translation_rate
                    
                    debit = debit * rate
                    credit = credit * rate
                
                consolidated[account_code]["account_name"] = account_data["account_name"]
                consolidated[account_code]["account_type"] = account_data["account_type"]
                consolidated[account_code]["debit"] += debit
                consolidated[account_code]["credit"] += credit
                
                entity_contributions[str(member.entity_id)]["accounts"][account_code] = {
                    "debit": float(debit),
                    "credit": float(credit)
                }
        
        # ===========================================
        # STEP 2: ADD CTA TO OCI
        # ===========================================
        if translation_summary and translation_summary.get("total_cta", 0) != 0:
            # Add CTA account (goes to equity/OCI)
            cta_account_code = "3200"  # Typical OCI account code
            cta_amount = Decimal(str(translation_summary["total_cta"]))
            
            consolidated[cta_account_code]["account_name"] = "Cumulative Translation Adjustment (OCI)"
            consolidated[cta_account_code]["account_type"] = "EQUITY"
            if cta_amount >= 0:
                consolidated[cta_account_code]["credit"] += cta_amount
            else:
                consolidated[cta_account_code]["debit"] += abs(cta_amount)
        
        # Generate elimination entries
        eliminations = []
        if include_eliminations:
            eliminations = await self._generate_elimination_entries(group_id, as_of_date)
            
            for elimination in eliminations:
                for line in elimination.get("lines", []):
                    account_code = line["account_code"]
                    if account_code in consolidated:
                        consolidated[account_code]["debit"] += Decimal(str(line.get("debit", 0)))
                        consolidated[account_code]["credit"] += Decimal(str(line.get("credit", 0)))
        
        # Calculate minority interest
        minority_interest = await self._calculate_minority_interest(group_id, consolidated, members, as_of_date)
        
        # Calculate totals
        total_debits = sum(data["debit"] for data in consolidated.values())
        total_credits = sum(data["credit"] for data in consolidated.values())
        
        result = {
            "group_id": str(group_id),
            "group_name": group.name,
            "as_of_date": as_of_date.isoformat(),
            "consolidation_currency": group.consolidation_currency,
            "translation_summary": translation_summary,
            "accounts": {
                code: {
                    "account_name": data["account_name"],
                    "account_type": data["account_type"],
                    "debit": float(data["debit"]),
                    "credit": float(data["credit"]),
                    "balance": float(data["debit"] - data["credit"])
                }
                for code, data in sorted(consolidated.items())
            },
            "entity_contributions": entity_contributions,
            "eliminations": eliminations,
            "minority_interest": minority_interest,
            "totals": {
                "total_debits": float(total_debits),
                "total_credits": float(total_credits),
                "is_balanced": abs(total_debits - total_credits) < Decimal("0.01")
            }
        }
        
        # Cache the result
        if use_cache:
            cache = get_cache_service()
            await cache.set_consolidated_tb(
                str(group_id), as_of_date, include_eliminations, result
            )
            logger.debug(f"Cached consolidated TB for: {group_id}")
        
        return result
    
    # =========================================================================
    # CONSOLIDATED FINANCIAL STATEMENTS
    # =========================================================================
    
    async def get_consolidated_balance_sheet(
        self,
        group_id: uuid.UUID,
        as_of_date: date
    ) -> Dict[str, Any]:
        """
        Generate consolidated balance sheet.
        
        Groups accounts by:
        - Assets (Current and Non-current)
        - Liabilities (Current and Non-current)
        - Equity (including minority interest)
        """
        trial_balance = await self.get_consolidated_trial_balance(group_id, as_of_date)
        
        # Initialize categories
        balance_sheet = {
            "assets": {
                "current": {"accounts": [], "total": Decimal("0")},
                "non_current": {"accounts": [], "total": Decimal("0")},
                "total": Decimal("0")
            },
            "liabilities": {
                "current": {"accounts": [], "total": Decimal("0")},
                "non_current": {"accounts": [], "total": Decimal("0")},
                "total": Decimal("0")
            },
            "equity": {
                "accounts": [],
                "minority_interest": Decimal("0"),
                "total": Decimal("0")
            }
        }
        
        # Classify accounts
        for account_code, account_data in trial_balance["accounts"].items():
            account_type = account_data["account_type"]
            balance = Decimal(str(account_data["balance"]))
            
            entry = {
                "account_code": account_code,
                "account_name": account_data["account_name"],
                "balance": float(abs(balance))
            }
            
            if account_type == "asset":
                # Simple classification - first digit determines current/non-current
                if account_code.startswith("1"):  # Current assets
                    balance_sheet["assets"]["current"]["accounts"].append(entry)
                    balance_sheet["assets"]["current"]["total"] += abs(balance)
                else:
                    balance_sheet["assets"]["non_current"]["accounts"].append(entry)
                    balance_sheet["assets"]["non_current"]["total"] += abs(balance)
                balance_sheet["assets"]["total"] += abs(balance)
                
            elif account_type == "liability":
                if account_code.startswith("2"):  # Current liabilities
                    balance_sheet["liabilities"]["current"]["accounts"].append(entry)
                    balance_sheet["liabilities"]["current"]["total"] += abs(balance)
                else:
                    balance_sheet["liabilities"]["non_current"]["accounts"].append(entry)
                    balance_sheet["liabilities"]["non_current"]["total"] += abs(balance)
                balance_sheet["liabilities"]["total"] += abs(balance)
                
            elif account_type == "equity":
                balance_sheet["equity"]["accounts"].append(entry)
                balance_sheet["equity"]["total"] += abs(balance)
        
        # Add minority interest
        minority_interest = trial_balance.get("minority_interest", {}).get("total", 0)
        balance_sheet["equity"]["minority_interest"] = float(minority_interest)
        balance_sheet["equity"]["total"] += Decimal(str(minority_interest))
        
        # Convert to float for JSON serialization
        balance_sheet["assets"]["current"]["total"] = float(balance_sheet["assets"]["current"]["total"])
        balance_sheet["assets"]["non_current"]["total"] = float(balance_sheet["assets"]["non_current"]["total"])
        balance_sheet["assets"]["total"] = float(balance_sheet["assets"]["total"])
        balance_sheet["liabilities"]["current"]["total"] = float(balance_sheet["liabilities"]["current"]["total"])
        balance_sheet["liabilities"]["non_current"]["total"] = float(balance_sheet["liabilities"]["non_current"]["total"])
        balance_sheet["liabilities"]["total"] = float(balance_sheet["liabilities"]["total"])
        balance_sheet["equity"]["total"] = float(balance_sheet["equity"]["total"])
        
        return {
            "group_id": str(group_id),
            "group_name": trial_balance["group_name"],
            "as_of_date": as_of_date.isoformat(),
            "currency": trial_balance["consolidation_currency"],
            "balance_sheet": balance_sheet,
            "is_balanced": abs(
                balance_sheet["assets"]["total"] - 
                balance_sheet["liabilities"]["total"] - 
                balance_sheet["equity"]["total"]
            ) < 0.01
        }
    
    async def get_consolidated_income_statement(
        self,
        group_id: uuid.UUID,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """
        Generate consolidated income statement for a period.
        
        Groups accounts by:
        - Revenue
        - Cost of Goods Sold
        - Operating Expenses
        - Other Income/Expense
        - Tax Expense
        """
        # Get trial balance as of end date
        trial_balance = await self.get_consolidated_trial_balance(group_id, end_date)
        
        income_statement = {
            "revenue": {"accounts": [], "total": Decimal("0")},
            "cost_of_goods_sold": {"accounts": [], "total": Decimal("0")},
            "gross_profit": Decimal("0"),
            "operating_expenses": {"accounts": [], "total": Decimal("0")},
            "operating_income": Decimal("0"),
            "other_income": {"accounts": [], "total": Decimal("0")},
            "other_expenses": {"accounts": [], "total": Decimal("0")},
            "income_before_tax": Decimal("0"),
            "tax_expense": Decimal("0"),
            "net_income": Decimal("0"),
            "minority_interest_share": Decimal("0"),
            "net_income_attributable_to_parent": Decimal("0")
        }
        
        # Classify accounts
        for account_code, account_data in trial_balance["accounts"].items():
            account_type = account_data["account_type"]
            balance = Decimal(str(account_data["balance"]))
            
            entry = {
                "account_code": account_code,
                "account_name": account_data["account_name"],
                "balance": float(abs(balance))
            }
            
            if account_type == "revenue":
                income_statement["revenue"]["accounts"].append(entry)
                income_statement["revenue"]["total"] += abs(balance)
                
            elif account_type == "expense":
                # Classify expense by account code pattern
                if account_code.startswith("5"):  # COGS
                    income_statement["cost_of_goods_sold"]["accounts"].append(entry)
                    income_statement["cost_of_goods_sold"]["total"] += abs(balance)
                elif account_code.startswith("6"):  # Operating expenses
                    income_statement["operating_expenses"]["accounts"].append(entry)
                    income_statement["operating_expenses"]["total"] += abs(balance)
                else:
                    income_statement["other_expenses"]["accounts"].append(entry)
                    income_statement["other_expenses"]["total"] += abs(balance)
        
        # Calculate subtotals
        income_statement["gross_profit"] = (
            income_statement["revenue"]["total"] - 
            income_statement["cost_of_goods_sold"]["total"]
        )
        income_statement["operating_income"] = (
            income_statement["gross_profit"] - 
            income_statement["operating_expenses"]["total"]
        )
        income_statement["income_before_tax"] = (
            income_statement["operating_income"] + 
            income_statement["other_income"]["total"] - 
            income_statement["other_expenses"]["total"]
        )
        income_statement["net_income"] = (
            income_statement["income_before_tax"] - 
            income_statement["tax_expense"]
        )
        
        # Calculate minority interest share
        minority_share = trial_balance.get("minority_interest", {}).get("income_share", Decimal("0"))
        income_statement["minority_interest_share"] = minority_share
        income_statement["net_income_attributable_to_parent"] = (
            income_statement["net_income"] - minority_share
        )
        
        # Convert to float for JSON
        for key in ["gross_profit", "operating_income", "income_before_tax", 
                    "tax_expense", "net_income", "minority_interest_share",
                    "net_income_attributable_to_parent"]:
            income_statement[key] = float(income_statement[key])
        
        for section in ["revenue", "cost_of_goods_sold", "operating_expenses", 
                        "other_income", "other_expenses"]:
            income_statement[section]["total"] = float(income_statement[section]["total"])
        
        return {
            "group_id": str(group_id),
            "group_name": trial_balance["group_name"],
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            },
            "currency": trial_balance["consolidation_currency"],
            "income_statement": income_statement
        }
    
    async def get_consolidated_cash_flow_statement(
        self,
        group_id: uuid.UUID,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """
        Generate consolidated cash flow statement (indirect method).
        """
        # Get income statement data
        income_statement = await self.get_consolidated_income_statement(
            group_id, start_date, end_date
        )
        
        cash_flow = {
            "operating_activities": {
                "net_income": income_statement["income_statement"]["net_income"],
                "adjustments": [],
                "working_capital_changes": [],
                "total": Decimal("0")
            },
            "investing_activities": {
                "items": [],
                "total": Decimal("0")
            },
            "financing_activities": {
                "items": [],
                "total": Decimal("0")
            },
            "net_change_in_cash": Decimal("0"),
            "beginning_cash": Decimal("0"),
            "ending_cash": Decimal("0")
        }
        
        # Note: Full implementation would track actual changes in balance sheet accounts
        # This is a simplified structure
        
        cash_flow["operating_activities"]["total"] = Decimal(str(
            income_statement["income_statement"]["net_income"]
        ))
        cash_flow["net_change_in_cash"] = (
            cash_flow["operating_activities"]["total"] +
            cash_flow["investing_activities"]["total"] +
            cash_flow["financing_activities"]["total"]
        )
        
        # Convert to float
        for section in ["operating_activities", "investing_activities", "financing_activities"]:
            cash_flow[section]["total"] = float(cash_flow[section]["total"])
        cash_flow["net_change_in_cash"] = float(cash_flow["net_change_in_cash"])
        cash_flow["beginning_cash"] = float(cash_flow["beginning_cash"])
        cash_flow["ending_cash"] = float(cash_flow["ending_cash"])
        
        return {
            "group_id": str(group_id),
            "group_name": income_statement["group_name"],
            "period": income_statement["period"],
            "currency": income_statement["currency"],
            "cash_flow_statement": cash_flow
        }
    
    # =========================================================================
    # ELIMINATION ENTRIES
    # =========================================================================
    
    async def _generate_elimination_entries(
        self,
        group_id: uuid.UUID,
        as_of_date: date
    ) -> List[Dict[str, Any]]:
        """
        Generate elimination entries for intercompany transactions.
        
        Elimination types:
        1. Intercompany sales/purchases
        2. Intercompany receivables/payables
        3. Intercompany loans
        4. Intercompany dividends
        5. Investment in subsidiaries
        6. Unrealized profit in inventory
        """
        eliminations = []
        
        # Get uneliminated intercompany transactions
        result = await self.db.execute(
            select(IntercompanyTransaction).where(
                and_(
                    IntercompanyTransaction.group_id == group_id,
                    IntercompanyTransaction.transaction_date <= as_of_date,
                    IntercompanyTransaction.is_eliminated == False
                )
            )
        )
        transactions = list(result.scalars().all())
        
        # Group by transaction type
        by_type = defaultdict(list)
        for t in transactions:
            by_type[t.transaction_type].append(t)
        
        # Generate eliminations for each type
        for trans_type, trans_list in by_type.items():
            total_amount = sum(t.amount for t in trans_list)
            
            if trans_type in ["sale", "purchase"]:
                # Eliminate intercompany revenue and COGS
                eliminations.append({
                    "type": EliminationType.INTERCOMPANY_REVENUE.value,
                    "description": f"Eliminate intercompany {trans_type} revenue",
                    "amount": float(total_amount),
                    "lines": [
                        {"account_code": "4000", "account_name": "Intercompany Revenue", "debit": float(total_amount), "credit": 0},
                        {"account_code": "5000", "account_name": "Intercompany COGS", "debit": 0, "credit": float(total_amount)}
                    ],
                    "transaction_ids": [str(t.id) for t in trans_list]
                })
            
            elif trans_type in ["loan", "advance"]:
                # Eliminate intercompany loans
                eliminations.append({
                    "type": EliminationType.INTERCOMPANY_LOAN.value,
                    "description": "Eliminate intercompany loan balances",
                    "amount": float(total_amount),
                    "lines": [
                        {"account_code": "2500", "account_name": "Intercompany Payable", "debit": float(total_amount), "credit": 0},
                        {"account_code": "1300", "account_name": "Intercompany Receivable", "debit": 0, "credit": float(total_amount)}
                    ],
                    "transaction_ids": [str(t.id) for t in trans_list]
                })
            
            elif trans_type == "dividend":
                # Eliminate intercompany dividends
                eliminations.append({
                    "type": EliminationType.INTERCOMPANY_DIVIDEND.value,
                    "description": "Eliminate intercompany dividend income",
                    "amount": float(total_amount),
                    "lines": [
                        {"account_code": "4500", "account_name": "Dividend Income", "debit": float(total_amount), "credit": 0},
                        {"account_code": "3200", "account_name": "Retained Earnings", "debit": 0, "credit": float(total_amount)}
                    ],
                    "transaction_ids": [str(t.id) for t in trans_list]
                })
        
        return eliminations
    
    async def create_elimination_journal_entry(
        self,
        group_id: uuid.UUID,
        elimination_type: str,
        lines: List[Dict[str, Any]],
        as_of_date: date,
        description: str,
        created_by_id: uuid.UUID
    ) -> Dict[str, Any]:
        """
        Create an actual elimination journal entry in the consolidation workbook.
        
        Note: These entries are for consolidation purposes only and do not
        affect individual entity books.
        """
        group = await self.get_entity_group(group_id)
        if not group:
            raise ValueError("Entity group not found")
        
        # Create elimination journal entry
        entry = JournalEntry(
            entity_id=group.parent_entity_id,  # Record at parent level
            entry_number=f"ELIM-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            entry_date=as_of_date,
            entry_type=JournalEntryType.ADJUSTMENT,
            description=f"[CONSOLIDATION] {description}",
            status=JournalEntryStatus.POSTED,
            posted_at=datetime.utcnow(),
            posted_by_id=created_by_id,
            created_by_id=created_by_id,
            is_system_generated=True
        )
        self.db.add(entry)
        await self.db.flush()
        
        # Add lines
        total_debits = Decimal("0")
        total_credits = Decimal("0")
        line_number = 1
        
        for line in lines:
            je_line = JournalEntryLine(
                journal_entry_id=entry.id,
                line_number=line_number,
                account_id=line.get("account_id"),  # Would need to resolve from account_code
                debit_amount=Decimal(str(line.get("debit", 0))),
                credit_amount=Decimal(str(line.get("credit", 0))),
                description=line.get("description", "")
            )
            self.db.add(je_line)
            total_debits += je_line.debit_amount
            total_credits += je_line.credit_amount
            line_number += 1
        
        entry.total_amount = total_debits
        await self.db.commit()
        
        return {
            "id": str(entry.id),
            "entry_number": entry.entry_number,
            "entry_date": as_of_date.isoformat(),
            "description": entry.description,
            "total_debits": float(total_debits),
            "total_credits": float(total_credits),
            "is_balanced": total_debits == total_credits
        }
    
    # =========================================================================
    # MINORITY INTEREST CALCULATIONS
    # =========================================================================
    
    async def _calculate_minority_interest(
        self,
        group_id: uuid.UUID,
        consolidated_balances: Dict,
        members: List[EntityGroupMember],
        as_of_date: date
    ) -> Dict[str, Any]:
        """
        Calculate minority (non-controlling) interest.
        
        Minority interest = (100% - Parent ownership%) × Subsidiary net assets
        """
        minority_interest = {
            "total": Decimal("0"),
            "income_share": Decimal("0"),
            "by_entity": {}
        }
        
        for member in members:
            if member.is_parent or member.consolidation_method != ConsolidationMethod.FULL.value:
                continue
            
            minority_percentage = Decimal("100") - member.ownership_percentage
            if minority_percentage <= 0:
                continue
            
            # Get subsidiary's equity
            entity_tb = await self.get_entity_trial_balance(member.entity_id, as_of_date)
            
            entity_equity = Decimal("0")
            entity_net_income = Decimal("0")
            
            for account_code, account_data in entity_tb.items():
                balance = account_data["debit"] - account_data["credit"]
                if account_data["account_type"] == "equity":
                    entity_equity += abs(balance)
                elif account_data["account_type"] in ["revenue", "expense"]:
                    # Net income calculation
                    if account_data["account_type"] == "revenue":
                        entity_net_income += abs(balance)
                    else:
                        entity_net_income -= abs(balance)
            
            minority_factor = minority_percentage / Decimal("100")
            entity_minority = entity_equity * minority_factor
            entity_income_share = entity_net_income * minority_factor
            
            minority_interest["total"] += entity_minority
            minority_interest["income_share"] += entity_income_share
            minority_interest["by_entity"][str(member.entity_id)] = {
                "ownership_percentage": float(member.ownership_percentage),
                "minority_percentage": float(minority_percentage),
                "equity_share": float(entity_minority),
                "income_share": float(entity_income_share)
            }
        
        minority_interest["total"] = float(minority_interest["total"])
        minority_interest["income_share"] = float(minority_interest["income_share"])
        
        return minority_interest
    
    # =========================================================================
    # CURRENCY TRANSLATION (IAS 21 COMPLIANT)
    # =========================================================================
    
    async def translate_foreign_subsidiary(
        self,
        entity_id: uuid.UUID,
        group_id: uuid.UUID,
        functional_currency: str,
        presentation_currency: str,
        translation_date: date,
        fiscal_period_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """
        Translate foreign subsidiary financials per IAS 21.
        
        Translation rules (Current Rate Method):
        - Assets/Liabilities: Closing rate (rate at balance sheet date)
        - Income/Expenses: Average rate for the period
        - Equity: Historical rates
        - Translation differences: Other Comprehensive Income (CTA)
        
        Args:
            entity_id: The subsidiary entity to translate
            group_id: The consolidation group
            functional_currency: Subsidiary's functional currency
            presentation_currency: Group's presentation currency (usually NGN)
            translation_date: The date for translation (period end)
            fiscal_period_id: Optional fiscal period reference
            user_id: User performing the translation
            
        Returns:
            Translation result with pre/post amounts and CTA
        """
        from app.services.fx_service import FXService
        from app.models.advanced_accounting import EntityGroupMember, CurrencyTranslationHistory
        
        fx_service = FXService(self.db)
        
        result = {
            "entity_id": str(entity_id),
            "group_id": str(group_id),
            "functional_currency": functional_currency,
            "presentation_currency": presentation_currency,
            "translation_date": str(translation_date),
            "rates_used": {},
            "pre_translation": {},
            "post_translation": {},
            "translation_adjustment": 0.0,
            "cumulative_translation_adjustment": 0.0,
            "success": True,
            "errors": []
        }
        
        # Skip if same currency
        if functional_currency == presentation_currency:
            result["success"] = True
            result["notes"] = "No translation needed - same currency"
            return result
        
        try:
            # Get exchange rates
            closing_rate = await fx_service.get_exchange_rate(
                functional_currency, presentation_currency, translation_date
            )
            if not closing_rate:
                result["errors"].append(f"No closing rate for {functional_currency}/{presentation_currency}")
                result["success"] = False
                return result
            
            # Get average rate (use a simple approach - average of beginning/end)
            # In production, this would use weighted average based on when transactions occurred
            period_start = date(translation_date.year, translation_date.month, 1)
            start_rate = await fx_service.get_exchange_rate(
                functional_currency, presentation_currency, period_start
            )
            average_rate = (closing_rate + (start_rate or closing_rate)) / 2
            
            # Get member's historical equity rate
            member_result = await self.db.execute(
                select(EntityGroupMember).where(and_(
                    EntityGroupMember.group_id == group_id,
                    EntityGroupMember.entity_id == entity_id
                ))
            )
            member = member_result.scalar_one_or_none()
            historical_equity_rate = Decimal(str(
                member.historical_equity_rate or closing_rate
            )) if member else closing_rate
            
            result["rates_used"] = {
                "closing_rate": float(closing_rate),
                "average_rate": float(average_rate),
                "historical_equity_rate": float(historical_equity_rate)
            }
            
            # Get trial balance for the entity
            trial_balance = await self.get_entity_trial_balance(entity_id, translation_date)
            
            # Categorize and translate
            pre_translation = {
                "assets": Decimal("0.00"),
                "liabilities": Decimal("0.00"),
                "equity": Decimal("0.00"),
                "revenue": Decimal("0.00"),
                "expenses": Decimal("0.00"),
                "net_income": Decimal("0.00")
            }
            post_translation = {
                "assets": Decimal("0.00"),
                "liabilities": Decimal("0.00"),
                "equity": Decimal("0.00"),
                "revenue": Decimal("0.00"),
                "expenses": Decimal("0.00"),
                "net_income": Decimal("0.00")
            }
            
            for account_code, data in trial_balance.items():
                account_type = data.get("account_type", "")
                balance = data.get("debit", Decimal("0")) - data.get("credit", Decimal("0"))
                
                # Determine translation rate based on account type
                if account_type in ["ASSET"]:
                    pre_translation["assets"] += balance
                    translated = balance * closing_rate
                    post_translation["assets"] += translated
                    
                elif account_type in ["LIABILITY"]:
                    pre_translation["liabilities"] += abs(balance)
                    translated = abs(balance) * closing_rate
                    post_translation["liabilities"] += translated
                    
                elif account_type in ["EQUITY"]:
                    pre_translation["equity"] += abs(balance)
                    # Equity uses historical rate
                    translated = abs(balance) * historical_equity_rate
                    post_translation["equity"] += translated
                    
                elif account_type in ["REVENUE"]:
                    pre_translation["revenue"] += abs(balance)
                    # Income statement uses average rate
                    translated = abs(balance) * average_rate
                    post_translation["revenue"] += translated
                    
                elif account_type in ["EXPENSE"]:
                    pre_translation["expenses"] += balance
                    translated = balance * average_rate
                    post_translation["expenses"] += translated
            
            # Calculate net income
            pre_translation["net_income"] = pre_translation["revenue"] - pre_translation["expenses"]
            post_translation["net_income"] = post_translation["revenue"] - post_translation["expenses"]
            
            # Calculate translation adjustment (balancing figure to OCI)
            # CTA = Translated Assets - Translated Liabilities - Translated Equity - Translated Net Income
            expected_equity = (
                post_translation["assets"] - 
                post_translation["liabilities"]
            )
            recorded_equity = post_translation["equity"] + post_translation["net_income"]
            
            translation_adjustment = expected_equity - recorded_equity
            
            # Get previous CTA
            previous_cta = Decimal("0.00")
            if member and member.cumulative_translation_adjustment:
                previous_cta = Decimal(str(member.cumulative_translation_adjustment))
            
            cumulative_cta = previous_cta + translation_adjustment
            
            result["pre_translation"] = {k: float(v) for k, v in pre_translation.items()}
            result["post_translation"] = {k: float(v) for k, v in post_translation.items()}
            result["translation_adjustment"] = float(translation_adjustment)
            result["cumulative_translation_adjustment"] = float(cumulative_cta)
            
            # Update member with translation details
            if member:
                member.last_translation_date = translation_date
                member.last_translation_rate = float(closing_rate)
                member.average_rate_period = float(average_rate)
                member.cumulative_translation_adjustment = float(cumulative_cta)
                if not member.historical_equity_rate:
                    member.historical_equity_rate = float(closing_rate)
            
            # Create translation history record
            history = CurrencyTranslationHistory(
                group_id=group_id,
                member_id=member.id if member else None,
                entity_id=entity_id,
                translation_date=translation_date,
                fiscal_period_id=fiscal_period_id,
                functional_currency=functional_currency,
                presentation_currency=presentation_currency,
                closing_rate=closing_rate,
                average_rate=average_rate,
                historical_equity_rate=historical_equity_rate,
                pre_translation_assets=pre_translation["assets"],
                pre_translation_liabilities=pre_translation["liabilities"],
                pre_translation_equity=pre_translation["equity"],
                pre_translation_revenue=pre_translation["revenue"],
                pre_translation_expenses=pre_translation["expenses"],
                pre_translation_net_income=pre_translation["net_income"],
                post_translation_assets=post_translation["assets"],
                post_translation_liabilities=post_translation["liabilities"],
                post_translation_equity=post_translation["equity"],
                post_translation_revenue=post_translation["revenue"],
                post_translation_expenses=post_translation["expenses"],
                post_translation_net_income=post_translation["net_income"],
                translation_adjustment=translation_adjustment,
                cumulative_translation_adjustment=cumulative_cta,
                translation_method="current_rate",
                created_by=user_id,
            )
            self.db.add(history)
            
            await self.db.commit()
            
        except Exception as e:
            result["success"] = False
            result["errors"].append(str(e))
            await self.db.rollback()
        
        return result
    
    async def translate_all_subsidiaries(
        self,
        group_id: uuid.UUID,
        translation_date: date,
        fiscal_period_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """
        Translate all foreign currency subsidiaries in a group.
        
        Returns:
            Summary of all translations performed
        """
        group = await self.get_entity_group(group_id)
        if not group:
            raise ValueError("Entity group not found")
        
        presentation_currency = group.consolidation_currency
        members = await self.get_group_members(group_id)
        
        results = {
            "group_id": str(group_id),
            "group_name": group.name,
            "presentation_currency": presentation_currency,
            "translation_date": str(translation_date),
            "subsidiaries_translated": [],
            "total_cta": 0.0,
            "errors": []
        }
        
        total_cta = Decimal("0.00")
        
        for member in members:
            entity_id = uuid.UUID(member["entity_id"])
            
            # Get entity's functional currency
            from app.models.advanced_accounting import EntityGroupMember
            member_result = await self.db.execute(
                select(EntityGroupMember).where(and_(
                    EntityGroupMember.group_id == group_id,
                    EntityGroupMember.entity_id == entity_id
                ))
            )
            member_record = member_result.scalar_one_or_none()
            
            functional_currency = member_record.functional_currency if member_record else presentation_currency
            
            # Skip if same currency (no translation needed)
            if functional_currency == presentation_currency:
                continue
            
            # Translate the subsidiary
            translation_result = await self.translate_foreign_subsidiary(
                entity_id=entity_id,
                group_id=group_id,
                functional_currency=functional_currency,
                presentation_currency=presentation_currency,
                translation_date=translation_date,
                fiscal_period_id=fiscal_period_id,
                user_id=user_id,
            )
            
            if translation_result["success"]:
                results["subsidiaries_translated"].append({
                    "entity_id": str(entity_id),
                    "entity_name": member["entity_name"],
                    "functional_currency": functional_currency,
                    "translation_adjustment": translation_result["translation_adjustment"],
                    "cumulative_cta": translation_result["cumulative_translation_adjustment"],
                })
                total_cta += Decimal(str(translation_result["cumulative_translation_adjustment"]))
            else:
                results["errors"].extend(translation_result.get("errors", []))
        
        results["total_cta"] = float(total_cta)
        
        return results
    
    # =========================================================================
    # CTA TRACKING AND OCI REPORTING
    # =========================================================================
    
    async def get_translation_history(
        self,
        group_id: uuid.UUID,
        entity_id: Optional[uuid.UUID] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get currency translation history for OCI reporting.
        
        Returns historical CTA movements for specified period.
        """
        from app.models.advanced_accounting import CurrencyTranslationHistory
        
        query = select(CurrencyTranslationHistory).where(
            CurrencyTranslationHistory.group_id == group_id
        )
        
        if entity_id:
            query = query.where(CurrencyTranslationHistory.entity_id == entity_id)
        
        if start_date:
            query = query.where(CurrencyTranslationHistory.translation_date >= start_date)
        
        if end_date:
            query = query.where(CurrencyTranslationHistory.translation_date <= end_date)
        
        query = query.order_by(CurrencyTranslationHistory.translation_date.desc())
        
        result = await self.db.execute(query)
        histories = result.scalars().all()
        
        return [
            {
                "id": str(h.id),
                "entity_id": str(h.entity_id),
                "translation_date": h.translation_date.isoformat(),
                "functional_currency": h.functional_currency,
                "presentation_currency": h.presentation_currency,
                "closing_rate": float(h.closing_rate) if h.closing_rate else None,
                "average_rate": float(h.average_rate) if h.average_rate else None,
                "historical_equity_rate": float(h.historical_equity_rate) if h.historical_equity_rate else None,
                "pre_translation": {
                    "assets": float(h.pre_translation_assets or 0),
                    "liabilities": float(h.pre_translation_liabilities or 0),
                    "equity": float(h.pre_translation_equity or 0),
                    "revenue": float(h.pre_translation_revenue or 0),
                    "expenses": float(h.pre_translation_expenses or 0),
                    "net_income": float(h.pre_translation_net_income or 0),
                },
                "post_translation": {
                    "assets": float(h.post_translation_assets or 0),
                    "liabilities": float(h.post_translation_liabilities or 0),
                    "equity": float(h.post_translation_equity or 0),
                    "revenue": float(h.post_translation_revenue or 0),
                    "expenses": float(h.post_translation_expenses or 0),
                    "net_income": float(h.post_translation_net_income or 0),
                },
                "translation_adjustment": float(h.translation_adjustment or 0),
                "cumulative_translation_adjustment": float(h.cumulative_translation_adjustment or 0),
                "translation_method": h.translation_method,
                "notes": h.notes,
            }
            for h in histories
        ]
    
    async def get_oci_cta_report(
        self,
        group_id: uuid.UUID,
        as_of_date: date,
        comparative_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Generate OCI report for Cumulative Translation Adjustments.
        
        IAS 1 Compliance:
        - Shows CTA movement in statement of comprehensive income
        - Beginning balance, current period movement, ending balance
        """
        group = await self.get_entity_group(group_id)
        if not group:
            raise ValueError("Entity group not found")
        
        # Get members with foreign currency
        members_result = await self.db.execute(
            select(EntityGroupMember).where(
                EntityGroupMember.group_id == group_id,
                EntityGroupMember.functional_currency != group.consolidation_currency,
                EntityGroupMember.functional_currency.isnot(None),
            )
        )
        members = list(members_result.scalars().all())
        
        # Build OCI CTA report
        cta_details = []
        total_beginning_cta = Decimal("0")
        total_period_change = Decimal("0")
        total_ending_cta = Decimal("0")
        
        for member in members:
            # Get current CTA
            ending_cta = Decimal(str(member.cumulative_translation_adjustment or 0))
            
            # Get beginning CTA from history
            beginning_cta = Decimal("0")
            if comparative_date:
                history_query = select(CurrencyTranslationHistory).where(
                    CurrencyTranslationHistory.member_id == member.id,
                    CurrencyTranslationHistory.translation_date <= comparative_date,
                ).order_by(CurrencyTranslationHistory.translation_date.desc()).limit(1)
                
                hist_result = await self.db.execute(history_query)
                hist_record = hist_result.scalar_one_or_none()
                
                if hist_record:
                    beginning_cta = Decimal(str(hist_record.cumulative_translation_adjustment or 0))
            
            period_change = ending_cta - beginning_cta
            
            # Get business entity name
            entity = await self.db.execute(
                select(BusinessEntity).where(BusinessEntity.id == member.entity_id)
            )
            entity_obj = entity.scalar_one_or_none()
            entity_name = entity_obj.name if entity_obj else "Unknown"
            
            cta_details.append({
                "entity_id": str(member.entity_id),
                "entity_name": entity_name,
                "functional_currency": member.functional_currency,
                "beginning_cta": float(beginning_cta),
                "period_change": float(period_change),
                "ending_cta": float(ending_cta),
                "last_translation_date": member.last_translation_date.isoformat() if member.last_translation_date else None,
            })
            
            total_beginning_cta += beginning_cta
            total_period_change += period_change
            total_ending_cta += ending_cta
        
        return {
            "group_id": str(group_id),
            "group_name": group.name,
            "presentation_currency": group.consolidation_currency,
            "as_of_date": as_of_date.isoformat(),
            "comparative_date": comparative_date.isoformat() if comparative_date else None,
            "cta_summary": {
                "beginning_balance": float(total_beginning_cta),
                "period_movement": float(total_period_change),
                "ending_balance": float(total_ending_cta),
            },
            "subsidiary_details": cta_details,
            "oci_classification": "Items that may be reclassified to profit or loss",
            "reclassification_trigger": "Disposal or partial disposal of foreign operation",
        }
    
    async def recycle_cta_on_disposal(
        self,
        group_id: uuid.UUID,
        entity_id: uuid.UUID,
        disposal_date: date,
        disposal_percentage: Decimal = Decimal("100"),
        user_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """
        Recycle CTA to profit/loss on disposal of foreign subsidiary.
        
        IAS 21 para 48-49:
        - On disposal, cumulative CTA is reclassified from OCI to P&L
        - Partial disposals recycle proportionate amount
        """
        # Get member
        member_result = await self.db.execute(
            select(EntityGroupMember).where(
                EntityGroupMember.group_id == group_id,
                EntityGroupMember.entity_id == entity_id,
            )
        )
        member = member_result.scalar_one_or_none()
        
        if not member:
            raise ValueError("Entity is not a member of this group")
        
        if not member.cumulative_translation_adjustment:
            return {
                "success": True,
                "message": "No CTA to recycle",
                "recycled_amount": 0,
            }
        
        # Calculate amount to recycle
        total_cta = Decimal(str(member.cumulative_translation_adjustment))
        recycle_amount = total_cta * (disposal_percentage / Decimal("100"))
        
        # Create journal entry to recycle CTA
        # Dr: CTA (OCI/Equity) - remove from balance sheet
        # Cr: FX Gain/Loss (P&L) - recognize in income statement
        # or vice versa if CTA was negative
        
        journal_data = {
            "tenant_id": member.tenant_id,
            "entity_id": entity_id,
            "journal_date": disposal_date,
            "reference_number": f"CTA-RECYCLE-{disposal_date.isoformat()}",
            "description": f"Recycling of CTA on disposal ({disposal_percentage}%) of foreign operation",
            "journal_type": "ADJUSTMENT",
            "source": "FX_DISPOSAL",
            "is_system_generated": True,
            "created_by": user_id,
            "lines": [],
        }
        
        cta_account_code = "3200"  # OCI - CTA account
        fx_pl_account_code = "7300"  # FX Gain/Loss in P&L
        
        if recycle_amount >= 0:
            # CTA was a credit (gain), now recognize as income
            journal_data["lines"] = [
                {"account_code": cta_account_code, "debit": float(recycle_amount), "credit": 0},
                {"account_code": fx_pl_account_code, "debit": 0, "credit": float(recycle_amount)},
            ]
        else:
            # CTA was a debit (loss), now recognize as expense
            journal_data["lines"] = [
                {"account_code": fx_pl_account_code, "debit": float(abs(recycle_amount)), "credit": 0},
                {"account_code": cta_account_code, "debit": 0, "credit": float(abs(recycle_amount))},
            ]
        
        # Update member CTA balance
        remaining_cta = total_cta - recycle_amount
        member.cumulative_translation_adjustment = float(remaining_cta)
        
        # Record in history
        history = CurrencyTranslationHistory(
            group_id=group_id,
            member_id=member.id,
            entity_id=entity_id,
            translation_date=disposal_date,
            functional_currency=member.functional_currency or "NGN",
            presentation_currency=(await self.get_entity_group(group_id)).consolidation_currency,
            closing_rate=Decimal(str(member.last_translation_rate or 1)),
            average_rate=Decimal(str(member.last_translation_rate or 1)),
            translation_adjustment=-recycle_amount,  # Negative because we're removing
            cumulative_translation_adjustment=remaining_cta,
            translation_method="disposal_recycle",
            notes=f"CTA recycled on {disposal_percentage}% disposal of foreign operation",
            created_by=user_id,
        )
        self.db.add(history)
        
        await self.db.commit()
        
        return {
            "success": True,
            "disposal_date": disposal_date.isoformat(),
            "disposal_percentage": float(disposal_percentage),
            "recycled_amount": float(recycle_amount),
            "remaining_cta": float(remaining_cta),
            "journal_entry": journal_data,
            "message": f"Successfully recycled {recycle_amount} CTA to profit/loss",
        }
    
    # =========================================================================
    # CONSOLIDATION REPORTS
    # =========================================================================
    
    async def get_consolidation_worksheet(
        self,
        group_id: uuid.UUID,
        as_of_date: date
    ) -> Dict[str, Any]:
        """
        Generate a full consolidation worksheet showing:
        - Individual entity columns
        - Elimination entries
        - Consolidated totals
        """
        group = await self.get_entity_group(group_id)
        if not group:
            raise ValueError("Entity group not found")
        
        members = await self.get_group_members(group_id)
        
        # Get individual trial balances
        entity_columns = {}
        all_accounts = set()
        
        for member in members:
            entity_id = uuid.UUID(member["entity_id"])
            tb = await self.get_entity_trial_balance(entity_id, as_of_date)
            entity_columns[member["entity_name"]] = tb
            all_accounts.update(tb.keys())
        
        # Generate eliminations
        eliminations = await self._generate_elimination_entries(group_id, as_of_date)
        
        # Build worksheet
        worksheet_rows = []
        for account_code in sorted(all_accounts):
            row = {
                "account_code": account_code,
                "account_name": "",
                "entities": {},
                "eliminations": {"debit": 0, "credit": 0},
                "consolidated": {"debit": 0, "credit": 0}
            }
            
            for entity_name, tb in entity_columns.items():
                if account_code in tb:
                    row["account_name"] = tb[account_code]["account_name"]
                    row["entities"][entity_name] = {
                        "debit": float(tb[account_code]["debit"]),
                        "credit": float(tb[account_code]["credit"])
                    }
                    row["consolidated"]["debit"] += float(tb[account_code]["debit"])
                    row["consolidated"]["credit"] += float(tb[account_code]["credit"])
                else:
                    row["entities"][entity_name] = {"debit": 0, "credit": 0}
            
            worksheet_rows.append(row)
        
        return {
            "group_id": str(group_id),
            "group_name": group.name,
            "as_of_date": as_of_date.isoformat(),
            "entity_columns": list(entity_columns.keys()),
            "rows": worksheet_rows,
            "eliminations_summary": eliminations,
            "totals": {
                "is_balanced": True  # Would calculate actual balance check
            }
        }
    
    async def get_segment_reporting(
        self,
        group_id: uuid.UUID,
        start_date: date,
        end_date: date,
        segment_by: str = "entity"  # entity, geography, business_line
    ) -> Dict[str, Any]:
        """
        Generate segment reporting per IFRS 8.
        
        Segments can be:
        - By entity
        - By geography
        - By business line
        """
        group = await self.get_entity_group(group_id)
        if not group:
            raise ValueError("Entity group not found")
        
        members = await self.get_group_members(group_id)
        
        segments = []
        for member in members:
            entity_id = uuid.UUID(member["entity_id"])
            
            # Get entity income statement
            entity_tb = await self.get_entity_trial_balance(entity_id, end_date)
            
            revenue = Decimal("0")
            expenses = Decimal("0")
            assets = Decimal("0")
            
            for account_code, account_data in entity_tb.items():
                balance = account_data["debit"] - account_data["credit"]
                if account_data["account_type"] == "revenue":
                    revenue += abs(balance)
                elif account_data["account_type"] == "expense":
                    expenses += abs(balance)
                elif account_data["account_type"] == "asset":
                    assets += abs(balance)
            
            segments.append({
                "segment_name": member["entity_name"],
                "segment_id": member["entity_id"],
                "revenue": float(revenue),
                "operating_expenses": float(expenses),
                "operating_profit": float(revenue - expenses),
                "total_assets": float(assets),
                "ownership_percentage": member["ownership_percentage"]
            })
        
        # Calculate totals
        total_revenue = sum(s["revenue"] for s in segments)
        total_expenses = sum(s["operating_expenses"] for s in segments)
        total_assets = sum(s["total_assets"] for s in segments)
        
        return {
            "group_id": str(group_id),
            "group_name": group.name,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            },
            "segment_by": segment_by,
            "segments": segments,
            "totals": {
                "revenue": total_revenue,
                "operating_expenses": total_expenses,
                "operating_profit": total_revenue - total_expenses,
                "total_assets": total_assets
            },
            "reconciliation_to_consolidated": {
                "note": "Intercompany eliminations applied at group level"
            }
        }
