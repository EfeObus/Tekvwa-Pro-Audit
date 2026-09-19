"""
Tekvwa Pro Audit - Behavioral Analytics Service

This module provides behavioral analytics for detecting anomalous patterns:
- Unusual timing patterns (odd-hour edits, weekend transactions)
- Volume anomalies (VAT refund spikes, sudden expense increases)
- Pattern anomalies (year-end asset disposals, circular transactions)
- User behavior profiling for insider threat detection
- Risk scoring with detailed explanations

Based on statistical analysis and rule-based detection engines.
"""

import uuid
from datetime import datetime, date, time, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import statistics
import math


class AnomalyCategory(str, Enum):
    """Categories of behavioral anomalies."""
    TIMING = "timing"
    VOLUME = "volume"
    PATTERN = "pattern"
    USER_BEHAVIOR = "user_behavior"
    TRANSACTION = "transaction"
    TAX_EVASION = "tax_evasion"


class RiskLevel(str, Enum):
    """Risk levels for detected anomalies."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AnomalyType(str, Enum):
    """Specific types of anomalies detected."""
    ODD_HOUR_EDIT = "odd_hour_edit"
    WEEKEND_TRANSACTION = "weekend_transaction"
    HOLIDAY_ACTIVITY = "holiday_activity"
    VAT_REFUND_SPIKE = "vat_refund_spike"
    EXPENSE_SURGE = "expense_surge"
    REVENUE_DROP = "revenue_drop"
    YEAR_END_ASSET_DISPOSAL = "year_end_asset_disposal"
    CIRCULAR_TRANSACTION = "circular_transaction"
    RELATED_PARTY_PATTERN = "related_party_pattern"
    INVOICE_SPLITTING = "invoice_splitting"
    ROUND_NUMBER_BIAS = "round_number_bias"
    MISSING_SEQUENCE = "missing_sequence"
    DUPLICATE_AMOUNT = "duplicate_amount"
    VELOCITY_ANOMALY = "velocity_anomaly"
    ACCESS_PATTERN = "access_pattern"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    DATA_EXPORT_SPIKE = "data_export_spike"


@dataclass
class BehavioralAnomaly:
    """A detected behavioral anomaly."""
    anomaly_id: str
    category: AnomalyCategory
    anomaly_type: AnomalyType
    risk_level: RiskLevel
    risk_score: float  # 0-100
    title: str
    description: str
    evidence: Dict[str, Any]
    detected_at: datetime
    affected_period: Tuple[date, date]
    affected_records: List[str]
    recommendations: List[str]
    false_positive_probability: float  # 0-1
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "anomaly_id": self.anomaly_id,
            "category": self.category.value,
            "anomaly_type": self.anomaly_type.value,
            "risk_level": self.risk_level.value,
            "risk_score": self.risk_score,
            "title": self.title,
            "description": self.description,
            "evidence": self.evidence,
            "detected_at": self.detected_at.isoformat(),
            "affected_period": {
                "start": self.affected_period[0].isoformat(),
                "end": self.affected_period[1].isoformat(),
            },
            "affected_records": self.affected_records[:10],  # Limit for display
            "affected_record_count": len(self.affected_records),
            "recommendations": self.recommendations,
            "false_positive_probability": self.false_positive_probability,
        }


@dataclass
class UserBehaviorProfile:
    """Profile of a user's typical behavior."""
    user_id: str
    typical_work_hours: Tuple[int, int]  # start, end hour
    typical_work_days: List[int]  # 0=Monday, 6=Sunday
    average_transactions_per_day: float
    average_transaction_amount: float
    common_transaction_types: List[str]
    access_patterns: Dict[str, int]
    last_updated: datetime


@dataclass
class BehavioralAnalysisReport:
    """Complete behavioral analysis report."""
    entity_id: uuid.UUID
    analysis_date: datetime
    period_start: date
    period_end: date
    total_transactions_analyzed: int
    total_anomalies_detected: int
    anomalies_by_category: Dict[str, int]
    anomalies_by_risk: Dict[str, int]
    overall_risk_score: float
    anomalies: List[BehavioralAnomaly]
    summary: str
    top_concerns: List[Dict[str, Any]]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": str(self.entity_id),
            "analysis_date": self.analysis_date.isoformat(),
            "period": {
                "start": self.period_start.isoformat(),
                "end": self.period_end.isoformat(),
            },
            "statistics": {
                "transactions_analyzed": self.total_transactions_analyzed,
                "anomalies_detected": self.total_anomalies_detected,
                "by_category": self.anomalies_by_category,
                "by_risk_level": self.anomalies_by_risk,
            },
            "overall_risk_score": self.overall_risk_score,
            "anomalies": [a.to_dict() for a in self.anomalies],
            "summary": self.summary,
            "top_concerns": self.top_concerns,
        }


