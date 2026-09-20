"""
Tekvwa Pro Audit - Forensic Audit Router

World-Class Audit API Endpoints:
1. Benford's Law Analysis
2. Z-Score Anomaly Detection
3. NRS Gap Analysis
4. Full Population Testing
5. Data Integrity Verification (Hash Chain)
6. Match Summary Report

Nigerian Tax Reform 2026 Compliant

SKU Tier: INTELLIGENCE ADD-ON (₦250,000+/mo)
Feature Flags: BENFORDS_LAW, ZSCORE_ANALYSIS, FRAUD_DETECTION
"""

import uuid
from datetime import date
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException, status, Body
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.database import get_db
from app.dependencies import get_current_user, require_feature
from app.models.user import User
from app.models.sku import Feature
from app.services.forensic_audit_service import (
    ForensicAuditService,
    BenfordsLawAnalyzer,
    ZScoreAnomalyDetector,
    NRSGapAnalyzer,
    worm_storage,
)
from app.services.three_way_matching import three_way_matching_service


router = APIRouter(
    prefix="/{entity_id}/forensic-audit", 
    tags=["Forensic Audit"],
    dependencies=[Depends(require_feature([Feature.BENFORDS_LAW]))]
)

# Note: All endpoints in this router require Intelligence add-on (BENFORDS_LAW feature)


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class BenfordsAnalysisRequest(BaseModel):
    """Request model for Benford's Law analysis."""
    amounts: List[float] = Field(..., min_length=100, description="List of amounts to analyze (min 100)")
    analysis_type: str = Field("first_digit", description="'first_digit' or 'second_digit'")


class AnomalyDetectionRequest(BaseModel):
    """Request model for anomaly detection."""
    transactions: List[dict] = Field(..., description="List of transaction objects with 'amount' field")
    amount_field: str = Field("amount", description="Field name containing the amount")
    group_by: Optional[str] = Field(None, description="Optional field to group by (e.g., 'category')")
    threshold: float = Field(2.5, ge=1.5, le=5.0, description="Z-score threshold for anomalies")


class ForensicAuditRequest(BaseModel):
    """Request model for full forensic audit."""
    fiscal_year: int = Field(..., ge=2020, le=2030, description="Fiscal year to analyze")
    categories: Optional[List[str]] = Field(None, description="Optional category filter")


# =============================================================================
# INFO ENDPOINTS
# =============================================================================

@router.get("/info")
async def get_forensic_audit_info():
    """
    Get forensic audit capabilities and information.
    
    Describes all available world-class audit features.
    """
    return {
        "name": "Tekvwa Pro Audit Forensic Audit Engine",
        "version": "1.0.0",
        "compliance_standards": ["NTAA 2025", "Nigerian Tax Reform 2026", "FIRS e-Invoicing"],
        "capabilities": {
            "benfords_law": {
                "description": "Detects fraud using digit distribution analysis",
                "methodology": "Compares first/second digit distribution against expected Benford's Law distribution",
                "use_cases": ["Expense fraud detection", "Invoice manipulation", "Revenue fabrication"],
                "minimum_sample": 100,
            },
            "z_score_anomaly": {
                "description": "Statistical outlier detection using Z-scores",
                "methodology": "Identifies transactions that deviate significantly from category/vendor averages",
                "use_cases": ["Unusual expense detection", "Vendor overcharging", "Category abuse"],
                "minimum_sample": 10,
            },
            "nrs_gap_analysis": {
                "description": "Compares local records against NRS government portal",
                "methodology": "Identifies invoices without IRNs and unreported B2C transactions",
                "use_cases": ["FIRS audit preparation", "IRN compliance", "B2C reporting compliance"],
                "compliance": "Mandatory for Nigerian businesses",
            },
            "ledger_integrity": {
                "description": "Cryptographic hash chain verification",
                "methodology": "SHA-256 hash chain ensures no retroactive modifications",
                "use_cases": ["Data tampering detection", "Audit trail verification", "Non-repudiation"],
                "standard": "Blockchain-like immutability",
            },
            "three_way_matching": {
                "description": "PO-GRN-Invoice matching for AP audit",
                "methodology": "Links Purchase Orders, Goods Received Notes, and Invoices",
                "use_cases": ["Accounts Payable audit", "Unauthorized payment detection", "Vendor fraud"],
            },
        },
        "outputs": [
            "Risk assessment with severity levels",
            "Specific flagged transactions",
            "Actionable recommendations",
            "Compliance status badges",
            "Export-ready audit reports",
        ],
    }


