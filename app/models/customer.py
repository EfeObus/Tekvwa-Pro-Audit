"""
Tekvwa Pro Audit - Customer Model

Customer model for tracking customers/clients.
"""

import uuid
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.entity import BusinessEntity
    from app.models.invoice import Invoice


class Customer(BaseModel):
    """
    Customer model for tracking customers and clients.
    
    Used for invoicing and income tracking.
    """
    
    __tablename__ = "customers"
    
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
    
    # Tax Information (for B2B invoicing)
    tin: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        index=True,
        comment="Tax Identification Number (required for B2B e-invoicing)",
    )
    is_business: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="True for B2B, False for B2C",
    )
    
    # Contact
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    contact_person: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Address
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Relationships
    entity: Mapped["BusinessEntity"] = relationship(
        "BusinessEntity",
        back_populates="customers",
    )
    invoices: Mapped[List["Invoice"]] = relationship(
        "Invoice",
        back_populates="customer",
    )
    
    @property
    def requires_tin_for_invoice(self) -> bool:
        """Check if TIN is required for NRS e-invoicing."""
        return self.is_business
    
    def __repr__(self) -> str:
        return f"<Customer(id={self.id}, name={self.name})>"
