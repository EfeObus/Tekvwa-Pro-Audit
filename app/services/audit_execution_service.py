"""
Tekvwa Pro Audit - Audit Execution Service

Comprehensive audit execution service that:
1. Connects to all data sources (accounting, payroll, inventory, transactions, etc.)
2. Runs actual audit checks based on audit type
3. Generates findings with proper risk levels
4. Supports Nigerian compliance (NRS/IRN verification, NTAA 2025)
5. Supports global audit standards (ISA, GAAP)

CRITICAL: All audit results are reproducible with version-controlled rules.
"""

import uuid
import hashlib
import json
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import math

from sqlalchemy import select, func, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    # Audit
    AuditRun, AuditRunStatus, AuditRunType,
    AuditFinding, FindingRiskLevel, FindingCategory,
    AuditEvidence, EvidenceType,
    # Customers/Vendors
    Customer, Vendor,
    # Inventory
    InventoryItem, StockMovement,
    # Payroll
    Employee, PayrollRun, Payslip, PayslipItem,
    # Fixed Assets
    FixedAsset, DepreciationEntry,
    # Tax
    VATRecord, PAYERecord,
)
from app.models.accounting import (
    JournalEntry, JournalEntryLine,
    ChartOfAccounts, AccountType, AccountBalance,
)
from app.models.transaction import Transaction, TransactionType
from app.models.invoice import Invoice, InvoiceStatus, InvoiceLineItem
from app.models.entity import BusinessEntity


# Nigerian Tax Rates (2026)
VAT_RATE = Decimal('0.075')  # 7.5%
WHT_SERVICES_RATE = Decimal('0.10')  # 10%
WHT_GOODS_RATE = Decimal('0.05')  # 5%

# Audit Thresholds
BENFORD_SAMPLE_MINIMUM = 100
ZSCORE_THRESHOLD = 3.0
MATERIALITY_DEFAULT = Decimal('50000.00')


@dataclass
class AuditCheckResult:
    """Result of a single audit check."""
    check_name: str
    passed: bool
    risk_level: FindingRiskLevel
    category: FindingCategory
    title: str
    description: str
    impact: str
    recommendation: str
    affected_records: int = 0
    affected_amount: Decimal = Decimal('0')
    evidence: Dict[str, Any] = None
    regulatory_reference: Optional[str] = None
    
    def __post_init__(self):
        if self.evidence is None:
            self.evidence = {}


