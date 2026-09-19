"""
Tekvwa Pro Audit - Vendor Model

Vendor model for supply chain management with TIN verification.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.entity import BusinessEntity
    from app.models.transaction import Transaction


class Vendor(BaseModel):
    """
    Vendor model for tracking suppliers and service providers.
    
    Includes TIN verification status and VAT registration tracking
    for proper Input VAT recovery.
    """
    
    __tablename__ = "vendors"
    
    # Entity
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Basic Info
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    trading_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Tax Information
    tin: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        index=True,
        comment="Tax Identification Number",
    )
    tin_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    tin_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    tin_registered_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Name returned from TIN verification",
    )
    
    # VAT Status
    is_vat_registered: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="True if vendor is VAT registered",
    )
    
    # Withholding Tax Settings
    default_wht_rate: Mapped[Optional[float]] = mapped_column(
        nullable=True,
        comment="Default withholding tax rate for this vendor (0-100)",
    )
    
    # Contact
    contact_person: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # Address
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[str] = mapped_column(String(100), default="Nigeria", nullable=False)
    
    # Bank Details
    bank_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bank_account_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    bank_account_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Relationships
    entity: Mapped["BusinessEntity"] = relationship(
        "BusinessEntity",
        back_populates="vendors",
    )
    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction",
        back_populates="vendor",
    )
    
    @property
    def can_claim_input_vat(self) -> bool:
        """Check if Input VAT can be claimed for purchases from this vendor."""
        return self.is_vat_registered and self.tin_verified
    
    def __repr__(self) -> str:
        return f"<Vendor(id={self.id}, name={self.name}, tin={self.tin})>"
