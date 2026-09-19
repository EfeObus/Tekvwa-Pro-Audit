"""
Tekvwa Pro Audit - Audit Explainability Service

This module provides comprehensive explainability for all tax calculations,
ensuring every computed figure has:
- Human-readable explanation
- Machine-parseable breakdown
- Legal references (Nigerian Tax Law sections)
- Step-by-step calculation methodology

Supports: PAYE, VAT, WHT, CIT, ETR, and CGT calculations.
"""

import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession


class TaxType(str, Enum):
    """Supported tax types for explainability."""
    PAYE = "paye"
    VAT = "vat"
    WHT = "wht"
    CIT = "cit"
    ETR = "etr"
    CGT = "cgt"


@dataclass
class LegalReference:
    """Legal reference for a tax provision."""
    act: str
    section: str
    subsection: Optional[str] = None
    schedule: Optional[str] = None
    description: str = ""
    effective_date: Optional[date] = None
    
    def to_citation(self) -> str:
        """Generate formal legal citation."""
        citation = f"{self.act}, Section {self.section}"
        if self.subsection:
            citation += f"({self.subsection})"
        if self.schedule:
            citation += f", {self.schedule}"
        return citation


@dataclass
class CalculationStep:
    """Single step in a tax calculation."""
    step_number: int
    description: str
    formula: str
    inputs: Dict[str, Any]
    result: Decimal
    legal_reference: Optional[LegalReference] = None
    notes: Optional[str] = None


@dataclass
class TaxExplanation:
    """Complete explanation for a tax calculation."""
    tax_type: TaxType
    entity_id: uuid.UUID
    calculation_date: datetime
    period_start: date
    period_end: date
    gross_amount: Decimal
    final_tax_amount: Decimal
    effective_rate: Decimal
    steps: List[CalculationStep] = field(default_factory=list)
    summary: str = ""
    assumptions: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    legal_references: List[LegalReference] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "tax_type": self.tax_type.value,
            "entity_id": str(self.entity_id),
            "calculation_date": self.calculation_date.isoformat(),
            "period": {
                "start": self.period_start.isoformat(),
                "end": self.period_end.isoformat(),
            },
            "gross_amount": float(self.gross_amount),
            "final_tax_amount": float(self.final_tax_amount),
            "effective_rate": float(self.effective_rate),
            "summary": self.summary,
            "steps": [
                {
                    "step_number": s.step_number,
                    "description": s.description,
                    "formula": s.formula,
                    "inputs": {k: float(v) if isinstance(v, Decimal) else v for k, v in s.inputs.items()},
                    "result": float(s.result),
                    "legal_reference": s.legal_reference.to_citation() if s.legal_reference else None,
                    "notes": s.notes,
                }
                for s in self.steps
            ],
            "assumptions": self.assumptions,
            "warnings": self.warnings,
            "legal_references": [
                {
                    "citation": ref.to_citation(),
                    "description": ref.description,
                }
                for ref in self.legal_references
            ],
        }


# Nigeria Tax Law Legal References
NIGERIA_TAX_LAWS = {
    "pita": "Personal Income Tax Act (PITA)",
    "cita": "Companies Income Tax Act (CITA)",
    "vata": "Value Added Tax Act (VATA)",
    "fira": "Finance Act 2026",
    "nfa_2020": "Nigeria Finance Act 2020",
    "nfa_2021": "Nigeria Finance Act 2021",
    "nfa_2026": "Nigeria Finance Act 2026",
}

# PAYE Legal References (2026)
PAYE_LEGAL_REFS = {
    "cra": LegalReference(
        act=NIGERIA_TAX_LAWS["pita"],
        section="33",
        subsection="1",
        description="Consolidated Relief Allowance: NGN 200,000 or 1% of gross income (higher) plus 20% of gross income",
        effective_date=date(2011, 1, 1),
    ),
    "tax_bands": LegalReference(
        act=NIGERIA_TAX_LAWS["pita"],
        section="37",
        subsection="2",
        schedule="Sixth Schedule",
        description="Progressive PAYE tax rates and bands as amended by Finance Act 2026",
        effective_date=date(2026, 1, 1),
    ),
    "pension_relief": LegalReference(
        act="Pension Reform Act 2014",
        section="9",
        subsection="1",
        description="Employee pension contribution (up to 8%) exempt from income tax",
        effective_date=date(2014, 7, 1),
    ),
    "nhf": LegalReference(
        act="National Housing Fund Act",
        section="4",
        description="NHF contribution of 2.5% of basic salary is tax-deductible",
        effective_date=date(1992, 1, 1),
    ),
}