# Nigerian public holidays (2026)
NIGERIA_HOLIDAYS_2026 = [
    date(2026, 1, 1),   # New Year
    date(2026, 3, 30),  # Eid al-Fitr (estimated)
    date(2026, 3, 31),  # Eid al-Fitr Day 2
    date(2026, 4, 10),  # Good Friday
    date(2026, 4, 13),  # Easter Monday
    date(2026, 5, 1),   # Workers Day
    date(2026, 5, 27),  # Children's Day
    date(2026, 6, 6),   # Eid al-Adha (estimated)
    date(2026, 6, 7),   # Eid al-Adha Day 2
    date(2026, 6, 12),  # Democracy Day
    date(2026, 10, 1),  # Independence Day
    date(2026, 12, 25), # Christmas
    date(2026, 12, 26), # Boxing Day
]


class TimingAnomalyDetector:
    """Detects anomalies related to timing of activities."""
    
    BUSINESS_HOURS_START = 8
    BUSINESS_HOURS_END = 18
    WORKING_DAYS = [0, 1, 2, 3, 4]  # Monday-Friday
    
    @classmethod
    def detect_odd_hour_activity(
        cls,
        activities: List[Dict[str, Any]],
        threshold_pct: float = 10.0,
    ) -> List[BehavioralAnomaly]:
        """Detect activities occurring outside normal business hours."""
        anomalies = []
        odd_hour_activities = []
        
        for activity in activities:
            activity_time = activity.get("timestamp")
            if isinstance(activity_time, str):
                activity_time = datetime.fromisoformat(activity_time)
            if isinstance(activity_time, datetime):
                hour = activity_time.hour
                if hour < cls.BUSINESS_HOURS_START or hour >= cls.BUSINESS_HOURS_END:
                    odd_hour_activities.append(activity)
        
        if not activities:
            return []
        
        odd_hour_pct = (len(odd_hour_activities) / len(activities)) * 100
        
        if odd_hour_pct > threshold_pct:
            anomalies.append(BehavioralAnomaly(
                anomaly_id=f"TIM-{uuid.uuid4().hex[:8].upper()}",
                category=AnomalyCategory.TIMING,
                anomaly_type=AnomalyType.ODD_HOUR_EDIT,
                risk_level=RiskLevel.MEDIUM if odd_hour_pct < 25 else RiskLevel.HIGH,
                risk_score=min(80, odd_hour_pct * 2),
                title="Unusual After-Hours Activity Pattern",
                description=f"{odd_hour_pct:.1f}% of activities occur outside business hours (8AM-6PM). This exceeds the threshold of {threshold_pct}%.",
                evidence={
                    "total_activities": len(activities),
                    "odd_hour_activities": len(odd_hour_activities),
                    "percentage": odd_hour_pct,
                    "sample_times": [
                        str(a.get("timestamp")) for a in odd_hour_activities[:5]
                    ],
                },
                detected_at=datetime.utcnow(),
                affected_period=(date.today() - timedelta(days=30), date.today()),
                affected_records=[str(a.get("id", "")) for a in odd_hour_activities],
                recommendations=[
                    "Review after-hours activities for legitimacy",
                    "Implement approval workflow for off-hours transactions",
                    "Consider restricting system access outside business hours",
                ],
                false_positive_probability=0.3,
            ))
        
        return anomalies
    
    @classmethod
    def detect_weekend_transactions(
        cls,
        transactions: List[Dict[str, Any]],
        threshold_pct: float = 5.0,
    ) -> List[BehavioralAnomaly]:
        """Detect transactions occurring on weekends."""
        anomalies = []
        weekend_txns = []
        
        for txn in transactions:
            txn_date = txn.get("date")
            if isinstance(txn_date, str):
                txn_date = date.fromisoformat(txn_date)
            if isinstance(txn_date, date):
                if txn_date.weekday() in [5, 6]:  # Saturday, Sunday
                    weekend_txns.append(txn)
        
        if not transactions:
            return []
        
        weekend_pct = (len(weekend_txns) / len(transactions)) * 100
        
        if weekend_pct > threshold_pct:
            anomalies.append(BehavioralAnomaly(
                anomaly_id=f"TIM-{uuid.uuid4().hex[:8].upper()}",
                category=AnomalyCategory.TIMING,
                anomaly_type=AnomalyType.WEEKEND_TRANSACTION,
                risk_level=RiskLevel.MEDIUM,
                risk_score=min(60, weekend_pct * 3),
                title="Elevated Weekend Transaction Activity",
                description=f"{weekend_pct:.1f}% of transactions occur on weekends, exceeding threshold of {threshold_pct}%.",
                evidence={
                    "total_transactions": len(transactions),
                    "weekend_transactions": len(weekend_txns),
                    "percentage": weekend_pct,
                    "weekend_dates": list(set(
                        str(t.get("date")) for t in weekend_txns[:10]
                    )),
                },
                detected_at=datetime.utcnow(),
                affected_period=(date.today() - timedelta(days=30), date.today()),
                affected_records=[str(t.get("id", "")) for t in weekend_txns],
                recommendations=[
                    "Verify weekend transactions are legitimate business activities",
                    "Implement weekend transaction approval requirements",
                ],
                false_positive_probability=0.4,
            ))
        
        return anomalies
    
    @classmethod
    def detect_holiday_activity(
        cls,
        activities: List[Dict[str, Any]],
        holidays: List[date] = None,
    ) -> List[BehavioralAnomaly]:
        """Detect activities on public holidays."""
        anomalies = []
        holidays = holidays or NIGERIA_HOLIDAYS_2026
        holiday_activities = []
        
        for activity in activities:
            activity_date = activity.get("date")
            if isinstance(activity_date, str):
                activity_date = date.fromisoformat(activity_date)
            if isinstance(activity_date, date):
                if activity_date in holidays:
                    holiday_activities.append(activity)
        
        if holiday_activities:
            anomalies.append(BehavioralAnomaly(
                anomaly_id=f"TIM-{uuid.uuid4().hex[:8].upper()}",
                category=AnomalyCategory.TIMING,
                anomaly_type=AnomalyType.HOLIDAY_ACTIVITY,
                risk_level=RiskLevel.LOW,
                risk_score=len(holiday_activities) * 5,
                title="Activity on Public Holidays",
                description=f"{len(holiday_activities)} activities recorded on Nigerian public holidays.",
                evidence={
                    "holiday_activity_count": len(holiday_activities),
                    "holidays_affected": list(set(
                        str(a.get("date")) for a in holiday_activities
                    )),
                },
                detected_at=datetime.utcnow(),
                affected_period=(date.today() - timedelta(days=365), date.today()),
                affected_records=[str(a.get("id", "")) for a in holiday_activities],
                recommendations=[
                    "Verify holiday activities are legitimate",
                    "Consider if backdating of transactions occurred",
                ],
                false_positive_probability=0.5,
            ))
        
        return anomalies


