"""
Tekvwa Pro Audit - Consolidated Audit Service Module

This module provides a single entry point for all audit-related services.
It consolidates access to:

1. BASIC AUDIT SERVICES:
   - AuditService: Basic audit logging
   - AuditVaultService: 5-year record retention (NTAA 2025)

2. ADVANCED AUDIT SYSTEM SERVICES:
   - AuditorRoleEnforcer: Read-only enforcement for auditors
   - EvidenceImmutabilityService: Tamper-proof evidence
   - ReproducibleAuditService: Point-in-time audit reproducibility
   - AuditFindingsService: Human-readable findings management
   - AuditorSessionService: Auditor access session tracking
   - AdvancedAuditSystemService: Combined advanced audit operations

3. FORENSIC AUDIT SERVICES:
   - ForensicAuditService: Benford's Law, Z-score, NRS Gap Analysis
   - WORMStorageService: Write-Once-Read-Many immutable storage

4. ENTERPRISE AUDIT SERVICES:
   - AuditExplainabilityService: Tax calculation explanations
   - ComplianceReplayEngine: Point-in-time recalculation
   - RegulatoryConfidenceScorer: Compliance confidence scoring
   - ThirdPartyAttestationService: Digital sign-off workflows
   - BehavioralAnalyticsService: Anomaly pattern detection
   - AuditReadyExportService: Multi-format regulatory exports

NTAA 2025 & FIRS Compliance:
- 5-year digital record keeping
- Immutable audit trails
- Device fingerprint verification
- Export for regulatory audits
"""

# =========================================================
# BASIC AUDIT SERVICES
# =========================================================
from app.services.audit_service import (
    AuditService,
    AuditEntry,
)

from app.services.audit_vault_service import (
    AuditVaultService,
    RetentionStatus,
    DocumentType,
    VaultDocument,
    VaultStatistics,
    NTAA_RETENTION_YEARS,
    LEGAL_HOLD_EXTENSION_YEARS,
    ARCHIVE_AFTER_YEARS,
)

# =========================================================
# ADVANCED AUDIT SYSTEM SERVICES
# =========================================================
from app.services.audit_system_service import (
    # Exceptions
    AuditorPermissionError,
    EvidenceImmutabilityError,
    AuditRunError,
    # Role Enforcement
    AuditorRoleEnforcer,
    # Evidence Management
    EvidenceImmutabilityService,
    # Reproducible Audits
    ReproducibleAuditService,
    # Findings Management
    AuditFindingsService,
    # Session Management
    AuditorSessionService,
    # Combined Service
    AdvancedAuditSystemService,
)

# =========================================================
# FORENSIC AUDIT SERVICES
# =========================================================
from app.services.forensic_audit_service import (
    ForensicAuditService,
    WORMStorageService,
)

# =========================================================
# ENTERPRISE AUDIT SERVICES
# =========================================================
from app.services.audit_explainability_service import (
    AuditExplainabilityService,
)

from app.services.compliance_replay_service import (
    ComplianceReplayEngine,
    RuleType,
)

from app.services.regulatory_confidence_service import (
    RegulatoryConfidenceScorer,
)

from app.services.attestation_service import (
    ThirdPartyAttestationService,
    AttestationRole,
    AttestationType,
    AuditOpinionType,
)

from app.services.behavioral_analytics_service import (
    BehavioralAnalyticsService,
    AnomalyType,
)

from app.services.audit_export_service import (
    AuditReadyExportService,
    ExportFormat,
    ExportPurpose,
    DataCategory,
)

# =========================================================
# REPORTING SERVICE
# =========================================================
from app.services.audit_reporting import (
    AuditReportingService,
)


