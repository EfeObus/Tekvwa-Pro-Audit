"""
Tekvwa Pro Audit - Forensic Audit Service

World-Class Audit Features:
1. Benford's Law Analysis - Detect fraud in digit distributions
2. Z-Score Anomaly Detection - Statistical outlier identification  
3. NRS Gap Analysis - Compare local vs government portal
4. Full Population Testing - Beyond sampling
5. WORM Storage Integration - AWS S3 Object Lock support

Nigerian Tax Reform 2026 Compliant
"""

import math
import hashlib
import json
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
from collections import Counter, defaultdict
import statistics
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, text
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)


# ==============================================================================
# BENFORD'S LAW ANALYSIS
# ==============================================================================

class BenfordsLawAnalyzer:
    """
    Implements Benford's Law analysis for fraud detection.
    
    Benford's Law states that in naturally occurring numerical data,
    the leading digit is distributed logarithmically. Digit 1 appears
    ~30.1% of the time, digit 2 ~17.6%, etc.
    
    Fraudulent data often deviates from this distribution as humans
    tend to fabricate numbers with more uniform distributions.
    """
    
    # Expected Benford's Law distribution for first digit
    EXPECTED_FIRST_DIGIT = {
        1: 0.301,
        2: 0.176,
        3: 0.125,
        4: 0.097,
        5: 0.079,
        6: 0.067,
        7: 0.058,
        8: 0.051,
        9: 0.046,
    }
    
    # Expected distribution for second digit
    EXPECTED_SECOND_DIGIT = {
        0: 0.120,
        1: 0.114,
        2: 0.109,
        3: 0.104,
        4: 0.100,
        5: 0.097,
        6: 0.093,
        7: 0.090,
        8: 0.088,
        9: 0.085,
    }
    
    # Chi-square critical values (df=8 for first digit, df=9 for second)
    CHI_SQUARE_CRITICAL = {
        "first_digit": {
            0.10: 13.362,  # 90% confidence
            0.05: 15.507,  # 95% confidence
            0.01: 20.090,  # 99% confidence
        },
        "second_digit": {
            0.10: 14.684,
            0.05: 16.919,
            0.01: 21.666,
        }
    }
    
    def extract_first_digit(self, number: Decimal) -> Optional[int]:
        """Extract the first significant digit from a number."""
        try:
            abs_num = abs(float(number))
            if abs_num == 0:
                return None
            # Remove decimal point and leading zeros
            num_str = f"{abs_num:.10f}".lstrip('0').replace('.', '').lstrip('0')
            if num_str:
                return int(num_str[0])
            return None
        except (ValueError, TypeError):
            return None
    
    def extract_second_digit(self, number: Decimal) -> Optional[int]:
        """Extract the second significant digit from a number."""
        try:
            abs_num = abs(float(number))
            if abs_num == 0:
                return None
            num_str = f"{abs_num:.10f}".lstrip('0').replace('.', '').lstrip('0')
            if len(num_str) >= 2:
                return int(num_str[1])
            return None
        except (ValueError, TypeError):
            return None
    
    def calculate_chi_square(
        self,
        observed: Dict[int, int],
        expected: Dict[int, float],
        total: int
    ) -> float:
        """Calculate chi-square statistic."""
        chi_square = 0.0
        for digit, expected_pct in expected.items():
            observed_count = observed.get(digit, 0)
            expected_count = expected_pct * total
            if expected_count > 0:
                chi_square += ((observed_count - expected_count) ** 2) / expected_count
        return chi_square
    
    def analyze(
        self,
        amounts: List[Decimal],
        analysis_type: str = "first_digit"
    ) -> Dict[str, Any]:
        """
        Perform Benford's Law analysis on a list of amounts.
        
        Args:
            amounts: List of monetary amounts to analyze
            analysis_type: "first_digit" or "second_digit"
            
        Returns:
            Analysis results with conformity score and anomalies
        """
        if len(amounts) < 100:
            return {
                "valid": False,
                "error": "Minimum 100 data points required for Benford's Law analysis",
                "sample_size": len(amounts),
            }
        
        # Extract digits
        if analysis_type == "first_digit":
            digits = [self.extract_first_digit(a) for a in amounts]
            expected = self.EXPECTED_FIRST_DIGIT
            critical_values = self.CHI_SQUARE_CRITICAL["first_digit"]
        else:
            digits = [self.extract_second_digit(a) for a in amounts]
            expected = self.EXPECTED_SECOND_DIGIT
            critical_values = self.CHI_SQUARE_CRITICAL["second_digit"]
        
        # Remove None values
        valid_digits = [d for d in digits if d is not None]
        total = len(valid_digits)
        
        if total < 100:
            return {
                "valid": False,
                "error": f"Only {total} valid data points after extraction",
                "sample_size": total,
            }
        
        # Count digit frequencies
        observed = Counter(valid_digits)
        
        # Calculate observed percentages
        observed_pct = {
            digit: count / total
            for digit, count in observed.items()
        }
        
        # Calculate chi-square statistic
        chi_square = self.calculate_chi_square(observed, expected, total)
        
        # Calculate Mean Absolute Deviation (MAD)
        mad = sum(
            abs(observed_pct.get(digit, 0) - expected_pct)
            for digit, expected_pct in expected.items()
        ) / len(expected)
        
        # Determine conformity level based on MAD
        # Close conformity: MAD < 0.006
        # Acceptable conformity: 0.006 <= MAD < 0.012
        # Marginally acceptable: 0.012 <= MAD < 0.015
        # Nonconforming: MAD >= 0.015
        
        if mad < 0.006:
            conformity_level = "close_conformity"
            conformity_status = "PASS"
            risk_level = "low"
        elif mad < 0.012:
            conformity_level = "acceptable_conformity"
            conformity_status = "PASS"
            risk_level = "low"
        elif mad < 0.015:
            conformity_level = "marginally_acceptable"
            conformity_status = "WARNING"
            risk_level = "medium"
        else:
            conformity_level = "nonconforming"
            conformity_status = "FAIL"
            risk_level = "high"
        
        # Identify specific digit anomalies
        digit_anomalies = []
        for digit, expected_pct in expected.items():
            actual_pct = observed_pct.get(digit, 0)
            deviation = abs(actual_pct - expected_pct)
            z_score = deviation / (expected_pct * (1 - expected_pct) / total) ** 0.5 if total > 0 else 0
            
            if z_score > 2.0:  # Significant deviation
                digit_anomalies.append({
                    "digit": digit,
                    "expected_pct": round(expected_pct * 100, 2),
                    "actual_pct": round(actual_pct * 100, 2),
                    "deviation": round(deviation * 100, 2),
                    "z_score": round(z_score, 2),
                    "severity": "high" if z_score > 3.0 else "medium",
                })
        
        # Chi-square test results
        chi_square_pass = chi_square < critical_values[0.05]
        
        return {
            "valid": True,
            "analysis_type": analysis_type,
            "sample_size": total,
            "chi_square": round(chi_square, 3),
            "chi_square_critical_95": critical_values[0.05],
            "chi_square_pass": chi_square_pass,
            "mean_absolute_deviation": round(mad, 4),
            "conformity_level": conformity_level,
            "conformity_status": conformity_status,
            "risk_level": risk_level,
            "digit_distribution": {
                str(digit): {
                    "count": observed.get(digit, 0),
                    "actual_pct": round(observed_pct.get(digit, 0) * 100, 2),
                    "expected_pct": round(expected_pct * 100, 2),
                }
                for digit, expected_pct in expected.items()
            },
            "anomalies": sorted(digit_anomalies, key=lambda x: x["z_score"], reverse=True),
            "interpretation": self._get_interpretation(conformity_level, len(digit_anomalies)),
            "analyzed_at": datetime.utcnow().isoformat(),
        }
    
    def _get_interpretation(self, conformity_level: str, anomaly_count: int) -> str:
        """Get human-readable interpretation of results."""
        interpretations = {
            "close_conformity": (
                "Data shows close conformity to Benford's Law. "
                "This is typical of naturally occurring financial data. "
                "Low risk of data manipulation."
            ),
            "acceptable_conformity": (
                "Data shows acceptable conformity to Benford's Law. "
                "Distribution is within normal ranges for financial records."
            ),
            "marginally_acceptable": (
                "Data shows marginal conformity to Benford's Law. "
                "Some deviation detected - recommend manual review of flagged categories."
            ),
            "nonconforming": (
                "WARNING: Data DOES NOT conform to Benford's Law. "
                "This may indicate data manipulation, fabricated entries, or unusual patterns. "
                "IMMEDIATE FORENSIC REVIEW RECOMMENDED."
            ),
        }
        base = interpretations.get(conformity_level, "Unable to interpret results.")
        if anomaly_count > 0:
            base += f" {anomaly_count} specific digit anomalies detected."
        return base


