"""
Tekvwa Pro Audit - Minimum ETR & CGT Calculator (2026 Tax Reform)

Implements the 15% Minimum Effective Tax Rate (ETR) for large companies
and Capital Gains Tax at CIT rate (30%) as per the 2026 Nigeria Tax Reform.

Minimum ETR Applicability (Section 57):
- Companies with annual turnover >= ₦50,000,000,000 (₦50 billion)
- Constituents of Multinational Enterprise (MNE) groups with 
  aggregate revenue >= €750,000,000

Capital Gains Tax (2026):
- CGT rate increased from 10% to 30% for large companies
- CGT is now merged with general income tax reporting
- Small companies (turnover <= ₦100M, assets <= ₦250M) are exempt
"""

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


# Threshold constants
MINIMUM_ETR_RATE = Decimal("0.15")  # 15%
TURNOVER_THRESHOLD_NGN = Decimal("50000000000")  # ₦50 billion
MNE_REVENUE_THRESHOLD_EUR = Decimal("750000000")  # €750 million

# CGT rates
CGT_RATE_LARGE = Decimal("0.30")  # 30% for large companies
CGT_RATE_OLD = Decimal("0.10")     # 10% (pre-2026)

# Small company exemption thresholds
SMALL_COMPANY_TURNOVER = Decimal("100000000")  # ₦100 million
SMALL_COMPANY_ASSETS = Decimal("250000000")    # ₦250 million


class CompanyClassification(str, Enum):
    """Company classification for tax purposes."""
    SMALL = "small"              # Exempt from CGT and Development Levy
    MEDIUM = "medium"            # Standard rates apply
    LARGE = "large"              # Subject to 30% CGT
    MNE_CONSTITUENT = "mne_constituent"  # Subject to 15% Minimum ETR


@dataclass
class MinimumETRResult:
    """Result of Minimum ETR calculation."""
    is_subject_to_minimum_etr: bool
    reason: str
    calculated_etr: Decimal
    minimum_etr: Decimal
    etr_shortfall: Decimal
    top_up_tax: Decimal
    regular_tax: Decimal
    total_tax: Decimal
    turnover: Decimal
    assessable_profit: Decimal


@dataclass
class CGTResult:
    """Result of Capital Gains Tax calculation."""
    is_exempt: bool
    exemption_reason: Optional[str]
    asset_cost: Decimal
    sale_proceeds: Decimal
    capital_gain: Decimal
    cgt_rate: Decimal
    cgt_liability: Decimal
    indexation_allowance: Decimal
    net_gain_after_indexation: Decimal


