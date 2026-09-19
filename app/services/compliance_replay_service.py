"""
Tekvwa Pro Audit - Compliance Replay Engine (Audit Time Machine)

This module provides point-in-time reconstruction of tax calculations,
enabling auditors to:
- Reconstruct any historical tax calculation
- View rules, rates, and parameters as they were at any date
- Compare current vs historical calculations
- Prove compliance at specific points in time

Supports temporal queries for audit defense and regulatory inquiries.
"""

import uuid
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json
import hashlib

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession


class RuleType(str, Enum):
    """Types of tax rules that can be versioned."""
    PAYE_BAND = "paye_band"
    VAT_RATE = "vat_rate"
    WHT_RATE = "wht_rate"
    CIT_RATE = "cit_rate"
    MINIMUM_TAX = "minimum_tax"
    ETR_RATE = "etr_rate"
    CGT_RATE = "cgt_rate"
    RELIEF_AMOUNT = "relief_amount"
    THRESHOLD = "threshold"
    EXCHANGE_RATE = "exchange_rate"


@dataclass
class TaxRuleVersion:
    """A versioned tax rule for point-in-time queries."""
    rule_type: RuleType
    rule_key: str
    value: Any
    effective_from: date
    effective_to: Optional[date]
    legal_reference: str
    description: str
    
    def is_effective_on(self, query_date: date) -> bool:
        """Check if rule was effective on a specific date."""
        if query_date < self.effective_from:
            return False
        if self.effective_to and query_date > self.effective_to:
            return False
        return True


@dataclass
class ReplaySnapshot:
    """Point-in-time snapshot for compliance replay."""
    snapshot_id: str
    entity_id: uuid.UUID
    snapshot_date: date
    created_at: datetime
    tax_type: str
    calculation_inputs: Dict[str, Any]
    calculation_outputs: Dict[str, Any]
    rules_applied: List[Dict[str, Any]]
    hash_signature: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "snapshot_id": self.snapshot_id,
            "entity_id": str(self.entity_id),
            "snapshot_date": self.snapshot_date.isoformat(),
            "created_at": self.created_at.isoformat(),
            "tax_type": self.tax_type,
            "calculation_inputs": self.calculation_inputs,
            "calculation_outputs": self.calculation_outputs,
            "rules_applied": self.rules_applied,
            "hash_signature": self.hash_signature,
        }