# VAT Legal References (2026)
VAT_LEGAL_REFS = {
    "standard_rate": LegalReference(
        act=NIGERIA_TAX_LAWS["vata"],
        section="4",
        subsection="1",
        description="Standard VAT rate of 7.5% on taxable goods and services",
        effective_date=date(2020, 2, 1),
    ),
    "zero_rated": LegalReference(
        act=NIGERIA_TAX_LAWS["vata"],
        section="3",
        schedule="First Schedule",
        description="Zero-rated goods and services including exports",
        effective_date=date(2020, 2, 1),
    ),
    "exempt": LegalReference(
        act=NIGERIA_TAX_LAWS["vata"],
        section="3",
        schedule="Second Schedule",
        description="VAT exempt goods and services",
        effective_date=date(2020, 2, 1),
    ),
    "input_vat": LegalReference(
        act=NIGERIA_TAX_LAWS["vata"],
        section="10",
        subsection="1",
        description="Input VAT on WREN-compliant expenses is recoverable",
        effective_date=date(2020, 2, 1),
    ),
    "registration": LegalReference(
        act=NIGERIA_TAX_LAWS["vata"],
        section="8",
        description="Mandatory VAT registration for taxable persons",
        effective_date=date(1993, 1, 1),
    ),
}

# WHT Legal References (2026)
WHT_LEGAL_REFS = {
    "rates": LegalReference(
        act=NIGERIA_TAX_LAWS["cita"],
        section="77",
        description="Withholding tax rates for various payment categories",
        effective_date=date(1979, 1, 1),
    ),
    "dividends": LegalReference(
        act=NIGERIA_TAX_LAWS["cita"],
        section="78",
        description="WHT on dividends at 10%",
        effective_date=date(1979, 1, 1),
    ),
    "contracts": LegalReference(
        act=NIGERIA_TAX_LAWS["cita"],
        section="79",
        description="WHT on contracts at 5%",
        effective_date=date(1979, 1, 1),
    ),
}

# CIT Legal References (2026)
CIT_LEGAL_REFS = {
    "standard_rate": LegalReference(
        act=NIGERIA_TAX_LAWS["cita"],
        section="40",
        subsection="1",
        description="Standard CIT rate of 30% for large companies",
        effective_date=date(2020, 1, 1),
    ),
    "medium_rate": LegalReference(
        act=NIGERIA_TAX_LAWS["cita"],
        section="40",
        subsection="2",
        description="CIT rate of 20% for medium companies (turnover NGN 25M - 100M)",
        effective_date=date(2020, 1, 1),
    ),
    "small_rate": LegalReference(
        act=NIGERIA_TAX_LAWS["cita"],
        section="40",
        subsection="3",
        description="CIT rate of 0% for small companies (turnover below NGN 25M)",
        effective_date=date(2020, 1, 1),
    ),
    "minimum_tax": LegalReference(
        act=NIGERIA_TAX_LAWS["cita"],
        section="33",
        description="Minimum tax of 0.5% of gross turnover",
        effective_date=date(2020, 1, 1),
    ),
    "etr_2026": LegalReference(
        act=NIGERIA_TAX_LAWS["nfa_2026"],
        section="12",
        description="Minimum Effective Tax Rate of 15% for qualifying companies",
        effective_date=date(2026, 1, 1),
    ),
}