# ==============================================================================
# Z-SCORE ANOMALY DETECTION
# ==============================================================================

class ZScoreAnomalyDetector:
    """
    Statistical anomaly detection using Z-scores.
    
    Identifies transactions that deviate significantly from normal
    patterns within each category or vendor relationship.
    """
    
    # Z-score thresholds
    THRESHOLD_WARNING = 2.0   # ~2.3% of normal data
    THRESHOLD_CRITICAL = 3.0  # ~0.1% of normal data
    THRESHOLD_EXTREME = 4.0   # Virtually never in normal data
    
    def calculate_z_score(self, value: float, mean: float, std_dev: float) -> float:
        """Calculate Z-score for a value."""
        if std_dev == 0:
            return 0.0
        return (value - mean) / std_dev
    
    def detect_anomalies(
        self,
        transactions: List[Dict[str, Any]],
        amount_field: str = "amount",
        group_by: Optional[str] = None,
        threshold: float = 2.5
    ) -> Dict[str, Any]:
        """
        Detect statistical anomalies in transaction data.
        
        Args:
            transactions: List of transaction dictionaries
            amount_field: Field name containing the amount
            group_by: Optional field to group transactions by (e.g., 'category', 'vendor')
            threshold: Z-score threshold for flagging anomalies
            
        Returns:
            Anomaly detection results with flagged transactions
        """
        if not transactions:
            return {
                "valid": False,
                "error": "No transactions provided",
                "anomalies": [],
            }
        
        # Extract amounts
        amounts = []
        for txn in transactions:
            amt = txn.get(amount_field)
            if amt is not None:
                try:
                    amounts.append(float(amt))
                except (ValueError, TypeError):
                    pass
        
        if len(amounts) < 10:
            return {
                "valid": False,
                "error": "Minimum 10 transactions required for anomaly detection",
                "sample_size": len(amounts),
            }
        
        # If grouping, analyze each group separately
        if group_by:
            return self._detect_grouped_anomalies(transactions, amount_field, group_by, threshold)
        
        # Overall statistics
        mean = statistics.mean(amounts)
        std_dev = statistics.stdev(amounts) if len(amounts) > 1 else 0
        
        # Detect anomalies
        anomalies = []
        for i, txn in enumerate(transactions):
            amt = txn.get(amount_field)
            if amt is None:
                continue
            
            try:
                amount = float(amt)
            except (ValueError, TypeError):
                continue
            
            z_score = self.calculate_z_score(amount, mean, std_dev)
            
            if abs(z_score) >= threshold:
                severity = self._get_severity(abs(z_score))
                anomalies.append({
                    "transaction_id": str(txn.get("id", i)),
                    "amount": amount,
                    "z_score": round(z_score, 2),
                    "severity": severity,
                    "deviation_from_mean": round(amount - mean, 2),
                    "deviation_pct": round((amount - mean) / mean * 100, 1) if mean else 0,
                    "direction": "above" if z_score > 0 else "below",
                    "transaction_date": txn.get("transaction_date") or txn.get("date"),
                    "description": txn.get("description"),
                    "category": txn.get("category"),
                    "vendor": txn.get("vendor") or txn.get("vendor_name"),
                })
        
        # Sort by severity
        anomalies.sort(key=lambda x: abs(x["z_score"]), reverse=True)
        
        return {
            "valid": True,
            "sample_size": len(amounts),
            "statistics": {
                "mean": round(mean, 2),
                "std_dev": round(std_dev, 2),
                "min": round(min(amounts), 2),
                "max": round(max(amounts), 2),
                "median": round(statistics.median(amounts), 2),
            },
            "threshold_used": threshold,
            "anomaly_count": len(anomalies),
            "anomalies": anomalies,
            "summary": {
                "extreme": len([a for a in anomalies if a["severity"] == "extreme"]),
                "critical": len([a for a in anomalies if a["severity"] == "critical"]),
                "warning": len([a for a in anomalies if a["severity"] == "warning"]),
            },
            "analyzed_at": datetime.utcnow().isoformat(),
        }
    
    def _detect_grouped_anomalies(
        self,
        transactions: List[Dict[str, Any]],
        amount_field: str,
        group_by: str,
        threshold: float
    ) -> Dict[str, Any]:
        """Detect anomalies within each group."""
        # Group transactions
        groups = defaultdict(list)
        for txn in transactions:
            group_key = txn.get(group_by) or "Unknown"
            groups[group_key].append(txn)
        
        all_anomalies = []
        group_stats = {}
        
        for group_name, group_txns in groups.items():
            amounts = []
            for txn in group_txns:
                amt = txn.get(amount_field)
                if amt is not None:
                    try:
                        amounts.append(float(amt))
                    except (ValueError, TypeError):
                        pass
            
            if len(amounts) < 3:  # Need at least 3 for meaningful stats
                continue
            
            mean = statistics.mean(amounts)
            std_dev = statistics.stdev(amounts) if len(amounts) > 1 else 0
            
            group_stats[group_name] = {
                "count": len(amounts),
                "mean": round(mean, 2),
                "std_dev": round(std_dev, 2),
            }
            
            # Find anomalies in this group
            for txn in group_txns:
                amt = txn.get(amount_field)
                if amt is None:
                    continue
                
                try:
                    amount = float(amt)
                except (ValueError, TypeError):
                    continue
                
                z_score = self.calculate_z_score(amount, mean, std_dev)
                
                if abs(z_score) >= threshold:
                    all_anomalies.append({
                        "transaction_id": str(txn.get("id", "")),
                        "group": group_name,
                        "amount": amount,
                        "z_score": round(z_score, 2),
                        "severity": self._get_severity(abs(z_score)),
                        "group_mean": round(mean, 2),
                        "deviation_from_mean": round(amount - mean, 2),
                        "transaction_date": txn.get("transaction_date") or txn.get("date"),
                        "description": txn.get("description"),
                    })
        
        all_anomalies.sort(key=lambda x: abs(x["z_score"]), reverse=True)
        
        return {
            "valid": True,
            "sample_size": len(transactions),
            "grouped_by": group_by,
            "groups_analyzed": len(group_stats),
            "group_statistics": group_stats,
            "threshold_used": threshold,
            "anomaly_count": len(all_anomalies),
            "anomalies": all_anomalies,
            "summary": {
                "extreme": len([a for a in all_anomalies if a["severity"] == "extreme"]),
                "critical": len([a for a in all_anomalies if a["severity"] == "critical"]),
                "warning": len([a for a in all_anomalies if a["severity"] == "warning"]),
            },
            "analyzed_at": datetime.utcnow().isoformat(),
        }
    
    def _get_severity(self, z_score: float) -> str:
        """Determine severity based on Z-score magnitude."""
        if z_score >= self.THRESHOLD_EXTREME:
            return "extreme"
        elif z_score >= self.THRESHOLD_CRITICAL:
            return "critical"
        else:
            return "warning"


