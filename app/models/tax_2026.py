"""
Tekvwa Pro Audit - 2026 Tax Reform Models

Models for the 2026 Nigerian Tax Administration Act compliance:
- VAT Recovery Audit Trail
- Development Levy
- PIT Relief Documents
- Credit Notes
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.entity import BusinessEntity
    from app.models.transaction import Transaction
    from app.models.invoice import Invoice
    from app.models.user import User


# ===========================================
# ENUMS
# ===========================================

class VATRecoveryType(str, Enum):
    """Type of VAT recovery (2026 law allows services and capital assets)."""
    STOCK_IN_TRADE = "stock_in_trade"        # Traditional input VAT on goods for resale
    CAPITAL_EXPENDITURE = "capital_expenditure"  # NEW: VAT on fixed assets
    SERVICES = "services"                     # NEW: VAT on services


class ReliefType(str, Enum):
    """PIT relief types (2026 reforms - CRA abolished)."""
    RENT = "rent"                    # 20% of rent paid (max ₦500,000)
    LIFE_INSURANCE = "life_insurance"  # Actual premium paid
    NHF = "nhf"                      # National Housing Fund contribution
    PENSION = "pension"              # Pension contribution
    NHIS = "nhis"                    # National Health Insurance
    GRATUITY = "gratuity"            # Gratuity contribution
    OTHER = "other"                  # Other approved reliefs


class ReliefStatus(str, Enum):
    """Status of relief document."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class CreditNoteStatus(str, Enum):
    """Credit note status."""
    DRAFT = "draft"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"


# ===========================================
# VAT RECOVERY AUDIT TRAIL
# ===========================================

class VATRecoveryRecord(BaseModel):
    """
    VAT Recovery Audit Trail for 2026 compliance.
    
    The 2026 law allows recovery of VAT on:
    - Stock-in-trade (existing)
    - Services (NEW)
    - Capital expenditure/fixed assets (NEW)
    
    Recovery is ONLY allowed if vendor provided valid NRS e-invoice (IRN).
    """
    
    __tablename__ = "vat_recovery_records"
    
    # Entity
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Link to transaction (optional)
    transaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # VAT Details
    vat_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    recovery_type: Mapped[VATRecoveryType] = mapped_column(
        SQLEnum(VATRecoveryType),
        nullable=False,
    )
    is_recoverable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    non_recovery_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # NRS Validation (CRITICAL for 2026 compliance)
    vendor_irn: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Vendor's NRS Invoice Reference Number",
    )
    has_valid_irn: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Only recoverable if vendor provided valid IRN",
    )
    
    # Vendor Details
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    vendor_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    vendor_tin: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # Period
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    recovery_period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    recovery_period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Relationships
    entity: Mapped["BusinessEntity"] = relationship("BusinessEntity")
    transaction: Mapped[Optional["Transaction"]] = relationship("Transaction")
    
    def __repr__(self) -> str:
        return f"<VATRecoveryRecord(id={self.id}, amount={self.vat_amount}, recoverable={self.is_recoverable})>"


# ===========================================
# DEVELOPMENT LEVY (4% - 2026 Consolidation)
# ===========================================

class DevelopmentLevyRecord(BaseModel):
    """
    Development Levy calculation for 2026.
    
    The 2026 Act consolidates:
    - Tertiary Education Tax
    - Police Fund
    - Other levies
    
    Into a single 4% Development Levy on assessable profit.
    
    Exemption: Turnover <= ₦100M AND Fixed Assets <= ₦250M
    """
    
    __tablename__ = "development_levy_records"
    
    # Entity
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Period
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Calculation
    assessable_profit: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    levy_rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=4),
        default=Decimal("0.04"),  # 4%
        nullable=False,
    )
    levy_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    
    # Eligibility check
    turnover: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=True,
    )
    fixed_assets: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=True,
    )
    is_exempt: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    exemption_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Filing
    is_filed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    filed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Relationships
    entity: Mapped["BusinessEntity"] = relationship("BusinessEntity")
    
    def __repr__(self) -> str:
        return f"<DevelopmentLevyRecord(id={self.id}, year={self.fiscal_year}, amount={self.levy_amount})>"


# ===========================================
# PIT RELIEF DOCUMENTS (2026 - CRA Abolished)
# ===========================================

class PITReliefDocument(BaseModel):
    """
    PIT Relief Document Vault for 2026.
    
    The 2026 reforms ABOLISHED the Consolidated Relief Allowance (CRA)
    and replaced it with specific, document-backed reliefs:
    
    - Rent Relief: 20% of rent paid (capped at ₦500,000)
    - Life Insurance Premium
    - NHF Contribution
    - Pension Contribution
    - NHIS Contribution
    - Gratuity
    
    NRS now requires digital proof for each relief claim.
    """
    
    __tablename__ = "pit_relief_documents"
    
    # Entity
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # User (employee claiming relief)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    # Relief Details
    relief_type: Mapped[ReliefType] = mapped_column(
        SQLEnum(ReliefType),
        nullable=False,
    )
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Amounts
    claimed_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    allowed_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=True,
        comment="After cap applied",
    )
    
    # Rent Relief Specifics
    annual_rent: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=True,
    )
    rent_relief_cap: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("500000"),  # ₦500,000 cap
        nullable=True,
    )
    
    # Document Upload
    document_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    document_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    document_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Verification
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    verification_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Status
    status: Mapped[ReliefStatus] = mapped_column(
        SQLEnum(ReliefStatus),
        default=ReliefStatus.PENDING,
        nullable=False,
    )
    
    # Relationships
    entity: Mapped["BusinessEntity"] = relationship("BusinessEntity")
    user: Mapped["User"] = relationship("User")
    
    def calculate_allowed_amount(self) -> Decimal:
        """Calculate allowed relief amount based on type and caps."""
        if self.relief_type == ReliefType.RENT:
            # 20% of rent, capped at ₦500,000
            rent_relief = self.annual_rent * Decimal("0.20") if self.annual_rent else Decimal("0")
            cap = self.rent_relief_cap or Decimal("500000")
            return min(rent_relief, cap)
        else:
            # Other reliefs: full amount claimed (subject to verification)
            return self.claimed_amount
    
    def __repr__(self) -> str:
        return f"<PITReliefDocument(id={self.id}, type={self.relief_type}, amount={self.claimed_amount})>"


# ===========================================
# CREDIT NOTES (For Rejected Invoices)
# ===========================================

class CreditNote(BaseModel):
    """
    Credit Note for reversing rejected invoices.
    
    When a buyer rejects an invoice within the 72-hour window,
    the app must automatically generate a credit note to reverse
    the tax liability.
    """
    
    __tablename__ = "credit_notes"
    
    # Entity
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Original Invoice
    original_invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Credit Note Details
    credit_note_number: Mapped[str] = mapped_column(String(50), nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Amounts (should match original invoice)
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    vat_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    
    # NRS Submission
    nrs_irn: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        unique=True,
    )
    nrs_submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Status
    status: Mapped[CreditNoteStatus] = mapped_column(
        SQLEnum(CreditNoteStatus),
        default=CreditNoteStatus.DRAFT,
        nullable=False,
    )
    
    # Relationships
    entity: Mapped["BusinessEntity"] = relationship("BusinessEntity")
    original_invoice: Mapped[Optional["Invoice"]] = relationship("Invoice", foreign_keys=[original_invoice_id])
    
    def __repr__(self) -> str:
        return f"<CreditNote(id={self.id}, number={self.credit_note_number}, amount={self.total_amount})>"