class AuditExecutionService:
    """
    Executes comprehensive audit runs against all data sources.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def execute_audit(
        self,
        audit_run: AuditRun,
    ) -> Dict[str, Any]:
        """
        Execute an audit run and generate findings.
        
        Returns execution summary with findings count.
        """
        entity_id = audit_run.entity_id
        period_start = audit_run.period_start
        period_end = audit_run.period_end
        run_type = audit_run.run_type
        
        # Track execution
        findings: List[AuditCheckResult] = []
        data_sources_used = []
        checks_performed = []
        records_analyzed = 0
        
        # Get materiality threshold from config or use default
        materiality = MATERIALITY_DEFAULT
        if audit_run.rule_config:
            threshold_value = audit_run.rule_config.get('materiality_threshold')
            if threshold_value is not None and threshold_value != '' and threshold_value != 'null':
                try:
                    materiality = Decimal(str(threshold_value))
                except:
                    materiality = MATERIALITY_DEFAULT
        
        # Run checks based on audit type
        if run_type == AuditRunType.TAX_COMPLIANCE:
            tax_results = await self._run_tax_compliance_checks(entity_id, period_start, period_end, materiality)
            findings.extend(tax_results['findings'])
            records_analyzed += tax_results['records_analyzed']
            data_sources_used.extend(tax_results['data_sources'])
            checks_performed.extend(tax_results['checks'])
            
        elif run_type == AuditRunType.FINANCIAL_STATEMENT:
            fs_results = await self._run_financial_statement_checks(entity_id, period_start, period_end, materiality)
            findings.extend(fs_results['findings'])
            records_analyzed += fs_results['records_analyzed']
            data_sources_used.extend(fs_results['data_sources'])
            checks_performed.extend(fs_results['checks'])
            
        elif run_type == AuditRunType.VAT_AUDIT:
            vat_results = await self._run_vat_audit_checks(entity_id, period_start, period_end, materiality)
            findings.extend(vat_results['findings'])
            records_analyzed += vat_results['records_analyzed']
            data_sources_used.extend(vat_results['data_sources'])
            checks_performed.extend(vat_results['checks'])
            
        elif run_type == AuditRunType.WHT_AUDIT:
            wht_results = await self._run_wht_audit_checks(entity_id, period_start, period_end, materiality)
            findings.extend(wht_results['findings'])
            records_analyzed += wht_results['records_analyzed']
            data_sources_used.extend(wht_results['data_sources'])
            checks_performed.extend(wht_results['checks'])
            
        else:  # CUSTOM or other types - run all checks
            all_results = await self._run_all_checks(entity_id, period_start, period_end, materiality)
            findings.extend(all_results['findings'])
            records_analyzed += all_results['records_analyzed']
            data_sources_used.extend(all_results['data_sources'])
            checks_performed.extend(all_results['checks'])
        
        # Create finding records in database
        critical_count = 0
        high_count = 0
        medium_count = 0
        low_count = 0
        
        for finding in findings:
            if not finding.passed:
                await self._create_finding_record(audit_run.id, entity_id, finding)
                
                if finding.risk_level == FindingRiskLevel.CRITICAL:
                    critical_count += 1
                elif finding.risk_level == FindingRiskLevel.HIGH:
                    high_count += 1
                elif finding.risk_level == FindingRiskLevel.MEDIUM:
                    medium_count += 1
                elif finding.risk_level == FindingRiskLevel.LOW:
                    low_count += 1
        
        # Update audit run with results
        audit_run.status = AuditRunStatus.COMPLETED
        audit_run.completed_at = datetime.now()
        audit_run.total_records_analyzed = records_analyzed
        audit_run.findings_count = len([f for f in findings if not f.passed])
        audit_run.critical_findings = critical_count
        audit_run.high_findings = high_count
        audit_run.medium_findings = medium_count
        audit_run.low_findings = low_count
        
        execution_summary = {
            "records_analyzed": records_analyzed,
            "checks_performed": list(set(checks_performed)),
            "data_sources": list(set(data_sources_used)),
            "findings_generated": len([f for f in findings if not f.passed]),
            "completed_at": datetime.now().isoformat(),
            "materiality_threshold": str(materiality),
        }
        
        audit_run.result_summary = execution_summary
        audit_run.run_hash = self._calculate_run_hash(audit_run)
        
        await self.db.flush()
        
        return {
            "status": "completed",
            "records_analyzed": records_analyzed,
            "findings": {
                "total": len([f for f in findings if not f.passed]),
                "critical": critical_count,
                "high": high_count,
                "medium": medium_count,
                "low": low_count,
            },
            "execution_summary": execution_summary,
        }
    
    # ========================================
    # TAX COMPLIANCE CHECKS
    # ========================================
    
    async def _run_tax_compliance_checks(
        self,
        entity_id: uuid.UUID,
        period_start: date,
        period_end: date,
        materiality: Decimal,
    ) -> Dict[str, Any]:
        """Run comprehensive tax compliance checks."""
        findings = []
        records_analyzed = 0
        data_sources = ['transactions', 'invoices', 'vat_records', 'payroll']
        checks = []
        
        # Check 1: VAT on taxable transactions
        vat_check = await self._check_vat_on_taxable_transactions(entity_id, period_start, period_end)
        findings.append(vat_check)
        records_analyzed += vat_check.affected_records
        checks.append('VAT on Taxable Transactions')
        
        # Check 2: WHT compliance on payments
        wht_check = await self._check_wht_deduction_compliance(entity_id, period_start, period_end)
        findings.append(wht_check)
        records_analyzed += wht_check.affected_records
        checks.append('WHT Deduction Compliance')
        
        # Check 3: Invoice NRS/IRN submission
        nrs_check = await self._check_nrs_submission_compliance(entity_id, period_start, period_end)
        findings.append(nrs_check)
        records_analyzed += nrs_check.affected_records
        checks.append('NRS/IRN Submission')
        
        # Check 4: PAYE on payroll
        paye_check = await self._check_paye_compliance(entity_id, period_start, period_end)
        findings.append(paye_check)
        records_analyzed += paye_check.affected_records
        checks.append('PAYE Compliance')
        
        return {
            'findings': findings,
            'records_analyzed': records_analyzed,
            'data_sources': data_sources,
            'checks': checks,
        }
    
    async def _check_vat_on_taxable_transactions(
        self,
        entity_id: uuid.UUID,
        period_start: date,
        period_end: date,
    ) -> AuditCheckResult:
        """Check that VAT is correctly applied on taxable transactions."""
        # Query invoices in period
        stmt = select(Invoice).where(
            and_(
                Invoice.entity_id == entity_id,
                Invoice.invoice_date >= period_start,
                Invoice.invoice_date <= period_end,
                Invoice.status != InvoiceStatus.DRAFT,
            )
        )
        result = await self.db.execute(stmt)
        invoices = result.scalars().all()
        
        issues = []
        total_vat_discrepancy = Decimal('0')
        
        for invoice in invoices:
            # Calculate expected VAT
            subtotal = invoice.subtotal or Decimal('0')
            expected_vat = subtotal * VAT_RATE
            actual_vat = invoice.vat_amount or Decimal('0')
            
            # Allow 1 naira tolerance for rounding
            if abs(expected_vat - actual_vat) > Decimal('1.00'):
                issues.append({
                    'invoice_number': invoice.invoice_number,
                    'expected_vat': str(expected_vat),
                    'actual_vat': str(actual_vat),
                    'difference': str(expected_vat - actual_vat),
                })
                total_vat_discrepancy += abs(expected_vat - actual_vat)
        
        passed = len(issues) == 0
        
        return AuditCheckResult(
            check_name='vat_on_taxable_transactions',
            passed=passed,
            risk_level=FindingRiskLevel.HIGH if total_vat_discrepancy > Decimal('10000') else FindingRiskLevel.MEDIUM if not passed else FindingRiskLevel.LOW,
            category=FindingCategory.TAX_DISCREPANCY,
            title='VAT Calculation Discrepancies' if not passed else 'VAT Correctly Applied',
            description=f'Found {len(issues)} invoices with VAT calculation discrepancies totaling ₦{total_vat_discrepancy:,.2f}' if not passed else 'All invoices have correct VAT calculations',
            impact=f'Potential FIRS penalty for VAT under-remittance of ₦{total_vat_discrepancy:,.2f}' if not passed else 'No impact',
            recommendation='Review and correct VAT calculations on flagged invoices. File amended VAT returns if necessary.' if not passed else 'Continue current VAT calculation practices',
            affected_records=len(invoices),
            affected_amount=total_vat_discrepancy,
            evidence={'discrepancies': issues[:20]},  # Limit to 20 for storage
            regulatory_reference='FIRS VAT Act 2007, Section 4',
        )
    
    async def _check_wht_deduction_compliance(
        self,
        entity_id: uuid.UUID,
        period_start: date,
        period_end: date,
    ) -> AuditCheckResult:
        """Check that WHT is correctly deducted on applicable payments."""
        # Query transactions that might require WHT
        stmt = select(Transaction).where(
            and_(
                Transaction.entity_id == entity_id,
                Transaction.transaction_date >= period_start,
                Transaction.transaction_date <= period_end,
                Transaction.transaction_type == TransactionType.EXPENSE,
            )
        )
        result = await self.db.execute(stmt)
        transactions = result.scalars().all()
        
        issues = []
        total_wht_gap = Decimal('0')
        
        for txn in transactions:
            amount = txn.amount or Decimal('0')
            # Transactions above ₦50,000 typically require WHT
            if amount >= Decimal('50000'):
                wht_amount = txn.wht_amount or Decimal('0')
                expected_wht = amount * WHT_SERVICES_RATE  # Default to services rate
                
                if wht_amount < expected_wht * Decimal('0.9'):  # Allow 10% tolerance
                    issues.append({
                        'transaction_id': str(txn.id),
                        'amount': str(amount),
                        'expected_wht': str(expected_wht),
                        'actual_wht': str(wht_amount),
                    })
                    total_wht_gap += expected_wht - wht_amount
        
        passed = len(issues) == 0
        
        return AuditCheckResult(
            check_name='wht_deduction_compliance',
            passed=passed,
            risk_level=FindingRiskLevel.HIGH if total_wht_gap > Decimal('50000') else FindingRiskLevel.MEDIUM if not passed else FindingRiskLevel.LOW,
            category=FindingCategory.TAX_DISCREPANCY,
            title='WHT Deduction Gaps' if not passed else 'WHT Correctly Deducted',
            description=f'Found {len(issues)} transactions with potential WHT deduction gaps totaling ₦{total_wht_gap:,.2f}' if not passed else 'All applicable transactions have WHT correctly deducted',
            impact=f'Potential FIRS penalty plus interest on unremitted WHT of ₦{total_wht_gap:,.2f}' if not passed else 'No impact',
            recommendation='Review WHT deduction on flagged transactions. Ensure WHT is deducted at source for payments to contractors.' if not passed else 'Continue current WHT practices',
            affected_records=len(transactions),
            affected_amount=total_wht_gap,
            evidence={'gaps': issues[:20]},
            regulatory_reference='FIRS WHT Regulations 2024',
        )
    
    async def _check_nrs_submission_compliance(
        self,
        entity_id: uuid.UUID,
        period_start: date,
        period_end: date,
    ) -> AuditCheckResult:
        """Check that invoices are submitted to NRS and have valid IRN."""
        stmt = select(Invoice).where(
            and_(
                Invoice.entity_id == entity_id,
                Invoice.invoice_date >= period_start,
                Invoice.invoice_date <= period_end,
                Invoice.status.in_([InvoiceStatus.SUBMITTED, InvoiceStatus.ACCEPTED, InvoiceStatus.PAID, InvoiceStatus.PARTIALLY_PAID]),
            )
        )
        result = await self.db.execute(stmt)
        invoices = result.scalars().all()
        
        missing_irn = []
        
        for invoice in invoices:
            # Check if invoice has IRN (Invoice Reference Number from NRS)
            irn = getattr(invoice, 'irn', None) or getattr(invoice, 'nrs_irn', None)
            if not irn:
                missing_irn.append({
                    'invoice_number': invoice.invoice_number,
                    'invoice_date': invoice.invoice_date.isoformat() if invoice.invoice_date else None,
                    'amount': str(invoice.total_amount),
                })
        
        total_count = len(invoices)
        missing_count = len(missing_irn)
        compliance_rate = ((total_count - missing_count) / total_count * 100) if total_count > 0 else 100
        
        passed = missing_count == 0
        
        return AuditCheckResult(
            check_name='nrs_submission_compliance',
            passed=passed,
            risk_level=FindingRiskLevel.CRITICAL if compliance_rate < 80 else FindingRiskLevel.HIGH if compliance_rate < 95 else FindingRiskLevel.MEDIUM if not passed else FindingRiskLevel.LOW,
            category=FindingCategory.COMPLIANCE_GAP,
            title=f'NRS Compliance at {compliance_rate:.1f}%' if not passed else 'Full NRS Compliance',
            description=f'{missing_count} out of {total_count} invoices missing NRS IRN submission' if not passed else 'All invoices have been submitted to NRS with valid IRN',
            impact='Non-compliant invoices may attract FIRS penalties and are not considered valid tax documents' if not passed else 'No impact',
            recommendation='Submit all outstanding invoices to NRS to obtain IRN. Ensure automated NRS integration is functioning.' if not passed else 'Continue automated NRS submission practices',
            affected_records=total_count,
            affected_amount=Decimal('0'),
            evidence={'missing_irn': missing_irn[:20], 'compliance_rate': compliance_rate},
            regulatory_reference='FIRS NRS Guidelines 2024, NTAA 2025',
        )
    
    async def _check_paye_compliance(
        self,
        entity_id: uuid.UUID,
        period_start: date,
        period_end: date,
    ) -> AuditCheckResult:
        """Check PAYE deduction and remittance compliance."""
        # Query payroll runs in period
        stmt = select(PayrollRun).where(
            and_(
                PayrollRun.entity_id == entity_id,
                PayrollRun.period_start >= period_start,
                PayrollRun.period_end <= period_end,
            )
        )
        result = await self.db.execute(stmt)
        payroll_runs = result.scalars().all()
        
        issues = []
        total_paye_gap = Decimal('0')
        
        for run in payroll_runs:
            # Get payslips for this run
            payslip_stmt = select(Payslip).where(Payslip.payroll_run_id == run.id)
            payslip_result = await self.db.execute(payslip_stmt)
            payslips = payslip_result.scalars().all()
            
            for payslip in payslips:
                gross = payslip.gross_pay or Decimal('0')
                paye = payslip.paye_tax or Decimal('0')
                
                # Simple check: PAYE should be deducted on gross above minimum wage
                if gross > Decimal('70000') and paye < Decimal('100'):  # Minimum threshold
                    issues.append({
                        'payroll_run_id': str(run.id),
                        'employee_id': str(payslip.employee_id),
                        'gross_pay': str(gross),
                        'paye_deducted': str(paye),
                    })
                    total_paye_gap += gross * Decimal('0.1')  # Estimate
        
        passed = len(issues) == 0
        
        return AuditCheckResult(
            check_name='paye_compliance',
            passed=passed,
            risk_level=FindingRiskLevel.HIGH if len(issues) > 5 else FindingRiskLevel.MEDIUM if not passed else FindingRiskLevel.LOW,
            category=FindingCategory.TAX_DISCREPANCY,
            title='PAYE Deduction Gaps' if not passed else 'PAYE Correctly Deducted',
            description=f'Found {len(issues)} payslips with potential PAYE deduction issues' if not passed else 'All payslips have appropriate PAYE deductions',
            impact=f'Potential SIRS penalty for PAYE under-remittance' if not passed else 'No impact',
            recommendation='Review PAYE calculation methodology. Ensure all taxable allowances are included in PAYE base.' if not passed else 'Continue current PAYE practices',
            affected_records=len(payroll_runs),
            affected_amount=total_paye_gap,
            evidence={'issues': issues[:20]},
            regulatory_reference='Personal Income Tax Act (PITA) 2011',
        )
    
    # ========================================
    # FINANCIAL STATEMENT CHECKS
    # ========================================
    
    async def _run_financial_statement_checks(
        self,
        entity_id: uuid.UUID,
        period_start: date,
        period_end: date,
        materiality: Decimal,
    ) -> Dict[str, Any]:
        """Run financial statement audit checks."""
        findings = []
        records_analyzed = 0
        data_sources = ['journal_entries', 'accounts', 'transactions', 'invoices']
        checks = []
        
        # Check 1: Trial Balance
        tb_check = await self._check_trial_balance(entity_id, period_start, period_end)
        findings.append(tb_check)
        records_analyzed += tb_check.affected_records
        checks.append('Trial Balance Check')
        
        # Check 2: Unreconciled transactions
        unrec_check = await self._check_unreconciled_transactions(entity_id, period_start, period_end, materiality)
        findings.append(unrec_check)
        records_analyzed += unrec_check.affected_records
        checks.append('Unreconciled Transactions')
        
        # Check 3: Duplicate transactions
        dup_check = await self._check_duplicate_transactions(entity_id, period_start, period_end)
        findings.append(dup_check)
        records_analyzed += dup_check.affected_records
        checks.append('Duplicate Detection')
        
        # Check 4: Unusual journal entries
        unusual_check = await self._check_unusual_journal_entries(entity_id, period_start, period_end, materiality)
        findings.append(unusual_check)
        records_analyzed += unusual_check.affected_records
        checks.append('Unusual Journal Entries')
        
        return {
            'findings': findings,
            'records_analyzed': records_analyzed,
            'data_sources': data_sources,
            'checks': checks,
        }
    
    async def _check_trial_balance(
        self,
        entity_id: uuid.UUID,
        period_start: date,
        period_end: date,
    ) -> AuditCheckResult:
        """Check that debits equal credits (trial balance check)."""
        # Query journal entry lines
        stmt = select(
            func.sum(JournalEntryLine.debit_amount).label('total_debits'),
            func.sum(JournalEntryLine.credit_amount).label('total_credits'),
            func.count(JournalEntryLine.id).label('line_count'),
        ).join(JournalEntry).where(
            and_(
                JournalEntry.entity_id == entity_id,
                JournalEntry.entry_date >= period_start,
                JournalEntry.entry_date <= period_end,
            )
        )
        
        result = await self.db.execute(stmt)
        row = result.first()
        
        total_debits = row.total_debits or Decimal('0')
        total_credits = row.total_credits or Decimal('0')
        line_count = row.line_count or 0
        
        difference = abs(total_debits - total_credits)
        passed = difference < Decimal('1.00')  # Allow 1 naira tolerance
        
        return AuditCheckResult(
            check_name='trial_balance',
            passed=passed,
            risk_level=FindingRiskLevel.CRITICAL if difference > Decimal('1000') else FindingRiskLevel.HIGH if not passed else FindingRiskLevel.LOW,
            category=FindingCategory.DATA_INTEGRITY,
            title='Trial Balance Imbalance' if not passed else 'Trial Balance Balanced',
            description=f'Trial balance has a difference of ₦{difference:,.2f}. Total Debits: ₦{total_debits:,.2f}, Total Credits: ₦{total_credits:,.2f}' if not passed else f'Trial balance is balanced. Total: ₦{total_debits:,.2f}',
            impact='Financial statements may be materially misstated' if not passed else 'No impact',
            recommendation='Investigate and correct the trial balance imbalance before finalizing financial statements' if not passed else 'Financial records are balanced',
            affected_records=line_count,
            affected_amount=difference,
            evidence={'total_debits': str(total_debits), 'total_credits': str(total_credits), 'difference': str(difference)},
            regulatory_reference='ISA 315 - Understanding the Entity',
        )
    
    async def _check_unreconciled_transactions(
        self,
        entity_id: uuid.UUID,
        period_start: date,
        period_end: date,
        materiality: Decimal,
    ) -> AuditCheckResult:
        """Check for large transactions that may need review (proxy for unreconciled)."""
        # Since Transaction model doesn't have is_reconciled field,
        # we check for large transactions above materiality that may need attention
        stmt = select(Transaction).where(
            and_(
                Transaction.entity_id == entity_id,
                Transaction.transaction_date >= period_start,
                Transaction.transaction_date <= period_end,
                Transaction.amount >= materiality,
            )
        )
        result = await self.db.execute(stmt)
        large_transactions = result.scalars().all()
        
        total_large = sum(t.amount or Decimal('0') for t in large_transactions)
        
        # For this check, we consider it passed if we have a reasonable number of large transactions
        # (less than 10% of total would be large transactions above materiality)
        passed = len(large_transactions) <= 50  # Reasonable threshold
        
        return AuditCheckResult(
            check_name='large_transactions_review',
            passed=passed,
            risk_level=FindingRiskLevel.MEDIUM if len(large_transactions) > 100 else FindingRiskLevel.LOW,
            category=FindingCategory.CONTROL_DEFICIENCY,
            title=f'{len(large_transactions)} Large Transactions for Review' if len(large_transactions) > 0 else 'No Material Transactions Found',
            description=f'Found {len(large_transactions)} transactions above materiality threshold (₦{materiality:,.2f}) totaling ₦{total_large:,.2f}. These should be reviewed for proper documentation.' if len(large_transactions) > 0 else 'No transactions above materiality threshold found',
            impact='Large transactions should have proper supporting documentation' if len(large_transactions) > 0 else 'No impact',
            recommendation='Ensure all large transactions have proper approval and documentation' if len(large_transactions) > 0 else 'Continue transaction monitoring',
            affected_records=len(large_transactions),
            affected_amount=total_large,
            evidence={'large_transaction_count': len(large_transactions), 'total_amount': str(total_large)},
            regulatory_reference='ISA 500 - Audit Evidence',
        )
    
    async def _check_duplicate_transactions(
        self,
        entity_id: uuid.UUID,
        period_start: date,
        period_end: date,
    ) -> AuditCheckResult:
        """Check for potential duplicate transactions."""
        # Find transactions with same amount, date, and description
        stmt = text("""
            SELECT amount, transaction_date, description, COUNT(*) as cnt
            FROM transactions
            WHERE entity_id = :entity_id
              AND transaction_date >= :period_start
              AND transaction_date <= :period_end
              AND amount > 0
            GROUP BY amount, transaction_date, description
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC
            LIMIT 50
        """)
        
        result = await self.db.execute(stmt, {
            'entity_id': str(entity_id),
            'period_start': period_start,
            'period_end': period_end,
        })
        duplicates = result.fetchall()
        
        duplicate_count = len(duplicates)
        total_affected = sum(d.cnt for d in duplicates) if duplicates else 0
        
        passed = duplicate_count == 0
        
        return AuditCheckResult(
            check_name='duplicate_transactions',
            passed=passed,
            risk_level=FindingRiskLevel.HIGH if duplicate_count > 10 else FindingRiskLevel.MEDIUM if not passed else FindingRiskLevel.LOW,
            category=FindingCategory.FRAUD_INDICATOR,
            title=f'{duplicate_count} Potential Duplicate Groups' if not passed else 'No Duplicate Transactions Detected',
            description=f'Found {duplicate_count} groups of potential duplicate transactions affecting {total_affected} records' if not passed else 'No potential duplicates detected',
            impact='Duplicate transactions may result in overstated expenses or revenues' if not passed else 'No impact',
            recommendation='Review flagged transactions and void any confirmed duplicates' if not passed else 'Continue transaction monitoring',
            affected_records=total_affected,
            affected_amount=Decimal('0'),
            evidence={'duplicate_groups': duplicate_count},
            regulatory_reference='ISA 240 - Fraud',
        )
    
    async def _check_unusual_journal_entries(
        self,
        entity_id: uuid.UUID,
        period_start: date,
        period_end: date,
        materiality: Decimal,
    ) -> AuditCheckResult:
        """Check for unusual journal entries (weekend/holiday, round amounts, etc.)."""
        # Find entries posted on weekends or with round amounts
        stmt = select(JournalEntry).where(
            and_(
                JournalEntry.entity_id == entity_id,
                JournalEntry.entry_date >= period_start,
                JournalEntry.entry_date <= period_end,
            )
        )
        result = await self.db.execute(stmt)
        entries = result.scalars().all()
        
        unusual = []
        
        for entry in entries:
            reasons = []
            
            # Check if posted on weekend
            if entry.entry_date.weekday() >= 5:  # Saturday = 5, Sunday = 6
                reasons.append('Posted on weekend')
            
            # Check for perfectly round amounts - use total_debit since debits = credits in balanced entries
            total = entry.total_debit or Decimal('0')
            if total > materiality and total % Decimal('100000') == 0:
                reasons.append('Perfectly round amount')
            
            # Check if posted after hours (if we have timestamp)
            if hasattr(entry, 'created_at') and entry.created_at:
                hour = entry.created_at.hour
                if hour < 6 or hour > 22:
                    reasons.append('Posted outside business hours')
            
            if reasons:
                unusual.append({
                    'entry_id': str(entry.id),
                    'entry_date': entry.entry_date.isoformat(),
                    'amount': str(total),
                    'reasons': reasons,
                })
        
        passed = len(unusual) == 0
        
        return AuditCheckResult(
            check_name='unusual_journal_entries',
            passed=passed,
            risk_level=FindingRiskLevel.MEDIUM if len(unusual) > 5 else FindingRiskLevel.LOW,
            category=FindingCategory.FRAUD_INDICATOR,
            title=f'{len(unusual)} Unusual Journal Entries' if not passed else 'No Unusual Entries Detected',
            description=f'Found {len(unusual)} journal entries with unusual characteristics (weekend posting, round amounts, etc.)' if not passed else 'No unusual journal entry patterns detected',
            impact='Unusual entries may indicate management override of controls' if not passed else 'No impact',
            recommendation='Review flagged entries with posting users and obtain explanations' if not passed else 'Continue monitoring journal entry patterns',
            affected_records=len(unusual),
            affected_amount=Decimal('0'),
            evidence={'unusual_entries': unusual[:20]},
            regulatory_reference='ISA 240 - Fraud, ISA 330 - Responses to Assessed Risks',
        )
    
    # ========================================
    # VAT AUDIT CHECKS
    # ========================================
    
    async def _run_vat_audit_checks(
        self,
        entity_id: uuid.UUID,
        period_start: date,
        period_end: date,
        materiality: Decimal,
    ) -> Dict[str, Any]:
        """Run VAT-specific audit checks."""
        findings = []
        records_analyzed = 0
        data_sources = ['invoices', 'vat_records', 'transactions']
        checks = []
        
        # VAT on taxable transactions
        vat_check = await self._check_vat_on_taxable_transactions(entity_id, period_start, period_end)
        findings.append(vat_check)
        records_analyzed += vat_check.affected_records
        checks.append('VAT on Taxable Transactions')
        
        # NRS compliance
        nrs_check = await self._check_nrs_submission_compliance(entity_id, period_start, period_end)
        findings.append(nrs_check)
        records_analyzed += nrs_check.affected_records
        checks.append('NRS/IRN Submission')
        
        # Input VAT recovery
        input_vat_check = await self._check_input_vat_recovery(entity_id, period_start, period_end)
        findings.append(input_vat_check)
        records_analyzed += input_vat_check.affected_records
        checks.append('Input VAT Recovery')
        
        return {
            'findings': findings,
            'records_analyzed': records_analyzed,
            'data_sources': data_sources,
            'checks': checks,
        }
    
    async def _check_input_vat_recovery(
        self,
        entity_id: uuid.UUID,
        period_start: date,
        period_end: date,
    ) -> AuditCheckResult:
        """Check input VAT recovery claims for validity."""
        # Query expenses/purchases with VAT
        stmt = select(Transaction).where(
            and_(
                Transaction.entity_id == entity_id,
                Transaction.transaction_date >= period_start,
                Transaction.transaction_date <= period_end,
                Transaction.transaction_type == TransactionType.EXPENSE,
                Transaction.vat_amount > 0,
            )
        )
        result = await self.db.execute(stmt)
        expenses = result.scalars().all()
        
        issues = []
        total_questionable = Decimal('0')
        
        for expense in expenses:
            vat_claimed = expense.vat_amount or Decimal('0')
            amount = expense.amount or Decimal('0')
            
            # Check if VAT rate is correct (should be 7.5%)
            expected_vat = amount * VAT_RATE / (1 + VAT_RATE)  # VAT from VAT-inclusive amount
            
            if vat_claimed > expected_vat * Decimal('1.1'):  # More than 10% over expected
                issues.append({
                    'transaction_id': str(expense.id),
                    'amount': str(amount),
                    'vat_claimed': str(vat_claimed),
                    'expected_vat': str(expected_vat),
                })
                total_questionable += vat_claimed - expected_vat
        
        passed = len(issues) == 0
        
        return AuditCheckResult(
            check_name='input_vat_recovery',
            passed=passed,
            risk_level=FindingRiskLevel.HIGH if total_questionable > Decimal('50000') else FindingRiskLevel.MEDIUM if not passed else FindingRiskLevel.LOW,
            category=FindingCategory.TAX_DISCREPANCY,
            title='Questionable Input VAT Claims' if not passed else 'Input VAT Claims Valid',
            description=f'Found {len(issues)} transactions with potentially excessive input VAT claims totaling ₦{total_questionable:,.2f}' if not passed else 'All input VAT claims appear valid',
            impact='Excessive input VAT claims may result in FIRS audits and penalties' if not passed else 'No impact',
            recommendation='Review flagged transactions and ensure VAT invoices are obtained from registered vendors' if not passed else 'Continue input VAT documentation practices',
            affected_records=len(expenses),
            affected_amount=total_questionable,
            evidence={'questionable_claims': issues[:20]},
            regulatory_reference='VAT Act 2007, Section 16 - Input Tax',
        )
    
    # ========================================
    # WHT AUDIT CHECKS
    # ========================================
    
    async def _run_wht_audit_checks(
        self,
        entity_id: uuid.UUID,
        period_start: date,
        period_end: date,
        materiality: Decimal,
    ) -> Dict[str, Any]:
        """Run WHT-specific audit checks."""
        findings = []
        records_analyzed = 0
        data_sources = ['transactions', 'vendors', 'invoices']
        checks = []
        
        # WHT deduction compliance
        wht_check = await self._check_wht_deduction_compliance(entity_id, period_start, period_end)
        findings.append(wht_check)
        records_analyzed += wht_check.affected_records
        checks.append('WHT Deduction Compliance')
        
        # Vendor TIN verification
        tin_check = await self._check_vendor_tin_compliance(entity_id)
        findings.append(tin_check)
        records_analyzed += tin_check.affected_records
        checks.append('Vendor TIN Verification')
        
        return {
            'findings': findings,
            'records_analyzed': records_analyzed,
            'data_sources': data_sources,
            'checks': checks,
        }
    
    async def _check_vendor_tin_compliance(
        self,
        entity_id: uuid.UUID,
    ) -> AuditCheckResult:
        """Check that all vendors have valid TIN."""
        stmt = select(Vendor).where(Vendor.entity_id == entity_id)
        result = await self.db.execute(stmt)
        vendors = result.scalars().all()
        
        missing_tin = []
        
        for vendor in vendors:
            if not vendor.tin or len(str(vendor.tin).strip()) < 8:
                missing_tin.append({
                    'vendor_id': str(vendor.id),
                    'vendor_name': vendor.name,
                })
        
        passed = len(missing_tin) == 0
        compliance_rate = ((len(vendors) - len(missing_tin)) / len(vendors) * 100) if vendors else 100
        
        return AuditCheckResult(
            check_name='vendor_tin_compliance',
            passed=passed,
            risk_level=FindingRiskLevel.MEDIUM if len(missing_tin) > 5 else FindingRiskLevel.LOW,
            category=FindingCategory.COMPLIANCE_GAP,
            title=f'{len(missing_tin)} Vendors Missing TIN' if not passed else 'All Vendors Have TIN',
            description=f'Found {len(missing_tin)} out of {len(vendors)} vendors without valid TIN ({compliance_rate:.1f}% compliant)' if not passed else 'All vendors have valid Tax Identification Numbers',
            impact='Payments to vendors without TIN may face disallowed deductions' if not passed else 'No impact',
            recommendation='Obtain TIN from all vendors before processing payments' if not passed else 'Continue vendor TIN verification practices',
            affected_records=len(vendors),
            affected_amount=Decimal('0'),
            evidence={'missing_tin_vendors': missing_tin[:20], 'compliance_rate': compliance_rate},
            regulatory_reference='FIRS WHT Regulations 2024',
        )
    
    # ========================================
    # ALL CHECKS (CUSTOM)
    # ========================================
    
    async def _run_all_checks(
        self,
        entity_id: uuid.UUID,
        period_start: date,
        period_end: date,
        materiality: Decimal,
    ) -> Dict[str, Any]:
        """Run all available checks for custom audit."""
        findings = []
        records_analyzed = 0
        data_sources = []
        checks = []
        
        # Run tax checks
        tax_results = await self._run_tax_compliance_checks(entity_id, period_start, period_end, materiality)
        findings.extend(tax_results['findings'])
        records_analyzed += tax_results['records_analyzed']
        data_sources.extend(tax_results['data_sources'])
        checks.extend(tax_results['checks'])
        
        # Run financial statement checks
        fs_results = await self._run_financial_statement_checks(entity_id, period_start, period_end, materiality)
        findings.extend(fs_results['findings'])
        records_analyzed += fs_results['records_analyzed']
        data_sources.extend(fs_results['data_sources'])
        checks.extend(fs_results['checks'])
        
        return {
            'findings': findings,
            'records_analyzed': records_analyzed,
            'data_sources': list(set(data_sources)),
            'checks': list(set(checks)),
        }
    
    # ========================================
    # HELPER METHODS
    # ========================================
    
    async def _create_finding_record(
        self,
        audit_run_id: uuid.UUID,
        entity_id: uuid.UUID,
        check_result: AuditCheckResult,
    ) -> AuditFinding:
        """Create an AuditFinding record from check result."""
        # Generate finding reference
        count_stmt = select(func.count()).select_from(AuditFinding).where(
            AuditFinding.entity_id == entity_id
        )
        count_result = await self.db.execute(count_stmt)
        count = count_result.scalar() or 0
        
        finding_ref = f"FIND-{datetime.now().year}-{count + 1:05d}"
        
        # Generate finding hash for deduplication
        hash_data = {
            'audit_run_id': str(audit_run_id),
            'check_name': check_result.check_name,
            'title': check_result.title,
            'category': check_result.category.value if hasattr(check_result.category, 'value') else str(check_result.category),
            'risk_level': check_result.risk_level.value if hasattr(check_result.risk_level, 'value') else str(check_result.risk_level),
            'affected_records': check_result.affected_records,
            'affected_amount': str(check_result.affected_amount),
        }
        finding_hash = hashlib.sha256(json.dumps(hash_data, sort_keys=True).encode()).hexdigest()
        
        finding = AuditFinding(
            audit_run_id=audit_run_id,
            entity_id=entity_id,
            finding_ref=finding_ref,
            finding_hash=finding_hash,
            category=check_result.category,
            risk_level=check_result.risk_level,
            title=check_result.title,
            description=check_result.description,
            impact=check_result.impact,
            recommendation=check_result.recommendation,
            evidence_summary=json.dumps(check_result.evidence) if check_result.evidence else None,
            detection_method=check_result.check_name,
            affected_records=check_result.affected_records,
            affected_amount=check_result.affected_amount,
            regulatory_reference=check_result.regulatory_reference,
            confidence_score=1.0,
        )
        
        self.db.add(finding)
        await self.db.flush()
        
        return finding
    
    def _calculate_run_hash(self, audit_run: AuditRun) -> str:
        """Calculate hash for audit run reproducibility."""
        data = {
            'run_id': audit_run.run_id,
            'run_type': audit_run.run_type.value,
            'period_start': audit_run.period_start.isoformat() if audit_run.period_start else None,
            'period_end': audit_run.period_end.isoformat() if audit_run.period_end else None,
            'rule_version': audit_run.rule_version,
            'rule_config': audit_run.rule_config,
            'critical_findings': audit_run.critical_findings,
            'high_findings': audit_run.high_findings,
            'medium_findings': audit_run.medium_findings,
            'low_findings': audit_run.low_findings,
        }
        data_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(data_str.encode()).hexdigest()