class VolumeAnomalyDetector:
    """Detects anomalies in transaction volumes and amounts."""
    
    @classmethod
    def detect_vat_refund_spike(
        cls,
        vat_records: List[Dict[str, Any]],
        z_score_threshold: float = 2.5,
    ) -> List[BehavioralAnomaly]:
        """Detect unusual spikes in VAT refund claims."""
        anomalies = []
        
        # Extract refund amounts
        refunds = []
        for record in vat_records:
            net_vat = record.get("net_vat", 0)
            if net_vat < 0:  # Refund situation
                refunds.append({
                    "period": record.get("period"),
                    "amount": abs(net_vat),
                    "record": record,
                })
        
        if len(refunds) < 3:
            return []
        
        amounts = [r["amount"] for r in refunds]
        mean_refund = statistics.mean(amounts)
        std_refund = statistics.stdev(amounts) if len(amounts) > 1 else 1
        
        spikes = []
        for refund in refunds:
            if std_refund > 0:
                z_score = (refund["amount"] - mean_refund) / std_refund
                if z_score > z_score_threshold:
                    spikes.append({
                        **refund,
                        "z_score": z_score,
                    })
        
        if spikes:
            total_spike_amount = sum(s["amount"] for s in spikes)
            anomalies.append(BehavioralAnomaly(
                anomaly_id=f"VOL-{uuid.uuid4().hex[:8].upper()}",
                category=AnomalyCategory.VOLUME,
                anomaly_type=AnomalyType.VAT_REFUND_SPIKE,
                risk_level=RiskLevel.HIGH,
                risk_score=min(90, 50 + max(s["z_score"] for s in spikes) * 10),
                title="VAT Refund Claim Spike Detected",
                description=f"{len(spikes)} periods show abnormally high VAT refund claims totaling NGN {total_spike_amount:,.2f}.",
                evidence={
                    "spike_count": len(spikes),
                    "total_spike_amount": total_spike_amount,
                    "mean_refund": mean_refund,
                    "std_deviation": std_refund,
                    "spikes": [
                        {"period": s["period"], "amount": s["amount"], "z_score": s["z_score"]}
                        for s in spikes
                    ],
                },
                detected_at=datetime.utcnow(),
                affected_period=(date.today() - timedelta(days=365), date.today()),
                affected_records=[str(s.get("record", {}).get("id", "")) for s in spikes],
                recommendations=[
                    "Review input VAT claims for proper documentation",
                    "Verify WREN compliance for claimed expenses",
                    "Cross-check supplier invoices with NRS",
                    "Consider requesting VAT audit",
                ],
                false_positive_probability=0.15,
            ))
        
        return anomalies
    
    @classmethod
    def detect_expense_surge(
        cls,
        expenses_by_period: List[Dict[str, Any]],
        surge_threshold_pct: float = 50.0,
    ) -> List[BehavioralAnomaly]:
        """Detect sudden increases in expenses."""
        anomalies = []
        
        if len(expenses_by_period) < 2:
            return []
        
        # Sort by period
        sorted_expenses = sorted(expenses_by_period, key=lambda x: x.get("period", ""))
        
        surges = []
        for i in range(1, len(sorted_expenses)):
            prev_amount = sorted_expenses[i - 1].get("amount", 0)
            curr_amount = sorted_expenses[i].get("amount", 0)
            
            if prev_amount > 0:
                change_pct = ((curr_amount - prev_amount) / prev_amount) * 100
                if change_pct > surge_threshold_pct:
                    surges.append({
                        "period": sorted_expenses[i].get("period"),
                        "previous_amount": prev_amount,
                        "current_amount": curr_amount,
                        "change_pct": change_pct,
                    })
        
        if surges:
            anomalies.append(BehavioralAnomaly(
                anomaly_id=f"VOL-{uuid.uuid4().hex[:8].upper()}",
                category=AnomalyCategory.VOLUME,
                anomaly_type=AnomalyType.EXPENSE_SURGE,
                risk_level=RiskLevel.MEDIUM,
                risk_score=min(70, 30 + len(surges) * 10),
                title="Unusual Expense Surge Detected",
                description=f"{len(surges)} periods show expense increases exceeding {surge_threshold_pct}% threshold.",
                evidence={
                    "surge_count": len(surges),
                    "surges": surges,
                },
                detected_at=datetime.utcnow(),
                affected_period=(date.today() - timedelta(days=365), date.today()),
                affected_records=[],
                recommendations=[
                    "Review expense documentation for surge periods",
                    "Verify expenses are legitimate business costs",
                    "Check for potential expense inflation",
                ],
                false_positive_probability=0.3,
            ))
        
        return anomalies