class MinimumETRCalculator:
    """
    Calculator for the 15% Minimum Effective Tax Rate.
    
    Applies to:
    1. Companies with turnover >= ₦50 billion
    2. MNE constituents with group revenue >= €750 million
    
    If a company's ETR is below 15%, they pay a top-up tax to reach 15%.
    """
    
    def __init__(self, eur_to_ngn_rate: Decimal = Decimal("1800")):
        """
        Initialize calculator.
        
        Args:
            eur_to_ngn_rate: Exchange rate for EUR to NGN (default 1800)
        """
        self.eur_to_ngn_rate = eur_to_ngn_rate
    
    def check_minimum_etr_applicability(
        self,
        annual_turnover: Decimal,
        is_mne_constituent: bool = False,
        mne_group_revenue_eur: Optional[Decimal] = None,
    ) -> Tuple[bool, str]:
        """
        Check if company is subject to Minimum ETR.
        
        Args:
            annual_turnover: Annual turnover in NGN
            is_mne_constituent: Whether company is part of an MNE group
            mne_group_revenue_eur: Group revenue in EUR (if MNE)
        
        Returns:
            Tuple of (is_subject, reason)
        """
        # Check turnover threshold
        if annual_turnover >= TURNOVER_THRESHOLD_NGN:
            return True, f"Annual turnover (₦{annual_turnover:,.2f}) >= ₦50 billion threshold"
        
        # Check MNE threshold
        if is_mne_constituent and mne_group_revenue_eur:
            if mne_group_revenue_eur >= MNE_REVENUE_THRESHOLD_EUR:
                return True, f"MNE group revenue (€{mne_group_revenue_eur:,.2f}) >= €750 million threshold"
        
        return False, "Company does not meet Minimum ETR thresholds"
    
    def calculate_minimum_etr(
        self,
        annual_turnover: Decimal,
        assessable_profit: Decimal,
        regular_tax_paid: Decimal,
        is_mne_constituent: bool = False,
        mne_group_revenue_eur: Optional[Decimal] = None,
    ) -> MinimumETRResult:
        """
        Calculate Minimum ETR and any top-up tax required.
        
        Args:
            annual_turnover: Annual turnover in NGN
            assessable_profit: Taxable profit
            regular_tax_paid: CIT and other taxes already calculated
            is_mne_constituent: Whether company is part of an MNE group
            mne_group_revenue_eur: Group revenue in EUR (if MNE)
        
        Returns:
            MinimumETRResult with calculation details
        """
        # Check applicability
        is_subject, reason = self.check_minimum_etr_applicability(
            annual_turnover, is_mne_constituent, mne_group_revenue_eur
        )
        
        if not is_subject:
            return MinimumETRResult(
                is_subject_to_minimum_etr=False,
                reason=reason,
                calculated_etr=Decimal("0"),
                minimum_etr=MINIMUM_ETR_RATE,
                etr_shortfall=Decimal("0"),
                top_up_tax=Decimal("0"),
                regular_tax=regular_tax_paid,
                total_tax=regular_tax_paid,
                turnover=annual_turnover,
                assessable_profit=assessable_profit,
            )
        
        # Calculate ETR
        if assessable_profit <= 0:
            calculated_etr = Decimal("0")
        else:
            calculated_etr = regular_tax_paid / assessable_profit
        
        # Calculate shortfall and top-up
        if calculated_etr >= MINIMUM_ETR_RATE:
            etr_shortfall = Decimal("0")
            top_up_tax = Decimal("0")
        else:
            etr_shortfall = MINIMUM_ETR_RATE - calculated_etr
            # Top-up tax brings ETR up to 15%
            top_up_tax = max(Decimal("0"), (MINIMUM_ETR_RATE * assessable_profit) - regular_tax_paid)
        
        total_tax = regular_tax_paid + top_up_tax
        
        return MinimumETRResult(
            is_subject_to_minimum_etr=True,
            reason=reason,
            calculated_etr=calculated_etr,
            minimum_etr=MINIMUM_ETR_RATE,
            etr_shortfall=etr_shortfall,
            top_up_tax=round(top_up_tax, 2),
            regular_tax=regular_tax_paid,
            total_tax=round(total_tax, 2),
            turnover=annual_turnover,
            assessable_profit=assessable_profit,
        )
    
    def format_result(self, result: MinimumETRResult) -> Dict[str, Any]:
        """Format result for API response."""
        return {
            "is_subject_to_minimum_etr": result.is_subject_to_minimum_etr,
            "reason": result.reason,
            "calculated_etr_percentage": f"{float(result.calculated_etr) * 100:.2f}%",
            "minimum_etr_percentage": f"{float(result.minimum_etr) * 100:.2f}%",
            "etr_shortfall_percentage": f"{float(result.etr_shortfall) * 100:.2f}%",
            "top_up_tax": float(result.top_up_tax),
            "regular_tax": float(result.regular_tax),
            "total_tax": float(result.total_tax),
            "turnover": float(result.turnover),
            "assessable_profit": float(result.assessable_profit),
            "compliance_note": (
                "Company meets 15% Minimum ETR requirement"
                if result.calculated_etr >= MINIMUM_ETR_RATE
                else f"Company must pay ₦{result.top_up_tax:,.2f} top-up tax to meet 15% Minimum ETR"
            ) if result.is_subject_to_minimum_etr else "Company not subject to Minimum ETR",
        }


