"""
Tekvwa Pro Audit - Authentication Schemas

Pydantic schemas for authentication requests and responses.
"""

from datetime import datetime
from typing import Optional, List, Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


# ===========================================
# ACCOUNT TYPE DEFINITIONS
# ===========================================

AccountType = Literal["individual", "small_business", "sme", "school", "non_profit", "corporation"]
SchoolType = Literal["primary", "secondary", "tertiary", "vocational", "other"]
IndustryType = Literal[
    "agriculture", "manufacturing", "retail", "wholesale", "technology", 
    "healthcare", "education", "construction", "real_estate", "financial_services",
    "hospitality", "transportation", "professional_services", "other"
]


# ===========================================
# REQUEST SCHEMAS
# ===========================================

class UserRegisterRequest(BaseModel):
    """
    Comprehensive schema for user registration request.
    
    Supports different account types:
    - Individual: Personal use, minimal info required
    - Small Business: Micro businesses (BN registration)
    - SME: Small & Medium Enterprises (RC registration)
    - School: Educational institutions
    - Non-Profit: NGOs and charities (IT registration)
    - Corporation: Large companies (RC registration + more details)
    """
    # ===== USER DETAILS (All account types) =====
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    phone_number: Optional[str] = Field(None, max_length=20)
    
    # ===== ACCOUNT TYPE =====
    account_type: AccountType = Field(
        default="individual",
        description="Type of account: individual, small_business, sme, school, non_profit, corporation"
    )
    
    # ===== ORGANIZATION/BUSINESS NAME =====
    # For Individual: Optional (will use full name if not provided)
    # For Others: Required
    organization_name: Optional[str] = Field(None, min_length=1, max_length=255)
    
    # ===== ADDRESS FIELDS (All except Individual) =====
    street_address: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    lga: Optional[str] = Field(None, max_length=100, description="Local Government Area")
    postal_code: Optional[str] = Field(None, max_length=20)
    country: str = Field(default="Nigeria", max_length=100)
    
    # ===== NIGERIAN COMPLIANCE FIELDS =====
    # TIN - Required for all business types
    tin: Optional[str] = Field(None, max_length=20, description="Tax Identification Number")
    
    # CAC Registration - Type depends on organization type
    # BN: Business Name (Small Business)
    # RC: Registered Company (SME, Corporation)
    # IT: Incorporated Trustees (Non-Profit)
    cac_registration_number: Optional[str] = Field(None, max_length=50, description="CAC BN/RC/IT Number")
    cac_registration_type: Optional[Literal["BN", "RC", "IT"]] = Field(None, description="CAC registration type")
    date_of_incorporation: Optional[str] = Field(None, description="Date of incorporation (YYYY-MM-DD)")
    
    # NIN - For Individual accounts
    nin: Optional[str] = Field(None, max_length=20, description="National Identification Number")
    
    # ===== BUSINESS-SPECIFIC FIELDS =====
    industry: Optional[IndustryType] = Field(None, description="Industry/Sector")
    employee_count: Optional[Literal["1-5", "6-20", "21-50", "51-100", "101-250", "251-500", "500+"]] = Field(
        None, description="Number of employees"
    )
    annual_revenue_range: Optional[Literal[
        "0-5m", "5m-25m", "25m-100m", "100m-500m", "500m-1b", "1b+"
    ]] = Field(None, description="Annual revenue range in Naira")
    
    # ===== SCHOOL-SPECIFIC FIELDS =====
    school_type: Optional[SchoolType] = Field(None, description="Type of school")
    moe_registration_number: Optional[str] = Field(None, max_length=50, description="Ministry of Education registration")
    
    # ===== NON-PROFIT-SPECIFIC FIELDS =====
    scuml_registration: Optional[str] = Field(None, max_length=50, description="SCUML registration number")
    mission_statement: Optional[str] = Field(None, max_length=1000, description="Organization mission")
    
    # ===== REFERRAL =====
    referral_code: Optional[str] = Field(None, max_length=20, description="Referral code if any")
    
    @field_validator('password')
    @classmethod
    def password_strength(cls, v: str) -> str:
        """Validate password strength."""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v
    
    @field_validator('tin')
    @classmethod
    def validate_tin(cls, v: Optional[str]) -> Optional[str]:
        """Validate TIN format (Nigerian TIN is typically 10-14 digits)."""
        if v:
            v = v.replace("-", "").replace(" ", "")
            if not v.isdigit() or len(v) < 10 or len(v) > 14:
                raise ValueError('TIN must be 10-14 digits')
        return v
    
    @field_validator('nin')
    @classmethod
    def validate_nin(cls, v: Optional[str]) -> Optional[str]:
        """Validate NIN format (Nigerian NIN is 11 digits)."""
        if v:
            v = v.replace(" ", "")
            if not v.isdigit() or len(v) != 11:
                raise ValueError('NIN must be 11 digits')
        return v
    
    @model_validator(mode='after')
    def validate_account_type_requirements(self):
        """Validate required fields based on account type."""
        account_type = self.account_type
        
        # For Individual, organization_name is optional (will use full name)
        if account_type == "individual":
            if not self.organization_name:
                self.organization_name = f"{self.first_name} {self.last_name}"
        else:
            # For all business types, organization_name is required
            if not self.organization_name:
                raise ValueError(f'Organization/Business name is required for {account_type} accounts')
        
        # Business types require address
        if account_type in ["small_business", "sme", "school", "non_profit", "corporation"]:
            if not self.state:
                raise ValueError(f'State is required for {account_type} accounts')
            if not self.city:
                raise ValueError(f'City is required for {account_type} accounts')
        
        # School-specific validation
        if account_type == "school":
            if not self.school_type:
                raise ValueError('School type is required for school accounts')
        
        return self


