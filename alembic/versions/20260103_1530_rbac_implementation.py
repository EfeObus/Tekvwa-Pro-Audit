"""RBAC implementation - Add platform roles and organization types

Revision ID: 20260103_1530_rbac_implementation
Revises: 2026_tax_reform
Create Date: 2026-01-03 15:30:00.000000

This migration implements Role-Based Access Control (RBAC) for:
1. Platform Staff (Internal Tekvwa employees)
   - Super Admin, Admin, IT/Developer, Customer Service, Marketing
2. Organizations (External customers)
   - SME, Small Business, School, Non-Profit, Individual, Corporation
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '20260103_1530_rbac_implementation'
down_revision = '2026_tax_reform'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ===========================================
    # CREATE ENUMS
    # ===========================================
    
    # Platform role enum for internal staff
    platform_role_enum = postgresql.ENUM(
        'super_admin', 'admin', 'it_developer', 'customer_service', 'marketing',
        name='platformrole',
        create_type=False
    )
    platform_role_enum.create(op.get_bind(), checkfirst=True)
    
    # Organization type enum
    organization_type_enum = postgresql.ENUM(
        'sme', 'small_business', 'school', 'non_profit', 'individual', 'corporation',
        name='organizationtype',
        create_type=False
    )
    organization_type_enum.create(op.get_bind(), checkfirst=True)
    
    # Verification status enum
    verification_status_enum = postgresql.ENUM(
        'pending', 'submitted', 'under_review', 'verified', 'rejected',
        name='verificationstatus',
        create_type=False
    )
    verification_status_enum.create(op.get_bind(), checkfirst=True)
    
    # ===========================================
    # UPDATE USERS TABLE
    # ===========================================
    
    # Make organization_id nullable (for platform staff who don't belong to orgs)
    op.alter_column(
        'users',
        'organization_id',
        existing_type=postgresql.UUID(),
        nullable=True
    )
    
    # Make role nullable (for platform staff)
    op.alter_column(
        'users',
        'role',
        existing_type=sa.Enum('owner', 'admin', 'accountant', 'auditor', 
                              'payroll_manager', 'inventory_manager', 'viewer',
                              name='userrole'),
        nullable=True
    )
    
    # Add platform staff fields
    op.add_column(
        'users',
        sa.Column(
            'is_platform_staff',
            sa.Boolean(),
            nullable=False,
            server_default='false',
            comment='True for internal Tekvwa employees'
        )
    )
    
    op.add_column(
        'users',
        sa.Column(
            'platform_role',
            sa.Enum('super_admin', 'admin', 'it_developer', 'customer_service', 'marketing',
                    name='platformrole'),
            nullable=True,
            comment='Role for platform staff only'
        )
    )
    
    op.add_column(
        'users',
        sa.Column(
            'onboarded_by_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
            comment='ID of user who onboarded this staff member'
        )
    )
    
    op.add_column(
        'users',
        sa.Column(
            'staff_notes',
            sa.Text(),
            nullable=True,
            comment='Internal notes about staff member'
        )
    )
    
    op.add_column(
        'users',
        sa.Column(
            'can_be_impersonated',
            sa.Boolean(),
            nullable=False,
            server_default='false',
            comment='Whether CSR can impersonate this user (requires user permission)'
        )
    )
    
    # Create index on is_platform_staff for faster queries
    op.create_index(
        'ix_users_is_platform_staff',
        'users',
        ['is_platform_staff']
    )
    
    # ===========================================
    # UPDATE ORGANIZATIONS TABLE
    # ===========================================
    
    # Add organization type
    op.add_column(
        'organizations',
        sa.Column(
            'organization_type',
            sa.Enum('sme', 'small_business', 'school', 'non_profit', 'individual', 'corporation',
                    name='organizationtype'),
            nullable=False,
            server_default='small_business',
            comment='Type of organization for compliance and feature differentiation'
        )
    )
    
    # Add verification fields
    op.add_column(
        'organizations',
        sa.Column(
            'verification_status',
            sa.Enum('pending', 'submitted', 'under_review', 'verified', 'rejected',
                    name='verificationstatus'),
            nullable=False,
            server_default='pending',
            comment='Document verification status'
        )
    )
    
    op.add_column(
        'organizations',
        sa.Column(
            'cac_document_path',
            sa.String(500),
            nullable=True,
            comment='Path to CAC registration document'
        )
    )
    
    op.add_column(
        'organizations',
        sa.Column(
            'tin_document_path',
            sa.String(500),
            nullable=True,
            comment='Path to TIN certificate document'
        )
    )
    
    op.add_column(
        'organizations',
        sa.Column(
            'additional_documents',
            sa.Text(),
            nullable=True,
            comment='JSON array of additional document paths'
        )
    )
    
    op.add_column(
        'organizations',
        sa.Column(
            'verification_notes',
            sa.Text(),
            nullable=True,
            comment='Notes from admin during verification review'
        )
    )
    
    op.add_column(
        'organizations',
        sa.Column(
            'verified_by_id',
            sa.String(36),
            nullable=True,
            comment='ID of admin who verified the organization'
        )
    )
    
    # Add referral fields
    op.add_column(
        'organizations',
        sa.Column(
            'referral_code',
            sa.String(20),
            nullable=True,
            comment='Unique referral code for marketing campaigns'
        )
    )
    
    op.add_column(
        'organizations',
        sa.Column(
            'referred_by_code',
            sa.String(20),
            nullable=True,
            comment='Referral code of the organization that referred this one'
        )
    )
    
    # Create unique index on referral_code
    op.create_index(
        'ix_organizations_referral_code',
        'organizations',
        ['referral_code'],
        unique=True
    )


def downgrade() -> None:
    # ===========================================
    # REVERT ORGANIZATIONS TABLE
    # ===========================================
    
    op.drop_index('ix_organizations_referral_code', table_name='organizations')
    op.drop_column('organizations', 'referred_by_code')
    op.drop_column('organizations', 'referral_code')
    op.drop_column('organizations', 'verified_by_id')
    op.drop_column('organizations', 'verification_notes')
    op.drop_column('organizations', 'additional_documents')
    op.drop_column('organizations', 'tin_document_path')
    op.drop_column('organizations', 'cac_document_path')
    op.drop_column('organizations', 'verification_status')
    op.drop_column('organizations', 'organization_type')
    
    # ===========================================
    # REVERT USERS TABLE
    # ===========================================
    
    op.drop_index('ix_users_is_platform_staff', table_name='users')
    op.drop_column('users', 'can_be_impersonated')
    op.drop_column('users', 'staff_notes')
    op.drop_column('users', 'onboarded_by_id')
    op.drop_column('users', 'platform_role')
    op.drop_column('users', 'is_platform_staff')
    
    # Make organization_id and role non-nullable again
    op.alter_column(
        'users',
        'role',
        existing_type=sa.Enum('owner', 'admin', 'accountant', 'auditor', 
                              'payroll_manager', 'inventory_manager', 'viewer',
                              name='userrole'),
        nullable=False
    )
    
    op.alter_column(
        'users',
        'organization_id',
        existing_type=postgresql.UUID(),
        nullable=False
    )
    
    # ===========================================
    # DROP ENUMS
    # ===========================================
    
    # Drop enums (in reverse order)
    sa.Enum(name='verificationstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='organizationtype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='platformrole').drop(op.get_bind(), checkfirst=True)
