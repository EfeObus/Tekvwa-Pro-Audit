"""
Tekvwa Pro Audit - Inventory Schemas

Pydantic schemas for inventory management.
"""

from datetime import date, datetime
from typing import List, Optional
from uuid import UUID
from decimal import Decimal

from pydantic import BaseModel, Field, ConfigDict


# ===========================================
# INVENTORY ITEM SCHEMAS
# ===========================================

class InventoryItemBase(BaseModel):
    """Base schema for inventory items."""
    sku: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    barcode: Optional[str] = Field(None, max_length=50)
    category: Optional[str] = Field(None, max_length=100)
    unit_cost: float = Field(0, ge=0)
    unit_price: float = Field(0, ge=0)
    reorder_level: int = Field(0, ge=0)
    reorder_quantity: int = Field(0, ge=0)
    unit_of_measure: str = Field("pcs", max_length=20)
    is_tracked: bool = Field(True)


class InventoryItemCreate(InventoryItemBase):
    """Schema for creating an inventory item."""
    quantity_on_hand: int = Field(0, ge=0)


class InventoryItemUpdate(BaseModel):
    """Schema for updating an inventory item."""
    sku: Optional[str] = Field(None, min_length=1, max_length=50)
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    barcode: Optional[str] = Field(None, max_length=50)
    category: Optional[str] = Field(None, max_length=100)
    unit_cost: Optional[float] = Field(None, ge=0)
    unit_price: Optional[float] = Field(None, ge=0)
    reorder_level: Optional[int] = Field(None, ge=0)
    reorder_quantity: Optional[int] = Field(None, ge=0)
    unit_of_measure: Optional[str] = Field(None, max_length=20)
    is_tracked: Optional[bool] = None
    is_active: Optional[bool] = None


class InventoryItemResponse(BaseModel):
    """Response schema for inventory item."""
    id: UUID
    entity_id: UUID
    sku: str
    name: str
    description: Optional[str]
    barcode: Optional[str]
    category: Optional[str]
    unit_cost: float
    unit_price: float
    quantity_on_hand: int
    reorder_level: int
    reorder_quantity: int
    unit_of_measure: str
    is_active: bool
    is_tracked: bool
    is_low_stock: bool
    stock_value: float
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class InventoryItemListResponse(BaseModel):
    """Response schema for inventory item list."""
    items: List[InventoryItemResponse]
    total: int
    low_stock_count: int


# ===========================================
# STOCK MOVEMENT SCHEMAS
# ===========================================

class StockMovementCreate(BaseModel):
    """Schema for creating a stock movement."""
    movement_type: str = Field(..., description="purchase, sale, adjustment, transfer, write_off, return")
    quantity: int = Field(..., description="Positive for inbound, negative for outbound")
    unit_cost: float = Field(..., ge=0)
    reference: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None
    movement_date: date


class StockMovementResponse(BaseModel):
    """Response schema for stock movement."""
    id: UUID
    item_id: UUID
    movement_type: str
    quantity: int
    unit_cost: float
    reference: Optional[str]
    notes: Optional[str]
    movement_date: date
    created_at: datetime
    created_by: Optional[UUID]

    model_config = ConfigDict(from_attributes=True)


# ===========================================
# STOCK ADJUSTMENT SCHEMAS
# ===========================================

class StockAdjustmentRequest(BaseModel):
    """Schema for stock adjustment."""
    quantity_change: int = Field(..., description="Positive to add, negative to subtract")
    reason: str = Field(..., min_length=1)
    reference: Optional[str] = Field(None, max_length=100)
    adjustment_date: Optional[date] = None


class StockReceiveRequest(BaseModel):
    """Schema for receiving stock (purchase)."""
    quantity: int = Field(..., gt=0)
    unit_cost: float = Field(..., ge=0)
    reference: Optional[str] = Field(None, max_length=100, description="PO number")
    notes: Optional[str] = None
    receive_date: Optional[date] = None


class StockSaleRequest(BaseModel):
    """Schema for recording a sale."""
    quantity: int = Field(..., gt=0)
    reference: Optional[str] = Field(None, max_length=100, description="Invoice number")
    notes: Optional[str] = None
    sale_date: Optional[date] = None


# ===========================================
# WRITE-OFF SCHEMAS
# ===========================================

class StockWriteOffCreate(BaseModel):
    """Schema for creating a stock write-off."""
    quantity: int = Field(..., gt=0)
    reason: str = Field(..., description="expired, damaged, obsolete, theft, other")
    notes: Optional[str] = None
    documentation_url: Optional[str] = Field(None, max_length=500)
    write_off_date: Optional[date] = None
    is_tax_deductible: bool = Field(True)


class StockWriteOffResponse(BaseModel):
    """Response schema for stock write-off."""
    id: UUID
    item_id: UUID
    quantity: int
    unit_cost: float
    total_value: float
    reason: str
    notes: Optional[str]
    documentation_url: Optional[str]
    write_off_date: date
    is_tax_deductible: bool
    reviewed: bool
    reviewed_at: Optional[datetime]
    created_at: datetime
    created_by: Optional[UUID]

    model_config = ConfigDict(from_attributes=True)


class StockWriteOffReviewRequest(BaseModel):
    """Schema for reviewing a write-off."""
    is_tax_deductible: bool = Field(True)
    notes: Optional[str] = None


# ===========================================
# INVENTORY REPORT SCHEMAS
# ===========================================

class InventorySummaryResponse(BaseModel):
    """Summary of inventory status."""
    total_items: int
    active_items: int
    inactive_items: int
    total_quantity: int
    total_stock_value: float
    low_stock_count: int
    out_of_stock_count: int


class LowStockAlertResponse(BaseModel):
    """Low stock alert item."""
    item_id: UUID
    sku: str
    name: str
    quantity_on_hand: int
    reorder_level: int
    reorder_quantity: int


class InventoryValuationResponse(BaseModel):
    """Inventory valuation report."""
    valuation_date: date
    total_items: int
    total_quantity: int
    total_value_at_cost: float
    total_value_at_price: float
    potential_profit: float
    items: List["InventoryItemResponse"]
