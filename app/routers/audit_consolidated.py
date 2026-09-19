"""
Tekvwa Pro Audit - Consolidated Audit Router

This module provides a unified entry point for all audit-related API endpoints.
It consolidates routes from:

1. Basic Audit Trail (audit.py):
   - /audit/{entity_id}/logs - Audit log listing
   - /audit/{entity_id}/history - Entity history
   - /audit/{entity_id}/vault - Audit vault operations

2. Audit System (audit_system.py):
   - /api/audit-system/runs - Reproducible audit runs
   - /api/audit-system/findings - Human-readable findings
   - /api/audit-system/evidence - Immutable evidence
   - /api/audit-system/sessions - Auditor sessions
   - /api/audit-system/role - Role enforcement

3. Advanced Audit (advanced_audit.py):
   - /advanced-audit/explainability - Tax calculation explanations
   - /advanced-audit/replay - Compliance replay
   - /advanced-audit/confidence - Regulatory confidence scoring
   - /advanced-audit/attestation - Third-party sign-offs
   - /advanced-audit/behavioral - Behavioral analytics
   - /advanced-audit/export - Audit-ready exports

4. Forensic Audit (forensic_audit.py):
   - /forensic-audit/benfords-law - Benford's Law analysis
   - /forensic-audit/anomaly-detection - Z-score anomaly detection
   - /forensic-audit/nrs-gap - NRS Gap analysis
   - /forensic-audit/worm - WORM storage

USAGE:
    This consolidated router re-exports all individual routers.
    In main.py, you can either:
    
    Option 1 (Recommended): Continue using individual routers
        app.include_router(audit.router, prefix="/api/v1/entities")
        app.include_router(audit_system.router)
        app.include_router(advanced_audit.router, prefix="/api/v1/entities")
        app.include_router(forensic_audit.router, prefix="/api/v1/entities")
    
    Option 2: Use the unified router (after removing individual routers)
        app.include_router(audit_consolidated.unified_router, prefix="/api/v1")

NTAA 2025 & FIRS Compliance:
- All endpoints maintain 5-year audit trail
- Immutable evidence storage
- Device fingerprint verification
- Export for regulatory audits
"""

from fastapi import APIRouter

# Import individual routers
from app.routers.audit import router as basic_audit_router
from app.routers.audit_system import router as audit_system_router
from app.routers.advanced_audit import router as advanced_audit_router
from app.routers.forensic_audit import router as forensic_audit_router


# =========================================================
# UNIFIED ROUTER
# Combines all audit routes under one namespace
# =========================================================

unified_router = APIRouter(tags=["Unified Audit System"])

# Include all sub-routers with their prefixes
# Basic audit trail - entity-scoped
unified_router.include_router(
    basic_audit_router,
    prefix="/entities",
    tags=["Audit Trail"],
)

# Advanced audit system - global (cross-entity)
# Note: audit_system already has /api/audit-system prefix
unified_router.include_router(
    audit_system_router,
    tags=["Audit System"],
)

# Enterprise advanced audit - entity-scoped
unified_router.include_router(
    advanced_audit_router,
    prefix="/entities",
    tags=["Advanced Audit"],
)

# Forensic audit - entity-scoped
unified_router.include_router(
    forensic_audit_router,
    prefix="/entities",
    tags=["Forensic Audit"],
)


# =========================================================
# EXPORTS
# =========================================================

# Export individual routers for backward compatibility
__all__ = [
    # Unified router
    "unified_router",
    
    # Individual routers for granular control
    "basic_audit_router",
    "audit_system_router",
    "advanced_audit_router",
    "forensic_audit_router",
]

# Alias for convenience
router = unified_router
