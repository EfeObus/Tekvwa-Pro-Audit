"""
Tekvwa Pro Audit - Category Schemas

Pydantic schemas for category management with WREN classification.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, Field


class VATTreatment(str, Enum):
    """VAT treatment options."""
    STANDARD = "standard"       # 7.5% VAT
    ZERO_RATED = "zero_rated"   # 0% VAT (exports, basic food)
    EXEMPT = "exempt"           # Not subject to VAT
    INPUT_ONLY = "input_only"   # Input VAT claimable only


class WRENType(str, Enum):
    """WREN classification types for tax categorization."""
    WORK = "work"           # W - Salary, wages, services rendered
    RENT = "rent"           # R - Rental income/expenses
    EQUITY = "equity"       # E - Dividends, profit share, capital gains
    ENTERPRISE = "enterprise"  # N - Business/trade income/expenses


# ===========================================
# REQUEST SCHEMAS
# ===========================================

class CategoryCreateRequest(BaseModel):
    """Schema for creating a category."""
    name: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=20, description="Category code (e.g., '4000', 'OPS-001')")
    description: Optional[str] = Field(None, max_length=500)
    
    # Classification
    category_type: str = Field(..., description="'income', 'expense', or 'asset'")
    wren_type: WRENType = Field(WRENType.ENTERPRISE, description="WREN classification")
    vat_treatment: VATTreatment = Field(VATTreatment.STANDARD, description="VAT treatment")
    
    # Parent category (for hierarchy)
    parent_id: Optional[UUID] = None
    
    # Tax settings
    is_wht_applicable: bool = Field(False, description="Subject to Withholding Tax")
    wht_rate: Optional[float] = Field(None, ge=0, le=100, description="WHT rate if applicable")


class CategoryUpdateRequest(BaseModel):
    """Schema for updating a category."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    code: Optional[str] = Field(None, min_length=1, max_length=20)
    description: Optional[str] = Field(None, max_length=500)
    
    # Classification
    category_type: Optional[str] = None
    wren_type: Optional[WRENType] = None
    vat_treatment: Optional[VATTreatment] = None
    
    # Parent
    parent_id: Optional[UUID] = None
    
    # Tax settings
    is_wht_applicable: Optional[bool] = None
    wht_rate: Optional[float] = Field(None, ge=0, le=100)


# ===========================================
# RESPONSE SCHEMAS
# ===========================================

class CategoryResponse(BaseModel):
    """Schema for category response."""
    id: UUID
    entity_id: UUID
    name: str
    code: str
    description: Optional[str] = None
    category_type: str
    wren_type: str
    vat_treatment: str
    parent_id: Optional[UUID] = None
    is_wht_applicable: bool
    wht_rate: Optional[float] = None
    is_system_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class CategoryWithChildrenResponse(CategoryResponse):
    """Category with nested children."""
    children: List["CategoryWithChildrenResponse"] = []


class CategoryListResponse(BaseModel):
    """List of categories response."""
    categories: List[CategoryResponse]
    total: int


class CategoryTreeResponse(BaseModel):
    """Hierarchical category tree response."""
    categories: List[CategoryWithChildrenResponse]


# For Pydantic v2 self-referencing
CategoryWithChildrenResponse.model_rebuild()