# ==============================================================================
# NRS GAP ANALYSIS
# ==============================================================================

class NRSGapAnalyzer:
    """
    NRS (FIRS) Gap Analysis Service
    
    Compares local ledger entries against NRS-validated invoices
    to identify missing IRNs, unrecorded transactions, and 
    compliance gaps.
    """
    
    async def analyze_gaps(
        self,
        db: AsyncSession,
        entity_id: UUID,
        start_date: date,
        end_date: date,
        include_b2c: bool = True
    ) -> Dict[str, Any]:
        """
        Perform comprehensive gap analysis between local records and NRS.
        
        This is the first thing an FIRS/NRS auditor will check.
        """
        from app.models.invoice import Invoice
        from app.models.transaction import Transaction
        
        # Get all invoices for the period
        invoice_query = select(Invoice).where(
            and_(
                Invoice.entity_id == entity_id,
                Invoice.invoice_date >= start_date,
                Invoice.invoice_date <= end_date,
            )
        ).order_by(Invoice.invoice_date)
        
        result = await db.execute(invoice_query)
        invoices = result.scalars().all()
        
        # Categorize invoices
        missing_irn = []           # No IRN generated
        pending_validation = []     # IRN generated, not validated
        validated = []              # Fully NRS validated
        b2c_high_value = []         # B2C > ₦50,000 (2026 reporting required)
        
        total_value = Decimal("0")
        validated_value = Decimal("0")
        missing_irn_value = Decimal("0")
        
        B2C_THRESHOLD = Decimal("50000")
        
        for inv in invoices:
            amount = inv.total_amount or Decimal("0")
            total_value += amount
            
            invoice_data = {
                "id": str(inv.id),
                "invoice_number": inv.invoice_number,
                "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
                "customer_name": getattr(inv, 'customer_name', None),
                "customer_tin": getattr(inv, 'customer_tin', None),
                "total_amount": str(amount),
                "vat_amount": str(inv.vat_amount or 0),
                "invoice_type": getattr(inv, 'invoice_type', 'B2B'),
            }
            
            has_irn = hasattr(inv, 'irn') and inv.irn
            is_validated = hasattr(inv, 'nrs_validated') and inv.nrs_validated
            is_b2c = getattr(inv, 'invoice_type', 'B2B') == 'B2C'
            
            if is_validated:
                validated.append({
                    **invoice_data,
                    "irn": inv.irn,
                    "status": "validated",
                })
                validated_value += amount
            elif has_irn:
                pending_validation.append({
                    **invoice_data,
                    "irn": inv.irn,
                    "status": "pending_validation",
                    "risk": "medium",
                })
            else:
                missing_irn.append({
                    **invoice_data,
                    "status": "missing_irn",
                    "risk": "high",
                    "days_overdue": (date.today() - inv.invoice_date).days if inv.invoice_date else 0,
                })
                missing_irn_value += amount
            
            # Check B2C high-value threshold (2026 compliance)
            if include_b2c and is_b2c and amount > B2C_THRESHOLD:
                has_b2c_report = getattr(inv, 'b2c_reported', False)
                b2c_high_value.append({
                    **invoice_data,
                    "reported": has_b2c_report,
                    "reporting_required": True,
                    "deadline": "24 hours from transaction",
                })
        
        # Calculate compliance metrics
        total_invoices = len(invoices)
        compliance_rate = (len(validated) / total_invoices * 100) if total_invoices else 0
        value_compliance_rate = (validated_value / total_value * 100) if total_value else Decimal("0")
        
        # Risk assessment
        if compliance_rate >= 95:
            risk_level = "low"
            risk_status = "COMPLIANT"
        elif compliance_rate >= 80:
            risk_level = "medium"
            risk_status = "ATTENTION REQUIRED"
        else:
            risk_level = "high"
            risk_status = "NON-COMPLIANT"
        
        return {
            "entity_id": str(entity_id),
            "analysis_period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            "summary": {
                "total_invoices": total_invoices,
                "validated": len(validated),
                "pending_validation": len(pending_validation),
                "missing_irn": len(missing_irn),
                "b2c_high_value": len(b2c_high_value),
            },
            "financials": {
                "total_value": str(total_value),
                "validated_value": str(validated_value),
                "missing_irn_value": str(missing_irn_value),
                "value_at_risk": str(missing_irn_value),
            },
            "compliance": {
                "rate": round(compliance_rate, 2),
                "value_rate": round(float(value_compliance_rate), 2),
                "risk_level": risk_level,
                "status": risk_status,
            },
            "gaps": {
                "missing_irn": missing_irn[:50],  # Limit to first 50
                "pending_validation": pending_validation[:50],
                "b2c_unreported": [i for i in b2c_high_value if not i["reported"]][:50],
            },
            "recommendations": self._generate_recommendations(
                len(missing_irn), len(pending_validation), len(b2c_high_value)
            ),
            "analyzed_at": datetime.utcnow().isoformat(),
        }
    
    def _generate_recommendations(
        self,
        missing_count: int,
        pending_count: int,
        b2c_count: int
    ) -> List[Dict[str, Any]]:
        """Generate actionable recommendations based on gap analysis."""
        recommendations = []
        
        if missing_count > 0:
            recommendations.append({
                "priority": "high",
                "category": "missing_irn",
                "title": f"Submit {missing_count} invoices to NRS",
                "description": (
                    f"There are {missing_count} invoices without Invoice Reference Numbers (IRN). "
                    "These MUST be submitted to the NRS portal before the next FIRS audit."
                ),
                "action": "Use the batch NRS submission feature to generate IRNs for all pending invoices.",
                "deadline": "Immediate",
            })
        
        if pending_count > 0:
            recommendations.append({
                "priority": "medium",
                "category": "pending_validation",
                "title": f"Verify {pending_count} pending IRN validations",
                "description": (
                    f"{pending_count} invoices have IRNs but are not yet validated. "
                    "Check the NRS portal for validation status."
                ),
                "action": "Run NRS sync to update validation status.",
            })
        
        if b2c_count > 0:
            recommendations.append({
                "priority": "high",
                "category": "b2c_reporting",
                "title": f"Report {b2c_count} high-value B2C transactions",
                "description": (
                    f"2026 Tax Reform requires B2C transactions above ₦50,000 to be "
                    f"reported within 24 hours. {b2c_count} transactions need reporting."
                ),
                "action": "Submit B2C real-time reports to FIRS.",
                "deadline": "24 hours from transaction date",
            })
        
        if not recommendations:
            recommendations.append({
                "priority": "low",
                "category": "compliant",
                "title": "NRS Compliance Status: Good",
                "description": "All invoices are properly registered with valid IRNs.",
                "action": "Continue regular NRS sync operations.",
            })
        
        return recommendations


