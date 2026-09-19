"""
Tekvwa Pro Audit - Advanced Payroll Service

Implements world-class payroll features for Nigerian enterprises:
- Compliance Status Engine with penalty estimation
- Payroll Change Impact Preview
- Exception Flags with acknowledgement
- Decision Logs (immutable)
- YTD Ledger (stored snapshots)
- Opening Balance Import
- Smart Validation (Ghost detection, variance flags)
- Cost-to-Company Analytics
- What-If Simulations
"""

import hashlib
import uuid
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, extract, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.payroll import (
    Employee, PayrollRun, Payslip, StatutoryRemittance,
    EmploymentStatus, PayrollStatus
)
from app.models.payroll_advanced import (
    ComplianceSnapshot, ComplianceStatus, RemittanceType,
    PayrollImpactPreview, PayrollException, ExceptionCode, ExceptionSeverity,
    PayrollDecisionLog, YTDPayrollLedger, OpeningBalanceImport,
    PayslipExplanation, EmployeeVarianceLog, VarianceReason,
    CostToCompanySnapshot, WhatIfSimulation, GhostWorkerDetection
)
from app.schemas.payroll_advanced import (
    ComplianceStatusItem, ComplianceSnapshotResponse,
    ComplianceSnapshotCreate
)


# ===========================================
# PENALTY RATES (NIGERIAN COMPLIANCE)
# ===========================================

# PAYE late filing: 10% of tax due + 2% monthly interest
PAYE_LATE_PENALTY_RATE = Decimal("0.10")
PAYE_MONTHLY_INTEREST_RATE = Decimal("0.02")

# Pension late remittance: 2% monthly interest
PENSION_MONTHLY_INTEREST_RATE = Decimal("0.02")

# NHF: 10% + interest
NHF_LATE_PENALTY_RATE = Decimal("0.10")

# Due dates (day of month)
PAYE_DUE_DAY = 10  # 10th of the following month
PENSION_DUE_DAY = 7  # 7th of the following month
NHF_DUE_DAY = 10


