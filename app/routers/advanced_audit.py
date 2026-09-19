"""
Tekvwa Pro Audit - Advanced Audit Router

Enterprise Audit API Endpoints:
1. Tax Explainability Layer - Detailed breakdown with legal references
2. Compliance Replay Engine - Point-in-time calculation reconstruction
3. Regulatory Confidence Scoring - Quantified compliance with reasons
4. Third-Party Attestation - Digital sign-off workflows
5. Audit-Ready Export - Multi-format regulatory exports
6. Behavioral Analytics - Anomaly pattern detection

Nigerian Tax Reform 2026 Compliant

SKU Tier: ENTERPRISE (₦1,000,000+/mo)
Feature Flags: WORM_VAULT, ATTESTATION, SEGREGATION_OF_DUTIES
"""

import uuid
from datetime import date, datetime
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, Query, HTTPException, status, Body
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.database import get_db
from app.dependencies import get_current_user, get_current_entity_id, require_feature
from app.models.user import User
from app.models.sku import Feature

from app.services.audit_explainability_service import AuditExplainabilityService
from app.services.compliance_replay_service import ComplianceReplayEngine, RuleType
from app.services.regulatory_confidence_service import RegulatoryConfidenceScorer
from app.services.attestation_service import (
    ThirdPartyAttestationService,
    AttestationRole,
    AttestationType,
    AuditOpinionType,
)
from app.services.audit_export_service import (
    AuditReadyExportService,
    ExportFormat,
    ExportPurpose,
    DataCategory,
)
from app.services.behavioral_analytics_service import (
    BehavioralAnalyticsService,
    AnomalyType,
)


router = APIRouter(
    prefix="/{entity_id}/advanced-audit", 
    tags=["Advanced Audit"],
    dependencies=[Depends(require_feature([Feature.WORM_VAULT]))]
)

# Note: All endpoints in this router require Enterprise tier (WORM_VAULT feature)

# Initialize services
explainability_service = AuditExplainabilityService()
replay_engine = ComplianceReplayEngine()
confidence_scorer = RegulatoryConfidenceScorer()
attestation_service = ThirdPartyAttestationService()
export_service = AuditReadyExportService()
behavioral_service = BehavioralAnalyticsService()


# =============================================================================
# REQUEST/RESPONSE MODELS
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


class WHTExplainabilityRequest(BaseModel):
    """Request for WHT calculation explanation."""
    payment_amount: float = Field(..., gt=0, description="Payment amount")
    payment_type: str = Field(..., description="Type: dividends, interest, contracts, etc.")
    recipient_name: str = Field(..., description="Recipient name")
    recipient_tin: Optional[str] = Field(None, description="Recipient TIN")
    is_resident: bool = Field(True, description="Is recipient a Nigerian resident")


class CITExplainabilityRequest(BaseModel):
    """Request for CIT calculation explanation."""
    gross_turnover: float = Field(..., gt=0, description="Annual gross turnover")
    assessable_profit: float = Field(..., description="Assessable profit")
    capital_allowances: float = Field(0, ge=0, description="Capital allowances claimed")
    prior_year_losses: float = Field(0, ge=0, description="Prior year losses brought forward")
    period_year: int = Field(2026, ge=2020, le=2030, description="Tax year")


class ReplayRequest(BaseModel):
    """Request for compliance replay."""
    calculation_type: str = Field(..., description="Type: paye, vat")
    calculation_date: str = Field(..., description="Date to replay (YYYY-MM-DD)")
    inputs: Dict[str, Any] = Field(..., description="Calculation inputs")


class ComparisonRequest(BaseModel):
    """Request for calculation comparison."""
    calculation_type: str = Field(..., description="Type: paye, vat")
    date_1: str = Field(..., description="First date (YYYY-MM-DD)")
    date_2: str = Field(..., description="Second date (YYYY-MM-DD)")
    inputs: Dict[str, Any] = Field(..., description="Calculation inputs")


class ComplianceMetricsRequest(BaseModel):
    """Request for compliance scorecard."""
    period_start: str = Field(..., description="Period start (YYYY-MM-DD)")
    period_end: str = Field(..., description="Period end (YYYY-MM-DD)")
    vat_metrics: Dict[str, Any] = Field(..., description="VAT compliance metrics")
    paye_metrics: Dict[str, Any] = Field(..., description="PAYE compliance metrics")
    nrs_metrics: Dict[str, Any] = Field(..., description="NRS compliance metrics")
    documentation_metrics: Dict[str, Any] = Field(..., description="Documentation metrics")


