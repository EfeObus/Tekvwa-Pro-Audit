"""
Tekvwa Pro Audit - Fixed Asset Register Model

Fixed Asset Register for tracking capital assets, depreciation, and capital gains.

The 2026 Nigeria Tax Administration Act merges capital gains into profit planning:
- Capital gains now taxed at flat CIT rate (30% for large companies)
- Input VAT on fixed assets is now recoverable (with valid IRN)
- Depreciation affects assessable profit calculation
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.entity import BusinessEntity
    from app.models.user import User


class AssetCategory(str, Enum):
    """Fixed asset categories with standard depreciation rates."""
    LAND = "land"                           # 0% - land doesn't depreciate
    BUILDINGS = "buildings"                 # 10%
    PLANT_MACHINERY = "plant_machinery"     # 25%
    FURNITURE_FITTINGS = "furniture_fittings"  # 20%
    MOTOR_VEHICLES = "motor_vehicles"       # 25%
    COMPUTER_EQUIPMENT = "computer_equipment"  # 25%
    OFFICE_EQUIPMENT = "office_equipment"   # 20%
    LEASEHOLD_IMPROVEMENTS = "leasehold_improvements"  # Term of lease
    INTANGIBLE_ASSETS = "intangible_assets"  # 12.5%
    OTHER = "other"                         # Custom rate


class AssetStatus(str, Enum):
    """Status of fixed asset."""
    ACTIVE = "active"           # In use
    DISPOSED = "disposed"       # Sold or disposed
    WRITTEN_OFF = "written_off" # Fully written off
    UNDER_REPAIR = "under_repair"
    IDLE = "idle"               # Not currently in use


class DepreciationMethod(str, Enum):
    """Depreciation calculation method."""
    STRAIGHT_LINE = "straight_line"      # Even depreciation over useful life
    REDUCING_BALANCE = "reducing_balance"  # Nigerian tax standard
    UNITS_OF_PRODUCTION = "units_of_production"


class DisposalType(str, Enum):
    """Type of asset disposal."""
    SALE = "sale"
    TRADE_IN = "trade_in"
    SCRAPPED = "scrapped"
    DONATED = "donated"
    THEFT = "theft"
    INSURANCE_CLAIM = "insurance_claim"


# Standard depreciation rates per Nigerian tax law
STANDARD_DEPRECIATION_RATES = {
    AssetCategory.LAND: Decimal("0"),
    AssetCategory.BUILDINGS: Decimal("10"),
    AssetCategory.PLANT_MACHINERY: Decimal("25"),
    AssetCategory.FURNITURE_FITTINGS: Decimal("20"),
    AssetCategory.MOTOR_VEHICLES: Decimal("25"),
    AssetCategory.COMPUTER_EQUIPMENT: Decimal("25"),
    AssetCategory.OFFICE_EQUIPMENT: Decimal("20"),
    AssetCategory.LEASEHOLD_IMPROVEMENTS: Decimal("10"),  # Default, actual based on lease
    AssetCategory.INTANGIBLE_ASSETS: Decimal("12.5"),
    AssetCategory.OTHER: Decimal("20"),
}


class FixedAsset(BaseModel):
    """
    Fixed Asset Register entry.
    
    Tracks capital assets for:
    - Depreciation calculation
    - Capital gains on disposal (2026: taxed at CIT rate)
    - Input VAT recovery (2026: now allowed on capital expenditure)
    - Development Levy threshold calculation

    Finding 50 (docs/FINDING_50_SCOPE.md): app/services/fixed_asset_service.py's create_asset()
    already accepted both this model's field names AND the live table's real column names as
    aliased parameters (vendor_invoice_number/invoice_number, insured_value/insurance_value,
    insurance_expiry/insurance_expiry_date) -- but only ever wrote to this model's names, meaning
    the DB never actually had columns for them. app/services/reports_service.py's real,
    independent read of `asset.disposal_amount` confirmed the model's naming (not the DB's
    disposal_proceeds) is the one real code outside this file depends on, so direction (A) was
    used throughout: migrated the DB to add vendor_invoice_number/insured_value/insurance_expiry/
    disposal_amount/vat_recovered/department/assigned_to/warranty_expiry/notes/asset_metadata. The
    live table's own invoice_number/insurance_value/insurance_expiry_date/disposal_proceeds stay
    in place, unmapped -- fully superseded duplicates of the fields above, same treatment as
    bank_statement_transactions' `is_matched`. Genuinely distinct DB-only fields (not duplicates)
    were added here for parity: depreciation_start_date/disposal_buyer_name/disposal_buyer_tin/
    vat_recovery_eligible/vat_recovery_claimed/vat_recovery_date/created_by_id/updated_by_id/
    disposed_by_id (all dormant, confirmed via grep with zero references), plus condition/
    is_insured, which create_asset() already accepted as parameters but silently never wired into
    the constructor -- wired up here.
    """
    
    __tablename__ = "fixed_assets"
    
    # Entity
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Asset Identification
    asset_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Unique asset identifier (e.g., FA-001)",
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Classification
    category: Mapped[AssetCategory] = mapped_column(
        SQLEnum(AssetCategory),
        nullable=False,
        index=True,
    )
    status: Mapped[AssetStatus] = mapped_column(
        SQLEnum(AssetStatus),
        default=AssetStatus.ACTIVE,
        nullable=False,
    )
    
    # Location & Assignment
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    assigned_to: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Acquisition Details
    acquisition_date: Mapped[date] = mapped_column(Date, nullable=False)
    acquisition_cost: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
        comment="Original purchase price",
    )
    vendor_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    vendor_invoice_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # NRS/VAT Recovery (2026 Compliance)
    vendor_irn: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Vendor NRS Invoice Reference Number for VAT recovery",
    )
    vat_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0"),
        nullable=False,
    )
    vat_recovered: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="True if input VAT has been recovered",
    )
    
    # Depreciation Settings
    depreciation_method: Mapped[DepreciationMethod] = mapped_column(
        SQLEnum(DepreciationMethod),
        default=DepreciationMethod.REDUCING_BALANCE,
        nullable=False,
    )
    depreciation_rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2),
        nullable=False,
        comment="Annual depreciation rate as percentage",
    )
    useful_life_years: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Estimated useful life in years",
    )
    residual_value: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0"),
        nullable=False,
        comment="Expected value at end of useful life",
    )
    
    # Depreciation Tracking
    accumulated_depreciation: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        default=Decimal("0"),
        nullable=False,
    )
    last_depreciation_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    depreciation_start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Disposal Details (for capital gains calculation)
    disposal_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    disposal_type: Mapped[Optional[DisposalType]] = mapped_column(
        SQLEnum(DisposalType),
        nullable=True,
    )
    disposal_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=True,
        comment="Proceeds from disposal",
    )
    disposal_buyer_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    disposal_buyer_tin: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    disposal_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Insurance
    insured_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=True,
    )
    insurance_policy_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    insurance_expiry: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_insured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # VAT Recovery (richer tracking alongside vat_recovered)
    vat_recovery_eligible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    vat_recovery_claimed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    vat_recovery_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Additional Info
    serial_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    condition: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    warranty_expiry: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    asset_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Audit trail
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    updated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    disposed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    
    # Relationships
    entity: Mapped["BusinessEntity"] = relationship("BusinessEntity")
    depreciation_entries: Mapped[List["DepreciationEntry"]] = relationship(
        "DepreciationEntry",
        back_populates="asset",
        cascade="all, delete-orphan",
    )
    
    @property
    def net_book_value(self) -> Decimal:
        """Calculate current net book value."""
        return self.acquisition_cost - self.accumulated_depreciation
    
    @property
    def is_fully_depreciated(self) -> bool:
        """Check if asset is fully depreciated."""
        return self.net_book_value <= self.residual_value
    
    @property
    def capital_gain_on_disposal(self) -> Optional[Decimal]:
        """Calculate capital gain (or loss) on disposal."""
        if not self.disposal_amount:
            return None
        return self.disposal_amount - self.net_book_value
    
    def calculate_annual_depreciation(self) -> Decimal:
        """Calculate annual depreciation amount."""
        if self.is_fully_depreciated:
            return Decimal("0")
        
        if self.depreciation_method == DepreciationMethod.STRAIGHT_LINE:
            depreciable_amount = self.acquisition_cost - self.residual_value
            if self.useful_life_years and self.useful_life_years > 0:
                return depreciable_amount / self.useful_life_years
            return Decimal("0")
        
        elif self.depreciation_method == DepreciationMethod.REDUCING_BALANCE:
            return self.net_book_value * (self.depreciation_rate / 100)
        
        return Decimal("0")
    
    def __repr__(self) -> str:
        return f"<FixedAsset(id={self.id}, code={self.asset_code}, nbv={self.net_book_value})>"


class DepreciationEntry(BaseModel):
    """
    Monthly/Annual depreciation entry for fixed assets.

    Used for:
    - Tracking depreciation over time
    - Generating depreciation reports
    - Calculating assessable profit (less depreciation)

    Finding 50 (docs/FINDING_50_SCOPE.md): the live table represented periods as a fiscal-year-end
    plus a start/end date range (fiscal_year_end/period_start/period_end), and tracked
    depreciation_rate_used/is_posted instead of depreciation_method/posted_by_id -- but
    app/services/fixed_asset_service.py's only real construction site already used this model's
    simpler period_year/period_month representation plus depreciation_method/posted_by_id
    directly, meaning every real call has always failed with an UndefinedColumnError. Migrated the
    DB to match (direction (A)); entity_id (present on the live table, NOT NULL, but absent here)
    is now wired up from the asset's own entity_id at the one real construction site.
    fiscal_year_end/period_start/period_end/depreciation_rate_used stay in place, unmapped --
    superseded by period_year/period_month/depreciation_rate above.
    """

    __tablename__ = "depreciation_entries"

    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Asset
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fixed_assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Period
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Month (1-12) for monthly depreciation, NULL for annual",
    )
    
    # Values
    opening_book_value: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    depreciation_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    closing_book_value: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    
    # Method used
    depreciation_method: Mapped[DepreciationMethod] = mapped_column(
        SQLEnum(DepreciationMethod),
        nullable=False,
    )
    depreciation_rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2),
        nullable=False,
    )
    
    # Posted by
    is_posted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    posted_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    asset: Mapped["FixedAsset"] = relationship(
        "FixedAsset",
        back_populates="depreciation_entries",
    )
    
    def __repr__(self) -> str:
        return f"<DepreciationEntry(asset_id={self.asset_id}, period={self.period_year}/{self.period_month}, amount={self.depreciation_amount})>"
