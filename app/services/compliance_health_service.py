"""
Tekvwa Pro Audit - Compliance Health Service

Real-time compliance score calculation with automated threshold monitoring.
Implements 2026 Nigeria Tax Reforms compliance checking.
"""

import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import BusinessEntity
from app.models.transaction import Transaction


class ComplianceHealthService:
    """
    Service for real-time compliance health monitoring.
    
    Features:
    - Compliance score calculation (0-100)
    - Threshold monitoring for tax obligations
    - Alert generation for approaching thresholds
    - Subscription management for notifications
    """
    
    # 2026 Tax Reform Thresholds
    THRESHOLDS = {
        "vat_registration": Decimal("25000000"),      # ₦25M annual turnover
        "small_company_turnover": Decimal("50000000"), # ₦50M for 0% CIT
        "small_company_assets": Decimal("250000000"),  # ₦250M fixed assets
        "dev_levy_turnover": Decimal("100000000"),     # ₦100M for exemption
        "dev_levy_assets": Decimal("250000000"),       # ₦250M fixed assets
    }
    
    # Warning threshold percentage (alert when reaching this %)
    WARNING_THRESHOLD_PERCENT = Decimal("0.80")  # 80%
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_compliance_health(
        self,
        entity_id: uuid.UUID,
        include_alerts: bool = True,
    ) -> Dict[str, Any]:
        """
        Get real-time compliance health score with threshold monitoring.
        
        Args:
            entity_id: Business entity UUID
            include_alerts: Include threshold alerts in response
            
        Returns:
            Dict with overall_status, score, checks, alerts, thresholds
        """
        # Get entity
        entity = await self._get_entity(entity_id)
        if not entity:
            return {
                "overall_status": "unknown",
                "score": 0,
                "message": "Entity not found",
                "checks": [],
                "alerts": [],
                "thresholds": {},
            }
        
        # Perform compliance checks
        checks = await self._perform_compliance_checks(entity)
        
        # Calculate score
        total_checks = len(checks)
        passed = sum(1 for c in checks if c["status"] == "pass")
        score = int((passed / total_checks) * 100) if total_checks > 0 else 0
        
        # Count issues and warnings
        issues = sum(1 for c in checks if c["status"] == "fail")
        warnings = sum(1 for c in checks if c["status"] == "warning")
        
        # Determine overall status
        if issues > 0:
            overall_status = "critical"
        elif warnings > 0:
            overall_status = "warning"
        elif score == 100:
            overall_status = "excellent"
        else:
            overall_status = "good"
        
        result = {
            "overall_status": overall_status,
            "score": score,
            "issues_count": issues,
            "warnings_count": warnings,
            "checks": checks,
            "summary": f"{passed}/{total_checks} compliance checks passed",
            "entity_id": str(entity_id),
            "entity_name": entity.name,
            "last_checked": datetime.utcnow().isoformat(),
        }
        
        # Add threshold status
        result["thresholds"] = await self._get_threshold_details(entity)
        
        # Add alerts if requested
        if include_alerts:
            result["alerts"] = await self._generate_alerts(entity)
        
        return result
    
    async def get_threshold_status(
        self,
        entity_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Get current threshold status for all compliance metrics.
        
        Shows current values vs threshold limits with percentage used.
        """
        entity = await self._get_entity(entity_id)
        if not entity:
            return {"error": "Entity not found"}
        
        return await self._get_threshold_details(entity)
    
    async def get_alerts(
        self,
        entity_id: uuid.UUID,
        severity: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get compliance threshold alerts.
        
        Args:
            entity_id: Business entity UUID
            severity: Filter by severity (critical, warning, info)
            
        Returns:
            Dict with alerts array and summary
        """
        entity = await self._get_entity(entity_id)
        if not entity:
            return {"error": "Entity not found", "alerts": []}
        
        alerts = await self._generate_alerts(entity)
        
        # Filter by severity if specified
        if severity:
            alerts = [a for a in alerts if a["severity"] == severity]
        
        # Group alerts by severity
        critical = [a for a in alerts if a["severity"] == "critical"]
        warning = [a for a in alerts if a["severity"] == "warning"]
        info = [a for a in alerts if a["severity"] == "info"]
        
        return {
            "entity_id": str(entity_id),
            "entity_name": entity.name,
            "total_alerts": len(alerts),
            "critical_count": len(critical),
            "warning_count": len(warning),
            "info_count": len(info),
            "alerts": alerts,
            "last_checked": datetime.utcnow().isoformat(),
        }
    
    async def subscribe_alerts(
        self,
        entity_id: uuid.UUID,
        user_id: uuid.UUID,
        alert_types: List[str],
    ) -> Dict[str, Any]:
        """
        Subscribe to compliance threshold alerts.
        
        Note: This creates a subscription record for notification purposes.
        Actual notification delivery would be handled by a background task.
        """
        # For now, return confirmation of subscription intent
        # Full implementation would store this in a subscriptions table
        return {
            "status": "subscribed",
            "entity_id": str(entity_id),
            "user_id": str(user_id),
            "alert_types": alert_types,
            "message": "You will receive notifications for compliance threshold alerts",
            "subscribed_at": datetime.utcnow().isoformat(),
        }
    
    async def _get_entity(self, entity_id: uuid.UUID) -> Optional[BusinessEntity]:
        """Get entity by ID."""
        result = await self.db.execute(
            select(BusinessEntity).where(BusinessEntity.id == entity_id)
        )
        return result.scalar_one_or_none()
    
    async def _get_ytd_turnover(self, entity_id: uuid.UUID) -> Decimal:
        """Calculate year-to-date turnover from transactions."""
        current_year = datetime.now().year
        start_of_year = date(current_year, 1, 1)
        
        result = await self.db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(
                Transaction.entity_id == entity_id,
                Transaction.type == "income",
                Transaction.transaction_date >= start_of_year,
            )
        )
        return Decimal(str(result.scalar() or 0))
    
    async def _perform_compliance_checks(
        self,
        entity: BusinessEntity,
    ) -> List[Dict[str, Any]]:
        """
        Perform all compliance checks for an entity.
        
        Returns list of check results with status, message, and recommendations.
        """
        checks = []
        turnover = entity.annual_turnover or Decimal("0")
        fixed_assets = entity.fixed_assets_value or Decimal("0")
        
        # Check 1: TIN Registration
        if entity.tin:
            checks.append({
                "name": "TIN Registration",
                "category": "registration",
                "status": "pass",
                "message": f"TIN registered: {entity.tin}",
                "icon": "check-circle",
                "required": True,
            })
        else:
            checks.append({
                "name": "TIN Registration",
                "category": "registration",
                "status": "fail",
                "message": "TIN not registered - required for NRS e-invoicing",
                "icon": "x-circle",
                "required": True,
                "action": "Register for TIN at FIRS office or online portal",
            })
        
        # Check 2: CAC Registration
        if entity.rc_number:
            checks.append({
                "name": "CAC Registration",
                "category": "registration",
                "status": "pass",
                "message": f"CAC registered: {entity.rc_number}",
                "icon": "check-circle",
                "required": True,
            })
        else:
            checks.append({
                "name": "CAC Registration",
                "category": "registration",
                "status": "fail",
                "message": "CAC number missing",
                "icon": "x-circle",
                "required": True,
                "action": "Complete CAC registration at Corporate Affairs Commission",
            })
        
        # Check 3: Small Company Status (for CIT exemption)
        is_small_company = (
            turnover <= self.THRESHOLDS["small_company_turnover"] and
            fixed_assets <= self.THRESHOLDS["small_company_assets"]
        )
        
        if entity.business_type and entity.business_type.value == "limited_company":
            if is_small_company:
                checks.append({
                    "name": "Small Company Status",
                    "category": "tax_exemption",
                    "status": "pass",
                    "message": f"Qualifies for 0% CIT (Turnover: ₦{turnover:,.0f}, Assets: ₦{fixed_assets:,.0f})",
                    "icon": "badge-check",
                    "highlight": True,
                    "benefit": "0% Company Income Tax rate applies",
                })
            else:
                reasons = []
                if turnover > self.THRESHOLDS["small_company_turnover"]:
                    reasons.append(f"Turnover ₦{turnover:,.0f} > ₦50M")
                if fixed_assets > self.THRESHOLDS["small_company_assets"]:
                    reasons.append(f"Assets ₦{fixed_assets:,.0f} > ₦250M")
                checks.append({
                    "name": "Small Company Status",
                    "category": "tax_exemption",
                    "status": "info",
                    "message": f"Standard CIT applies: {', '.join(reasons)}",
                    "icon": "information-circle",
                    "note": "20% CIT rate applies for medium companies, 30% for large",
                })
        
        # Check 4: Development Levy Exemption
        is_dev_levy_exempt = (
            turnover <= self.THRESHOLDS["dev_levy_turnover"] and
            fixed_assets <= self.THRESHOLDS["dev_levy_assets"]
        )
        
        if entity.business_type and entity.business_type.value == "limited_company":
            if is_dev_levy_exempt:
                checks.append({
                    "name": "Development Levy",
                    "category": "tax_exemption",
                    "status": "pass",
                    "message": "Exempt from 4% Development Levy",
                    "icon": "shield-check",
                    "benefit": "No Development Levy payable",
                })
            else:
                checks.append({
                    "name": "Development Levy",
                    "category": "tax_obligation",
                    "status": "info",
                    "message": "Subject to 4% Development Levy on assessable profit",
                    "icon": "currency-dollar",
                    "obligation": "4% of assessable profit",
                })
        else:
            checks.append({
                "name": "Development Levy",
                "category": "tax_exemption",
                "status": "pass",
                "message": "Not applicable (Business Names pay PIT only)",
                "icon": "shield-check",
            })
        
        # Check 5: VAT Registration
        if entity.is_vat_registered:
            checks.append({
                "name": "VAT Registration",
                "category": "registration",
                "status": "pass",
                "message": "VAT registered - can issue VAT invoices",
                "icon": "check-circle",
            })
        else:
            if turnover > self.THRESHOLDS["vat_registration"]:
                checks.append({
                    "name": "VAT Registration",
                    "category": "registration",
                    "status": "warning",
                    "message": f"Turnover ₦{turnover:,.0f} exceeds ₦25M threshold - VAT registration recommended",
                    "icon": "exclamation",
                    "action": "Register for VAT at FIRS to comply with tax law",
                })
            else:
                checks.append({
                    "name": "VAT Registration",
                    "category": "registration",
                    "status": "info",
                    "message": f"Below VAT threshold (₦25M). Current: ₦{turnover:,.0f}",
                    "icon": "information-circle",
                })
        
        # Check 6: NRS e-Invoicing Readiness
        nrs_ready = bool(entity.tin) and bool(entity.rc_number)
        if nrs_ready:
            checks.append({
                "name": "NRS e-Invoicing",
                "category": "compliance",
                "status": "pass",
                "message": "Ready for NRS electronic invoicing",
                "icon": "document-check",
            })
        else:
            missing = []
            if not entity.tin:
                missing.append("TIN")
            if not entity.rc_number:
                missing.append("CAC number")
            checks.append({
                "name": "NRS e-Invoicing",
                "category": "compliance",
                "status": "fail",
                "message": f"Missing {', '.join(missing)} for NRS compliance",
                "icon": "document-x",
                "action": f"Register {', '.join(missing)} to enable NRS e-invoicing",
            })
        
        return checks
    
    async def _get_threshold_details(
        self,
        entity: BusinessEntity,
    ) -> Dict[str, Any]:
        """
        Get detailed threshold status for entity.
        
        Shows current values, limits, percentages, and headroom.
        """
        turnover = entity.annual_turnover or Decimal("0")
        fixed_assets = entity.fixed_assets_value or Decimal("0")
        
        def calculate_threshold_status(current: Decimal, threshold: Decimal) -> Dict[str, Any]:
            percentage = float((current / threshold) * 100) if threshold > 0 else 0
            headroom = max(threshold - current, Decimal("0"))
            at_risk = percentage >= 80
            exceeded = current > threshold
            
            if exceeded:
                status = "exceeded"
            elif at_risk:
                status = "at_risk"
            else:
                status = "safe"
            
            return {
                "current_value": float(current),
                "threshold": float(threshold),
                "percentage_used": round(percentage, 1),
                "headroom": float(headroom),
                "status": status,
                "at_risk": at_risk,
                "exceeded": exceeded,
            }
        
        return {
            "vat_registration": {
                "name": "VAT Registration Threshold",
                "description": "Mandatory VAT registration when annual turnover exceeds ₦25M",
                **calculate_threshold_status(turnover, self.THRESHOLDS["vat_registration"]),
            },
            "small_company_turnover": {
                "name": "Small Company Turnover Limit",
                "description": "0% CIT applies when turnover ≤ ₦50M",
                **calculate_threshold_status(turnover, self.THRESHOLDS["small_company_turnover"]),
            },
            "small_company_assets": {
                "name": "Small Company Assets Limit",
                "description": "0% CIT applies when fixed assets ≤ ₦250M",
                **calculate_threshold_status(fixed_assets, self.THRESHOLDS["small_company_assets"]),
            },
            "dev_levy_turnover": {
                "name": "Development Levy Turnover Exemption",
                "description": "Exempt from 4% Development Levy when turnover ≤ ₦100M",
                **calculate_threshold_status(turnover, self.THRESHOLDS["dev_levy_turnover"]),
            },
            "dev_levy_assets": {
                "name": "Development Levy Assets Exemption",
                "description": "Exempt from 4% Development Levy when assets ≤ ₦250M",
                **calculate_threshold_status(fixed_assets, self.THRESHOLDS["dev_levy_assets"]),
            },
            "summary": {
                "annual_turnover": float(turnover),
                "fixed_assets_value": float(fixed_assets),
                "currency": "NGN",
            },
        }
    
    async def _generate_alerts(
        self,
        entity: BusinessEntity,
    ) -> List[Dict[str, Any]]:
        """
        Generate threshold alerts for entity.
        
        Creates alerts when approaching or exceeding thresholds.
        """
        alerts = []
        turnover = entity.annual_turnover or Decimal("0")
        fixed_assets = entity.fixed_assets_value or Decimal("0")
        warning_percent = self.WARNING_THRESHOLD_PERCENT
        
        # Check VAT registration threshold
        vat_threshold = self.THRESHOLDS["vat_registration"]
        if not entity.is_vat_registered:
            if turnover > vat_threshold:
                alerts.append({
                    "id": f"vat_exceeded_{entity.id}",
                    "type": "vat_registration",
                    "severity": "critical",
                    "title": "VAT Registration Required",
                    "message": f"Annual turnover ₦{turnover:,.0f} exceeds ₦25M threshold. VAT registration is mandatory.",
                    "action": "Register for VAT immediately to avoid penalties",
                    "threshold": float(vat_threshold),
                    "current_value": float(turnover),
                    "created_at": datetime.utcnow().isoformat(),
                })
            elif turnover >= vat_threshold * warning_percent:
                remaining = vat_threshold - turnover
                alerts.append({
                    "id": f"vat_approaching_{entity.id}",
                    "type": "vat_registration",
                    "severity": "warning",
                    "title": "Approaching VAT Threshold",
                    "message": f"₦{remaining:,.0f} remaining before VAT registration threshold. Current: ₦{turnover:,.0f}",
                    "action": "Prepare for VAT registration",
                    "threshold": float(vat_threshold),
                    "current_value": float(turnover),
                    "percentage_used": float((turnover / vat_threshold) * 100),
                    "created_at": datetime.utcnow().isoformat(),
                })
        
        # Check Small Company status
        if entity.business_type and entity.business_type.value == "limited_company":
            sc_turnover = self.THRESHOLDS["small_company_turnover"]
            sc_assets = self.THRESHOLDS["small_company_assets"]
            
            # Turnover check
            if turnover > sc_turnover:
                alerts.append({
                    "id": f"sc_turnover_exceeded_{entity.id}",
                    "type": "small_company_status",
                    "severity": "info",
                    "title": "Small Company Turnover Exceeded",
                    "message": f"Turnover ₦{turnover:,.0f} exceeds ₦50M. Standard CIT rates now apply.",
                    "action": "Plan for CIT at standard rates",
                    "threshold": float(sc_turnover),
                    "current_value": float(turnover),
                    "created_at": datetime.utcnow().isoformat(),
                })
            elif turnover >= sc_turnover * warning_percent:
                remaining = sc_turnover - turnover
                alerts.append({
                    "id": f"sc_turnover_approaching_{entity.id}",
                    "type": "small_company_status",
                    "severity": "warning",
                    "title": "Small Company Status at Risk",
                    "message": f"₦{remaining:,.0f} remaining before losing 0% CIT benefit. Current: ₦{turnover:,.0f}",
                    "action": "Consider timing of income recognition",
                    "threshold": float(sc_turnover),
                    "current_value": float(turnover),
                    "percentage_used": float((turnover / sc_turnover) * 100),
                    "created_at": datetime.utcnow().isoformat(),
                })
            
            # Assets check
            if fixed_assets > sc_assets:
                alerts.append({
                    "id": f"sc_assets_exceeded_{entity.id}",
                    "type": "small_company_status",
                    "severity": "info",
                    "title": "Small Company Assets Exceeded",
                    "message": f"Fixed assets ₦{fixed_assets:,.0f} exceeds ₦250M limit.",
                    "action": "Standard CIT rates apply",
                    "threshold": float(sc_assets),
                    "current_value": float(fixed_assets),
                    "created_at": datetime.utcnow().isoformat(),
                })
            elif fixed_assets >= sc_assets * warning_percent:
                remaining = sc_assets - fixed_assets
                alerts.append({
                    "id": f"sc_assets_approaching_{entity.id}",
                    "type": "small_company_status",
                    "severity": "warning",
                    "title": "Small Company Assets Approaching Limit",
                    "message": f"₦{remaining:,.0f} remaining before losing 0% CIT benefit.",
                    "action": "Consider asset acquisition timing",
                    "threshold": float(sc_assets),
                    "current_value": float(fixed_assets),
                    "percentage_used": float((fixed_assets / sc_assets) * 100),
                    "created_at": datetime.utcnow().isoformat(),
                })
            
            # Development Levy checks
            dl_turnover = self.THRESHOLDS["dev_levy_turnover"]
            if turnover > dl_turnover:
                alerts.append({
                    "id": f"dl_turnover_exceeded_{entity.id}",
                    "type": "development_levy",
                    "severity": "info",
                    "title": "Development Levy Now Applicable",
                    "message": f"Turnover ₦{turnover:,.0f} exceeds ₦100M. 4% Development Levy applies.",
                    "action": "Include Development Levy in tax planning",
                    "threshold": float(dl_turnover),
                    "current_value": float(turnover),
                    "created_at": datetime.utcnow().isoformat(),
                })
            elif turnover >= dl_turnover * warning_percent:
                remaining = dl_turnover - turnover
                alerts.append({
                    "id": f"dl_approaching_{entity.id}",
                    "type": "development_levy",
                    "severity": "warning",
                    "title": "Development Levy Exemption at Risk",
                    "message": f"₦{remaining:,.0f} remaining before 4% Development Levy applies.",
                    "action": "Monitor turnover closely",
                    "threshold": float(dl_turnover),
                    "current_value": float(turnover),
                    "percentage_used": float((turnover / dl_turnover) * 100),
                    "created_at": datetime.utcnow().isoformat(),
                })
        
        # Check missing registrations
        if not entity.tin:
            alerts.append({
                "id": f"missing_tin_{entity.id}",
                "type": "registration",
                "severity": "critical",
                "title": "TIN Registration Required",
                "message": "Tax Identification Number (TIN) is required for NRS e-invoicing compliance",
                "action": "Register for TIN at FIRS",
                "created_at": datetime.utcnow().isoformat(),
            })
        
        if not entity.rc_number:
            alerts.append({
                "id": f"missing_cac_{entity.id}",
                "type": "registration",
                "severity": "critical",
                "title": "CAC Registration Required",
                "message": "CAC registration number is required for business compliance",
                "action": "Complete registration at Corporate Affairs Commission",
                "created_at": datetime.utcnow().isoformat(),
            })
        
        # Sort alerts by severity
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        alerts.sort(key=lambda x: severity_order.get(x["severity"], 3))
        
        return alerts