# Historical Tax Rules Registry
# This stores all versions of tax rules for replay capability
TAX_RULES_REGISTRY: List[TaxRuleVersion] = [
    # PAYE Bands - Pre-2026 (2020 rates)
    TaxRuleVersion(
        rule_type=RuleType.PAYE_BAND,
        rule_key="band_1",
        value={"lower": 0, "upper": 300000, "rate": 7},
        effective_from=date(2020, 1, 1),
        effective_to=date(2025, 12, 31),
        legal_reference="PITA S.37, Sixth Schedule (2020)",
        description="First NGN 300,000 at 7%",
    ),
    TaxRuleVersion(
        rule_type=RuleType.PAYE_BAND,
        rule_key="band_2",
        value={"lower": 300000, "upper": 600000, "rate": 11},
        effective_from=date(2020, 1, 1),
        effective_to=date(2025, 12, 31),
        legal_reference="PITA S.37, Sixth Schedule (2020)",
        description="Next NGN 300,000 at 11%",
    ),
    TaxRuleVersion(
        rule_type=RuleType.PAYE_BAND,
        rule_key="band_3",
        value={"lower": 600000, "upper": 1100000, "rate": 15},
        effective_from=date(2020, 1, 1),
        effective_to=date(2025, 12, 31),
        legal_reference="PITA S.37, Sixth Schedule (2020)",
        description="Next NGN 500,000 at 15%",
    ),
    TaxRuleVersion(
        rule_type=RuleType.PAYE_BAND,
        rule_key="band_4",
        value={"lower": 1100000, "upper": 1600000, "rate": 19},
        effective_from=date(2020, 1, 1),
        effective_to=date(2025, 12, 31),
        legal_reference="PITA S.37, Sixth Schedule (2020)",
        description="Next NGN 500,000 at 19%",
    ),
    TaxRuleVersion(
        rule_type=RuleType.PAYE_BAND,
        rule_key="band_5",
        value={"lower": 1600000, "upper": 3200000, "rate": 21},
        effective_from=date(2020, 1, 1),
        effective_to=date(2025, 12, 31),
        legal_reference="PITA S.37, Sixth Schedule (2020)",
        description="Next NGN 1,600,000 at 21%",
    ),
    TaxRuleVersion(
        rule_type=RuleType.PAYE_BAND,
        rule_key="band_6",
        value={"lower": 3200000, "upper": None, "rate": 24},
        effective_from=date(2020, 1, 1),
        effective_to=date(2025, 12, 31),
        legal_reference="PITA S.37, Sixth Schedule (2020)",
        description="Above NGN 3,200,000 at 24%",
    ),
    
    # PAYE Bands - 2026 Reform
    TaxRuleVersion(
        rule_type=RuleType.PAYE_BAND,
        rule_key="band_1",
        value={"lower": 0, "upper": 800000, "rate": 0},
        effective_from=date(2026, 1, 1),
        effective_to=None,
        legal_reference="PITA S.37, Sixth Schedule (2026 Amendment)",
        description="First NGN 800,000 at 0% (Tax-Free)",
    ),
    TaxRuleVersion(
        rule_type=RuleType.PAYE_BAND,
        rule_key="band_2",
        value={"lower": 800000, "upper": 2400000, "rate": 15},
        effective_from=date(2026, 1, 1),
        effective_to=None,
        legal_reference="PITA S.37, Sixth Schedule (2026 Amendment)",
        description="NGN 800,001 - 2,400,000 at 15%",
    ),
    TaxRuleVersion(
        rule_type=RuleType.PAYE_BAND,
        rule_key="band_3",
        value={"lower": 2400000, "upper": 4800000, "rate": 20},
        effective_from=date(2026, 1, 1),
        effective_to=None,
        legal_reference="PITA S.37, Sixth Schedule (2026 Amendment)",
        description="NGN 2,400,001 - 4,800,000 at 20%",
    ),
    TaxRuleVersion(
        rule_type=RuleType.PAYE_BAND,
        rule_key="band_4",
        value={"lower": 4800000, "upper": 7200000, "rate": 25},
        effective_from=date(2026, 1, 1),
        effective_to=None,
        legal_reference="PITA S.37, Sixth Schedule (2026 Amendment)",
        description="NGN 4,800,001 - 7,200,000 at 25%",
    ),
    TaxRuleVersion(
        rule_type=RuleType.PAYE_BAND,
        rule_key="band_5",
        value={"lower": 7200000, "upper": None, "rate": 30},
        effective_from=date(2026, 1, 1),
        effective_to=None,
        legal_reference="PITA S.37, Sixth Schedule (2026 Amendment)",
        description="Above NGN 7,200,000 at 30%",
    ),
    
    # VAT Rate Changes
    TaxRuleVersion(
        rule_type=RuleType.VAT_RATE,
        rule_key="standard_rate",
        value=Decimal("5"),
        effective_from=date(1993, 1, 1),
        effective_to=date(2020, 1, 31),
        legal_reference="VATA S.4",
        description="Original VAT rate of 5%",
    ),
    TaxRuleVersion(
        rule_type=RuleType.VAT_RATE,
        rule_key="standard_rate",
        value=Decimal("7.5"),
        effective_from=date(2020, 2, 1),
        effective_to=None,
        legal_reference="Finance Act 2019, S.35",
        description="Increased VAT rate of 7.5%",
    ),
    
    # CIT Rates
    TaxRuleVersion(
        rule_type=RuleType.CIT_RATE,
        rule_key="large_company",
        value=Decimal("30"),
        effective_from=date(2020, 1, 1),
        effective_to=None,
        legal_reference="CITA S.40(1)",
        description="CIT rate for large companies (turnover > NGN 100M)",
    ),
    TaxRuleVersion(
        rule_type=RuleType.CIT_RATE,
        rule_key="medium_company",
        value=Decimal("20"),
        effective_from=date(2020, 1, 1),
        effective_to=None,
        legal_reference="CITA S.40(2)",
        description="CIT rate for medium companies (turnover NGN 25M - 100M)",
    ),
    TaxRuleVersion(
        rule_type=RuleType.CIT_RATE,
        rule_key="small_company",
        value=Decimal("0"),
        effective_from=date(2020, 1, 1),
        effective_to=None,
        legal_reference="CITA S.40(3)",
        description="CIT rate for small companies (turnover < NGN 25M)",
    ),
    
    # Minimum Tax
    TaxRuleVersion(
        rule_type=RuleType.MINIMUM_TAX,
        rule_key="rate",
        value=Decimal("0.5"),
        effective_from=date(2020, 1, 1),
        effective_to=None,
        legal_reference="CITA S.33",
        description="Minimum tax of 0.5% of gross turnover",
    ),
    
    # CRA (Consolidated Relief Allowance)
    TaxRuleVersion(
        rule_type=RuleType.RELIEF_AMOUNT,
        rule_key="cra_fixed",
        value=Decimal("200000"),
        effective_from=date(2011, 1, 1),
        effective_to=None,
        legal_reference="PITA S.33(1)",
        description="Fixed CRA component of NGN 200,000",
    ),
    TaxRuleVersion(
        rule_type=RuleType.RELIEF_AMOUNT,
        rule_key="cra_percentage",
        value=Decimal("20"),
        effective_from=date(2011, 1, 1),
        effective_to=None,
        legal_reference="PITA S.33(1)",
        description="Variable CRA component of 20% of gross income",
    ),
    
    # ETR 2026 (Minimum Effective Tax Rate)
    TaxRuleVersion(
        rule_type=RuleType.ETR_RATE,
        rule_key="minimum_etr",
        value=Decimal("15"),
        effective_from=date(2026, 1, 1),
        effective_to=None,
        legal_reference="Finance Act 2026, S.12",
        description="Minimum ETR of 15% for qualifying multinational enterprises",
    ),
    
    # CGT Rate
    TaxRuleVersion(
        rule_type=RuleType.CGT_RATE,
        rule_key="standard_rate",
        value=Decimal("10"),
        effective_from=date(1967, 1, 1),
        effective_to=None,
        legal_reference="CGT Act S.2",
        description="Capital Gains Tax rate of 10%",
    ),
]


