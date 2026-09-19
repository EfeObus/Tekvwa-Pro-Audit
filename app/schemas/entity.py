"""
Tekvwa Pro Audit - Entity Schemas

Pydantic schemas for business entity management.
"""

from datetime import date, datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field, EmailStr


# ===========================================
# REQUEST SCHEMAS
# ===========================================

class EntityCreateRequest(BaseModel):
    """Schema for creating a business entity."""
    name: str = Field(..., min_length=1, max_length=255)
    legal_name: Optional[str] = Field(None, max_length=255)
    tin: Optional[str] = Field(None, max_length=20, description="Tax Identification Number")
    rc_number: Optional[str] = Field(None, max_length=20, description="CAC Registration Number")
    
    # Address
    address_line1: Optional[str] = Field(None, max_length=255)
    address_line2: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    
    # Contact
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    website: Optional[str] = Field(None, max_length=255)
    
    # Financial Settings
    fiscal_year_start_month: int = Field(1, ge=1, le=12, description="Month when fiscal year starts")
    currency: str = Field("NGN", max_length=3)
    
    # Tax Settings
    is_vat_registered: bool = False
    vat_registration_date: Optional[date] = None
    annual_turnover_threshold: bool = Field(
        True,
        description="True if turnover <= ₦50M (0% CIT eligible)"
    )


class EntityUpdateRequest(BaseModel):
    """Schema for updating a business entity."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    legal_name: Optional[str] = Field(None, max_length=255)
    tin: Optional[str] = Field(None, max_length=20)
    rc_number: Optional[str] = Field(None, max_length=20)
    
    # Address
    address_line1: Optional[str] = Field(None, max_length=255)
    address_line2: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    
    # Contact
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    website: Optional[str] = Field(None, max_length=255)
    
    # Financial Settings
    fiscal_year_start_month: Optional[int] = Field(None, ge=1, le=12)
    currency: Optional[str] = Field(None, max_length=3)
    
    # Tax Settings
    is_vat_registered: Optional[bool] = None
    vat_registration_date: Optional[date] = None
    annual_turnover_threshold: Optional[bool] = None


# ===========================================
# RESPONSE SCHEMAS
# ===========================================

class EntityResponse(BaseModel):
    """Schema for business entity response."""
    id: UUID
    organization_id: UUID
    name: str
    legal_name: Optional[str] = None
    tin: Optional[str] = None
    rc_number: Optional[str] = None
    
    # Address
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: str
    full_address: str
    
    # Contact
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    
    # Financial Settings
    fiscal_year_start_month: int
    currency: str
    
    # Tax Settings
    is_vat_registered: bool
    vat_registration_date: Optional[date] = None
    annual_turnover_threshold: bool
    
    # Status
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class EntityListResponse(BaseModel):
    """Schema for list of entities response."""
    entities: List[EntityResponse]
    total: int


class EntitySummaryResponse(BaseModel):
    """Brief entity info for dropdowns/selection."""
    id: UUID
    name: str
    tin: Optional[str] = None
    is_active: bool
    
    class Config:
        from_attributes = True
