"""
Tekvwa Pro Audit - Vendor Schemas

Pydantic schemas for vendor management with TIN verification.
"""

from datetime import date, datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# ===========================================
# REQUEST SCHEMAS
# ===========================================

class VendorCreateRequest(BaseModel):
    """Schema for creating a vendor."""
    name: str = Field(..., min_length=1, max_length=255)
    tin: Optional[str] = Field(None, max_length=20, description="Tax Identification Number")
    
    # Contact Information
    contact_person: Optional[str] = Field(None, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    
    # Address
    address: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    
    # Bank Details
    bank_name: Optional[str] = Field(None, max_length=100)
    bank_account_number: Optional[str] = Field(None, max_length=20)
    bank_account_name: Optional[str] = Field(None, max_length=255)
    
    # Tax Settings
    is_vat_registered: bool = False
    default_wht_rate: Optional[float] = Field(None, ge=0, le=100, description="Default WHT rate for this vendor")
    
    notes: Optional[str] = None


class VendorUpdateRequest(BaseModel):
    """Schema for updating a vendor."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    tin: Optional[str] = Field(None, max_length=20)
    
    # Contact Information
    contact_person: Optional[str] = Field(None, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    
    # Address
    address: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    
    # Bank Details
    bank_name: Optional[str] = Field(None, max_length=100)
    bank_account_number: Optional[str] = Field(None, max_length=20)
    bank_account_name: Optional[str] = Field(None, max_length=255)
    
    # Tax Settings
    is_vat_registered: Optional[bool] = None
    default_wht_rate: Optional[float] = Field(None, ge=0, le=100)
    
    notes: Optional[str] = None


class TINVerificationRequest(BaseModel):
    """Request to verify a vendor's TIN."""
    vendor_id: UUID


# ===========================================
# RESPONSE SCHEMAS
# ===========================================

class VendorResponse(BaseModel):
    """Schema for vendor response."""
    id: UUID
    entity_id: UUID
    name: str
    tin: Optional[str] = None
    
    # Contact Information
    contact_person: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    
    # Address
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: str
    
    # Bank Details
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_account_name: Optional[str] = None
    
    # Tax Settings
    is_vat_registered: bool
    default_wht_rate: Optional[float] = None
    
    # TIN Verification Status
    tin_verified: bool
    tin_verified_at: Optional[datetime] = None
    
    # Stats
    total_paid: float
    transaction_count: int
    
    notes: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class VendorListResponse(BaseModel):
    """List of vendors response."""
    vendors: List[VendorResponse]
    total: int


class VendorSummaryResponse(BaseModel):
    """Brief vendor info for dropdowns."""
    id: UUID
    name: str
    tin: Optional[str] = None
    tin_verified: bool
    is_vat_registered: bool
    
    class Config:
        from_attributes = True


class TINVerificationResponse(BaseModel):
    """Response for TIN verification."""
    vendor_id: UUID
    tin: str
    verified: bool
    verified_at: Optional[datetime] = None
    verification_message: str