class PatternAnomalyDetector:
    """Detects suspicious patterns in transactions."""
    
    @classmethod
    def detect_year_end_asset_disposal(
        cls,
        asset_disposals: List[Dict[str, Any]],
        year_end_threshold_pct: float = 40.0,
    ) -> List[BehavioralAnomaly]:
        """Detect concentration of asset disposals at year-end."""
        anomalies = []
        
        if not asset_disposals:
            return []
        
        # Count disposals in Q4 (Oct, Nov, Dec)
        q4_disposals = [
            d for d in asset_disposals
            if d.get("disposal_month", 0) in [10, 11, 12]
        ]
        
        q4_pct = (len(q4_disposals) / len(asset_disposals)) * 100
        
        if q4_pct > year_end_threshold_pct:
            q4_value = sum(float(d.get("disposal_value", 0)) for d in q4_disposals)
            anomalies.append(BehavioralAnomaly(
                anomaly_id=f"PAT-{uuid.uuid4().hex[:8].upper()}",
                category=AnomalyCategory.PATTERN,
                anomaly_type=AnomalyType.YEAR_END_ASSET_DISPOSAL,
                risk_level=RiskLevel.HIGH,
                risk_score=min(85, q4_pct + 20),
                title="Year-End Asset Disposal Concentration",
                description=f"{q4_pct:.1f}% of asset disposals occur in Q4, suggesting potential tax manipulation.",
                evidence={
                    "total_disposals": len(asset_disposals),
                    "q4_disposals": len(q4_disposals),
                    "q4_percentage": q4_pct,
                    "q4_total_value": q4_value,
                },
                detected_at=datetime.utcnow(),
                affected_period=(date(date.today().year, 10, 1), date(date.today().year, 12, 31)),
                affected_records=[str(d.get("id", "")) for d in q4_disposals],
                recommendations=[
                    "Review asset disposal valuations",
                    "Verify disposals at arm's length",
                    "Check for related party transactions",
                    "Review capital gains tax implications",
                ],
                false_positive_probability=0.2,
            ))
        
        return anomalies
    
    @classmethod
    def detect_invoice_splitting(
        cls,
        invoices: List[Dict[str, Any]],
        threshold_amount: float = 500000,  # Amount that might trigger special treatment
        time_window_days: int = 7,
    ) -> List[BehavioralAnomaly]:
        """Detect potential invoice splitting to avoid thresholds."""
        anomalies = []
        
        # Group invoices by customer within time window
        customer_invoices: Dict[str, List] = defaultdict(list)
        for inv in invoices:
            customer = inv.get("customer_id", inv.get("customer_name", "unknown"))
            customer_invoices[customer].append(inv)
        
        splitting_suspects = []
        
        for customer, invs in customer_invoices.items():
            # Sort by date
            sorted_invs = sorted(invs, key=lambda x: x.get("date", ""))
            
            # Look for clusters of small invoices
            for i, inv in enumerate(sorted_invs):
                inv_date = inv.get("date")
                if isinstance(inv_date, str):
                    inv_date = date.fromisoformat(inv_date)
                
                # Find invoices within time window
                cluster = [inv]
                for j in range(i + 1, len(sorted_invs)):
                    other_date = sorted_invs[j].get("date")
                    if isinstance(other_date, str):
                        other_date = date.fromisoformat(other_date)
                    
                    if isinstance(inv_date, date) and isinstance(other_date, date):
                        if (other_date - inv_date).days <= time_window_days:
                            cluster.append(sorted_invs[j])
                
                # Check if cluster total exceeds threshold while individuals don't
                if len(cluster) >= 3:
                    cluster_total = sum(float(c.get("amount", 0)) for c in cluster)
                    max_individual = max(float(c.get("amount", 0)) for c in cluster)
                    
                    if cluster_total >= threshold_amount and max_individual < threshold_amount * 0.5:
                        splitting_suspects.append({
                            "customer": customer,
                            "invoice_count": len(cluster),
                            "cluster_total": cluster_total,
                            "max_individual": max_individual,
                            "invoices": [c.get("invoice_number") for c in cluster],
                        })
        
        if splitting_suspects:
            anomalies.append(BehavioralAnomaly(
                anomaly_id=f"PAT-{uuid.uuid4().hex[:8].upper()}",
                category=AnomalyCategory.PATTERN,
                anomaly_type=AnomalyType.INVOICE_SPLITTING,
                risk_level=RiskLevel.HIGH,
                risk_score=70 + len(splitting_suspects) * 5,
                title="Potential Invoice Splitting Pattern",
                description=f"{len(splitting_suspects)} customer(s) show patterns suggesting invoice splitting to avoid thresholds.",
                evidence={
                    "suspect_count": len(splitting_suspects),
                    "threshold_amount": threshold_amount,
                    "time_window_days": time_window_days,
                    "suspects": splitting_suspects[:5],
                },
                detected_at=datetime.utcnow(),
                affected_period=(date.today() - timedelta(days=90), date.today()),
                affected_records=[
                    inv for s in splitting_suspects for inv in s["invoices"]
                ],
                recommendations=[
                    "Review flagged invoice clusters",
                    "Verify legitimate business reasons for multiple invoices",
                    "Consider consolidating for accurate reporting",
                ],
                false_positive_probability=0.25,
            ))
        
        return anomalies
    
    @classmethod
    def detect_round_number_bias(
        cls,
        amounts: List[float],
        round_number_threshold_pct: float = 30.0,
    ) -> List[BehavioralAnomaly]:
        """Detect excessive use of round numbers suggesting estimation or fabrication."""
        anomalies = []
        
        if not amounts:
            return []
        
        round_numbers = [a for a in amounts if a % 1000 == 0 or a % 500 == 0]
        round_pct = (len(round_numbers) / len(amounts)) * 100
        
        if round_pct > round_number_threshold_pct:
            anomalies.append(BehavioralAnomaly(
                anomaly_id=f"PAT-{uuid.uuid4().hex[:8].upper()}",
                category=AnomalyCategory.PATTERN,
                anomaly_type=AnomalyType.ROUND_NUMBER_BIAS,
                risk_level=RiskLevel.MEDIUM,
                risk_score=min(60, round_pct),
                title="Excessive Round Number Usage",
                description=f"{round_pct:.1f}% of amounts are round numbers (multiples of 500 or 1000), suggesting potential estimation.",
                evidence={
                    "total_amounts": len(amounts),
                    "round_numbers": len(round_numbers),
                    "percentage": round_pct,
                    "sample_round": round_numbers[:10],
                },
                detected_at=datetime.utcnow(),
                affected_period=(date.today() - timedelta(days=90), date.today()),
                affected_records=[],
                recommendations=[
                    "Review transactions with round amounts for supporting documentation",
                    "Verify amounts against source documents (invoices, receipts)",
                ],
                false_positive_probability=0.4,
            ))
        
        return anomalies


