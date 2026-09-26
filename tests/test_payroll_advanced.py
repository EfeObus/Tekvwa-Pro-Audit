"""
Regression coverage for Finding 50's payroll_advanced.py column drift
(docs/FINDING_50_SCOPE.md, docs/REMEDIATION_LOG.md).

app/services/payroll_advanced_service.py -- the only real construction site for every model in
this file -- already used each model's own field names, none of which existed on the live
tables. Several tables showed a deeper pattern than a simple rename: the live table implemented a
genuinely different design (e.g. compliance_snapshots was one row per remittance type in the DB
vs. one row per period covering all remittance types in the model and real usage). These tests
are direct ORM round-trips confirming the model's real column set now matches the live schema for
all 11 tables, plus two service-level tests for the specific behavioral fixes made along the way
(PayrollException.entity_id wiring, EmployeeVarianceLog.reason_code wiring).
"""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import BusinessEntity
from app.models.payroll import Employee, Payslip, PayrollFrequency, PayrollRun, PayrollStatus
from app.models.payroll_advanced import (
    ComplianceSnapshot,
    ComplianceStatus,
    CostToCompanySnapshot,
    EmployeeVarianceLog,
    ExceptionCode,
    ExceptionSeverity,
    GhostWorkerDetection,
    OpeningBalanceImport,
    PayrollDecisionLog,
    PayrollException,
    PayslipExplanation,
    VarianceReason,
    WhatIfSimulation,
    YTDPayrollLedger,
)
from app.models.user import User
from app.services.payroll_advanced_service import PayrollAdvancedService


async def _make_employee(db_session: AsyncSession, entity: BusinessEntity, staff_no: str) -> Employee:
    employee = Employee(
        entity_id=entity.id,
        employee_id=staff_no,
        first_name="Chidi",
        last_name="Eze",
        email=f"{staff_no.lower()}@example.com",
        hire_date=date(2024, 1, 1),
    )
    db_session.add(employee)
    await db_session.commit()
    await db_session.refresh(employee)
    return employee


async def _make_payslip(
    db_session: AsyncSession, payroll_run: PayrollRun, employee: Employee, number: str,
) -> Payslip:
    payslip = Payslip(
        payroll_run_id=payroll_run.id,
        employee_id=employee.id,
        payslip_number=number,
    )
    db_session.add(payslip)
    await db_session.commit()
    await db_session.refresh(payslip)
    return payslip