# =============================================================================
# BENFORD'S LAW ANALYSIS
# =============================================================================

@router.get("/benfords-law")
async def analyze_benfords_law(
    entity_id: uuid.UUID,
    fiscal_year: int = Query(..., ge=2020, le=2030, description="Fiscal year to analyze"),
    transaction_type: Optional[str] = Query(None, description="Filter by transaction type"),
    analysis_type: str = Query("first_digit", description="'first_digit' or 'second_digit'"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Perform Benford's Law analysis on financial data.
    
    Aggregates data from: Transactions, Journal Entries, Invoices, Sales, and Expense Claims.
    
    Benford's Law states that in naturally occurring numerical data,
    the leading digit follows a specific logarithmic distribution.
    Deviation from this pattern may indicate data manipulation or fraud.
    
    **Interpretation:**
    - Close conformity (MAD < 0.006): Low risk, data appears natural
    - Acceptable (MAD 0.006-0.012): Normal for financial data
    - Marginal (MAD 0.012-0.015): Warrants review
    - Non-conforming (MAD >= 0.015): Potential fraud indicator
    """
    from app.models.transaction import Transaction
    from app.models.accounting import JournalEntry, JournalEntryStatus
    from app.models.invoice import Invoice
    from sqlalchemy import select, and_, union_all
    from decimal import Decimal
    
    start_date = date(fiscal_year, 1, 1)
    end_date = date(fiscal_year, 12, 31)
    
    amounts = []
    data_sources = {}
    
    # 1. Query transactions
    try:
        txn_query = select(Transaction.amount).where(
            and_(
                Transaction.entity_id == entity_id,
                Transaction.transaction_date >= start_date,
                Transaction.transaction_date <= end_date,
                Transaction.amount > 0,
            )
        )
        if transaction_type:
            txn_query = txn_query.where(Transaction.type == transaction_type)
        
        result = await db.execute(txn_query)
        txn_amounts = [Decimal(str(row[0])) for row in result.all() if row[0]]
        amounts.extend(txn_amounts)
        data_sources["transactions"] = len(txn_amounts)
    except Exception as e:
        data_sources["transactions"] = f"Error: {str(e)}"
    
    # 2. Query journal entries (total_debit or total_credit)
    try:
        je_query = select(JournalEntry.total_debit).where(
            and_(
                JournalEntry.entity_id == entity_id,
                JournalEntry.entry_date >= start_date,
                JournalEntry.entry_date <= end_date,
                JournalEntry.status == JournalEntryStatus.POSTED,
                JournalEntry.total_debit > 0,
            )
        )
        result = await db.execute(je_query)
        je_amounts = [Decimal(str(row[0])) for row in result.all() if row[0]]
        amounts.extend(je_amounts)
        data_sources["journal_entries"] = len(je_amounts)
    except Exception as e:
        data_sources["journal_entries"] = f"Error: {str(e)}"
    
    # 3. Query invoices
    try:
        inv_query = select(Invoice.total_amount).where(
            and_(
                Invoice.entity_id == entity_id,
                Invoice.invoice_date >= start_date,
                Invoice.invoice_date <= end_date,
                Invoice.total_amount > 0,
            )
        )
        result = await db.execute(inv_query)
        inv_amounts = [Decimal(str(row[0])) for row in result.all() if row[0]]
        amounts.extend(inv_amounts)
        data_sources["invoices"] = len(inv_amounts)
    except Exception as e:
        data_sources["invoices"] = f"Error: {str(e)}"
    
    # 4. Query sales (if model exists)
    try:
        from app.models.inventory import Sale
        sale_query = select(Sale.total_amount).where(
            and_(
                Sale.entity_id == entity_id,
                Sale.sale_date >= start_date,
                Sale.sale_date <= end_date,
                Sale.total_amount > 0,
            )
        )
        result = await db.execute(sale_query)
        sale_amounts = [Decimal(str(row[0])) for row in result.all() if row[0]]
        amounts.extend(sale_amounts)
        data_sources["sales"] = len(sale_amounts)
    except Exception as e:
        data_sources["sales"] = f"Not available: {str(e)}"
    
    # 5. Query expense claims
    try:
        from app.models.expense_claims import ExpenseClaim
        exp_query = select(ExpenseClaim.total_amount).where(
            and_(
                ExpenseClaim.entity_id == entity_id,
                ExpenseClaim.claim_date >= start_date,
                ExpenseClaim.claim_date <= end_date,
                ExpenseClaim.total_amount > 0,
            )
        )
        result = await db.execute(exp_query)
        exp_amounts = [Decimal(str(row[0])) for row in result.all() if row[0]]
        amounts.extend(exp_amounts)
        data_sources["expense_claims"] = len(exp_amounts)
    except Exception as e:
        data_sources["expense_claims"] = f"Not available: {str(e)}"
    
    if len(amounts) < 100:
        # Return a helpful response instead of error
        return {
            "status": "insufficient_data",
            "message": f"Benford's Law analysis requires minimum 100 data points for statistical significance. Found {len(amounts)} records.",
            "records_found": len(amounts),
            "minimum_required": 100,
            "data_sources": data_sources,
            "suggestions": [
                "Record more transactions in the system",
                "Create journal entries for accounting activity",
                "Add sales invoices or expense claims",
                f"The current fiscal year ({fiscal_year}) may have limited data - try a previous year if available"
            ],
            "interpretation": {
                "why_100": "Benford's Law is a statistical phenomenon that requires a sufficient sample size to produce meaningful results.",
                "alternatives": "You can still run Anomaly Detection or Data Integrity checks with smaller datasets."
            }
        }
    
    # Perform analysis
    analyzer = BenfordsLawAnalyzer()
    analysis = analyzer.analyze(amounts, analysis_type)
    
    return {
        "entity_id": str(entity_id),
        "fiscal_year": fiscal_year,
        "transaction_type": transaction_type or "all",
        "data_sources": data_sources,
        "total_records_analyzed": len(amounts),
        **analysis,
    }


@router.post("/benfords-law/custom")
async def analyze_benfords_law_custom(
    entity_id: uuid.UUID,
    request: BenfordsAnalysisRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Perform Benford's Law analysis on custom data.
    
    Allows analysis of specific datasets (e.g., specific vendor payments,
    category expenses, etc.)
    """
    from decimal import Decimal
    
    amounts = [Decimal(str(a)) for a in request.amounts if a > 0]
    
    if len(amounts) < 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Minimum 100 positive amounts required. Found: {len(amounts)}"
        )
    
    analyzer = BenfordsLawAnalyzer()
    return analyzer.analyze(amounts, request.analysis_type)


# =============================================================================
# Z-SCORE ANOMALY DETECTION
# =============================================================================

@router.get("/anomaly-detection")
async def detect_anomalies(
    entity_id: uuid.UUID,
    fiscal_year: int = Query(..., ge=2020, le=2030),
    group_by: Optional[str] = Query(None, description="Group analysis by field (category, vendor, source)"),
    threshold: float = Query(2.5, ge=1.5, le=5.0, description="Z-score threshold"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Detect statistical anomalies in financial data using Z-scores.
    
    Aggregates data from: Transactions, Journal Entries, Invoices, Sales, and Expense Claims.
    
    Z-score measures how many standard deviations a value is from the mean.
    Transactions with high Z-scores are statistically unusual.
    
    **Severity Levels:**
    - Warning (Z >= 2.0): ~2.3% probability in normal data
    - Critical (Z >= 3.0): ~0.1% probability in normal data
    - Extreme (Z >= 4.0): Virtually never in normal data
    
    **Use Cases:**
    - Detect unusually large expenses
    - Identify vendor overcharging
    - Find category anomalies
    """
    from app.models.transaction import Transaction
    from app.models.accounting import JournalEntry, JournalEntryStatus
    from app.models.invoice import Invoice
    from sqlalchemy import select, and_
    
    start_date = date(fiscal_year, 1, 1)
    end_date = date(fiscal_year, 12, 31)
    
    all_data = []
    data_sources = {}
    
    # 1. Query transactions
    try:
        query = select(Transaction).where(
            and_(
                Transaction.entity_id == entity_id,
                Transaction.transaction_date >= start_date,
                Transaction.transaction_date <= end_date,
            )
        )
        result = await db.execute(query)
        transactions = result.scalars().all()
        
        for txn in transactions:
            all_data.append({
                "id": str(txn.id),
                "amount": float(txn.amount) if txn.amount else 0,
                "date": txn.transaction_date.isoformat() if txn.transaction_date else None,
                "description": txn.description,
                "category": getattr(txn, 'category_name', None) or str(getattr(txn, 'category_id', '')),
                "vendor": getattr(txn, 'vendor_name', None) or str(getattr(txn, 'vendor_id', '')),
                "source": "transaction",
            })
        data_sources["transactions"] = len(transactions)
    except Exception as e:
        data_sources["transactions"] = f"Error: {str(e)}"
    
    # 2. Query journal entries
    try:
        je_query = select(JournalEntry).where(
            and_(
                JournalEntry.entity_id == entity_id,
                JournalEntry.entry_date >= start_date,
                JournalEntry.entry_date <= end_date,
                JournalEntry.status == JournalEntryStatus.POSTED,
            )
        )
        result = await db.execute(je_query)
        journals = result.scalars().all()
        
        for je in journals:
            all_data.append({
                "id": str(je.id),
                "amount": float(je.total_debit) if je.total_debit else 0,
                "date": je.entry_date.isoformat() if je.entry_date else None,
                "description": je.description,
                "category": je.entry_type.value if je.entry_type else "journal",
                "vendor": je.source_module or "manual",
                "source": "journal_entry",
            })
        data_sources["journal_entries"] = len(journals)
    except Exception as e:
        data_sources["journal_entries"] = f"Error: {str(e)}"
    
    # 3. Query invoices
    try:
        inv_query = select(Invoice).where(
            and_(
                Invoice.entity_id == entity_id,
                Invoice.invoice_date >= start_date,
                Invoice.invoice_date <= end_date,
            )
        )
        result = await db.execute(inv_query)
        invoices = result.scalars().all()
        
        for inv in invoices:
            all_data.append({
                "id": str(inv.id),
                "amount": float(inv.total_amount) if inv.total_amount else 0,
                "date": inv.invoice_date.isoformat() if inv.invoice_date else None,
                "description": f"Invoice {inv.invoice_number}",
                "category": getattr(inv, 'invoice_type', 'B2B'),
                "vendor": getattr(inv, 'customer_name', None) or str(getattr(inv, 'customer_id', '')),
                "source": "invoice",
            })
        data_sources["invoices"] = len(invoices)
    except Exception as e:
        data_sources["invoices"] = f"Error: {str(e)}"
    
    # 4. Query expense claims
    try:
        from app.models.expense_claims import ExpenseClaim
        exp_query = select(ExpenseClaim).where(
            and_(
                ExpenseClaim.entity_id == entity_id,
                ExpenseClaim.claim_date >= start_date,
                ExpenseClaim.claim_date <= end_date,
            )
        )
        result = await db.execute(exp_query)
        expenses = result.scalars().all()
        
        for exp in expenses:
            all_data.append({
                "id": str(exp.id),
                "amount": float(exp.total_amount) if exp.total_amount else 0,
                "date": exp.claim_date.isoformat() if exp.claim_date else None,
                "description": exp.description or f"Expense Claim {exp.claim_number}",
                "category": getattr(exp, 'expense_type', 'expense'),
                "vendor": getattr(exp, 'employee_name', None) or str(getattr(exp, 'employee_id', '')),
                "source": "expense_claim",
            })
        data_sources["expense_claims"] = len(expenses)
    except Exception as e:
        data_sources["expense_claims"] = f"Not available: {str(e)}"
    
    if len(all_data) < 10:
        # Return a helpful JSON response instead of error
        return {
            "status": "insufficient_data",
            "message": f"Anomaly detection requires at least 10 records. Found {len(all_data)} records.",
            "records_found": len(all_data),
            "data_sources": data_sources,
            "suggestions": [
                "Create more transactions in the system",
                "Record journal entries for accounting transactions",
                "Add invoices or expense claims",
                "Check the date range - current year may have limited data"
            ],
            "anomalies": [],
            "summary": {
                "total_anomalies": 0,
                "critical_count": 0,
                "warning_count": 0,
                "normal_count": 0
            }
        }
    
    detector = ZScoreAnomalyDetector()
    result = detector.detect_anomalies(
        all_data,
        amount_field="amount",
        group_by=group_by if group_by else "source",
        threshold=threshold
    )
    
    result["data_sources"] = data_sources
    result["total_records_analyzed"] = len(all_data)
    
    return result


@router.post("/anomaly-detection/custom")
async def detect_anomalies_custom(
    entity_id: uuid.UUID,
    request: AnomalyDetectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Detect anomalies in custom transaction data.
    
    Allows analysis of specific datasets or external data.
    """
    detector = ZScoreAnomalyDetector()
    return detector.detect_anomalies(
        request.transactions,
        amount_field=request.amount_field,
        group_by=request.group_by,
        threshold=request.threshold
    )


# =============================================================================
# NRS GAP ANALYSIS
# =============================================================================

@router.get("/nrs-gap-analysis")
async def analyze_nrs_gaps(
    entity_id: uuid.UUID,
    start_date: date = Query(..., description="Analysis period start"),
    end_date: date = Query(..., description="Analysis period end"),
    include_b2c: bool = Query(True, description="Include B2C high-value analysis"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Analyze gaps between local records and NRS government portal.
    
    This is the FIRST thing an FIRS/NRS auditor will check.
    
    **Identifies:**
    - Invoices without IRNs (non-compliant)
    - Pending IRN validations
    - High-value B2C transactions requiring reporting (2026 reform)
    
    **Compliance Levels:**
    - >= 95% validated: COMPLIANT
    - 80-95% validated: ATTENTION REQUIRED
    - < 80% validated: NON-COMPLIANT
    """
    analyzer = NRSGapAnalyzer()
    return await analyzer.analyze_gaps(
        db, entity_id, start_date, end_date, include_b2c
    )


@router.get("/nrs-gap-analysis/{fiscal_year}")
async def analyze_nrs_gaps_by_year(
    entity_id: uuid.UUID,
    fiscal_year: int,
    include_b2c: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Analyze NRS gaps for an entire fiscal year.
    """
    start_date = date(fiscal_year, 1, 1)
    end_date = date(fiscal_year, 12, 31)
    
    analyzer = NRSGapAnalyzer()
    return await analyzer.analyze_gaps(
        db, entity_id, start_date, end_date, include_b2c
    )


# =============================================================================
# DATA INTEGRITY VERIFICATION
# =============================================================================

@router.post("/verify-integrity")
async def verify_data_integrity(
    entity_id: uuid.UUID,
    fiscal_year: Optional[int] = Query(None, description="Optional fiscal year filter"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Verify data integrity using cryptographic hash chain.
    
    This is the "Verify Integrity" button feature.
    
    **How it works:**
    Every ledger entry stores SHA-256(entry_data + previous_hash).
    If ANY historical record is modified, ALL subsequent hashes break.
    
    **Returns:**
    - Green badge: Data integrity verified
    - Red badge: Integrity breach detected
    
    **Legal Weight:**
    Hash chain provides non-repudiation evidence for audit disputes.
    """
    service = ForensicAuditService(db)
    return await service.verify_data_integrity(entity_id, fiscal_year)


@router.get("/ledger-integrity-report")
async def get_ledger_integrity_report(
    entity_id: uuid.UUID,
    start_sequence: Optional[int] = Query(None, description="Start sequence number"),
    end_sequence: Optional[int] = Query(None, description="End sequence number"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate detailed ledger integrity report.
    
    Provides sequence-by-sequence verification of the hash chain.
    """
    from app.services.immutable_ledger import immutable_ledger_service
    
    is_valid, discrepancies = await immutable_ledger_service.verify_chain_integrity(
        db, entity_id, start_sequence, end_sequence
    )
    
    return {
        "entity_id": str(entity_id),
        "sequence_range": {
            "start": start_sequence,
            "end": end_sequence,
        },
        "integrity_status": "VERIFIED" if is_valid else "BREACH_DETECTED",
        "chain_valid": is_valid,
        "discrepancy_count": len(discrepancies),
        "discrepancies": discrepancies,
        "verification_time": date.today().isoformat(),
        "badge": "green" if is_valid else "red",
        "legal_statement": (
            "This report certifies the cryptographic integrity of the audit trail. "
            "All ledger entries are linked via SHA-256 hash chain, ensuring "
            "no retroactive modifications have occurred."
        ) if is_valid else (
            "INTEGRITY BREACH: Discrepancies detected in hash chain. "
            "This indicates possible data tampering. Immediate investigation required."
        ),
    }


# =============================================================================
# 3-WAY MATCHING SUMMARY
# =============================================================================

@router.get("/three-way-matching/summary")
async def get_three_way_matching_summary(
    entity_id: uuid.UUID,
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get 3-way matching summary report.
    
    Shows PO-GRN-Invoice matching status for auditor review.
    
    **Matched:** All three documents agree on quantity and price
    **Discrepancy:** Mismatch detected - requires investigation
    **Pending:** Awaiting review/resolution
    
    **Risk Indicator:**
    Invoices paid without 100% match = High-Risk Exception
    """
    summary = await three_way_matching_service.get_matching_summary(
        db, entity_id, start_date, end_date
    )
    
    # Add risk assessment
    discrepancy_count = summary.get("by_status", {}).get("discrepancy", {}).get("count", 0)
    total_count = summary.get("totals", {}).get("total_matches", 0)
    
    if total_count > 0:
        discrepancy_rate = discrepancy_count / total_count * 100
    else:
        discrepancy_rate = 0
    
    summary["risk_assessment"] = {
        "discrepancy_rate": round(discrepancy_rate, 2),
        "risk_level": "high" if discrepancy_rate > 10 else "medium" if discrepancy_rate > 5 else "low",
        "high_risk_exceptions": discrepancy_count,
        "auditor_note": (
            f"{discrepancy_count} invoices were paid without 100% match on "
            f"quantity and price. These are flagged as High-Risk Exceptions."
        ) if discrepancy_count > 0 else "All invoices matched successfully.",
    }
    
    return summary


@router.get("/three-way-matching/exceptions")
async def get_matching_exceptions(
    entity_id: uuid.UUID,
    status_filter: Optional[str] = Query(None, description="Filter by status: discrepancy, pending_review"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get list of 3-way matching exceptions (High-Risk).
    
    These are invoices that were processed without perfect
    PO-GRN-Invoice matching and require auditor attention.
    """
    from app.models.advanced_accounting import ThreeWayMatch, MatchingStatus
    from sqlalchemy import select, and_
    
    query = select(ThreeWayMatch).where(
        ThreeWayMatch.entity_id == entity_id
    )
    
    if status_filter:
        try:
            status_enum = MatchingStatus(status_filter)
            query = query.where(ThreeWayMatch.status == status_enum)
        except ValueError:
            pass
    else:
        # Default to showing discrepancies and pending
        query = query.where(
            ThreeWayMatch.status.in_([
                MatchingStatus.DISCREPANCY,
                MatchingStatus.PENDING,
                MatchingStatus.PENDING_REVIEW,
            ])
        )
    
    result = await db.execute(query.order_by(ThreeWayMatch.created_at.desc()).limit(100))
    matches = result.scalars().all()
    
    return {
        "entity_id": str(entity_id),
        "exception_count": len(matches),
        "exceptions": [
            {
                "id": str(m.id),
                "purchase_order_id": str(m.purchase_order_id) if m.purchase_order_id else None,
                "grn_id": str(m.grn_id) if m.grn_id else None,
                "invoice_id": str(m.invoice_id) if m.invoice_id else None,
                "status": m.status.value if hasattr(m.status, 'value') else str(m.status),
                "po_amount": str(m.po_amount) if m.po_amount else None,
                "invoice_amount": str(m.invoice_amount) if m.invoice_amount else None,
                "discrepancies": m.discrepancies,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "resolved_at": m.resolved_at.isoformat() if hasattr(m, 'resolved_at') and m.resolved_at else None,
            }
            for m in matches
        ],
        "auditor_guidance": (
            "Review each exception to determine if the variance is acceptable. "
            "Document resolution with notes and approver signature."
        ),
    }


# =============================================================================
# FULL FORENSIC AUDIT
# =============================================================================

@router.post("/full-audit")
async def run_full_forensic_audit(
    entity_id: uuid.UUID,
    request: ForensicAuditRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Run comprehensive forensic audit (Full Population Testing).
    
    This is NOT sampling - it analyzes EVERY transaction.
    
    **Tests Performed:**
    1. Benford's Law (first & second digit)
    2. Z-score anomaly detection (overall & by category)
    3. NRS gap analysis
    4. Hash chain integrity verification
    
    **Returns:**
    - Overall risk assessment
    - Specific risk factors identified
    - Detailed results from each test
    - Actionable recommendations
    """
    service = ForensicAuditService(db)
    return await service.run_full_forensic_audit(
        entity_id,
        request.fiscal_year,
        request.categories
    )


@router.get("/audit-summary/{fiscal_year}")
async def get_audit_summary(
    entity_id: uuid.UUID,
    fiscal_year: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get executive summary of audit status for a fiscal year.
    
    Quick overview for management and auditors.
    """
    # This would aggregate results from various services
    # For now, return a structured summary
    
    service = ForensicAuditService(db)
    integrity_result = await service.verify_data_integrity(entity_id, fiscal_year)
    
    start_date = date(fiscal_year, 1, 1)
    end_date = date(fiscal_year, 12, 31)
    
    nrs_analyzer = NRSGapAnalyzer()
    nrs_result = await nrs_analyzer.analyze_gaps(db, entity_id, start_date, end_date)
    
    matching_summary = await three_way_matching_service.get_matching_summary(
        db, entity_id, start_date, end_date
    )
    
    return {
        "entity_id": str(entity_id),
        "fiscal_year": fiscal_year,
        "summary": {
            "data_integrity": {
                "status": integrity_result.get("status"),
                "badge": integrity_result.get("badge"),
            },
            "nrs_compliance": {
                "rate": nrs_result.get("compliance", {}).get("rate"),
                "status": nrs_result.get("compliance", {}).get("status"),
                "risk_level": nrs_result.get("compliance", {}).get("risk_level"),
            },
            "three_way_matching": {
                "match_rate": matching_summary.get("totals", {}).get("match_rate"),
                "exceptions": matching_summary.get("by_status", {}).get("discrepancy", {}).get("count", 0),
            },
        },
        "quick_actions": [
            "Run Full Forensic Audit" if not integrity_result.get("verified") else None,
            "Submit pending invoices to NRS" if nrs_result.get("summary", {}).get("missing_irn", 0) > 0 else None,
            "Review matching exceptions" if matching_summary.get("by_status", {}).get("discrepancy", {}).get("count", 0) > 0 else None,
        ],
        "generated_at": date.today().isoformat(),
    }


# =============================================================================
# WORM STORAGE (AUDIT VAULT)
# =============================================================================

@router.get("/worm-storage/status")
async def get_worm_storage_status(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get WORM (Write-Once-Read-Many) storage status.
    
    WORM storage provides legal-grade document retention where
    files cannot be deleted or modified for the retention period.
    
    **Compliance:**
    - 7-year retention for Nigerian tax records
    - Object Lock prevents deletion even by admins
    - Provides legal weight for audit disputes
    """
    return {
        "enabled": worm_storage.enabled,
        "storage_type": "AWS S3 Object Lock" if worm_storage.enabled else "Not Configured",
        "retention_mode": "COMPLIANCE" if worm_storage.enabled else None,
        "default_retention_years": worm_storage.DEFAULT_RETENTION_YEARS,
        "legal_protection": (
            "Documents stored in WORM cannot be modified or deleted until "
            "the retention period expires. This provides legal-grade "
            "evidence for tax disputes and audits."
        ),
        "supported_documents": [
            "Tax filings",
            "NRS-validated invoices",
            "Financial statements",
            "Audit reports",
            "Bank statements",
            "Supporting documents",
        ],
        "configuration_status": "active" if worm_storage.enabled else "requires_setup",
    }


@router.post("/worm-storage/verify/{document_type}/{document_id}")
async def verify_worm_document(
    entity_id: uuid.UUID,
    document_type: str,
    document_id: str,
    expected_hash: Optional[str] = Query(None, description="Expected SHA-256 hash"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Verify a document's integrity and legal lock status in WORM storage.
    
    Proves that the document is exactly the same as when it was stored.
    """
    return await worm_storage.verify_document(
        entity_id, document_type, document_id, expected_hash
    )


# =============================================================================
# IMMUTABLE LEDGER SYNC
# =============================================================================

@router.post("/sync-ledger")
async def sync_journal_entries_to_ledger(
    entity_id: uuid.UUID,
    fiscal_year: int = Query(..., ge=2020, le=2030, description="Fiscal year to sync"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Sync posted journal entries to the immutable ledger.
    
    Creates hash-chained ledger entries from existing journal entries
    for blockchain-like audit integrity verification.
    
    **IMPORTANT:** This is a one-time sync operation per fiscal year.
    Once synced, entries cannot be modified without breaking the hash chain.
    """
    from app.models.accounting import JournalEntry, JournalEntryLine, JournalEntryStatus
    from app.models.advanced_accounting import LedgerEntry
    from app.services.immutable_ledger import immutable_ledger_service
    from sqlalchemy import select, func, and_
    from decimal import Decimal
    
    start_date = date(fiscal_year, 1, 1)
    end_date = date(fiscal_year, 12, 31)
    
    # Check if there are already ledger entries for this period
    existing_count_query = select(func.count(LedgerEntry.id)).where(
        and_(
            LedgerEntry.entity_id == entity_id,
            LedgerEntry.entry_date >= start_date,
            LedgerEntry.entry_date <= end_date,
        )
    )
    result = await db.execute(existing_count_query)
    existing_count = result.scalar() or 0
    
    if existing_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ledger already has {existing_count} entries for fiscal year {fiscal_year}. Cannot re-sync."
        )
    
    # Get all posted journal entries with their lines
    je_query = select(JournalEntry).where(
        and_(
            JournalEntry.entity_id == entity_id,
            JournalEntry.entry_date >= start_date,
            JournalEntry.entry_date <= end_date,
            JournalEntry.status == JournalEntryStatus.POSTED,
        )
    ).order_by(JournalEntry.entry_date, JournalEntry.entry_number)
    
    result = await db.execute(je_query)
    journal_entries = result.scalars().all()
    
    if not journal_entries:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No posted journal entries found for fiscal year {fiscal_year}."
        )
    
    synced_count = 0
    errors = []
    
    for je in journal_entries:
        try:
            # Create ledger entry for each journal entry
            await immutable_ledger_service.create_entry(
                db=db,
                entity_id=entity_id,
                entry_type="journal_entry",
                source_type="journal",
                source_id=je.id,
                account_code=None,  # Will be tracked per line in a more detailed implementation
                debit_amount=je.total_debit or Decimal("0"),
                credit_amount=je.total_credit or Decimal("0"),
                entry_date=je.entry_date,
                description=je.description or f"Journal Entry {je.entry_number}",
                reference=je.entry_number,
                created_by_id=current_user.id,
                currency=je.currency or "NGN"
            )
            synced_count += 1
        except Exception as e:
            errors.append({
                "entry_number": je.entry_number,
                "error": str(e)
            })
    
    await db.commit()
    
    return {
        "status": "success" if synced_count > 0 else "no_entries",
        "message": f"Synced {synced_count} journal entries to immutable ledger for fiscal year {fiscal_year}.",
        "fiscal_year": fiscal_year,
        "synced_count": synced_count,
        "error_count": len(errors),
        "errors": errors[:10] if errors else [],
        "next_steps": [
            "Run 'Verify Integrity' to confirm hash chain is valid",
            "Entries are now protected with SHA-256 hash chain",
            "Any modification will be detectable in integrity checks"
        ]
    }


@router.get("/ledger-stats")
async def get_ledger_statistics(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get statistics about the immutable ledger for this entity.
    """
    from app.models.advanced_accounting import LedgerEntry
    from app.models.accounting import JournalEntry, JournalEntryStatus
    from sqlalchemy import select, func, and_
    
    # Ledger stats
    ledger_query = select(
        func.count(LedgerEntry.id).label('count'),
        func.min(LedgerEntry.entry_date).label('first_date'),
        func.max(LedgerEntry.entry_date).label('last_date'),
        func.sum(LedgerEntry.debit_amount).label('total_debit'),
        func.sum(LedgerEntry.credit_amount).label('total_credit'),
    ).where(LedgerEntry.entity_id == entity_id)
    
    result = await db.execute(ledger_query)
    ledger_stats = result.first()
    
    # Journal entry stats (for comparison)
    je_query = select(
        func.count(JournalEntry.id).label('count'),
        func.min(JournalEntry.entry_date).label('first_date'),
        func.max(JournalEntry.entry_date).label('last_date'),
    ).where(
        and_(
            JournalEntry.entity_id == entity_id,
            JournalEntry.status == JournalEntryStatus.POSTED,
        )
    )
    
    je_result = await db.execute(je_query)
    je_stats = je_result.first()
    
    return {
        "immutable_ledger": {
            "entry_count": ledger_stats.count or 0,
            "first_entry_date": ledger_stats.first_date.isoformat() if ledger_stats.first_date else None,
            "last_entry_date": ledger_stats.last_date.isoformat() if ledger_stats.last_date else None,
            "total_debit": str(ledger_stats.total_debit or 0),
            "total_credit": str(ledger_stats.total_credit or 0),
            "status": "populated" if (ledger_stats.count or 0) > 0 else "empty"
        },
        "journal_entries": {
            "posted_count": je_stats.count or 0,
            "first_entry_date": je_stats.first_date.isoformat() if je_stats.first_date else None,
            "last_entry_date": je_stats.last_date.isoformat() if je_stats.last_date else None,
            "sync_status": "synced" if ledger_stats.count == je_stats.count else "needs_sync" if je_stats.count > 0 else "no_entries"
        },
        "recommendations": (
            ["Run 'Sync Ledger' to populate immutable ledger from journal entries"]
            if (ledger_stats.count or 0) == 0 and (je_stats.count or 0) > 0
            else ["Ledger is up to date"] if ledger_stats.count == je_stats.count
            else ["Some journal entries may not be synced - consider running sync"]
        )
    }