class CGTCalculator:
    """
    Calculator for Capital Gains Tax under 2026 Tax Reform.
    
    Key Changes:
    - CGT rate increased from 10% to 30% for large companies
    - CGT is merged with CIT reporting
    - Small companies are exempt
    - Indexation allowance available
    """
    
    def classify_company(
        self,
        annual_turnover: Decimal,
        fixed_assets_value: Decimal,
    ) -> CompanyClassification:
        """
        Classify company for CGT purposes.
        
        Args:
            annual_turnover: Annual turnover in NGN
            fixed_assets_value: Total fixed assets value in NGN
        
        Returns:
            CompanyClassification
        """
        # Small company: turnover <= ₦100M AND assets <= ₦250M
        if annual_turnover <= SMALL_COMPANY_TURNOVER and fixed_assets_value <= SMALL_COMPANY_ASSETS:
            return CompanyClassification.SMALL
        
        # Large company: turnover > ₦100M OR assets > ₦250M
        return CompanyClassification.LARGE
    
    def calculate_indexation_allowance(
        self,
        acquisition_cost: Decimal,
        acquisition_date: date,
        disposal_date: date,
        average_inflation_rate: Decimal = Decimal("0.15"),  # 15% average
    ) -> Decimal:
        """
        Calculate indexation allowance to adjust for inflation.
        
        Args:
            acquisition_cost: Original cost of asset
            acquisition_date: Date of acquisition
            disposal_date: Date of disposal
            average_inflation_rate: Average annual inflation rate
        
        Returns:
            Indexation allowance amount
        """
        years_held = (disposal_date - acquisition_date).days / 365.25
        if years_held <= 0:
            return Decimal("0")
        
        # Compound inflation adjustment
        inflation_factor = (1 + average_inflation_rate) ** Decimal(str(years_held))
        indexed_cost = acquisition_cost * inflation_factor
        
        return round(indexed_cost - acquisition_cost, 2)
    
    def calculate_cgt(
        self,
        asset_cost: Decimal,
        sale_proceeds: Decimal,
        annual_turnover: Decimal,
        fixed_assets_value: Decimal,
        acquisition_date: Optional[date] = None,
        disposal_date: Optional[date] = None,
        apply_indexation: bool = True,
    ) -> CGTResult:
        """
        Calculate Capital Gains Tax on asset disposal.
        
        Args:
            asset_cost: Original cost of the asset
            sale_proceeds: Proceeds from sale
            annual_turnover: Company's annual turnover
            fixed_assets_value: Company's total fixed assets value
            acquisition_date: Date asset was acquired
            disposal_date: Date asset was disposed
            apply_indexation: Whether to apply indexation allowance
        
        Returns:
            CGTResult with calculation details
        """
        # Classify company
        classification = self.classify_company(annual_turnover, fixed_assets_value)
        
        # Check small company exemption
        if classification == CompanyClassification.SMALL:
            return CGTResult(
                is_exempt=True,
                exemption_reason="Small company exemption: Turnover ≤ ₦100M and Fixed Assets ≤ ₦250M",
                asset_cost=asset_cost,
                sale_proceeds=sale_proceeds,
                capital_gain=sale_proceeds - asset_cost,
                cgt_rate=Decimal("0"),
                cgt_liability=Decimal("0"),
                indexation_allowance=Decimal("0"),
                net_gain_after_indexation=sale_proceeds - asset_cost,
            )
        
        # Calculate capital gain
        capital_gain = sale_proceeds - asset_cost
        
        if capital_gain <= 0:
            # Capital loss
            return CGTResult(
                is_exempt=False,
                exemption_reason=None,
                asset_cost=asset_cost,
                sale_proceeds=sale_proceeds,
                capital_gain=capital_gain,
                cgt_rate=CGT_RATE_LARGE,
                cgt_liability=Decimal("0"),
                indexation_allowance=Decimal("0"),
                net_gain_after_indexation=capital_gain,
            )
        
        # Calculate indexation allowance if applicable
        indexation_allowance = Decimal("0")
        if apply_indexation and acquisition_date and disposal_date:
            indexation_allowance = self.calculate_indexation_allowance(
                asset_cost, acquisition_date, disposal_date
            )
        
        # Net gain after indexation
        net_gain = capital_gain - indexation_allowance
        if net_gain < 0:
            net_gain = Decimal("0")
        
        # CGT at 30% for large companies
        cgt_liability = net_gain * CGT_RATE_LARGE
        
        return CGTResult(
            is_exempt=False,
            exemption_reason=None,
            asset_cost=asset_cost,
            sale_proceeds=sale_proceeds,
            capital_gain=capital_gain,
            cgt_rate=CGT_RATE_LARGE,
            cgt_liability=round(cgt_liability, 2),
            indexation_allowance=indexation_allowance,
            net_gain_after_indexation=net_gain,
        )
    
    def format_result(self, result: CGTResult) -> Dict[str, Any]:
        """Format result for API response."""
        return {
            "is_exempt": result.is_exempt,
            "exemption_reason": result.exemption_reason,
            "asset_cost": float(result.asset_cost),
            "sale_proceeds": float(result.sale_proceeds),
            "capital_gain": float(result.capital_gain),
            "cgt_rate_percentage": f"{float(result.cgt_rate) * 100:.0f}%",
            "cgt_liability": float(result.cgt_liability),
            "indexation_allowance": float(result.indexation_allowance),
            "net_gain_after_indexation": float(result.net_gain_after_indexation),
            "note": (
                result.exemption_reason if result.is_exempt
                else f"CGT of ₦{result.cgt_liability:,.2f} due at {float(result.cgt_rate) * 100:.0f}% rate"
                if result.cgt_liability > 0
                else "No CGT due (capital loss or no gain)"
            ),
        }