class AttestorRegistrationRequest(BaseModel):
    """Request to register an attestor."""
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    role: str = Field(..., description="Role: accountant, auditor, cfo, etc.")
    title: str = Field(..., description="Job title")
    organization: str = Field(..., description="Organization name")
    credentials: Optional[List[str]] = Field(None, description="Professional credentials")


class WorkflowCreateRequest(BaseModel):
    """Request to create attestation workflow."""
    document_type: str = Field(..., description="Type: financial_statements, tax_returns, etc.")
    document_id: str = Field(..., description="Document identifier")
    document_title: str = Field(..., description="Document title")
    document_content: str = Field(..., description="Document content for hashing")
    period_start: str = Field(..., description="Period start")
    period_end: str = Field(..., description="Period end")
    template_name: Optional[str] = Field(None, description="Workflow template to use")


class AuditorAccessRequest(BaseModel):
    """Request to grant auditor access."""
    auditor_id: str = Field(..., description="Attestor ID of the auditor")
    scope: List[str] = Field(..., description="Data categories to grant access")
    validity_days: int = Field(90, ge=1, le=365, description="Access validity in days")


class BehavioralAnalysisRequest(BaseModel):
    """Request for behavioral analysis."""
    period_start: str = Field(..., description="Analysis period start")
    period_end: str = Field(..., description="Analysis period end")
    transactions: List[Dict[str, Any]] = Field(default_factory=list)
    activities: List[Dict[str, Any]] = Field(default_factory=list)
    vat_records: List[Dict[str, Any]] = Field(default_factory=list)
    asset_disposals: List[Dict[str, Any]] = Field(default_factory=list)
    invoices: List[Dict[str, Any]] = Field(default_factory=list)


# =============================================================================
# EXPLAINABILITY ENDPOINTS
# =============================================================================

@router.post("/explainability/paye")
async def explain_paye_calculation(
    request: PAYEExplainabilityRequest,
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    current_user: User = Depends(get_current_user),
):
    """
    Generate detailed PAYE calculation explanation with legal references.
    
    Returns step-by-step breakdown including:
    - CRA calculation with PITA Section 33 reference
    - Pension relief with Pension Reform Act reference
    - Progressive tax bands with Sixth Schedule reference
    - Effective tax rate computation
    """
    explanation = explainability_service.explain_paye(
        entity_id=entity_id,
        gross_annual_income=request.gross_annual_income,
        basic_salary=request.basic_salary,
        pension_percentage=request.pension_percentage,
        nhf_contribution=request.nhf_contribution,
        other_reliefs=request.other_reliefs,
        period_year=request.period_year,
    )
    return {"status": "success", "explanation": explanation}


@router.post("/explainability/vat")
async def explain_vat_calculation(
    request: VATExplainabilityRequest,
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    current_user: User = Depends(get_current_user),
):
    """
    Generate detailed VAT calculation explanation with legal references.
    
    Returns step-by-step breakdown including:
    - Output VAT computation with VATA Section 4 reference
    - WREN compliance assessment for input VAT recovery
    - Net VAT payable/refundable determination
    """
    explanation = explainability_service.explain_vat(
        entity_id=entity_id,
        output_vat_base=request.output_vat_base,
        input_vat_base=request.input_vat_base,
        wren_compliant_input=request.wren_compliant_input,
        non_compliant_input=request.non_compliant_input,
        period_month=request.period_month,
        period_year=request.period_year,
        zero_rated_sales=request.zero_rated_sales,
        exempt_sales=request.exempt_sales,
    )
    return {"status": "success", "explanation": explanation}


@router.post("/explainability/wht")
async def explain_wht_calculation(
    request: WHTExplainabilityRequest,
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    current_user: User = Depends(get_current_user),
):
    """
    Generate detailed WHT calculation explanation with legal references.
    """
    explanation = explainability_service.explain_wht(
        entity_id=entity_id,
        payment_amount=request.payment_amount,
        payment_type=request.payment_type,
        recipient_name=request.recipient_name,
        recipient_tin=request.recipient_tin,
        is_resident=request.is_resident,
    )
    return {"status": "success", "explanation": explanation}