class ComplianceReplayEngine:
    """
    Audit Time Machine for point-in-time tax calculation reconstruction.
    
    Enables auditors to:
    - Query tax rules as they existed at any historical date
    - Reconstruct calculations for any past period
    - Compare current vs historical rule applications
    - Provide evidence for audit defense
    """
    
    def __init__(self, db: AsyncSession = None):
        self.db = db
        self.rules_registry = TAX_RULES_REGISTRY
        self._snapshots: Dict[str, ReplaySnapshot] = {}
    
    def get_effective_rules(
        self,
        rule_type: RuleType,
        as_of_date: date,
    ) -> List[TaxRuleVersion]:
        """
        Get all rules of a specific type effective on a given date.
        """
        return [
            rule for rule in self.rules_registry
            if rule.rule_type == rule_type and rule.is_effective_on(as_of_date)
        ]
    
    def get_rule_value(
        self,
        rule_type: RuleType,
        rule_key: str,
        as_of_date: date,
    ) -> Optional[Any]:
        """Get the value of a specific rule on a given date."""
        for rule in self.rules_registry:
            if (rule.rule_type == rule_type 
                and rule.rule_key == rule_key 
                and rule.is_effective_on(as_of_date)):
                return rule.value
        return None
    
    def get_paye_bands(self, as_of_date: date) -> List[Dict[str, Any]]:
        """Get PAYE tax bands effective on a specific date."""
        rules = self.get_effective_rules(RuleType.PAYE_BAND, as_of_date)
        bands = []
        for rule in sorted(rules, key=lambda r: r.value.get("lower", 0)):
            bands.append({
                "lower": rule.value["lower"],
                "upper": rule.value["upper"],
                "rate": rule.value["rate"],
                "legal_reference": rule.legal_reference,
                "description": rule.description,
            })
        return bands
    
    def get_vat_rate(self, as_of_date: date) -> Decimal:
        """Get VAT rate effective on a specific date."""
        rate = self.get_rule_value(RuleType.VAT_RATE, "standard_rate", as_of_date)
        return rate if rate else Decimal("7.5")
    
    def get_cit_rate(self, as_of_date: date, company_size: str) -> Decimal:
        """Get CIT rate for a company size on a specific date."""
        size_key = f"{company_size.lower()}_company"
        rate = self.get_rule_value(RuleType.CIT_RATE, size_key, as_of_date)
        return rate if rate else Decimal("30")
    
    def replay_paye_calculation(
        self,
        entity_id: uuid.UUID,
        gross_annual_income: float,
        calculation_date: date,
        pension_percentage: float = 8.0,
    ) -> Dict[str, Any]:
        """
        Replay PAYE calculation as it would have been computed on a specific date.
        
        Uses tax bands and rules that were effective on that date.
        """
        gross = Decimal(str(gross_annual_income))
        bands = self.get_paye_bands(calculation_date)
        
        # Get CRA rules for the date
        cra_fixed = self.get_rule_value(RuleType.RELIEF_AMOUNT, "cra_fixed", calculation_date)
        cra_pct = self.get_rule_value(RuleType.RELIEF_AMOUNT, "cra_percentage", calculation_date)
        
        if not cra_fixed:
            cra_fixed = Decimal("200000")
        if not cra_pct:
            cra_pct = Decimal("20")
        
        # Calculate CRA
        cra = max(cra_fixed, gross * Decimal("0.01")) + (gross * cra_pct / 100)
        
        # Calculate pension relief
        pension_relief = gross * Decimal(str(pension_percentage)) / 100
        
        # Calculate taxable income
        taxable = max(Decimal("0"), gross - cra - pension_relief)
        
        # Apply tax bands
        total_tax = Decimal("0")
        band_breakdown = []
        
        for band in bands:
            lower = Decimal(str(band["lower"]))
            upper = Decimal(str(band["upper"])) if band["upper"] else None
            rate = Decimal(str(band["rate"]))
            
            if taxable <= lower:
                tax_in_band = Decimal("0")
            elif upper is None:
                tax_in_band = (taxable - lower) * (rate / 100)
            else:
                taxable_in_band = min(taxable, upper) - lower
                tax_in_band = max(Decimal("0"), taxable_in_band) * (rate / 100)
            
            if tax_in_band > 0 or taxable > lower:
                band_breakdown.append({
                    "range": f"NGN {lower:,.0f} - {'Unlimited' if upper is None else f'NGN {upper:,.0f}'}",
                    "rate": f"{rate}%",
                    "tax_amount": float(tax_in_band),
                    "legal_reference": band["legal_reference"],
                })
            
            total_tax += tax_in_band
        
        effective_rate = (total_tax / gross * 100) if gross > 0 else Decimal("0")
        
        # Create snapshot
        snapshot = self._create_snapshot(
            entity_id=entity_id,
            snapshot_date=calculation_date,
            tax_type="paye",
            inputs={
                "gross_annual_income": float(gross),
                "pension_percentage": pension_percentage,
            },
            outputs={
                "consolidated_relief": float(cra),
                "pension_relief": float(pension_relief),
                "taxable_income": float(taxable),
                "annual_tax": float(total_tax),
                "monthly_tax": float(total_tax / 12),
                "effective_rate": float(effective_rate),
            },
            rules_applied=band_breakdown,
        )
        
        return {
            "replay_date": calculation_date.isoformat(),
            "calculation_type": "PAYE",
            "inputs": {
                "gross_annual_income": float(gross),
                "pension_percentage": pension_percentage,
            },
            "reliefs": {
                "consolidated_relief": float(cra),
                "pension_relief": float(pension_relief),
                "total_reliefs": float(cra + pension_relief),
            },
            "taxable_income": float(taxable),
            "annual_tax": float(total_tax),
            "monthly_tax": float(total_tax / 12),
            "effective_rate": float(effective_rate),
            "tax_bands_applied": band_breakdown,
            "snapshot_id": snapshot.snapshot_id,
            "hash_signature": snapshot.hash_signature,
        }
    
    def replay_vat_calculation(
        self,
        entity_id: uuid.UUID,
        sales_amount: float,
        purchases_amount: float,
        calculation_date: date,
        wren_compliant_pct: float = 100.0,
    ) -> Dict[str, Any]:
        """
        Replay VAT calculation using rates effective on a specific date.
        """
        vat_rate = self.get_vat_rate(calculation_date)
        
        sales = Decimal(str(sales_amount))
        purchases = Decimal(str(purchases_amount))
        wren_factor = Decimal(str(wren_compliant_pct)) / 100
        
        output_vat = sales * (vat_rate / 100)
        total_input_vat = purchases * (vat_rate / 100)
        recoverable_input_vat = total_input_vat * wren_factor
        net_vat = output_vat - recoverable_input_vat
        
        # Get legal reference for the rate
        vat_rules = self.get_effective_rules(RuleType.VAT_RATE, calculation_date)
        legal_ref = vat_rules[0].legal_reference if vat_rules else "VATA S.4"
        
        snapshot = self._create_snapshot(
            entity_id=entity_id,
            snapshot_date=calculation_date,
            tax_type="vat",
            inputs={
                "sales_amount": float(sales),
                "purchases_amount": float(purchases),
                "wren_compliant_pct": wren_compliant_pct,
            },
            outputs={
                "vat_rate": float(vat_rate),
                "output_vat": float(output_vat),
                "recoverable_input_vat": float(recoverable_input_vat),
                "net_vat_payable": float(net_vat),
            },
            rules_applied=[{"vat_rate": float(vat_rate), "legal_reference": legal_ref}],
        )
        
        return {
            "replay_date": calculation_date.isoformat(),
            "calculation_type": "VAT",
            "vat_rate_applied": float(vat_rate),
            "vat_rate_legal_reference": legal_ref,
            "inputs": {
                "sales_amount": float(sales),
                "purchases_amount": float(purchases),
                "wren_compliant_percentage": wren_compliant_pct,
            },
            "outputs": {
                "output_vat": float(output_vat),
                "total_input_vat": float(total_input_vat),
                "recoverable_input_vat": float(recoverable_input_vat),
                "non_recoverable_vat": float(total_input_vat - recoverable_input_vat),
                "net_vat_payable": float(net_vat),
            },
            "snapshot_id": snapshot.snapshot_id,
            "hash_signature": snapshot.hash_signature,
        }
    
    def compare_calculations(
        self,
        entity_id: uuid.UUID,
        calculation_type: str,
        date_1: date,
        date_2: date,
        inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Compare how a calculation differs between two dates.
        
        Useful for demonstrating impact of rule changes.
        """
        if calculation_type.lower() == "paye":
            calc_1 = self.replay_paye_calculation(
                entity_id=entity_id,
                gross_annual_income=inputs.get("gross_annual_income", 0),
                calculation_date=date_1,
                pension_percentage=inputs.get("pension_percentage", 8.0),
            )
            calc_2 = self.replay_paye_calculation(
                entity_id=entity_id,
                gross_annual_income=inputs.get("gross_annual_income", 0),
                calculation_date=date_2,
                pension_percentage=inputs.get("pension_percentage", 8.0),
            )
            
            tax_1 = calc_1["annual_tax"]
            tax_2 = calc_2["annual_tax"]
            
        elif calculation_type.lower() == "vat":
            calc_1 = self.replay_vat_calculation(
                entity_id=entity_id,
                sales_amount=inputs.get("sales_amount", 0),
                purchases_amount=inputs.get("purchases_amount", 0),
                calculation_date=date_1,
                wren_compliant_pct=inputs.get("wren_compliant_pct", 100.0),
            )
            calc_2 = self.replay_vat_calculation(
                entity_id=entity_id,
                sales_amount=inputs.get("sales_amount", 0),
                purchases_amount=inputs.get("purchases_amount", 0),
                calculation_date=date_2,
                wren_compliant_pct=inputs.get("wren_compliant_pct", 100.0),
            )
            
            tax_1 = calc_1["outputs"]["net_vat_payable"]
            tax_2 = calc_2["outputs"]["net_vat_payable"]
        else:
            return {"error": f"Unsupported calculation type: {calculation_type}"}
        
        difference = tax_2 - tax_1
        pct_change = (difference / tax_1 * 100) if tax_1 != 0 else 0
        
        return {
            "comparison_type": calculation_type.upper(),
            "date_1": date_1.isoformat(),
            "date_2": date_2.isoformat(),
            "inputs": inputs,
            "result_date_1": calc_1,
            "result_date_2": calc_2,
            "analysis": {
                "tax_on_date_1": tax_1,
                "tax_on_date_2": tax_2,
                "absolute_difference": difference,
                "percentage_change": pct_change,
                "direction": "increase" if difference > 0 else "decrease" if difference < 0 else "no_change",
            },
        }
    
    def get_rule_history(
        self,
        rule_type: RuleType,
        rule_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get the complete history of a rule type.
        
        Useful for audit trail and understanding rule evolution.
        """
        history = []
        for rule in self.rules_registry:
            if rule.rule_type == rule_type:
                if rule_key is None or rule.rule_key == rule_key:
                    history.append({
                        "rule_key": rule.rule_key,
                        "value": rule.value if not isinstance(rule.value, Decimal) else float(rule.value),
                        "effective_from": rule.effective_from.isoformat(),
                        "effective_to": rule.effective_to.isoformat() if rule.effective_to else "Current",
                        "legal_reference": rule.legal_reference,
                        "description": rule.description,
                    })
        
        return sorted(history, key=lambda x: x["effective_from"])
    
    def _create_snapshot(
        self,
        entity_id: uuid.UUID,
        snapshot_date: date,
        tax_type: str,
        inputs: Dict[str, Any],
        outputs: Dict[str, Any],
        rules_applied: List[Dict[str, Any]],
    ) -> ReplaySnapshot:
        """Create a cryptographically signed snapshot of a calculation."""
        # Create hash of the calculation for integrity verification
        hash_input = json.dumps({
            "entity_id": str(entity_id),
            "snapshot_date": snapshot_date.isoformat(),
            "tax_type": tax_type,
            "inputs": inputs,
            "outputs": outputs,
            "rules_applied": rules_applied,
        }, sort_keys=True, default=str)
        
        hash_signature = hashlib.sha256(hash_input.encode()).hexdigest()
        
        snapshot = ReplaySnapshot(
            snapshot_id=str(uuid.uuid4()),
            entity_id=entity_id,
            snapshot_date=snapshot_date,
            created_at=datetime.utcnow(),
            tax_type=tax_type,
            calculation_inputs=inputs,
            calculation_outputs=outputs,
            rules_applied=rules_applied,
            hash_signature=hash_signature,
        )
        
        self._snapshots[snapshot.snapshot_id] = snapshot
        return snapshot
    
    def get_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a stored snapshot by ID."""
        snapshot = self._snapshots.get(snapshot_id)
        return snapshot.to_dict() if snapshot else None
    
    def verify_snapshot(self, snapshot_id: str) -> Dict[str, Any]:
        """Verify integrity of a stored snapshot."""
        snapshot = self._snapshots.get(snapshot_id)
        if not snapshot:
            return {"verified": False, "error": "Snapshot not found"}
        
        # Recalculate hash
        hash_input = json.dumps({
            "entity_id": str(snapshot.entity_id),
            "snapshot_date": snapshot.snapshot_date.isoformat(),
            "tax_type": snapshot.tax_type,
            "inputs": snapshot.calculation_inputs,
            "outputs": snapshot.calculation_outputs,
            "rules_applied": snapshot.rules_applied,
        }, sort_keys=True, default=str)
        
        current_hash = hashlib.sha256(hash_input.encode()).hexdigest()
        
        return {
            "snapshot_id": snapshot_id,
            "verified": current_hash == snapshot.hash_signature,
            "original_hash": snapshot.hash_signature,
            "current_hash": current_hash,
            "created_at": snapshot.created_at.isoformat(),
        }
    
    def list_snapshots(
        self,
        entity_id: Optional[uuid.UUID] = None,
        tax_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List all stored snapshots with optional filtering."""
        results = []
        for snapshot in self._snapshots.values():
            if entity_id and snapshot.entity_id != entity_id:
                continue
            if tax_type and snapshot.tax_type != tax_type:
                continue
            results.append({
                "snapshot_id": snapshot.snapshot_id,
                "entity_id": str(snapshot.entity_id),
                "snapshot_date": snapshot.snapshot_date.isoformat(),
                "tax_type": snapshot.tax_type,
                "created_at": snapshot.created_at.isoformat(),
            })
        return results