class BehavioralAnalyticsService:
    """
    Main service for behavioral analytics and anomaly detection.
    
    Combines multiple detection engines to provide comprehensive analysis.
    """
    
    def __init__(self):
        self.timing_detector = TimingAnomalyDetector()
        self.volume_detector = VolumeAnomalyDetector()
        self.pattern_detector = PatternAnomalyDetector()
        self._analysis_history: List[BehavioralAnalysisReport] = []
    
    async def run_full_analysis(
        self,
        entity_id: uuid.UUID,
        period_start: date,
        period_end: date,
        transactions: List[Dict[str, Any]],
        activities: List[Dict[str, Any]],
        vat_records: List[Dict[str, Any]],
        asset_disposals: List[Dict[str, Any]],
        invoices: List[Dict[str, Any]],
    ) -> BehavioralAnalysisReport:
        """
        Run comprehensive behavioral analysis across all detection engines.
        """
        all_anomalies = []
        
        # Timing Analysis
        all_anomalies.extend(
            self.timing_detector.detect_odd_hour_activity(activities)
        )
        all_anomalies.extend(
            self.timing_detector.detect_weekend_transactions(transactions)
        )
        all_anomalies.extend(
            self.timing_detector.detect_holiday_activity(activities)
        )
        
        # Volume Analysis
        all_anomalies.extend(
            self.volume_detector.detect_vat_refund_spike(vat_records)
        )
        
        # Pattern Analysis
        all_anomalies.extend(
            self.pattern_detector.detect_year_end_asset_disposal(asset_disposals)
        )
        all_anomalies.extend(
            self.pattern_detector.detect_invoice_splitting(invoices)
        )
        
        # Round number analysis on transaction amounts
        amounts = [float(t.get("amount", 0)) for t in transactions if t.get("amount")]
        all_anomalies.extend(
            self.pattern_detector.detect_round_number_bias(amounts)
        )
        
        # Calculate summary statistics
        anomalies_by_category = defaultdict(int)
        anomalies_by_risk = defaultdict(int)
        
        for anomaly in all_anomalies:
            anomalies_by_category[anomaly.category.value] += 1
            anomalies_by_risk[anomaly.risk_level.value] += 1
        
        # Calculate overall risk score
        if all_anomalies:
            risk_weights = {
                RiskLevel.CRITICAL: 100,
                RiskLevel.HIGH: 75,
                RiskLevel.MEDIUM: 50,
                RiskLevel.LOW: 25,
                RiskLevel.INFO: 10,
            }
            weighted_scores = [
                risk_weights[a.risk_level] * (1 - a.false_positive_probability)
                for a in all_anomalies
            ]
            overall_risk = min(100, sum(weighted_scores) / len(weighted_scores) * 1.5)
        else:
            overall_risk = 0
        
        # Generate summary
        if overall_risk >= 70:
            summary = f"HIGH RISK: {len(all_anomalies)} behavioral anomalies detected with overall risk score of {overall_risk:.1f}. Immediate review recommended."
        elif overall_risk >= 40:
            summary = f"MODERATE RISK: {len(all_anomalies)} anomalies detected with risk score of {overall_risk:.1f}. Review within 7 days recommended."
        elif overall_risk > 0:
            summary = f"LOW RISK: {len(all_anomalies)} minor anomalies detected. Monitor and review during regular audit cycle."
        else:
            summary = "No significant behavioral anomalies detected. Continue regular monitoring."
        
        # Identify top concerns
        top_concerns = sorted(
            all_anomalies,
            key=lambda a: a.risk_score * (1 - a.false_positive_probability),
            reverse=True,
        )[:5]
        
        report = BehavioralAnalysisReport(
            entity_id=entity_id,
            analysis_date=datetime.utcnow(),
            period_start=period_start,
            period_end=period_end,
            total_transactions_analyzed=len(transactions),
            total_anomalies_detected=len(all_anomalies),
            anomalies_by_category=dict(anomalies_by_category),
            anomalies_by_risk=dict(anomalies_by_risk),
            overall_risk_score=overall_risk,
            anomalies=all_anomalies,
            summary=summary,
            top_concerns=[a.to_dict() for a in top_concerns],
        )
        
        self._analysis_history.append(report)
        return report
    
    def get_risk_summary(
        self,
        entity_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Get a quick risk summary for an entity."""
        entity_reports = [
            r for r in self._analysis_history
            if r.entity_id == entity_id
        ]
        
        if not entity_reports:
            return {
                "entity_id": str(entity_id),
                "status": "No analysis available",
                "recommendation": "Run behavioral analysis",
            }
        
        latest = entity_reports[-1]
        
        return {
            "entity_id": str(entity_id),
            "latest_analysis": latest.analysis_date.isoformat(),
            "overall_risk_score": latest.overall_risk_score,
            "total_anomalies": latest.total_anomalies_detected,
            "critical_count": latest.anomalies_by_risk.get("critical", 0),
            "high_count": latest.anomalies_by_risk.get("high", 0),
            "summary": latest.summary,
            "top_concern": latest.top_concerns[0] if latest.top_concerns else None,
        }
    
    def detect_single_anomaly_type(
        self,
        anomaly_type: AnomalyType,
        data: List[Dict[str, Any]],
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """Run a specific anomaly detection check."""
        anomalies = []
        
        if anomaly_type == AnomalyType.ODD_HOUR_EDIT:
            anomalies = self.timing_detector.detect_odd_hour_activity(
                data, kwargs.get("threshold_pct", 10.0)
            )
        elif anomaly_type == AnomalyType.WEEKEND_TRANSACTION:
            anomalies = self.timing_detector.detect_weekend_transactions(
                data, kwargs.get("threshold_pct", 5.0)
            )
        elif anomaly_type == AnomalyType.VAT_REFUND_SPIKE:
            anomalies = self.volume_detector.detect_vat_refund_spike(
                data, kwargs.get("z_score_threshold", 2.5)
            )
        elif anomaly_type == AnomalyType.INVOICE_SPLITTING:
            anomalies = self.pattern_detector.detect_invoice_splitting(
                data,
                kwargs.get("threshold_amount", 500000),
                kwargs.get("time_window_days", 7),
            )
        elif anomaly_type == AnomalyType.ROUND_NUMBER_BIAS:
            amounts = [float(d.get("amount", 0)) for d in data if d.get("amount")]
            anomalies = self.pattern_detector.detect_round_number_bias(
                amounts, kwargs.get("threshold_pct", 30.0)
            )
        
        return [a.to_dict() for a in anomalies]