async def _make_payroll_run(db_session: AsyncSession, entity: BusinessEntity, code: str) -> PayrollRun:
    run = PayrollRun(
        entity_id=entity.id,
        payroll_code=code,
        name="September 2026 Payroll",
        frequency=PayrollFrequency.MONTHLY.value,
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
        payment_date=date(2026, 9, 28),
        status=PayrollStatus.DRAFT.value,
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    return run


class TestComplianceSnapshotPersistence:
    async def test_create_and_fetch(self, db_session: AsyncSession, test_entity: BusinessEntity):
        snapshot = ComplianceSnapshot(
            entity_id=test_entity.id,
            period_month=9,
            period_year=2026,
            paye_status=ComplianceStatus.OVERDUE,
            paye_amount_due=Decimal("50000.00"),
            pension_status=ComplianceStatus.ON_TIME,
            nhf_status=ComplianceStatus.NOT_DUE,
            nsitf_status=ComplianceStatus.NOT_DUE,
            itf_status=ComplianceStatus.NOT_DUE,
        )
        db_session.add(snapshot)
        await db_session.commit()
        await db_session.refresh(snapshot)

        assert snapshot.id is not None
        assert snapshot.paye_status == ComplianceStatus.OVERDUE
        assert snapshot.paye_amount_due == Decimal("50000.00")


class TestPayrollImpactPreviewPersistence:
    async def test_generate_impact_preview_derives_entity_id(
        self, db_session: AsyncSession, test_entity: BusinessEntity,
    ):
        """
        Regression test for a Finding 49 gap: the live table's entity_id column is NOT NULL, but
        the model never declared it at all, and generate_impact_preview() never set it either --
        every real call has always crashed with a NotNullViolation. An earlier version of this
        test constructed PayrollImpactPreview directly, bypassing generate_impact_preview()
        entirely, which is exactly why this went undetected. Calling the real service here.
        """
        run = await _make_payroll_run(db_session, test_entity, "PAY-2026-09")
        run.total_gross_pay = Decimal("1000000.00")
        run.total_net_pay = Decimal("800000.00")
        run.total_employees = 10
        await db_session.commit()

        service = PayrollAdvancedService(db_session)
        preview = await service.generate_impact_preview(
            entity_id=test_entity.id,
            payroll_run_id=run.id,
        )

        assert preview.id is not None
        assert preview.entity_id == test_entity.id
        assert preview.current_gross == Decimal("1000000.00")


class TestPayrollExceptionPersistence:
    async def test_create_exception_derives_entity_id(
        self, db_session: AsyncSession, test_entity: BusinessEntity,
    ):
        run = await _make_payroll_run(db_session, test_entity, "PAY-2026-10")
        service = PayrollAdvancedService(db_session)

        exception = await service.create_exception(
            payroll_run_id=run.id,
            exception_code=ExceptionCode.NEGATIVE_NET_PAY.value,
            severity=ExceptionSeverity.CRITICAL.value,
            title="Negative net pay detected",
            description="Employee's net pay is negative after deductions.",
            related_field="net_pay",
            current_value="-5000.00",
            expected_value=">= 0",
        )

        assert exception.id is not None
        assert exception.entity_id == test_entity.id
        assert exception.related_field == "net_pay"
        assert exception.requires_acknowledgement is True


class TestPayrollDecisionLogPersistence:
    async def test_create_decision_log(
        self, db_session: AsyncSession, test_entity: BusinessEntity, test_user: User,
    ):
        service = PayrollAdvancedService(db_session)
        log = await service.create_decision_log(
            entity_id=test_entity.id,
            decision_type="note",
            category="payroll",
            title="Manual adjustment approved",
            description="Approved a manual bonus adjustment for September payroll.",
            user_id=test_user.id,
            user_name="Efe Obukohwo",
            user_role="admin",
        )

        assert log.id is not None
        assert log.entity_id == test_entity.id
        assert log.updated_at is not None


class TestYTDPayrollLedgerPersistence:
    async def test_create_and_fetch(
        self, db_session: AsyncSession, test_entity: BusinessEntity,
    ):
        employee = await _make_employee(db_session, test_entity, "EMP-YTD1")
        ledger = YTDPayrollLedger(
            entity_id=test_entity.id,
            employee_id=employee.id,
            tax_year=2026,
            ytd_gross=Decimal("500000.00"),
            ytd_basic=Decimal("300000.00"),
            ytd_paye=Decimal("50000.00"),
            ytd_pension_employee=Decimal("24000.00"),
            ytd_pension_employer=Decimal("36000.00"),
            ytd_net=Decimal("420000.00"),
            months_processed=3,
        )
        db_session.add(ledger)
        await db_session.commit()
        await db_session.refresh(ledger)

        assert ledger.id is not None
        assert ledger.ytd_gross == Decimal("500000.00")
        assert ledger.months_processed == 3


class TestOpeningBalanceImportPersistence:
    async def test_create_and_fetch(
        self, db_session: AsyncSession, test_entity: BusinessEntity, test_user: User,
    ):
        employee = await _make_employee(db_session, test_entity, "EMP-OB1")
        service = PayrollAdvancedService(db_session)
        opening_balance = await service.create_opening_balance(
            entity_id=test_entity.id,
            employee_id=employee.id,
            tax_year=2026,
            effective_date=date(2026, 7, 1),
            months_covered=6,
            prior_ytd_gross=Decimal("600000.00"),
            prior_ytd_paye=Decimal("60000.00"),
            prior_ytd_pension_employee=Decimal("30000.00"),
            prior_ytd_pension_employer=Decimal("45000.00"),
            prior_ytd_nhf=Decimal("15000.00"),
            prior_ytd_net=Decimal("500000.00"),
        )

        assert opening_balance.id is not None
        assert opening_balance.created_at is not None
        assert opening_balance.prior_ytd_gross == Decimal("600000.00")


class TestPayslipExplanationPersistence:
    async def test_create_and_fetch(self, db_session: AsyncSession, test_entity: BusinessEntity):
        employee = await _make_employee(db_session, test_entity, "EMP-PSE1")
        run = await _make_payroll_run(db_session, test_entity, "PAY-2026-11")
        payslip = await _make_payslip(db_session, run, employee, "PS-2026-11-001")
        explanation = PayslipExplanation(
            payslip_id=payslip.id,
            has_changes=True,
            gross_explanation="Gross pay increased due to a housing allowance adjustment.",
            deduction_explanation="Pension contribution recalculated at 8%.",
            tax_explanation="PAYE recalculated per 2026 tax bands.",
            net_explanation="Net pay increased by NGN 12,000.",
            full_explanation="Full breakdown of this month's payslip changes.",
        )
        db_session.add(explanation)
        await db_session.commit()
        await db_session.refresh(explanation)

        assert explanation.id is not None
        assert explanation.has_changes is True
        assert explanation.updated_at is not None


class TestEmployeeVarianceLogPersistence:
    async def test_create_and_update_reason(
        self, db_session: AsyncSession, test_entity: BusinessEntity,
    ):
        employee = await _make_employee(db_session, test_entity, "EMP-VAR1")
        run = await _make_payroll_run(db_session, test_entity, "PAY-2026-12")
        payslip = await _make_payslip(db_session, run, employee, "PS-2026-12-001")
        log = EmployeeVarianceLog(
            entity_id=test_entity.id,
            employee_id=employee.id,
            payslip_id=payslip.id,
            variance_type="gross",
            previous_value=Decimal("100000.00"),
            current_value=Decimal("120000.00"),
            variance_amount=Decimal("20000.00"),
            variance_percent=Decimal("20.00"),
            is_flagged=True,
        )
        db_session.add(log)
        await db_session.commit()
        await db_session.refresh(log)

        service = PayrollAdvancedService(db_session)
        updated = await service.update_variance_reason(
            log_id=log.id, reason_code=VarianceReason.SALARY_INCREASE.value, reason_note="Annual raise",
        )

        assert updated.reason_code == VarianceReason.SALARY_INCREASE
        assert updated.reason_note == "Annual raise"


class TestCostToCompanySnapshotPersistence:
    async def test_create_and_fetch(self, db_session: AsyncSession, test_entity: BusinessEntity):
        snapshot = CostToCompanySnapshot(
            entity_id=test_entity.id,
            snapshot_month=9,
            snapshot_year=2026,
            total_employees=25,
            total_gross_salary=Decimal("12500000.00"),
            total_pension_employer=Decimal("900000.00"),
            total_ctc=Decimal("14000000.00"),
            average_ctc_per_employee=Decimal("560000.00"),
        )
        db_session.add(snapshot)
        await db_session.commit()
        await db_session.refresh(snapshot)

        assert snapshot.id is not None
        assert snapshot.total_employees == 25
        assert snapshot.updated_at is not None


class TestWhatIfSimulationPersistence:
    async def test_create_and_fetch(
        self, db_session: AsyncSession, test_entity: BusinessEntity, test_user: User,
    ):
        simulation = WhatIfSimulation(
            entity_id=test_entity.id,
            simulation_name="10% raise for engineering",
            scenario_type="salary_increase",
            parameters={"increase_type": "percentage", "increase_value": 10.0},
            baseline_gross=Decimal("5000000.00"),
            baseline_ctc=Decimal("5800000.00"),
            projected_gross=Decimal("5500000.00"),
            projected_ctc=Decimal("6300000.00"),
            gross_impact=Decimal("500000.00"),
            ctc_impact=Decimal("500000.00"),
            impact_summary="10% raise increases CTC by NGN 500,000.",
            created_by_id=test_user.id,
        )
        db_session.add(simulation)
        await db_session.commit()
        await db_session.refresh(simulation)

        assert simulation.id is not None
        assert simulation.is_saved is False
        assert simulation.parameters["increase_value"] == 10.0


class TestGhostWorkerDetectionPersistence:
    async def test_create_and_fetch(self, db_session: AsyncSession, test_entity: BusinessEntity):
        emp1 = await _make_employee(db_session, test_entity, "EMP-G1")
        emp2 = await _make_employee(db_session, test_entity, "EMP-G2")
        detection = GhostWorkerDetection(
            entity_id=test_entity.id,
            detection_type="duplicate_bvn",
            employee_1_id=emp1.id,
            employee_2_id=emp2.id,
            duplicate_field="bvn",
            duplicate_value="12345678901",
            severity=ExceptionSeverity.CRITICAL.value,
        )
        db_session.add(detection)
        await db_session.commit()
        await db_session.refresh(detection)

        assert detection.id is not None
        assert detection.employee_1_id == emp1.id
        assert detection.updated_at is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
