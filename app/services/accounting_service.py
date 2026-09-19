"""
Tekvwa Pro Audit - Accounting Service

Service layer for Chart of Accounts and General Ledger operations.
This is the core accounting engine that handles:
- Chart of Accounts management
- Journal entry creation, posting, and reversal
- Fiscal period management
- GL integration with other modules
- Financial reporting
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Tuple, Dict, Any

from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.accounting import (
    ChartOfAccounts, AccountType, AccountSubType, NormalBalance,
    FiscalYear, FiscalPeriod, FiscalPeriodStatus,
    JournalEntry, JournalEntryLine, JournalEntryStatus, JournalEntryType,
    AccountBalance, RecurringJournalEntry, GLIntegrationLog,
)
from app.schemas.accounting import (
    ChartOfAccountsCreate, ChartOfAccountsUpdate, ChartOfAccountsResponse,
    FiscalYearCreate, FiscalPeriodCreate, FiscalPeriodUpdate,
    JournalEntryCreate, JournalEntryUpdate, JournalEntryLineCreate,
    TrialBalanceReport, TrialBalanceItem,
    IncomeStatementReport, IncomeStatementItem,
    BalanceSheetReport, BalanceSheetItem,
    CashFlowStatementReport, CashFlowItem, CashFlowCategory,
    AccountLedgerReport, AccountLedgerEntry,
    GLPostingRequest, GLPostingResponse,
    PeriodCloseChecklist, PeriodCloseRequest, PeriodCloseResponse,
    FixedAssetSummaryItem, FixedAssetCategorySummary, FixedAssetRegisterSummary,
    GLFixedAssetValidation, EnhancedBalanceSheetReport,
    InventorySummaryForGL, ARAgingSummary, APAgingSummary,
    PayrollSummaryForGL, BankAccountSummaryForGL, ExpenseClaimSummaryForGL,
    GLSourceSystemSummary, GLAccountReconciliation,
)


class AccountingService:
    """Service for accounting operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # =========================================================================
    # CHART OF ACCOUNTS
    # =========================================================================
    
    async def get_chart_of_accounts(
        self,
        entity_id: uuid.UUID,
        account_type: Optional[AccountType] = None,
        is_active: bool = True,
        include_headers: bool = True,
    ) -> List[ChartOfAccounts]:
        """Get chart of accounts for an entity."""
        query = select(ChartOfAccounts).where(
            ChartOfAccounts.entity_id == entity_id
        )
        
        if account_type:
            query = query.where(ChartOfAccounts.account_type == account_type)
        
        if not include_headers:
            query = query.where(ChartOfAccounts.is_header == False)
        
        query = query.where(ChartOfAccounts.is_active == is_active)
        query = query.order_by(ChartOfAccounts.account_code)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_account_by_id(
        self,
        account_id: uuid.UUID,
    ) -> Optional[ChartOfAccounts]:
        """Get account by ID."""
        result = await self.db.execute(
            select(ChartOfAccounts).where(ChartOfAccounts.id == account_id)
        )
        return result.scalar_one_or_none()
    
    async def get_account_by_code(
        self,
        entity_id: uuid.UUID,
        account_code: str,
    ) -> Optional[ChartOfAccounts]:
        """Get account by code."""
        result = await self.db.execute(
            select(ChartOfAccounts).where(
                and_(
                    ChartOfAccounts.entity_id == entity_id,
                    ChartOfAccounts.account_code == account_code,
                )
            )
        )
        return result.scalar_one_or_none()
    
    async def create_account(
        self,
        entity_id: uuid.UUID,
        data: ChartOfAccountsCreate,
        user_id: uuid.UUID,
    ) -> ChartOfAccounts:
        """Create a new account in the chart of accounts."""
        # Check for duplicate code
        existing = await self.get_account_by_code(entity_id, data.account_code)
        if existing:
            raise ValueError(f"Account code {data.account_code} already exists")
        
        # Determine level based on parent
        level = 1
        if data.parent_id:
            parent = await self.get_account_by_id(data.parent_id)
            if parent:
                level = parent.level + 1
        
        account = ChartOfAccounts(
            entity_id=entity_id,
            account_code=data.account_code,
            account_name=data.account_name,
            description=data.description,
            account_type=data.account_type,
            account_sub_type=data.account_sub_type,
            normal_balance=data.normal_balance,
            parent_id=data.parent_id,
            level=level,
            is_header=data.is_header,
            opening_balance=data.opening_balance,
            opening_balance_date=data.opening_balance_date,
            current_balance=data.opening_balance,
            bank_account_id=data.bank_account_id,
            is_tax_account=data.is_tax_account,
            tax_type=data.tax_type,
            tax_rate=data.tax_rate,
            is_reconcilable=data.is_reconcilable,
            cash_flow_category=data.cash_flow_category,
            sort_order=data.sort_order,
            created_by_id=user_id,
            updated_by_id=user_id,
        )
        
        self.db.add(account)
        await self.db.flush()
        return account
    
    async def update_account(
        self,
        account_id: uuid.UUID,
        data: ChartOfAccountsUpdate,
        user_id: uuid.UUID,
    ) -> ChartOfAccounts:
        """Update an existing account."""
        account = await self.get_account_by_id(account_id)
        if not account:
            raise ValueError("Account not found")
        
        if account.is_system_account:
            raise ValueError("Cannot modify system account")
        
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(account, field, value)
        
        account.updated_by_id = user_id
        await self.db.flush()
        return account
    
    async def create_default_chart_of_accounts(
        self,
        entity_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> List[ChartOfAccounts]:
        """Create default Nigerian Chart of Accounts."""
        default_accounts = [
            # ASSETS
            {"code": "1000", "name": "Assets", "type": AccountType.ASSET, "sub_type": None, "normal": NormalBalance.DEBIT, "is_header": True},
            {"code": "1100", "name": "Current Assets", "type": AccountType.ASSET, "sub_type": None, "normal": NormalBalance.DEBIT, "is_header": True, "parent": "1000"},
            {"code": "1110", "name": "Cash on Hand", "type": AccountType.ASSET, "sub_type": AccountSubType.CASH, "normal": NormalBalance.DEBIT, "parent": "1100"},
            {"code": "1120", "name": "Bank Accounts", "type": AccountType.ASSET, "sub_type": AccountSubType.BANK, "normal": NormalBalance.DEBIT, "is_header": True, "parent": "1100", "reconcilable": True},
            {"code": "1130", "name": "Accounts Receivable", "type": AccountType.ASSET, "sub_type": AccountSubType.ACCOUNTS_RECEIVABLE, "normal": NormalBalance.DEBIT, "parent": "1100", "reconcilable": True},
            {"code": "1140", "name": "Inventory", "type": AccountType.ASSET, "sub_type": AccountSubType.INVENTORY, "normal": NormalBalance.DEBIT, "parent": "1100"},
            {"code": "1150", "name": "Prepaid Expenses", "type": AccountType.ASSET, "sub_type": AccountSubType.PREPAID_EXPENSE, "normal": NormalBalance.DEBIT, "parent": "1100"},
            {"code": "1160", "name": "VAT Receivable (Input VAT)", "type": AccountType.ASSET, "sub_type": AccountSubType.OTHER_CURRENT_ASSET, "normal": NormalBalance.DEBIT, "parent": "1100", "tax_account": True, "tax_type": "vat_input"},
            {"code": "1170", "name": "WHT Receivable", "type": AccountType.ASSET, "sub_type": AccountSubType.OTHER_CURRENT_ASSET, "normal": NormalBalance.DEBIT, "parent": "1100", "tax_account": True, "tax_type": "wht_receivable"},
            {"code": "1200", "name": "Non-Current Assets", "type": AccountType.ASSET, "sub_type": None, "normal": NormalBalance.DEBIT, "is_header": True, "parent": "1000"},
            {"code": "1210", "name": "Property, Plant & Equipment", "type": AccountType.ASSET, "sub_type": AccountSubType.FIXED_ASSET, "normal": NormalBalance.DEBIT, "parent": "1200"},
            {"code": "1220", "name": "Accumulated Depreciation", "type": AccountType.ASSET, "sub_type": AccountSubType.ACCUMULATED_DEPRECIATION, "normal": NormalBalance.CREDIT, "parent": "1200"},
            {"code": "1230", "name": "Intangible Assets", "type": AccountType.ASSET, "sub_type": AccountSubType.OTHER_NON_CURRENT_ASSET, "normal": NormalBalance.DEBIT, "parent": "1200"},
            
            # LIABILITIES
            {"code": "2000", "name": "Liabilities", "type": AccountType.LIABILITY, "sub_type": None, "normal": NormalBalance.CREDIT, "is_header": True},
            {"code": "2100", "name": "Current Liabilities", "type": AccountType.LIABILITY, "sub_type": None, "normal": NormalBalance.CREDIT, "is_header": True, "parent": "2000"},
            {"code": "2110", "name": "Accounts Payable", "type": AccountType.LIABILITY, "sub_type": AccountSubType.ACCOUNTS_PAYABLE, "normal": NormalBalance.CREDIT, "parent": "2100", "reconcilable": True},
            {"code": "2120", "name": "Accrued Expenses", "type": AccountType.LIABILITY, "sub_type": AccountSubType.ACCRUED_EXPENSE, "normal": NormalBalance.CREDIT, "parent": "2100"},
            {"code": "2130", "name": "VAT Payable (Output VAT)", "type": AccountType.LIABILITY, "sub_type": AccountSubType.VAT_PAYABLE, "normal": NormalBalance.CREDIT, "parent": "2100", "tax_account": True, "tax_type": "vat_output", "tax_rate": Decimal("7.5")},
            {"code": "2140", "name": "WHT Payable", "type": AccountType.LIABILITY, "sub_type": AccountSubType.WHT_PAYABLE, "normal": NormalBalance.CREDIT, "parent": "2100", "tax_account": True, "tax_type": "wht_payable"},
            {"code": "2150", "name": "PAYE Payable", "type": AccountType.LIABILITY, "sub_type": AccountSubType.PAYE_PAYABLE, "normal": NormalBalance.CREDIT, "parent": "2100", "tax_account": True, "tax_type": "paye"},
            {"code": "2160", "name": "Pension Payable", "type": AccountType.LIABILITY, "sub_type": AccountSubType.PENSION_PAYABLE, "normal": NormalBalance.CREDIT, "parent": "2100", "tax_account": True, "tax_type": "pension"},
            {"code": "2170", "name": "NHF Payable", "type": AccountType.LIABILITY, "sub_type": AccountSubType.OTHER_CURRENT_LIABILITY, "normal": NormalBalance.CREDIT, "parent": "2100", "tax_account": True, "tax_type": "nhf"},
            {"code": "2180", "name": "NSITF Payable", "type": AccountType.LIABILITY, "sub_type": AccountSubType.OTHER_CURRENT_LIABILITY, "normal": NormalBalance.CREDIT, "parent": "2100", "tax_account": True, "tax_type": "nsitf"},
            {"code": "2190", "name": "Salaries Payable", "type": AccountType.LIABILITY, "sub_type": AccountSubType.ACCRUED_EXPENSE, "normal": NormalBalance.CREDIT, "parent": "2100"},
            {"code": "2200", "name": "Non-Current Liabilities", "type": AccountType.LIABILITY, "sub_type": None, "normal": NormalBalance.CREDIT, "is_header": True, "parent": "2000"},
            {"code": "2210", "name": "Long-term Loans", "type": AccountType.LIABILITY, "sub_type": AccountSubType.LOAN, "normal": NormalBalance.CREDIT, "parent": "2200"},
            
            # EQUITY
            {"code": "3000", "name": "Equity", "type": AccountType.EQUITY, "sub_type": None, "normal": NormalBalance.CREDIT, "is_header": True},
            {"code": "3100", "name": "Share Capital", "type": AccountType.EQUITY, "sub_type": AccountSubType.SHARE_CAPITAL, "normal": NormalBalance.CREDIT, "parent": "3000"},
            {"code": "3200", "name": "Retained Earnings", "type": AccountType.EQUITY, "sub_type": AccountSubType.RETAINED_EARNINGS, "normal": NormalBalance.CREDIT, "parent": "3000"},
            {"code": "3300", "name": "Drawings", "type": AccountType.EQUITY, "sub_type": AccountSubType.DRAWINGS, "normal": NormalBalance.DEBIT, "parent": "3000"},
            
            # REVENUE
            {"code": "4000", "name": "Revenue", "type": AccountType.REVENUE, "sub_type": None, "normal": NormalBalance.CREDIT, "is_header": True},
            {"code": "4100", "name": "Sales Revenue", "type": AccountType.REVENUE, "sub_type": AccountSubType.SALES_REVENUE, "normal": NormalBalance.CREDIT, "parent": "4000"},
            {"code": "4200", "name": "Service Revenue", "type": AccountType.REVENUE, "sub_type": AccountSubType.SERVICE_REVENUE, "normal": NormalBalance.CREDIT, "parent": "4000"},
            {"code": "4300", "name": "Interest Income", "type": AccountType.REVENUE, "sub_type": AccountSubType.INTEREST_INCOME, "normal": NormalBalance.CREDIT, "parent": "4000"},
            {"code": "4900", "name": "Other Income", "type": AccountType.REVENUE, "sub_type": AccountSubType.OTHER_INCOME, "normal": NormalBalance.CREDIT, "parent": "4000"},
            
            # EXPENSES
            {"code": "5000", "name": "Expenses", "type": AccountType.EXPENSE, "sub_type": None, "normal": NormalBalance.DEBIT, "is_header": True},
            {"code": "5100", "name": "Cost of Goods Sold", "type": AccountType.EXPENSE, "sub_type": AccountSubType.COST_OF_GOODS_SOLD, "normal": NormalBalance.DEBIT, "parent": "5000"},
            {"code": "5200", "name": "Salaries & Wages", "type": AccountType.EXPENSE, "sub_type": AccountSubType.SALARY_EXPENSE, "normal": NormalBalance.DEBIT, "parent": "5000"},
            {"code": "5210", "name": "Employer Pension Contribution", "type": AccountType.EXPENSE, "sub_type": AccountSubType.SALARY_EXPENSE, "normal": NormalBalance.DEBIT, "parent": "5000", "tax_account": True, "tax_type": "employer_pension"},
            {"code": "5220", "name": "NSITF Contribution", "type": AccountType.EXPENSE, "sub_type": AccountSubType.SALARY_EXPENSE, "normal": NormalBalance.DEBIT, "parent": "5000", "tax_account": True, "tax_type": "nsitf_expense"},
            {"code": "5230", "name": "ITF Contribution", "type": AccountType.EXPENSE, "sub_type": AccountSubType.SALARY_EXPENSE, "normal": NormalBalance.DEBIT, "parent": "5000", "tax_account": True, "tax_type": "itf"},
            {"code": "5300", "name": "Rent Expense", "type": AccountType.EXPENSE, "sub_type": AccountSubType.RENT_EXPENSE, "normal": NormalBalance.DEBIT, "parent": "5000"},
            {"code": "5400", "name": "Utilities Expense", "type": AccountType.EXPENSE, "sub_type": AccountSubType.UTILITIES_EXPENSE, "normal": NormalBalance.DEBIT, "parent": "5000"},
            {"code": "5500", "name": "Depreciation Expense", "type": AccountType.EXPENSE, "sub_type": AccountSubType.DEPRECIATION_EXPENSE, "normal": NormalBalance.DEBIT, "parent": "5000"},
            {"code": "5600", "name": "Bank Charges", "type": AccountType.EXPENSE, "sub_type": AccountSubType.BANK_CHARGES, "normal": NormalBalance.DEBIT, "parent": "5000"},
            {"code": "5610", "name": "EMTL Charges", "type": AccountType.EXPENSE, "sub_type": AccountSubType.BANK_CHARGES, "normal": NormalBalance.DEBIT, "parent": "5000", "tax_account": True, "tax_type": "emtl"},
            {"code": "5620", "name": "Stamp Duty", "type": AccountType.EXPENSE, "sub_type": AccountSubType.BANK_CHARGES, "normal": NormalBalance.DEBIT, "parent": "5000", "tax_account": True, "tax_type": "stamp_duty"},
            {"code": "5700", "name": "Income Tax Expense", "type": AccountType.EXPENSE, "sub_type": AccountSubType.TAX_EXPENSE, "normal": NormalBalance.DEBIT, "parent": "5000"},
            {"code": "5800", "name": "Professional Fees", "type": AccountType.EXPENSE, "sub_type": AccountSubType.OTHER_EXPENSE, "normal": NormalBalance.DEBIT, "parent": "5000"},
            {"code": "5900", "name": "Other Expenses", "type": AccountType.EXPENSE, "sub_type": AccountSubType.OTHER_EXPENSE, "normal": NormalBalance.DEBIT, "parent": "5000"},
        ]
        
        # Create accounts in order (parents first)
        created_accounts = []
        code_to_id = {}
        
        for acc_data in default_accounts:
            parent_id = None
            if "parent" in acc_data and acc_data["parent"] in code_to_id:
                parent_id = code_to_id[acc_data["parent"]]
            
            level = 1
            if parent_id:
                parent = await self.get_account_by_id(parent_id)
                if parent:
                    level = parent.level + 1
            
            account = ChartOfAccounts(
                entity_id=entity_id,
                account_code=acc_data["code"],
                account_name=acc_data["name"],
                account_type=acc_data["type"],
                account_sub_type=acc_data.get("sub_type"),
                normal_balance=acc_data["normal"],
                parent_id=parent_id,
                level=level,
                is_header=acc_data.get("is_header", False),
                is_tax_account=acc_data.get("tax_account", False),
                tax_type=acc_data.get("tax_type"),
                tax_rate=acc_data.get("tax_rate"),
                is_reconcilable=acc_data.get("reconcilable", False),
                is_system_account=True,
                created_by_id=user_id,
                updated_by_id=user_id,
            )
            
            self.db.add(account)
            await self.db.flush()
            
            code_to_id[acc_data["code"]] = account.id
            created_accounts.append(account)
        
        return created_accounts
    
    # =========================================================================
    # FISCAL PERIODS
    # =========================================================================
    
    async def get_fiscal_years(
        self,
        entity_id: uuid.UUID,
    ) -> List[FiscalYear]:
        """Get all fiscal years for an entity."""
        result = await self.db.execute(
            select(FiscalYear)
            .where(FiscalYear.entity_id == entity_id)
            .order_by(desc(FiscalYear.start_date))
        )
        return list(result.scalars().all())
    
    async def get_current_fiscal_year(
        self,
        entity_id: uuid.UUID,
    ) -> Optional[FiscalYear]:
        """Get current fiscal year for an entity."""
        result = await self.db.execute(
            select(FiscalYear).where(
                and_(
                    FiscalYear.entity_id == entity_id,
                    FiscalYear.is_current == True,
                )
            )
        )
        return result.scalar_one_or_none()
    
    async def create_fiscal_year(
        self,
        entity_id: uuid.UUID,
        data: FiscalYearCreate,
        user_id: uuid.UUID,
    ) -> FiscalYear:
        """Create a new fiscal year with optional periods."""
        # Check for overlapping years
        existing = await self.db.execute(
            select(FiscalYear).where(
                and_(
                    FiscalYear.entity_id == entity_id,
                    or_(
                        and_(
                            FiscalYear.start_date <= data.start_date,
                            FiscalYear.end_date >= data.start_date,
                        ),
                        and_(
                            FiscalYear.start_date <= data.end_date,
                            FiscalYear.end_date >= data.end_date,
                        ),
                    )
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Fiscal year overlaps with existing year")
        
        fiscal_year = FiscalYear(
            entity_id=entity_id,
            year_name=data.year_name,
            start_date=data.start_date,
            end_date=data.end_date,
            is_current=True,
        )
        
        self.db.add(fiscal_year)
        await self.db.flush()
        
        # Auto-create periods (12 months)
        if data.auto_create_periods:
            await self._create_fiscal_periods(entity_id, fiscal_year, user_id)
        
        return fiscal_year
    
    async def _create_fiscal_periods(
        self,
        entity_id: uuid.UUID,
        fiscal_year: FiscalYear,
        user_id: uuid.UUID,
    ) -> List[FiscalPeriod]:
        """Create 12 monthly periods for a fiscal year."""
        from calendar import monthrange
        from dateutil.relativedelta import relativedelta
        
        periods = []
        current_date = fiscal_year.start_date
        
        for period_num in range(1, 13):
            month_name = current_date.strftime("%B %Y")
            _, last_day = monthrange(current_date.year, current_date.month)
            period_end = date(current_date.year, current_date.month, last_day)
            
            # Don't exceed fiscal year end
            if period_end > fiscal_year.end_date:
                period_end = fiscal_year.end_date
            
            period = FiscalPeriod(
                entity_id=entity_id,
                fiscal_year_id=fiscal_year.id,
                period_name=month_name,
                period_number=period_num,
                start_date=current_date,
                end_date=period_end,
                status=FiscalPeriodStatus.OPEN,
            )
            
            self.db.add(period)
            periods.append(period)
            
            # Move to next month
            current_date = period_end + relativedelta(days=1)
            if current_date > fiscal_year.end_date:
                break
        
        await self.db.flush()
        return periods
    
    async def get_fiscal_period_for_date(
        self,
        entity_id: uuid.UUID,
        entry_date: date,
    ) -> Optional[FiscalPeriod]:
        """Get the fiscal period containing a specific date."""
        result = await self.db.execute(
            select(FiscalPeriod).where(
                and_(
                    FiscalPeriod.entity_id == entity_id,
                    FiscalPeriod.start_date <= entry_date,
                    FiscalPeriod.end_date >= entry_date,
                )
            )
        )
        return result.scalar_one_or_none()
    
    async def get_open_period_for_date(
        self,
        entity_id: uuid.UUID,
        entry_date: date,
    ) -> Optional[FiscalPeriod]:
        """Get an open fiscal period for a specific date."""
        result = await self.db.execute(
            select(FiscalPeriod).where(
                and_(
                    FiscalPeriod.entity_id == entity_id,
                    FiscalPeriod.start_date <= entry_date,
                    FiscalPeriod.end_date >= entry_date,
                    FiscalPeriod.status == FiscalPeriodStatus.OPEN,
                )
            )
        )
        return result.scalar_one_or_none()
    
    # =========================================================================
    # JOURNAL ENTRIES
    # =========================================================================
    
    async def _generate_entry_number(
        self,
        entity_id: uuid.UUID,
        entry_date: date,
    ) -> str:
        """Generate unique journal entry number."""
        year = entry_date.year
        
        # Count existing entries for this year
        result = await self.db.execute(
            select(func.count(JournalEntry.id)).where(
                and_(
                    JournalEntry.entity_id == entity_id,
                    JournalEntry.entry_number.like(f"JE-{year}-%"),
                )
            )
        )
        count = result.scalar() or 0
        
        return f"JE-{year}-{str(count + 1).zfill(5)}"
    
    async def get_journal_entries(
        self,
        entity_id: uuid.UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        status: Optional[JournalEntryStatus] = None,
        entry_type: Optional[JournalEntryType] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[JournalEntry], int]:
        """Get journal entries with filtering."""
        query = select(JournalEntry).where(JournalEntry.entity_id == entity_id)
        
        if start_date:
            query = query.where(JournalEntry.entry_date >= start_date)
        if end_date:
            query = query.where(JournalEntry.entry_date <= end_date)
        if status:
            query = query.where(JournalEntry.status == status)
        if entry_type:
            query = query.where(JournalEntry.entry_type == entry_type)
        
        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0
        
        # Get entries with lines
        query = query.options(selectinload(JournalEntry.lines))
        query = query.order_by(desc(JournalEntry.entry_date), desc(JournalEntry.entry_number))
        query = query.limit(limit).offset(offset)
        
        result = await self.db.execute(query)
        entries = list(result.scalars().all())
        
        return entries, total
    
    async def get_journal_entry_by_id(
        self,
        entry_id: uuid.UUID,
    ) -> Optional[JournalEntry]:
        """Get journal entry by ID with lines."""
        result = await self.db.execute(
            select(JournalEntry)
            .options(selectinload(JournalEntry.lines))
            .where(JournalEntry.id == entry_id)
        )
        return result.scalar_one_or_none()
    
    async def create_journal_entry(
        self,
        entity_id: uuid.UUID,
        data: JournalEntryCreate,
        user_id: uuid.UUID,
    ) -> JournalEntry:
        """Create a new journal entry."""
        # First check if any period exists for this date
        any_period = await self.get_fiscal_period_for_date(entity_id, data.entry_date)
        if not any_period:
            raise ValueError(f"No fiscal period exists for date {data.entry_date}")
        
        # Check if period is LOCKED (hard enforcement)
        if any_period.status == FiscalPeriodStatus.LOCKED:
            raise ValueError(
                f"Cannot post to locked period '{any_period.period_name}'. "
                f"Period has been permanently locked and no further entries are allowed."
            )
        
        # Check if period is CLOSED
        if any_period.status == FiscalPeriodStatus.CLOSED:
            raise ValueError(
                f"Cannot post to closed period '{any_period.period_name}'. "
                f"Reopen the period or use a different date."
            )
        
        # Validate period is open (covers remaining statuses)
        period = await self.get_open_period_for_date(entity_id, data.entry_date)
        if not period:
            raise ValueError(f"No open fiscal period for date {data.entry_date}")
        
        # Generate entry number
        entry_number = await self._generate_entry_number(entity_id, data.entry_date)
        
        # Calculate totals
        total_debit = sum(line.debit_amount for line in data.lines)
        total_credit = sum(line.credit_amount for line in data.lines)
        
        if total_debit != total_credit:
            raise ValueError(f"Entry must be balanced. Debit: {total_debit}, Credit: {total_credit}")
        
        # Create entry
        entry = JournalEntry(
            entity_id=entity_id,
            fiscal_period_id=period.id,
            entry_number=entry_number,
            entry_date=data.entry_date,
            description=data.description,
            memo=data.memo,
            entry_type=data.entry_type,
            source_module=data.source_module,
            source_document_type=data.source_document_type,
            source_document_id=data.source_document_id,
            source_reference=data.source_reference,
            total_debit=total_debit,
            total_credit=total_credit,
            currency=data.currency,
            exchange_rate=data.exchange_rate,
            requires_approval=data.requires_approval,
            reconciliation_id=data.reconciliation_id,
            status=JournalEntryStatus.DRAFT,
            created_by_id=user_id,
            updated_by_id=user_id,
        )
        
        self.db.add(entry)
        await self.db.flush()
        
        # Create lines
        for idx, line_data in enumerate(data.lines, 1):
            line = JournalEntryLine(
                journal_entry_id=entry.id,
                account_id=line_data.account_id,
                line_number=idx,
                description=line_data.description,
                debit_amount=line_data.debit_amount,
                credit_amount=line_data.credit_amount,
                department_id=line_data.department_id,
                project_id=line_data.project_id,
                tax_code=line_data.tax_code,
                tax_amount=line_data.tax_amount,
                customer_id=line_data.customer_id,
                vendor_id=line_data.vendor_id,
                bank_transaction_id=line_data.bank_transaction_id,
            )
            self.db.add(line)
        
        await self.db.flush()
        
        # Auto-post if requested
        if data.auto_post:
            entry = await self.post_journal_entry(entry.id, user_id)
        
        return entry
    
    async def post_journal_entry(
        self,
        entry_id: uuid.UUID,
        user_id: uuid.UUID,
        post_date: Optional[date] = None,
    ) -> JournalEntry:
        """Post a journal entry to the GL."""
        entry = await self.get_journal_entry_by_id(entry_id)
        if not entry:
            raise ValueError("Journal entry not found")
        
        if entry.status != JournalEntryStatus.DRAFT:
            raise ValueError(f"Cannot post entry with status: {entry.status}")
        
        # Check if period is LOCKED (hard enforcement)
        any_period = await self.get_fiscal_period_for_date(entry.entity_id, entry.entry_date)
        if any_period and any_period.status == FiscalPeriodStatus.LOCKED:
            raise ValueError(
                f"Cannot post to locked period '{any_period.period_name}'. "
                f"Period has been permanently locked and no further entries are allowed."
            )
        
        # Verify period is still open
        period = await self.get_open_period_for_date(entry.entity_id, entry.entry_date)
        if not period:
            raise ValueError(f"Fiscal period is not open for date {entry.entry_date}")
        
        # Update account balances
        for line in entry.lines:
            account = await self.get_account_by_id(line.account_id)
            if account:
                if account.normal_balance == NormalBalance.DEBIT:
                    account.current_balance += line.debit_amount - line.credit_amount
                else:
                    account.current_balance += line.credit_amount - line.debit_amount
                account.ytd_debit += line.debit_amount
                account.ytd_credit += line.credit_amount
        
        # Update entry status
        entry.status = JournalEntryStatus.POSTED
        entry.posted_at = datetime.utcnow()
        entry.posted_by_id = user_id
        
        await self.db.flush()
        return entry
    
    async def reverse_journal_entry(
        self,
        entry_id: uuid.UUID,
        reversal_date: date,
        reason: str,
        user_id: uuid.UUID,
    ) -> JournalEntry:
        """Reverse a posted journal entry."""
        entry = await self.get_journal_entry_by_id(entry_id)
        if not entry:
            raise ValueError("Journal entry not found")
        
        if entry.status != JournalEntryStatus.POSTED:
            raise ValueError("Can only reverse posted entries")
        
        if entry.is_reversed:
            raise ValueError("Entry has already been reversed")
        
        # Check if reversal period is LOCKED (hard enforcement)
        any_period = await self.get_fiscal_period_for_date(entry.entity_id, reversal_date)
        if any_period and any_period.status == FiscalPeriodStatus.LOCKED:
            raise ValueError(
                f"Cannot create reversal in locked period '{any_period.period_name}'. "
                f"Period has been permanently locked."
            )
        
        # Check period is open
        period = await self.get_open_period_for_date(entry.entity_id, reversal_date)
        if not period:
            raise ValueError(f"No open fiscal period for reversal date {reversal_date}")
        
        # Create reversal entry with swapped debits/credits
        reversal_lines = []
        for line in entry.lines:
            reversal_lines.append(JournalEntryLineCreate(
                account_id=line.account_id,
                description=f"Reversal: {line.description or ''}",
                debit_amount=line.credit_amount,  # Swap
                credit_amount=line.debit_amount,  # Swap
                department_id=line.department_id,
                project_id=line.project_id,
                tax_code=line.tax_code,
                tax_amount=line.tax_amount,
                customer_id=line.customer_id,
                vendor_id=line.vendor_id,
            ))
        
        reversal_data = JournalEntryCreate(
            entry_date=reversal_date,
            description=f"Reversal of {entry.entry_number}: {reason}",
            entry_type=JournalEntryType.REVERSAL,
            source_module=entry.source_module,
            source_document_type=entry.source_document_type,
            source_document_id=entry.source_document_id,
            lines=reversal_lines,
            auto_post=True,
        )
        
        reversal_entry = await self.create_journal_entry(entry.entity_id, reversal_data, user_id)
        reversal_entry.original_entry_id = entry.id
        
        # Update original entry
        entry.is_reversed = True
        entry.reversed_at = datetime.utcnow()
        entry.reversed_by_id = user_id
        entry.reversal_entry_id = reversal_entry.id
        entry.reversal_reason = reason
        entry.status = JournalEntryStatus.REVERSED
        
        await self.db.flush()
        return reversal_entry
    
    # =========================================================================
    # GL INTEGRATION (FOR OTHER MODULES)
    # =========================================================================
    
    async def post_to_gl(
        self,
        entity_id: uuid.UUID,
        request: GLPostingRequest,
        user_id: uuid.UUID,
    ) -> GLPostingResponse:
        """
        Post a document from another module to the GL.
        This is the main integration point for all modules.
        """
        # Check if already posted
        existing = await self.db.execute(
            select(GLIntegrationLog).where(
                and_(
                    GLIntegrationLog.entity_id == entity_id,
                    GLIntegrationLog.source_module == request.source_module,
                    GLIntegrationLog.source_document_type == request.source_document_type,
                    GLIntegrationLog.source_document_id == request.source_document_id,
                    GLIntegrationLog.is_reversed == False,
                )
            )
        )
        if existing.scalar_one_or_none():
            return GLPostingResponse(
                success=False,
                message="Document has already been posted to GL",
            )
        
        try:
            # Create journal entry
            entry_data = JournalEntryCreate(
                entry_date=request.entry_date,
                description=request.description,
                entry_type=self._map_module_to_entry_type(request.source_module),
                source_module=request.source_module,
                source_document_type=request.source_document_type,
                source_document_id=request.source_document_id,
                source_reference=request.source_reference,
                lines=request.lines,
                auto_post=request.auto_post,
            )
            
            entry = await self.create_journal_entry(entity_id, entry_data, user_id)
            
            # Log the integration
            log = GLIntegrationLog(
                entity_id=entity_id,
                source_module=request.source_module,
                source_document_type=request.source_document_type,
                source_document_id=request.source_document_id,
                source_reference=request.source_reference,
                journal_entry_id=entry.id,
                posted_by_id=user_id,
            )
            self.db.add(log)
            await self.db.flush()
            
            return GLPostingResponse(
                success=True,
                journal_entry_id=entry.id,
                entry_number=entry.entry_number,
                message="Successfully posted to GL",
            )
        except Exception as e:
            return GLPostingResponse(
                success=False,
                message=str(e),
            )
    
    def _map_module_to_entry_type(self, source_module: str) -> JournalEntryType:
        """Map source module to journal entry type."""
        mapping = {
            "sales": JournalEntryType.SALES,
            "invoices": JournalEntryType.SALES,
            "receipts": JournalEntryType.RECEIPT,
            "purchases": JournalEntryType.PURCHASE,
            "vendors": JournalEntryType.PURCHASE,
            "payments": JournalEntryType.PAYMENT,
            "payroll": JournalEntryType.PAYROLL,
            "fixed_assets": JournalEntryType.DEPRECIATION,
            "inventory": JournalEntryType.INVENTORY_ADJUSTMENT,
            "bank_reconciliation": JournalEntryType.BANK_RECONCILIATION,
            "tax": JournalEntryType.TAX_ADJUSTMENT,
        }
        return mapping.get(source_module.lower(), JournalEntryType.MANUAL)
    
    # =========================================================================
    # REPORTING
    # =========================================================================
    
    async def get_trial_balance(
        self,
        entity_id: uuid.UUID,
        as_of_date: date,
    ) -> TrialBalanceReport:
        """Generate trial balance report."""
        accounts = await self.get_chart_of_accounts(entity_id, include_headers=False)
        
        items = []
        total_debits = Decimal("0.00")
        total_credits = Decimal("0.00")
        
        for account in accounts:
            # Determine if balance should show as debit or credit
            balance = account.current_balance
            
            if account.normal_balance == NormalBalance.DEBIT:
                debit_balance = balance if balance >= 0 else Decimal("0.00")
                credit_balance = abs(balance) if balance < 0 else Decimal("0.00")
            else:
                credit_balance = balance if balance >= 0 else Decimal("0.00")
                debit_balance = abs(balance) if balance < 0 else Decimal("0.00")
            
            if debit_balance > 0 or credit_balance > 0:
                items.append(TrialBalanceItem(
                    account_id=account.id,
                    account_code=account.account_code,
                    account_name=account.account_name,
                    account_type=account.account_type,
                    debit_balance=debit_balance,
                    credit_balance=credit_balance,
                ))
                total_debits += debit_balance
                total_credits += credit_balance
        
        return TrialBalanceReport(
            entity_id=entity_id,
            as_of_date=as_of_date,
            total_debits=total_debits,
            total_credits=total_credits,
            is_balanced=total_debits == total_credits,
            items=items,
        )
    
    async def get_income_statement(
        self,
        entity_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> IncomeStatementReport:
        """Generate income statement (P&L) report."""
        accounts = await self.get_chart_of_accounts(entity_id, include_headers=False)
        
        revenue_items = []
        expense_items = []
        total_revenue = Decimal("0.00")
        total_expenses = Decimal("0.00")
        
        for account in accounts:
            if account.account_type in [AccountType.REVENUE, AccountType.INCOME]:
                if account.current_balance != 0:
                    revenue_items.append(IncomeStatementItem(
                        account_id=account.id,
                        account_code=account.account_code,
                        account_name=account.account_name,
                        account_sub_type=account.account_sub_type,
                        amount=abs(account.current_balance),
                    ))
                    total_revenue += abs(account.current_balance)
            elif account.account_type == AccountType.EXPENSE:
                if account.current_balance != 0:
                    expense_items.append(IncomeStatementItem(
                        account_id=account.id,
                        account_code=account.account_code,
                        account_name=account.account_name,
                        account_sub_type=account.account_sub_type,
                        amount=abs(account.current_balance),
                    ))
                    total_expenses += abs(account.current_balance)
        
        return IncomeStatementReport(
            entity_id=entity_id,
            start_date=start_date,
            end_date=end_date,
            revenue_items=revenue_items,
            expense_items=expense_items,
            total_revenue=total_revenue,
            total_expenses=total_expenses,
            net_income=total_revenue - total_expenses,
        )
    
    async def get_balance_sheet(
        self,
        entity_id: uuid.UUID,
        as_of_date: date,
    ) -> BalanceSheetReport:
        """Generate balance sheet report."""
        accounts = await self.get_chart_of_accounts(entity_id, include_headers=False)
        
        assets = []
        liabilities = []
        equity = []
        total_assets = Decimal("0.00")
        total_liabilities = Decimal("0.00")
        total_equity = Decimal("0.00")
        
        for account in accounts:
            balance = abs(account.current_balance) if account.current_balance != 0 else Decimal("0.00")
            
            if account.account_type == AccountType.ASSET:
                if balance > 0:
                    assets.append(BalanceSheetItem(
                        account_id=account.id,
                        account_code=account.account_code,
                        account_name=account.account_name,
                        account_sub_type=account.account_sub_type,
                        balance=balance,
                    ))
                    total_assets += balance
            elif account.account_type == AccountType.LIABILITY:
                if balance > 0:
                    liabilities.append(BalanceSheetItem(
                        account_id=account.id,
                        account_code=account.account_code,
                        account_name=account.account_name,
                        account_sub_type=account.account_sub_type,
                        balance=balance,
                    ))
                    total_liabilities += balance
            elif account.account_type == AccountType.EQUITY:
                if balance > 0:
                    equity.append(BalanceSheetItem(
                        account_id=account.id,
                        account_code=account.account_code,
                        account_name=account.account_name,
                        account_sub_type=account.account_sub_type,
                        balance=balance,
                    ))
                    total_equity += balance
        
        return BalanceSheetReport(
            entity_id=entity_id,
            as_of_date=as_of_date,
            assets=assets,
            liabilities=liabilities,
            equity=equity,
            total_assets=total_assets,
            total_liabilities=total_liabilities,
            total_equity=total_equity,
            is_balanced=total_assets == (total_liabilities + total_equity),
        )
    
    async def get_cash_flow_statement(
        self,
        entity_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> CashFlowStatementReport:
        """
        Generate cash flow statement (indirect method).
        
        Uses cash_flow_category on accounts to classify movements.
        Categories: operating, investing, financing
        """
        # Get accounts with balances
        accounts = await self.get_chart_of_accounts(entity_id, include_headers=False)
        
        # Calculate net income for the period
        income_statement = await self.get_income_statement(entity_id, start_date, end_date)
        net_income = income_statement.net_income
        
        # Track cash flow items
        operating_items = []
        investing_items = []
        financing_items = []
        
        # Get depreciation (non-cash expense - add back)
        depreciation_total = Decimal("0.00")
        for account in accounts:
            if account.account_sub_type and "DEPRECIATION" in str(account.account_sub_type).upper():
                depreciation_total += abs(account.current_balance)
        
        # Get changes in working capital accounts
        working_capital_changes = []
        
        for account in accounts:
            cash_flow_cat = account.cash_flow_category or ""
            
            # Skip if no balance change
            if account.current_balance == 0:
                continue
            
            # Operating activities: AR, AP, Inventory changes
            if account.account_sub_type:
                sub_type_str = str(account.account_sub_type).upper()
                
                # AR increase = cash outflow; AR decrease = cash inflow
                if "RECEIVABLE" in sub_type_str and account.account_type == AccountType.ASSET:
                    # For indirect method, increase in AR is subtracted
                    working_capital_changes.append(CashFlowItem(
                        description=f"Change in {account.account_name}",
                        amount=-account.current_balance,  # Negative if AR increased
                        category=CashFlowCategory.OPERATING,
                    ))
                
                # AP increase = cash inflow
                elif "PAYABLE" in sub_type_str and account.account_type == AccountType.LIABILITY:
                    working_capital_changes.append(CashFlowItem(
                        description=f"Change in {account.account_name}",
                        amount=account.current_balance,
                        category=CashFlowCategory.OPERATING,
                    ))
                
                # Inventory increase = cash outflow
                elif "INVENTORY" in sub_type_str:
                    working_capital_changes.append(CashFlowItem(
                        description=f"Change in {account.account_name}",
                        amount=-account.current_balance,
                        category=CashFlowCategory.OPERATING,
                    ))
            
            # Investing activities: Fixed assets
            if cash_flow_cat.lower() == "investing" or (
                account.account_sub_type and "ASSET" in str(account.account_sub_type).upper()
                and account.account_type == AccountType.ASSET
                and "FIXED" in account.account_name.upper()
            ):
                investing_items.append(CashFlowItem(
                    description=account.account_name,
                    amount=-account.current_balance,  # Purchases are outflows
                    category=CashFlowCategory.INVESTING,
                ))
            
            # Financing activities: Loans, equity
            if cash_flow_cat.lower() == "financing" or (
                account.account_type == AccountType.LIABILITY
                and account.account_sub_type
                and "LOAN" in str(account.account_sub_type).upper()
            ):
                financing_items.append(CashFlowItem(
                    description=account.account_name,
                    amount=account.current_balance,
                    category=CashFlowCategory.FINANCING,
                ))
        
        # Calculate totals
        operating_total = net_income + depreciation_total + sum(
            item.amount for item in working_capital_changes
        )
        investing_total = sum(item.amount for item in investing_items)
        financing_total = sum(item.amount for item in financing_items)
        
        net_change = operating_total + investing_total + financing_total
        
        # Get beginning and ending cash
        beginning_cash = Decimal("0.00")
        ending_cash = Decimal("0.00")
        
        for account in accounts:
            if account.account_sub_type and "CASH" in str(account.account_sub_type).upper():
                ending_cash += account.current_balance
                beginning_cash = ending_cash - net_change  # Derive beginning balance
        
        return CashFlowStatementReport(
            entity_id=entity_id,
            start_date=start_date,
            end_date=end_date,
            net_income=net_income,
            depreciation=depreciation_total,
            changes_in_working_capital=working_capital_changes,
            operating_activities_total=operating_total,
            investing_items=investing_items,
            investing_activities_total=investing_total,
            financing_items=financing_items,
            financing_activities_total=financing_total,
            net_change_in_cash=net_change,
            beginning_cash=beginning_cash,
            ending_cash=ending_cash,
        )
    
    # =========================================================================
    # PERIOD CLOSE (ENHANCED WITH BANK RECONCILIATION VALIDATION)
    # =========================================================================
    
    async def get_period_close_checklist(
        self,
        entity_id: uuid.UUID,
        period_id: uuid.UUID,
    ) -> PeriodCloseChecklist:
        """
        Get comprehensive checklist for closing a period.
        
        Enforces Nigerian accounting standards:
        1. All journal entries must be posted
        2. All bank accounts must be reconciled up to period end
        3. All reconciliation adjustments must be posted to GL
        4. Trial balance must be balanced
        5. Outstanding items must be reviewed
        """
        period = await self.db.execute(
            select(FiscalPeriod).where(FiscalPeriod.id == period_id)
        )
        period = period.scalar_one_or_none()
        if not period:
            raise ValueError("Fiscal period not found")
        
        # Check for unposted entries
        unposted_result = await self.db.execute(
            select(func.count(JournalEntry.id)).where(
                and_(
                    JournalEntry.entity_id == entity_id,
                    JournalEntry.fiscal_period_id == period_id,
                    JournalEntry.status == JournalEntryStatus.DRAFT,
                )
            )
        )
        unposted_count = unposted_result.scalar() or 0
        
        # Validate bank reconciliations using the bank reconciliation service
        from app.services.bank_reconciliation_service import BankReconciliationService
        bank_service = BankReconciliationService(self.db)
        bank_validation = await bank_service.validate_reconciliation_for_period_close(
            entity_id=entity_id,
            period_end_date=period.end_date,
        )
        
        bank_reconciled = bank_validation["is_valid"]
        unreconciled_accounts = [
            f"{acc['bank_name']} ({acc['account_number'][-4:] if len(acc.get('account_number', '')) >= 4 else acc.get('account_number', '')}): {', '.join(acc.get('issues', []))}"
            for acc in bank_validation.get("accounts", [])
            if not acc.get("is_valid", False)
        ]
        
        # Build checklist
        blocking_issues = []
        
        if unposted_count > 0:
            blocking_issues.append(f"{unposted_count} unposted journal entries")
        
        if not bank_reconciled:
            blocking_issues.append("Bank reconciliations not complete")
            blocking_issues.extend(unreconciled_accounts)
        
        trial_balance = await self.get_trial_balance(entity_id, period.end_date)
        if not trial_balance.is_balanced:
            blocking_issues.append(
                f"Trial balance is not balanced (difference: {trial_balance.total_debit - trial_balance.total_credit})"
            )
        
        # Check for pending AR/AP reconciliation (receipts/payments not matched to bank)
        # This would require querying transactions without bank matches
        outstanding_items_count = bank_validation.get("accounts", [])
        
        return PeriodCloseChecklist(
            period_id=period_id,
            period_name=period.period_name,
            all_entries_posted=unposted_count == 0,
            bank_reconciliations_complete=bank_reconciled,
            outstanding_items_reviewed=True,  # User must manually confirm
            adjusting_entries_made=True,  # User must manually confirm
            trial_balance_balanced=trial_balance.is_balanced,
            unposted_entries_count=unposted_count,
            unreconciled_bank_accounts=unreconciled_accounts,
            outstanding_items_count=len(outstanding_items_count),
            can_close=len(blocking_issues) == 0,
            blocking_issues=blocking_issues,
        )
    
    async def close_period(
        self,
        entity_id: uuid.UUID,
        request: PeriodCloseRequest,
        user_id: uuid.UUID,
    ) -> PeriodCloseResponse:
        """Close a fiscal period."""
        checklist = await self.get_period_close_checklist(entity_id, request.period_id)
        
        if not checklist.can_close and not request.force_close:
            return PeriodCloseResponse(
                success=False,
                period_id=request.period_id,
                status=FiscalPeriodStatus.OPEN,
                message=f"Cannot close period: {', '.join(checklist.blocking_issues)}",
            )
        
        # Get and update period
        period = await self.db.execute(
            select(FiscalPeriod).where(FiscalPeriod.id == request.period_id)
        )
        period = period.scalar_one_or_none()
        
        period.status = FiscalPeriodStatus.CLOSED
        period.closed_at = datetime.utcnow()
        period.closed_by_id = user_id
        period.closing_notes = request.closing_notes
        
        await self.db.flush()
        
        return PeriodCloseResponse(
            success=True,
            period_id=request.period_id,
            status=FiscalPeriodStatus.CLOSED,
            message="Period closed successfully",
            closed_at=period.closed_at,
        )

    # =========================================================================
    # FIXED ASSET INTEGRATION
    # =========================================================================
    
    async def get_fixed_asset_summary(
        self,
        entity_id: uuid.UUID,
        as_of_date: date,
    ) -> FixedAssetRegisterSummary:
        """
        Pull fixed asset totals from the Fixed Asset Register for Balance Sheet reporting.
        
        This provides detailed breakdown of:
        - Total fixed assets by category
        - Accumulated depreciation
        - Net book values
        - Individual asset details
        """
        from app.models.fixed_asset import FixedAsset, AssetStatus
        
        # Query all assets for the entity
        result = await self.db.execute(
            select(FixedAsset).where(
                and_(
                    FixedAsset.entity_id == entity_id,
                    FixedAsset.acquisition_date <= as_of_date,
                )
            ).order_by(FixedAsset.category, FixedAsset.asset_code)
        )
        assets = list(result.scalars().all())
        
        # Calculate totals
        total_cost = Decimal("0.00")
        total_depreciation = Decimal("0.00")
        active_count = 0
        disposed_count = 0
        
        # Group by category
        category_data = {}
        asset_items = []
        
        for asset in assets:
            cat = asset.category.value
            
            # Initialize category if not exists
            if cat not in category_data:
                category_data[cat] = {
                    "count": 0,
                    "cost": Decimal("0.00"),
                    "depreciation": Decimal("0.00"),
                    "nbv": Decimal("0.00"),
                }
            
            # Accumulate totals
            category_data[cat]["count"] += 1
            category_data[cat]["cost"] += asset.acquisition_cost
            category_data[cat]["depreciation"] += asset.accumulated_depreciation
            category_data[cat]["nbv"] += asset.net_book_value
            
            total_cost += asset.acquisition_cost
            total_depreciation += asset.accumulated_depreciation
            
            if asset.status == AssetStatus.ACTIVE:
                active_count += 1
            elif asset.status == AssetStatus.DISPOSED:
                disposed_count += 1
            
            # Build asset item
            asset_items.append(FixedAssetSummaryItem(
                asset_id=asset.id,
                asset_code=asset.asset_code,
                name=asset.name,
                category=asset.category.value,
                acquisition_date=asset.acquisition_date,
                acquisition_cost=asset.acquisition_cost,
                accumulated_depreciation=asset.accumulated_depreciation,
                net_book_value=asset.net_book_value,
                depreciation_method=asset.depreciation_method.value,
                depreciation_rate=asset.depreciation_rate,
                status=asset.status.value,
            ))
        
        # Build category summaries
        category_summaries = [
            FixedAssetCategorySummary(
                category=cat,
                asset_count=data["count"],
                total_cost=data["cost"],
                total_depreciation=data["depreciation"],
                total_nbv=data["nbv"],
            )
            for cat, data in category_data.items()
        ]
        
        return FixedAssetRegisterSummary(
            entity_id=entity_id,
            as_of_date=as_of_date,
            total_assets=len(assets),
            active_assets=active_count,
            disposed_assets=disposed_count,
            total_acquisition_cost=total_cost,
            total_accumulated_depreciation=total_depreciation,
            total_net_book_value=total_cost - total_depreciation,
            by_category=category_summaries,
            assets=asset_items,
        )
    
    async def validate_fixed_asset_gl_balances(
        self,
        entity_id: uuid.UUID,
        as_of_date: date,
    ) -> GLFixedAssetValidation:
        """
        Validate GL balances against Fixed Asset Register totals.
        
        Compares:
        - GL Account 1210 (Property, Plant & Equipment) vs Register total cost
        - GL Account 1220 (Accumulated Depreciation) vs Register accumulated depreciation
        - Net book value (GL vs Register)
        
        Returns validation result with any discrepancies identified.
        """
        from app.models.fixed_asset import FixedAsset, AssetStatus
        
        # Get GL balances for fixed asset accounts
        # Account codes: 1210 = Fixed Assets, 1220 = Accumulated Depreciation
        gl_fixed_asset_cost = Decimal("0.00")
        gl_accumulated_depreciation = Decimal("0.00")
        
        accounts = await self.get_chart_of_accounts(entity_id, include_headers=False)
        
        for account in accounts:
            if account.account_code == "1210" or (
                account.account_sub_type and "FIXED_ASSET" in str(account.account_sub_type).upper()
            ):
                gl_fixed_asset_cost += abs(account.current_balance)
            elif account.account_code == "1220" or (
                account.account_sub_type and "ACCUMULATED_DEPRECIATION" in str(account.account_sub_type).upper()
            ):
                gl_accumulated_depreciation += abs(account.current_balance)
        
        gl_net_book_value = gl_fixed_asset_cost - gl_accumulated_depreciation
        
        # Get Fixed Asset Register totals
        result = await self.db.execute(
            select(
                func.sum(FixedAsset.acquisition_cost).label("total_cost"),
                func.sum(FixedAsset.accumulated_depreciation).label("total_depreciation"),
            ).where(
                and_(
                    FixedAsset.entity_id == entity_id,
                    FixedAsset.status == AssetStatus.ACTIVE,
                )
            )
        )
        register_totals = result.first()
        
        register_total_cost = register_totals.total_cost or Decimal("0.00")
        register_accumulated_depreciation = register_totals.total_depreciation or Decimal("0.00")
        register_net_book_value = register_total_cost - register_accumulated_depreciation
        
        # Calculate variances
        cost_variance = gl_fixed_asset_cost - register_total_cost
        depreciation_variance = gl_accumulated_depreciation - register_accumulated_depreciation
        nbv_variance = gl_net_book_value - register_net_book_value
        
        # Identify issues
        issues = []
        recommendations = []
        tolerance = Decimal("0.01")  # Allow for rounding differences
        
        if abs(cost_variance) > tolerance:
            issues.append(
                f"Fixed asset cost variance: GL shows ₦{gl_fixed_asset_cost:,.2f} but Register shows ₦{register_total_cost:,.2f} "
                f"(difference: ₦{cost_variance:,.2f})"
            )
            recommendations.append(
                "Review asset acquisitions and disposals. Ensure all purchases are posted to both GL and Asset Register."
            )
        
        if abs(depreciation_variance) > tolerance:
            issues.append(
                f"Accumulated depreciation variance: GL shows ₦{gl_accumulated_depreciation:,.2f} but Register shows ₦{register_accumulated_depreciation:,.2f} "
                f"(difference: ₦{depreciation_variance:,.2f})"
            )
            recommendations.append(
                "Run depreciation posting to ensure GL is updated. Check for manual GL adjustments not reflected in Register."
            )
        
        if abs(nbv_variance) > tolerance:
            issues.append(
                f"Net book value variance: GL shows ₦{gl_net_book_value:,.2f} but Register shows ₦{register_net_book_value:,.2f} "
                f"(difference: ₦{nbv_variance:,.2f})"
            )
        
        if not issues:
            recommendations.append("GL balances are in sync with the Fixed Asset Register. No action required.")
        
        is_valid = len(issues) == 0
        
        return GLFixedAssetValidation(
            entity_id=entity_id,
            validation_date=as_of_date,
            is_valid=is_valid,
            gl_fixed_asset_cost=gl_fixed_asset_cost,
            gl_accumulated_depreciation=gl_accumulated_depreciation,
            gl_net_book_value=gl_net_book_value,
            register_total_cost=register_total_cost,
            register_accumulated_depreciation=register_accumulated_depreciation,
            register_net_book_value=register_net_book_value,
            cost_variance=cost_variance,
            depreciation_variance=depreciation_variance,
            nbv_variance=nbv_variance,
            issues=issues,
            recommendations=recommendations,
        )
    
    async def get_enhanced_balance_sheet(
        self,
        entity_id: uuid.UUID,
        as_of_date: date,
        include_fixed_asset_details: bool = True,
        validate_fixed_assets: bool = True,
    ) -> EnhancedBalanceSheetReport:
        """
        Generate enhanced Balance Sheet with fixed asset details and validation.
        
        This provides:
        - Standard Balance Sheet format
        - Detailed fixed asset breakdown by category
        - Validation of GL vs Fixed Asset Register
        - Notes on depreciation policy
        """
        # Get standard balance sheet
        basic_balance_sheet = await self.get_balance_sheet(entity_id, as_of_date)
        
        # Get fixed asset summary if requested
        fixed_asset_summary = None
        fixed_asset_validation = None
        
        if include_fixed_asset_details:
            fixed_asset_summary = await self.get_fixed_asset_summary(entity_id, as_of_date)
        
        if validate_fixed_assets:
            fixed_asset_validation = await self.validate_fixed_asset_gl_balances(entity_id, as_of_date)
        
        # Build depreciation policy note
        depreciation_policy = """
Depreciation Policy (Nigerian Tax Standards):
- Buildings: 10% Reducing Balance
- Plant & Machinery: 25% Reducing Balance  
- Furniture & Fittings: 20% Reducing Balance
- Motor Vehicles: 25% Reducing Balance
- Computer Equipment: 25% Reducing Balance
- Office Equipment: 20% Reducing Balance
- Intangible Assets: 12.5% Reducing Balance

Note: Under the 2026 Nigeria Tax Administration Act, capital gains on asset disposal 
are taxed at the flat CIT rate (30% for large companies). Input VAT on capital 
expenditure is now recoverable with a valid NRS Invoice Reference Number (IRN).
        """.strip()
        
        # Build fixed asset notes
        fixed_asset_notes = None
        if fixed_asset_summary:
            fixed_asset_notes = f"""
Fixed Asset Register Summary as at {as_of_date.strftime('%B %d, %Y')}:
- Total Assets: {fixed_asset_summary.total_assets} ({fixed_asset_summary.active_assets} active, {fixed_asset_summary.disposed_assets} disposed)
- Total Acquisition Cost: ₦{fixed_asset_summary.total_acquisition_cost:,.2f}
- Total Accumulated Depreciation: ₦{fixed_asset_summary.total_accumulated_depreciation:,.2f}
- Total Net Book Value: ₦{fixed_asset_summary.total_net_book_value:,.2f}
            """.strip()
        
        return EnhancedBalanceSheetReport(
            entity_id=basic_balance_sheet.entity_id,
            as_of_date=basic_balance_sheet.as_of_date,
            assets=basic_balance_sheet.assets,
            liabilities=basic_balance_sheet.liabilities,
            equity=basic_balance_sheet.equity,
            total_assets=basic_balance_sheet.total_assets,
            total_liabilities=basic_balance_sheet.total_liabilities,
            total_equity=basic_balance_sheet.total_equity,
            is_balanced=basic_balance_sheet.is_balanced,
            fixed_asset_summary=fixed_asset_summary,
            fixed_asset_validation=fixed_asset_validation,
            fixed_asset_notes=fixed_asset_notes,
            depreciation_policy=depreciation_policy,
        )

    # =========================================================================
    # SOURCE SYSTEM INTEGRATIONS - ACCOUNTING READS FROM OTHER MODULES
    # =========================================================================
    
    async def get_inventory_summary_for_gl(
        self,
        entity_id: uuid.UUID,
        as_of_date: date,
    ) -> "InventorySummaryForGL":
        """
        Get inventory summary for GL account 1140 reconciliation.
        
        Reads from: Inventory system
        Maps to: GL 1140 - Inventory
        """
        from app.schemas.accounting import InventorySummaryForGL
        from app.models.inventory import InventoryItem
        
        # Get all inventory items
        result = await self.db.execute(
            select(InventoryItem).where(
                InventoryItem.entity_id == entity_id
            )
        )
        items = result.scalars().all()
        
        # Calculate totals
        total_value = Decimal("0.00")
        total_quantity = 0
        low_stock_count = 0
        active_count = 0
        category_totals = {}
        
        for item in items:
            if item.is_active:
                active_count += 1
                item_value = Decimal(str(item.unit_cost)) * item.quantity_on_hand
                total_value += item_value
                total_quantity += item.quantity_on_hand
                
                if item.quantity_on_hand <= item.reorder_level:
                    low_stock_count += 1
                
                # Group by category
                cat = item.category or "Uncategorized"
                if cat not in category_totals:
                    category_totals[cat] = {"count": 0, "value": Decimal("0.00"), "quantity": 0}
                category_totals[cat]["count"] += 1
                category_totals[cat]["value"] += item_value
                category_totals[cat]["quantity"] += item.quantity_on_hand
        
        categories = [
            {"category": k, "count": v["count"], "value": float(v["value"]), "quantity": v["quantity"]}
            for k, v in category_totals.items()
        ]
        
        return InventorySummaryForGL(
            entity_id=entity_id,
            as_of_date=as_of_date,
            total_items=len(items),
            active_items=active_count,
            total_inventory_value=total_value,
            total_quantity_on_hand=total_quantity,
            low_stock_items=low_stock_count,
            categories=categories,
            valuation_method="weighted_average",
        )
    
    async def get_ar_aging_summary(
        self,
        entity_id: uuid.UUID,
        as_of_date: date,
    ) -> "ARAgingSummary":
        """
        Get Accounts Receivable aging for GL account 1130 reconciliation.
        
        Reads from: Invoice/Customer system
        Maps to: GL 1130 - Accounts Receivable
        """
        from app.schemas.accounting import ARAgingSummary
        from app.models.invoice import Invoice, InvoiceStatus
        from app.models.customer import Customer
        
        # Get all unpaid/partially paid invoices
        result = await self.db.execute(
            select(Invoice).where(
                and_(
                    Invoice.entity_id == entity_id,
                    Invoice.status.in_([InvoiceStatus.PENDING, InvoiceStatus.OVERDUE, InvoiceStatus.PARTIAL]),
                    Invoice.invoice_date <= as_of_date,
                )
            )
        )
        invoices = result.scalars().all()
        
        # Calculate aging buckets
        current = Decimal("0.00")
        days_31_60 = Decimal("0.00")
        days_61_90 = Decimal("0.00")
        over_90_days = Decimal("0.00")
        customer_balances = {}
        
        for inv in invoices:
            outstanding = Decimal(str(inv.total_amount)) - Decimal(str(inv.amount_paid or 0))
            if outstanding <= 0:
                continue
                
            days_old = (as_of_date - inv.invoice_date).days
            
            if days_old <= 30:
                current += outstanding
            elif days_old <= 60:
                days_31_60 += outstanding
            elif days_old <= 90:
                days_61_90 += outstanding
            else:
                over_90_days += outstanding
            
            # Track by customer
            cust_id = str(inv.customer_id) if inv.customer_id else "Unknown"
            if cust_id not in customer_balances:
                customer_balances[cust_id] = {"customer_id": cust_id, "balance": Decimal("0.00")}
            customer_balances[cust_id]["balance"] += outstanding
        
        total_receivables = current + days_31_60 + days_61_90 + over_90_days
        
        # Get top 10 customers by balance
        top_receivables = sorted(
            customer_balances.values(),
            key=lambda x: x["balance"],
            reverse=True
        )[:10]
        
        # Convert Decimal to float for JSON
        for item in top_receivables:
            item["balance"] = float(item["balance"])
        
        # Count unique customers
        customers_with_balance = len([c for c in customer_balances.values() if c["balance"] > 0])
        
        # Get total customers count
        cust_result = await self.db.execute(
            select(func.count(Customer.id)).where(
                and_(Customer.entity_id == entity_id, Customer.is_active == True)
            )
        )
        total_customers = cust_result.scalar() or 0
        
        return ARAgingSummary(
            entity_id=entity_id,
            as_of_date=as_of_date,
            total_receivables=total_receivables,
            current=current,
            days_31_60=days_31_60,
            days_61_90=days_61_90,
            over_90_days=over_90_days,
            total_customers=total_customers,
            customers_with_balance=customers_with_balance,
            top_receivables=top_receivables,
        )
    
    async def get_ap_aging_summary(
        self,
        entity_id: uuid.UUID,
        as_of_date: date,
    ) -> "APAgingSummary":
        """
        Get Accounts Payable aging for GL account 2110 reconciliation.
        
        Reads from: Vendor/Transaction system
        Maps to: GL 2110 - Accounts Payable
        """
        from app.schemas.accounting import APAgingSummary
        from app.models.transaction import Transaction, TransactionType
        from app.models.vendor import Vendor
        
        # Get all unpaid expense transactions (simplified - could be enhanced with vendor bills table)
        result = await self.db.execute(
            select(Transaction).where(
                and_(
                    Transaction.entity_id == entity_id,
                    Transaction.transaction_type == TransactionType.EXPENSE,
                    Transaction.transaction_date <= as_of_date,
                )
            )
        )
        transactions = result.scalars().all()
        
        # Calculate aging buckets
        current = Decimal("0.00")
        days_31_60 = Decimal("0.00")
        days_61_90 = Decimal("0.00")
        over_90_days = Decimal("0.00")
        vendor_balances = {}
        
        for txn in transactions:
            # For simplicity, treat transaction amount as payable (should check payment status)
            outstanding = Decimal(str(txn.total_amount))
            days_old = (as_of_date - txn.transaction_date).days
            
            if days_old <= 30:
                current += outstanding
            elif days_old <= 60:
                days_31_60 += outstanding
            elif days_old <= 90:
                days_61_90 += outstanding
            else:
                over_90_days += outstanding
            
            # Track by vendor
            vendor_id = str(txn.vendor_id) if txn.vendor_id else "Unknown"
            if vendor_id not in vendor_balances:
                vendor_balances[vendor_id] = {"vendor_id": vendor_id, "balance": Decimal("0.00")}
            vendor_balances[vendor_id]["balance"] += outstanding
        
        total_payables = current + days_31_60 + days_61_90 + over_90_days
        
        # Get top 10 vendors by balance
        top_payables = sorted(
            vendor_balances.values(),
            key=lambda x: x["balance"],
            reverse=True
        )[:10]
        
        for item in top_payables:
            item["balance"] = float(item["balance"])
        
        vendors_with_balance = len([v for v in vendor_balances.values() if v["balance"] > 0])
        
        # Get total vendors count
        vendor_result = await self.db.execute(
            select(func.count(Vendor.id)).where(
                and_(Vendor.entity_id == entity_id, Vendor.is_active == True)
            )
        )
        total_vendors = vendor_result.scalar() or 0
        
        return APAgingSummary(
            entity_id=entity_id,
            as_of_date=as_of_date,
            total_payables=total_payables,
            current=current,
            days_31_60=days_31_60,
            days_61_90=days_61_90,
            over_90_days=over_90_days,
            total_vendors=total_vendors,
            vendors_with_balance=vendors_with_balance,
            top_payables=top_payables,
        )
    
    async def get_payroll_summary_for_gl(
        self,
        entity_id: uuid.UUID,
        period_start: date,
        period_end: date,
    ) -> "PayrollSummaryForGL":
        """
        Get payroll summary for GL reconciliation.
        
        Reads from: Payroll system
        Maps to: GL 2150-2190 (liabilities), GL 5200-5230 (expenses)
        """
        from app.schemas.accounting import PayrollSummaryForGL
        from app.models.payroll import PayrollRun, PayrollStatus, Employee
        
        # Get payroll runs in period
        result = await self.db.execute(
            select(PayrollRun).where(
                and_(
                    PayrollRun.entity_id == entity_id,
                    PayrollRun.period_start >= period_start,
                    PayrollRun.period_end <= period_end,
                    PayrollRun.status.in_([PayrollStatus.COMPLETED, PayrollStatus.APPROVED]),
                )
            )
        )
        payroll_runs = result.scalars().all()
        
        # Sum totals
        total_gross = Decimal("0.00")
        total_employer_pension = Decimal("0.00")
        total_employer_nsitf = Decimal("0.00")
        total_paye = Decimal("0.00")
        total_pension_payable = Decimal("0.00")
        total_nhf = Decimal("0.00")
        total_net = Decimal("0.00")
        
        for pr in payroll_runs:
            total_gross += Decimal(str(pr.total_gross_pay or 0))
            total_employer_pension += Decimal(str(pr.total_pension_employer or 0))
            total_employer_nsitf += Decimal(str(pr.total_nsitf or 0))
            total_paye += Decimal(str(pr.total_paye or 0))
            total_pension_payable += Decimal(str(pr.total_pension_employee or 0)) + Decimal(str(pr.total_pension_employer or 0))
            total_nhf += Decimal(str(pr.total_nhf or 0))
            total_net += Decimal(str(pr.total_net_pay or 0))
        
        # Get employee count
        emp_result = await self.db.execute(
            select(func.count(Employee.id)).where(
                and_(Employee.entity_id == entity_id, Employee.employment_status != "terminated")
            )
        )
        total_employees = emp_result.scalar() or 0
        
        return PayrollSummaryForGL(
            entity_id=entity_id,
            period_start=period_start,
            period_end=period_end,
            total_gross_salary=total_gross,
            total_employer_pension=total_employer_pension,
            total_employer_nsitf=total_employer_nsitf,
            total_itf=Decimal("0.00"),  # ITF is calculated annually
            total_paye_payable=total_paye,
            total_pension_payable=total_pension_payable,
            total_nhf_payable=total_nhf,
            total_nsitf_payable=total_employer_nsitf,
            total_salaries_payable=total_net,
            total_employees=total_employees,
            payroll_runs=len(payroll_runs),
        )
    
    async def get_bank_summary_for_gl(
        self,
        entity_id: uuid.UUID,
        as_of_date: date,
    ) -> "BankAccountSummaryForGL":
        """
        Get bank account summary for GL account 1120 reconciliation.
        
        Reads from: Bank Reconciliation system
        Maps to: GL 1120 - Bank Accounts
        """
        from app.schemas.accounting import BankAccountSummaryForGL
        from app.models.bank_reconciliation import BankAccount, BankReconciliation
        
        # Get all bank accounts
        result = await self.db.execute(
            select(BankAccount).where(
                and_(
                    BankAccount.entity_id == entity_id,
                    BankAccount.is_active == True,
                )
            )
        )
        bank_accounts = result.scalars().all()
        
        total_balance = Decimal("0.00")
        accounts_list = []
        last_reconciled = None
        total_unreconciled = 0
        outstanding_deposits = Decimal("0.00")
        outstanding_checks = Decimal("0.00")
        
        for acc in bank_accounts:
            balance = Decimal(str(acc.current_balance or 0))
            total_balance += balance
            
            accounts_list.append({
                "account_id": str(acc.id),
                "bank_name": acc.bank_name,
                "account_number": acc.account_number[-4:] if acc.account_number else "****",
                "account_name": acc.account_name,
                "balance": float(balance),
                "currency": acc.currency or "NGN",
            })
            
            # Get latest reconciliation for this account
            recon_result = await self.db.execute(
                select(BankReconciliation)
                .where(BankReconciliation.bank_account_id == acc.id)
                .order_by(desc(BankReconciliation.reconciliation_date))
                .limit(1)
            )
            latest_recon = recon_result.scalar_one_or_none()
            
            if latest_recon:
                if last_reconciled is None or latest_recon.reconciliation_date > last_reconciled:
                    last_reconciled = latest_recon.reconciliation_date
                outstanding_deposits += Decimal(str(latest_recon.outstanding_deposits or 0))
                outstanding_checks += Decimal(str(latest_recon.outstanding_checks or 0))
        
        return BankAccountSummaryForGL(
            entity_id=entity_id,
            as_of_date=as_of_date,
            total_bank_balance=total_balance,
            accounts=accounts_list,
            last_reconciled_date=last_reconciled,
            unreconciled_items_count=total_unreconciled,
            outstanding_deposits=outstanding_deposits,
            outstanding_checks=outstanding_checks,
        )
    
    async def get_expense_claims_summary_for_gl(
        self,
        entity_id: uuid.UUID,
        as_of_date: date,
    ) -> "ExpenseClaimSummaryForGL":
        """
        Get expense claims summary for GL reconciliation.
        
        Reads from: Expense Claims system
        """
        from app.schemas.accounting import ExpenseClaimSummaryForGL
        from app.models.expense_claims import ExpenseClaim, ClaimStatus
        
        # Get claims
        result = await self.db.execute(
            select(ExpenseClaim).where(
                and_(
                    ExpenseClaim.entity_id == entity_id,
                    ExpenseClaim.created_at <= as_of_date,
                )
            )
        )
        claims = result.scalars().all()
        
        pending = Decimal("0.00")
        approved = Decimal("0.00")
        paid = Decimal("0.00")
        
        for claim in claims:
            amount = Decimal(str(claim.approved_amount or claim.total_amount or 0))
            if claim.status in [ClaimStatus.DRAFT, ClaimStatus.SUBMITTED, ClaimStatus.PENDING_APPROVAL]:
                pending += amount
            elif claim.status == ClaimStatus.APPROVED:
                approved += amount
            elif claim.status == ClaimStatus.PAID:
                paid += amount
        
        return ExpenseClaimSummaryForGL(
            entity_id=entity_id,
            as_of_date=as_of_date,
            total_pending_claims=pending,
            total_approved_claims=approved,
            total_paid_claims=paid,
            claims_by_category=[],  # Could be expanded
            claims_count=len(claims),
        )
    
    async def get_gl_source_system_summary(
        self,
        entity_id: uuid.UUID,
        as_of_date: date,
    ) -> "GLSourceSystemSummary":
        """
        Get comprehensive GL summary with all source system data.
        
        This is the master endpoint for reconciling GL accounts with source systems.
        """
        from app.schemas.accounting import GLSourceSystemSummary
        
        # Gather all source system summaries
        inventory = await self.get_inventory_summary_for_gl(entity_id, as_of_date)
        ar = await self.get_ar_aging_summary(entity_id, as_of_date)
        ap = await self.get_ap_aging_summary(entity_id, as_of_date)
        
        # Get payroll for current month
        first_of_month = as_of_date.replace(day=1)
        payroll = await self.get_payroll_summary_for_gl(entity_id, first_of_month, as_of_date)
        
        bank = await self.get_bank_summary_for_gl(entity_id, as_of_date)
        fixed_assets = await self.get_fixed_asset_summary(entity_id, as_of_date)
        expense_claims = await self.get_expense_claims_summary_for_gl(entity_id, as_of_date)
        
        # Validate GL accounts against source systems
        validations = []
        discrepancy_count = 0
        
        # Get GL balances
        gl_accounts = await self.get_chart_of_accounts(entity_id, include_headers=False)
        gl_map = {acc.account_code: acc for acc in gl_accounts}
        
        def add_validation(code: str, name: str, source: str, source_balance: Decimal):
            gl_acc = gl_map.get(code)
            gl_balance = Decimal(str(gl_acc.current_balance)) if gl_acc else Decimal("0.00")
            variance = gl_balance - source_balance
            is_reconciled = abs(variance) < Decimal("0.01")
            
            validations.append({
                "account_code": code,
                "account_name": name,
                "gl_balance": float(gl_balance),
                "source_system": source,
                "source_balance": float(source_balance),
                "variance": float(variance),
                "is_reconciled": is_reconciled,
            })
            
            return 0 if is_reconciled else 1
        
        # Validate key accounts
        discrepancy_count += add_validation("1140", "Inventory", "inventory", inventory.total_inventory_value)
        discrepancy_count += add_validation("1130", "Accounts Receivable", "invoices", ar.total_receivables)
        discrepancy_count += add_validation("2110", "Accounts Payable", "vendors", ap.total_payables)
        discrepancy_count += add_validation("1120", "Bank Accounts", "bank_reconciliation", bank.total_bank_balance)
        discrepancy_count += add_validation("1210", "Fixed Assets", "fixed_assets", fixed_assets.total_acquisition_cost)
        discrepancy_count += add_validation("1220", "Accumulated Depreciation", "fixed_assets", fixed_assets.total_accumulated_depreciation)
        
        return GLSourceSystemSummary(
            entity_id=entity_id,
            as_of_date=as_of_date,
            generated_at=datetime.utcnow(),
            inventory=inventory,
            accounts_receivable=ar,
            accounts_payable=ap,
            payroll=payroll,
            bank_accounts=bank,
            fixed_assets=fixed_assets,
            expense_claims=expense_claims,
            validations=validations,
            has_discrepancies=discrepancy_count > 0,
            discrepancy_count=discrepancy_count,
        )

    # =========================================================================
    # GL SYNC FROM SOURCE SYSTEMS
    # =========================================================================
    
    async def sync_gl_from_source_systems(
        self,
        entity_id: uuid.UUID,
        user_id: uuid.UUID,
        as_of_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Synchronize GL balances by reading from all source systems and updating
        the Chart of Accounts current_balance field directly.
        
        This method:
        1. Reads totals from all source systems (Inventory, AR, AP, Payroll, etc.)
        2. Updates the corresponding GL account balances
        3. Returns a summary of what was synced
        
        NOTE: This is a direct balance update, not via journal entries.
        Use this for initial setup or reconciliation purposes.
        """
        sync_date = as_of_date or date.today()
        results = {
            "entity_id": str(entity_id),
            "sync_date": str(sync_date),
            "accounts_updated": [],
            "errors": [],
            "summary": {}
        }
        
        # Get all GL accounts
        gl_accounts = await self.get_chart_of_accounts(entity_id, include_headers=False)
        gl_map = {acc.account_code: acc for acc in gl_accounts}
        
        async def update_account(code: str, new_balance: Decimal, source: str):
            """Helper to update an account balance."""
            acc = gl_map.get(code)
            if acc:
                old_balance = acc.current_balance
                acc.current_balance = new_balance
                results["accounts_updated"].append({
                    "account_code": code,
                    "account_name": acc.account_name,
                    "old_balance": float(old_balance),
                    "new_balance": float(new_balance),
                    "source": source,
                })
            else:
                results["errors"].append(f"Account {code} not found in Chart of Accounts")
        
        try:
            # ==========================================
            # 1. INVENTORY (GL 1140)
            # ==========================================
            from app.models.inventory import InventoryItem
            
            inv_result = await self.db.execute(
                select(func.coalesce(func.sum(InventoryItem.unit_cost * InventoryItem.quantity_on_hand), 0))
                .where(and_(InventoryItem.entity_id == entity_id, InventoryItem.is_active == True))
            )
            inventory_total = Decimal(str(inv_result.scalar() or 0))
            await update_account("1140", inventory_total, "inventory")
            results["summary"]["inventory"] = float(inventory_total)
            
            # ==========================================
            # 2. ACCOUNTS RECEIVABLE (GL 1130) - From unpaid invoices
            # ==========================================
            from app.models.invoice import Invoice, InvoiceStatus
            
            ar_result = await self.db.execute(
                select(func.coalesce(func.sum(Invoice.total_amount - Invoice.amount_paid), 0))
                .where(and_(
                    Invoice.entity_id == entity_id,
                    Invoice.status.in_([InvoiceStatus.PENDING, InvoiceStatus.OVERDUE, InvoiceStatus.PARTIAL]),
                ))
            )
            ar_total = Decimal(str(ar_result.scalar() or 0))
            await update_account("1130", ar_total, "invoices")
            results["summary"]["accounts_receivable"] = float(ar_total)
            
            # ==========================================
            # 3. SALES REVENUE (GL 4100) - Total invoiced
            # ==========================================
            sales_result = await self.db.execute(
                select(func.coalesce(func.sum(Invoice.subtotal), 0))
                .where(and_(
                    Invoice.entity_id == entity_id,
                    Invoice.status != InvoiceStatus.DRAFT,
                    Invoice.status != InvoiceStatus.CANCELLED,
                ))
            )
            sales_total = Decimal(str(sales_result.scalar() or 0))
            await update_account("4100", sales_total, "invoices")
            results["summary"]["sales_revenue"] = float(sales_total)
            
            # ==========================================
            # 4. VAT PAYABLE (GL 2130) - Output VAT from invoices
            # ==========================================
            vat_output_result = await self.db.execute(
                select(func.coalesce(func.sum(Invoice.vat_amount), 0))
                .where(and_(
                    Invoice.entity_id == entity_id,
                    Invoice.status != InvoiceStatus.DRAFT,
                    Invoice.status != InvoiceStatus.CANCELLED,
                ))
            )
            vat_output_total = Decimal(str(vat_output_result.scalar() or 0))
            await update_account("2130", vat_output_total, "invoices")
            results["summary"]["vat_payable"] = float(vat_output_total)
            
            # ==========================================
            # 5. ACCOUNTS PAYABLE (GL 2110) - From expense transactions
            # ==========================================
            from app.models.transaction import Transaction, TransactionType
            
            ap_result = await self.db.execute(
                select(func.coalesce(func.sum(Transaction.total_amount), 0))
                .where(and_(
                    Transaction.entity_id == entity_id,
                    Transaction.transaction_type == TransactionType.EXPENSE,
                ))
            )
            ap_total = Decimal(str(ap_result.scalar() or 0))
            await update_account("2110", ap_total, "transactions")
            results["summary"]["accounts_payable"] = float(ap_total)
            
            # ==========================================
            # 6. VAT RECEIVABLE (GL 1160) - Input VAT from expenses
            # ==========================================
            vat_input_result = await self.db.execute(
                select(func.coalesce(func.sum(Transaction.vat_amount), 0))
                .where(and_(
                    Transaction.entity_id == entity_id,
                    Transaction.transaction_type == TransactionType.EXPENSE,
                    Transaction.vat_recoverable == True,
                ))
            )
            vat_input_total = Decimal(str(vat_input_result.scalar() or 0))
            await update_account("1160", vat_input_total, "transactions")
            results["summary"]["vat_receivable"] = float(vat_input_total)
            
            # ==========================================
            # 7. FIXED ASSETS (GL 1210) & ACCUMULATED DEPRECIATION (GL 1220)
            # ==========================================
            from app.models.fixed_asset import FixedAsset, AssetStatus
            
            fa_cost_result = await self.db.execute(
                select(func.coalesce(func.sum(FixedAsset.acquisition_cost), 0))
                .where(and_(
                    FixedAsset.entity_id == entity_id,
                    FixedAsset.status != AssetStatus.DISPOSED,
                ))
            )
            fa_cost = Decimal(str(fa_cost_result.scalar() or 0))
            await update_account("1210", fa_cost, "fixed_assets")
            results["summary"]["fixed_assets_cost"] = float(fa_cost)
            
            fa_depr_result = await self.db.execute(
                select(func.coalesce(func.sum(FixedAsset.accumulated_depreciation), 0))
                .where(and_(
                    FixedAsset.entity_id == entity_id,
                    FixedAsset.status != AssetStatus.DISPOSED,
                ))
            )
            fa_depr = Decimal(str(fa_depr_result.scalar() or 0))
            # Accumulated depreciation is a contra-asset (credit balance)
            await update_account("1220", fa_depr, "fixed_assets")
            results["summary"]["accumulated_depreciation"] = float(fa_depr)
            
            # ==========================================
            # 8. PAYROLL LIABILITIES & EXPENSES
            # ==========================================
            from app.models.payroll import PayrollRun, PayrollStatus
            
            # Get totals from completed payroll runs
            payroll_result = await self.db.execute(
                select(
                    func.coalesce(func.sum(PayrollRun.total_gross_pay), 0).label("gross"),
                    func.coalesce(func.sum(PayrollRun.total_paye), 0).label("paye"),
                    func.coalesce(func.sum(PayrollRun.total_pension_employee + PayrollRun.total_pension_employer), 0).label("pension"),
                    func.coalesce(func.sum(PayrollRun.total_nhf), 0).label("nhf"),
                    func.coalesce(func.sum(PayrollRun.total_nsitf), 0).label("nsitf"),
                    func.coalesce(func.sum(PayrollRun.total_net_pay), 0).label("net"),
                    func.coalesce(func.sum(PayrollRun.total_pension_employer), 0).label("employer_pension"),
                )
                .where(and_(
                    PayrollRun.entity_id == entity_id,
                    PayrollRun.status.in_([PayrollStatus.COMPLETED, PayrollStatus.APPROVED]),
                ))
            )
            payroll = payroll_result.one()
            
            # Salary Expense (GL 5200)
            await update_account("5200", Decimal(str(payroll.gross)), "payroll")
            results["summary"]["salaries_expense"] = float(payroll.gross)
            
            # Employer Pension Expense (GL 5210)
            await update_account("5210", Decimal(str(payroll.employer_pension)), "payroll")
            results["summary"]["employer_pension_expense"] = float(payroll.employer_pension)
            
            # NSITF Expense (GL 5220)
            await update_account("5220", Decimal(str(payroll.nsitf)), "payroll")
            results["summary"]["nsitf_expense"] = float(payroll.nsitf)
            
            # PAYE Payable (GL 2150)
            await update_account("2150", Decimal(str(payroll.paye)), "payroll")
            results["summary"]["paye_payable"] = float(payroll.paye)
            
            # Pension Payable (GL 2160)
            await update_account("2160", Decimal(str(payroll.pension)), "payroll")
            results["summary"]["pension_payable"] = float(payroll.pension)
            
            # NHF Payable (GL 2170)
            await update_account("2170", Decimal(str(payroll.nhf)), "payroll")
            results["summary"]["nhf_payable"] = float(payroll.nhf)
            
            # NSITF Payable (GL 2180)
            await update_account("2180", Decimal(str(payroll.nsitf)), "payroll")
            results["summary"]["nsitf_payable"] = float(payroll.nsitf)
            
            # Salaries Payable (GL 2190)
            await update_account("2190", Decimal(str(payroll.net)), "payroll")
            results["summary"]["salaries_payable"] = float(payroll.net)
            
            # ==========================================
            # 9. BANK ACCOUNTS (GL 1120)
            # ==========================================
            from app.models.bank_reconciliation import BankAccount
            
            bank_result = await self.db.execute(
                select(func.coalesce(func.sum(BankAccount.current_balance), 0))
                .where(and_(
                    BankAccount.entity_id == entity_id,
                    BankAccount.is_active == True,
                ))
            )
            bank_total = Decimal(str(bank_result.scalar() or 0))
            await update_account("1120", bank_total, "bank_accounts")
            results["summary"]["bank_accounts"] = float(bank_total)
            
            # ==========================================
            # 10. COGS (GL 5100) - From inventory sold
            # Calculate based on sales * average margin (simplified)
            # In real system, would track actual COGS from stock movements
            # ==========================================
            from app.models.inventory import StockMovement, StockMovementType
            
            cogs_result = await self.db.execute(
                select(func.coalesce(func.sum(func.abs(StockMovement.quantity) * StockMovement.unit_cost), 0))
                .where(and_(
                    StockMovement.movement_type == StockMovementType.SALE,
                ))
            )
            cogs_total = Decimal(str(cogs_result.scalar() or 0))
            await update_account("5100", cogs_total, "inventory_movements")
            results["summary"]["cost_of_goods_sold"] = float(cogs_total)
            
            # Commit all changes
            await self.db.commit()
            
            results["success"] = True
            results["total_accounts_updated"] = len(results["accounts_updated"])
            
        except Exception as e:
            results["success"] = False
            results["errors"].append(str(e))
            await self.db.rollback()
        
        return results
    
    async def recalculate_gl_balances_from_journal_entries(
        self,
        entity_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Recalculate all GL account balances from posted journal entries.
        
        This is useful when balances get out of sync with journal entry lines.
        """
        results = {
            "entity_id": str(entity_id),
            "accounts_updated": [],
            "errors": [],
        }
        
        try:
            # Get all accounts
            accounts = await self.get_chart_of_accounts(entity_id, include_headers=False)
            
            for account in accounts:
                # Sum all posted journal entry lines for this account
                debit_result = await self.db.execute(
                    select(func.coalesce(func.sum(JournalEntryLine.debit_amount), 0))
                    .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
                    .where(and_(
                        JournalEntry.entity_id == entity_id,
                        JournalEntry.status == JournalEntryStatus.POSTED,
                        JournalEntryLine.account_id == account.id,
                    ))
                )
                total_debit = Decimal(str(debit_result.scalar() or 0))
                
                credit_result = await self.db.execute(
                    select(func.coalesce(func.sum(JournalEntryLine.credit_amount), 0))
                    .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
                    .where(and_(
                        JournalEntry.entity_id == entity_id,
                        JournalEntry.status == JournalEntryStatus.POSTED,
                        JournalEntryLine.account_id == account.id,
                    ))
                )
                total_credit = Decimal(str(credit_result.scalar() or 0))
                
                # Calculate balance based on normal balance
                if account.normal_balance == NormalBalance.DEBIT:
                    new_balance = total_debit - total_credit
                else:
                    new_balance = total_credit - total_debit
                
                old_balance = account.current_balance
                account.current_balance = new_balance
                account.ytd_debit = total_debit
                account.ytd_credit = total_credit
                
                results["accounts_updated"].append({
                    "account_code": account.account_code,
                    "account_name": account.account_name,
                    "old_balance": float(old_balance),
                    "new_balance": float(new_balance),
                    "total_debit": float(total_debit),
                    "total_credit": float(total_credit),
                })
            
            await self.db.commit()
            results["success"] = True
            results["total_accounts_updated"] = len(results["accounts_updated"])
            
        except Exception as e:
            results["success"] = False
            results["errors"].append(str(e))
            await self.db.rollback()
        
        return results
