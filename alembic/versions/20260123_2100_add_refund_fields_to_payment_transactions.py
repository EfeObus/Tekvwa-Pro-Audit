"""Add refund and invoice fields to payment_transactions

Revision ID: 20260123_2100
Revises: 0563e1dd3aeb
Create Date: 2026-01-23 21:00:00.000000

Adds columns to support:
- Refund tracking (refunded_at, refund_amount_kobo, refund_reference, refund_reason)
- Paystack invoice tracking (paystack_invoice_id, paystack_invoice_status)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260123_2100'
down_revision: Union[str, None] = '0563e1dd3aeb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Note: refunded_at and refund_amount_kobo are already defined on payment_transactions
    # in 20260122_1920_add_payment_transactions.py - only the remaining refund/invoice
    # tracking columns are actually new here.
    op.add_column(
        'payment_transactions',
        sa.Column('refund_reference', sa.String(100), nullable=True,
                  comment='Paystack refund/transfer reference')
    )
    op.add_column(
        'payment_transactions',
        sa.Column('refund_reason', sa.String(500), nullable=True,
                  comment='Reason for refund')
    )
    
    # Add Paystack invoice tracking columns
    op.add_column(
        'payment_transactions',
        sa.Column('paystack_invoice_id', sa.String(100), nullable=True,
                  comment='Paystack invoice ID for subscription payments')
    )
    op.add_column(
        'payment_transactions',
        sa.Column('paystack_invoice_status', sa.String(50), nullable=True,
                  comment='Paystack invoice status (pending, paid, failed)')
    )
    
    # Create indexes for efficient lookups
    op.create_index(
        'ix_payment_transactions_refund_reference',
        'payment_transactions',
        ['refund_reference'],
        unique=False
    )
    op.create_index(
        'ix_payment_transactions_paystack_invoice_id',
        'payment_transactions',
        ['paystack_invoice_id'],
        unique=False
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_payment_transactions_paystack_invoice_id', 'payment_transactions')
    op.drop_index('ix_payment_transactions_refund_reference', 'payment_transactions')
    
    # Drop columns
    op.drop_column('payment_transactions', 'paystack_invoice_status')
    op.drop_column('payment_transactions', 'paystack_invoice_id')
    op.drop_column('payment_transactions', 'refund_reason')
    op.drop_column('payment_transactions', 'refund_reference')
