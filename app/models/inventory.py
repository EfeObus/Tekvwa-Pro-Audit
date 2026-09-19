"""
Tekvwa Pro Audit - Inventory Models

Inventory models for stock tracking and write-offs.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, AuditMixin

if TYPE_CHECKING:
    from app.models.entity import BusinessEntity


class StockMovementType(str, Enum):
    """Type of stock movement."""
    PURCHASE = "purchase"       # Stock received from purchase
    SALE = "sale"               # Stock sold
    ADJUSTMENT = "adjustment"   # Manual adjustment
    TRANSFER = "transfer"       # Transfer between locations
    WRITE_OFF = "write_off"     # Damaged/expired goods
    RETURN = "return"           # Customer return


class WriteOffReason(str, Enum):
    """Reason for stock write-off."""
    EXPIRED = "expired"
    DAMAGED = "damaged"
    OBSOLETE = "obsolete"
    THEFT = "theft"
    OTHER = "other"


class InventoryItem(BaseModel):
    """
    Inventory item model for stock tracking.
    """
    
    __tablename__ = "inventory_items"
    
    # Entity
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Basic Info
    sku: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Stock Keeping Unit",
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    barcode: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    
    # Category
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Pricing
    unit_cost: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        comment="Cost price per unit",
    )
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
        default=Decimal("0.00"),
        comment="Selling price per unit",
    )
    
    # Stock Levels
    quantity_on_hand: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    reorder_level: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Alert when stock falls below this level",
    )
    reorder_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Suggested quantity to reorder",
    )
    
    # Unit
    unit_of_measure: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pcs",
        comment="e.g., pcs, kg, liters",
    )
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_tracked: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="True if stock levels should be tracked",
    )
    
    # Relationships
    entity: Mapped["BusinessEntity"] = relationship(
        "BusinessEntity",
        back_populates="inventory_items",
    )
    stock_movements: Mapped[List["StockMovement"]] = relationship(
        "StockMovement",
        back_populates="item",
        cascade="all, delete-orphan",
    )
    write_offs: Mapped[List["StockWriteOff"]] = relationship(
        "StockWriteOff",
        back_populates="item",
        cascade="all, delete-orphan",
    )
    
    @property
    def is_low_stock(self) -> bool:
        """Check if stock is below reorder level."""
        return self.quantity_on_hand <= self.reorder_level
    
    @property
    def stock_value(self) -> Decimal:
        """Calculate total stock value at cost."""
        return self.unit_cost * self.quantity_on_hand
    
    def __repr__(self) -> str:
        return f"<InventoryItem(id={self.id}, sku={self.sku}, qty={self.quantity_on_hand})>"


class StockMovement(BaseModel, AuditMixin):
    """
    Stock movement model for tracking inventory changes.
    """
    
    __tablename__ = "stock_movements"
    
    # Item
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inventory_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Movement Details
    movement_type: Mapped[StockMovementType] = mapped_column(
        SQLEnum(StockMovementType),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Positive for inbound, negative for outbound",
    )
    unit_cost: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    
    # Reference
    reference: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="PO number, invoice number, etc.",
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Date
    movement_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Relationships
    item: Mapped["InventoryItem"] = relationship(
        "InventoryItem",
        back_populates="stock_movements",
    )
    
    def __repr__(self) -> str:
        return f"<StockMovement(id={self.id}, type={self.movement_type}, qty={self.quantity})>"


class StockWriteOff(BaseModel, AuditMixin):
    """
    Stock write-off model for tracking damaged/expired goods.
    
    Write-offs are flagged for tax deduction eligibility.
    """
    
    __tablename__ = "stock_write_offs"
    
    # Item
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inventory_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Write-off Details
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    total_value: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2),
        nullable=False,
    )
    
    # Reason
    reason: Mapped[WriteOffReason] = mapped_column(
        SQLEnum(WriteOffReason),
        nullable=False,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Documentation
    documentation_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Photos, inspection reports",
    )
    
    # Date
    write_off_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Tax Treatment
    is_tax_deductible: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Eligible for tax deduction",
    )
    reviewed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Reviewed by accountant/auditor",
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Relationships
    item: Mapped["InventoryItem"] = relationship(
        "InventoryItem",
        back_populates="write_offs",
    )
    
    def __repr__(self) -> str:
        return f"<StockWriteOff(id={self.id}, reason={self.reason}, value={self.total_value})>"