class PAYEExplainability:
    """Generates detailed explanations for PAYE calculations."""
    
    # 2026 Tax Bands
    TAX_BANDS = [
        {"lower": 0, "upper": 800000, "rate": 0, "name": "Tax-Free Band"},
        {"lower": 800000, "upper": 2400000, "rate": 15, "name": "First Taxable Band"},
        {"lower": 2400000, "upper": 4800000, "rate": 20, "name": "Second Taxable Band"},
        {"lower": 4800000, "upper": 7200000, "rate": 25, "name": "Third Taxable Band"},
        {"lower": 7200000, "upper": None, "rate": 30, "name": "Top Rate Band"},
    ]
    
    @classmethod
    def explain_calculation(
        cls,
        entity_id: uuid.UUID,
        gross_annual_income: Decimal,
        basic_salary: Optional[Decimal] = None,
        pension_percentage: Decimal = Decimal("8"),
        nhf_contribution: Optional[Decimal] = None,
        other_reliefs: Decimal = Decimal("0"),
        period_year: int = 2026,
    ) -> TaxExplanation:
        """
        Generate comprehensive explanation for PAYE calculation.
        
        Provides step-by-step breakdown with legal references.
        """
        steps = []
        legal_refs = []
        assumptions = []
        warnings = []
        step_num = 0
        
        # Derive basic salary if not provided
        if basic_salary is None:
            basic_salary = gross_annual_income * Decimal("0.6")
            assumptions.append("Basic salary assumed as 60% of gross income (industry standard)")
        
        # Step 1: Gross Income
        step_num += 1
        steps.append(CalculationStep(
            step_number=step_num,
            description="Determine Gross Annual Income",
            formula="Gross Annual Income = Sum of all taxable earnings",
            inputs={"gross_annual_income": gross_annual_income},
            result=gross_annual_income,
            legal_reference=LegalReference(
                act=NIGERIA_TAX_LAWS["pita"],
                section="3",
                description="Definition of gross income for PAYE purposes",
            ),
        ))
        
        # Step 2: Calculate CRA
        step_num += 1
        cra_fixed = max(Decimal("200000"), gross_annual_income * Decimal("0.01"))
        cra_variable = gross_annual_income * Decimal("0.20")
        cra_total = cra_fixed + cra_variable
        
        steps.append(CalculationStep(
            step_number=step_num,
            description="Calculate Consolidated Relief Allowance (CRA)",
            formula="CRA = Higher of (NGN 200,000 or 1% of Gross) + 20% of Gross",
            inputs={
                "fixed_relief": cra_fixed,
                "percentage_relief": cra_variable,
            },
            result=cra_total,
            legal_reference=PAYE_LEGAL_REFS["cra"],
            notes=f"Fixed relief: NGN {cra_fixed:,.2f} (higher of 200,000 or 1%); Variable: NGN {cra_variable:,.2f}",
        ))
        legal_refs.append(PAYE_LEGAL_REFS["cra"])
        
        # Step 3: Pension Contribution Relief
        step_num += 1
        pension_relief = gross_annual_income * (pension_percentage / 100)
        steps.append(CalculationStep(
            step_number=step_num,
            description="Calculate Pension Contribution Relief",
            formula="Pension Relief = Gross Income x Pension Rate (max 8%)",
            inputs={
                "gross_income": gross_annual_income,
                "pension_rate": pension_percentage,
            },
            result=pension_relief,
            legal_reference=PAYE_LEGAL_REFS["pension_relief"],
            notes=f"Employee contributes {pension_percentage}% to pension fund",
        ))
        legal_refs.append(PAYE_LEGAL_REFS["pension_relief"])
        
        # Step 4: NHF Contribution Relief
        step_num += 1
        if nhf_contribution is None:
            nhf_contribution = basic_salary * Decimal("0.025")
        steps.append(CalculationStep(
            step_number=step_num,
            description="Calculate National Housing Fund (NHF) Relief",
            formula="NHF Relief = Basic Salary x 2.5%",
            inputs={
                "basic_salary": basic_salary,
                "nhf_rate": Decimal("2.5"),
            },
            result=nhf_contribution,
            legal_reference=PAYE_LEGAL_REFS["nhf"],
        ))
        legal_refs.append(PAYE_LEGAL_REFS["nhf"])
        
        # Step 5: Total Reliefs
        step_num += 1
        total_reliefs = cra_total + pension_relief + nhf_contribution + other_reliefs
        steps.append(CalculationStep(
            step_number=step_num,
            description="Calculate Total Tax Reliefs",
            formula="Total Reliefs = CRA + Pension + NHF + Other Reliefs",
            inputs={
                "cra": cra_total,
                "pension": pension_relief,
                "nhf": nhf_contribution,
                "other": other_reliefs,
            },
            result=total_reliefs,
        ))
        
        # Step 6: Taxable Income
        step_num += 1
        taxable_income = max(Decimal("0"), gross_annual_income - total_reliefs)
        steps.append(CalculationStep(
            step_number=step_num,
            description="Calculate Taxable Income",
            formula="Taxable Income = Gross Income - Total Reliefs",
            inputs={
                "gross_income": gross_annual_income,
                "total_reliefs": total_reliefs,
            },
            result=taxable_income,
            notes="Taxable income cannot be negative",
        ))
        
        # Step 7: Apply Progressive Tax Bands
        step_num += 1
        total_tax = Decimal("0")
        band_results = []
        
        for band in cls.TAX_BANDS:
            lower = Decimal(str(band["lower"]))
            upper = Decimal(str(band["upper"])) if band["upper"] else None
            rate = Decimal(str(band["rate"]))
            
            if taxable_income <= lower:
                tax_in_band = Decimal("0")
            elif upper is None:
                tax_in_band = (taxable_income - lower) * (rate / 100)
            else:
                taxable_in_band = min(taxable_income, upper) - lower
                tax_in_band = max(Decimal("0"), taxable_in_band) * (rate / 100)
            
            band_results.append({
                "band": band["name"],
                "range": f"NGN {lower:,.0f} - {'No Limit' if upper is None else f'NGN {upper:,.0f}'}",
                "rate": f"{rate}%",
                "tax_amount": tax_in_band,
            })
            total_tax += tax_in_band
        
        steps.append(CalculationStep(
            step_number=step_num,
            description="Apply Progressive Tax Bands",
            formula="Tax = Sum of (Income in each band x Band Rate)",
            inputs={
                "taxable_income": taxable_income,
                "bands_applied": [b["band"] for b in band_results if b["tax_amount"] > 0],
            },
            result=total_tax,
            legal_reference=PAYE_LEGAL_REFS["tax_bands"],
            notes=f"Income taxed across {len([b for b in band_results if b['tax_amount'] > 0])} bands",
        ))
        legal_refs.append(PAYE_LEGAL_REFS["tax_bands"])
        
        # Step 8: Calculate Monthly Tax
        step_num += 1
        monthly_tax = total_tax / 12
        steps.append(CalculationStep(
            step_number=step_num,
            description="Calculate Monthly PAYE Deduction",
            formula="Monthly PAYE = Annual Tax / 12",
            inputs={"annual_tax": total_tax},
            result=monthly_tax,
            notes="Monthly amount to be remitted to tax authority",
        ))
        
        # Calculate effective rate
        effective_rate = (total_tax / gross_annual_income * 100) if gross_annual_income > 0 else Decimal("0")
        
        # Build summary
        summary = (
            f"PAYE Calculation for {period_year}: "
            f"Gross Annual Income of NGN {gross_annual_income:,.2f} "
            f"yields taxable income of NGN {taxable_income:,.2f} after reliefs of NGN {total_reliefs:,.2f}. "
            f"Annual PAYE tax is NGN {total_tax:,.2f} (effective rate: {effective_rate:.2f}%), "
            f"resulting in monthly deduction of NGN {monthly_tax:,.2f}."
        )
        
        return TaxExplanation(
            tax_type=TaxType.PAYE,
            entity_id=entity_id,
            calculation_date=datetime.utcnow(),
            period_start=date(period_year, 1, 1),
            period_end=date(period_year, 12, 31),
            gross_amount=gross_annual_income,
            final_tax_amount=total_tax,
            effective_rate=effective_rate,
            steps=steps,
            summary=summary,
            assumptions=assumptions,
            warnings=warnings,
            legal_references=legal_refs,
        )