# =========================================================
# CONVENIENCE CLASS: Unified Audit Facade
# =========================================================
class UnifiedAuditService:
    """
    Unified facade providing access to all audit services.
    
    Usage:
        from app.services.audit_consolidated_service import UnifiedAuditService
        
        audit = UnifiedAuditService(db)
        
        # Basic audit logging
        await audit.basic.log_action(...)
        
        # Vault operations
        stats = await audit.vault.get_vault_statistics(entity_id)
        
        # Forensic analysis
        benfords = await audit.forensic.run_benfords_law_analysis(...)
        
        # Explainability
        paye_breakdown = audit.explainability.explain_paye_calculation(...)
        
        # Compliance replay
        replay = audit.replay.replay_tax_calculation(...)
    """
    
    def __init__(self, db):
        """Initialize all audit services with the database session."""
        self.db = db
        
        # Basic Services
        self._basic = None
        self._vault = None
        
        # Advanced Services
        self._role_enforcer = None
        self._evidence = None
        self._reproducible = None
        self._findings = None
        self._sessions = None
        self._advanced_system = None
        
        # Forensic Services
        self._forensic = None
        self._worm = None
        
        # Enterprise Services (stateless - no db required)
        self._explainability = AuditExplainabilityService()
        self._replay = ComplianceReplayEngine()
        self._confidence = RegulatoryConfidenceScorer()
        self._attestation = ThirdPartyAttestationService()
        self._behavioral = BehavioralAnalyticsService()
        self._export = AuditReadyExportService()
    
    # ===== Basic Services =====
    @property
    def basic(self) -> AuditService:
        """Basic audit logging service."""
        if self._basic is None:
            self._basic = AuditService(self.db)
        return self._basic
    
    @property
    def vault(self) -> AuditVaultService:
        """Audit vault service for 5-year retention."""
        if self._vault is None:
            self._vault = AuditVaultService(self.db)
        return self._vault
    
    # ===== Advanced System Services =====
    @property
    def role_enforcer(self) -> AuditorRoleEnforcer:
        """Auditor read-only role enforcement."""
        if self._role_enforcer is None:
            self._role_enforcer = AuditorRoleEnforcer()
        return self._role_enforcer
    
    @property
    def evidence(self) -> EvidenceImmutabilityService:
        """Evidence immutability service."""
        if self._evidence is None:
            self._evidence = EvidenceImmutabilityService(self.db)
        return self._evidence
    
    @property
    def reproducible(self) -> ReproducibleAuditService:
        """Reproducible audit runs service."""
        if self._reproducible is None:
            self._reproducible = ReproducibleAuditService(self.db)
        return self._reproducible
    
    @property
    def findings(self) -> AuditFindingsService:
        """Audit findings service."""
        if self._findings is None:
            self._findings = AuditFindingsService(self.db)
        return self._findings
    
    @property
    def sessions(self) -> AuditorSessionService:
        """Auditor session management service."""
        if self._sessions is None:
            self._sessions = AuditorSessionService(self.db)
        return self._sessions
    
    @property
    def advanced_system(self) -> AdvancedAuditSystemService:
        """Advanced audit system service."""
        if self._advanced_system is None:
            self._advanced_system = AdvancedAuditSystemService(self.db)
        return self._advanced_system
    
    # ===== Forensic Services =====
    @property
    def forensic(self) -> ForensicAuditService:
        """Forensic audit service."""
        if self._forensic is None:
            self._forensic = ForensicAuditService(self.db)
        return self._forensic
    
    @property
    def worm(self) -> WORMStorageService:
        """WORM storage service."""
        if self._worm is None:
            self._worm = WORMStorageService(self.db)
        return self._worm
    
    # ===== Enterprise Services (Stateless) =====
    @property
    def explainability(self) -> AuditExplainabilityService:
        """Tax explainability service."""
        return self._explainability
    
    @property
    def replay(self) -> ComplianceReplayEngine:
        """Compliance replay engine."""
        return self._replay
    
    @property
    def confidence(self) -> RegulatoryConfidenceScorer:
        """Regulatory confidence scorer."""
        return self._confidence
    
    @property
    def attestation(self) -> ThirdPartyAttestationService:
        """Third-party attestation service."""
        return self._attestation
    
    @property
    def behavioral(self) -> BehavioralAnalyticsService:
        """Behavioral analytics service."""
        return self._behavioral
    
    @property
    def export(self) -> AuditReadyExportService:
        """Audit-ready export service."""
        return self._export


# =========================================================
# EXPORTS
# =========================================================
__all__ = [
    # Unified Facade
    "UnifiedAuditService",
    
    # Basic Audit
    "AuditService",
    "AuditEntry",
    "AuditVaultService",
    "RetentionStatus",
    "DocumentType",
    "VaultDocument",
    "VaultStatistics",
    "NTAA_RETENTION_YEARS",
    "LEGAL_HOLD_EXTENSION_YEARS",
    "ARCHIVE_AFTER_YEARS",
    
    # Advanced System
    "AuditorPermissionError",
    "EvidenceImmutabilityError",
    "AuditRunError",
    "AuditorRoleEnforcer",
    "EvidenceImmutabilityService",
    "ReproducibleAuditService",
    "AuditFindingsService",
    "AuditorSessionService",
    "AdvancedAuditSystemService",
    
    # Forensic
    "ForensicAuditService",
    "WORMStorageService",
    
    # Enterprise
    "AuditExplainabilityService",
    "ComplianceReplayEngine",
    "RuleType",
    "RegulatoryConfidenceScorer",
    "ThirdPartyAttestationService",
    "AttestationRole",
    "AttestationType",
    "AuditOpinionType",
    "BehavioralAnalyticsService",
    "AnomalyType",
    "AuditReadyExportService",
    "ExportFormat",
    "ExportPurpose",
    "DataCategory",
    
    # Reporting
    "AuditReportingService",
]
