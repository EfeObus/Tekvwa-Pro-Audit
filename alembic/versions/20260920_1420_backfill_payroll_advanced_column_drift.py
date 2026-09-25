"""backfill_payroll_advanced_column_drift

Finding 50 (docs/FINDING_50_SCOPE.md): app/services/payroll_advanced_service.py (the only real
construction site for every model below) already used each model's own field names, none of
which existed on the live tables -- every real call has always failed with an
UndefinedColumnError. Several tables (compliance_snapshots, payroll_impact_previews, ctc_snapshots,
what_if_simulations, ghost_worker_detections, payslip_explanations) show a deeper pattern than a
simple rename: the live table implements a genuinely different design (e.g. compliance_snapshots
is one row per remittance type in the DB vs. one row per period covering all remittance types in
the model and in real usage; ctc_snapshots is per-employee in the DB vs. company-wide in the model
and real usage). In every case, the model's shape is what real code depends on, confirmed via
grep across the whole service file -- so this migration adds the model's real columns and relaxes
the live table's own now-orphaned NOT NULL columns to nullable (never dropped, per this session's
additive-only policy -- they stay in place, unmapped).

All 6 tables here are confirmed structurally unable to hold a row under the pre-fix code (each
table's own legacy NOT NULL columns, with no default, are never set by the only real construction
site), so no backfill is needed for anything added or relaxed here. payroll_decision_logs needed
no changes at all (already matched exactly).

Revision ID: 01cf410e050d
Revises: 6415d481ab54
Create Date: 2026-09-20 14:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '01cf410e050d'
down_revision: Union[str, None] = '6415d481ab54'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -----------------------------------------------------------------
    # compliance_snapshots: DB was one-row-per-remittance-type; model
    # and real usage are one-row-per-period covering all five types.
    # -----------------------------------------------------------------
    op.add_column('compliance_snapshots', sa.Column('paye_status', sa.String(length=30), server_default='not_due', nullable=False))
    op.add_column('compliance_snapshots', sa.Column('paye_amount_due', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('compliance_snapshots', sa.Column('paye_amount_paid', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('compliance_snapshots', sa.Column('paye_due_date', sa.Date(), nullable=True))
    op.add_column('compliance_snapshots', sa.Column('paye_days_overdue', sa.Integer(), server_default='0', nullable=False))
    op.add_column('compliance_snapshots', sa.Column('paye_penalty_estimate', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('compliance_snapshots', sa.Column('paye_tax_state', sa.String(length=100), nullable=True))
    op.add_column('compliance_snapshots', sa.Column('pension_status', sa.String(length=30), server_default='not_due', nullable=False))
    op.add_column('compliance_snapshots', sa.Column('pension_amount_due', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('compliance_snapshots', sa.Column('pension_amount_paid', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('compliance_snapshots', sa.Column('pension_due_date', sa.Date(), nullable=True))
    op.add_column('compliance_snapshots', sa.Column('pension_days_overdue', sa.Integer(), server_default='0', nullable=False))
    op.add_column('compliance_snapshots', sa.Column('pension_penalty_estimate', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('compliance_snapshots', sa.Column('nhf_status', sa.String(length=30), server_default='not_due', nullable=False))
    op.add_column('compliance_snapshots', sa.Column('nhf_amount_due', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('compliance_snapshots', sa.Column('nhf_amount_paid', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('compliance_snapshots', sa.Column('nhf_due_date', sa.Date(), nullable=True))
    op.add_column('compliance_snapshots', sa.Column('nhf_days_overdue', sa.Integer(), server_default='0', nullable=False))
    op.add_column('compliance_snapshots', sa.Column('nsitf_status', sa.String(length=30), server_default='not_due', nullable=False))
    op.add_column('compliance_snapshots', sa.Column('nsitf_amount_due', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('compliance_snapshots', sa.Column('nsitf_amount_paid', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('compliance_snapshots', sa.Column('itf_status', sa.String(length=30), server_default='not_due', nullable=False))
    op.add_column('compliance_snapshots', sa.Column('itf_amount_due', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('compliance_snapshots', sa.Column('itf_amount_paid', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('compliance_snapshots', sa.Column('total_penalty_exposure', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('compliance_snapshots', sa.Column('snapshot_date', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.alter_column('compliance_snapshots', 'remittance_type', nullable=True)
    op.alter_column('compliance_snapshots', 'status', nullable=True)
    op.alter_column('compliance_snapshots', 'amount_due', nullable=True)
    op.alter_column('compliance_snapshots', 'amount_paid', nullable=True)
    op.alter_column('compliance_snapshots', 'days_overdue', nullable=True)
    op.alter_column('compliance_snapshots', 'estimated_penalty', nullable=True)
    op.create_unique_constraint('uq_compliance_period', 'compliance_snapshots', ['entity_id', 'period_month', 'period_year'])

    # -----------------------------------------------------------------
    # payroll_impact_previews: DB was a field-level change log; model
    # and real usage are a payroll-run-vs-previous-run comparison.
    # -----------------------------------------------------------------
    op.add_column('payroll_impact_previews', sa.Column('previous_payroll_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('payroll_impact_previews', sa.Column('current_gross', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('payroll_impact_previews', sa.Column('current_net', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('payroll_impact_previews', sa.Column('current_paye', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('payroll_impact_previews', sa.Column('current_employer_cost', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('payroll_impact_previews', sa.Column('current_employee_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('payroll_impact_previews', sa.Column('previous_gross', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('payroll_impact_previews', sa.Column('previous_net', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('payroll_impact_previews', sa.Column('previous_paye', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('payroll_impact_previews', sa.Column('previous_employer_cost', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('payroll_impact_previews', sa.Column('previous_employee_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('payroll_impact_previews', sa.Column('gross_variance', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('payroll_impact_previews', sa.Column('gross_variance_percent', sa.Numeric(precision=5, scale=2), server_default='0', nullable=False))
    op.add_column('payroll_impact_previews', sa.Column('net_variance', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('payroll_impact_previews', sa.Column('paye_variance', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('payroll_impact_previews', sa.Column('employer_cost_variance', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('payroll_impact_previews', sa.Column('variance_drivers', postgresql.JSONB(), server_default='[]', nullable=False))
    op.add_column('payroll_impact_previews', sa.Column('new_hires_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('payroll_impact_previews', sa.Column('new_hires_cost', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('payroll_impact_previews', sa.Column('terminations_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('payroll_impact_previews', sa.Column('terminations_savings', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('payroll_impact_previews', sa.Column('impact_summary', sa.Text(), server_default='', nullable=False))
    op.add_column('payroll_impact_previews', sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('payroll_impact_previews', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.alter_column('payroll_impact_previews', 'change_type', nullable=True)
    op.alter_column('payroll_impact_previews', 'impact_on_gross', nullable=True)
    op.alter_column('payroll_impact_previews', 'impact_on_tax', nullable=True)
    op.alter_column('payroll_impact_previews', 'impact_on_pension', nullable=True)
    op.alter_column('payroll_impact_previews', 'impact_on_net', nullable=True)
    op.alter_column('payroll_impact_previews', 'is_applied', nullable=True)
    op.create_unique_constraint('uq_payroll_impact_preview_run', 'payroll_impact_previews', ['payroll_run_id'])
    op.create_foreign_key('fk_payroll_impact_previews_previous_payroll_id_payroll_runs', 'payroll_impact_previews', 'payroll_runs', ['previous_payroll_id'], ['id'], ondelete='SET NULL')

    # -----------------------------------------------------------------
    # payroll_exceptions: mostly matched already; entity_id (direction
    # B, handled on the model) already existed. Add the 3 genuinely
    # missing columns real code sends.
    # -----------------------------------------------------------------
    op.add_column('payroll_exceptions', sa.Column('related_field', sa.String(length=100), nullable=True))
    op.add_column('payroll_exceptions', sa.Column('current_value', sa.String(length=255), nullable=True))
    op.add_column('payroll_exceptions', sa.Column('requires_acknowledgement', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('payroll_exceptions', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))

    # -----------------------------------------------------------------
    # ytd_payroll_ledgers
    # -----------------------------------------------------------------
    op.add_column('ytd_payroll_ledgers', sa.Column('ytd_gross', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('ytd_payroll_ledgers', sa.Column('ytd_basic', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('ytd_payroll_ledgers', sa.Column('ytd_housing', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('ytd_payroll_ledgers', sa.Column('ytd_transport', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('ytd_payroll_ledgers', sa.Column('ytd_other_earnings', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('ytd_payroll_ledgers', sa.Column('ytd_pension_employee', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('ytd_payroll_ledgers', sa.Column('ytd_total_deductions', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('ytd_payroll_ledgers', sa.Column('ytd_net', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('ytd_payroll_ledgers', sa.Column('ytd_pension_employer', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('ytd_payroll_ledgers', sa.Column('ytd_nsitf', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('ytd_payroll_ledgers', sa.Column('ytd_itf', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('ytd_payroll_ledgers', sa.Column('ytd_total_employer_cost', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('ytd_payroll_ledgers', sa.Column('months_processed', sa.Integer(), server_default='0', nullable=False))
    op.add_column('ytd_payroll_ledgers', sa.Column('last_payroll_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('ytd_payroll_ledgers', sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('ytd_payroll_ledgers', sa.Column('has_opening_balance', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('ytd_payroll_ledgers', sa.Column('opening_balance_date', sa.Date(), nullable=True))
    op.alter_column('ytd_payroll_ledgers', 'ytd_gross_salary', nullable=True)
    op.alter_column('ytd_payroll_ledgers', 'ytd_basic_salary', nullable=True)
    op.alter_column('ytd_payroll_ledgers', 'ytd_housing_allowance', nullable=True)
    op.alter_column('ytd_payroll_ledgers', 'ytd_transport_allowance', nullable=True)
    op.alter_column('ytd_payroll_ledgers', 'ytd_other_allowances', nullable=True)
    op.alter_column('ytd_payroll_ledgers', 'ytd_bonuses', nullable=True)
    op.alter_column('ytd_payroll_ledgers', 'ytd_employee_pension', nullable=True)
    op.alter_column('ytd_payroll_ledgers', 'ytd_net_pay', nullable=True)
    op.alter_column('ytd_payroll_ledgers', 'ytd_consolidated_relief', nullable=True)
    op.alter_column('ytd_payroll_ledgers', 'ytd_rent_relief', nullable=True)
    op.create_foreign_key('fk_ytd_payroll_ledgers_last_payroll_id_payroll_runs', 'ytd_payroll_ledgers', 'payroll_runs', ['last_payroll_id'], ['id'], ondelete='SET NULL')

    # -----------------------------------------------------------------
    # opening_balance_imports
    # -----------------------------------------------------------------
    op.add_column('opening_balance_imports', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('opening_balance_imports', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('opening_balance_imports', sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('opening_balance_imports', sa.Column('updated_by_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('opening_balance_imports', sa.Column('import_batch_id', sa.String(length=50), server_default='', nullable=False))
    op.add_column('opening_balance_imports', sa.Column('effective_date', sa.Date(), nullable=True))
    op.add_column('opening_balance_imports', sa.Column('months_covered', sa.Integer(), server_default='0', nullable=False))
    op.add_column('opening_balance_imports', sa.Column('prior_ytd_gross', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('opening_balance_imports', sa.Column('prior_ytd_paye', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('opening_balance_imports', sa.Column('prior_ytd_pension_employee', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('opening_balance_imports', sa.Column('prior_ytd_pension_employer', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('opening_balance_imports', sa.Column('prior_ytd_nhf', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('opening_balance_imports', sa.Column('prior_ytd_net', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('opening_balance_imports', sa.Column('source_file', sa.String(length=500), nullable=True))
    op.add_column('opening_balance_imports', sa.Column('is_applied', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('opening_balance_imports', sa.Column('applied_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('opening_balance_imports', sa.Column('notes', sa.Text(), nullable=True))
    op.alter_column('opening_balance_imports', 'import_month', nullable=True)
    op.alter_column('opening_balance_imports', 'gross_salary', nullable=True)
    op.alter_column('opening_balance_imports', 'basic_salary', nullable=True)
    op.alter_column('opening_balance_imports', 'paye', nullable=True)
    op.alter_column('opening_balance_imports', 'employee_pension', nullable=True)
    op.alter_column('opening_balance_imports', 'employer_pension', nullable=True)
    op.alter_column('opening_balance_imports', 'nhf', nullable=True)
    op.alter_column('opening_balance_imports', 'net_pay', nullable=True)

    # -----------------------------------------------------------------
    # payslip_explanations: DB was one-row-per-line-item; model and
    # real usage are one-row-per-payslip with 4 explanation blocks.
    # -----------------------------------------------------------------
    op.add_column('payslip_explanations', sa.Column('has_changes', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('payslip_explanations', sa.Column('gross_explanation', sa.Text(), server_default='', nullable=False))
    op.add_column('payslip_explanations', sa.Column('deduction_explanation', sa.Text(), server_default='', nullable=False))
    op.add_column('payslip_explanations', sa.Column('tax_explanation', sa.Text(), server_default='', nullable=False))
    op.add_column('payslip_explanations', sa.Column('net_explanation', sa.Text(), server_default='', nullable=False))
    op.add_column('payslip_explanations', sa.Column('full_explanation', sa.Text(), server_default='', nullable=False))
    op.add_column('payslip_explanations', sa.Column('variance_notes', sa.Text(), nullable=True))
    op.add_column('payslip_explanations', sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('payslip_explanations', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.alter_column('payslip_explanations', 'section', nullable=True)
    op.alter_column('payslip_explanations', 'item_name', nullable=True)
    op.alter_column('payslip_explanations', 'explanation', nullable=True)
    op.alter_column('payslip_explanations', 'sort_order', nullable=True)
    op.create_unique_constraint('uq_payslip_explanation_payslip', 'payslip_explanations', ['payslip_id'])

    # -----------------------------------------------------------------
    # employee_variance_logs
    # -----------------------------------------------------------------
    op.add_column('employee_variance_logs', sa.Column('previous_payslip_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('employee_variance_logs', sa.Column('variance_type', sa.String(length=50), nullable=True))
    op.add_column('employee_variance_logs', sa.Column('reason_code', sa.String(length=50), nullable=True))
    op.add_column('employee_variance_logs', sa.Column('reason_note', sa.Text(), nullable=True))
    op.add_column('employee_variance_logs', sa.Column('flag_threshold_percent', sa.Numeric(precision=5, scale=2), server_default='5.00', nullable=False))
    op.add_column('employee_variance_logs', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.alter_column('employee_variance_logs', 'field_name', nullable=True)
    op.create_foreign_key('fk_employee_variance_logs_previous_payslip_id_payslips', 'employee_variance_logs', 'payslips', ['previous_payslip_id'], ['id'], ondelete='SET NULL')

    # -----------------------------------------------------------------
    # ctc_snapshots: DB was per-employee; model and real usage are
    # company-wide.
    # -----------------------------------------------------------------
    op.add_column('ctc_snapshots', sa.Column('snapshot_month', sa.Integer(), server_default='1', nullable=False))
    op.add_column('ctc_snapshots', sa.Column('snapshot_year', sa.Integer(), server_default='2026', nullable=False))
    op.add_column('ctc_snapshots', sa.Column('total_employees', sa.Integer(), server_default='0', nullable=False))
    op.add_column('ctc_snapshots', sa.Column('total_gross_salary', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('ctc_snapshots', sa.Column('total_pension_employer', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('ctc_snapshots', sa.Column('total_nsitf', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('ctc_snapshots', sa.Column('total_itf', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('ctc_snapshots', sa.Column('total_hmo', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('ctc_snapshots', sa.Column('total_group_life', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('ctc_snapshots', sa.Column('total_other_benefits', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('ctc_snapshots', sa.Column('average_ctc_per_employee', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('ctc_snapshots', sa.Column('department_breakdown', postgresql.JSONB(), server_default='{}', nullable=False))
    op.add_column('ctc_snapshots', sa.Column('monthly_budget', sa.Numeric(precision=18, scale=2), nullable=True))
    op.add_column('ctc_snapshots', sa.Column('budget_variance', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('ctc_snapshots', sa.Column('budget_variance_percent', sa.Numeric(precision=5, scale=2), server_default='0', nullable=False))
    op.add_column('ctc_snapshots', sa.Column('snapshot_date', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('ctc_snapshots', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.alter_column('ctc_snapshots', 'employee_id', nullable=True)
    op.alter_column('ctc_snapshots', 'period_month', nullable=True)
    op.alter_column('ctc_snapshots', 'period_year', nullable=True)
    op.alter_column('ctc_snapshots', 'gross_salary', nullable=True)
    op.alter_column('ctc_snapshots', 'employer_pension', nullable=True)
    op.alter_column('ctc_snapshots', 'employer_nhf', nullable=True)
    op.alter_column('ctc_snapshots', 'employer_nsitf', nullable=True)
    op.alter_column('ctc_snapshots', 'employer_itf', nullable=True)
    op.alter_column('ctc_snapshots', 'other_employer_costs', nullable=True)
    op.create_unique_constraint('uq_ctc_entity_period', 'ctc_snapshots', ['entity_id', 'snapshot_month', 'snapshot_year'])

    # -----------------------------------------------------------------
    # what_if_simulations
    # -----------------------------------------------------------------
    op.add_column('what_if_simulations', sa.Column('scenario_type', sa.String(length=50), server_default='custom', nullable=False))
    op.add_column('what_if_simulations', sa.Column('parameters', postgresql.JSONB(), server_default='{}', nullable=False))
    op.add_column('what_if_simulations', sa.Column('baseline_gross', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('what_if_simulations', sa.Column('baseline_paye', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('what_if_simulations', sa.Column('baseline_employer_cost', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('what_if_simulations', sa.Column('baseline_ctc', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('what_if_simulations', sa.Column('projected_gross', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('what_if_simulations', sa.Column('projected_paye', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('what_if_simulations', sa.Column('projected_employer_cost', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('what_if_simulations', sa.Column('projected_ctc', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('what_if_simulations', sa.Column('gross_impact', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('what_if_simulations', sa.Column('paye_impact', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('what_if_simulations', sa.Column('employer_cost_impact', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('what_if_simulations', sa.Column('ctc_impact', sa.Numeric(precision=18, scale=2), server_default='0', nullable=False))
    op.add_column('what_if_simulations', sa.Column('gross_impact_percent', sa.Numeric(precision=5, scale=2), server_default='0', nullable=False))
    op.add_column('what_if_simulations', sa.Column('ctc_impact_percent', sa.Numeric(precision=5, scale=2), server_default='0', nullable=False))
    op.add_column('what_if_simulations', sa.Column('impact_summary', sa.Text(), server_default='', nullable=False))
    op.add_column('what_if_simulations', sa.Column('is_saved', sa.Boolean(), server_default='false', nullable=False))
    op.alter_column('what_if_simulations', 'simulation_type', nullable=True)
    op.alter_column('what_if_simulations', 'input_parameters', nullable=True)
    op.alter_column('what_if_simulations', 'status', nullable=True)
    op.alter_column('what_if_simulations', 'is_applied', nullable=True)

    # -----------------------------------------------------------------
    # ghost_worker_detections
    # -----------------------------------------------------------------
    op.add_column('ghost_worker_detections', sa.Column('employee_1_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('ghost_worker_detections', sa.Column('employee_2_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('ghost_worker_detections', sa.Column('duplicate_field', sa.String(length=50), nullable=True))
    op.add_column('ghost_worker_detections', sa.Column('duplicate_value', sa.String(length=255), nullable=True))
    op.add_column('ghost_worker_detections', sa.Column('severity', sa.String(length=20), server_default='critical', nullable=False))
    op.add_column('ghost_worker_detections', sa.Column('resolution_note', sa.Text(), nullable=True))
    op.add_column('ghost_worker_detections', sa.Column('detected_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('ghost_worker_detections', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.alter_column('ghost_worker_detections', 'detection_run_id', nullable=True)
    op.alter_column('ghost_worker_detections', 'risk_score', nullable=True)
    op.alter_column('ghost_worker_detections', 'risk_level', nullable=True)
    op.alter_column('ghost_worker_detections', 'detection_details', nullable=True)
    op.create_foreign_key('fk_ghost_worker_detections_employee_1_id_employees', 'ghost_worker_detections', 'employees', ['employee_1_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_ghost_worker_detections_employee_2_id_employees', 'ghost_worker_detections', 'employees', ['employee_2_id'], ['id'], ondelete='CASCADE')

    # -----------------------------------------------------------------
    # payroll_decision_logs: otherwise matched exactly; only missing
    # updated_at (only created_at existed, despite inheriting
    # BaseModel/TimestampMixin).
    # -----------------------------------------------------------------
    op.add_column('payroll_decision_logs', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))


def downgrade() -> None:
    op.drop_column('payroll_decision_logs', 'updated_at')

    op.drop_constraint('fk_ghost_worker_detections_employee_2_id_employees', 'ghost_worker_detections', type_='foreignkey')
    op.drop_constraint('fk_ghost_worker_detections_employee_1_id_employees', 'ghost_worker_detections', type_='foreignkey')
    op.drop_column('ghost_worker_detections', 'updated_at')
    op.alter_column('ghost_worker_detections', 'detection_details', nullable=False)
    op.alter_column('ghost_worker_detections', 'risk_level', nullable=False)
    op.alter_column('ghost_worker_detections', 'risk_score', nullable=False)
    op.alter_column('ghost_worker_detections', 'detection_run_id', nullable=False)
    op.drop_column('ghost_worker_detections', 'detected_at')
    op.drop_column('ghost_worker_detections', 'resolution_note')
    op.drop_column('ghost_worker_detections', 'severity')
    op.drop_column('ghost_worker_detections', 'duplicate_value')
    op.drop_column('ghost_worker_detections', 'duplicate_field')
    op.drop_column('ghost_worker_detections', 'employee_2_id')
    op.drop_column('ghost_worker_detections', 'employee_1_id')

    op.alter_column('what_if_simulations', 'is_applied', nullable=False)
    op.alter_column('what_if_simulations', 'status', nullable=False)
    op.alter_column('what_if_simulations', 'input_parameters', nullable=False)
    op.alter_column('what_if_simulations', 'simulation_type', nullable=False)
    op.drop_column('what_if_simulations', 'is_saved')
    op.drop_column('what_if_simulations', 'impact_summary')
    op.drop_column('what_if_simulations', 'ctc_impact_percent')
    op.drop_column('what_if_simulations', 'gross_impact_percent')
    op.drop_column('what_if_simulations', 'ctc_impact')
    op.drop_column('what_if_simulations', 'employer_cost_impact')
    op.drop_column('what_if_simulations', 'paye_impact')
    op.drop_column('what_if_simulations', 'gross_impact')
    op.drop_column('what_if_simulations', 'projected_ctc')
    op.drop_column('what_if_simulations', 'projected_employer_cost')
    op.drop_column('what_if_simulations', 'projected_paye')
    op.drop_column('what_if_simulations', 'projected_gross')
    op.drop_column('what_if_simulations', 'baseline_ctc')
    op.drop_column('what_if_simulations', 'baseline_employer_cost')
    op.drop_column('what_if_simulations', 'baseline_paye')
    op.drop_column('what_if_simulations', 'baseline_gross')
    op.drop_column('what_if_simulations', 'parameters')
    op.drop_column('what_if_simulations', 'scenario_type')

    op.drop_constraint('uq_ctc_entity_period', 'ctc_snapshots', type_='unique')
    op.drop_column('ctc_snapshots', 'updated_at')
    op.alter_column('ctc_snapshots', 'other_employer_costs', nullable=False)
    op.alter_column('ctc_snapshots', 'employer_itf', nullable=False)
    op.alter_column('ctc_snapshots', 'employer_nsitf', nullable=False)
    op.alter_column('ctc_snapshots', 'employer_nhf', nullable=False)
    op.alter_column('ctc_snapshots', 'employer_pension', nullable=False)
    op.alter_column('ctc_snapshots', 'gross_salary', nullable=False)
    op.alter_column('ctc_snapshots', 'period_year', nullable=False)
    op.alter_column('ctc_snapshots', 'period_month', nullable=False)
    op.alter_column('ctc_snapshots', 'employee_id', nullable=False)
    op.drop_column('ctc_snapshots', 'snapshot_date')
    op.drop_column('ctc_snapshots', 'budget_variance_percent')
    op.drop_column('ctc_snapshots', 'budget_variance')
    op.drop_column('ctc_snapshots', 'monthly_budget')
    op.drop_column('ctc_snapshots', 'department_breakdown')
    op.drop_column('ctc_snapshots', 'average_ctc_per_employee')
    op.drop_column('ctc_snapshots', 'total_other_benefits')
    op.drop_column('ctc_snapshots', 'total_group_life')
    op.drop_column('ctc_snapshots', 'total_hmo')
    op.drop_column('ctc_snapshots', 'total_itf')
    op.drop_column('ctc_snapshots', 'total_nsitf')
    op.drop_column('ctc_snapshots', 'total_pension_employer')
    op.drop_column('ctc_snapshots', 'total_gross_salary')
    op.drop_column('ctc_snapshots', 'total_employees')
    op.drop_column('ctc_snapshots', 'snapshot_year')
    op.drop_column('ctc_snapshots', 'snapshot_month')

    op.drop_constraint('fk_employee_variance_logs_previous_payslip_id_payslips', 'employee_variance_logs', type_='foreignkey')
    op.drop_column('employee_variance_logs', 'updated_at')
    op.alter_column('employee_variance_logs', 'field_name', nullable=False)
    op.drop_column('employee_variance_logs', 'flag_threshold_percent')
    op.drop_column('employee_variance_logs', 'reason_note')
    op.drop_column('employee_variance_logs', 'reason_code')
    op.drop_column('employee_variance_logs', 'variance_type')
    op.drop_column('employee_variance_logs', 'previous_payslip_id')

    op.drop_constraint('uq_payslip_explanation_payslip', 'payslip_explanations', type_='unique')
    op.drop_column('payslip_explanations', 'updated_at')
    op.alter_column('payslip_explanations', 'sort_order', nullable=False)
    op.alter_column('payslip_explanations', 'explanation', nullable=False)
    op.alter_column('payslip_explanations', 'item_name', nullable=False)
    op.alter_column('payslip_explanations', 'section', nullable=False)
    op.drop_column('payslip_explanations', 'generated_at')
    op.drop_column('payslip_explanations', 'variance_notes')
    op.drop_column('payslip_explanations', 'full_explanation')
    op.drop_column('payslip_explanations', 'net_explanation')
    op.drop_column('payslip_explanations', 'tax_explanation')
    op.drop_column('payslip_explanations', 'deduction_explanation')
    op.drop_column('payslip_explanations', 'gross_explanation')
    op.drop_column('payslip_explanations', 'has_changes')

    op.alter_column('opening_balance_imports', 'net_pay', nullable=False)
    op.alter_column('opening_balance_imports', 'nhf', nullable=False)
    op.alter_column('opening_balance_imports', 'employer_pension', nullable=False)
    op.alter_column('opening_balance_imports', 'employee_pension', nullable=False)
    op.alter_column('opening_balance_imports', 'paye', nullable=False)
    op.alter_column('opening_balance_imports', 'basic_salary', nullable=False)
    op.alter_column('opening_balance_imports', 'gross_salary', nullable=False)
    op.alter_column('opening_balance_imports', 'import_month', nullable=False)
    op.drop_column('opening_balance_imports', 'notes')
    op.drop_column('opening_balance_imports', 'applied_at')
    op.drop_column('opening_balance_imports', 'is_applied')
    op.drop_column('opening_balance_imports', 'source_file')
    op.drop_column('opening_balance_imports', 'prior_ytd_net')
    op.drop_column('opening_balance_imports', 'prior_ytd_nhf')
    op.drop_column('opening_balance_imports', 'prior_ytd_pension_employer')
    op.drop_column('opening_balance_imports', 'prior_ytd_pension_employee')
    op.drop_column('opening_balance_imports', 'prior_ytd_paye')
    op.drop_column('opening_balance_imports', 'prior_ytd_gross')
    op.drop_column('opening_balance_imports', 'months_covered')
    op.drop_column('opening_balance_imports', 'effective_date')
    op.drop_column('opening_balance_imports', 'import_batch_id')
    op.drop_column('opening_balance_imports', 'updated_by_id')
    op.drop_column('opening_balance_imports', 'created_by_id')
    op.drop_column('opening_balance_imports', 'updated_at')
    op.drop_column('opening_balance_imports', 'created_at')

    op.drop_constraint('fk_ytd_payroll_ledgers_last_payroll_id_payroll_runs', 'ytd_payroll_ledgers', type_='foreignkey')
    op.alter_column('ytd_payroll_ledgers', 'ytd_rent_relief', nullable=False)
    op.alter_column('ytd_payroll_ledgers', 'ytd_consolidated_relief', nullable=False)
    op.alter_column('ytd_payroll_ledgers', 'ytd_net_pay', nullable=False)
    op.alter_column('ytd_payroll_ledgers', 'ytd_employee_pension', nullable=False)
    op.alter_column('ytd_payroll_ledgers', 'ytd_bonuses', nullable=False)
    op.alter_column('ytd_payroll_ledgers', 'ytd_other_allowances', nullable=False)
    op.alter_column('ytd_payroll_ledgers', 'ytd_transport_allowance', nullable=False)
    op.alter_column('ytd_payroll_ledgers', 'ytd_housing_allowance', nullable=False)
    op.alter_column('ytd_payroll_ledgers', 'ytd_basic_salary', nullable=False)
    op.alter_column('ytd_payroll_ledgers', 'ytd_gross_salary', nullable=False)
    op.drop_column('ytd_payroll_ledgers', 'opening_balance_date')
    op.drop_column('ytd_payroll_ledgers', 'has_opening_balance')
    op.drop_column('ytd_payroll_ledgers', 'last_updated')
    op.drop_column('ytd_payroll_ledgers', 'last_payroll_id')
    op.drop_column('ytd_payroll_ledgers', 'months_processed')
    op.drop_column('ytd_payroll_ledgers', 'ytd_total_employer_cost')
    op.drop_column('ytd_payroll_ledgers', 'ytd_itf')
    op.drop_column('ytd_payroll_ledgers', 'ytd_nsitf')
    op.drop_column('ytd_payroll_ledgers', 'ytd_pension_employer')
    op.drop_column('ytd_payroll_ledgers', 'ytd_net')
    op.drop_column('ytd_payroll_ledgers', 'ytd_total_deductions')
    op.drop_column('ytd_payroll_ledgers', 'ytd_pension_employee')
    op.drop_column('ytd_payroll_ledgers', 'ytd_other_earnings')
    op.drop_column('ytd_payroll_ledgers', 'ytd_transport')
    op.drop_column('ytd_payroll_ledgers', 'ytd_housing')
    op.drop_column('ytd_payroll_ledgers', 'ytd_basic')
    op.drop_column('ytd_payroll_ledgers', 'ytd_gross')

    op.drop_column('payroll_exceptions', 'updated_at')
    op.drop_column('payroll_exceptions', 'requires_acknowledgement')
    op.drop_column('payroll_exceptions', 'current_value')
    op.drop_column('payroll_exceptions', 'related_field')

    op.drop_constraint('fk_payroll_impact_previews_previous_payroll_id_payroll_runs', 'payroll_impact_previews', type_='foreignkey')
    op.drop_column('payroll_impact_previews', 'updated_at')
    op.drop_constraint('uq_payroll_impact_preview_run', 'payroll_impact_previews', type_='unique')
    op.alter_column('payroll_impact_previews', 'is_applied', nullable=False)
    op.alter_column('payroll_impact_previews', 'impact_on_net', nullable=False)
    op.alter_column('payroll_impact_previews', 'impact_on_pension', nullable=False)
    op.alter_column('payroll_impact_previews', 'impact_on_tax', nullable=False)
    op.alter_column('payroll_impact_previews', 'impact_on_gross', nullable=False)
    op.alter_column('payroll_impact_previews', 'change_type', nullable=False)
    op.drop_column('payroll_impact_previews', 'generated_at')
    op.drop_column('payroll_impact_previews', 'impact_summary')
    op.drop_column('payroll_impact_previews', 'terminations_savings')
    op.drop_column('payroll_impact_previews', 'terminations_count')
    op.drop_column('payroll_impact_previews', 'new_hires_cost')
    op.drop_column('payroll_impact_previews', 'new_hires_count')
    op.drop_column('payroll_impact_previews', 'variance_drivers')
    op.drop_column('payroll_impact_previews', 'employer_cost_variance')
    op.drop_column('payroll_impact_previews', 'paye_variance')
    op.drop_column('payroll_impact_previews', 'net_variance')
    op.drop_column('payroll_impact_previews', 'gross_variance_percent')
    op.drop_column('payroll_impact_previews', 'gross_variance')
    op.drop_column('payroll_impact_previews', 'previous_employee_count')
    op.drop_column('payroll_impact_previews', 'previous_employer_cost')
    op.drop_column('payroll_impact_previews', 'previous_paye')
    op.drop_column('payroll_impact_previews', 'previous_net')
    op.drop_column('payroll_impact_previews', 'previous_gross')
    op.drop_column('payroll_impact_previews', 'current_employee_count')
    op.drop_column('payroll_impact_previews', 'current_employer_cost')
    op.drop_column('payroll_impact_previews', 'current_paye')
    op.drop_column('payroll_impact_previews', 'current_net')
    op.drop_column('payroll_impact_previews', 'current_gross')
    op.drop_column('payroll_impact_previews', 'previous_payroll_id')

    op.drop_constraint('uq_compliance_period', 'compliance_snapshots', type_='unique')
    op.alter_column('compliance_snapshots', 'estimated_penalty', nullable=False)
    op.alter_column('compliance_snapshots', 'days_overdue', nullable=False)
    op.alter_column('compliance_snapshots', 'amount_paid', nullable=False)
    op.alter_column('compliance_snapshots', 'amount_due', nullable=False)
    op.alter_column('compliance_snapshots', 'status', nullable=False)
    op.alter_column('compliance_snapshots', 'remittance_type', nullable=False)
    op.drop_column('compliance_snapshots', 'snapshot_date')
    op.drop_column('compliance_snapshots', 'total_penalty_exposure')
    op.drop_column('compliance_snapshots', 'itf_amount_paid')
    op.drop_column('compliance_snapshots', 'itf_amount_due')
    op.drop_column('compliance_snapshots', 'itf_status')
    op.drop_column('compliance_snapshots', 'nsitf_amount_paid')
    op.drop_column('compliance_snapshots', 'nsitf_amount_due')
    op.drop_column('compliance_snapshots', 'nsitf_status')
    op.drop_column('compliance_snapshots', 'nhf_days_overdue')
    op.drop_column('compliance_snapshots', 'nhf_due_date')
    op.drop_column('compliance_snapshots', 'nhf_amount_paid')
    op.drop_column('compliance_snapshots', 'nhf_amount_due')
    op.drop_column('compliance_snapshots', 'nhf_status')
    op.drop_column('compliance_snapshots', 'pension_penalty_estimate')
    op.drop_column('compliance_snapshots', 'pension_days_overdue')
    op.drop_column('compliance_snapshots', 'pension_due_date')
    op.drop_column('compliance_snapshots', 'pension_amount_paid')
    op.drop_column('compliance_snapshots', 'pension_amount_due')
    op.drop_column('compliance_snapshots', 'pension_status')
    op.drop_column('compliance_snapshots', 'paye_tax_state')
    op.drop_column('compliance_snapshots', 'paye_penalty_estimate')
    op.drop_column('compliance_snapshots', 'paye_days_overdue')
    op.drop_column('compliance_snapshots', 'paye_due_date')
    op.drop_column('compliance_snapshots', 'paye_amount_paid')
    op.drop_column('compliance_snapshots', 'paye_amount_due')
    op.drop_column('compliance_snapshots', 'paye_status')