@router.post("/explainability/cit")
async def explain_cit_calculation(
    request: CITExplainabilityRequest,
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    current_user: User = Depends(get_current_user),
):
    """
    Generate detailed CIT calculation explanation with legal references.
    """
    explanation = explainability_service.explain_cit(
        entity_id=entity_id,
        gross_turnover=request.gross_turnover,
        assessable_profit=request.assessable_profit,
        capital_allowances=request.capital_allowances,
        prior_year_losses=request.prior_year_losses,
        period_year=request.period_year,
    )
    return {"status": "success", "explanation": explanation}


@router.get("/explainability/legal-references/{tax_type}")
async def get_legal_references(
    tax_type: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get all legal references for a specific tax type.
    
    Useful for compliance documentation and audit evidence.
    """
    refs = explainability_service.get_legal_references(tax_type)
    return {"status": "success", "tax_type": tax_type, "legal_references": refs}


# =============================================================================
# COMPLIANCE REPLAY ENDPOINTS
# =============================================================================

@router.post("/replay/calculate")
async def replay_calculation(
    request: ReplayRequest,
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    current_user: User = Depends(get_current_user),
):
    """
    Replay a tax calculation as of a specific historical date.
    
    Uses tax rules and rates that were effective on that date.
    Useful for audit defense and demonstrating point-in-time compliance.
    """
    calc_date = date.fromisoformat(request.calculation_date)
    
    if request.calculation_type.lower() == "paye":
        result = replay_engine.replay_paye_calculation(
            entity_id=entity_id,
            gross_annual_income=request.inputs.get("gross_annual_income", 0),
            calculation_date=calc_date,
            pension_percentage=request.inputs.get("pension_percentage", 8.0),
        )
    elif request.calculation_type.lower() == "vat":
        result = replay_engine.replay_vat_calculation(
            entity_id=entity_id,
            sales_amount=request.inputs.get("sales_amount", 0),
            purchases_amount=request.inputs.get("purchases_amount", 0),
            calculation_date=calc_date,
            wren_compliant_pct=request.inputs.get("wren_compliant_pct", 100.0),
        )
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported calculation type: {request.calculation_type}"
        )
    
    return {"status": "success", "replay_result": result}


@router.post("/replay/compare")
async def compare_calculations(
    request: ComparisonRequest,
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    current_user: User = Depends(get_current_user),
):
    """
    Compare how a calculation differs between two dates.
    
    Demonstrates the impact of rule changes (e.g., 2025 vs 2026 PAYE bands).
    """
    date_1 = date.fromisoformat(request.date_1)
    date_2 = date.fromisoformat(request.date_2)
    
    result = replay_engine.compare_calculations(
        entity_id=entity_id,
        calculation_type=request.calculation_type,
        date_1=date_1,
        date_2=date_2,
        inputs=request.inputs,
    )
    
    return {"status": "success", "comparison": result}


@router.get("/replay/rule-history/{rule_type}")
async def get_rule_history(
    rule_type: str,
    rule_key: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """
    Get the historical evolution of a tax rule.
    
    Shows all versions of a rule with effective dates and legal references.
    """
    try:
        rt = RuleType(rule_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid rule type. Valid types: {[r.value for r in RuleType]}"
        )
    
    history = replay_engine.get_rule_history(rt, rule_key)
    return {"status": "success", "rule_type": rule_type, "history": history}


@router.get("/replay/paye-bands")
async def get_paye_bands_for_date(
    as_of_date: str = Query(..., description="Date in YYYY-MM-DD format"),
    current_user: User = Depends(get_current_user),
):
    """
    Get PAYE tax bands effective on a specific date.
    """
    query_date = date.fromisoformat(as_of_date)
    bands = replay_engine.get_paye_bands(query_date)
    return {
        "status": "success",
        "as_of_date": as_of_date,
        "paye_bands": bands,
    }


@router.get("/replay/snapshot/{snapshot_id}")
async def get_calculation_snapshot(
    snapshot_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve a stored calculation snapshot.
    """
    snapshot = replay_engine.get_snapshot(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return {"status": "success", "snapshot": snapshot}


@router.get("/replay/snapshot/{snapshot_id}/verify")
async def verify_snapshot_integrity(
    snapshot_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Verify the integrity of a calculation snapshot.
    """
    result = replay_engine.verify_snapshot(snapshot_id)
    return {"status": "success", "verification": result}


# =============================================================================
# CONFIDENCE SCORING ENDPOINTS
# =============================================================================

@router.post("/confidence/scorecard")
async def generate_compliance_scorecard(
    request: ComplianceMetricsRequest,
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a comprehensive compliance scorecard.
    
    Provides quantified compliance scores across all categories with
    specific issues identified and remediation recommendations.
    """
    scorer = RegulatoryConfidenceScorer(db)
    
    scorecard = await scorer.generate_full_scorecard(
        entity_id=entity_id,
        period_start=date.fromisoformat(request.period_start),
        period_end=date.fromisoformat(request.period_end),
        vat_metrics=request.vat_metrics,
        paye_metrics=request.paye_metrics,
        nrs_metrics=request.nrs_metrics,
        documentation_metrics=request.documentation_metrics,
    )
    
    return {"status": "success", "scorecard": scorecard}


@router.get("/confidence/summary")
async def get_compliance_summary(
    period_start: str = Query(..., description="Period start YYYY-MM-DD"),
    period_end: str = Query(..., description="Period end YYYY-MM-DD"),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a quick compliance summary with overall score.
    """
    # Generate with sample/minimal metrics for quick view
    scorer = RegulatoryConfidenceScorer(db)
    
    return {
        "status": "success",
        "entity_id": str(entity_id),
        "period": {"start": period_start, "end": period_end},
        "message": "Use POST /confidence/scorecard for full assessment with metrics",
    }


# =============================================================================
# ATTESTATION ENDPOINTS
# =============================================================================

@router.post("/attestation/register-attestor")
async def register_attestor(
    request: AttestorRegistrationRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Register a new attestor (accountant, auditor, CFO, etc.).
    """
    try:
        role = AttestationRole(request.role.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Valid roles: {[r.value for r in AttestationRole]}"
        )
    
    attestor = attestation_service.register_attestor(
        name=request.name,
        email=request.email,
        role=role,
        title=request.title,
        organization=request.organization,
        professional_credentials=request.credentials,
    )
    
    return {"status": "success", "attestor": attestor.to_dict()}


@router.post("/attestation/workflow/create")
async def create_attestation_workflow(
    request: WorkflowCreateRequest,
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new attestation workflow for a document.
    
    Supports templates: financial_statements, tax_returns, vat_returns, audit_report
    """
    # Create a default attestor for the current user
    creator = attestation_service.register_attestor(
        name=current_user.full_name or current_user.email,
        email=current_user.email,
        role=AttestationRole.PREPARER,
        title="System User",
        organization="Entity",
    )
    
    workflow = attestation_service.create_workflow(
        entity_id=entity_id,
        document_type=request.document_type,
        document_id=request.document_id,
        document_title=request.document_title,
        document_content=request.document_content,
        period_start=date.fromisoformat(request.period_start),
        period_end=date.fromisoformat(request.period_end),
        created_by=creator,
        template_name=request.template_name,
    )
    
    return {"status": "success", "workflow": workflow.to_dict()}


@router.get("/attestation/workflow/{workflow_id}/status")
async def get_workflow_status(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get the current status of an attestation workflow.
    """
    status_info = attestation_service.get_workflow_status(workflow_id)
    if "error" in status_info:
        raise HTTPException(status_code=404, detail=status_info["error"])
    return {"status": "success", "workflow_status": status_info}


@router.get("/attestation/workflow/{workflow_id}/certificate")
async def get_attestation_certificate(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Generate an attestation certificate for a completed workflow.
    """
    try:
        certificate = attestation_service.get_attestation_certificate(workflow_id)
        return {"status": "success", "certificate": certificate}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/attestation/workflows")
async def list_workflows(
    status_filter: Optional[str] = None,
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    current_user: User = Depends(get_current_user),
):
    """
    List all attestation workflows for the entity.
    """
    workflows = attestation_service.list_workflows(entity_id=entity_id)
    return {"status": "success", "workflows": workflows}


@router.post("/attestation/auditor-access/grant")
async def grant_auditor_access(
    request: AuditorAccessRequest,
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    current_user: User = Depends(get_current_user),
):
    """
    Grant read-only access to an external auditor.
    """
    # Get or create the auditor
    auditor = attestation_service._attestors.get(request.auditor_id)
    if not auditor:
        raise HTTPException(status_code=404, detail="Attestor not found")
    
    # Create grantor attestor
    grantor = attestation_service.register_attestor(
        name=current_user.full_name or current_user.email,
        email=current_user.email,
        role=AttestationRole.CFO,
        title="Authorizing Officer",
        organization="Entity",
    )
    
    try:
        grant = attestation_service.grant_auditor_access(
            entity_id=entity_id,
            auditor=auditor,
            granted_by=grantor,
            scope=request.scope,
            validity_days=request.validity_days,
        )
        return {"status": "success", "access_grant": grant.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/attestation/auditor-access")
async def list_auditor_access_grants(
    active_only: bool = True,
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    current_user: User = Depends(get_current_user),
):
    """
    List all auditor access grants for the entity.
    """
    grants = attestation_service.list_access_grants(
        entity_id=entity_id,
        active_only=active_only,
    )
    return {"status": "success", "access_grants": grants}


# =============================================================================
# EXPORT ENDPOINTS
# =============================================================================

@router.post("/export/nrs-audit")
async def export_nrs_audit_package(
    period_start: str = Query(...),
    period_end: str = Query(...),
    invoices: List[Dict[str, Any]] = Body(default=[]),
    transactions: List[Dict[str, Any]] = Body(default=[]),
    vat_returns: List[Dict[str, Any]] = Body(default=[]),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    current_user: User = Depends(get_current_user),
):
    """
    Generate NRS audit-ready export package.
    
    Includes all invoices with IRN validation status.
    """
    package = export_service.generate_nrs_audit_package(
        entity_id=entity_id,
        entity_name=current_user.full_name or "Entity",
        entity_tin=str(entity_id)[:10],  # Placeholder
        period_start=date.fromisoformat(period_start),
        period_end=date.fromisoformat(period_end),
        invoices=invoices,
        transactions=transactions,
        vat_returns=vat_returns,
    )
    
    return {"status": "success", "export": package.to_dict()}


@router.post("/export/firs-desk-audit")
async def export_firs_desk_audit_package(
    period_start: str = Query(...),
    period_end: str = Query(...),
    vat_data: Dict[str, Any] = Body(default={}),
    paye_data: Dict[str, Any] = Body(default={}),
    wht_data: Dict[str, Any] = Body(default={}),
    cit_data: Dict[str, Any] = Body(default={}),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    current_user: User = Depends(get_current_user),
):
    """
    Generate FIRS desk audit package with all tax types.
    """
    package = export_service.generate_firs_desk_audit_package(
        entity_id=entity_id,
        entity_name=current_user.full_name or "Entity",
        entity_tin=str(entity_id)[:10],
        period_start=date.fromisoformat(period_start),
        period_end=date.fromisoformat(period_end),
        vat_data=vat_data,
        paye_data=paye_data,
        wht_data=wht_data,
        cit_data=cit_data,
    )
    
    return {"status": "success", "export": package.to_dict()}


@router.post("/export/legal-evidence")
async def export_court_dispute_package(
    dispute_reference: str = Query(..., description="Case/dispute reference number"),
    period_start: str = Query(...),
    period_end: str = Query(...),
    evidence_items: List[Dict[str, Any]] = Body(default=[]),
    supporting_documents: List[Dict[str, Any]] = Body(default=[]),
    calculation_explanations: List[Dict[str, Any]] = Body(default=[]),
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    current_user: User = Depends(get_current_user),
):
    """
    Generate legally admissible evidence package for tax disputes.
    """
    package = export_service.generate_court_dispute_package(
        entity_id=entity_id,
        entity_name=current_user.full_name or "Entity",
        entity_tin=str(entity_id)[:10],
        dispute_reference=dispute_reference,
        period_start=date.fromisoformat(period_start),
        period_end=date.fromisoformat(period_end),
        evidence_items=evidence_items,
        supporting_documents=supporting_documents,
        calculation_explanations=calculation_explanations,
    )
    
    return {"status": "success", "export": package.to_dict()}


@router.get("/export/history")
async def get_export_history(
    purpose: Optional[str] = None,
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    current_user: User = Depends(get_current_user),
):
    """
    Get history of all exports for the entity.
    """
    purpose_enum = None
    if purpose:
        try:
            purpose_enum = ExportPurpose(purpose)
        except ValueError:
            pass
    
    history = export_service.get_export_history(
        entity_id=entity_id,
        purpose=purpose_enum,
    )
    
    return {"status": "success", "exports": history}


@router.post("/export/verify")
async def verify_export_integrity(
    content: bytes = Body(...),
    expected_hash: str = Query(...),
    current_user: User = Depends(get_current_user),
):
    """
    Verify the integrity of an exported package.
    """
    result = export_service.verify_export(content, expected_hash)
    return {"status": "success", "verification": result}


# =============================================================================
# BEHAVIORAL ANALYTICS ENDPOINTS
# =============================================================================

@router.post("/behavioral/analyze")
async def run_behavioral_analysis(
    request: BehavioralAnalysisRequest,
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    current_user: User = Depends(get_current_user),
):
    """
    Run comprehensive behavioral analytics on entity data.
    
    Detects timing anomalies, volume spikes, and suspicious patterns.
    """
    report = await behavioral_service.run_full_analysis(
        entity_id=entity_id,
        period_start=date.fromisoformat(request.period_start),
        period_end=date.fromisoformat(request.period_end),
        transactions=request.transactions,
        activities=request.activities,
        vat_records=request.vat_records,
        asset_disposals=request.asset_disposals,
        invoices=request.invoices,
    )
    
    return {"status": "success", "analysis": report.to_dict()}


@router.get("/behavioral/risk-summary")
async def get_risk_summary(
    entity_id: uuid.UUID = Depends(get_current_entity_id),
    current_user: User = Depends(get_current_user),
):
    """
    Get quick risk summary based on latest behavioral analysis.
    """
    summary = behavioral_service.get_risk_summary(entity_id)
    return {"status": "success", "risk_summary": summary}


@router.post("/behavioral/detect/{anomaly_type}")
async def detect_specific_anomaly(
    anomaly_type: str,
    data: List[Dict[str, Any]] = Body(...),
    threshold: Optional[float] = Query(None),
    current_user: User = Depends(get_current_user),
):
    """
    Run a specific anomaly detection check.
    
    Supported types: odd_hour_edit, weekend_transaction, vat_refund_spike,
    invoice_splitting, round_number_bias
    """
    try:
        a_type = AnomalyType(anomaly_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid anomaly type. Valid types: {[a.value for a in AnomalyType]}"
        )
    
    kwargs = {}
    if threshold is not None:
        kwargs["threshold_pct"] = threshold
    
    anomalies = behavioral_service.detect_single_anomaly_type(a_type, data, **kwargs)
    
    return {
        "status": "success",
        "anomaly_type": anomaly_type,
        "detected_anomalies": anomalies,
        "count": len(anomalies),
    }


# =============================================================================
# INFO ENDPOINT
# =============================================================================

@router.get("/info")
async def get_advanced_audit_info():
    """
    Get information about all advanced audit capabilities.
    """
    return {
        "name": "Tekvwa Pro Audit Advanced Audit Engine",
        "version": "2.0.0",
        "compliance_standards": [
            "NTAA 2025",
            "Nigerian Tax Reform 2026",
            "ISA 500 (Audit Evidence)",
            "ISA 580 (Written Representations)",
            "ISO 27001",
        ],
        "modules": {
            "explainability": {
                "description": "Detailed tax calculation explanations with legal references",
                "supported_taxes": ["PAYE", "VAT", "WHT", "CIT"],
                "features": ["Step-by-step breakdown", "Legal citations", "Assumptions documentation"],
            },
            "compliance_replay": {
                "description": "Point-in-time tax calculation reconstruction",
                "features": ["Historical rule lookup", "Calculation snapshots", "Date comparison"],
                "use_cases": ["Audit defense", "Regulatory inquiries", "Rule change impact"],
            },
            "confidence_scoring": {
                "description": "Quantified compliance scores with issue identification",
                "categories": ["VAT", "PAYE", "WHT", "NRS", "Documentation", "Filing"],
                "features": ["Issue prioritization", "Remediation guidance", "Trend analysis"],
            },
            "attestation": {
                "description": "Multi-party approval workflows with cryptographic signatures",
                "features": ["Role-based workflows", "Digital signatures", "Auditor access control"],
                "templates": ["Financial Statements", "Tax Returns", "Audit Reports"],
            },
            "export": {
                "description": "Audit-ready exports in multiple regulatory formats",
                "formats": ["TaxPro Max", "Peppol UBL", "ISO JSON", "CSV"],
                "purposes": ["NRS Audit", "FIRS Desk Audit", "Court Disputes", "External Audit"],
            },
            "behavioral_analytics": {
                "description": "Anomaly detection for suspicious patterns",
                "categories": ["Timing", "Volume", "Pattern", "User Behavior"],
                "detectors": ["Odd-hour activity", "VAT refund spikes", "Invoice splitting", "Year-end disposals"],
            },
        },
    }