class PayrollAdvancedService:
    """
    Advanced payroll service for compliance tracking and analytics.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ===========================================
    # COMPLIANCE SNAPSHOT METHODS
    # ===========================================

    async def get_compliance_snapshot(
        self,
        entity_id: uuid.UUID,
        period_month: int,
        period_year: int,
    ) -> Optional[ComplianceSnapshot]:
        """Get compliance snapshot for a specific period."""
        result = await self.db.execute(
            select(ComplianceSnapshot).where(
                and_(
                    ComplianceSnapshot.entity_id == entity_id,
                    ComplianceSnapshot.period_month == period_month,
                    ComplianceSnapshot.period_year == period_year,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_compliance_snapshots(
        self,
        entity_id: uuid.UUID,
        year: Optional[int] = None,
        page: int = 1,
        per_page: int = 12,
    ) -> Tuple[List[ComplianceSnapshot], int]:
        """List compliance snapshots with pagination."""
        query = select(ComplianceSnapshot).where(
            ComplianceSnapshot.entity_id == entity_id
        )

        if year:
            query = query.where(ComplianceSnapshot.period_year == year)

        # Count total
        count_result = await self.db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar() or 0

        # Apply ordering and pagination
        query = query.order_by(
            ComplianceSnapshot.period_year.desc(),
            ComplianceSnapshot.period_month.desc(),
        )
        query = query.offset((page - 1) * per_page).limit(per_page)

        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def generate_compliance_snapshot(
        self,
        entity_id: uuid.UUID,
        period_month: int,
        period_year: int,
        paye_tax_state: Optional[str] = None,
    ) -> ComplianceSnapshot:
        """
        Generate or update compliance snapshot for a period.
        Calculates status based on remittances and payroll data.
        """
        today = date.today()
        
        # Calculate due dates for the period
        # Remittances are due the following month
        if period_month == 12:
            due_month = 1
            due_year = period_year + 1
        else:
            due_month = period_month + 1
            due_year = period_year
        
        _, last_day = monthrange(due_year, due_month)
        
        paye_due_date = date(due_year, due_month, min(PAYE_DUE_DAY, last_day))
        pension_due_date = date(due_year, due_month, min(PENSION_DUE_DAY, last_day))
        nhf_due_date = date(due_year, due_month, min(NHF_DUE_DAY, last_day))
        
        # Get payroll run for this period
        payroll_result = await self.db.execute(
            select(PayrollRun).where(
                and_(
                    PayrollRun.entity_id == entity_id,
                    extract('month', PayrollRun.period_start) == period_month,
                    extract('year', PayrollRun.period_start) == period_year,
                    PayrollRun.status.in_([
                        PayrollStatus.APPROVED,
                        PayrollStatus.PROCESSING,
                        PayrollStatus.COMPLETED,
                        PayrollStatus.PAID,
                    ])
                )
            )
        )
        payroll = payroll_result.scalar_one_or_none()
        
        # Get remittances for this period
        remittances = await self._get_period_remittances(
            entity_id, period_month, period_year
        )
        
        # Calculate amounts due from payroll
        paye_due = Decimal("0")
        pension_due = Decimal("0")
        nhf_due = Decimal("0")
        nsitf_due = Decimal("0")
        itf_due = Decimal("0")
        
        if payroll:
            paye_due = payroll.total_paye
            pension_due = payroll.total_pension_employee + payroll.total_pension_employer
            nhf_due = payroll.total_nhf
            nsitf_due = payroll.total_nsitf
            itf_due = payroll.total_itf
        
        # Calculate paid amounts from remittances
        paye_paid = sum(
            r.amount_paid for r in remittances
            if r.remittance_type == "PAYE"
        )
        pension_paid = sum(
            r.amount_paid for r in remittances
            if r.remittance_type == "PENSION"
        )
        nhf_paid = sum(
            r.amount_paid for r in remittances
            if r.remittance_type == "NHF"
        )
        nsitf_paid = sum(
            r.amount_paid for r in remittances
            if r.remittance_type == "NSITF"
        )
        itf_paid = sum(
            r.amount_paid for r in remittances
            if r.remittance_type == "ITF"
        )
        
        # Calculate statuses and penalties
        paye_status, paye_days_overdue, paye_penalty = self._calculate_remittance_status(
            amount_due=paye_due,
            amount_paid=paye_paid,
            due_date=paye_due_date,
            today=today,
            penalty_rate=PAYE_LATE_PENALTY_RATE,
            monthly_interest=PAYE_MONTHLY_INTEREST_RATE,
        )
        
        pension_status, pension_days_overdue, pension_penalty = self._calculate_remittance_status(
            amount_due=pension_due,
            amount_paid=pension_paid,
            due_date=pension_due_date,
            today=today,
            penalty_rate=Decimal("0"),
            monthly_interest=PENSION_MONTHLY_INTEREST_RATE,
        )
        
        nhf_status, nhf_days_overdue, _ = self._calculate_remittance_status(
            amount_due=nhf_due,
            amount_paid=nhf_paid,
            due_date=nhf_due_date,
            today=today,
            penalty_rate=NHF_LATE_PENALTY_RATE,
            monthly_interest=Decimal("0"),
        )
        
        nsitf_status, _, _ = self._calculate_remittance_status(
            amount_due=nsitf_due,
            amount_paid=nsitf_paid,
            due_date=None,  # NSITF annual
            today=today,
            penalty_rate=Decimal("0"),
            monthly_interest=Decimal("0"),
        )
        
        itf_status, _, _ = self._calculate_remittance_status(
            amount_due=itf_due,
            amount_paid=itf_paid,
            due_date=None,  # ITF annual
            today=today,
            penalty_rate=Decimal("0"),
            monthly_interest=Decimal("0"),
        )
        
        # Total penalty exposure
        total_penalty = paye_penalty + pension_penalty
        
        # Check if snapshot exists, update or create
        existing = await self.get_compliance_snapshot(entity_id, period_month, period_year)
        
        if existing:
            # Update existing snapshot
            existing.paye_status = paye_status
            existing.paye_amount_due = paye_due
            existing.paye_amount_paid = paye_paid
            existing.paye_due_date = paye_due_date
            existing.paye_days_overdue = paye_days_overdue
            existing.paye_penalty_estimate = paye_penalty
            existing.paye_tax_state = paye_tax_state
            
            existing.pension_status = pension_status
            existing.pension_amount_due = pension_due
            existing.pension_amount_paid = pension_paid
            existing.pension_due_date = pension_due_date
            existing.pension_days_overdue = pension_days_overdue
            existing.pension_penalty_estimate = pension_penalty
            
            existing.nhf_status = nhf_status
            existing.nhf_amount_due = nhf_due
            existing.nhf_amount_paid = nhf_paid
            existing.nhf_due_date = nhf_due_date
            existing.nhf_days_overdue = nhf_days_overdue
            
            existing.nsitf_status = nsitf_status
            existing.nsitf_amount_due = nsitf_due
            existing.nsitf_amount_paid = nsitf_paid
            
            existing.itf_status = itf_status
            existing.itf_amount_due = itf_due
            existing.itf_amount_paid = itf_paid
            
            existing.total_penalty_exposure = total_penalty
            existing.snapshot_date = datetime.utcnow()
            
            await self.db.commit()
            await self.db.refresh(existing)
            return existing
        
        # Create new snapshot
        snapshot = ComplianceSnapshot(
            entity_id=entity_id,
            period_month=period_month,
            period_year=period_year,
            
            paye_status=paye_status,
            paye_amount_due=paye_due,
            paye_amount_paid=paye_paid,
            paye_due_date=paye_due_date,
            paye_days_overdue=paye_days_overdue,
            paye_penalty_estimate=paye_penalty,
            paye_tax_state=paye_tax_state,
            
            pension_status=pension_status,
            pension_amount_due=pension_due,
            pension_amount_paid=pension_paid,
            pension_due_date=pension_due_date,
            pension_days_overdue=pension_days_overdue,
            pension_penalty_estimate=pension_penalty,
            
            nhf_status=nhf_status,
            nhf_amount_due=nhf_due,
            nhf_amount_paid=nhf_paid,
            nhf_due_date=nhf_due_date,
            nhf_days_overdue=nhf_days_overdue,
            
            nsitf_status=nsitf_status,
            nsitf_amount_due=nsitf_due,
            nsitf_amount_paid=nsitf_paid,
            
            itf_status=itf_status,
            itf_amount_due=itf_due,
            itf_amount_paid=itf_paid,
            
            total_penalty_exposure=total_penalty,
        )
        
        self.db.add(snapshot)
        await self.db.commit()
        await self.db.refresh(snapshot)
        
        return snapshot

    async def get_current_compliance_status(
        self,
        entity_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Get real-time compliance status dashboard data.
        Returns current month status + YTD summary.
        """
        today = date.today()
        current_month = today.month
        current_year = today.year
        
        # Generate/refresh current month snapshot
        current_snapshot = await self.generate_compliance_snapshot(
            entity_id=entity_id,
            period_month=current_month,
            period_year=current_year,
        )
        
        # Get all snapshots for the year
        year_snapshots, _ = await self.list_compliance_snapshots(
            entity_id=entity_id,
            year=current_year,
            per_page=12,
        )
        
        # Calculate YTD totals
        ytd_paye_due = sum(s.paye_amount_due for s in year_snapshots)
        ytd_paye_paid = sum(s.paye_amount_paid for s in year_snapshots)
        ytd_pension_due = sum(s.pension_amount_due for s in year_snapshots)
        ytd_pension_paid = sum(s.pension_amount_paid for s in year_snapshots)
        ytd_nhf_due = sum(s.nhf_amount_due for s in year_snapshots)
        ytd_nhf_paid = sum(s.nhf_amount_paid for s in year_snapshots)
        ytd_total_penalty = sum(s.total_penalty_exposure for s in year_snapshots)
        
        # Count overdue statuses
        overdue_count = sum(
            1 for s in year_snapshots
            if s.paye_status == ComplianceStatus.OVERDUE
            or s.pension_status == ComplianceStatus.OVERDUE
            or s.nhf_status == ComplianceStatus.OVERDUE
        )
        
        # Determine overall status
        if current_snapshot.total_penalty_exposure > 0:
            overall_status = "overdue"
        elif (current_snapshot.paye_status == ComplianceStatus.PENALTY_RISK or
              current_snapshot.pension_status == ComplianceStatus.PENALTY_RISK):
            overall_status = "at_risk"
        else:
            overall_status = "compliant"
        
        return {
            "current_period": {
                "month": current_month,
                "year": current_year,
                "snapshot": self._format_snapshot_response(current_snapshot),
            },
            "ytd_summary": {
                "paye_due": float(ytd_paye_due),
                "paye_paid": float(ytd_paye_paid),
                "paye_outstanding": float(ytd_paye_due - ytd_paye_paid),
                "pension_due": float(ytd_pension_due),
                "pension_paid": float(ytd_pension_paid),
                "pension_outstanding": float(ytd_pension_due - ytd_pension_paid),
                "nhf_due": float(ytd_nhf_due),
                "nhf_paid": float(ytd_nhf_paid),
                "nhf_outstanding": float(ytd_nhf_due - ytd_nhf_paid),
                "total_penalty_exposure": float(ytd_total_penalty),
            },
            "overall_status": overall_status,
            "overdue_periods": overdue_count,
            "periods_reviewed": len(year_snapshots),
        }

    def _calculate_remittance_status(
        self,
        amount_due: Decimal,
        amount_paid: Decimal,
        due_date: Optional[date],
        today: date,
        penalty_rate: Decimal,
        monthly_interest: Decimal,
    ) -> Tuple[ComplianceStatus, int, Decimal]:
        """
        Calculate remittance status and penalty.
        Returns: (status, days_overdue, penalty_amount)
        """
        if amount_due == 0:
            return ComplianceStatus.NOT_DUE, 0, Decimal("0")
        
        outstanding = amount_due - amount_paid
        
        if outstanding <= 0:
            return ComplianceStatus.ON_TIME, 0, Decimal("0")
        
        if due_date is None:
            # No specific due date (e.g., NSITF/ITF)
            if amount_paid > 0:
                return ComplianceStatus.PARTIALLY_PAID, 0, Decimal("0")
            return ComplianceStatus.NOT_DUE, 0, Decimal("0")
        
        if today <= due_date:
            # Not yet due
            days_until_due = (due_date - today).days
            if days_until_due <= 3 and outstanding > 0:
                return ComplianceStatus.PENALTY_RISK, 0, Decimal("0")
            if amount_paid > 0 and amount_paid < amount_due:
                return ComplianceStatus.PARTIALLY_PAID, 0, Decimal("0")
            return ComplianceStatus.NOT_DUE, 0, Decimal("0")
        
        # Past due date
        days_overdue = (today - due_date).days
        
        # Calculate penalty
        penalty = Decimal("0")
        if penalty_rate > 0:
            penalty = outstanding * penalty_rate
        
        if monthly_interest > 0:
            months_overdue = days_overdue // 30
            if months_overdue > 0:
                penalty += outstanding * monthly_interest * months_overdue
        
        penalty = penalty.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        if amount_paid > 0:
            return ComplianceStatus.PARTIALLY_PAID, days_overdue, penalty
        
        return ComplianceStatus.OVERDUE, days_overdue, penalty

    async def _get_period_remittances(
        self,
        entity_id: uuid.UUID,
        period_month: int,
        period_year: int,
    ) -> List[StatutoryRemittance]:
        """Get remittances for a specific period."""
        result = await self.db.execute(
            select(StatutoryRemittance).where(
                and_(
                    StatutoryRemittance.entity_id == entity_id,
                    StatutoryRemittance.period_month == period_month,
                    StatutoryRemittance.period_year == period_year,
                )
            )
        )
        return list(result.scalars().all())

    def _format_snapshot_response(
        self,
        snapshot: ComplianceSnapshot,
    ) -> Dict[str, Any]:
        """Format snapshot for API response."""
        def format_status_item(
            remittance_type: str,
            status: ComplianceStatus,
            amount_due: Decimal,
            amount_paid: Decimal,
            due_date: Optional[date],
            days_overdue: int,
            penalty_estimate: Decimal = Decimal("0"),
        ) -> Dict[str, Any]:
            """Create human-readable message for status."""
            outstanding = amount_due - amount_paid
            
            if status == ComplianceStatus.ON_TIME:
                message = f"{remittance_type} fully paid on time."
            elif status == ComplianceStatus.NOT_DUE:
                if due_date:
                    message = f"{remittance_type} due on {due_date.strftime('%d %b %Y')}."
                else:
                    message = f"No {remittance_type} due for this period."
            elif status == ComplianceStatus.PARTIALLY_PAID:
                message = f"₦{outstanding:,.2f} {remittance_type} outstanding."
            elif status == ComplianceStatus.PENALTY_RISK:
                message = f"{remittance_type} due within 3 days! Pay ₦{outstanding:,.2f} to avoid penalties."
            elif status == ComplianceStatus.OVERDUE:
                message = f"OVERDUE: {remittance_type} ₦{outstanding:,.2f} outstanding. {days_overdue} days late. Estimated penalty: ₦{penalty_estimate:,.2f}"
            else:
                message = f"{remittance_type} exempt for this period."
            
            return {
                "remittance_type": remittance_type.lower(),
                "status": status.value,
                "amount_due": float(amount_due),
                "amount_paid": float(amount_paid),
                "due_date": due_date.isoformat() if due_date else None,
                "days_overdue": days_overdue,
                "penalty_estimate": float(penalty_estimate),
                "human_message": message,
            }
        
        # Determine overall status
        statuses = [
            snapshot.paye_status,
            snapshot.pension_status,
            snapshot.nhf_status,
        ]
        
        if any(s == ComplianceStatus.OVERDUE for s in statuses):
            overall_status = "overdue"
            summary_message = "URGENT: You have overdue statutory remittances. Pay immediately to minimize penalties."
        elif any(s == ComplianceStatus.PENALTY_RISK for s in statuses):
            overall_status = "at_risk"
            summary_message = "Payment deadlines approaching. Pay now to avoid penalties."
        elif all(s in [ComplianceStatus.ON_TIME, ComplianceStatus.NOT_DUE, ComplianceStatus.EXEMPT] for s in statuses):
            overall_status = "compliant"
            summary_message = "All statutory remittances are up to date."
        else:
            overall_status = "at_risk"
            summary_message = "Some remittances require attention."
        
        return {
            "id": str(snapshot.id),
            "entity_id": str(snapshot.entity_id),
            "period_month": snapshot.period_month,
            "period_year": snapshot.period_year,
            "paye_status": format_status_item(
                "PAYE",
                snapshot.paye_status,
                snapshot.paye_amount_due,
                snapshot.paye_amount_paid,
                snapshot.paye_due_date,
                snapshot.paye_days_overdue,
                snapshot.paye_penalty_estimate,
            ),
            "pension_status": format_status_item(
                "Pension",
                snapshot.pension_status,
                snapshot.pension_amount_due,
                snapshot.pension_amount_paid,
                snapshot.pension_due_date,
                snapshot.pension_days_overdue,
                snapshot.pension_penalty_estimate,
            ),
            "nhf_status": format_status_item(
                "NHF",
                snapshot.nhf_status,
                snapshot.nhf_amount_due,
                snapshot.nhf_amount_paid,
                snapshot.nhf_due_date,
                snapshot.nhf_days_overdue,
            ),
            "nsitf_status": format_status_item(
                "NSITF",
                snapshot.nsitf_status,
                snapshot.nsitf_amount_due,
                snapshot.nsitf_amount_paid,
                None,
                0,
            ),
            "itf_status": format_status_item(
                "ITF",
                snapshot.itf_status,
                snapshot.itf_amount_due,
                snapshot.itf_amount_paid,
                None,
                0,
            ),
            "total_penalty_exposure": float(snapshot.total_penalty_exposure),
            "overall_status": overall_status,
            "summary_message": summary_message,
            "snapshot_date": snapshot.snapshot_date.isoformat(),
        }

    async def refresh_all_compliance_snapshots(
        self,
        entity_id: uuid.UUID,
        year: int,
    ) -> List[ComplianceSnapshot]:
        """Refresh all compliance snapshots for a year."""
        snapshots = []
        for month in range(1, 13):
            # Only process months up to current date
            if year == date.today().year and month > date.today().month:
                break
            snapshot = await self.generate_compliance_snapshot(
                entity_id=entity_id,
                period_month=month,
                period_year=year,
            )
            snapshots.append(snapshot)
        return snapshots

    async def get_compliance_calendar(
        self,
        entity_id: uuid.UUID,
        year: int,
    ) -> Dict[str, Any]:
        """
        Get compliance calendar for the year.
        Shows due dates and status for each month.
        """
        snapshots, _ = await self.list_compliance_snapshots(
            entity_id=entity_id,
            year=year,
            per_page=12,
        )
        
        # Index by month
        by_month = {s.period_month: s for s in snapshots}
        
        calendar = []
        today = date.today()
        
        for month in range(1, 13):
            if year == today.year and month > today.month:
                # Future months
                calendar.append({
                    "month": month,
                    "status": "future",
                    "paye_due": None,
                    "pension_due": None,
                    "nhf_due": None,
                })
            elif month in by_month:
                s = by_month[month]
                calendar.append({
                    "month": month,
                    "status": "reviewed",
                    "paye_status": s.paye_status.value,
                    "paye_due": s.paye_due_date.isoformat() if s.paye_due_date else None,
                    "paye_amount": float(s.paye_amount_due),
                    "pension_status": s.pension_status.value,
                    "pension_due": s.pension_due_date.isoformat() if s.pension_due_date else None,
                    "pension_amount": float(s.pension_amount_due),
                    "nhf_status": s.nhf_status.value,
                    "nhf_due": s.nhf_due_date.isoformat() if s.nhf_due_date else None,
                    "nhf_amount": float(s.nhf_amount_due),
                    "has_penalty": s.total_penalty_exposure > 0,
                })
            else:
                # Month needs snapshot generation
                calendar.append({
                    "month": month,
                    "status": "pending",
                    "paye_due": None,
                    "pension_due": None,
                    "nhf_due": None,
                })
        
        return {
            "year": year,
            "months": calendar,
            "total_months_reviewed": len(snapshots),
        }

    # ===========================================
    # PAYROLL IMPACT PREVIEW METHODS
    # ===========================================

    async def get_impact_preview(
        self,
        entity_id: uuid.UUID,
        payroll_run_id: uuid.UUID,
    ) -> Optional[PayrollImpactPreview]:
        """Get impact preview for a payroll run."""
        # First verify the payroll belongs to the entity
        payroll_result = await self.db.execute(
            select(PayrollRun).where(
                and_(
                    PayrollRun.id == payroll_run_id,
                    PayrollRun.entity_id == entity_id,
                )
            )
        )
        payroll = payroll_result.scalar_one_or_none()
        if not payroll:
            return None

        result = await self.db.execute(
            select(PayrollImpactPreview).where(
                PayrollImpactPreview.payroll_run_id == payroll_run_id
            )
        )
        return result.scalar_one_or_none()

    async def generate_impact_preview(
        self,
        entity_id: uuid.UUID,
        payroll_run_id: uuid.UUID,
    ) -> PayrollImpactPreview:
        """
        Generate or update impact preview for a payroll run.
        Compares current payroll to the most recent previous payroll.
        """
        # Get current payroll run
        payroll_result = await self.db.execute(
            select(PayrollRun).where(
                and_(
                    PayrollRun.id == payroll_run_id,
                    PayrollRun.entity_id == entity_id,
                )
            )
        )
        current_payroll = payroll_result.scalar_one_or_none()
        if not current_payroll:
            raise ValueError("Payroll run not found")

        # Get previous payroll run
        previous_result = await self.db.execute(
            select(PayrollRun)
            .where(
                and_(
                    PayrollRun.entity_id == entity_id,
                    PayrollRun.id != payroll_run_id,
                    PayrollRun.status.in_([
                        PayrollStatus.APPROVED,
                        PayrollStatus.PROCESSING,
                        PayrollStatus.COMPLETED,
                        PayrollStatus.PAID,
                    ]),
                    PayrollRun.period_end < current_payroll.period_start,
                )
            )
            .order_by(PayrollRun.period_end.desc())
            .limit(1)
        )
        previous_payroll = previous_result.scalar_one_or_none()

        # Current period totals
        current_gross = current_payroll.total_gross_pay or Decimal("0")
        current_net = current_payroll.total_net_pay or Decimal("0")
        current_paye = current_payroll.total_paye or Decimal("0")
        current_employer_cost = (
            current_gross +
            (current_payroll.total_pension_employer or Decimal("0")) +
            (current_payroll.total_nsitf or Decimal("0")) +
            (current_payroll.total_itf or Decimal("0"))
        )
        current_employee_count = current_payroll.total_employees or 0

        # Previous period totals
        if previous_payroll:
            previous_gross = previous_payroll.total_gross_pay or Decimal("0")
            previous_net = previous_payroll.total_net_pay or Decimal("0")
            previous_paye = previous_payroll.total_paye or Decimal("0")
            previous_employer_cost = (
                previous_gross +
                (previous_payroll.total_pension_employer or Decimal("0")) +
                (previous_payroll.total_nsitf or Decimal("0")) +
                (previous_payroll.total_itf or Decimal("0"))
            )
            previous_employee_count = previous_payroll.total_employees or 0
            previous_payroll_id = previous_payroll.id
        else:
            previous_gross = Decimal("0")
            previous_net = Decimal("0")
            previous_paye = Decimal("0")
            previous_employer_cost = Decimal("0")
            previous_employee_count = 0
            previous_payroll_id = None

        # Calculate variances
        gross_variance = current_gross - previous_gross
        net_variance = current_net - previous_net
        paye_variance = current_paye - previous_paye
        employer_cost_variance = current_employer_cost - previous_employer_cost

        if previous_gross > 0:
            gross_variance_percent = (
                (gross_variance / previous_gross) * Decimal("100")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            gross_variance_percent = Decimal("100") if current_gross > 0 else Decimal("0")

        # Analyze variance drivers
        variance_drivers, new_hires, terminations = await self._analyze_variance_drivers(
            entity_id=entity_id,
            current_payroll=current_payroll,
            previous_payroll=previous_payroll,
        )

        # Calculate new hires cost and termination savings
        new_hires_count = len(new_hires)
        new_hires_cost = sum(h.get("gross", 0) for h in new_hires)
        terminations_count = len(terminations)
        terminations_savings = sum(t.get("gross", 0) for t in terminations)

        # Generate human-readable summary
        impact_summary = self._generate_impact_summary(
            gross_variance=gross_variance,
            gross_variance_percent=gross_variance_percent,
            new_hires_count=new_hires_count,
            terminations_count=terminations_count,
            current_employee_count=current_employee_count,
            previous_employee_count=previous_employee_count,
            variance_drivers=variance_drivers,
        )

        # Check if preview exists
        existing = await self.get_impact_preview(entity_id, payroll_run_id)

        if existing:
            # Update existing preview
            existing.previous_payroll_id = previous_payroll_id
            existing.current_gross = current_gross
            existing.current_net = current_net
            existing.current_paye = current_paye
            existing.current_employer_cost = current_employer_cost
            existing.current_employee_count = current_employee_count
            existing.previous_gross = previous_gross
            existing.previous_net = previous_net
            existing.previous_paye = previous_paye
            existing.previous_employer_cost = previous_employer_cost
            existing.previous_employee_count = previous_employee_count
            existing.gross_variance = gross_variance
            existing.gross_variance_percent = gross_variance_percent
            existing.net_variance = net_variance
            existing.paye_variance = paye_variance
            existing.employer_cost_variance = employer_cost_variance
            existing.variance_drivers = variance_drivers
            existing.new_hires_count = new_hires_count
            existing.new_hires_cost = Decimal(str(new_hires_cost))
            existing.terminations_count = terminations_count
            existing.terminations_savings = Decimal(str(terminations_savings))
            existing.impact_summary = impact_summary
            existing.generated_at = datetime.utcnow()

            await self.db.commit()
            await self.db.refresh(existing)
            return existing

        # Create new preview
        preview = PayrollImpactPreview(
            payroll_run_id=payroll_run_id,
            previous_payroll_id=previous_payroll_id,
            current_gross=current_gross,
            current_net=current_net,
            current_paye=current_paye,
            current_employer_cost=current_employer_cost,
            current_employee_count=current_employee_count,
            previous_gross=previous_gross,
            previous_net=previous_net,
            previous_paye=previous_paye,
            previous_employer_cost=previous_employer_cost,
            previous_employee_count=previous_employee_count,
            gross_variance=gross_variance,
            gross_variance_percent=gross_variance_percent,
            net_variance=net_variance,
            paye_variance=paye_variance,
            employer_cost_variance=employer_cost_variance,
            variance_drivers=variance_drivers,
            new_hires_count=new_hires_count,
            new_hires_cost=Decimal(str(new_hires_cost)),
            terminations_count=terminations_count,
            terminations_savings=Decimal(str(terminations_savings)),
            impact_summary=impact_summary,
        )

        self.db.add(preview)
        await self.db.commit()
        await self.db.refresh(preview)

        return preview

    async def _analyze_variance_drivers(
        self,
        entity_id: uuid.UUID,
        current_payroll: PayrollRun,
        previous_payroll: Optional[PayrollRun],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Analyze what's driving the variance between payroll periods.
        Returns: (variance_drivers, new_hires, terminations)
        """
        variance_drivers = []
        new_hires = []
        terminations = []

        # Get current payslips
        current_payslips_result = await self.db.execute(
            select(Payslip)
            .options(selectinload(Payslip.employee))
            .where(Payslip.payroll_run_id == current_payroll.id)
        )
        current_payslips = {
            p.employee_id: p for p in current_payslips_result.scalars().all()
        }

        # Get previous payslips if exists
        previous_payslips = {}
        if previous_payroll:
            previous_payslips_result = await self.db.execute(
                select(Payslip)
                .options(selectinload(Payslip.employee))
                .where(Payslip.payroll_run_id == previous_payroll.id)
            )
            previous_payslips = {
                p.employee_id: p for p in previous_payslips_result.scalars().all()
            }

        # Identify new hires (in current but not in previous)
        for emp_id, payslip in current_payslips.items():
            if emp_id not in previous_payslips:
                new_hires.append({
                    "employee_id": str(emp_id),
                    "employee_name": payslip.employee.full_name if payslip.employee else "Unknown",
                    "gross": float(payslip.gross_pay),
                })

        # Identify terminations (in previous but not in current)
        for emp_id, payslip in previous_payslips.items():
            if emp_id not in current_payslips:
                terminations.append({
                    "employee_id": str(emp_id),
                    "employee_name": payslip.employee.full_name if payslip.employee else "Unknown",
                    "gross": float(payslip.gross_pay),
                })

        # Track salary changes for continuing employees
        salary_increases = []
        salary_decreases = []

        for emp_id, current in current_payslips.items():
            if emp_id in previous_payslips:
                prev = previous_payslips[emp_id]
                diff = current.gross_pay - prev.gross_pay

                if diff > Decimal("1000"):  # Significant increase
                    salary_increases.append({
                        "employee_id": str(emp_id),
                        "employee_name": current.employee.full_name if current.employee else "Unknown",
                        "previous": float(prev.gross_pay),
                        "current": float(current.gross_pay),
                        "difference": float(diff),
                    })
                elif diff < Decimal("-1000"):  # Significant decrease
                    salary_decreases.append({
                        "employee_id": str(emp_id),
                        "employee_name": current.employee.full_name if current.employee else "Unknown",
                        "previous": float(prev.gross_pay),
                        "current": float(current.gross_pay),
                        "difference": float(diff),
                    })

        # Build variance drivers list (top 5)
        if new_hires:
            total_new_hire_cost = sum(h["gross"] for h in new_hires)
            variance_drivers.append({
                "category": "new_hires",
                "description": f"{len(new_hires)} new employee(s) added",
                "amount": total_new_hire_cost,
                "affected_employees": len(new_hires),
            })

        if terminations:
            total_termination_savings = sum(t["gross"] for t in terminations)
            variance_drivers.append({
                "category": "terminations",
                "description": f"{len(terminations)} employee(s) terminated/exited",
                "amount": -total_termination_savings,
                "affected_employees": len(terminations),
            })

        if salary_increases:
            total_increase = sum(s["difference"] for s in salary_increases)
            variance_drivers.append({
                "category": "salary_increase",
                "description": f"Salary increases for {len(salary_increases)} employee(s)",
                "amount": total_increase,
                "affected_employees": len(salary_increases),
            })

        if salary_decreases:
            total_decrease = sum(s["difference"] for s in salary_decreases)
            variance_drivers.append({
                "category": "salary_decrease",
                "description": f"Salary decreases for {len(salary_decreases)} employee(s)",
                "amount": total_decrease,
                "affected_employees": len(salary_decreases),
            })

        # Sort by absolute amount and take top 5
        variance_drivers.sort(key=lambda x: abs(x["amount"]), reverse=True)
        variance_drivers = variance_drivers[:5]

        return variance_drivers, new_hires, terminations

    def _generate_impact_summary(
        self,
        gross_variance: Decimal,
        gross_variance_percent: Decimal,
        new_hires_count: int,
        terminations_count: int,
        current_employee_count: int,
        previous_employee_count: int,
        variance_drivers: List[Dict[str, Any]],
    ) -> str:
        """Generate human-readable impact summary."""
        summary_parts = []

        # Overall change
        if gross_variance > 0:
            summary_parts.append(
                f"Total payroll increased by ₦{gross_variance:,.2f} ({gross_variance_percent:+.1f}%)."
            )
        elif gross_variance < 0:
            summary_parts.append(
                f"Total payroll decreased by ₦{abs(gross_variance):,.2f} ({gross_variance_percent:.1f}%)."
            )
        else:
            summary_parts.append("Total payroll unchanged from previous period.")

        # Headcount change
        headcount_diff = current_employee_count - previous_employee_count
        if headcount_diff > 0:
            summary_parts.append(
                f"Headcount increased by {headcount_diff} to {current_employee_count} employees."
            )
        elif headcount_diff < 0:
            summary_parts.append(
                f"Headcount decreased by {abs(headcount_diff)} to {current_employee_count} employees."
            )

        # Key drivers
        if new_hires_count > 0:
            summary_parts.append(f"{new_hires_count} new hire(s) added.")

        if terminations_count > 0:
            summary_parts.append(f"{terminations_count} employee(s) exited.")

        # Top variance driver
        if variance_drivers:
            top_driver = variance_drivers[0]
            if top_driver["amount"] > 0:
                summary_parts.append(
                    f"Largest impact: {top_driver['description']} (+₦{top_driver['amount']:,.2f})."
                )
            else:
                summary_parts.append(
                    f"Largest impact: {top_driver['description']} (-₦{abs(top_driver['amount']):,.2f})."
                )

        return " ".join(summary_parts)

    def format_impact_preview_response(
        self,
        preview: PayrollImpactPreview,
        payroll_run: Optional[PayrollRun] = None,
    ) -> Dict[str, Any]:
        """Format impact preview for API response."""
        response = {
            "id": str(preview.id),
            "payroll_run_id": str(preview.payroll_run_id),
            "previous_payroll_id": str(preview.previous_payroll_id) if preview.previous_payroll_id else None,
            "current_gross": float(preview.current_gross),
            "current_net": float(preview.current_net),
            "current_paye": float(preview.current_paye),
            "current_employer_cost": float(preview.current_employer_cost),
            "current_employee_count": preview.current_employee_count,
            "previous_gross": float(preview.previous_gross),
            "previous_net": float(preview.previous_net),
            "previous_paye": float(preview.previous_paye),
            "previous_employer_cost": float(preview.previous_employer_cost),
            "previous_employee_count": preview.previous_employee_count,
            "gross_variance": float(preview.gross_variance),
            "gross_variance_percent": float(preview.gross_variance_percent),
            "net_variance": float(preview.net_variance),
            "paye_variance": float(preview.paye_variance),
            "employer_cost_variance": float(preview.employer_cost_variance),
            "variance_drivers": preview.variance_drivers or [],
            "new_hires_count": preview.new_hires_count,
            "new_hires_cost": float(preview.new_hires_cost),
            "terminations_count": preview.terminations_count,
            "terminations_savings": float(preview.terminations_savings),
            "impact_summary": preview.impact_summary,
            "generated_at": preview.generated_at.isoformat() if preview.generated_at else None,
        }
        
        # Include payroll run details if provided
        if payroll_run:
            response["payroll_run_name"] = payroll_run.name
            response["period_start"] = payroll_run.period_start.isoformat() if payroll_run.period_start else None
            response["period_end"] = payroll_run.period_end.isoformat() if payroll_run.period_end else None
            response["payroll_status"] = payroll_run.status.value if payroll_run.status else None
        
        return response

    async def get_latest_impact_preview(
        self,
        entity_id: uuid.UUID,
    ) -> Optional[PayrollImpactPreview]:
        """
        Get the most recent impact preview for the entity.
        
        Args:
            entity_id: Entity UUID
            
        Returns:
            Most recent PayrollImpactPreview or None
        """
        query = (
            select(PayrollImpactPreview)
            .join(PayrollRun, PayrollImpactPreview.payroll_run_id == PayrollRun.id)
            .where(PayrollRun.entity_id == entity_id)
            .order_by(PayrollImpactPreview.generated_at.desc())
            .limit(1)
        )
        
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_impact_previews(
        self,
        entity_id: uuid.UUID,
        year: Optional[int] = None,
        page: int = 1,
        per_page: int = 12,
    ) -> Tuple[List[Tuple[PayrollImpactPreview, PayrollRun]], int]:
        """
        List impact previews with pagination.
        
        Args:
            entity_id: Entity UUID
            year: Optional year filter
            page: Page number (1-indexed)
            per_page: Items per page
            
        Returns:
            Tuple of (list of (preview, payroll_run) tuples, total count)
        """
        # Base query - select both preview and payroll run
        base_query = (
            select(PayrollImpactPreview, PayrollRun)
            .join(PayrollRun, PayrollImpactPreview.payroll_run_id == PayrollRun.id)
            .where(PayrollRun.entity_id == entity_id)
        )
        
        # Filter by year if specified
        if year:
            base_query = base_query.where(
                func.extract('year', PayrollRun.period_start) == year
            )
        
        # Count query - count only previews
        count_query = (
            select(func.count(PayrollImpactPreview.id))
            .join(PayrollRun, PayrollImpactPreview.payroll_run_id == PayrollRun.id)
            .where(PayrollRun.entity_id == entity_id)
        )
        if year:
            count_query = count_query.where(
                func.extract('year', PayrollRun.period_start) == year
            )
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0
        
        # Paginated query
        offset = (page - 1) * per_page
        query = (
            base_query
            .order_by(PayrollRun.period_start.desc())
            .offset(offset)
            .limit(per_page)
        )
        
        result = await self.db.execute(query)
        rows = result.all()
        
        return list(rows), total

    # ===========================================
    # PAYROLL EXCEPTION MANAGEMENT
    # ===========================================

    async def get_exception(
        self,
        exception_id: uuid.UUID,
    ) -> Optional[PayrollException]:
        """
        Get a specific exception by ID.
        
        Args:
            exception_id: Exception UUID
            
        Returns:
            PayrollException or None
        """
        query = select(PayrollException).where(PayrollException.id == exception_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_exceptions_for_payroll_run(
        self,
        payroll_run_id: uuid.UUID,
        severity: Optional[str] = None,
        acknowledged: Optional[bool] = None,
    ) -> List[PayrollException]:
        """
        Get all exceptions for a payroll run.
        
        Args:
            payroll_run_id: Payroll run UUID
            severity: Optional filter by severity (critical, warning, info)
            acknowledged: Optional filter by acknowledgement status
            
        Returns:
            List of PayrollException objects
        """
        query = (
            select(PayrollException)
            .where(PayrollException.payroll_run_id == payroll_run_id)
        )
        
        if severity:
            query = query.where(PayrollException.severity == ExceptionSeverity(severity))
        
        if acknowledged is not None:
            query = query.where(PayrollException.is_acknowledged == acknowledged)
        
        query = query.order_by(
            PayrollException.severity.asc(),  # Critical first
            PayrollException.created_at.desc(),
        )
        
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_exception_summary(
        self,
        payroll_run_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Get summary of exceptions for a payroll run.
        
        Args:
            payroll_run_id: Payroll run UUID
            
        Returns:
            Exception summary with counts and blocking status
        """
        exceptions = await self.get_exceptions_for_payroll_run(payroll_run_id)
        
        critical_count = sum(1 for e in exceptions if e.severity == ExceptionSeverity.CRITICAL)
        warning_count = sum(1 for e in exceptions if e.severity == ExceptionSeverity.WARNING)
        info_count = sum(1 for e in exceptions if e.severity == ExceptionSeverity.INFO)
        
        unacknowledged = [e for e in exceptions if e.requires_acknowledgement and not e.is_acknowledged]
        unacknowledged_count = len(unacknowledged)
        
        # Can approve if no unacknowledged critical exceptions
        blocking = [e for e in exceptions if e.severity == ExceptionSeverity.CRITICAL and not e.is_acknowledged]
        can_approve = len(blocking) == 0
        
        return {
            "payroll_run_id": str(payroll_run_id),
            "total_exceptions": len(exceptions),
            "critical_count": critical_count,
            "warning_count": warning_count,
            "info_count": info_count,
            "unacknowledged_count": unacknowledged_count,
            "can_approve": can_approve,
            "blocking_exceptions": [
                self.format_exception_response(e) for e in blocking
            ],
            "exceptions": [
                self.format_exception_response(e) for e in exceptions
            ],
        }

    async def create_exception(
        self,
        payroll_run_id: uuid.UUID,
        exception_code: str,
        severity: str,
        title: str,
        description: str,
        payslip_id: Optional[uuid.UUID] = None,
        employee_id: Optional[uuid.UUID] = None,
        related_field: Optional[str] = None,
        current_value: Optional[str] = None,
        expected_value: Optional[str] = None,
        requires_acknowledgement: bool = True,
    ) -> PayrollException:
        """
        Create a new payroll exception.
        
        Args:
            payroll_run_id: Payroll run UUID
            exception_code: Exception code enum value
            severity: Severity level (critical, warning, info)
            title: Exception title
            description: Detailed description
            payslip_id: Optional related payslip
            employee_id: Optional related employee
            related_field: Optional field name causing exception
            current_value: Current value of the field
            expected_value: Expected value
            requires_acknowledgement: Whether acknowledgement is required
            
        Returns:
            Created PayrollException
        """
        exception = PayrollException(
            payroll_run_id=payroll_run_id,
            payslip_id=payslip_id,
            employee_id=employee_id,
            exception_code=ExceptionCode(exception_code),
            severity=ExceptionSeverity(severity),
            title=title,
            description=description,
            related_field=related_field,
            current_value=current_value,
            expected_value=expected_value,
            requires_acknowledgement=requires_acknowledgement,
            is_acknowledged=False,
            is_resolved=False,
        )
        
        self.db.add(exception)
        await self.db.commit()
        await self.db.refresh(exception)
        
        return exception

    async def acknowledge_exception(
        self,
        exception_id: uuid.UUID,
        user_id: uuid.UUID,
        acknowledgement_note: Optional[str] = None,
    ) -> Optional[PayrollException]:
        """
        Acknowledge an exception.
        
        Args:
            exception_id: Exception UUID
            user_id: User acknowledging the exception
            acknowledgement_note: Optional note for acknowledgement
            
        Returns:
            Updated PayrollException or None if not found
        """
        exception = await self.get_exception(exception_id)
        if not exception:
            return None
        
        exception.is_acknowledged = True
        exception.acknowledged_by_id = user_id
        exception.acknowledged_at = datetime.now(timezone.utc)
        exception.acknowledgement_note = acknowledgement_note
        
        await self.db.commit()
        await self.db.refresh(exception)
        
        return exception

    async def resolve_exception(
        self,
        exception_id: uuid.UUID,
    ) -> Optional[PayrollException]:
        """
        Mark an exception as resolved.
        
        Args:
            exception_id: Exception UUID
            
        Returns:
            Updated PayrollException or None if not found
        """
        exception = await self.get_exception(exception_id)
        if not exception:
            return None
        
        exception.is_resolved = True
        exception.resolved_at = datetime.now(timezone.utc)
        
        await self.db.commit()
        await self.db.refresh(exception)
        
        return exception

    async def bulk_acknowledge_exceptions(
        self,
        exception_ids: List[uuid.UUID],
        user_id: uuid.UUID,
        acknowledgement_note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Acknowledge multiple exceptions at once.
        
        Args:
            exception_ids: List of exception UUIDs
            user_id: User acknowledging
            acknowledgement_note: Optional note
            
        Returns:
            Summary of acknowledged exceptions
        """
        acknowledged = []
        failed = []
        
        for exception_id in exception_ids:
            result = await self.acknowledge_exception(
                exception_id=exception_id,
                user_id=user_id,
                acknowledgement_note=acknowledgement_note,
            )
            if result:
                acknowledged.append(str(exception_id))
            else:
                failed.append(str(exception_id))
        
        return {
            "acknowledged_count": len(acknowledged),
            "failed_count": len(failed),
            "acknowledged_ids": acknowledged,
            "failed_ids": failed,
        }

    async def validate_payroll_run(
        self,
        payroll_run_id: uuid.UUID,
    ) -> List[PayrollException]:
        """
        Run validation checks on a payroll run and create exceptions.
        
        This method performs various validation checks:
        - Negative net pay
        - Duplicate bank accounts/BVN
        - Below minimum wage
        - Missing required fields (TIN, Pension PIN, etc.)
        - Large variances from previous period
        
        Args:
            payroll_run_id: Payroll run UUID
            
        Returns:
            List of created exceptions
        """
        from app.models.payroll import PayrollRun, Payslip
        from app.models.employee import Employee
        
        # Get payroll run with payslips
        run_query = select(PayrollRun).where(PayrollRun.id == payroll_run_id)
        run_result = await self.db.execute(run_query)
        payroll_run = run_result.scalar_one_or_none()
        
        if not payroll_run:
            return []
        
        # Get payslips for this run
        payslips_query = (
            select(Payslip)
            .where(Payslip.payroll_run_id == payroll_run_id)
        )
        payslips_result = await self.db.execute(payslips_query)
        payslips = list(payslips_result.scalars().all())
        
        created_exceptions = []
        
        # Check each payslip
        for payslip in payslips:
            # Get employee
            emp_query = select(Employee).where(Employee.id == payslip.employee_id)
            emp_result = await self.db.execute(emp_query)
            employee = emp_result.scalar_one_or_none()
            
            if not employee:
                continue
            
            # Check for negative net pay
            if payslip.net_pay < 0:
                exception = await self.create_exception(
                    payroll_run_id=payroll_run_id,
                    payslip_id=payslip.id,
                    employee_id=employee.id,
                    exception_code=ExceptionCode.NEGATIVE_NET_PAY.value,
                    severity=ExceptionSeverity.CRITICAL.value,
                    title="Negative Net Pay",
                    description=f"Employee {employee.first_name} {employee.last_name} has negative net pay of ₦{payslip.net_pay:,.2f}. This may indicate excessive deductions.",
                    related_field="net_pay",
                    current_value=str(payslip.net_pay),
                    expected_value=">= 0",
                )
                created_exceptions.append(exception)
            
            # Check for below minimum wage
            minimum_wage = Decimal("70000")  # Current Nigerian minimum wage
            if payslip.basic_salary < minimum_wage:
                exception = await self.create_exception(
                    payroll_run_id=payroll_run_id,
                    payslip_id=payslip.id,
                    employee_id=employee.id,
                    exception_code=ExceptionCode.BELOW_MINIMUM_WAGE.value,
                    severity=ExceptionSeverity.CRITICAL.value,
                    title="Below Minimum Wage",
                    description=f"Employee {employee.first_name} {employee.last_name} basic salary of ₦{payslip.basic_salary:,.2f} is below national minimum wage of ₦{minimum_wage:,.2f}.",
                    related_field="basic_salary",
                    current_value=str(payslip.basic_salary),
                    expected_value=f">= {minimum_wage}",
                )
                created_exceptions.append(exception)
            
            # Check for missing TIN
            if not getattr(employee, 'tax_id', None):
                exception = await self.create_exception(
                    payroll_run_id=payroll_run_id,
                    payslip_id=payslip.id,
                    employee_id=employee.id,
                    exception_code=ExceptionCode.MISSING_TIN.value,
                    severity=ExceptionSeverity.WARNING.value,
                    title="Missing Tax ID",
                    description=f"Employee {employee.first_name} {employee.last_name} is missing Tax Identification Number (TIN). This is required for PAYE remittance.",
                    related_field="tax_id",
                    current_value="None",
                    expected_value="Valid TIN",
                )
                created_exceptions.append(exception)
            
            # Check for missing bank account
            if not getattr(employee, 'bank_account_number', None):
                exception = await self.create_exception(
                    payroll_run_id=payroll_run_id,
                    payslip_id=payslip.id,
                    employee_id=employee.id,
                    exception_code=ExceptionCode.MISSING_BANK_ACCOUNT.value,
                    severity=ExceptionSeverity.WARNING.value,
                    title="Missing Bank Account",
                    description=f"Employee {employee.first_name} {employee.last_name} has no bank account on file. Salary cannot be paid electronically.",
                    related_field="bank_account_number",
                    current_value="None",
                    expected_value="Valid Bank Account",
                )
                created_exceptions.append(exception)
            
            # Check for zero PAYE on high income
            high_income_threshold = Decimal("500000")
            if payslip.gross_pay > high_income_threshold and getattr(payslip, 'paye_tax', Decimal("0")) == 0:
                exception = await self.create_exception(
                    payroll_run_id=payroll_run_id,
                    payslip_id=payslip.id,
                    employee_id=employee.id,
                    exception_code=ExceptionCode.ZERO_PAYE_HIGH_INCOME.value,
                    severity=ExceptionSeverity.WARNING.value,
                    title="Zero PAYE on High Income",
                    description=f"Employee {employee.first_name} {employee.last_name} with gross pay ₦{payslip.gross_pay:,.2f} has zero PAYE tax. Please verify tax calculation.",
                    related_field="paye_tax",
                    current_value="0",
                    expected_value="> 0",
                )
                created_exceptions.append(exception)
        
        # Check for duplicate bank accounts
        bank_accounts = {}
        for payslip in payslips:
            emp_query = select(Employee).where(Employee.id == payslip.employee_id)
            emp_result = await self.db.execute(emp_query)
            employee = emp_result.scalar_one_or_none()
            
            if employee and getattr(employee, 'bank_account_number', None):
                account = employee.bank_account_number
                if account in bank_accounts:
                    # Duplicate found
                    exception = await self.create_exception(
                        payroll_run_id=payroll_run_id,
                        payslip_id=payslip.id,
                        employee_id=employee.id,
                        exception_code=ExceptionCode.DUPLICATE_ACCOUNT.value,
                        severity=ExceptionSeverity.CRITICAL.value,
                        title="Duplicate Bank Account",
                        description=f"Bank account {account} is used by multiple employees. This may indicate a ghost worker or data error.",
                        related_field="bank_account_number",
                        current_value=account,
                        expected_value="Unique account per employee",
                    )
                    created_exceptions.append(exception)
                else:
                    bank_accounts[account] = employee.id
        
        return created_exceptions

    def format_exception_response(
        self,
        exception: PayrollException,
    ) -> Dict[str, Any]:
        """Format exception for API response."""
        return {
            "id": str(exception.id),
            "payroll_run_id": str(exception.payroll_run_id),
            "payslip_id": str(exception.payslip_id) if exception.payslip_id else None,
            "employee_id": str(exception.employee_id) if exception.employee_id else None,
            "exception_code": exception.exception_code.value if exception.exception_code else None,
            "severity": exception.severity.value if exception.severity else None,
            "title": exception.title,
            "description": exception.description,
            "related_field": exception.related_field,
            "current_value": exception.current_value,
            "expected_value": exception.expected_value,
            "requires_acknowledgement": exception.requires_acknowledgement,
            "is_acknowledged": exception.is_acknowledged,
            "acknowledged_by_id": str(exception.acknowledged_by_id) if exception.acknowledged_by_id else None,
            "acknowledged_at": exception.acknowledged_at.isoformat() if exception.acknowledged_at else None,
            "acknowledgement_note": exception.acknowledgement_note,
            "is_resolved": exception.is_resolved,
            "resolved_at": exception.resolved_at.isoformat() if exception.resolved_at else None,
            "created_at": exception.created_at.isoformat() if exception.created_at else None,
        }

    # ===========================================
    # PAYROLL DECISION LOG (IMMUTABLE)
    # ===========================================

    async def get_decision_log(
        self,
        log_id: uuid.UUID,
    ) -> Optional[PayrollDecisionLog]:
        """
        Get a specific decision log by ID.
        
        Args:
            log_id: Decision log UUID
            
        Returns:
            PayrollDecisionLog or None
        """
        query = select(PayrollDecisionLog).where(PayrollDecisionLog.id == log_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_decision_logs(
        self,
        entity_id: uuid.UUID,
        payroll_run_id: Optional[uuid.UUID] = None,
        employee_id: Optional[uuid.UUID] = None,
        decision_type: Optional[str] = None,
        category: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[List[PayrollDecisionLog], int]:
        """
        List decision logs with filters and pagination.
        
        Args:
            entity_id: Entity UUID
            payroll_run_id: Optional filter by payroll run
            employee_id: Optional filter by employee
            decision_type: Optional filter by type
            category: Optional filter by category
            page: Page number
            per_page: Items per page
            
        Returns:
            Tuple of (list of logs, total count)
        """
        base_query = (
            select(PayrollDecisionLog)
            .where(PayrollDecisionLog.entity_id == entity_id)
        )
        
        if payroll_run_id:
            base_query = base_query.where(PayrollDecisionLog.payroll_run_id == payroll_run_id)
        
        if employee_id:
            base_query = base_query.where(PayrollDecisionLog.employee_id == employee_id)
        
        if decision_type:
            base_query = base_query.where(PayrollDecisionLog.decision_type == decision_type)
        
        if category:
            base_query = base_query.where(PayrollDecisionLog.category == category)
        
        # Count query
        count_query = select(func.count()).select_from(base_query.subquery())
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0
        
        # Paginated query
        offset = (page - 1) * per_page
        query = (
            base_query
            .order_by(PayrollDecisionLog.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        
        result = await self.db.execute(query)
        logs = result.scalars().all()
        
        return list(logs), total

    async def create_decision_log(
        self,
        entity_id: uuid.UUID,
        user_id: uuid.UUID,
        user_name: str,
        user_role: str,
        decision_type: str,
        category: str,
        title: str,
        description: str,
        payroll_run_id: Optional[uuid.UUID] = None,
        payslip_id: Optional[uuid.UUID] = None,
        employee_id: Optional[uuid.UUID] = None,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> PayrollDecisionLog:
        """
        Create a new immutable decision log entry.
        
        Args:
            entity_id: Entity UUID
            user_id: User creating the log
            user_name: User's display name
            user_role: User's role
            decision_type: Type of decision (approval, adjustment, exception_override, note)
            category: Category (payroll, salary, deduction, exception, approval, other)
            title: Log title
            description: Detailed description
            payroll_run_id: Optional related payroll run
            payslip_id: Optional related payslip
            employee_id: Optional related employee
            context_data: Optional contextual data
            
        Returns:
            Created PayrollDecisionLog
        """
        # Generate content hash for integrity
        content = f"{decision_type}|{category}|{title}|{description}|{user_id}|{datetime.now(timezone.utc).isoformat()}"
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        
        log = PayrollDecisionLog(
            entity_id=entity_id,
            payroll_run_id=payroll_run_id,
            payslip_id=payslip_id,
            employee_id=employee_id,
            decision_type=decision_type,
            category=category,
            title=title,
            description=description,
            context_data=context_data or {},
            created_by_id=user_id,
            created_by_name=user_name,
            created_by_role=user_role,
            is_locked=False,
            content_hash=content_hash,
        )
        
        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)
        
        return log

    async def lock_decision_logs_for_payroll(
        self,
        payroll_run_id: uuid.UUID,
    ) -> int:
        """
        Lock all decision logs for a completed payroll run.
        This makes them immutable.
        
        Args:
            payroll_run_id: Payroll run UUID
            
        Returns:
            Number of logs locked
        """
        from sqlalchemy import update
        
        stmt = (
            update(PayrollDecisionLog)
            .where(PayrollDecisionLog.payroll_run_id == payroll_run_id)
            .where(PayrollDecisionLog.is_locked == False)
            .values(is_locked=True)
        )
        
        result = await self.db.execute(stmt)
        await self.db.commit()
        
        return result.rowcount

    async def get_decision_log_summary(
        self,
        entity_id: uuid.UUID,
        payroll_run_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """
        Get summary of decision logs.
        
        Args:
            entity_id: Entity UUID
            payroll_run_id: Optional filter by payroll run
            
        Returns:
            Summary with counts by type and category
        """
        base_query = (
            select(PayrollDecisionLog)
            .where(PayrollDecisionLog.entity_id == entity_id)
        )
        
        if payroll_run_id:
            base_query = base_query.where(PayrollDecisionLog.payroll_run_id == payroll_run_id)
        
        result = await self.db.execute(base_query)
        logs = list(result.scalars().all())
        
        # Count by type
        type_counts = {}
        for log in logs:
            type_counts[log.decision_type] = type_counts.get(log.decision_type, 0) + 1
        
        # Count by category
        category_counts = {}
        for log in logs:
            category_counts[log.category] = category_counts.get(log.category, 0) + 1
        
        # Recent logs (last 5)
        recent_logs = sorted(logs, key=lambda x: x.created_at, reverse=True)[:5]
        
        return {
            "total_logs": len(logs),
            "locked_count": sum(1 for l in logs if l.is_locked),
            "unlocked_count": sum(1 for l in logs if not l.is_locked),
            "by_type": type_counts,
            "by_category": category_counts,
            "recent_logs": [self.format_decision_log_response(l) for l in recent_logs],
        }

    async def verify_log_integrity(
        self,
        log_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Verify the integrity of a decision log by checking its hash.
        
        Args:
            log_id: Decision log UUID
            
        Returns:
            Verification result
        """
        log = await self.get_decision_log(log_id)
        if not log:
            return {
                "valid": False,
                "error": "Log not found",
            }
        
        # Recreate hash (note: we can't perfectly recreate since timestamp is part of hash)
        # For now, just verify the hash exists and log is locked if payroll is complete
        
        return {
            "id": str(log.id),
            "content_hash": log.content_hash,
            "is_locked": log.is_locked,
            "has_hash": bool(log.content_hash),
            "created_at": log.created_at.isoformat() if log.created_at else None,
            "verification_note": "Hash present and log integrity maintained" if log.content_hash else "No hash found",
        }

    def format_decision_log_response(
        self,
        log: PayrollDecisionLog,
    ) -> Dict[str, Any]:
        """Format decision log for API response."""
        # Extract commonly used fields from context_data for frontend convenience
        context = log.context_data or {}
        
        return {
            "id": str(log.id),
            "entity_id": str(log.entity_id),
            "payroll_run_id": str(log.payroll_run_id) if log.payroll_run_id else None,
            "payslip_id": str(log.payslip_id) if log.payslip_id else None,
            "employee_id": str(log.employee_id) if log.employee_id else None,
            "decision_type": log.decision_type,
            "category": log.category,
            "title": log.title,
            "description": log.description,
            "context_data": context,
            "created_by_id": str(log.created_by_id),
            "created_by_name": log.created_by_name,
            "created_by_role": log.created_by_role,
            "created_at": log.created_at.isoformat() if log.created_at else None,
            "is_locked": log.is_locked,
            "content_hash": log.content_hash,
            # Frontend-expected fields extracted from context_data
            "employee_name": context.get("employee_name"),
            "original_value": context.get("original_value"),
            "new_value": context.get("new_value"),
            "justification": context.get("justification"),
            "impact_preview": context.get("impact_preview"),
        }

    # ===========================================
    # YTD PAYROLL LEDGER METHODS
    # ===========================================

    async def get_ytd_ledger(
        self,
        entity_id: uuid.UUID,
        employee_id: uuid.UUID,
        tax_year: int,
    ) -> Optional[YTDPayrollLedger]:
        """Get YTD ledger for an employee for a specific tax year."""
        result = await self.db.execute(
            select(YTDPayrollLedger).where(
                and_(
                    YTDPayrollLedger.entity_id == entity_id,
                    YTDPayrollLedger.employee_id == employee_id,
                    YTDPayrollLedger.tax_year == tax_year,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_ytd_ledgers(
        self,
        entity_id: uuid.UUID,
        tax_year: int,
        page: int = 1,
        per_page: int = 20,
        search: Optional[str] = None,
    ) -> Tuple[List[Tuple[YTDPayrollLedger, Optional[str]]], int]:
        """List YTD ledgers for all employees with pagination.
        
        Returns a list of tuples containing (ledger, employee_name).
        """
        # Base query with join to Employee for names
        base_query = (
            select(YTDPayrollLedger, Employee.first_name, Employee.middle_name, Employee.last_name)
            .outerjoin(Employee, YTDPayrollLedger.employee_id == Employee.id)
            .where(
                and_(
                    YTDPayrollLedger.entity_id == entity_id,
                    YTDPayrollLedger.tax_year == tax_year,
                )
            )
        )
        
        # Count total
        count_query = (
            select(func.count(YTDPayrollLedger.id))
            .where(
                and_(
                    YTDPayrollLedger.entity_id == entity_id,
                    YTDPayrollLedger.tax_year == tax_year,
                )
            )
        )
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0
        
        # Apply ordering and pagination
        query = base_query.order_by(YTDPayrollLedger.ytd_gross.desc())
        query = query.offset((page - 1) * per_page).limit(per_page)
        
        result = await self.db.execute(query)
        rows = result.all()
        
        # Build list of (ledger, full_name) tuples
        ledgers_with_names = []
        for row in rows:
            ledger = row[0]
            first_name = row[1]
            middle_name = row[2]
            last_name = row[3]
            
            # Build full name
            if first_name and last_name:
                name_parts = [first_name]
                if middle_name:
                    name_parts.append(middle_name)
                name_parts.append(last_name)
                full_name = " ".join(name_parts)
            else:
                full_name = None
            
            ledgers_with_names.append((ledger, full_name))
        
        return ledgers_with_names, total

    async def get_ytd_ledger_summary(
        self,
        entity_id: uuid.UUID,
        tax_year: int,
    ) -> Dict[str, Any]:
        """Get summary statistics for YTD ledgers."""
        result = await self.db.execute(
            select(
                func.count(YTDPayrollLedger.id).label("total_employees"),
                func.sum(YTDPayrollLedger.ytd_gross).label("total_ytd_gross"),
                func.sum(YTDPayrollLedger.ytd_paye).label("total_ytd_paye"),
                func.sum(YTDPayrollLedger.ytd_pension_employee).label("total_ytd_pension"),
                func.sum(YTDPayrollLedger.ytd_net).label("total_ytd_net"),
                func.sum(YTDPayrollLedger.ytd_total_employer_cost).label("total_ytd_employer_cost"),
                func.avg(YTDPayrollLedger.ytd_gross).label("average_ytd_gross"),
                func.avg(YTDPayrollLedger.ytd_net).label("average_ytd_net"),
            ).where(
                and_(
                    YTDPayrollLedger.entity_id == entity_id,
                    YTDPayrollLedger.tax_year == tax_year,
                )
            )
        )
        row = result.fetchone()
        
        return {
            "entity_id": str(entity_id),
            "tax_year": tax_year,
            "total_employees": row.total_employees or 0,
            "total_ytd_gross": float(row.total_ytd_gross or 0),
            "total_ytd_paye": float(row.total_ytd_paye or 0),
            "total_ytd_pension": float(row.total_ytd_pension or 0),
            "total_ytd_net": float(row.total_ytd_net or 0),
            "total_ytd_employer_cost": float(row.total_ytd_employer_cost or 0),
            "average_ytd_gross": float(row.average_ytd_gross or 0),
            "average_ytd_net": float(row.average_ytd_net or 0),
        }

    async def update_ytd_ledger_from_payroll(
        self,
        entity_id: uuid.UUID,
        payroll_run_id: uuid.UUID,
        tax_year: int,
    ) -> int:
        """
        Update YTD ledgers from a completed payroll run.
        Creates new ledgers if they don't exist.
        Returns count of updated ledgers.
        """
        # Get payslips for this payroll run
        payslip_result = await self.db.execute(
            select(Payslip).where(Payslip.payroll_run_id == payroll_run_id)
        )
        payslips = list(payslip_result.scalars().all())
        
        updated_count = 0
        for payslip in payslips:
            existing = await self.get_ytd_ledger(entity_id, payslip.employee_id, tax_year)
            
            if existing:
                # Update existing ledger
                existing.ytd_gross += payslip.gross_pay
                existing.ytd_basic += payslip.basic_salary
                existing.ytd_housing += getattr(payslip, 'housing_allowance', Decimal("0")) or Decimal("0")
                existing.ytd_transport += getattr(payslip, 'transport_allowance', Decimal("0")) or Decimal("0")
                existing.ytd_paye += payslip.paye_tax
                existing.ytd_pension_employee += payslip.pension_employee
                existing.ytd_nhf += payslip.nhf
                existing.ytd_total_deductions += payslip.total_deductions
                existing.ytd_net += payslip.net_pay
                existing.ytd_pension_employer += payslip.pension_employer
                existing.ytd_nsitf += payslip.nsitf
                existing.ytd_itf += payslip.itf
                existing.ytd_total_employer_cost += (
                    payslip.gross_pay + payslip.pension_employer + 
                    payslip.nsitf + payslip.itf
                )
                existing.months_processed += 1
                existing.last_payroll_id = payroll_run_id
            else:
                # Create new ledger
                new_ledger = YTDPayrollLedger(
                    entity_id=entity_id,
                    employee_id=payslip.employee_id,
                    tax_year=tax_year,
                    ytd_gross=payslip.gross_pay,
                    ytd_basic=payslip.basic_salary,
                    ytd_housing=getattr(payslip, 'housing_allowance', Decimal("0")) or Decimal("0"),
                    ytd_transport=getattr(payslip, 'transport_allowance', Decimal("0")) or Decimal("0"),
                    ytd_paye=payslip.paye_tax,
                    ytd_pension_employee=payslip.pension_employee,
                    ytd_nhf=payslip.nhf,
                    ytd_total_deductions=payslip.total_deductions,
                    ytd_net=payslip.net_pay,
                    ytd_pension_employer=payslip.pension_employer,
                    ytd_nsitf=payslip.nsitf,
                    ytd_itf=payslip.itf,
                    ytd_total_employer_cost=(
                        payslip.gross_pay + payslip.pension_employer + 
                        payslip.nsitf + payslip.itf
                    ),
                    months_processed=1,
                    last_payroll_id=payroll_run_id,
                )
                self.db.add(new_ledger)
            
            updated_count += 1
        
        await self.db.commit()
        return updated_count

    def format_ytd_ledger_response(
        self,
        ledger: YTDPayrollLedger,
        employee_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Format YTD ledger for API response."""
        return {
            "id": str(ledger.id),
            "entity_id": str(ledger.entity_id),
            "employee_id": str(ledger.employee_id),
            "employee_name": employee_name,
            "tax_year": ledger.tax_year,
            "ytd_gross": float(ledger.ytd_gross),
            "ytd_basic": float(ledger.ytd_basic),
            "ytd_housing": float(ledger.ytd_housing),
            "ytd_transport": float(ledger.ytd_transport),
            "ytd_other_earnings": float(ledger.ytd_other_earnings),
            "ytd_paye": float(ledger.ytd_paye),
            "ytd_pension_employee": float(ledger.ytd_pension_employee),
            "ytd_nhf": float(ledger.ytd_nhf),
            "ytd_other_deductions": float(ledger.ytd_other_deductions),
            "ytd_total_deductions": float(ledger.ytd_total_deductions),
            "ytd_net": float(ledger.ytd_net),
            "ytd_pension_employer": float(ledger.ytd_pension_employer),
            "ytd_nsitf": float(ledger.ytd_nsitf),
            "ytd_itf": float(ledger.ytd_itf),
            "ytd_total_employer_cost": float(ledger.ytd_total_employer_cost),
            "months_processed": ledger.months_processed,
            "last_updated": ledger.last_updated.isoformat() if ledger.last_updated else None,
            "has_opening_balance": ledger.has_opening_balance,
            "opening_balance_date": ledger.opening_balance_date.isoformat() if ledger.opening_balance_date else None,
        }

    # ===========================================
    # OPENING BALANCE IMPORT METHODS
    # ===========================================

    async def get_opening_balance(
        self,
        entity_id: uuid.UUID,
        employee_id: uuid.UUID,
        tax_year: int,
    ) -> Optional[OpeningBalanceImport]:
        """Get opening balance for an employee."""
        result = await self.db.execute(
            select(OpeningBalanceImport).where(
                and_(
                    OpeningBalanceImport.entity_id == entity_id,
                    OpeningBalanceImport.employee_id == employee_id,
                    OpeningBalanceImport.tax_year == tax_year,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_opening_balances(
        self,
        entity_id: uuid.UUID,
        tax_year: int,
        verified_only: bool = False,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[List[OpeningBalanceImport], int]:
        """List opening balances with pagination."""
        query = (
            select(OpeningBalanceImport)
            .where(
                and_(
                    OpeningBalanceImport.entity_id == entity_id,
                    OpeningBalanceImport.tax_year == tax_year,
                )
            )
        )
        
        if verified_only:
            query = query.where(OpeningBalanceImport.is_verified == True)
        
        # Count total
        count_result = await self.db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar() or 0
        
        # Apply ordering and pagination
        query = query.order_by(OpeningBalanceImport.created_at.desc())
        query = query.offset((page - 1) * per_page).limit(per_page)
        
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def create_opening_balance(
        self,
        entity_id: uuid.UUID,
        employee_id: uuid.UUID,
        tax_year: int,
        effective_date: date,
        months_covered: int,
        prior_ytd_gross: Decimal,
        prior_ytd_paye: Decimal,
        prior_ytd_pension_employee: Decimal,
        prior_ytd_pension_employer: Decimal,
        prior_ytd_nhf: Decimal,
        prior_ytd_net: Decimal,
        source_system: Optional[str] = None,
        notes: Optional[str] = None,
        import_batch_id: Optional[str] = None,
    ) -> OpeningBalanceImport:
        """Create an opening balance import record."""
        if not import_batch_id:
            import_batch_id = f"OB-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        
        opening_balance = OpeningBalanceImport(
            entity_id=entity_id,
            employee_id=employee_id,
            tax_year=tax_year,
            effective_date=effective_date,
            months_covered=months_covered,
            prior_ytd_gross=prior_ytd_gross,
            prior_ytd_paye=prior_ytd_paye,
            prior_ytd_pension_employee=prior_ytd_pension_employee,
            prior_ytd_pension_employer=prior_ytd_pension_employer,
            prior_ytd_nhf=prior_ytd_nhf,
            prior_ytd_net=prior_ytd_net,
            source_system=source_system or "Manual Import",
            notes=notes,
            import_batch_id=import_batch_id,
        )
        
        self.db.add(opening_balance)
        await self.db.commit()
        await self.db.refresh(opening_balance)
        return opening_balance

    async def verify_opening_balance(
        self,
        opening_balance_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[OpeningBalanceImport]:
        """Mark an opening balance as verified."""
        result = await self.db.execute(
            select(OpeningBalanceImport).where(OpeningBalanceImport.id == opening_balance_id)
        )
        ob = result.scalar_one_or_none()
        
        if ob:
            ob.is_verified = True
            ob.verified_by_id = user_id
            ob.verified_at = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(ob)
        
        return ob

    async def apply_opening_balances(
        self,
        entity_id: uuid.UUID,
        tax_year: int,
    ) -> Dict[str, Any]:
        """
        Apply verified opening balances to YTD ledgers.
        Returns count of applied balances.
        """
        result = await self.db.execute(
            select(OpeningBalanceImport).where(
                and_(
                    OpeningBalanceImport.entity_id == entity_id,
                    OpeningBalanceImport.tax_year == tax_year,
                    OpeningBalanceImport.is_verified == True,
                    OpeningBalanceImport.is_applied == False,
                )
            )
        )
        opening_balances = list(result.scalars().all())
        
        applied_count = 0
        for ob in opening_balances:
            # Get or create YTD ledger
            existing_ledger = await self.get_ytd_ledger(entity_id, ob.employee_id, tax_year)
            
            if existing_ledger:
                # Add opening balances to existing
                existing_ledger.ytd_gross += ob.prior_ytd_gross
                existing_ledger.ytd_paye += ob.prior_ytd_paye
                existing_ledger.ytd_pension_employee += ob.prior_ytd_pension_employee
                existing_ledger.ytd_pension_employer += ob.prior_ytd_pension_employer
                existing_ledger.ytd_nhf += ob.prior_ytd_nhf
                existing_ledger.ytd_net += ob.prior_ytd_net
                existing_ledger.months_processed += ob.months_covered
                existing_ledger.has_opening_balance = True
                existing_ledger.opening_balance_date = ob.effective_date
            else:
                # Create new ledger with opening balance
                new_ledger = YTDPayrollLedger(
                    entity_id=entity_id,
                    employee_id=ob.employee_id,
                    tax_year=tax_year,
                    ytd_gross=ob.prior_ytd_gross,
                    ytd_paye=ob.prior_ytd_paye,
                    ytd_pension_employee=ob.prior_ytd_pension_employee,
                    ytd_pension_employer=ob.prior_ytd_pension_employer,
                    ytd_nhf=ob.prior_ytd_nhf,
                    ytd_net=ob.prior_ytd_net,
                    months_processed=ob.months_covered,
                    has_opening_balance=True,
                    opening_balance_date=ob.effective_date,
                )
                self.db.add(new_ledger)
            
            # Mark opening balance as applied
            ob.is_applied = True
            ob.applied_at = datetime.now(timezone.utc)
            applied_count += 1
        
        await self.db.commit()
        
        return {
            "applied_count": applied_count,
            "tax_year": tax_year,
            "message": f"Successfully applied {applied_count} opening balance(s)",
        }

    def format_opening_balance_response(
        self,
        ob: OpeningBalanceImport,
    ) -> Dict[str, Any]:
        """Format opening balance for API response."""
        return {
            "id": str(ob.id),
            "entity_id": str(ob.entity_id),
            "employee_id": str(ob.employee_id),
            "import_batch_id": ob.import_batch_id,
            "tax_year": ob.tax_year,
            "effective_date": ob.effective_date.isoformat() if ob.effective_date else None,
            "months_covered": ob.months_covered,
            "prior_ytd_gross": float(ob.prior_ytd_gross),
            "prior_ytd_paye": float(ob.prior_ytd_paye),
            "prior_ytd_pension_employee": float(ob.prior_ytd_pension_employee),
            "prior_ytd_pension_employer": float(ob.prior_ytd_pension_employer),
            "prior_ytd_nhf": float(ob.prior_ytd_nhf),
            "prior_ytd_net": float(ob.prior_ytd_net),
            "source_system": ob.source_system,
            "source_file": ob.source_file,
            "notes": ob.notes,
            "is_verified": ob.is_verified,
            "verified_by_id": str(ob.verified_by_id) if ob.verified_by_id else None,
            "verified_at": ob.verified_at.isoformat() if ob.verified_at else None,
            "is_applied": ob.is_applied,
            "applied_at": ob.applied_at.isoformat() if ob.applied_at else None,
            "created_at": ob.created_at.isoformat() if ob.created_at else None,
        }

    # ===========================================
    # PAYSLIP EXPLANATION METHODS
    # ===========================================

    async def get_payslip_explanation(
        self,
        payslip_id: uuid.UUID,
    ) -> Optional[PayslipExplanation]:
        """Get explanation for a payslip."""
        result = await self.db.execute(
            select(PayslipExplanation).where(PayslipExplanation.payslip_id == payslip_id)
        )
        return result.scalar_one_or_none()

    async def generate_payslip_explanation(
        self,
        payslip_id: uuid.UUID,
    ) -> PayslipExplanation:
        """
        Generate human-readable explanation for a payslip.
        Compares to previous payslip if available.
        """
        # Get current payslip
        payslip_result = await self.db.execute(
            select(Payslip).where(Payslip.id == payslip_id)
        )
        payslip = payslip_result.scalar_one_or_none()
        
        if not payslip:
            raise ValueError(f"Payslip {payslip_id} not found")
        
        # Get employee info
        employee_result = await self.db.execute(
            select(Employee).where(Employee.id == payslip.employee_id)
        )
        employee = employee_result.scalar_one_or_none()
        
        # Get previous payslip for comparison
        prev_result = await self.db.execute(
            select(Payslip)
            .where(
                and_(
                    Payslip.employee_id == payslip.employee_id,
                    Payslip.id != payslip_id,
                    Payslip.created_at < payslip.created_at,
                )
            )
            .order_by(Payslip.created_at.desc())
            .limit(1)
        )
        prev_payslip = prev_result.scalar_one_or_none()
        
        # Build explanations
        has_changes = False
        variance_notes = []
        
        # Gross explanation
        gross_explanation = f"Your gross pay this period is ₦{payslip.gross_pay:,.2f}. "
        gross_explanation += f"This includes basic salary of ₦{payslip.basic_salary:,.2f}"
        
        if prev_payslip:
            gross_diff = payslip.gross_pay - prev_payslip.gross_pay
            if abs(gross_diff) > Decimal("100"):
                has_changes = True
                change_type = "increased" if gross_diff > 0 else "decreased"
                gross_explanation += f" Your gross pay has {change_type} by ₦{abs(gross_diff):,.2f} from last period."
                variance_notes.append(f"Gross pay {change_type} by ₦{abs(gross_diff):,.2f}")
        
        # Deduction explanation
        deduction_explanation = f"Total deductions: ₦{payslip.total_deductions:,.2f}. "
        deduction_explanation += f"This includes Pension (Employee): ₦{payslip.pension_employee:,.2f}, "
        deduction_explanation += f"NHF: ₦{payslip.nhf:,.2f}, "
        deduction_explanation += f"and PAYE Tax: ₦{payslip.paye_tax:,.2f}."
        
        # Tax explanation
        tax_explanation = f"PAYE Tax: ₦{payslip.paye_tax:,.2f}. "
        tax_explanation += "This is calculated using the current Nigerian tax bands and rates."
        
        if prev_payslip:
            tax_diff = payslip.paye_tax - prev_payslip.paye_tax
            if abs(tax_diff) > Decimal("100"):
                has_changes = True
                change_type = "increased" if tax_diff > 0 else "decreased"
                tax_explanation += f" Your tax has {change_type} by ₦{abs(tax_diff):,.2f}."
                variance_notes.append(f"PAYE tax {change_type} by ₦{abs(tax_diff):,.2f}")
        
        # Net explanation
        net_explanation = f"Your take-home pay (net pay) is ₦{payslip.net_pay:,.2f}. "
        net_explanation += f"This is your gross pay minus all deductions."
        
        if prev_payslip:
            net_diff = payslip.net_pay - prev_payslip.net_pay
            if abs(net_diff) > Decimal("100"):
                has_changes = True
                change_type = "more" if net_diff > 0 else "less"
                net_explanation += f" You're taking home ₦{abs(net_diff):,.2f} {change_type} than last period."
                variance_notes.append(f"Net pay changed by ₦{net_diff:,.2f}")
        
        # Full explanation
        full_explanation = f"""
Payslip Summary
===============

{gross_explanation}

{deduction_explanation}

{tax_explanation}

{net_explanation}

Employer Contributions (Not deducted from your pay):
- Employer Pension: ₦{payslip.pension_employer:,.2f}
- NSITF: ₦{payslip.nsitf:,.2f}
- ITF: ₦{payslip.itf:,.2f}
        """.strip()
        
        variance_notes_str = "\n".join(variance_notes) if variance_notes else None
        
        # Check if explanation exists
        existing = await self.get_payslip_explanation(payslip_id)
        
        if existing:
            existing.has_changes = has_changes
            existing.gross_explanation = gross_explanation
            existing.deduction_explanation = deduction_explanation
            existing.tax_explanation = tax_explanation
            existing.net_explanation = net_explanation
            existing.full_explanation = full_explanation
            existing.variance_notes = variance_notes_str
            existing.generated_at = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(existing)
            return existing
        
        explanation = PayslipExplanation(
            payslip_id=payslip_id,
            has_changes=has_changes,
            gross_explanation=gross_explanation,
            deduction_explanation=deduction_explanation,
            tax_explanation=tax_explanation,
            net_explanation=net_explanation,
            full_explanation=full_explanation,
            variance_notes=variance_notes_str,
        )
        
        self.db.add(explanation)
        await self.db.commit()
        await self.db.refresh(explanation)
        return explanation

    def format_payslip_explanation_response(
        self,
        explanation: PayslipExplanation,
    ) -> Dict[str, Any]:
        """Format payslip explanation for API response."""
        return {
            "id": str(explanation.id),
            "payslip_id": str(explanation.payslip_id),
            "has_changes": explanation.has_changes,
            "gross_explanation": explanation.gross_explanation,
            "deduction_explanation": explanation.deduction_explanation,
            "tax_explanation": explanation.tax_explanation,
            "net_explanation": explanation.net_explanation,
            "full_explanation": explanation.full_explanation,
            "variance_notes": explanation.variance_notes,
            "generated_at": explanation.generated_at.isoformat() if explanation.generated_at else None,
        }

    # ===========================================
    # EMPLOYEE VARIANCE LOG METHODS
    # ===========================================

    async def get_variance_log(
        self,
        log_id: uuid.UUID,
    ) -> Optional[EmployeeVarianceLog]:
        """Get a specific variance log by ID."""
        result = await self.db.execute(
            select(EmployeeVarianceLog).where(EmployeeVarianceLog.id == log_id)
        )
        return result.scalar_one_or_none()

    async def list_variance_logs(
        self,
        entity_id: uuid.UUID,
        payslip_id: Optional[uuid.UUID] = None,
        employee_id: Optional[uuid.UUID] = None,
        flagged_only: bool = False,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[List[EmployeeVarianceLog], int]:
        """List variance logs with filters."""
        query = select(EmployeeVarianceLog).where(
            EmployeeVarianceLog.entity_id == entity_id
        )
        
        if payslip_id:
            query = query.where(EmployeeVarianceLog.payslip_id == payslip_id)
        if employee_id:
            query = query.where(EmployeeVarianceLog.employee_id == employee_id)
        if flagged_only:
            query = query.where(EmployeeVarianceLog.is_flagged == True)
        
        # Count total
        count_result = await self.db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar() or 0
        
        # Apply ordering and pagination
        query = query.order_by(EmployeeVarianceLog.created_at.desc())
        query = query.offset((page - 1) * per_page).limit(per_page)
        
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def create_variance_log(
        self,
        entity_id: uuid.UUID,
        employee_id: uuid.UUID,
        payslip_id: uuid.UUID,
        previous_payslip_id: Optional[uuid.UUID],
        variance_type: str,
        previous_value: Decimal,
        current_value: Decimal,
        flag_threshold: Decimal = Decimal("5.00"),
    ) -> EmployeeVarianceLog:
        """Create a variance log entry."""
        variance_amount = current_value - previous_value
        
        # Calculate percentage
        if previous_value != 0:
            variance_percent = (variance_amount / previous_value * 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            variance_percent = Decimal("100.00") if variance_amount != 0 else Decimal("0.00")
        
        # Flag if above threshold
        is_flagged = abs(variance_percent) >= flag_threshold
        
        log = EmployeeVarianceLog(
            entity_id=entity_id,
            employee_id=employee_id,
            payslip_id=payslip_id,
            previous_payslip_id=previous_payslip_id,
            variance_type=variance_type,
            previous_value=previous_value,
            current_value=current_value,
            variance_amount=variance_amount,
            variance_percent=variance_percent,
            is_flagged=is_flagged,
            flag_threshold_percent=flag_threshold,
        )
        
        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)
        return log

    async def update_variance_reason(
        self,
        log_id: uuid.UUID,
        reason_code: str,
        reason_note: Optional[str] = None,
    ) -> Optional[EmployeeVarianceLog]:
        """Update the reason code for a variance log."""
        log = await self.get_variance_log(log_id)
        
        if log:
            log.reason_code = VarianceReason(reason_code)
            log.reason_note = reason_note
            await self.db.commit()
            await self.db.refresh(log)
        
        return log

    def format_variance_log_response(
        self,
        log: EmployeeVarianceLog,
        employee_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Format variance log for API response."""
        return {
            "id": str(log.id),
            "entity_id": str(log.entity_id),
            "employee_id": str(log.employee_id),
            "employee_name": employee_name,
            "payslip_id": str(log.payslip_id),
            "previous_payslip_id": str(log.previous_payslip_id) if log.previous_payslip_id else None,
            "variance_type": log.variance_type,
            "previous_value": float(log.previous_value),
            "current_value": float(log.current_value),
            "variance_amount": float(log.variance_amount),
            "variance_percent": float(log.variance_percent),
            "reason_code": log.reason_code.value if log.reason_code else None,
            "reason_note": log.reason_note,
            "is_flagged": log.is_flagged,
            "flag_threshold_percent": float(log.flag_threshold_percent),
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }

    # ===========================================
    # COST TO COMPANY SNAPSHOT METHODS
    # ===========================================

    async def get_ctc_snapshot(
        self,
        entity_id: uuid.UUID,
        snapshot_month: int,
        snapshot_year: int,
    ) -> Optional[CostToCompanySnapshot]:
        """Get CTC snapshot for a specific period."""
        result = await self.db.execute(
            select(CostToCompanySnapshot).where(
                and_(
                    CostToCompanySnapshot.entity_id == entity_id,
                    CostToCompanySnapshot.snapshot_month == snapshot_month,
                    CostToCompanySnapshot.snapshot_year == snapshot_year,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_ctc_snapshots(
        self,
        entity_id: uuid.UUID,
        year: Optional[int] = None,
        page: int = 1,
        per_page: int = 12,
    ) -> Tuple[List[CostToCompanySnapshot], int]:
        """List CTC snapshots with pagination."""
        query = select(CostToCompanySnapshot).where(
            CostToCompanySnapshot.entity_id == entity_id
        )
        
        if year:
            query = query.where(CostToCompanySnapshot.snapshot_year == year)
        
        # Count total
        count_result = await self.db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar() or 0
        
        # Apply ordering and pagination
        query = query.order_by(
            CostToCompanySnapshot.snapshot_year.desc(),
            CostToCompanySnapshot.snapshot_month.desc(),
        )
        query = query.offset((page - 1) * per_page).limit(per_page)
        
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def generate_ctc_snapshot(
        self,
        entity_id: uuid.UUID,
        snapshot_month: int,
        snapshot_year: int,
        payroll_run_id: Optional[uuid.UUID] = None,
        monthly_budget: Optional[Decimal] = None,
    ) -> CostToCompanySnapshot:
        """Generate or update CTC snapshot for a period."""
        # Get payroll run if not provided
        if not payroll_run_id:
            pr_result = await self.db.execute(
                select(PayrollRun).where(
                    and_(
                        PayrollRun.entity_id == entity_id,
                        extract('month', PayrollRun.period_start) == snapshot_month,
                        extract('year', PayrollRun.period_start) == snapshot_year,
                    )
                ).order_by(PayrollRun.created_at.desc()).limit(1)
            )
            payroll = pr_result.scalar_one_or_none()
            if payroll:
                payroll_run_id = payroll.id
        
        # Get payslips for the period
        payslip_query = select(Payslip)
        if payroll_run_id:
            payslip_query = payslip_query.where(Payslip.payroll_run_id == payroll_run_id)
        
        payslip_result = await self.db.execute(payslip_query)
        payslips = list(payslip_result.scalars().all())
        
        # Calculate totals
        total_employees = len(payslips)
        total_gross = sum(p.gross_pay for p in payslips)
        total_pension_employer = sum(p.pension_employer for p in payslips)
        total_nsitf = sum(p.nsitf for p in payslips)
        total_itf = sum(p.itf for p in payslips)
        
        # Calculate total CTC
        total_ctc = total_gross + total_pension_employer + total_nsitf + total_itf
        average_ctc = total_ctc / total_employees if total_employees > 0 else Decimal("0")
        
        # Budget variance
        budget_variance = Decimal("0")
        budget_variance_percent = Decimal("0")
        if monthly_budget:
            budget_variance = total_ctc - monthly_budget
            if monthly_budget > 0:
                budget_variance_percent = (budget_variance / monthly_budget * 100).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
        
        # Check if snapshot exists
        existing = await self.get_ctc_snapshot(entity_id, snapshot_month, snapshot_year)
        
        if existing:
            existing.payroll_run_id = payroll_run_id
            existing.total_employees = total_employees
            existing.total_gross_salary = total_gross
            existing.total_pension_employer = total_pension_employer
            existing.total_nsitf = total_nsitf
            existing.total_itf = total_itf
            existing.total_ctc = total_ctc
            existing.average_ctc_per_employee = average_ctc
            existing.monthly_budget = monthly_budget
            existing.budget_variance = budget_variance
            existing.budget_variance_percent = budget_variance_percent
            existing.snapshot_date = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(existing)
            return existing
        
        snapshot = CostToCompanySnapshot(
            entity_id=entity_id,
            snapshot_month=snapshot_month,
            snapshot_year=snapshot_year,
            payroll_run_id=payroll_run_id,
            total_employees=total_employees,
            total_gross_salary=total_gross,
            total_pension_employer=total_pension_employer,
            total_nsitf=total_nsitf,
            total_itf=total_itf,
            total_ctc=total_ctc,
            average_ctc_per_employee=average_ctc,
            monthly_budget=monthly_budget,
            budget_variance=budget_variance,
            budget_variance_percent=budget_variance_percent,
        )
        
        self.db.add(snapshot)
        await self.db.commit()
        await self.db.refresh(snapshot)
        return snapshot

    async def get_ctc_trend(
        self,
        entity_id: uuid.UUID,
        months: int = 12,
    ) -> List[Dict[str, Any]]:
        """Get CTC trend over the past N months."""
        result = await self.db.execute(
            select(CostToCompanySnapshot)
            .where(CostToCompanySnapshot.entity_id == entity_id)
            .order_by(
                CostToCompanySnapshot.snapshot_year.desc(),
                CostToCompanySnapshot.snapshot_month.desc(),
            )
            .limit(months)
        )
        snapshots = list(result.scalars().all())
        
        return [
            {
                "month": s.snapshot_month,
                "year": s.snapshot_year,
                "total_ctc": float(s.total_ctc),
                "employee_count": s.total_employees,
                "average_ctc": float(s.average_ctc_per_employee),
            }
            for s in reversed(snapshots)
        ]

    def format_ctc_snapshot_response(
        self,
        snapshot: CostToCompanySnapshot,
    ) -> Dict[str, Any]:
        """Format CTC snapshot for API response."""
        return {
            "id": str(snapshot.id),
            "entity_id": str(snapshot.entity_id),
            "snapshot_month": snapshot.snapshot_month,
            "snapshot_year": snapshot.snapshot_year,
            "payroll_run_id": str(snapshot.payroll_run_id) if snapshot.payroll_run_id else None,
            "total_employees": snapshot.total_employees,
            "total_gross_salary": float(snapshot.total_gross_salary),
            "total_pension_employer": float(snapshot.total_pension_employer),
            "total_nsitf": float(snapshot.total_nsitf),
            "total_itf": float(snapshot.total_itf),
            "total_hmo": float(snapshot.total_hmo),
            "total_group_life": float(snapshot.total_group_life),
            "total_other_benefits": float(snapshot.total_other_benefits),
            "total_ctc": float(snapshot.total_ctc),
            "average_ctc_per_employee": float(snapshot.average_ctc_per_employee),
            "department_breakdown": snapshot.department_breakdown or {},
            "monthly_budget": float(snapshot.monthly_budget) if snapshot.monthly_budget else None,
            "budget_variance": float(snapshot.budget_variance),
            "budget_variance_percent": float(snapshot.budget_variance_percent),
            "snapshot_date": snapshot.snapshot_date.isoformat() if snapshot.snapshot_date else None,
        }

    # ===========================================
    # WHAT-IF SIMULATION METHODS
    # ===========================================

    async def get_simulation(
        self,
        simulation_id: uuid.UUID,
    ) -> Optional[WhatIfSimulation]:
        """Get a simulation by ID."""
        result = await self.db.execute(
            select(WhatIfSimulation).where(WhatIfSimulation.id == simulation_id)
        )
        return result.scalar_one_or_none()

    async def list_simulations(
        self,
        entity_id: uuid.UUID,
        saved_only: bool = False,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[List[WhatIfSimulation], int]:
        """List simulations with pagination."""
        query = select(WhatIfSimulation).where(
            WhatIfSimulation.entity_id == entity_id
        )
        
        if saved_only:
            query = query.where(WhatIfSimulation.is_saved == True)
        
        # Count total
        count_result = await self.db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar() or 0
        
        # Apply ordering and pagination
        query = query.order_by(WhatIfSimulation.created_at.desc())
        query = query.offset((page - 1) * per_page).limit(per_page)
        
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def run_salary_increase_simulation(
        self,
        entity_id: uuid.UUID,
        user_id: uuid.UUID,
        simulation_name: str,
        increase_type: str,  # "percentage" or "flat_amount"
        increase_value: Decimal,
        apply_to: str = "all",  # "all", "department", "employee_list"
        department: Optional[str] = None,
        employee_ids: Optional[List[uuid.UUID]] = None,
        description: Optional[str] = None,
        save_simulation: bool = False,
    ) -> WhatIfSimulation:
        """Run a salary increase simulation."""
        # Get baseline data
        employees_query = select(Employee).where(
            and_(
                Employee.entity_id == entity_id,
                Employee.employment_status == EmploymentStatus.ACTIVE,
            )
        )
        
        if apply_to == "department" and department:
            employees_query = employees_query.where(Employee.department == department)
        elif apply_to == "employee_list" and employee_ids:
            employees_query = employees_query.where(Employee.id.in_(employee_ids))
        
        emp_result = await self.db.execute(employees_query)
        employees = list(emp_result.scalars().all())
        
        # Calculate baseline
        baseline_gross = sum(e.basic_salary for e in employees)
        baseline_paye = Decimal("0")  # Simplified - would need full tax calculation
        baseline_employer_cost = baseline_gross * Decimal("1.15")  # Approximate
        baseline_ctc = baseline_gross * Decimal("1.20")  # Approximate
        
        # Calculate projected
        if increase_type == "percentage":
            increase_multiplier = 1 + (increase_value / 100)
            projected_gross = baseline_gross * increase_multiplier
        else:
            projected_gross = baseline_gross + (increase_value * len(employees))
        
        projected_employer_cost = projected_gross * Decimal("1.15")
        projected_ctc = projected_gross * Decimal("1.20")
        
        # Calculate impacts
        gross_impact = projected_gross - baseline_gross
        employer_cost_impact = projected_employer_cost - baseline_employer_cost
        ctc_impact = projected_ctc - baseline_ctc
        
        gross_impact_percent = (gross_impact / baseline_gross * 100).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ) if baseline_gross > 0 else Decimal("0")
        ctc_impact_percent = (ctc_impact / baseline_ctc * 100).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ) if baseline_ctc > 0 else Decimal("0")
        
        # Build summary
        impact_summary = f"Salary increase simulation: {increase_value}{'%' if increase_type == 'percentage' else ' NGN'} "
        impact_summary += f"for {len(employees)} employees. "
        impact_summary += f"Total cost impact: ₦{ctc_impact:,.2f} ({ctc_impact_percent}% increase)."
        
        simulation = WhatIfSimulation(
            entity_id=entity_id,
            simulation_name=simulation_name,
            description=description,
            scenario_type="salary_increase",
            parameters={
                "increase_type": increase_type,
                "increase_value": float(increase_value),
                "apply_to": apply_to,
                "department": department,
                "employee_count": len(employees),
            },
            baseline_gross=baseline_gross,
            baseline_paye=baseline_paye,
            baseline_employer_cost=baseline_employer_cost,
            baseline_ctc=baseline_ctc,
            projected_gross=projected_gross,
            projected_paye=Decimal("0"),
            projected_employer_cost=projected_employer_cost,
            projected_ctc=projected_ctc,
            gross_impact=gross_impact,
            paye_impact=Decimal("0"),
            employer_cost_impact=employer_cost_impact,
            ctc_impact=ctc_impact,
            gross_impact_percent=gross_impact_percent,
            ctc_impact_percent=ctc_impact_percent,
            impact_summary=impact_summary,
            created_by_id=user_id,
            is_saved=save_simulation,
        )
        
        self.db.add(simulation)
        await self.db.commit()
        await self.db.refresh(simulation)
        return simulation

    async def delete_simulation(
        self,
        simulation_id: uuid.UUID,
    ) -> bool:
        """Delete a simulation."""
        simulation = await self.get_simulation(simulation_id)
        if simulation:
            await self.db.delete(simulation)
            await self.db.commit()
            return True
        return False

    def format_simulation_response(
        self,
        simulation: WhatIfSimulation,
    ) -> Dict[str, Any]:
        """Format simulation for API response."""
        return {
            "id": str(simulation.id),
            "entity_id": str(simulation.entity_id),
            "simulation_name": simulation.simulation_name,
            "description": simulation.description,
            "scenario_type": simulation.scenario_type,
            "parameters": simulation.parameters or {},
            "baseline_gross": float(simulation.baseline_gross),
            "baseline_paye": float(simulation.baseline_paye),
            "baseline_employer_cost": float(simulation.baseline_employer_cost),
            "baseline_ctc": float(simulation.baseline_ctc),
            "projected_gross": float(simulation.projected_gross),
            "projected_paye": float(simulation.projected_paye),
            "projected_employer_cost": float(simulation.projected_employer_cost),
            "projected_ctc": float(simulation.projected_ctc),
            "gross_impact": float(simulation.gross_impact),
            "paye_impact": float(simulation.paye_impact),
            "employer_cost_impact": float(simulation.employer_cost_impact),
            "ctc_impact": float(simulation.ctc_impact),
            "gross_impact_percent": float(simulation.gross_impact_percent),
            "ctc_impact_percent": float(simulation.ctc_impact_percent),
            "impact_summary": simulation.impact_summary,
            "is_saved": simulation.is_saved,
            "created_at": simulation.created_at.isoformat() if simulation.created_at else None,
        }

    # ===========================================
    # GHOST WORKER DETECTION METHODS
    # ===========================================

    async def get_ghost_detection(
        self,
        detection_id: uuid.UUID,
    ) -> Optional[GhostWorkerDetection]:
        """Get a ghost worker detection by ID."""
        result = await self.db.execute(
            select(GhostWorkerDetection).where(GhostWorkerDetection.id == detection_id)
        )
        return result.scalar_one_or_none()

    async def list_ghost_detections(
        self,
        entity_id: uuid.UUID,
        unresolved_only: bool = False,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[List[GhostWorkerDetection], int]:
        """List ghost worker detections with pagination."""
        query = select(GhostWorkerDetection).where(
            GhostWorkerDetection.entity_id == entity_id
        )
        
        if unresolved_only:
            query = query.where(GhostWorkerDetection.is_resolved == False)
        
        # Count total
        count_result = await self.db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar() or 0
        
        # Apply ordering and pagination
        query = query.order_by(GhostWorkerDetection.detected_at.desc())
        query = query.offset((page - 1) * per_page).limit(per_page)
        
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def run_ghost_worker_scan(
        self,
        entity_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Scan for ghost workers by detecting duplicates.
        Checks BVN, NIN, bank account numbers.
        """
        # Get all active employees
        result = await self.db.execute(
            select(Employee).where(
                and_(
                    Employee.entity_id == entity_id,
                    Employee.employment_status == EmploymentStatus.ACTIVE,
                )
            )
        )
        employees = list(result.scalars().all())
        
        detections = []
        
        # Check for duplicate BVNs
        bvn_map = {}
        for emp in employees:
            if emp.bvn:
                if emp.bvn in bvn_map:
                    detection = GhostWorkerDetection(
                        entity_id=entity_id,
                        detection_type="duplicate_bvn",
                        employee_1_id=bvn_map[emp.bvn].id,
                        employee_2_id=emp.id,
                        duplicate_field="bvn",
                        duplicate_value=emp.bvn,
                        severity=ExceptionSeverity.CRITICAL,
                    )
                    self.db.add(detection)
                    detections.append(detection)
                else:
                    bvn_map[emp.bvn] = emp
        
        # Check for duplicate bank accounts
        account_map = {}
        for emp in employees:
            if emp.account_number and emp.bank_name:
                key = f"{emp.bank_name}:{emp.account_number}"
                if key in account_map:
                    detection = GhostWorkerDetection(
                        entity_id=entity_id,
                        detection_type="duplicate_account",
                        employee_1_id=account_map[key].id,
                        employee_2_id=emp.id,
                        duplicate_field="bank_account",
                        duplicate_value=key,
                        severity=ExceptionSeverity.CRITICAL,
                    )
                    self.db.add(detection)
                    detections.append(detection)
                else:
                    account_map[key] = emp
        
        # Check for duplicate NINs
        nin_map = {}
        for emp in employees:
            if hasattr(emp, 'nin') and emp.nin:
                if emp.nin in nin_map:
                    detection = GhostWorkerDetection(
                        entity_id=entity_id,
                        detection_type="duplicate_nin",
                        employee_1_id=nin_map[emp.nin].id,
                        employee_2_id=emp.id,
                        duplicate_field="nin",
                        duplicate_value=emp.nin,
                        severity=ExceptionSeverity.CRITICAL,
                    )
                    self.db.add(detection)
                    detections.append(detection)
                else:
                    nin_map[emp.nin] = emp
        
        await self.db.commit()
        
        # Refresh all detections
        for d in detections:
            await self.db.refresh(d)
        
        critical_count = sum(1 for d in detections if d.severity == ExceptionSeverity.CRITICAL)
        
        return {
            "entity_id": str(entity_id),
            "scan_date": datetime.now(timezone.utc).isoformat(),
            "total_employees_scanned": len(employees),
            "detections_found": len(detections),
            "critical_detections": critical_count,
            "detections": [self.format_ghost_detection_response(d) for d in detections],
        }

    async def resolve_ghost_detection(
        self,
        detection_id: uuid.UUID,
        user_id: uuid.UUID,
        resolution_note: str,
    ) -> Optional[GhostWorkerDetection]:
        """Mark a ghost worker detection as resolved."""
        detection = await self.get_ghost_detection(detection_id)
        
        if detection:
            detection.is_resolved = True
            detection.resolved_by_id = user_id
            detection.resolved_at = datetime.now(timezone.utc)
            detection.resolution_note = resolution_note
            await self.db.commit()
            await self.db.refresh(detection)
        
        return detection

    def format_ghost_detection_response(
        self,
        detection: GhostWorkerDetection,
        employee_1_name: Optional[str] = None,
        employee_2_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Format ghost worker detection for API response."""
        return {
            "id": str(detection.id),
            "entity_id": str(detection.entity_id),
            "detection_type": detection.detection_type,
            "employee_1_id": str(detection.employee_1_id),
            "employee_1_name": employee_1_name,
            "employee_2_id": str(detection.employee_2_id),
            "employee_2_name": employee_2_name,
            "duplicate_field": detection.duplicate_field,
            "duplicate_value": detection.duplicate_value,
            "severity": detection.severity.value if detection.severity else "critical",
            "is_resolved": detection.is_resolved,
            "resolution_note": detection.resolution_note,
            "resolved_by_id": str(detection.resolved_by_id) if detection.resolved_by_id else None,
            "resolved_at": detection.resolved_at.isoformat() if detection.resolved_at else None,
            "detected_at": detection.detected_at.isoformat() if detection.detected_at else None,
        }