class ZeroRatedVATTracker:
    """
    Tracker for zero-rated VAT and input VAT refund claims.
    
    2026 Reform:
    - Essential goods (food, education, healthcare) are zero-rated, not exempt
    - Suppliers of zero-rated goods can claim input VAT refunds
    """
    
    # Zero-rated categories
    ZERO_RATED_CATEGORIES = [
        "basic_food",           # Basic food items
        "educational_materials", # Books, educational supplies
        "medical_supplies",     # Medical equipment, drugs
        "exported_goods",       # Exports
        "agricultural_inputs",  # Seeds, fertilizers
        "baby_products",        # Baby food, diapers, etc.
    ]
    
    def __init__(self):
        self.zero_rated_sales = []
        self.input_vat_paid = []
    
    def record_zero_rated_sale(
        self,
        sale_amount: Decimal,
        category: str,
        date: date,
        description: str,
    ) -> Dict[str, Any]:
        """Record a zero-rated sale for VAT refund tracking."""
        record = {
            "amount": sale_amount,
            "vat_rate": Decimal("0"),
            "vat_amount": Decimal("0"),
            "category": category,
            "date": date,
            "description": description,
            "is_zero_rated": True,
            "refund_eligible": True,
        }
        self.zero_rated_sales.append(record)
        return record
    
    def record_input_vat(
        self,
        purchase_amount: Decimal,
        vat_amount: Decimal,
        date: date,
        vendor_tin: str,
        vendor_irn: Optional[str] = None,
        description: str = "",
    ) -> Dict[str, Any]:
        """Record input VAT for potential refund."""
        record = {
            "purchase_amount": purchase_amount,
            "vat_amount": vat_amount,
            "date": date,
            "vendor_tin": vendor_tin,
            "vendor_irn": vendor_irn,
            "description": description,
            "has_valid_irn": bool(vendor_irn),
            "refund_eligible": bool(vendor_irn),  # Only with valid IRN
        }
        self.input_vat_paid.append(record)
        return record
    
    def calculate_refund_claim(self) -> Dict[str, Any]:
        """
        Calculate VAT refund claim.
        
        Zero-rated suppliers can claim back input VAT paid on purchases.
        """
        total_zero_rated_sales = sum(s["amount"] for s in self.zero_rated_sales)
        total_input_vat = sum(p["vat_amount"] for p in self.input_vat_paid)
        
        # Only refundable if there's evidence (IRN)
        refundable_input_vat = sum(
            p["vat_amount"] for p in self.input_vat_paid 
            if p["refund_eligible"]
        )
        non_refundable_vat = total_input_vat - refundable_input_vat
        
        return {
            "total_zero_rated_sales": float(total_zero_rated_sales),
            "total_input_vat_paid": float(total_input_vat),
            "refundable_input_vat": float(refundable_input_vat),
            "non_refundable_vat": float(non_refundable_vat),
            "refund_claim_amount": float(refundable_input_vat),
            "zero_rated_transactions": len(self.zero_rated_sales),
            "input_transactions": len(self.input_vat_paid),
            "note": (
                "Zero-rated suppliers can claim input VAT refund. "
                "Only purchases with valid NRS IRN are eligible for refund."
            ),
        }


# Factory functions
def get_minimum_etr_calculator() -> MinimumETRCalculator:
    """Get Minimum ETR calculator instance."""
    return MinimumETRCalculator()


def get_cgt_calculator() -> CGTCalculator:
    """Get CGT calculator instance."""
    return CGTCalculator()


def get_zero_rated_vat_tracker() -> ZeroRatedVATTracker:
    """Get zero-rated VAT tracker instance."""
    return ZeroRatedVATTracker()
