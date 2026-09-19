"""
Tekvwa Pro Audit - GL Event Service

This service handles automatic GL posting when source documents are created/modified.
It ensures proper double-entry accounting is maintained across all source systems.

Option 2: Automatic GL posting for future transactions.

Usage:
    This service should be called from other services when documents are finalized:
    - InvoiceService.finalize_invoice() -> gl_event_service.post_invoice_to_gl()
    - PaymentService.process_payment() -> gl_event_service.post_payment_to_gl()
    - TransactionService.create_transaction() -> gl_event_service.post_transaction_to_gl()
    - PayrollService.complete_payroll_run() -> gl_event_service.post_payroll_to_gl()
    - FixedAssetService.run_depreciation() -> gl_event_service.post_depreciation_to_gl()
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Dict, Any, TYPE_CHECKING
from enum import Enum

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accounting import (
    ChartOfAccounts, JournalEntry, JournalEntryLine,
    JournalEntryStatus, JournalEntryType, FiscalPeriod,
    GLIntegrationLog,
)
from app.schemas.accounting import (
    JournalEntryCreate, JournalEntryLineCreate,
    GLPostingRequest, GLPostingResponse,
)


class GLSourceModule(str, Enum):
    """Source modules that can post to GL."""
    INVOICES = "INVOICES"
    RECEIPTS = "RECEIPTS"
    PAYMENTS = "PAYMENTS"
    TRANSACTIONS = "TRANSACTIONS"
    PAYROLL = "PAYROLL"
    FIXED_ASSETS = "FIXED_ASSETS"
    DEPRECIATION = "DEPRECIATION"
    INVENTORY = "INVENTORY"
    EXPENSE_CLAIMS = "EXPENSE_CLAIMS"
    BANK_RECONCILIATION = "BANK_RECONCILIATION"


# Nigerian Standard Chart of Accounts codes
GL_ACCOUNT_CODES = {
    # Assets
    "CASH": "1110",
    "BANK": "1120",
    "ACCOUNTS_RECEIVABLE": "1130",
    "INVENTORY": "1140",
    "PREPAID_EXPENSES": "1150",
    "VAT_RECEIVABLE": "1160",
    "WHT_RECEIVABLE": "1170",
    "PROPERTY_PLANT_EQUIPMENT": "1210",
    "ACCUMULATED_DEPRECIATION": "1220",
    
    # Liabilities
    "ACCOUNTS_PAYABLE": "2110",
    "ACCRUED_EXPENSES": "2120",
    "VAT_PAYABLE": "2130",
    "PAYE_PAYABLE": "2141",
    "PENSION_PAYABLE": "2142",
    "NHF_PAYABLE": "2143",
    
    # Equity
    "RETAINED_EARNINGS": "3100",
    
    # Revenue
    "SALES_REVENUE": "4100",
    "SERVICE_REVENUE": "4200",
    "OTHER_INCOME": "4900",
    
    # Expenses
    "COST_OF_GOODS_SOLD": "5100",
    "SALARY_EXPENSE": "6110",
    "RENT_EXPENSE": "6120",
    "UTILITIES_EXPENSE": "6130",
    "DEPRECIATION_EXPENSE": "6140",
    "OFFICE_SUPPLIES": "6150",
    "MISCELLANEOUS_EXPENSE": "6900",
}


class GLEventService:
    """
    Service for automatic GL posting when source documents change.
    
    This service ensures:
    1. Every transaction creates proper double-entry journal entries
    2. Entries are automatically posted to the GL
    3. Source documents are linked to their journal entries
    4. Duplicate posting is prevented
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self._account_cache: Dict[str, uuid.UUID] = {}
    
    async def get_account_by_code(
        self,
        entity_id: uuid.UUID,
        account_code: str,
    ) -> Optional[ChartOfAccounts]:
        """Get GL account by code with caching."""
        cache_key = f"{entity_id}:{account_code}"
        if cache_key in self._account_cache:
            account_id = self._account_cache[cache_key]
            result = await self.db.execute(
                select(ChartOfAccounts).where(ChartOfAccounts.id == account_id)
            )
            return result.scalar_one_or_none()
        
        result = await self.db.execute(
            select(ChartOfAccounts)
            .where(ChartOfAccounts.entity_id == entity_id)
            .where(ChartOfAccounts.account_code == account_code)
            .where(ChartOfAccounts.is_active == True)
        )
        account = result.scalar_one_or_none()
        if account:
            self._account_cache[cache_key] = account.id
        return account
    
    async def get_fiscal_period(
        self,
        entity_id: uuid.UUID,
        entry_date: date,
    ) -> Optional[FiscalPeriod]:
        """Get open fiscal period for date."""
        result = await self.db.execute(
            select(FiscalPeriod)
            .where(FiscalPeriod.entity_id == entity_id)
            .where(FiscalPeriod.start_date <= entry_date)
            .where(FiscalPeriod.end_date >= entry_date)
        )
        return result.scalar_one_or_none()
    
    async def is_already_posted(
        self,
        entity_id: uuid.UUID,
        source_module: str,
        source_document_id: uuid.UUID,
    ) -> bool:
        """Check if document has already been posted to GL."""
        result = await self.db.execute(
            select(GLIntegrationLog)
            .where(GLIntegrationLog.entity_id == entity_id)
            .where(GLIntegrationLog.source_module == source_module)
            .where(GLIntegrationLog.source_document_id == source_document_id)
            .where(GLIntegrationLog.is_reversed == False)
        )
        return result.scalar_one_or_none() is not None
    
    async def _generate_entry_number(
        self,
        entity_id: uuid.UUID,
        entry_date: date,
    ) -> str:
        """Generate unique entry number."""
        from sqlalchemy import func
        
        prefix = f"JE-{entry_date.strftime('%Y%m')}"
        result = await self.db.execute(
            select(func.count(JournalEntry.id))
            .where(JournalEntry.entity_id == entity_id)
            .where(JournalEntry.entry_number.like(f"{prefix}%"))
        )
        count = result.scalar() or 0
        return f"{prefix}-{count + 1:05d}"
    
    async def create_journal_entry(
        self,
        entity_id: uuid.UUID,
        entry_date: date,
        description: str,
        entry_type: JournalEntryType,
        lines: list,
        source_module: str,
        source_document_type: str,
        source_document_id: uuid.UUID,
        source_reference: str,
        user_id: Optional[uuid.UUID] = None,
    ) -> GLPostingResponse:
        """
        Create and post a journal entry from a source document.
        
        Args:
            entity_id: The business entity ID
            entry_date: Date of the entry
            description: Description of the entry
            entry_type: Type of journal entry (SALES, PAYMENT, etc.)
            lines: List of {account_id, debit_amount, credit_amount, description}
            source_module: Source system (INVOICES, TRANSACTIONS, etc.)
            source_document_type: Type within source (INVOICE, PAYMENT, etc.)
            source_document_id: UUID of source document
            source_reference: Human-readable reference
            user_id: User creating the entry
            
        Returns:
            GLPostingResponse with success status and entry details
        """
        # Check if already posted
        if await self.is_already_posted(entity_id, source_module, source_document_id):
            return GLPostingResponse(
                success=False,
                message="Document has already been posted to GL",
            )
        
        # Get fiscal period
        period = await self.get_fiscal_period(entity_id, entry_date)
        if not period:
            return GLPostingResponse(
                success=False,
                message=f"No fiscal period found for date {entry_date}",
            )
        
        # Calculate totals and validate balance
        total_debit = sum(Decimal(str(line.get("debit_amount", 0))) for line in lines)
        total_credit = sum(Decimal(str(line.get("credit_amount", 0))) for line in lines)
        
        if abs(total_debit - total_credit) > Decimal("0.01"):
            return GLPostingResponse(
                success=False,
                message=f"Entry is not balanced. Debit: {total_debit}, Credit: {total_credit}",
            )
        
        try:
            # Generate entry number
            entry_number = await self._generate_entry_number(entity_id, entry_date)
            
            # Create the journal entry
            entry = JournalEntry(
                entity_id=entity_id,
                fiscal_period_id=period.id,
                entry_number=entry_number,
                entry_date=entry_date,
                description=description,
                entry_type=entry_type,
                source_module=source_module,
                source_document_type=source_document_type,
                source_document_id=source_document_id,
                source_reference=source_reference,
                total_debit=total_debit,
                total_credit=total_credit,
                currency="NGN",
                status=JournalEntryStatus.POSTED,
                posted_at=datetime.utcnow(),
                created_by_id=user_id,
                updated_by_id=user_id,
            )
            self.db.add(entry)
            await self.db.flush()
            
            # Create lines
            for idx, line_data in enumerate(lines, 1):
                line = JournalEntryLine(
                    journal_entry_id=entry.id,
                    account_id=line_data["account_id"],
                    line_number=idx,
                    description=line_data.get("description", ""),
                    debit_amount=Decimal(str(line_data.get("debit_amount", 0))),
                    credit_amount=Decimal(str(line_data.get("credit_amount", 0))),
                )
                self.db.add(line)
            
            # Log the GL integration
            log = GLIntegrationLog(
                entity_id=entity_id,
                source_module=source_module,
                source_document_type=source_document_type,
                source_document_id=source_document_id,
                source_reference=source_reference,
                journal_entry_id=entry.id,
                posted_by_id=user_id,
            )
            self.db.add(log)
            await self.db.flush()
            
            return GLPostingResponse(
                success=True,
                journal_entry_id=entry.id,
                entry_number=entry_number,
                message="Successfully posted to GL",
            )
            
        except Exception as e:
            return GLPostingResponse(
                success=False,
                message=f"Error posting to GL: {str(e)}",
            )
    
    # =========================================================================
    # INVOICE GL POSTING
    # =========================================================================
    
    async def post_invoice_to_gl(
        self,
        entity_id: uuid.UUID,
        invoice_id: uuid.UUID,
        invoice_number: str,
        invoice_date: date,
        subtotal: Decimal,
        vat_amount: Optional[Decimal],
        total_amount: Decimal,
        user_id: Optional[uuid.UUID] = None,
    ) -> GLPostingResponse:
        """
        Post an invoice to GL.
        
        Creates journal entry:
            Dr. Accounts Receivable (total_amount)
                Cr. Sales Revenue (subtotal)
                Cr. VAT Payable (vat_amount)
        """
        # Get accounts
        ar_account = await self.get_account_by_code(entity_id, GL_ACCOUNT_CODES["ACCOUNTS_RECEIVABLE"])
        revenue_account = await self.get_account_by_code(entity_id, GL_ACCOUNT_CODES["SALES_REVENUE"])
        vat_account = await self.get_account_by_code(entity_id, GL_ACCOUNT_CODES["VAT_PAYABLE"])
        
        if not ar_account or not revenue_account:
            return GLPostingResponse(
                success=False,
                message="Missing required GL accounts (AR or Revenue)",
            )
        
        lines = [
            {
                "account_id": ar_account.id,
                "description": f"Invoice {invoice_number} - AR",
                "debit_amount": total_amount,
                "credit_amount": Decimal("0"),
            },
            {
                "account_id": revenue_account.id,
                "description": f"Invoice {invoice_number} - Revenue",
                "debit_amount": Decimal("0"),
                "credit_amount": subtotal,
            },
        ]
        
        if vat_amount and vat_amount > 0 and vat_account:
            lines.append({
                "account_id": vat_account.id,
                "description": f"Invoice {invoice_number} - VAT",
                "debit_amount": Decimal("0"),
                "credit_amount": vat_amount,
            })
        
        return await self.create_journal_entry(
            entity_id=entity_id,
            entry_date=invoice_date,
            description=f"Sales Invoice {invoice_number}",
            entry_type=JournalEntryType.SALES,
            lines=lines,
            source_module=GLSourceModule.INVOICES.value,
            source_document_type="INVOICE",
            source_document_id=invoice_id,
            source_reference=invoice_number,
            user_id=user_id,
        )
    
    async def post_invoice_payment_to_gl(
        self,
        entity_id: uuid.UUID,
        invoice_id: uuid.UUID,
        invoice_number: str,
        payment_date: date,
        payment_amount: Decimal,
        user_id: Optional[uuid.UUID] = None,
    ) -> GLPostingResponse:
        """
        Post invoice payment to GL.
        
        Creates journal entry:
            Dr. Bank (payment_amount)
                Cr. Accounts Receivable (payment_amount)
        """
        ar_account = await self.get_account_by_code(entity_id, GL_ACCOUNT_CODES["ACCOUNTS_RECEIVABLE"])
        bank_account = await self.get_account_by_code(entity_id, GL_ACCOUNT_CODES["BANK"])
        
        if not ar_account or not bank_account:
            return GLPostingResponse(
                success=False,
                message="Missing required GL accounts (AR or Bank)",
            )
        
        lines = [
            {
                "account_id": bank_account.id,
                "description": f"Payment for Invoice {invoice_number}",
                "debit_amount": payment_amount,
                "credit_amount": Decimal("0"),
            },
            {
                "account_id": ar_account.id,
                "description": f"Payment for Invoice {invoice_number}",
                "debit_amount": Decimal("0"),
                "credit_amount": payment_amount,
            },
        ]
        
        # Use a different source_document_type to allow multiple payments
        return await self.create_journal_entry(
            entity_id=entity_id,
            entry_date=payment_date,
            description=f"Payment Received - Invoice {invoice_number}",
            entry_type=JournalEntryType.RECEIPT,
            lines=lines,
            source_module=GLSourceModule.RECEIPTS.value,
            source_document_type="INVOICE_PAYMENT",
            source_document_id=invoice_id,
            source_reference=f"PMT-{invoice_number}",
            user_id=user_id,
        )
    
    # =========================================================================
    # TRANSACTION GL POSTING
    # =========================================================================
    
    async def post_expense_to_gl(
        self,
        entity_id: uuid.UUID,
        transaction_id: uuid.UUID,
        transaction_date: date,
        amount: Decimal,
        description: str,
        reference: Optional[str] = None,
        expense_account_code: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> GLPostingResponse:
        """
        Post an expense transaction to GL.
        
        Creates journal entry:
            Dr. Expense Account (amount)
                Cr. Bank (amount)
        """
        expense_code = expense_account_code or GL_ACCOUNT_CODES["MISCELLANEOUS_EXPENSE"]
        expense_account = await self.get_account_by_code(entity_id, expense_code)
        bank_account = await self.get_account_by_code(entity_id, GL_ACCOUNT_CODES["BANK"])
        
        if not expense_account or not bank_account:
            return GLPostingResponse(
                success=False,
                message="Missing required GL accounts (Expense or Bank)",
            )
        
        lines = [
            {
                "account_id": expense_account.id,
                "description": description,
                "debit_amount": abs(amount),
                "credit_amount": Decimal("0"),
            },
            {
                "account_id": bank_account.id,
                "description": description,
                "debit_amount": Decimal("0"),
                "credit_amount": abs(amount),
            },
        ]
        
        return await self.create_journal_entry(
            entity_id=entity_id,
            entry_date=transaction_date,
            description=description,
            entry_type=JournalEntryType.PAYMENT,
            lines=lines,
            source_module=GLSourceModule.TRANSACTIONS.value,
            source_document_type="EXPENSE",
            source_document_id=transaction_id,
            source_reference=reference or str(transaction_id)[:8],
            user_id=user_id,
        )
    
    async def post_income_to_gl(
        self,
        entity_id: uuid.UUID,
        transaction_id: uuid.UUID,
        transaction_date: date,
        amount: Decimal,
        description: str,
        reference: Optional[str] = None,
        income_account_code: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> GLPostingResponse:
        """
        Post an income transaction to GL.
        
        Creates journal entry:
            Dr. Bank (amount)
                Cr. Income Account (amount)
        """
        income_code = income_account_code or GL_ACCOUNT_CODES["SALES_REVENUE"]
        income_account = await self.get_account_by_code(entity_id, income_code)
        bank_account = await self.get_account_by_code(entity_id, GL_ACCOUNT_CODES["BANK"])
        
        if not income_account or not bank_account:
            return GLPostingResponse(
                success=False,
                message="Missing required GL accounts (Income or Bank)",
            )
        
        lines = [
            {
                "account_id": bank_account.id,
                "description": description,
                "debit_amount": abs(amount),
                "credit_amount": Decimal("0"),
            },
            {
                "account_id": income_account.id,
                "description": description,
                "debit_amount": Decimal("0"),
                "credit_amount": abs(amount),
            },
        ]
        
        return await self.create_journal_entry(
            entity_id=entity_id,
            entry_date=transaction_date,
            description=description,
            entry_type=JournalEntryType.RECEIPT,
            lines=lines,
            source_module=GLSourceModule.TRANSACTIONS.value,
            source_document_type="INCOME",
            source_document_id=transaction_id,
            source_reference=reference or str(transaction_id)[:8],
            user_id=user_id,
        )
    
    # =========================================================================
    # PAYROLL GL POSTING
    # =========================================================================
    
    async def post_payroll_to_gl(
        self,
        entity_id: uuid.UUID,
        payroll_run_id: uuid.UUID,
        run_number: str,
        payment_date: date,
        total_gross_pay: Decimal,
        total_net_pay: Decimal,
        total_paye: Optional[Decimal] = None,
        total_pension: Optional[Decimal] = None,
        total_nhf: Optional[Decimal] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> GLPostingResponse:
        """
        Post a completed payroll run to GL.
        
        Creates journal entry:
            Dr. Salary Expense (gross_pay)
                Cr. Bank (net_pay)
                Cr. PAYE Payable (paye)
                Cr. Pension Payable (pension)
                Cr. NHF Payable (nhf)
        """
        salary_account = await self.get_account_by_code(entity_id, GL_ACCOUNT_CODES["SALARY_EXPENSE"])
        bank_account = await self.get_account_by_code(entity_id, GL_ACCOUNT_CODES["BANK"])
        paye_account = await self.get_account_by_code(entity_id, GL_ACCOUNT_CODES["PAYE_PAYABLE"])
        pension_account = await self.get_account_by_code(entity_id, GL_ACCOUNT_CODES["PENSION_PAYABLE"])
        nhf_account = await self.get_account_by_code(entity_id, GL_ACCOUNT_CODES["NHF_PAYABLE"])
        
        if not salary_account or not bank_account:
            return GLPostingResponse(
                success=False,
                message="Missing required GL accounts (Salary or Bank)",
            )
        
        lines = [
            {
                "account_id": salary_account.id,
                "description": f"Payroll {run_number} - Gross Pay",
                "debit_amount": total_gross_pay,
                "credit_amount": Decimal("0"),
            },
            {
                "account_id": bank_account.id,
                "description": f"Payroll {run_number} - Net Pay",
                "debit_amount": Decimal("0"),
                "credit_amount": total_net_pay,
            },
        ]
        
        if total_paye and total_paye > 0 and paye_account:
            lines.append({
                "account_id": paye_account.id,
                "description": f"Payroll {run_number} - PAYE",
                "debit_amount": Decimal("0"),
                "credit_amount": total_paye,
            })
        
        if total_pension and total_pension > 0 and pension_account:
            lines.append({
                "account_id": pension_account.id,
                "description": f"Payroll {run_number} - Pension",
                "debit_amount": Decimal("0"),
                "credit_amount": total_pension,
            })
        
        if total_nhf and total_nhf > 0 and nhf_account:
            lines.append({
                "account_id": nhf_account.id,
                "description": f"Payroll {run_number} - NHF",
                "debit_amount": Decimal("0"),
                "credit_amount": total_nhf,
            })
        
        return await self.create_journal_entry(
            entity_id=entity_id,
            entry_date=payment_date,
            description=f"Payroll Run {run_number}",
            entry_type=JournalEntryType.PAYROLL,
            lines=lines,
            source_module=GLSourceModule.PAYROLL.value,
            source_document_type="PAYROLL_RUN",
            source_document_id=payroll_run_id,
            source_reference=run_number,
            user_id=user_id,
        )
    
    # =========================================================================
    # DEPRECIATION GL POSTING
    # =========================================================================
    
    async def post_depreciation_to_gl(
        self,
        entity_id: uuid.UUID,
        asset_id: uuid.UUID,
        asset_code: str,
        asset_name: str,
        depreciation_date: date,
        depreciation_amount: Decimal,
        user_id: Optional[uuid.UUID] = None,
    ) -> GLPostingResponse:
        """
        Post monthly depreciation to GL.
        
        Creates journal entry:
            Dr. Depreciation Expense (depreciation_amount)
                Cr. Accumulated Depreciation (depreciation_amount)
        """
        depr_expense = await self.get_account_by_code(entity_id, GL_ACCOUNT_CODES["DEPRECIATION_EXPENSE"])
        accum_depr = await self.get_account_by_code(entity_id, GL_ACCOUNT_CODES["ACCUMULATED_DEPRECIATION"])
        
        if not depr_expense or not accum_depr:
            return GLPostingResponse(
                success=False,
                message="Missing required GL accounts (Depreciation Expense or Accumulated Depreciation)",
            )
        
        lines = [
            {
                "account_id": depr_expense.id,
                "description": f"Depreciation: {asset_name}",
                "debit_amount": depreciation_amount,
                "credit_amount": Decimal("0"),
            },
            {
                "account_id": accum_depr.id,
                "description": f"Depreciation: {asset_name}",
                "debit_amount": Decimal("0"),
                "credit_amount": depreciation_amount,
            },
        ]
        
        return await self.create_journal_entry(
            entity_id=entity_id,
            entry_date=depreciation_date,
            description=f"Monthly Depreciation: {asset_name}",
            entry_type=JournalEntryType.DEPRECIATION,
            lines=lines,
            source_module=GLSourceModule.DEPRECIATION.value,
            source_document_type="DEPRECIATION",
            source_document_id=asset_id,
            source_reference=f"DEPR-{asset_code}-{depreciation_date.strftime('%Y%m')}",
            user_id=user_id,
        )


# Factory function for dependency injection
def get_gl_event_service(db: AsyncSession) -> GLEventService:
    """Create a new GLEventService instance."""
    return GLEventService(db)
