"""
Tekvwa Pro Audit - Regulatory Confidence Scoring Service

This module provides quantified compliance scoring with detailed reasons,
enabling organizations to:
- Get real-time compliance health scores
- Identify specific compliance gaps
- Prioritize remediation efforts
- Track compliance trends over time

Scoring methodology is based on Nigerian tax regulations and international
best practices for tax compliance management.
"""

import uuid
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession


class ComplianceCategory(str, Enum):
    """Categories of compliance being assessed."""
    VAT = "vat"
    PAYE = "paye"
    WHT = "wht"
    CIT = "cit"
    NRS = "nrs"
    DOCUMENTATION = "documentation"
    FILING = "filing"
    PAYMENT = "payment"
    RECORD_KEEPING = "record_keeping"


class SeverityLevel(str, Enum):
    """Severity levels for compliance issues."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ComplianceStatus(str, Enum):
    """Overall compliance status."""
    COMPLIANT = "compliant"
    MINOR_ISSUES = "minor_issues"
    MODERATE_ISSUES = "moderate_issues"
    SIGNIFICANT_ISSUES = "significant_issues"
    NON_COMPLIANT = "non_compliant"


@dataclass
class ComplianceIssue:
    """A specific compliance issue identified."""
    issue_id: str
    category: ComplianceCategory
    severity: SeverityLevel
    title: str
    description: str
    impact_score: float  # 0-100 impact on overall score
    remediation: str
    legal_reference: Optional[str] = None
    deadline: Optional[date] = None
    affected_records: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "category": self.category.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "impact_score": self.impact_score,
            "remediation": self.remediation,
            "legal_reference": self.legal_reference,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "affected_records": self.affected_records,
        }


@dataclass
class CategoryScore:
    """Score for a specific compliance category."""
    category: ComplianceCategory
    score: float  # 0-100
    weight: float  # Weight in overall score
    issues: List[ComplianceIssue] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "score": self.score,
            "weight": self.weight,
            "weighted_score": self.score * self.weight,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
            "recommendations": self.recommendations,
        }


@dataclass
class ComplianceScorecard:
    """Complete compliance scorecard for an entity."""
    entity_id: uuid.UUID
    assessment_date: datetime
    period_start: date
    period_end: date
    overall_score: float
    status: ComplianceStatus
    category_scores: List[CategoryScore]
    critical_issues: List[ComplianceIssue]
    summary: str
    trend: str  # improving, stable, declining
    next_review_date: date
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": str(self.entity_id),
            "assessment_date": self.assessment_date.isoformat(),
            "period": {
                "start": self.period_start.isoformat(),
                "end": self.period_end.isoformat(),
            },
            "overall_score": self.overall_score,
            "status": self.status.value,
            "category_scores": [c.to_dict() for c in self.category_scores],
            "critical_issues": [i.to_dict() for i in self.critical_issues],
            "summary": self.summary,
            "trend": self.trend,
            "next_review_date": self.next_review_date.isoformat(),
        }


# Compliance rules and thresholds
COMPLIANCE_WEIGHTS = {
    ComplianceCategory.VAT: 0.20,
    ComplianceCategory.PAYE: 0.15,
    ComplianceCategory.WHT: 0.10,
    ComplianceCategory.CIT: 0.15,
    ComplianceCategory.NRS: 0.15,
    ComplianceCategory.DOCUMENTATION: 0.10,
    ComplianceCategory.FILING: 0.10,
    ComplianceCategory.PAYMENT: 0.05,
}

SCORE_THRESHOLDS = {
    ComplianceStatus.COMPLIANT: 95,
    ComplianceStatus.MINOR_ISSUES: 85,
    ComplianceStatus.MODERATE_ISSUES: 70,
    ComplianceStatus.SIGNIFICANT_ISSUES: 50,
    ComplianceStatus.NON_COMPLIANT: 0,
}


class RegulatoryConfidenceScorer:
    """
    Calculates regulatory confidence scores with detailed explanations.
    
    Provides:
    - Overall compliance score (0-100)
    - Category-specific scores
    - Issue identification with severity
    - Remediation recommendations
    - Trend analysis
    """
    
    def __init__(self, db: AsyncSession = None):
        self.db = db
        self._historical_scores: Dict[str, List[Tuple[date, float]]] = {}
    
    async def assess_vat_compliance(
        self,
        entity_id: uuid.UUID,
        period_start: date,
        period_end: date,
        total_invoices: int,
        invoices_with_vat: int,
        irn_compliant_invoices: int,
        filed_returns: int,
        expected_returns: int,
        on_time_filings: int,
        vat_payments_made: float,
        vat_liability: float,
    ) -> CategoryScore:
        """
        Assess VAT compliance for a period.
        """
        issues = []
        score = 100.0
        
        # Check VAT registration compliance
        if total_invoices > 0:
            vat_coverage = (invoices_with_vat / total_invoices) * 100
            if vat_coverage < 100:
                deduction = min(25, (100 - vat_coverage) * 0.5)
                score -= deduction
                issues.append(ComplianceIssue(
                    issue_id=f"VAT-001-{uuid.uuid4().hex[:8]}",
                    category=ComplianceCategory.VAT,
                    severity=SeverityLevel.HIGH if vat_coverage < 80 else SeverityLevel.MEDIUM,
                    title="Incomplete VAT Application",
                    description=f"{100 - vat_coverage:.1f}% of invoices missing VAT charges",
                    impact_score=deduction,
                    remediation="Review invoices to ensure VAT is correctly applied to all taxable supplies",
                    legal_reference="VATA Section 4",
                    affected_records=total_invoices - invoices_with_vat,
                ))
        
        # Check NRS/IRN compliance
        if total_invoices > 0:
            irn_rate = (irn_compliant_invoices / total_invoices) * 100
            if irn_rate < 100:
                deduction = min(20, (100 - irn_rate) * 0.4)
                score -= deduction
                issues.append(ComplianceIssue(
                    issue_id=f"VAT-002-{uuid.uuid4().hex[:8]}",
                    category=ComplianceCategory.VAT,
                    severity=SeverityLevel.CRITICAL if irn_rate < 70 else SeverityLevel.HIGH,
                    title="Missing Invoice Reference Numbers (IRN)",
                    description=f"{total_invoices - irn_compliant_invoices} invoices without valid IRN from NRS",
                    impact_score=deduction,
                    remediation="Obtain IRN for all invoices through Nigeria Revenue Service portal",
                    legal_reference="NRS Regulations 2024, Schedule 1",
                    affected_records=total_invoices - irn_compliant_invoices,
                ))
        
        # Check filing compliance
        if expected_returns > 0:
            filing_rate = (filed_returns / expected_returns) * 100
            if filing_rate < 100:
                deduction = min(20, (100 - filing_rate) * 0.5)
                score -= deduction
                severity = SeverityLevel.CRITICAL if filing_rate < 50 else SeverityLevel.HIGH
                issues.append(ComplianceIssue(
                    issue_id=f"VAT-003-{uuid.uuid4().hex[:8]}",
                    category=ComplianceCategory.VAT,
                    severity=severity,
                    title="Missing VAT Returns",
                    description=f"{expected_returns - filed_returns} VAT returns not filed for the period",
                    impact_score=deduction,
                    remediation="File outstanding VAT returns immediately via FIRS TaxPro Max portal",
                    legal_reference="VATA Section 15",
                    deadline=date.today() + timedelta(days=14),
                    affected_records=expected_returns - filed_returns,
                ))
        
        # Check timely filing
        if filed_returns > 0:
            on_time_rate = (on_time_filings / filed_returns) * 100
            if on_time_rate < 100:
                deduction = min(10, (100 - on_time_rate) * 0.2)
                score -= deduction
                issues.append(ComplianceIssue(
                    issue_id=f"VAT-004-{uuid.uuid4().hex[:8]}",
                    category=ComplianceCategory.VAT,
                    severity=SeverityLevel.MEDIUM,
                    title="Late VAT Return Filings",
                    description=f"{filed_returns - on_time_filings} returns filed after deadline",
                    impact_score=deduction,
                    remediation="Establish calendar reminders for VAT filing deadlines (21st of following month)",
                    legal_reference="VATA Section 15(1)",
                    affected_records=filed_returns - on_time_filings,
                ))
        
        # Check payment compliance
        if vat_liability > 0:
            payment_rate = (vat_payments_made / vat_liability) * 100
            if payment_rate < 100:
                deduction = min(15, (100 - payment_rate) * 0.3)
                score -= deduction
                issues.append(ComplianceIssue(
                    issue_id=f"VAT-005-{uuid.uuid4().hex[:8]}",
                    category=ComplianceCategory.VAT,
                    severity=SeverityLevel.CRITICAL if payment_rate < 80 else SeverityLevel.HIGH,
                    title="Outstanding VAT Liability",
                    description=f"NGN {vat_liability - vat_payments_made:,.2f} VAT payment outstanding",
                    impact_score=deduction,
                    remediation="Settle outstanding VAT liability to avoid penalties and interest",
                    legal_reference="VATA Section 16",
                    deadline=date.today() + timedelta(days=7),
                ))
        
        recommendations = []
        if score < 90:
            recommendations.append("Implement automated VAT tracking on all sales transactions")
        if irn_compliant_invoices < total_invoices:
            recommendations.append("Integrate with NRS API for automatic IRN generation")
        if on_time_filings < filed_returns:
            recommendations.append("Set up automated reminders 5 days before filing deadlines")
        
        return CategoryScore(
            category=ComplianceCategory.VAT,
            score=max(0, score),
            weight=COMPLIANCE_WEIGHTS[ComplianceCategory.VAT],
            issues=issues,
            recommendations=recommendations,
        )
    
    async def assess_paye_compliance(
        self,
        entity_id: uuid.UUID,
        period_start: date,
        period_end: date,
        employees_count: int,
        employees_with_tin: int,
        paye_deducted: float,
        paye_remitted: float,
        returns_filed: int,
        expected_returns: int,
        on_time_remittances: int,
        total_remittances: int,
    ) -> CategoryScore:
        """Assess PAYE compliance for a period."""
        issues = []
        score = 100.0
        
        # Check TIN registration
        if employees_count > 0:
            tin_rate = (employees_with_tin / employees_count) * 100
            if tin_rate < 100:
                deduction = min(15, (100 - tin_rate) * 0.3)
                score -= deduction
                issues.append(ComplianceIssue(
                    issue_id=f"PAYE-001-{uuid.uuid4().hex[:8]}",
                    category=ComplianceCategory.PAYE,
                    severity=SeverityLevel.HIGH if tin_rate < 80 else SeverityLevel.MEDIUM,
                    title="Employees Without TIN",
                    description=f"{employees_count - employees_with_tin} employees lack Tax Identification Numbers",
                    impact_score=deduction,
                    remediation="Assist employees in obtaining TIN from FIRS",
                    legal_reference="PITA Section 40",
                    affected_records=employees_count - employees_with_tin,
                ))
        
        # Check remittance compliance
        if paye_deducted > 0:
            remittance_rate = (paye_remitted / paye_deducted) * 100
            if remittance_rate < 100:
                deduction = min(25, (100 - remittance_rate) * 0.5)
                score -= deduction
                issues.append(ComplianceIssue(
                    issue_id=f"PAYE-002-{uuid.uuid4().hex[:8]}",
                    category=ComplianceCategory.PAYE,
                    severity=SeverityLevel.CRITICAL,
                    title="PAYE Under-Remittance",
                    description=f"NGN {paye_deducted - paye_remitted:,.2f} PAYE deducted but not remitted",
                    impact_score=deduction,
                    remediation="Remit all deducted PAYE to FIRS immediately",
                    legal_reference="PITA Section 81",
                    deadline=date.today() + timedelta(days=7),
                ))
        
        # Check filing compliance
        if expected_returns > 0:
            filing_rate = (returns_filed / expected_returns) * 100
            if filing_rate < 100:
                deduction = min(15, (100 - filing_rate) * 0.3)
                score -= deduction
                issues.append(ComplianceIssue(
                    issue_id=f"PAYE-003-{uuid.uuid4().hex[:8]}",
                    category=ComplianceCategory.PAYE,
                    severity=SeverityLevel.HIGH,
                    title="Missing PAYE Returns",
                    description=f"{expected_returns - returns_filed} monthly PAYE returns not filed",
                    impact_score=deduction,
                    remediation="File outstanding PAYE returns with relevant State IRS",
                    legal_reference="PITA Section 81(2)",
                    affected_records=expected_returns - returns_filed,
                ))
        
        # Check timely remittance
        if total_remittances > 0:
            on_time_rate = (on_time_remittances / total_remittances) * 100
            if on_time_rate < 100:
                deduction = min(10, (100 - on_time_rate) * 0.2)
                score -= deduction
                issues.append(ComplianceIssue(
                    issue_id=f"PAYE-004-{uuid.uuid4().hex[:8]}",
                    category=ComplianceCategory.PAYE,
                    severity=SeverityLevel.MEDIUM,
                    title="Late PAYE Remittances",
                    description=f"{total_remittances - on_time_remittances} remittances made after deadline",
                    impact_score=deduction,
                    remediation="Remit PAYE by 10th of following month to avoid penalties",
                    legal_reference="PITA Section 81(3)",
                ))
        
        recommendations = []
        if score < 90:
            recommendations.append("Automate PAYE calculation and remittance scheduling")
        if employees_with_tin < employees_count:
            recommendations.append("Conduct TIN registration drive for all employees")
        
        return CategoryScore(
            category=ComplianceCategory.PAYE,
            score=max(0, score),
            weight=COMPLIANCE_WEIGHTS[ComplianceCategory.PAYE],
            issues=issues,
            recommendations=recommendations,
        )
    
    async def assess_nrs_compliance(
        self,
        entity_id: uuid.UUID,
        period_start: date,
        period_end: date,
        total_invoices: int,
        irn_generated: int,
        irn_validated: int,
        sync_errors: int,
        last_sync_date: Optional[date],
    ) -> CategoryScore:
        """Assess NRS (Nigeria Revenue Service) compliance."""
        issues = []
        score = 100.0
        
        # Check IRN generation rate
        if total_invoices > 0:
            irn_rate = (irn_generated / total_invoices) * 100
            if irn_rate < 100:
                deduction = min(30, (100 - irn_rate) * 0.6)
                score -= deduction
                issues.append(ComplianceIssue(
                    issue_id=f"NRS-001-{uuid.uuid4().hex[:8]}",
                    category=ComplianceCategory.NRS,
                    severity=SeverityLevel.CRITICAL if irn_rate < 70 else SeverityLevel.HIGH,
                    title="Invoices Without IRN",
                    description=f"{total_invoices - irn_generated} invoices lack Invoice Reference Numbers",
                    impact_score=deduction,
                    remediation="Generate IRN for all invoices through NRS integration",
                    legal_reference="VATA (Amendment) 2024",
                    affected_records=total_invoices - irn_generated,
                ))
        
        # Check IRN validation rate
        if irn_generated > 0:
            validation_rate = (irn_validated / irn_generated) * 100
            if validation_rate < 100:
                deduction = min(20, (100 - validation_rate) * 0.4)
                score -= deduction
                issues.append(ComplianceIssue(
                    issue_id=f"NRS-002-{uuid.uuid4().hex[:8]}",
                    category=ComplianceCategory.NRS,
                    severity=SeverityLevel.HIGH,
                    title="IRN Validation Failures",
                    description=f"{irn_generated - irn_validated} IRNs failed NRS validation",
                    impact_score=deduction,
                    remediation="Review and correct invalid IRNs; regenerate if necessary",
                    legal_reference="NRS Technical Guidelines",
                    affected_records=irn_generated - irn_validated,
                ))
        
        # Check sync status
        if sync_errors > 0:
            deduction = min(15, sync_errors * 2)
            score -= deduction
            issues.append(ComplianceIssue(
                issue_id=f"NRS-003-{uuid.uuid4().hex[:8]}",
                category=ComplianceCategory.NRS,
                severity=SeverityLevel.MEDIUM,
                title="NRS Synchronization Errors",
                description=f"{sync_errors} synchronization errors with NRS platform",
                impact_score=deduction,
                remediation="Investigate and resolve NRS API connectivity issues",
                legal_reference="NRS Integration Requirements",
            ))
        
        # Check last sync date
        if last_sync_date:
            days_since_sync = (date.today() - last_sync_date).days
            if days_since_sync > 1:
                deduction = min(10, days_since_sync * 2)
                score -= deduction
                issues.append(ComplianceIssue(
                    issue_id=f"NRS-004-{uuid.uuid4().hex[:8]}",
                    category=ComplianceCategory.NRS,
                    severity=SeverityLevel.MEDIUM if days_since_sync < 7 else SeverityLevel.HIGH,
                    title="Stale NRS Synchronization",
                    description=f"Last NRS sync was {days_since_sync} days ago",
                    impact_score=deduction,
                    remediation="Configure automated daily NRS synchronization",
                    legal_reference="NRS Operational Guidelines",
                ))
        else:
            score -= 20
            issues.append(ComplianceIssue(
                issue_id=f"NRS-005-{uuid.uuid4().hex[:8]}",
                category=ComplianceCategory.NRS,
                severity=SeverityLevel.CRITICAL,
                title="No NRS Synchronization",
                description="NRS integration has never been synchronized",
                impact_score=20,
                remediation="Establish NRS integration and perform initial synchronization",
                legal_reference="NRS Mandatory Requirements",
            ))
        
        recommendations = []
        if irn_generated < total_invoices:
            recommendations.append("Enable automatic IRN generation for all new invoices")
        if sync_errors > 0:
            recommendations.append("Implement error monitoring and alerting for NRS sync")
        
        return CategoryScore(
            category=ComplianceCategory.NRS,
            score=max(0, score),
            weight=COMPLIANCE_WEIGHTS[ComplianceCategory.NRS],
            issues=issues,
            recommendations=recommendations,
        )
    
    async def assess_documentation_compliance(
        self,
        entity_id: uuid.UUID,
        total_transactions: int,
        transactions_with_docs: int,
        invoices_with_required_fields: int,
        total_invoices: int,
        contracts_on_file: int,
        total_contracts: int,
    ) -> CategoryScore:
        """Assess documentation compliance."""
        issues = []
        score = 100.0
        
        # Check transaction documentation
        if total_transactions > 0:
            doc_rate = (transactions_with_docs / total_transactions) * 100
            if doc_rate < 100:
                deduction = min(20, (100 - doc_rate) * 0.4)
                score -= deduction
                issues.append(ComplianceIssue(
                    issue_id=f"DOC-001-{uuid.uuid4().hex[:8]}",
                    category=ComplianceCategory.DOCUMENTATION,
                    severity=SeverityLevel.HIGH if doc_rate < 80 else SeverityLevel.MEDIUM,
                    title="Undocumented Transactions",
                    description=f"{total_transactions - transactions_with_docs} transactions lack supporting documents",
                    impact_score=deduction,
                    remediation="Attach supporting documents to all transactions",
                    legal_reference="CITA Section 55",
                    affected_records=total_transactions - transactions_with_docs,
                ))
        
        # Check invoice completeness
        if total_invoices > 0:
            complete_rate = (invoices_with_required_fields / total_invoices) * 100
            if complete_rate < 100:
                deduction = min(15, (100 - complete_rate) * 0.3)
                score -= deduction
                issues.append(ComplianceIssue(
                    issue_id=f"DOC-002-{uuid.uuid4().hex[:8]}",
                    category=ComplianceCategory.DOCUMENTATION,
                    severity=SeverityLevel.MEDIUM,
                    title="Incomplete Invoice Information",
                    description=f"{total_invoices - invoices_with_required_fields} invoices missing required fields",
                    impact_score=deduction,
                    remediation="Ensure all invoices include TIN, address, IRN, and VAT breakdown",
                    legal_reference="VATA Section 24",
                    affected_records=total_invoices - invoices_with_required_fields,
                ))
        
        # Check contract documentation
        if total_contracts > 0:
            contract_rate = (contracts_on_file / total_contracts) * 100
            if contract_rate < 100:
                deduction = min(15, (100 - contract_rate) * 0.3)
                score -= deduction
                issues.append(ComplianceIssue(
                    issue_id=f"DOC-003-{uuid.uuid4().hex[:8]}",
                    category=ComplianceCategory.DOCUMENTATION,
                    severity=SeverityLevel.MEDIUM,
                    title="Missing Contract Documentation",
                    description=f"{total_contracts - contracts_on_file} vendor/customer contracts not on file",
                    impact_score=deduction,
                    remediation="Obtain and file all vendor and customer contracts",
                    legal_reference="General Audit Best Practice",
                    affected_records=total_contracts - contracts_on_file,
                ))
        
        recommendations = []
        if score < 90:
            recommendations.append("Implement mandatory document attachment workflow")
            recommendations.append("Use invoice validation rules to enforce completeness")
        
        return CategoryScore(
            category=ComplianceCategory.DOCUMENTATION,
            score=max(0, score),
            weight=COMPLIANCE_WEIGHTS[ComplianceCategory.DOCUMENTATION],
            issues=issues,
            recommendations=recommendations,
        )
    
    async def calculate_overall_score(
        self,
        entity_id: uuid.UUID,
        period_start: date,
        period_end: date,
        category_scores: List[CategoryScore],
    ) -> ComplianceScorecard:
        """
        Calculate overall compliance score from category scores.
        """
        # Calculate weighted overall score
        total_weight = sum(cs.weight for cs in category_scores)
        if total_weight > 0:
            overall_score = sum(cs.score * cs.weight for cs in category_scores) / total_weight
        else:
            overall_score = 0.0
        
        # Determine status
        if overall_score >= SCORE_THRESHOLDS[ComplianceStatus.COMPLIANT]:
            status = ComplianceStatus.COMPLIANT
        elif overall_score >= SCORE_THRESHOLDS[ComplianceStatus.MINOR_ISSUES]:
            status = ComplianceStatus.MINOR_ISSUES
        elif overall_score >= SCORE_THRESHOLDS[ComplianceStatus.MODERATE_ISSUES]:
            status = ComplianceStatus.MODERATE_ISSUES
        elif overall_score >= SCORE_THRESHOLDS[ComplianceStatus.SIGNIFICANT_ISSUES]:
            status = ComplianceStatus.SIGNIFICANT_ISSUES
        else:
            status = ComplianceStatus.NON_COMPLIANT
        
        # Collect critical issues
        critical_issues = []
        for cs in category_scores:
            for issue in cs.issues:
                if issue.severity == SeverityLevel.CRITICAL:
                    critical_issues.append(issue)
        
        # Determine trend
        entity_key = str(entity_id)
        historical = self._historical_scores.get(entity_key, [])
        if len(historical) >= 2:
            recent_scores = [s[1] for s in historical[-3:]]
            avg_recent = sum(recent_scores) / len(recent_scores)
            if overall_score > avg_recent + 2:
                trend = "improving"
            elif overall_score < avg_recent - 2:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"
        
        # Store current score for trend analysis
        if entity_key not in self._historical_scores:
            self._historical_scores[entity_key] = []
        self._historical_scores[entity_key].append((date.today(), overall_score))
        
        # Generate summary
        issue_count = sum(len(cs.issues) for cs in category_scores)
        critical_count = len(critical_issues)
        
        if status == ComplianceStatus.COMPLIANT:
            summary = f"Excellent compliance with score of {overall_score:.1f}%. No significant issues identified."
        elif status == ComplianceStatus.MINOR_ISSUES:
            summary = f"Good compliance with score of {overall_score:.1f}%. {issue_count} minor issues require attention."
        elif status == ComplianceStatus.MODERATE_ISSUES:
            summary = f"Moderate compliance concerns with score of {overall_score:.1f}%. {issue_count} issues identified, {critical_count} critical."
        else:
            summary = f"Significant compliance gaps with score of {overall_score:.1f}%. Immediate action required on {critical_count} critical issues."
        
        return ComplianceScorecard(
            entity_id=entity_id,
            assessment_date=datetime.utcnow(),
            period_start=period_start,
            period_end=period_end,
            overall_score=overall_score,
            status=status,
            category_scores=category_scores,
            critical_issues=critical_issues,
            summary=summary,
            trend=trend,
            next_review_date=date.today() + timedelta(days=30),
        )
    
    async def generate_full_scorecard(
        self,
        entity_id: uuid.UUID,
        period_start: date,
        period_end: date,
        vat_metrics: Dict[str, Any],
        paye_metrics: Dict[str, Any],
        nrs_metrics: Dict[str, Any],
        documentation_metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Generate a complete compliance scorecard.
        
        This is the main entry point for compliance assessment.
        """
        category_scores = []
        
        # Assess each category
        vat_score = await self.assess_vat_compliance(
            entity_id=entity_id,
            period_start=period_start,
            period_end=period_end,
            **vat_metrics,
        )
        category_scores.append(vat_score)
        
        paye_score = await self.assess_paye_compliance(
            entity_id=entity_id,
            period_start=period_start,
            period_end=period_end,
            **paye_metrics,
        )
        category_scores.append(paye_score)
        
        nrs_score = await self.assess_nrs_compliance(
            entity_id=entity_id,
            period_start=period_start,
            period_end=period_end,
            **nrs_metrics,
        )
        category_scores.append(nrs_score)
        
        doc_score = await self.assess_documentation_compliance(
            entity_id=entity_id,
            **documentation_metrics,
        )
        category_scores.append(doc_score)
        
        # Calculate overall scorecard
        scorecard = await self.calculate_overall_score(
            entity_id=entity_id,
            period_start=period_start,
            period_end=period_end,
            category_scores=category_scores,
        )
        
        return scorecard.to_dict()
    
    def get_compliance_summary(
        self,
        scorecard: Dict[str, Any],
    ) -> str:
        """Generate executive summary of compliance status."""
        score = scorecard["overall_score"]
        status = scorecard["status"]
        critical_count = len(scorecard["critical_issues"])
        
        lines = [
            f"Regulatory Confidence Score: {score:.1f}%",
            f"Status: {status.replace('_', ' ').title()}",
            "",
        ]
        
        if critical_count > 0:
            lines.append(f"CRITICAL ISSUES ({critical_count}):")
            for issue in scorecard["critical_issues"][:5]:
                lines.append(f"  - {issue['title']}: {issue['description']}")
            lines.append("")
        
        lines.append("CATEGORY BREAKDOWN:")
        for cat in scorecard["category_scores"]:
            lines.append(f"  {cat['category'].upper()}: {cat['score']:.1f}% ({cat['issue_count']} issues)")
        
        return "\n".join(lines)