class UserLoginRequest(BaseModel):
    """Schema for user login request."""
    email: EmailStr
    password: str


class TokenRefreshRequest(BaseModel):
    """Schema for token refresh request."""
    refresh_token: str


class PasswordResetRequest(BaseModel):
    """Schema for password reset request."""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Schema for password reset confirmation."""
    token: str
    new_password: str = Field(..., min_length=8, max_length=100)


class PasswordChangeRequest(BaseModel):
    """Schema for password change request."""
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)


class EmailVerificationRequest(BaseModel):
    """Schema for email verification request."""
    token: str


class ResendVerificationRequest(BaseModel):
    """Schema for resending verification email."""
    email: EmailStr


# ===========================================
# RESPONSE SCHEMAS
# ===========================================

class TokenResponse(BaseModel):
    """Schema for token response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserResponse(BaseModel):
    """Schema for user response."""
    id: UUID
    email: str
    first_name: str
    last_name: str
    phone_number: Optional[str] = None
    role: Optional[str] = None  # Organization role (null for platform staff)
    is_active: bool
    is_verified: bool
    must_reset_password: bool = False  # Force password reset on first login
    organization_id: Optional[UUID] = None  # Null for platform staff
    # RBAC fields
    is_platform_staff: bool = False
    platform_role: Optional[str] = None  # Platform role (null for org users)
    created_at: datetime
    
    class Config:
        from_attributes = True


class UserWithTokenResponse(BaseModel):
    """Schema for user response with tokens."""
    user: UserResponse
    tokens: TokenResponse


class OrganizationResponse(BaseModel):
    """Schema for organization response."""
    id: UUID
    name: str
    slug: str
    subscription_tier: str
    organization_type: Optional[str] = None  # New: organization type
    verification_status: Optional[str] = None  # New: verification status
    is_verified: bool = False  # New: convenience field
    created_at: datetime
    
    class Config:
        from_attributes = True


class EntityAccessResponse(BaseModel):
    """Schema for entity access response."""
    entity_id: UUID
    entity_name: str
    can_write: bool
    can_delete: bool


class CurrentUserResponse(BaseModel):
    """Schema for current user with organization and entities."""
    user: UserResponse
    organization: Optional[OrganizationResponse] = None  # Null for platform staff
    entity_access: List[EntityAccessResponse] = []
    # RBAC permissions summary
    permissions: List[str] = []  # List of permission strings user has


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    success: bool = True


# ===========================================
# RBAC SCHEMAS
# ===========================================

class RolePermissionsResponse(BaseModel):
    """Schema for role permissions."""
    role: str
    role_type: str  # "platform" or "organization"
    permissions: List[str]


class UserPermissionsResponse(BaseModel):
    """Schema for user's permissions."""
    user_id: UUID
    is_platform_staff: bool
    role: str
    permissions: List[str]
