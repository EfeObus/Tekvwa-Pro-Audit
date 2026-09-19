"""
Tekvwa Pro Audit - Audit Schemas

Pydantic schemas for audit-related request/response validation.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, Field


# =============================================================================
# ENUMS
# =============================================================================

class AuditRiskLevel(str, Enum):
    """Audit risk levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConformityLevel(str, Enum):
    """Benford's Law conformity levels."""
    CLOSE_CONFORMITY = "close_conformity"
    ACCEPTABLE_CONFORMITY = "acceptable_conformity"
    MARGINALLY_ACCEPTABLE = "marginally_acceptable"
    NONCONFORMING = "nonconforming"


class AnomalySeverity(str, Enum):
    """Anomaly severity levels."""
    WARNING = "warning"
    CRITICAL = "critical"
    EXTREME = "extreme"


class IntegrityStatus(str, Enum):
    """Data integrity status."""
    VERIFIED = "DATA_INTEGRITY_VERIFIED"
    BREACH_DETECTED = "INTEGRITY_BREACH_DETECTED"


# =============================================================================
# BASE SCHEMAS
# =============================================================================

class AuditBaseSchema(BaseModel):
    """Base schema for audit responses."""
    entity_id: Optional[str] = None
    analyzed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# =============================================================================
# BENFORD'S LAW SCHEMAS
# =============================================================================

class BenfordsDigitDistribution(BaseModel):
    """Digit distribution data for Benford's analysis."""
    count: int
    actual_pct: float
    expected_pct: float


class BenfordsAnomaly(BaseModel):
    """Anomaly detected in Benford's analysis."""
    digit: int
    expected_pct: float
    actual_pct: float
    deviation: float
    z_score: float
    severity: str


class BenfordsAnalysisRequest(BaseModel):
    """Request model for Benford's Law analysis."""
    amounts: List[float] = Field(..., min_length=100, description="List of amounts to analyze (min 100)")
    analysis_type: str = Field("first_digit", description="'first_digit' or 'second_digit'")


class BenfordsAnalysisResponse(AuditBaseSchema):
    """Response model for Benford's Law analysis."""
    valid: bool
    analysis_type: Optional[str] = None
    sample_size: int
    chi_square: Optional[float] = None
    chi_square_critical_95: Optional[float] = None
    chi_square_pass: Optional[bool] = None
    mean_absolute_deviation: Optional[float] = None
    conformity_level: Optional[str] = None
    conformity_status: Optional[str] = None
    risk_level: Optional[str] = None
    digit_distribution: Optional[Dict[str, BenfordsDigitDistribution]] = None
    anomalies: Optional[List[BenfordsAnomaly]] = None
    interpretation: Optional[str] = None
    error: Optional[str] = None


# =============================================================================
# Z-SCORE ANOMALY DETECTION SCHEMAS
# =============================================================================

class ZScoreStatistics(BaseModel):
    """Statistics summary for Z-score analysis."""
    mean: float
    std_dev: float
    min: float
    max: float
    median: float


class ZScoreAnomaly(BaseModel):
    """Detected anomaly from Z-score analysis."""
    transaction_id: str
    amount: float
    z_score: float
    severity: str
    deviation_from_mean: float
    deviation_pct: Optional[float] = None
    direction: str
    transaction_date: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    vendor: Optional[str] = None
    group: Optional[str] = None
    group_mean: Optional[float] = None


class AnomalyDetectionRequest(BaseModel):
    """Request model for anomaly detection."""
    transactions: List[Dict[str, Any]] = Field(..., description="List of transaction objects with 'amount' field")
    amount_field: str = Field("amount", description="Field name containing the amount")
    group_by: Optional[str] = Field(None, description="Optional field to group by (e.g., 'category')")
    threshold: float = Field(2.5, ge=1.5, le=5.0, description="Z-score threshold for anomalies")


class AnomalyDetectionResponse(AuditBaseSchema):
    """Response model for anomaly detection."""
    valid: bool
    sample_size: int
    statistics: Optional[ZScoreStatistics] = None
    grouped_by: Optional[str] = None
    groups_analyzed: Optional[int] = None
    group_statistics: Optional[Dict[str, Dict[str, Any]]] = None
    threshold_used: float
    anomaly_count: int
    anomalies: List[ZScoreAnomaly]
    summary: Dict[str, int]
    error: Optional[str] = None