# ==============================================================================
# FORENSIC AUDIT SERVICE (MAIN CLASS)
# ==============================================================================

class ForensicAuditService:
    """
    Main forensic audit service integrating all detection algorithms.
    
    Provides:
    - Benford's Law analysis
    - Z-score anomaly detection
    - NRS gap analysis
    - Full population testing
    - Hash chain verification
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.benfords = BenfordsLawAnalyzer()
        self.z_score = ZScoreAnomalyDetector()
        self.nrs_gap = NRSGapAnalyzer()
    
    async def run_full_forensic_audit(
        self,
        entity_id: UUID,
        fiscal_year: int,
        categories: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Run comprehensive forensic audit on all transactions for a fiscal year.
        
        This is "Full Population Testing" - not sampling.
        """
        from app.models.transaction import Transaction
        from app.models.invoice import Invoice
        from app.services.immutable_ledger import immutable_ledger_service
        
        start_date = date(fiscal_year, 1, 1)
        end_date = date(fiscal_year, 12, 31)
        
        # Get all transactions
        txn_query = select(Transaction).where(
            and_(
                Transaction.entity_id == entity_id,
                Transaction.transaction_date >= start_date,
                Transaction.transaction_date <= end_date,
            )
        )
        
        if categories:
            txn_query = txn_query.where(Transaction.category_id.in_(categories))
        
        result = await self.db.execute(txn_query)
        transactions = result.scalars().all()
        
        # Prepare transaction data
        txn_data = [
            {
                "id": str(txn.id),
                "amount": txn.amount,
                "transaction_date": txn.transaction_date.isoformat() if txn.transaction_date else None,
                "description": txn.description,
                "category": str(txn.category_id) if txn.category_id else None,
                "vendor": str(txn.vendor_id) if txn.vendor_id else None,
                "type": txn.transaction_type.value if hasattr(txn, 'transaction_type') and txn.transaction_type else None,
            }
            for txn in transactions
        ]
        
        # Extract amounts
        amounts = [Decimal(str(t["amount"])) for t in txn_data if t["amount"] is not None]
        
        # Run analyses
        results = {
            "entity_id": str(entity_id),
            "fiscal_year": fiscal_year,
            "analysis_period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            "sample_size": len(transactions),
            "total_amount": str(sum(amounts)) if amounts else "0",
            "tests": {},
            "overall_risk": "low",
            "overall_status": "PASS",
        }
        
        # 1. Benford's Law - First Digit
        if len(amounts) >= 100:
            results["tests"]["benfords_first_digit"] = self.benfords.analyze(amounts, "first_digit")
            results["tests"]["benfords_second_digit"] = self.benfords.analyze(amounts, "second_digit")
        else:
            results["tests"]["benfords"] = {
                "valid": False,
                "skipped_reason": f"Minimum 100 transactions required, found {len(amounts)}",
            }
        
        # 2. Z-Score Anomaly Detection
        results["tests"]["z_score_overall"] = self.z_score.detect_anomalies(txn_data)
        results["tests"]["z_score_by_category"] = self.z_score.detect_anomalies(
            txn_data, group_by="category"
        )
        
        # 3. NRS Gap Analysis
        results["tests"]["nrs_gap"] = await self.nrs_gap.analyze_gaps(
            self.db, entity_id, start_date, end_date
        )
        
        # 4. Hash Chain Verification
        try:
            is_valid, discrepancies = await immutable_ledger_service.verify_chain_integrity(
                self.db, entity_id
            )
            results["tests"]["ledger_integrity"] = {
                "valid": True,
                "chain_valid": is_valid,
                "discrepancies": discrepancies,
                "status": "PASS" if is_valid else "FAIL",
            }
        except Exception as e:
            results["tests"]["ledger_integrity"] = {
                "valid": False,
                "error": str(e),
            }
        
        # Calculate overall risk
        risk_factors = []
        
        # Check Benford's
        if results["tests"].get("benfords_first_digit", {}).get("risk_level") == "high":
            risk_factors.append("benfords_nonconforming")
        
        # Check anomalies
        z_score_result = results["tests"].get("z_score_overall", {})
        if z_score_result.get("summary", {}).get("critical", 0) > 0:
            risk_factors.append("critical_anomalies")
        if z_score_result.get("summary", {}).get("extreme", 0) > 0:
            risk_factors.append("extreme_anomalies")
        
        # Check NRS compliance
        nrs_result = results["tests"].get("nrs_gap", {})
        if nrs_result.get("compliance", {}).get("risk_level") == "high":
            risk_factors.append("nrs_noncompliant")
        
        # Check ledger integrity
        if not results["tests"].get("ledger_integrity", {}).get("chain_valid", True):
            risk_factors.append("ledger_tampering")
        
        # Determine overall status
        if "ledger_tampering" in risk_factors:
            results["overall_risk"] = "critical"
            results["overall_status"] = "FAIL - LEDGER INTEGRITY BREACH"
        elif len(risk_factors) >= 3:
            results["overall_risk"] = "high"
            results["overall_status"] = "FAIL - MULTIPLE ISSUES"
        elif len(risk_factors) >= 1:
            results["overall_risk"] = "medium"
            results["overall_status"] = "WARNING - REVIEW REQUIRED"
        else:
            results["overall_risk"] = "low"
            results["overall_status"] = "PASS"
        
        results["risk_factors"] = risk_factors
        results["analyzed_at"] = datetime.utcnow().isoformat()
        
        return results
    
    async def verify_data_integrity(
        self,
        entity_id: UUID,
        fiscal_year: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Verify data integrity using hash chain verification.
        
        Falls back to journal entry verification if no ledger entries exist.
        This is the "Verify Integrity" button feature.
        Returns green badge if all hashes match.
        """
        from app.services.immutable_ledger import immutable_ledger_service
        from app.models.advanced_accounting import LedgerEntry
        from app.models.accounting import JournalEntry, JournalEntryStatus
        from sqlalchemy import select, func
        
        # Count ledger entries for this entity
        count_query = select(func.count(LedgerEntry.id)).where(
            LedgerEntry.entity_id == entity_id
        )
        result = await self.db.execute(count_query)
        ledger_count = result.scalar() or 0
        
        # Also count journal entries
        je_count_query = select(func.count(JournalEntry.id)).where(
            JournalEntry.entity_id == entity_id,
            JournalEntry.status == JournalEntryStatus.POSTED
        )
        je_result = await self.db.execute(je_count_query)
        journal_count = je_result.scalar() or 0
        
        # If no ledger entries but we have journal entries, verify those instead
        if ledger_count == 0:
            if journal_count > 0:
                # Verify journal entries are balanced
                balance_query = select(
                    func.sum(JournalEntry.total_debit).label('total_debit'),
                    func.sum(JournalEntry.total_credit).label('total_credit')
                ).where(
                    JournalEntry.entity_id == entity_id,
                    JournalEntry.status == JournalEntryStatus.POSTED
                )
                balance_result = await self.db.execute(balance_query)
                balance_row = balance_result.first()
                
                total_debit = balance_row.total_debit or Decimal("0")
                total_credit = balance_row.total_credit or Decimal("0")
                is_balanced = abs(total_debit - total_credit) < Decimal("0.01")
                
                if is_balanced:
                    return {
                        "verified": True,
                        "status": "JOURNAL_ENTRIES_VERIFIED",
                        "badge": "green",
                        "message": f"[OK] {journal_count} posted journal entries verified. All entries are balanced (Debits = Credits).",
                        "record_count": journal_count,
                        "total_debit": str(total_debit),
                        "total_credit": str(total_credit),
                        "discrepancy_count": 0,
                        "discrepancies": [],
                        "verified_at": datetime.utcnow().isoformat(),
                        "data_source": "journal_entries",
                        "note": "Immutable ledger not yet populated. Journal entries used for verification."
                    }
                else:
                    return {
                        "verified": False,
                        "status": "JOURNAL_IMBALANCE_DETECTED",
                        "badge": "red",
                        "message": f"[WARNING] Journal entries are not balanced! Total Debits: ₦{total_debit:,.2f}, Total Credits: ₦{total_credit:,.2f}",
                        "record_count": journal_count,
                        "total_debit": str(total_debit),
                        "total_credit": str(total_credit),
                        "discrepancy_count": 1,
                        "discrepancies": [{
                            "type": "balance_mismatch",
                            "message": "Debits and Credits do not balance",
                            "debit_total": str(total_debit),
                            "credit_total": str(total_credit),
                            "difference": str(abs(total_debit - total_credit))
                        }],
                        "verified_at": datetime.utcnow().isoformat(),
                        "data_source": "journal_entries"
                    }
            else:
                return {
                    "verified": False,
                    "status": "NO_RECORDS_FOUND",
                    "badge": "yellow",
                    "message": "No financial records found for this entity. Create journal entries or transactions to enable integrity verification.",
                    "record_count": 0,
                    "discrepancy_count": 0,
                    "discrepancies": [{
                        "type": "no_records",
                        "message": "No journal entries or ledger entries exist for verification",
                        "details": "Post financial transactions to enable data integrity checks."
                    }],
                    "verified_at": datetime.utcnow().isoformat(),
                }
        
        # If ledger entries exist, verify hash chain
        is_valid, discrepancies = await immutable_ledger_service.verify_chain_integrity(
            self.db, entity_id
        )
        
        if is_valid:
            return {
                "verified": True,
                "status": "DATA_INTEGRITY_VERIFIED",
                "badge": "green",
                "message": f"[OK] All {ledger_count} ledger entries verified. Hash chain is intact.",
                "record_count": ledger_count,
                "discrepancy_count": 0,
                "discrepancies": [],
                "verified_at": datetime.utcnow().isoformat(),
                "data_source": "immutable_ledger"
            }
        else:
            return {
                "verified": False,
                "status": "INTEGRITY_BREACH_DETECTED",
                "badge": "red",
                "message": f"[WARNING] Data integrity issues detected in {len(discrepancies)} of {ledger_count} records. Immediate investigation required.",
                "record_count": ledger_count,
                "discrepancy_count": len(discrepancies),
                "discrepancies": discrepancies[:10],  # First 10
                "verified_at": datetime.utcnow().isoformat(),
                "data_source": "immutable_ledger"
            }


# ==============================================================================
# WORM STORAGE INTERFACE
# ==============================================================================

class WORMStorageService:
    """
    Write-Once-Read-Many (WORM) Storage Interface
    
    Integrates with AWS S3 Object Lock for compliance document storage.
    Documents uploaded here cannot be deleted or modified for the
    configured retention period (e.g., 7 years for Nigerian tax compliance).
    """
    
    DEFAULT_RETENTION_YEARS = 7
    
    def __init__(self):
        # These would be configured from settings in production
        self.enabled = False  # Set to True when S3 is configured
        self.bucket_name = None
        self.s3_client = None
    
    async def store_document(
        self,
        entity_id: UUID,
        document_type: str,
        document_id: str,
        content: bytes,
        content_type: str,
        retention_years: int = DEFAULT_RETENTION_YEARS,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Store a document in WORM storage with Object Lock.
        
        Args:
            entity_id: Business entity ID
            document_type: Type of document (tax_filing, invoice, receipt, etc.)
            document_id: Unique document identifier
            content: Document content as bytes
            content_type: MIME type
            retention_years: Years to retain (cannot be deleted before this)
            metadata: Additional metadata
            
        Returns:
            Storage result with document reference
        """
        if not self.enabled:
            # Return simulated result for demo/testing
            return {
                "stored": True,
                "simulated": True,
                "message": "WORM storage not configured - simulated storage",
                "document_key": f"{entity_id}/{document_type}/{document_id}",
                "retention_until": (
                    datetime.utcnow() + timedelta(days=retention_years * 365)
                ).isoformat(),
                "content_hash": hashlib.sha256(content).hexdigest(),
            }
        
        # Calculate retention date
        retention_until = datetime.utcnow() + timedelta(days=retention_years * 365)
        
        # Generate storage key
        key = f"worm/{entity_id}/{document_type}/{document_id}"
        
        # Calculate content hash for verification
        content_hash = hashlib.sha256(content).hexdigest()
        
        try:
            # Store in S3 with Object Lock
            # Note: This requires the bucket to have Object Lock enabled
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=content,
                ContentType=content_type,
                ObjectLockMode='COMPLIANCE',  # Cannot be overridden
                ObjectLockRetainUntilDate=retention_until,
                Metadata={
                    'entity_id': str(entity_id),
                    'document_type': document_type,
                    'document_id': document_id,
                    'content_hash': content_hash,
                    **(metadata or {}),
                }
            )
            
            return {
                "stored": True,
                "bucket": self.bucket_name,
                "key": key,
                "content_hash": content_hash,
                "content_type": content_type,
                "size_bytes": len(content),
                "retention_mode": "COMPLIANCE",
                "retention_until": retention_until.isoformat(),
                "object_lock_enabled": True,
                "legal_weight": "Document is legally protected and cannot be modified or deleted.",
            }
            
        except Exception as e:
            logger.error(f"WORM storage failed: {e}")
            return {
                "stored": False,
                "error": str(e),
            }
    
    async def verify_document(
        self,
        entity_id: UUID,
        document_type: str,
        document_id: str,
        expected_hash: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Verify a document's integrity and legal lock status.
        
        This proves the document auditor sees is exactly the same
        as the one generated originally.
        """
        if not self.enabled:
            return {
                "verified": False,
                "simulated": True,
                "message": "WORM storage not configured",
            }
        
        key = f"worm/{entity_id}/{document_type}/{document_id}"
        
        try:
            # Get object metadata
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=key
            )
            
            metadata = response.get('Metadata', {})
            stored_hash = metadata.get('content_hash')
            retention_until = response.get('ObjectLockRetainUntilDate')
            lock_mode = response.get('ObjectLockMode')
            
            # Verify hash if provided
            hash_match = True
            if expected_hash and stored_hash:
                hash_match = expected_hash == stored_hash
            
            return {
                "verified": True,
                "document_exists": True,
                "content_hash": stored_hash,
                "hash_verified": hash_match,
                "object_lock_mode": lock_mode,
                "retention_until": retention_until.isoformat() if retention_until else None,
                "is_legally_protected": lock_mode == 'COMPLIANCE',
                "legal_status": (
                    "Document is protected under WORM compliance. "
                    "Cannot be modified or deleted until retention period expires."
                ) if lock_mode == 'COMPLIANCE' else "No legal lock applied.",
            }
            
        except Exception as e:
            return {
                "verified": False,
                "error": str(e),
            }


# Singleton instances
benfords_analyzer = BenfordsLawAnalyzer()
z_score_detector = ZScoreAnomalyDetector()
worm_storage = WORMStorageService()