class VATExplainability:
    """Generates detailed explanations for VAT calculations."""
    
    STANDARD_RATE = Decimal("7.5")
    
    @classmethod
    def explain_calculation(
        cls,
        entity_id: uuid.UUID,
        output_vat_base: Decimal,
        input_vat_base: Decimal,
        wren_compliant_input: Decimal,
        non_compliant_input: Decimal,
        period_month: int,
        period_year: int,
        zero_rated_sales: Decimal = Decimal("0"),
        exempt_sales: Decimal = Decimal("0"),
    ) -> TaxExplanation:
        """
        Generate comprehensive explanation for VAT calculation.
        """
        steps = []
        legal_refs = []
        assumptions = []
        warnings = []
        step_num = 0
        
        # Step 1: Determine Output VAT
        step_num += 1
        output_vat = output_vat_base * (cls.STANDARD_RATE / 100)
        steps.append(CalculationStep(
            step_number=step_num,
            description="Calculate Output VAT (on Sales)",
            formula="Output VAT = Taxable Sales x VAT Rate (7.5%)",
            inputs={
                "taxable_sales": output_vat_base,
                "vat_rate": cls.STANDARD_RATE,
            },
            result=output_vat,
            legal_reference=VAT_LEGAL_REFS["standard_rate"],
            notes=f"VAT charged on taxable goods and services sold",
        ))
        legal_refs.append(VAT_LEGAL_REFS["standard_rate"])
        
        # Step 2: Zero-Rated Sales
        if zero_rated_sales > 0:
            step_num += 1
            steps.append(CalculationStep(
                step_number=step_num,
                description="Zero-Rated Sales (0% VAT applies)",
                formula="Zero-Rated VAT = Zero-Rated Sales x 0%",
                inputs={"zero_rated_sales": zero_rated_sales},
                result=Decimal("0"),
                legal_reference=VAT_LEGAL_REFS["zero_rated"],
                notes="Exports and specified goods attract 0% VAT but remain in VAT system",
            ))
            legal_refs.append(VAT_LEGAL_REFS["zero_rated"])
        
        # Step 3: Exempt Sales
        if exempt_sales > 0:
            step_num += 1
            steps.append(CalculationStep(
                step_number=step_num,
                description="Exempt Sales (Outside VAT System)",
                formula="No VAT on exempt supplies",
                inputs={"exempt_sales": exempt_sales},
                result=Decimal("0"),
                legal_reference=VAT_LEGAL_REFS["exempt"],
                notes="Medical, educational, and specified services are VAT-exempt",
            ))
            legal_refs.append(VAT_LEGAL_REFS["exempt"])
        
        # Step 4: Calculate Total Input VAT
        step_num += 1
        total_input_vat = input_vat_base * (cls.STANDARD_RATE / 100)
        steps.append(CalculationStep(
            step_number=step_num,
            description="Calculate Total Input VAT (on Purchases)",
            formula="Total Input VAT = Total Purchases x VAT Rate",
            inputs={
                "total_purchases": input_vat_base,
                "vat_rate": cls.STANDARD_RATE,
            },
            result=total_input_vat,
            notes="VAT paid on goods and services purchased",
        ))
        
        # Step 5: Determine Recoverable Input VAT (WREN Compliance)
        step_num += 1
        recoverable_input_vat = wren_compliant_input * (cls.STANDARD_RATE / 100)
        non_recoverable = non_compliant_input * (cls.STANDARD_RATE / 100)
        steps.append(CalculationStep(
            step_number=step_num,
            description="Determine Recoverable Input VAT (WREN Compliant)",
            formula="Recoverable VAT = WREN-Compliant Expenses x VAT Rate",
            inputs={
                "wren_compliant_expenses": wren_compliant_input,
                "non_wren_expenses": non_compliant_input,
                "vat_rate": cls.STANDARD_RATE,
            },
            result=recoverable_input_vat,
            legal_reference=VAT_LEGAL_REFS["input_vat"],
            notes=f"Non-recoverable VAT: NGN {non_recoverable:,.2f} (non-WREN expenses)",
        ))
        legal_refs.append(VAT_LEGAL_REFS["input_vat"])
        
        if non_compliant_input > 0:
            warnings.append(
                f"NGN {non_compliant_input:,.2f} of expenses are non-WREN compliant. "
                f"VAT of NGN {non_recoverable:,.2f} is not recoverable."
            )
        
        # Step 6: Calculate Net VAT Payable/Refundable
        step_num += 1
        net_vat = output_vat - recoverable_input_vat
        steps.append(CalculationStep(
            step_number=step_num,
            description="Calculate Net VAT Payable or Refundable",
            formula="Net VAT = Output VAT - Recoverable Input VAT",
            inputs={
                "output_vat": output_vat,
                "recoverable_input_vat": recoverable_input_vat,
            },
            result=net_vat,
            notes="Positive = Payable to FIRS; Negative = Refundable/Carry Forward",
        ))
        
        # Build summary
        period_name = date(period_year, period_month, 1).strftime("%B %Y")
        if net_vat >= 0:
            summary = (
                f"VAT Calculation for {period_name}: "
                f"Output VAT of NGN {output_vat:,.2f} on sales of NGN {output_vat_base:,.2f}, "
                f"less recoverable input VAT of NGN {recoverable_input_vat:,.2f}, "
                f"results in net VAT payable of NGN {net_vat:,.2f} to FIRS."
            )
        else:
            summary = (
                f"VAT Calculation for {period_name}: "
                f"Output VAT of NGN {output_vat:,.2f} on sales of NGN {output_vat_base:,.2f}, "
                f"less recoverable input VAT of NGN {recoverable_input_vat:,.2f}, "
                f"results in VAT credit of NGN {abs(net_vat):,.2f} to carry forward."
            )
        
        effective_rate = (output_vat / output_vat_base * 100) if output_vat_base > 0 else Decimal("0")
        
        return TaxExplanation(
            tax_type=TaxType.VAT,
            entity_id=entity_id,
            calculation_date=datetime.utcnow(),
            period_start=date(period_year, period_month, 1),
            period_end=date(period_year, period_month, 28),  # Simplified
            gross_amount=output_vat_base,
            final_tax_amount=net_vat,
            effective_rate=effective_rate,
            steps=steps,
            summary=summary,
            assumptions=assumptions,
            warnings=warnings,
            legal_references=legal_refs,
        )