# =============================================================================
# NRS GAP ANALYSIS SCHEMAS
# =============================================================================

class NRSGapInvoice(BaseModel):
    """Invoice data for NRS gap analysis."""
    id: str
    invoice_number: str
    invoice_date: Optional[str] = None
    customer_name: Optional[str] = None
    customer_tin: Optional[str] = None
    total_amount: str
    vat_amount: Optional[str] = None
    invoice_type: Optional[str] = None
    status: str
    irn: Optional[str] = None
    risk: Optional[str] = None
    days_overdue: Optional[int] = None
    reported: Optional[bool] = None
    reporting_required: Optional[bool] = None
    deadline: Optional[str] = None


class NRSGapSummary(BaseModel):
    """Summary of NRS gap analysis."""
    total_invoices: int
    validated: int
    pending_validation: int
    missing_irn: int
    b2c_high_value: int


class NRSGapFinancials(BaseModel):
    """Financial summary from NRS gap analysis."""
    total_value: str
    validated_value: str
    missing_irn_value: str
    value_at_risk: str


class NRSGapCompliance(BaseModel):
    """Compliance metrics from NRS gap analysis."""
    rate: float
    value_rate: float
    risk_level: str
    status: str


class NRSGapRecommendation(BaseModel):
    """Recommendation from NRS gap analysis."""
    priority: str
    category: str
    title: str
    description: str
    action: str
    deadline: Optional[str] = None


class NRSGapAnalysisResponse(AuditBaseSchema):
    """Response model for NRS gap analysis."""
    analysis_period: Dict[str, str]
    summary: NRSGapSummary
    financials: NRSGapFinancials
    compliance: NRSGapCompliance
    gaps: Dict[str, List[NRSGapInvoice]]
    recommendations: List[NRSGapRecommendation]


# =============================================================================
# DATA INTEGRITY VERIFICATION SCHEMAS
# =============================================================================

class IntegrityDiscrepancy(BaseModel):
    """Discrepancy found in integrity verification."""
    sequence_number: int
    type: str
    message: str
    expected_previous_hash: Optional[str] = None
    actual_previous_hash: Optional[str] = None


class DataIntegrityResponse(AuditBaseSchema):
    """Response model for data integrity verification."""
    verified: bool
    status: str
    badge: str
    message: str
    discrepancy_count: int
    discrepancies: Optional[List[IntegrityDiscrepancy]] = None
    verified_at: str


class LedgerIntegrityReport(AuditBaseSchema):
    """Detailed ledger integrity report."""
    sequence_range: Dict[str, Optional[int]]
    integrity_status: str
    chain_valid: bool
    discrepancy_count: int
    discrepancies: List[IntegrityDiscrepancy]
    verification_time: str
    badge: str
    legal_statement: str


# =============================================================================
# 3-WAY MATCHING SCHEMAS
# =============================================================================

class MatchingException(BaseModel):
    """3-way matching exception."""
    id: str
    purchase_order_id: Optional[str] = None
    grn_id: Optional[str] = None
    invoice_id: Optional[str] = None
    status: str
    po_amount: Optional[str] = None
    invoice_amount: Optional[str] = None
    discrepancies: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    resolved_at: Optional[str] = None


class ThreeWayMatchingSummaryResponse(AuditBaseSchema):
    """Response model for 3-way matching summary."""
    period: Dict[str, str]
    totals: Dict[str, Any]
    by_status: Dict[str, Dict[str, Any]]
    risk_assessment: Dict[str, Any]


# =============================================================================
# FULL FORENSIC AUDIT SCHEMAS
# =============================================================================

class ForensicAuditRequest(BaseModel):
    """Request model for full forensic audit."""
    fiscal_year: int = Field(..., ge=2020, le=2030, description="Fiscal year to analyze")
    categories: Optional[List[str]] = Field(None, description="Optional category filter")


class ForensicAuditResponse(AuditBaseSchema):
    """Response model for full forensic audit."""
    fiscal_year: int
    analysis_period: Dict[str, str]
    sample_size: int
    total_amount: str
    tests: Dict[str, Any]
    overall_risk: str
    overall_status: str
    risk_factors: List[str]


# =============================================================================
# WORM STORAGE SCHEMAS
# =============================================================================

