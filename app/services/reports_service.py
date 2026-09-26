"""
Tekvwa Pro Audit - Reports Service

Financial and tax reporting service.

Reports:
- Profit & Loss Statement
- Balance Sheet (simplified)
- Cash Flow Statement
- VAT Return Report
- PAYE Summary
- WHT Summary
- CIT Calculation Report
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction, TransactionType
from app.models.invoice import Invoice, InvoiceStatus
from app.models.category import Category


class ReportsService:
    """Service for generating financial and tax reports."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # ===========================================
    # PROFIT & LOSS REPORT
    # ===========================================
    
    async def generate_profit_loss(
        self,
        entity_id: uuid.UUID,
        start_date: date,
        end_date: date,
        include_details: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate Profit & Loss (Income Statement) report.
        
        Structure:
        - Revenue
          - Sales/Service Income
          - Other Income
        - Less: Cost of Sales
        - Gross Profit
        - Less: Operating Expenses
        - Operating Profit
        - Less: Tax
        - Net Profit
        """
        # Get income by category
        income_result = await self.db.execute(
            select(
                Category.name.label("category"),
                func.sum(Transaction.amount).label("total"),
            )
            .join(Category, Transaction.category_id == Category.id, isouter=True)
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_type == TransactionType.INCOME)
            .where(Transaction.transaction_date >= start_date)
            .where(Transaction.transaction_date <= end_date)
            .group_by(Category.name)
        )
        income_categories = {
            row.category or "Uncategorized": float(row.total)
            for row in income_result
        }
        total_income = sum(income_categories.values())
        
        # Get expenses by category
        expense_result = await self.db.execute(
            select(
                Category.name.label("category"),
                Category.wren_default.label("wren_status"),
                func.sum(Transaction.amount).label("total"),
            )
            .join(Category, Transaction.category_id == Category.id, isouter=True)
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_type == TransactionType.EXPENSE)
            .where(Transaction.transaction_date >= start_date)
            .where(Transaction.transaction_date <= end_date)
            .group_by(Category.name, Category.wren_default)
        )
        expense_categories = {}
        for row in expense_result:
            cat_name = row.category or "Uncategorized"
            # wren_status is a boolean (True=tax deductible), not an enum
            wren_status = row.wren_status if row.wren_status is not None else False
            expense_categories[cat_name] = {
                "total": float(row.total),
                "wren_status": "deductible" if wren_status else "non-deductible",
            }
        total_expenses = sum(exp["total"] for exp in expense_categories.values())
        
        # Calculate VAT
        vat_result = await self.db.execute(
            select(
                func.coalesce(func.sum(Transaction.vat_amount), 0).label("total_vat"),
            )
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_date >= start_date)
            .where(Transaction.transaction_date <= end_date)
        )
        total_vat = float(vat_result.scalar() or 0)
        
        # Calculate net profit
        gross_profit = total_income - total_expenses
        
        report = {
            "report_type": "profit_loss",
            "entity_id": str(entity_id),
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "generated_at": datetime.utcnow().isoformat(),
            "summary": {
                "total_revenue": total_income,
                "total_expenses": total_expenses,
                "gross_profit": gross_profit,
                "vat_collected": total_vat,
                "net_profit": gross_profit,
            },
            "revenue": {
                "categories": income_categories,
                "total": total_income,
            },
            "expenses": {
                "categories": expense_categories,
                "total": total_expenses,
            },
        }
        
        if include_details:
            # Add transaction details
            income_transactions = await self._get_transactions_summary(
                entity_id, start_date, end_date, TransactionType.INCOME
            )
            expense_transactions = await self._get_transactions_summary(
                entity_id, start_date, end_date, TransactionType.EXPENSE
            )
            report["details"] = {
                "income_transactions": income_transactions,
                "expense_transactions": expense_transactions,
            }
        
        return report
    
    async def _get_transactions_summary(
        self,
        entity_id: uuid.UUID,
        start_date: date,
        end_date: date,
        transaction_type: TransactionType,
    ) -> List[Dict[str, Any]]:
        """Get transaction summary for report details."""
        result = await self.db.execute(
            select(Transaction)
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_type == transaction_type)
            .where(Transaction.transaction_date >= start_date)
            .where(Transaction.transaction_date <= end_date)
            .order_by(Transaction.transaction_date)
            .limit(100)
        )
        
        return [
            {
                "id": str(t.id),
                "date": t.transaction_date.isoformat(),
                "description": t.description,
                "amount": float(t.amount),
                "vat_amount": float(t.vat_amount) if t.vat_amount else 0,
            }
            for t in result.scalars()
        ]
    
    # ===========================================
    # CASH FLOW REPORT
    # ===========================================
    
    async def generate_cash_flow(
        self,
        entity_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """
        Generate Cash Flow Statement.
        
        Simplified format:
        - Cash from Operating Activities
        - Cash from Investing Activities
        - Cash from Financing Activities
        - Net Change in Cash
        """
        # Operating activities (income minus expenses)
        income_total = await self.db.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_type == TransactionType.INCOME)
            .where(Transaction.transaction_date >= start_date)
            .where(Transaction.transaction_date <= end_date)
        ) or 0
        
        expense_total = await self.db.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_type == TransactionType.EXPENSE)
            .where(Transaction.transaction_date >= start_date)
            .where(Transaction.transaction_date <= end_date)
        ) or 0
        
        # Receivables (invoices)
        invoiced_total = await self.db.scalar(
            select(func.coalesce(func.sum(Invoice.total_amount), 0))
            .where(Invoice.entity_id == entity_id)
            .where(Invoice.invoice_date >= start_date)
            .where(Invoice.invoice_date <= end_date)
            .where(Invoice.status.in_([InvoiceStatus.ACCEPTED, InvoiceStatus.PAID]))
        ) or 0
        
        collected_total = await self.db.scalar(
            select(func.coalesce(func.sum(Invoice.amount_paid), 0))
            .where(Invoice.entity_id == entity_id)
            .where(Invoice.invoice_date >= start_date)
            .where(Invoice.invoice_date <= end_date)
        ) or 0
        
        operating_cash_flow = float(income_total) - float(expense_total)
        receivables_change = float(invoiced_total) - float(collected_total)
        
        return {
            "report_type": "cash_flow",
            "entity_id": str(entity_id),
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "generated_at": datetime.utcnow().isoformat(),
            "operating_activities": {
                "cash_received": float(income_total),
                "cash_paid": float(expense_total),
                "net_operating": operating_cash_flow,
            },
            "receivables": {
                "invoiced": float(invoiced_total),
                "collected": float(collected_total),
                "outstanding": receivables_change,
            },
            "summary": {
                "net_cash_flow": operating_cash_flow,
            },
        }
    
    # ===========================================
    # INCOME/EXPENSE SUMMARY
    # ===========================================
    
    async def generate_summary(
        self,
        entity_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """Generate income/expense summary for dashboard."""
        # Monthly breakdown
        monthly_result = await self.db.execute(
            select(
                func.date_trunc('month', Transaction.transaction_date).label("month"),
                Transaction.transaction_type,
                func.sum(Transaction.amount).label("total"),
            )
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_date >= start_date)
            .where(Transaction.transaction_date <= end_date)
            .group_by(
                func.date_trunc('month', Transaction.transaction_date),
                Transaction.transaction_type,
            )
            .order_by(func.date_trunc('month', Transaction.transaction_date))
        )
        
        monthly_data = {}
        for row in monthly_result:
            month_str = row.month.strftime("%Y-%m")
            if month_str not in monthly_data:
                monthly_data[month_str] = {"income": 0, "expense": 0}
            
            if row.transaction_type == TransactionType.INCOME:
                monthly_data[month_str]["income"] = float(row.total)
            else:
                monthly_data[month_str]["expense"] = float(row.total)
        
        # Calculate totals
        total_income = sum(m["income"] for m in monthly_data.values())
        total_expense = sum(m["expense"] for m in monthly_data.values())
        
        return {
            "entity_id": str(entity_id),
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "totals": {
                "income": total_income,
                "expense": total_expense,
                "net": total_income - total_expense,
            },
            "monthly": monthly_data,
        }
    
    # ===========================================
    # TAX REPORTS
    # ===========================================
    
    async def generate_vat_return(
        self,
        entity_id: uuid.UUID,
        year: int,
        month: int,
    ) -> Dict[str, Any]:
        """Generate VAT return report for FIRS filing."""
        from calendar import monthrange
        
        start_date = date(year, month, 1)
        _, last_day = monthrange(year, month)
        end_date = date(year, month, last_day)
        
        # Output VAT (from invoices)
        output_vat = await self.db.scalar(
            select(func.coalesce(func.sum(Invoice.vat_amount), 0))
            .where(Invoice.entity_id == entity_id)
            .where(Invoice.invoice_date >= start_date)
            .where(Invoice.invoice_date <= end_date)
            .where(Invoice.status.in_([InvoiceStatus.ACCEPTED, InvoiceStatus.PAID]))
        ) or 0
        
        # Input VAT (from expenses)
        input_vat = await self.db.scalar(
            select(func.coalesce(func.sum(Transaction.vat_amount), 0))
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_type == TransactionType.EXPENSE)
            .where(Transaction.transaction_date >= start_date)
            .where(Transaction.transaction_date <= end_date)
        ) or 0
        
        net_vat = float(output_vat) - float(input_vat)
        
        return {
            "report_type": "vat_return",
            "entity_id": str(entity_id),
            "period": f"{year}-{month:02d}",
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "generated_at": datetime.utcnow().isoformat(),
            "output_vat": {
                "description": "VAT collected on sales",
                "amount": float(output_vat),
            },
            "input_vat": {
                "description": "VAT paid on purchases",
                "amount": float(input_vat),
            },
            "net_vat_payable": net_vat,
            "is_refund": net_vat < 0,
            "filing_deadline": date(year, month + 1 if month < 12 else 1, 21).isoformat(),
        }
    
    async def generate_paye_summary(
        self,
        entity_id: uuid.UUID,
        year: int,
        month: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Generate PAYE summary report."""
        from app.models.tax import PAYERecord
        
        query = select(
            func.count(PAYERecord.id).label("employee_count"),
            func.sum(PAYERecord.gross_salary).label("total_gross"),
            func.sum(PAYERecord.paye_tax).label("total_paye"),
        ).where(PAYERecord.entity_id == entity_id).where(PAYERecord.period_year == year)
        
        if month:
            query = query.where(PAYERecord.period_month == month)
        
        result = await self.db.execute(query)
        row = result.one()
        
        return {
            "report_type": "paye_summary",
            "entity_id": str(entity_id),
            "year": year,
            "month": month,
            "generated_at": datetime.utcnow().isoformat(),
            "summary": {
                "employee_count": row.employee_count or 0,
                "total_gross_salary": float(row.total_gross or 0),
                "total_paye_tax": float(row.total_paye or 0),
            },
        }
    
    async def generate_wht_summary(
        self,
        entity_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """Generate WHT summary report."""
        # Get WHT from expense transactions
        result = await self.db.execute(
            select(
                func.count(Transaction.id).label("count"),
                func.sum(Transaction.wht_amount).label("total_wht"),
                func.sum(Transaction.amount).label("total_gross"),
            )
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_type == TransactionType.EXPENSE)
            .where(Transaction.transaction_date >= start_date)
            .where(Transaction.transaction_date <= end_date)
            .where(Transaction.wht_amount > 0)
        )
        row = result.one()
        
        return {
            "report_type": "wht_summary",
            "entity_id": str(entity_id),
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "generated_at": datetime.utcnow().isoformat(),
            "summary": {
                "transaction_count": row.count or 0,
                "total_gross_payments": float(row.total_gross or 0),
                "total_wht_deducted": float(row.total_wht or 0),
            },
        }
    
    async def generate_cit_report(
        self,
        entity_id: uuid.UUID,
        fiscal_year: int,
    ) -> Dict[str, Any]:
        """Generate CIT calculation report."""
        start_date = date(fiscal_year, 1, 1)
        end_date = date(fiscal_year, 12, 31)
        
        # Get P&L data
        pnl = await self.generate_profit_loss(entity_id, start_date, end_date)
        
        turnover = pnl["summary"]["total_revenue"]
        profit = pnl["summary"]["gross_profit"]
        
        # Calculate CIT
        from app.services.tax_calculators.cit_service import CITCalculator
        
        cit_result = CITCalculator.calculate_cit(
            gross_turnover=turnover,
            assessable_profit=profit,
        )
        
        return {
            "report_type": "cit_calculation",
            "entity_id": str(entity_id),
            "fiscal_year": fiscal_year,
            "generated_at": datetime.utcnow().isoformat(),
            "financial_summary": {
                "gross_turnover": turnover,
                "total_expenses": pnl["summary"]["total_expenses"],
                "assessable_profit": profit,
            },
            "cit_calculation": cit_result,
        }
    
    # ===========================================
    # DASHBOARD METRICS
    # ===========================================
    
    async def get_dashboard_metrics(
        self,
        entity_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Get dashboard metrics for an entity."""
        today = date.today()
        month_start = date(today.year, today.month, 1)
        year_start = date(today.year, 1, 1)
        
        # This month totals
        month_income = await self.db.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_type == TransactionType.INCOME)
            .where(Transaction.transaction_date >= month_start)
        ) or 0
        
        month_expense = await self.db.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_type == TransactionType.EXPENSE)
            .where(Transaction.transaction_date >= month_start)
        ) or 0
        
        # Year to date totals
        ytd_income = await self.db.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_type == TransactionType.INCOME)
            .where(Transaction.transaction_date >= year_start)
        ) or 0
        
        ytd_expense = await self.db.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_type == TransactionType.EXPENSE)
            .where(Transaction.transaction_date >= year_start)
        ) or 0
        
        # Outstanding invoices
        outstanding = await self.db.scalar(
            select(func.coalesce(
                func.sum(Invoice.total_amount - Invoice.amount_paid), 0
            ))
            .where(Invoice.entity_id == entity_id)
            .where(Invoice.status == InvoiceStatus.ACCEPTED)
        ) or 0
        
        # Overdue invoices
        overdue = await self.db.scalar(
            select(func.coalesce(
                func.sum(Invoice.total_amount - Invoice.amount_paid), 0
            ))
            .where(Invoice.entity_id == entity_id)
            .where(Invoice.status == InvoiceStatus.ACCEPTED)
            .where(Invoice.due_date < today)
        ) or 0
        
        return {
            "entity_id": str(entity_id),
            "generated_at": datetime.utcnow().isoformat(),
            "this_month": {
                "income": float(month_income),
                "expense": float(month_expense),
                "net": float(month_income) - float(month_expense),
            },
            "year_to_date": {
                "income": float(ytd_income),
                "expense": float(ytd_expense),
                "net": float(ytd_income) - float(ytd_expense),
            },
            "receivables": {
                "outstanding": float(outstanding),
                "overdue": float(overdue),
            },
        }

    # ===========================================
    # TRIAL BALANCE
    # ===========================================

    async def generate_trial_balance(
        self,
        entity_id: uuid.UUID,
        as_of_date: date,
    ) -> Dict[str, Any]:
        """
        Generate Trial Balance report.
        
        Trial balance shows all accounts with their debit/credit balances.
        Total debits should equal total credits.
        """
        # Get income totals (credit)
        income_total = await self.db.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_type == TransactionType.INCOME)
            .where(Transaction.transaction_date <= as_of_date)
        ) or 0
        
        # Get expense totals (debit)
        expense_total = await self.db.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_type == TransactionType.EXPENSE)
            .where(Transaction.transaction_date <= as_of_date)
        ) or 0
        
        # Get VAT collected (credit - liability)
        vat_collected = await self.db.scalar(
            select(func.coalesce(func.sum(Invoice.vat_amount), 0))
            .where(Invoice.entity_id == entity_id)
            .where(Invoice.invoice_date <= as_of_date)
            .where(Invoice.status.in_([InvoiceStatus.ACCEPTED, InvoiceStatus.PAID]))
        ) or 0
        
        # Get VAT paid (debit - asset)
        vat_paid = await self.db.scalar(
            select(func.coalesce(func.sum(Transaction.vat_amount), 0))
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_type == TransactionType.EXPENSE)
            .where(Transaction.transaction_date <= as_of_date)
        ) or 0
        
        # Accounts receivable (debit)
        receivables = await self.db.scalar(
            select(func.coalesce(
                func.sum(Invoice.total_amount - Invoice.amount_paid), 0
            ))
            .where(Invoice.entity_id == entity_id)
            .where(Invoice.status == InvoiceStatus.ACCEPTED)
            .where(Invoice.invoice_date <= as_of_date)
        ) or 0
        
        # Cash/Bank (debit - assets = income - expenses + collections - receivables)
        cash_received = await self.db.scalar(
            select(func.coalesce(func.sum(Invoice.amount_paid), 0))
            .where(Invoice.entity_id == entity_id)
            .where(Invoice.invoice_date <= as_of_date)
        ) or 0
        
        # Retained earnings (credit)
        retained_earnings = float(income_total) - float(expense_total)
        
        # Build trial balance accounts
        accounts = []
        total_debit = Decimal(0)
        total_credit = Decimal(0)
        
        # Asset accounts (Debit)
        if cash_received > 0:
            accounts.append({
                "account": "Cash/Bank",
                "type": "Asset",
                "debit": float(cash_received),
                "credit": 0,
            })
            total_debit += Decimal(str(cash_received))
        
        if receivables > 0:
            accounts.append({
                "account": "Accounts Receivable",
                "type": "Asset",
                "debit": float(receivables),
                "credit": 0,
            })
            total_debit += Decimal(str(receivables))
        
        if vat_paid > 0:
            accounts.append({
                "account": "VAT Recoverable",
                "type": "Asset",
                "debit": float(vat_paid),
                "credit": 0,
            })
            total_debit += Decimal(str(vat_paid))
        
        # Liability accounts (Credit)
        if vat_collected > 0:
            accounts.append({
                "account": "VAT Payable",
                "type": "Liability",
                "debit": 0,
                "credit": float(vat_collected),
            })
            total_credit += Decimal(str(vat_collected))
        
        # Equity accounts (Credit)
        if retained_earnings != 0:
            if retained_earnings > 0:
                accounts.append({
                    "account": "Retained Earnings",
                    "type": "Equity",
                    "debit": 0,
                    "credit": retained_earnings,
                })
                total_credit += Decimal(str(retained_earnings))
            else:
                accounts.append({
                    "account": "Retained Earnings",
                    "type": "Equity",
                    "debit": abs(retained_earnings),
                    "credit": 0,
                })
                total_debit += Decimal(str(abs(retained_earnings)))
        
        # Revenue accounts (Credit)
        if income_total > 0:
            accounts.append({
                "account": "Revenue/Sales",
                "type": "Revenue",
                "debit": 0,
                "credit": float(income_total),
            })
            total_credit += Decimal(str(income_total))
        
        # Expense accounts (Debit)
        if expense_total > 0:
            accounts.append({
                "account": "Operating Expenses",
                "type": "Expense",
                "debit": float(expense_total),
                "credit": 0,
            })
            total_debit += Decimal(str(expense_total))
        
        return {
            "report_type": "trial_balance",
            "entity_id": str(entity_id),
            "as_of_date": as_of_date.isoformat(),
            "generated_at": datetime.utcnow().isoformat(),
            "accounts": accounts,
            "totals": {
                "total_debit": float(total_debit),
                "total_credit": float(total_credit),
                "is_balanced": abs(float(total_debit) - float(total_credit)) < 0.01,
            },
        }

    # ===========================================
    # BALANCE SHEET
    # ===========================================

    async def generate_balance_sheet(
        self,
        entity_id: uuid.UUID,
        as_of_date: date,
    ) -> Dict[str, Any]:
        """
        Generate Balance Sheet report.
        
        Assets = Liabilities + Owner's Equity
        """
        from app.models.fixed_asset import FixedAsset, AssetStatus
        
        # Current Assets
        # Cash/Bank approximation (collected invoices minus expenses)
        cash_received = await self.db.scalar(
            select(func.coalesce(func.sum(Invoice.amount_paid), 0))
            .where(Invoice.entity_id == entity_id)
            .where(Invoice.invoice_date <= as_of_date)
        ) or 0
        
        expense_total = await self.db.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_type == TransactionType.EXPENSE)
            .where(Transaction.transaction_date <= as_of_date)
        ) or 0
        
        cash_balance = float(cash_received) - float(expense_total)
        
        # Accounts Receivable
        receivables = await self.db.scalar(
            select(func.coalesce(
                func.sum(Invoice.total_amount - Invoice.amount_paid), 0
            ))
            .where(Invoice.entity_id == entity_id)
            .where(Invoice.status == InvoiceStatus.ACCEPTED)
            .where(Invoice.invoice_date <= as_of_date)
        ) or 0
        
        # VAT Recoverable
        vat_recoverable = await self.db.scalar(
            select(func.coalesce(func.sum(Transaction.vat_amount), 0))
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_type == TransactionType.EXPENSE)
            .where(Transaction.transaction_date <= as_of_date)
        ) or 0
        
        total_current_assets = cash_balance + float(receivables) + float(vat_recoverable)
        
        # Fixed Assets (Net Book Value)
        try:
            fixed_assets_result = await self.db.execute(
                select(
                    func.coalesce(func.sum(FixedAsset.acquisition_cost), 0).label("cost"),
                    func.coalesce(func.sum(FixedAsset.accumulated_depreciation), 0).label("depreciation"),
                )
                .where(FixedAsset.entity_id == entity_id)
                .where(FixedAsset.status == AssetStatus.ACTIVE)
            )
            row = fixed_assets_result.one()
            fixed_assets_cost = float(row.cost)
            accumulated_depreciation = float(row.depreciation)
            fixed_assets_nbv = fixed_assets_cost - accumulated_depreciation
        except Exception:
            fixed_assets_cost = 0
            accumulated_depreciation = 0
            fixed_assets_nbv = 0
        
        total_assets = total_current_assets + fixed_assets_nbv
        
        # Liabilities
        # VAT Payable
        vat_payable = await self.db.scalar(
            select(func.coalesce(func.sum(Invoice.vat_amount), 0))
            .where(Invoice.entity_id == entity_id)
            .where(Invoice.invoice_date <= as_of_date)
            .where(Invoice.status.in_([InvoiceStatus.ACCEPTED, InvoiceStatus.PAID]))
        ) or 0
        
        total_liabilities = float(vat_payable) - float(vat_recoverable)  # Net VAT liability
        if total_liabilities < 0:
            total_liabilities = 0
        
        # Owner's Equity
        income_total = await self.db.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(Transaction.entity_id == entity_id)
            .where(Transaction.transaction_type == TransactionType.INCOME)
            .where(Transaction.transaction_date <= as_of_date)
        ) or 0
        
        net_income = float(income_total) - float(expense_total)
        owners_equity = total_assets - total_liabilities
        
        return {
            "report_type": "balance_sheet",
            "entity_id": str(entity_id),
            "as_of_date": as_of_date.isoformat(),
            "generated_at": datetime.utcnow().isoformat(),
            "assets": {
                "current_assets": {
                    "cash_and_bank": max(0, cash_balance),
                    "accounts_receivable": float(receivables),
                    "vat_recoverable": float(vat_recoverable),
                    "total": max(0, total_current_assets),
                },
                "fixed_assets": {
                    "cost": fixed_assets_cost,
                    "accumulated_depreciation": accumulated_depreciation,
                    "net_book_value": fixed_assets_nbv,
                },
                "total_assets": max(0, total_assets),
            },
            "liabilities": {
                "current_liabilities": {
                    "vat_payable": max(0, total_liabilities),
                    "total": max(0, total_liabilities),
                },
                "total_liabilities": max(0, total_liabilities),
            },
            "equity": {
                "retained_earnings": net_income,
                "total_equity": owners_equity,
            },
            "validation": {
                "assets_equal_liabilities_plus_equity": abs(total_assets - (total_liabilities + owners_equity)) < 0.01,
            },
        }

    # ===========================================
    # FIXED ASSET REGISTER REPORT
    # ===========================================

    async def generate_fixed_assets_report(
        self,
        entity_id: uuid.UUID,
        as_of_date: date,
    ) -> Dict[str, Any]:
        """
        Generate Fixed Asset Register report.
        """
        from app.models.fixed_asset import FixedAsset, AssetStatus, DepreciationMethod
        
        result = await self.db.execute(
            select(FixedAsset)
            .where(FixedAsset.entity_id == entity_id)
            .order_by(FixedAsset.acquisition_date.desc())
        )
        assets = result.scalars().all()
        
        asset_list = []
        total_cost = Decimal(0)
        total_depreciation = Decimal(0)
        total_nbv = Decimal(0)
        
        for asset in assets:
            nbv = asset.acquisition_cost - asset.accumulated_depreciation
            asset_list.append({
                "id": str(asset.id),
                "name": asset.name,
                "asset_type": asset.category.value if asset.category else None,
                "acquisition_date": asset.acquisition_date.isoformat(),
                "acquisition_cost": float(asset.acquisition_cost),
                "depreciation_method": asset.depreciation_method.value if asset.depreciation_method else None,
                "useful_life_years": asset.useful_life_years,
                "depreciation_rate": float(asset.depreciation_rate) if asset.depreciation_rate else None,
                "accumulated_depreciation": float(asset.accumulated_depreciation),
                "net_book_value": float(nbv),
                "status": asset.status.value if asset.status else "active",
                "disposal_date": asset.disposal_date.isoformat() if asset.disposal_date else None,
                "disposal_amount": float(asset.disposal_amount) if asset.disposal_amount else None,
            })
            
            if asset.status == AssetStatus.ACTIVE:
                total_cost += asset.acquisition_cost
                total_depreciation += asset.accumulated_depreciation
                total_nbv += nbv
        
        return {
            "report_type": "fixed_asset_register",
            "entity_id": str(entity_id),
            "as_of_date": as_of_date.isoformat(),
            "generated_at": datetime.utcnow().isoformat(),
            "assets": asset_list,
            "summary": {
                "total_assets": len([a for a in assets if a.status == AssetStatus.ACTIVE]),
                "total_acquisition_cost": float(total_cost),
                "total_accumulated_depreciation": float(total_depreciation),
                "total_net_book_value": float(total_nbv),
                "disposed_assets": len([a for a in assets if a.status == AssetStatus.DISPOSED]),
            },
        }

    # ===========================================
    # PDF EXPORTS
    # ===========================================

    async def export_profit_loss_pdf(
        self,
        entity_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> bytes:
        """
        Export Profit & Loss report as PDF.
        """
        report = await self.generate_profit_loss(entity_id, start_date, end_date)
        return self._generate_pdf_report(
            title="Profit & Loss Statement",
            period=f"{start_date} to {end_date}",
            data=report,
        )

    async def export_trial_balance_pdf(
        self,
        entity_id: uuid.UUID,
        as_of_date: date,
    ) -> bytes:
        """
        Export Trial Balance report as PDF.
        """
        report = await self.generate_trial_balance(entity_id, as_of_date)
        return self._generate_pdf_report(
            title="Trial Balance",
            period=f"As of {as_of_date}",
            data=report,
        )

    async def export_fixed_assets_pdf(
        self,
        entity_id: uuid.UUID,
        as_of_date: date,
    ) -> bytes:
        """
        Export Fixed Asset Register as PDF.
        """
        report = await self.generate_fixed_assets_report(entity_id, as_of_date)
        return self._generate_pdf_report(
            title="Fixed Asset Register",
            period=f"As of {as_of_date}",
            data=report,
        )

    def _generate_pdf_report(
        self,
        title: str,
        period: str,
        data: Dict[str, Any],
    ) -> bytes:
        """
        Generate a PDF report from data.
        
        Uses ReportLab for PDF generation.
        """
        from io import BytesIO
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=12,
            textColor=colors.HexColor('#166534'),
        )
        
        elements = []
        
        # Title
        elements.append(Paragraph(title, title_style))
        elements.append(Paragraph(f"<b>Period:</b> {period}", styles['Normal']))
        elements.append(Paragraph(f"<b>Generated:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", styles['Normal']))
        elements.append(Spacer(1, 20))
        
        # Report-specific content
        if data.get("report_type") == "profit_loss":
            elements.extend(self._build_pnl_pdf_content(data, styles))
        elif data.get("report_type") == "trial_balance":
            elements.extend(self._build_trial_balance_pdf_content(data, styles))
        elif data.get("report_type") == "fixed_asset_register":
            elements.extend(self._build_fixed_assets_pdf_content(data, styles))
        
        # Footer
        elements.append(Spacer(1, 30))
        elements.append(Paragraph(
            "Tekvwa Pro Audit - Nigeria's Premier Tax Compliance Platform",
            ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.grey)
        ))
        
        doc.build(elements)
        return buffer.getvalue()

    def _build_pnl_pdf_content(self, data: Dict[str, Any], styles) -> List:
        """Build P&L PDF content."""
        from reportlab.lib import colors
        from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
        
        elements = []
        summary = data.get("summary", {})
        
        # Summary table
        summary_data = [
            ["Total Revenue", f"₦{summary.get('total_revenue', 0):,.2f}"],
            ["Total Expenses", f"₦{summary.get('total_expenses', 0):,.2f}"],
            ["Net Profit", f"₦{summary.get('net_profit', 0):,.2f}"],
        ]
        
        table = Table(summary_data, colWidths=[200, 150])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f0fdf4')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        
        elements.append(Paragraph("<b>Summary</b>", styles['Heading2']))
        elements.append(table)
        
        return elements

    def _build_trial_balance_pdf_content(self, data: Dict[str, Any], styles) -> List:
        """Build Trial Balance PDF content."""
        from reportlab.lib import colors
        from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
        
        elements = []
        accounts = data.get("accounts", [])
        totals = data.get("totals", {})
        
        # Accounts table
        table_data = [["Account", "Type", "Debit (₦)", "Credit (₦)"]]
        for acc in accounts:
            table_data.append([
                acc.get("account", ""),
                acc.get("type", ""),
                f"{acc.get('debit', 0):,.2f}" if acc.get('debit', 0) > 0 else "-",
                f"{acc.get('credit', 0):,.2f}" if acc.get('credit', 0) > 0 else "-",
            ])
        
        # Totals row
        table_data.append([
            "TOTALS",
            "",
            f"{totals.get('total_debit', 0):,.2f}",
            f"{totals.get('total_credit', 0):,.2f}",
        ])
        
        table = Table(table_data, colWidths=[150, 80, 100, 100])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#166534')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f0fdf4')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 10))
        
        balanced_text = "Balanced" if totals.get("is_balanced") else "Not Balanced"
        elements.append(Paragraph(f"<b>Status:</b> {balanced_text}", styles['Normal']))
        
        return elements

    def _build_fixed_assets_pdf_content(self, data: Dict[str, Any], styles) -> List:
        """Build Fixed Assets PDF content."""
        from reportlab.lib import colors
        from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
        
        elements = []
        assets = data.get("assets", [])
        summary = data.get("summary", {})
        
        # Summary
        elements.append(Paragraph("<b>Summary</b>", styles['Heading2']))
        summary_data = [
            ["Active Assets", str(summary.get("total_assets", 0))],
            ["Total Cost", f"₦{summary.get('total_acquisition_cost', 0):,.2f}"],
            ["Accumulated Depreciation", f"₦{summary.get('total_accumulated_depreciation', 0):,.2f}"],
            ["Net Book Value", f"₦{summary.get('total_net_book_value', 0):,.2f}"],
        ]
        
        summary_table = Table(summary_data, colWidths=[200, 150])
        summary_table.setStyle(TableStyle([
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 20))
        
        # Assets list
        if assets:
            elements.append(Paragraph("<b>Asset Details</b>", styles['Heading2']))
            table_data = [["Asset", "Type", "Cost (₦)", "Depreciation (₦)", "NBV (₦)"]]
            
            for asset in assets[:20]:  # Limit to 20 for PDF
                table_data.append([
                    asset.get("name", "")[:30],
                    asset.get("asset_type", "")[:15],
                    f"{asset.get('acquisition_cost', 0):,.0f}",
                    f"{asset.get('accumulated_depreciation', 0):,.0f}",
                    f"{asset.get('net_book_value', 0):,.0f}",
                ])
            
            table = Table(table_data, colWidths=[120, 70, 90, 90, 90])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#166534')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            elements.append(table)
        
        return elements