class WHTExplainability:
    """Generates detailed explanations for WHT calculations."""
    
    WHT_RATES = {
        "dividends": {"rate": Decimal("10"), "description": "Dividends"},
        "interest": {"rate": Decimal("10"), "description": "Interest"},
        "royalties": {"rate": Decimal("10"), "description": "Royalties"},
        "rent": {"rate": Decimal("10"), "description": "Rent"},
        "contracts": {"rate": Decimal("5"), "description": "Contracts/Agency"},
        "consultancy": {"rate": Decimal("10"), "description": "Consultancy/Professional Services"},
        "directors_fees": {"rate": Decimal("10"), "description": "Directors Fees"},
        "management_fees": {"rate": Decimal("10"), "description": "Management Fees"},
    }
    
    @classmethod
    def explain_calculation(
        cls,
        entity_id: uuid.UUID,
        payment_amount: Decimal,
        payment_type: str,
        recipient_name: str,
        recipient_tin: Optional[str] = None,
        is_resident: bool = True,
    ) -> TaxExplanation:
        """Generate explanation for WHT calculation."""
        steps = []
        legal_refs = []
        assumptions = []
        warnings = []
        step_num = 0
        
        # Get applicable rate
        rate_info = cls.WHT_RATES.get(payment_type.lower(), {"rate": Decimal("10"), "description": "Other"})
        wht_rate = rate_info["rate"]
        
        # Non-resident adjustment (10% additional for some categories)
        if not is_resident:
            wht_rate = min(wht_rate * Decimal("1.5"), Decimal("15"))
            assumptions.append("Non-resident WHT rates applied (higher of standard or 15%)")
        
        # Step 1: Identify Payment Type
        step_num += 1
        steps.append(CalculationStep(
            step_number=step_num,
            description="Identify Payment Type and Applicable WHT Rate",
            formula="Lookup WHT rate based on payment category",
            inputs={
                "payment_type": rate_info["description"],
                "is_resident": is_resident,
            },
            result=wht_rate,
            legal_reference=WHT_LEGAL_REFS["rates"],
            notes=f"WHT rate for {rate_info['description']}: {wht_rate}%",
        ))
        legal_refs.append(WHT_LEGAL_REFS["rates"])
        
        # Step 2: Calculate WHT Amount
        step_num += 1
        wht_amount = payment_amount * (wht_rate / 100)
        steps.append(CalculationStep(
            step_number=step_num,
            description="Calculate Withholding Tax Amount",
            formula="WHT Amount = Payment Amount x WHT Rate",
            inputs={
                "payment_amount": payment_amount,
                "wht_rate": wht_rate,
            },
            result=wht_amount,
            notes=f"Amount to be withheld and remitted to FIRS",
        ))
        
        # Step 3: Determine Net Payment
        step_num += 1
        net_payment = payment_amount - wht_amount
        steps.append(CalculationStep(
            step_number=step_num,
            description="Calculate Net Payment to Recipient",
            formula="Net Payment = Payment Amount - WHT Amount",
            inputs={
                "payment_amount": payment_amount,
                "wht_amount": wht_amount,
            },
            result=net_payment,
            notes=f"Amount payable to {recipient_name}",
        ))
        
        # TIN Warning
        if not recipient_tin:
            warnings.append(
                "Recipient TIN not provided. Higher WHT rate may apply for non-registered taxpayers."
            )
        
        summary = (
            f"WHT Calculation for {rate_info['description']} payment to {recipient_name}: "
            f"Payment of NGN {payment_amount:,.2f} attracts WHT of {wht_rate}% "
            f"(NGN {wht_amount:,.2f}). Net amount payable: NGN {net_payment:,.2f}."
        )
        
        return TaxExplanation(
            tax_type=TaxType.WHT,
            entity_id=entity_id,
            calculation_date=datetime.utcnow(),
            period_start=date.today(),
            period_end=date.today(),
            gross_amount=payment_amount,
            final_tax_amount=wht_amount,
            effective_rate=wht_rate,
            steps=steps,
            summary=summary,
            assumptions=assumptions,
            warnings=warnings,
            legal_references=legal_refs,
        )