class WORMStorageStatus(BaseModel):
    """WORM storage status response."""
    enabled: bool
    storage_type: str
    retention_mode: Optional[str] = None
    default_retention_years: int
    legal_protection: str
    supported_documents: List[str]
    configuration_status: str


class WORMDocumentVerification(BaseModel):
    """WORM document verification response."""
    verified: bool
    simulated: Optional[bool] = None
    message: Optional[str] = None
    document_exists: Optional[bool] = None
    content_hash: Optional[str] = None
    hash_verified: Optional[bool] = None
    object_lock_mode: Optional[str] = None
    retention_until: Optional[str] = None
    is_legally_protected: Optional[bool] = None
    legal_status: Optional[str] = None
    error: Optional[str] = None


# =============================================================================
# AUDIT LOG SCHEMAS
# =============================================================================

class AuditLogEntry(BaseModel):
    """Audit log entry."""
    id: str
    timestamp: str
    target_entity_type: str
    target_entity_id: str
    action: str
    user_id: Optional[str] = None
    changes: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None


class AuditLogsResponse(BaseModel):
    """Response for audit logs list."""
    items: List[AuditLogEntry]
    skip: int
    limit: int


class AuditSummaryResponse(BaseModel):
    """Response for audit summary."""
    entity_id: str
    fiscal_year: int
    summary: Dict[str, Any]
    quick_actions: List[Optional[str]]
    generated_at: str


# =============================================================================
# ADVANCED AUDIT SCHEMAS
# =============================================================================

class PAYEExplainabilityRequest(BaseModel):
    """Request for PAYE calculation explanation."""
    gross_annual_income: float = Field(..., gt=0, description="Annual gross income in NGN")
    basic_salary: Optional[float] = Field(None, description="Basic salary (defaults to 60% of gross)")
    pension_percentage: float = Field(8.0, ge=0, le=20, description="Pension contribution percentage")
    nhf_contribution: Optional[float] = Field(None, description="NHF contribution amount")
    other_reliefs: float = Field(0, ge=0, description="Other tax-exempt reliefs")
    period_year: int = Field(2026, ge=2020, le=2030, description="Tax year")


class VATExplainabilityRequest(BaseModel):
    """Request for VAT calculation explanation."""
    output_vat_base: float = Field(..., ge=0, description="Total taxable sales")
    input_vat_base: float = Field(..., ge=0, description="Total purchases")
    wren_compliant_input: float = Field(..., ge=0, description="WREN-compliant expenses")
    non_compliant_input: float = Field(..., ge=0, description="Non-WREN expenses")
    period_month: int = Field(..., ge=1, le=12, description="Month")
    period_year: int = Field(..., ge=2020, le=2030, description="Year")
    zero_rated_sales: float = Field(0, ge=0, description="Zero-rated sales")
    exempt_sales: float = Field(0, ge=0, description="Exempt sales")


class ComplianceReplayRequest(BaseModel):
    """Request for compliance replay."""
    calculation_type: str = Field(..., description="Type: paye, vat")
    calculation_date: str = Field(..., description="Date to replay (YYYY-MM-DD)")
    inputs: Dict[str, Any] = Field(..., description="Calculation inputs")


class ComplianceComparisonRequest(BaseModel):
    """Request for calculation comparison."""
    calculation_type: str = Field(..., description="Type: paye, vat")
    date_1: str = Field(..., description="First date (YYYY-MM-DD)")
    date_2: str = Field(..., description="Second date (YYYY-MM-DD)")
    inputs: Dict[str, Any] = Field(..., description="Calculation inputs")


class AttestorRegistrationRequest(BaseModel):
    """Request to register an attestor."""
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    role: str = Field(..., description="Role: accountant, auditor, cfo, etc.")
    title: str = Field(..., description="Job title")
    organization: str = Field(..., description="Organization name")
    credentials: Optional[List[str]] = Field(None, description="Professional credentials")


class BehavioralAnalysisRequest(BaseModel):
    """Request for behavioral analysis."""
    period_start: str = Field(..., description="Analysis period start")
    period_end: str = Field(..., description="Analysis period end")
    transactions: List[Dict[str, Any]] = Field(default_factory=list)
    activities: List[Dict[str, Any]] = Field(default_factory=list)
    vat_records: List[Dict[str, Any]] = Field(default_factory=list)
    asset_disposals: List[Dict[str, Any]] = Field(default_factory=list)
    invoices: List[Dict[str, Any]] = Field(default_factory=list)