class CITExplainability:
    """Generates detailed explanations for CIT calculations."""
    
    @classmethod
    def explain_calculation(
        cls,
        entity_id: uuid.UUID,
        gross_turnover: Decimal,
        assessable_profit: Decimal,
        capital_allowances: Decimal = Decimal("0"),
        prior_year_losses: Decimal = Decimal("0"),
        period_year: int = 2026,
    ) -> TaxExplanation:
        """Generate comprehensive explanation for CIT calculation."""
        steps = []
        legal_refs = []
        assumptions = []
        warnings = []
        step_num = 0
        
        # Determine company size and applicable rate
        if gross_turnover < 25000000:
            cit_rate = Decimal("0")
            company_size = "Small"
            legal_ref = CIT_LEGAL_REFS["small_rate"]
        elif gross_turnover <= 100000000:
            cit_rate = Decimal("20")
            company_size = "Medium"
            legal_ref = CIT_LEGAL_REFS["medium_rate"]
        else:
            cit_rate = Decimal("30")
            company_size = "Large"
            legal_ref = CIT_LEGAL_REFS["standard_rate"]
        
        # Step 1: Classify Company Size
        step_num += 1
        steps.append(CalculationStep(
            step_number=step_num,
            description="Classify Company by Turnover",
            formula="Compare turnover against size thresholds",
            inputs={
                "gross_turnover": gross_turnover,
                "small_threshold": Decimal("25000000"),
                "medium_threshold": Decimal("100000000"),
            },
            result=cit_rate,
            legal_reference=legal_ref,
            notes=f"Company classified as {company_size} (CIT Rate: {cit_rate}%)",
        ))
        legal_refs.append(legal_ref)
        
        # Step 2: Calculate Adjusted Profit
        step_num += 1
        adjusted_profit = assessable_profit - capital_allowances - prior_year_losses
        adjusted_profit = max(Decimal("0"), adjusted_profit)
        steps.append(CalculationStep(
            step_number=step_num,
            description="Calculate Adjusted/Taxable Profit",
            formula="Adjusted Profit = Assessable Profit - Capital Allowances - Prior Losses",
            inputs={
                "assessable_profit": assessable_profit,
                "capital_allowances": capital_allowances,
                "prior_year_losses": prior_year_losses,
            },
            result=adjusted_profit,
            notes="Capital allowances computed per Second Schedule CITA",
        ))
        
        # Step 3: Calculate CIT
        step_num += 1
        cit_amount = adjusted_profit * (cit_rate / 100)
        steps.append(CalculationStep(
            step_number=step_num,
            description="Calculate Companies Income Tax",
            formula=f"CIT = Adjusted Profit x CIT Rate ({cit_rate}%)",
            inputs={
                "adjusted_profit": adjusted_profit,
                "cit_rate": cit_rate,
            },
            result=cit_amount,
        ))
        
        # Step 4: Calculate Minimum Tax
        step_num += 1
        minimum_tax = gross_turnover * Decimal("0.005")  # 0.5%
        steps.append(CalculationStep(
            step_number=step_num,
            description="Calculate Minimum Tax",
            formula="Minimum Tax = Gross Turnover x 0.5%",
            inputs={"gross_turnover": gross_turnover},
            result=minimum_tax,
            legal_reference=CIT_LEGAL_REFS["minimum_tax"],
            notes="Minimum tax applies if CIT computed is lower",
        ))
        legal_refs.append(CIT_LEGAL_REFS["minimum_tax"])
        
        # Step 5: Determine Final Tax Payable
        step_num += 1
        final_tax = max(cit_amount, minimum_tax) if company_size != "Small" else Decimal("0")
        tax_basis = "CIT" if cit_amount >= minimum_tax else "Minimum Tax"
        steps.append(CalculationStep(
            step_number=step_num,
            description="Determine Final Tax Payable",
            formula="Final Tax = Higher of (CIT, Minimum Tax)",
            inputs={
                "cit_amount": cit_amount,
                "minimum_tax": minimum_tax,
            },
            result=final_tax,
            notes=f"Tax based on {tax_basis}",
        ))
        
        if cit_amount < minimum_tax and company_size != "Small":
            warnings.append(
                f"Minimum tax applies (NGN {minimum_tax:,.2f}) as it exceeds computed CIT "
                f"(NGN {cit_amount:,.2f})"
            )
        
        effective_rate = (final_tax / gross_turnover * 100) if gross_turnover > 0 else Decimal("0")
        
        summary = (
            f"CIT Calculation for {period_year}: "
            f"{company_size} company with turnover of NGN {gross_turnover:,.2f}. "
            f"Assessable profit of NGN {assessable_profit:,.2f} yields adjusted profit of "
            f"NGN {adjusted_profit:,.2f} after allowances. "
            f"Final CIT payable: NGN {final_tax:,.2f} (based on {tax_basis})."
        )
        
        return TaxExplanation(
            tax_type=TaxType.CIT,
            entity_id=entity_id,
            calculation_date=datetime.utcnow(),
            period_start=date(period_year, 1, 1),
            period_end=date(period_year, 12, 31),
            gross_amount=gross_turnover,
            final_tax_amount=final_tax,
            effective_rate=effective_rate,
            steps=steps,
            summary=summary,
            assumptions=assumptions,
            warnings=warnings,
            legal_references=legal_refs,
        )


class AuditExplainabilityService:
    """
    Main service for generating tax calculation explanations.
    
    Provides audit-ready documentation for all tax computations.
    """
    
    def __init__(self, db: AsyncSession = None):
        self.db = db
    
    def explain_paye(
        self,
        entity_id: uuid.UUID,
        gross_annual_income: float,
        basic_salary: Optional[float] = None,
        pension_percentage: float = 8.0,
        nhf_contribution: Optional[float] = None,
        other_reliefs: float = 0,
        period_year: int = 2026,
    ) -> Dict[str, Any]:
        """Generate PAYE calculation explanation."""
        explanation = PAYEExplainability.explain_calculation(
            entity_id=entity_id,
            gross_annual_income=Decimal(str(gross_annual_income)),
            basic_salary=Decimal(str(basic_salary)) if basic_salary else None,
            pension_percentage=Decimal(str(pension_percentage)),
            nhf_contribution=Decimal(str(nhf_contribution)) if nhf_contribution else None,
            other_reliefs=Decimal(str(other_reliefs)),
            period_year=period_year,
        )
        return explanation.to_dict()
    
    def explain_vat(
        self,
        entity_id: uuid.UUID,
        output_vat_base: float,
        input_vat_base: float,
        wren_compliant_input: float,
        non_compliant_input: float,
        period_month: int,
        period_year: int,
        zero_rated_sales: float = 0,
        exempt_sales: float = 0,
    ) -> Dict[str, Any]:
        """Generate VAT calculation explanation."""
        explanation = VATExplainability.explain_calculation(
            entity_id=entity_id,
            output_vat_base=Decimal(str(output_vat_base)),
            input_vat_base=Decimal(str(input_vat_base)),
            wren_compliant_input=Decimal(str(wren_compliant_input)),
            non_compliant_input=Decimal(str(non_compliant_input)),
            period_month=period_month,
            period_year=period_year,
            zero_rated_sales=Decimal(str(zero_rated_sales)),
            exempt_sales=Decimal(str(exempt_sales)),
        )
        return explanation.to_dict()
    
    def explain_wht(
        self,
        entity_id: uuid.UUID,
        payment_amount: float,
        payment_type: str,
        recipient_name: str,
        recipient_tin: Optional[str] = None,
        is_resident: bool = True,
    ) -> Dict[str, Any]:
        """Generate WHT calculation explanation."""
        explanation = WHTExplainability.explain_calculation(
            entity_id=entity_id,
            payment_amount=Decimal(str(payment_amount)),
            payment_type=payment_type,
            recipient_name=recipient_name,
            recipient_tin=recipient_tin,
            is_resident=is_resident,
        )
        return explanation.to_dict()
    
    def explain_cit(
        self,
        entity_id: uuid.UUID,
        gross_turnover: float,
        assessable_profit: float,
        capital_allowances: float = 0,
        prior_year_losses: float = 0,
        period_year: int = 2026,
    ) -> Dict[str, Any]:
        """Generate CIT calculation explanation."""
        explanation = CITExplainability.explain_calculation(
            entity_id=entity_id,
            gross_turnover=Decimal(str(gross_turnover)),
            assessable_profit=Decimal(str(assessable_profit)),
            capital_allowances=Decimal(str(capital_allowances)),
            prior_year_losses=Decimal(str(prior_year_losses)),
            period_year=period_year,
        )
        return explanation.to_dict()
    
    def get_legal_references(self, tax_type: str) -> List[Dict[str, Any]]:
        """Get all legal references for a tax type."""
        refs_map = {
            "paye": PAYE_LEGAL_REFS,
            "vat": VAT_LEGAL_REFS,
            "wht": WHT_LEGAL_REFS,
            "cit": CIT_LEGAL_REFS,
        }
        
        refs = refs_map.get(tax_type.lower(), {})
        return [
            {
                "key": key,
                "citation": ref.to_citation(),
                "description": ref.description,
                "effective_date": ref.effective_date.isoformat() if ref.effective_date else None,
            }
            for key, ref in refs.items()
        ]
